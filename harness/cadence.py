"""Deliverable liveness independent of sweep workers. Evaluation is strictly read-only.

Flat CADENCE.toml works with both supported Python TOML readers. JSONL evidence
is authoritative when configured; only its timestamp field is retained, and an
optional success_field excludes failed sweep attempts. No evidence text reaches
alerts, push arguments, state, or diagnostics.
"""
import datetime as dt
import glob
import json
import math
from pathlib import Path
import re
import lane_alerts

UTC = dt.timezone.utc
# Fixed release epoch: restarting the monitor or creating a lane never resets grace.
SHIPPED_UTC = '2026-11-03T14:18:58+00:00'
BOOTSTRAP_HOURS = 26
NAME = re.compile(r'[a-z0-9][a-z0-9_-]*')
FIELDS = frozenset(('deliverable', 'every_hours', 'warn_hours', 'window_opens',
                    'window_closes', 'evidence_root', 'evidence_globs',
                    'evidence_jsonl', 'timestamp_field', 'success_field', 'owner_session'))


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be an ISO UTC string')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() != dt.timedelta(0):
        raise ValueError('timestamp must be ISO UTC')
    return result.astimezone(UTC)


def text_field(value):
    return (isinstance(value, str) and bool(value.strip())
            and len(value) <= 160 and all(c.isprintable() for c in value))


def load(lane, rh):
    cfg = rh.config(lane / 'CADENCE.toml')
    if set(cfg) - FIELDS:
        raise ValueError('unknown CADENCE field')
    for key in ('deliverable', 'owner_session'):
        if not text_field(cfg.get(key)):
            raise ValueError('invalid ' + key)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}', cfg['owner_session']):
        raise ValueError('invalid owner_session')
    every = cfg.get('every_hours')
    if type(every) not in (int, float) or not math.isfinite(every) or every <= 0:
        raise ValueError('invalid every_hours')
    cfg.setdefault('warn_hours', every * .7)
    warn = cfg['warn_hours']
    if type(warn) not in (int, float) or not math.isfinite(warn) or not 0 <= warn < every:
        raise ValueError('invalid warn_hours')
    for key in ('window_opens', 'window_closes'):
        if key in cfg:
            stamp(cfg[key])
    if ('window_opens' in cfg and 'window_closes' in cfg
            and stamp(cfg['window_opens']) >= stamp(cfg['window_closes'])):
        raise ValueError('invalid window order')
    patterns = cfg.get('evidence_globs')
    if patterns is None and 'evidence_jsonl' in cfg:
        patterns = cfg['evidence_globs'] = []
    if (not isinstance(patterns, list) or (not patterns and 'evidence_jsonl' not in cfg)
            or any(not isinstance(p, str) or not p.strip() or '\0' in p for p in patterns)):
        raise ValueError('evidence_globs must be a path array (or configure evidence_jsonl)')
    if 'evidence_root' in cfg and (not isinstance(cfg['evidence_root'], str)
                                   or not cfg['evidence_root'].strip() or '\0' in cfg['evidence_root']):
        raise ValueError('invalid evidence_root')
    if 'evidence_jsonl' in cfg:
        for key in ('evidence_jsonl', 'timestamp_field'):
            if not isinstance(cfg.get(key), str) or not cfg[key].strip() or '\0' in cfg[key]:
                raise ValueError('invalid ' + key)
        if 'success_field' in cfg and not text_field(cfg['success_field']):
            raise ValueError('invalid success_field')
    elif 'timestamp_field' in cfg or 'success_field' in cfg:
        raise ValueError('timestamp_field and success_field require evidence_jsonl')
    return cfg


def path_at(value, base):
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def delivery_time(lane, cfg, clock):
    base = path_at(cfg.get('evidence_root', '.'), lane)
    if 'evidence_jsonl' in cfg:
        # An explicit receipt log is authoritative, including when absent/empty.
        # Falling back to report mtimes here would count a failed worker as delivery.
        newest = None
        try:
            with path_at(cfg['evidence_jsonl'], base).open() as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            continue
                        if 'success_field' in cfg and row.get(cfg['success_field']) is not True:
                            continue
                        when = stamp(row.get(cfg['timestamp_field']))
                        if when <= clock and (newest is None or when > newest):
                            newest = when
                    except (ValueError, TypeError, OverflowError):
                        continue
        except FileNotFoundError:
            pass
        return newest
    newest = None
    for pattern in cfg['evidence_globs']:
        for name in glob.iglob(str(path_at(pattern, base)), recursive=True):
            path = Path(name)
            if path.is_file():
                when = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
                if when <= clock and (newest is None or when > newest):
                    newest = when
    return newest


def last_sweep_refusal(lane, rh):
    """The refusal text of the lane's latest finished sweep, if it was refused before doing any work.

    virtual-embryo, 11-07: its sweep refused instantly on the disk floor and the lane read as STALLED
    for 57 hours, which looked like an idle session rather than a precondition nobody had fixed. The
    status stays STALLED (alerts and lint key on it), and this says why. Only the harness's own
    refusal messages are echoed, cut short."""
    try:
        rows = rh.rows(lane / 'SWEEP_RUNS.jsonl')
    except (OSError, ValueError):
        return None
    for row in reversed(rows):
        if row.get('status') != 'finished':
            continue
        if row.get('ok') is False:
            for err in row.get('errors') or []:
                if isinstance(err, str) and 'refused' in err:
                    return err[:240]
        return None
    return None


def evaluate(lane, rh, now=None):
    """One lane; no lane locks, worker config reads, mkdirs, alerts or pushes."""
    clock = stamp(now or rh.now())
    result = dict(lane=lane.name, status='UNCONFIGURED', deliverable=None,
                  owner_session=None, hours_since_last_delivery=None,
                  last_delivery=None, broken=False)
    try:
        # stat distinguishes a missing config from unreadable/dangling config.
        path = lane / 'CADENCE.toml'
        try:
            path.lstat()
        except FileNotFoundError:
            return result
        cfg = load(lane, rh)
        result.update(deliverable=cfg['deliverable'], owner_session=cfg['owner_session'],
                      every_hours=cfg['every_hours'], warn_hours=cfg['warn_hours'])
        if (('window_opens' in cfg and clock < stamp(cfg['window_opens']))
                or ('window_closes' in cfg and clock >= stamp(cfg['window_closes']))):
            result['status'] = 'EXEMPT'
            return result
        when = delivery_time(lane, cfg, clock)
        age = max(0, (clock - when).total_seconds() / 3600) if when else None
        result.update(last_delivery=when.isoformat() if when else None,
                      hours_since_last_delivery=age,
                      status=('STALLED' if age is None or age > cfg['every_hours'] else
                              'WARN' if age >= cfg['warn_hours'] else 'OK'))
        # An interval anchored to the last delivery is stable across polls/days.
        # Missing evidence has a stable sentinel, never a poll-time bucket.
        result['stall_window'] = when.isoformat() if when else 'never'
        if result['status'] != 'OK':
            refused = last_sweep_refusal(lane, rh)
            if refused:
                result['last_sweep_refused'] = refused
    except (OSError, ValueError, TypeError, OverflowError, SyntaxError):
        # Do not echo TOML/evidence/parser errors: they may include private text.
        result.update(status='STALLED', broken=True, error='CADENCE configuration or evidence unreadable/invalid')
    return result


def lanes(root, name=None):
    base = root.expanduser() / 'lanes'
    if name is not None:
        if not NAME.fullmatch(name):
            raise ValueError('invalid lane name')
        lane = base / name
        if not lane.is_dir():
            raise ValueError('lane directory missing: ' + name)
        return [lane]
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def report(root, rh, name=None, now=None):
    clock = now or rh.now()
    return [evaluate(lane, rh, clock) for lane in lanes(root, name)]


def lint(lane, rh, now=None):
    clock = now or rh.now()
    row = evaluate(lane, rh, clock)
    if row['broken']:
        return ['CADENCE.toml broken: configuration or evidence unreadable/invalid']
    if row['status'] == 'UNCONFIGURED':
        if stamp(clock) - stamp(SHIPPED_UTC) >= dt.timedelta(hours=BOOTSTRAP_HOURS):
            return ['CADENCE.toml missing after 26 hour bootstrap grace']
    elif row['status'] == 'STALLED':
        return ['lane deliverable cadence STALLED']
    return []


def body(row):
    checks = ['cadence-config-invalid'] if row['broken'] else (
        ['cadence-stalled'] if row['status'] == 'STALLED' else
        ['cadence-warning'] if row['status'] == 'WARN' else [])
    return lane_alerts.body(row['lane'], checks, row['owner_session'])


def monitor(root, rh):
    """Scheduler-only alert writes. Worker enablement is deliberately irrelevant."""
    rows = []
    for row in report(root, rh):
        check, kind = (('cadence-config-invalid', 'cadence-broken') if row['broken'] else
                       ('cadence-stalled', 'stalled') if row['status'] == 'STALLED' else
                       ('cadence-warning', 'warn') if row['status'] == 'WARN' else (None, None))
        rows.append(dict(lane=row['lane'], owner_session=row['owner_session'], kind=kind,
                         failures=[dict(check=check, message=check)] if check else []))
    return lane_alerts.monitor(root, 'cadence', rows)


def arguments(sub):
    actions = sub.add_parser('lanes', help='lane delivery health').add_subparsers(dest='action', required=True)
    parser = actions.add_parser('cadence', help='read-only delivery cadence status for every lane')
    parser.add_argument('--lane', help='limit to one lane')
    parser.add_argument('--json', action='store_true', help='machine-readable array')


def main(root, args, rh):
    rows = report(root, rh, args.lane)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        for row in rows:
            print('{} {}: {}'.format(row['status'], row['lane'], body(row).replace('\n', ' ').strip()))
            if row.get('last_sweep_refused'):
                print('  last sweep was refused, not idle: ' + row['last_sweep_refused'])
    return int(any(row['status'] == 'STALLED' for row in rows))
