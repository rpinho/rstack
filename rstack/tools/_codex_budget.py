"""Codex wrapper policy. Local, append-only accounting; no credentials or prompt bodies.

The allowance parser is reused unchanged from the parallel spend-guard worktree.
A lock serializes admission/reservations, not model runs. All limits are finite.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import glob
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

TOOLS = Path(__file__).resolve().parent
_loader = importlib.machinery.SourceFileLoader('rstack_allowance', str(TOOLS / 'allowance'))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
allowance = importlib.util.module_from_spec(_spec)
_loader.exec_module(allowance)
REFUSED = 75
# 11-17 accounting final.py RATE: credits/M uncached, cached, output; priority multiplier.
RATES = {'gpt-6.1-sol': (50, 2.5, 250, 2.5), 'gpt-6.2-sol': (50, 2.5, 250, 2),
         'gpt-6.2-astra': (200, 10, 1000, 2), 'gpt-6-astra': (250, 25, 1250, 2.5),
         'gpt-6-sol': (50, 5, 250, 2.5), 'gpt-6.1-terra': (25, 1.25, 125, 2.5)}
FALLBACK_TOKENS_PER_POINT = 250 / 50 * 1_000_000
# 11-20 (general, on the open-source report): agy's Gemini quota is spent until ~11-26, so a claim a Claude
# hunter made needs a Codex referee, and the lane's own Codex budget was refusing them ("past 50 calls").
# A referee call (RSTACK_CALL_ROLE=referee, set by tools/launch.sh from the selection receipt) that only the
# lane's daily budget refuses may run on a separate bucket of this many calls/day per lane, and only while
# every agy Gemini candidate is blocked; otherwise the bucket is 0. Hunts never use it.
REFEREE_EXTRA_PER_DAY = 40
RESETS_IN = re.compile(r'resets?\s+in\s+(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s)?', re.I)
AGY_TIERS = ('low', 'medium', 'high', 'xhigh', 'max')

DEFAULTS = {'calls_hour': 60, 'weekly_percent_day': 3}
LANES = {name: {'calls_hour': 200, 'weekly_percent_day': 10} for name in ('games', 'open-source')}
VALUE_OPTIONS = {'-c', '--config', '--remote', '-C', '--cd', '--add-dir', '--add-root', '-m', '--model',
                 '-p', '--profile', '-i', '--image', '--local-provider', '--permission-profile', '-s',
                 '--sandbox', '-a', '--ask-for-approval', '--enable', '--disable', '--output-schema',
                 '-o', '--output-last-message', '--color', '--remote-auth-token-env', '--base', '--commit', '--title'}


def state_dir():
    return Path(os.environ.get('RSTACK_STATE_DIR') or str(
        Path(os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')) / 'rstack')).expanduser()


def config():
    path = Path(os.environ.get('CODEX_BUDGET_CONFIG') or
                str(Path.home() / '.config/rstack/codex-budget.json')).expanduser()
    try:
        cfg = json.loads(path.read_text())
    except FileNotFoundError:
        if 'CODEX_BUDGET_CONFIG' in os.environ:
            raise ValueError('explicit config missing')
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError('config must be an object')
    cfg['defaults'] = dict(DEFAULTS, **cfg.get('defaults', {}))
    cfg['lanes'] = dict(LANES, **cfg.get('lanes', {}))
    for limits in [cfg['defaults'], *cfg['lanes'].values()]:
        for key, value in limits.items():
            if key in (*DEFAULTS, 'calls_run') and (not allowance.finite(value) or value <= 0):
                raise ValueError('limits must be positive and finite')
    cfg.setdefault('referee_extra_per_day', REFEREE_EXTRA_PER_DAY)
    for limits in [cfg, *cfg['lanes'].values()]:
        value = limits.get('referee_extra_per_day', 0)
        if type(value) is not int or value < 0:
            raise ValueError('referee_extra_per_day must be a whole number, 0 or more')
    cfg.setdefault('notify_command', [str(Path.home() / '.local/bin/tell-general')])
    cfg.setdefault('owner_command', [str(Path.home() / '.local/bin/notify-ricardo')])
    for key in ('notify_command', 'owner_command'):
        if not isinstance(cfg[key], list) or not cfg[key] or not all(isinstance(v, str) for v in cfg[key]):
            raise ValueError('notification commands must be argv arrays')
    return cfg


def safe_lane(value):
    value = str(value).strip()
    if not value or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', value):
        raise ValueError('invalid lane name')
    return 'open-source' if value == 'bio' else value


def host_list(key, default=()):
    """Host-only path settings (kept out of the repo): a list of strings from the host config."""
    path = Path(os.environ.get('CODEX_BUDGET_CONFIG') or
                str(Path.home() / '.config/rstack/codex-budget.json')).expanduser()
    try:
        value = json.loads(path.read_text()).get(key, list(default))
    except (OSError, ValueError, AttributeError):
        return list(default)
    return [str(v) for v in value] if isinstance(value, list) else list(default)


def registry():
    """The harness lane registry (repo: ../../harness; installed: the research-harness root).

    None, with a warning, when it cannot be read: spend accounting then falls back to the cwd.
    """
    root = TOOLS.parent.parent
    # Loaded by path: putting the installed root on sys.path would shadow modules for the rest of the run.
    path = next((p for p in (root / 'harness/lane_registry.py', root / 'lane_registry.py') if p.exists()), None)
    try:
        if path is None:
            raise ImportError('lane_registry.py not found')
        loader = importlib.machinery.SourceFileLoader('rstack_lane_registry', str(path))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        return module.load()
    except (ImportError, OSError, ValueError, SyntaxError) as exc:
        print('codex: WARNING lane registry unavailable ({}); lane from cwd'.format(type(exc).__name__),
              file=sys.stderr)
        return None


def job_name():
    for key in ('RH_JOB', 'LAUNCH_JOB', 'LAUNCH_JOB_NAME', 'JOB_NAME'):
        if os.environ.get(key, '').strip():
            return Path(os.environ[key].strip()).stem
    return ''


def lane_for(cwd, cfg=None, warn=True):
    """RSTACK_LANE, then the lane registry (names, aliases, job_prefixes) for the job name, then the cwd
    (whose lane name is resolved through the registry the same way).

    11-18: the nightly (worktree nightly-<date>) and bio's hunt_*/ref_* jobs were each charged as a lane
    of their own, under the 3%/day default. A job no lane claims still gets the default limits, with one
    warning line naming it.
    """
    reg = registry()
    explicit = os.environ.get('RSTACK_LANE', '').strip()
    if explicit:
        return safe_lane(reg.lane_of_session(explicit) if reg else explicit)
    job = job_name()
    budget_lanes = set((cfg or {}).get('lanes', LANES))
    if job:
        lane = reg.registered_lane_of_job(job) if reg else None
        if not lane:
            lane = next((name for name in sorted(budget_lanes, key=len, reverse=True)
                         if job == name or job.startswith((name + '_', name + '-'))), None)
        if lane:
            return safe_lane(lane)
    lane = None
    parts = Path(cwd).parts
    # Extra anchors (for example a private notes tree whose subfolders are lanes) come from the host config.
    for anchor in ['open-science', *host_list('lane_anchors'), 'lanes']:
        if anchor in parts and parts.index(anchor) + 1 < len(parts):
            value = parts[parts.index(anchor) + 1]
            if anchor == 'open-science':
                value = value.split('_', 1)[0]
            lane = value
            break
    lane = safe_lane(lane or Path(cwd).name or 'unknown')
    if reg:
        # 11-18: the nightly ran in a worktree named nightly-20261118 under a lane anchor, so the cwd named the job.
        lane = safe_lane(reg.registered_lane_of_job(lane) or reg.lane_of_session(lane))
    if warn and lane not in budget_lanes and not (reg and lane in reg.lanes):
        print('codex: WARNING {} maps to no registered lane; lane {!r} gets the default limits'.format(
            'job {!r}'.format(job) if job else 'cwd {}'.format(cwd), lane), file=sys.stderr)
    return lane


def command_position(args):
    pos = 0
    while pos < len(args) and args[pos].startswith('-'):
        if args[pos] == '--':
            return pos + 1
        pos += 2 if args[pos] in VALUE_OPTIONS else 1
    return pos


def routing(args):
    """Preserve the two Macs' 11-07 privacy routing, including explicit homes/resume."""
    args = list(args)
    personal, clean = '--personal' in args, '--clean' in args
    args = [a for a in args if a not in ('--personal', '--clean')]
    pos = command_position(args)
    sub = args[pos:pos + 2]
    batch = bool(sub) and (sub[0] in ('exec', 'e', 'review') or sub == ['debug', 'prompt-input'])
    option_args = args[:args.index('--')] if '--' in args else args
    help_only = any(a in ('--help', '-h') for a in option_args)
    # Options before the prompt are parsed by the CLI; prompt contents are never searched.
    workdir = os.getcwd()
    for i, a in enumerate(args):
        if a in ('-C', '--cd') and i + 1 < len(args):
            workdir = os.path.abspath(os.path.expanduser(args[i + 1]))
        elif a.startswith('--cd='):
            workdir = os.path.abspath(os.path.expanduser(a[5:]))
    personal_home, clean_home = Path.home() / '.codex', Path.home() / '.codex-clean'
    if batch and not help_only:
        current = os.environ.get('CODEX_HOME')
        explicit = bool(current) and os.path.realpath(os.path.expanduser(current)) != str(personal_home.resolve())
        real = os.path.realpath(workdir)
        # Personal roots (the owner's private trees, listed only in the host config) keep the personal home.
        roots = [Path(r).expanduser() for r in host_list('personal_roots')]
        in_kb = any(real == str(r.resolve()) or real.startswith(str(r.resolve()) + '/') for r in roots)
        route = 'personal' if personal else 'clean' if clean else 'personal:kb' if in_kb else 'clean'
        if explicit:
            route = 'explicit:' + current
        elif route == 'clean' and not clean and sub[0] in ('exec', 'e'):
            rest = args[pos + 1:]
            if rest[:1] == ['resume']:
                ids = [a for a in rest[1:] if not a.startswith('-')]
                if ids and not list((clean_home / 'sessions').rglob('rollout-*-{}.jsonl'.format(ids[0]))) and list(
                        (personal_home / 'sessions').rglob('rollout-*-{}.jsonl'.format(ids[0]))):
                    route = 'personal:resume'
        if route == 'clean':
            os.environ['CODEX_HOME'] = str(clean_home)
        elif route.startswith('personal'):
            os.environ['CODEX_HOME'] = str(personal_home)
        try:
            log = Path.home() / '.local/state/ricardo-agent/codex-routing.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a') as stream:
                stream.write('{} {} {} cwd={} ppid={}\n'.format(time.strftime('%F %T'), route,
                             ' '.join(sub[:1]), os.getcwd(), os.getppid()))
        except OSError:
            pass
    elif personal:
        os.environ['CODEX_HOME'] = str(personal_home)
    elif clean:
        os.environ['CODEX_HOME'] = str(clean_home)
    return args, batch, help_only, workdir


@contextmanager
def locked():
    base = state_dir() / 'codex-ledger'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (base / '.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield base


def append(base, lane, row):
    row = dict(row, lane=safe_lane(lane))
    row.setdefault('ts', time.time())
    row.setdefault('utc', datetime.fromtimestamp(row['ts'], timezone.utc).isoformat())
    with (base / (lane + '.jsonl')).open('a') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def read_rows(path):
    if not path.exists():
        return []
    with path.open() as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError('invalid ledger')
    return rows


def notify(cfg, base, lane, key, text, now, owner=False, interval=None):
    """Successful deliveries are deduplicated; failed notifications stay visible/retryable."""
    path = base / '.notifications.jsonl'
    prior = [r for r in read_rows(path) if r.get('key') == key and r.get('delivered')]
    if prior and (interval is None or now - prior[-1]['ts'] < interval):
        return True
    argv = cfg['owner_command'] if owner else cfg['notify_command'] + ['decision']
    try:
        result = subprocess.run(argv + [text], capture_output=True, timeout=20)
        delivered = result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        delivered = False
    with path.open('a') as stream:
        stream.write(json.dumps(dict(key=key, ts=now, lane=lane, delivered=delivered)) + '\n')
    if not delivered:
        print('codex: notification pending: ' + text.replace('\n', ' ')[:500], file=sys.stderr)
    return delivered


def codex_homes(cfg, discover=False):
    roots = {Path.home() / '.codex', Path.home() / '.codex-clean', *Path.home().glob('.codex*')}
    roots.update(Path(p).expanduser() for p in cfg.get('codex_homes', []))
    for name in ('CODEX_HOME', 'CODEX_HOMES'):
        roots.update(Path(p).expanduser() for p in os.environ.get(name, '').split(os.pathsep) if p)
    known = state_dir() / 'codex-homes.json'
    if known.exists():
        roots.update(Path(p) for p in json.loads(known.read_text()))
    if discover:
        roots.update(allowance.homes())
    return sorted({p.resolve() for p in roots if p.is_dir()})


def health_homes(cfg, now, write=False):
    """Scan known homes every pass; cache the expensive whole-home discovery for six hours.

    Wrappers register explicit homes immediately in codex-homes.json. Conventional
    homes and environment/config paths are also always read, independently of this cache.
    Unknown native-only homes are rediscovered at most six hours later.
    """
    path = state_dir() / 'codex-home-discovery.json'
    try:
        cache = json.loads(path.read_text())
        valid = (0 <= now - cache['at'] < 6 * 3600 and isinstance(cache['homes'], list)
                 and all(isinstance(p, str) for p in cache['homes']))
    except (OSError, ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        cache = dict(at=now, homes=list(map(str, allowance.homes())))
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.{}.tmp'.format(os.getpid()))
            temporary.write_text(json.dumps(cache) + '\n')
            temporary.replace(path)
    return sorted(set(codex_homes(cfg)) | {Path(p) for p in cache['homes'] if Path(p).is_dir()})


def weekly_snapshot(cfg, now):
    data = allowance.read_allowance(codex_homes(cfg), now=now)['codex']
    if data == 'unavailable' or data['resets_at'] <= now:
        return None
    return data


def strip_priority(args, urgent):
    """Remove CLI priority requests. Final root override also defeats config/profile priority."""
    if urgent:
        return args, False
    out, stripped, i = [], False, 0
    while i < len(args):
        arg = args[i]
        if arg == '--':
            out.extend(args[i:])
            break
        value, width = None, 1
        if arg in ('-c', '--config') and i + 1 < len(args):
            value, width = args[i + 1], 2
        elif arg.startswith('--config='):
            value = arg[len('--config='):]
        elif arg.startswith('-c') and len(arg) > 2:
            value = arg[2:]
        if value and re.search(r'(?:^|\.)service_tier\s*=\s*[\"\']?(?:priority|fast)(?:[\"\']|$)', value):
            stripped = True
            i += width
            continue
        out.extend(args[i:i + width])
        i += width
    # Also log a config/profile priority setting which the final root override suppresses.
    home = Path(os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')).expanduser()
    config_paths = [home / 'config.toml']
    for i, arg in enumerate(args):
        if arg in ('-p', '--profile') and i + 1 < len(args):
            config_paths.append(home / (args[i + 1] + '.config.toml'))
        elif arg.startswith('--profile='):
            config_paths.append(home / (arg.split('=', 1)[1] + '.config.toml'))
    for path in config_paths:
        if path.is_file():
            with path.open() as source:
                content = source.read(1024 * 1024)
            stripped |= bool(re.search(r'(?m)^\s*service_tier\s*=\s*[\"\'](?:priority|fast)[\"\']', content))
    # Empty string is Codex's standard tier (no priority header); CLI overrides config.toml/profile.
    return ['-c', 'service_tier=""'] + out, stripped


def calls(rows):
    starts = {r['call_id']: r.copy() for r in rows if r.get('event') == 'start'}
    for row in rows:
        if row.get('event') == 'finish' and row.get('call_id') in starts:
            starts[row['call_id']].update(row, started_at=starts[row['call_id']]['ts'])
    for row in starts.values():
        row.setdefault('started_at', row['ts'])
    return list(starts.values())


def ledger_tokens(base, row, cache=None):
    """Read new metered finishes, or recover legacy usage at its recorded byte boundary."""
    if 'weighted_tokens' in row:
        return row['weighted_tokens']
    if 'output_tokens' in row:
        return weighted_tokens(row, row.get('model', 'gpt-6.1-sol'), row.get('priority', False))
    path = base / '.legacy-token-usage.json'
    owned_cache = cache is None
    if owned_cache:
        cache = json.loads(path.read_text()) if path.exists() else {}
    key = '{}:{}:{}'.format(row.get('lane'), row.get('call_id'), row['ts'])
    if key not in cache:
        recovered = 0.0
        paths = row.get('rollouts', [])
        try:
            for name in paths:
                # Older resumes did not save offsets; timestamps delimit the wrapper's interval.
                total, _ = usage_at(Path(name), end=row.get('rollout_sizes', {}).get(name),
                                    since=row.get('started_at', 0))
                recovered += total.get('weighted_tokens', 0)
        except OSError:
            paths = []
        # Legacy rows without readable rollouts have only input/cache evidence.
        cache[key] = recovered if paths else weighted_tokens(row)
        if owned_cache:
            path.write_text(json.dumps(cache, sort_keys=True) + '\n')
    return cache[key]


def calibration_from_rows(rows, now, weekly):
    """One account-window difference, never the sum of overlapping per-call deltas.

    At least six hours, five percentage points and ten completed calls suppress
    snapshot quantization and single-probe noise. Windows never cross a reset.
    """
    snapshots = []
    for row in rows:
        for key in ('weekly_before', 'weekly_after'):
            snapshot = row.get(key)
            if snapshot and snapshot.get('resets_at') == weekly['resets_at']:
                stamp = datetime.fromisoformat(snapshot['snapshot_at'].replace('Z', '+00:00')).timestamp()
                if now - 7 * 86400 <= stamp <= now:
                    snapshots.append((stamp, snapshot['weekly_used_percent']))
    if not snapshots:
        return None
    snapshots = sorted(set(snapshots))
    if any(b[1] < a[1] for a, b in zip(snapshots, snapshots[1:])):
        return None
    first, last = snapshots[0], snapshots[-1]
    points = last[1] - first[1]
    if last[0] - first[0] < 6 * 3600 or points < 5:
        return None
    finished = [r for r in rows if r.get('event') == 'finish' and first[0] < r['ts'] <= last[0]]
    if len(finished) < 10 or any(r.get('usage_missing') for r in finished):
        return None
    tokens = sum(r['weighted_tokens'] for r in finished)
    if tokens <= 0:
        return None
    return dict(source='ledger/account-window', tokens_per_point=tokens / points,
                weighted_tokens=tokens, weekly_points=points, calls=len(finished),
                window_start=first[0], window_end=last[0], resets_at=weekly['resets_at'])


def token_calibration(base, now, weekly):
    """Refresh on the first batch admission each UTC day; retain the last usable fit."""
    path = base / '.token-calibration.json'
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    try:
        saved = json.loads(path.read_text())
        if not isinstance(saved, dict) or not allowance.finite(saved.get('tokens_per_point')) or saved['tokens_per_point'] <= 0:
            saved = {}
    except (OSError, ValueError):
        saved = {}
    if saved.get('checked_day') == day:
        return saved
    rows = []
    legacy_path = base / '.legacy-token-usage.json'
    cache = json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
    for ledger in sorted(base.glob('*.jsonl')):
        if ledger.name.startswith('.'):
            continue
        for row in calls(read_rows(ledger)):
            if now - 7 * 86400 < row['ts'] <= now:
                if row.get('event') == 'finish':
                    row['weighted_tokens'] = ledger_tokens(base, row, cache)
                rows.append(row)
    if weekly:
        rows.append(dict(weekly_after=weekly))
    fitted = calibration_from_rows(rows, now, weekly) if weekly else None
    # A local ledger cannot see other machines or native bypasses. A rate below
    # 200 credits/point (20% below the measured 250 floor) indicates incomplete
    # coverage, not that this host's lanes should pay for the missing traffic.
    if fitted and fitted['tokens_per_point'] < .8 * FALLBACK_TOKENS_PER_POINT:
        fitted = None
    result = fitted or saved or dict(source='11-17 fallback: 250 credits/point; 50 credits/M Sol input',
                                    tokens_per_point=FALLBACK_TOKENS_PER_POINT)
    result = dict(result, checked_day=day, checked_at=now)
    if fitted:
        result['calibrated_at'] = now
    legacy_path.write_text(json.dumps(cache, sort_keys=True) + '\n')
    path.write_text(json.dumps(result, sort_keys=True) + '\n')
    return result


def account_alerts(cfg, base, lane, weekly, now):
    """Share 70/85% delivery receipts with the companion launcher's allowance reader."""
    folder = state_dir() / 'allowance'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = folder / 'alerts.json'
        seen = json.loads(path.read_text()) if path.exists() else {}
        for threshold in (50, 70, 85):
            key = '{}:{}'.format(weekly['resets_at'], threshold)
            if weekly['weekly_used_percent'] < threshold or key in seen:
                continue
            if notify(cfg, base, lane, 'account:' + key,
                      'Codex week {}% used ({}% threshold, resets {}).'.format(
                          weekly['weekly_used_percent'], threshold, weekly['resets_at']), now):
                seen[key] = now
                path.write_text(json.dumps(seen, sort_keys=True) + '\n')


def lane_rows(base, lane):
    rows = read_rows(base / (lane + '.jsonl'))
    if lane == 'open-source':
        # Preserve spend recorded before bio became an alias; renaming must not reset limits.
        rows = sorted(rows + read_rows(base / 'bio.jsonl'), key=lambda row: row.get('ts', 0))
    return rows


def admit(cfg, base, lane, now, prefix, prompt_tokens, weekly, interactive=False, urgent='', budget=True):
    """The refusal reason, or None. budget=False skips the lane's own daily budget (the day limit and the
    bulk-estimate gate) and keeps every other check: what a referee call on the referee bucket is held to."""
    rows = lane_rows(base, lane)
    history = calls(rows)
    limits = dict(cfg['defaults'], **cfg['lanes'].get(lane, {}))
    if weekly:
        used = weekly['weekly_used_percent']
        account_alerts(cfg, base, lane, weekly, now)
        if used > 85:
            if interactive:
                print('codex: WARNING week {}% used; interactive session remains available'.format(used), file=sys.stderr)
            elif not urgent:
                return 'above 85% weekly usage; LAUNCH_URGENT=<reason> required'
    elif not interactive:
        return 'weekly allowance unavailable or reset; obtain a current snapshot interactively'
    else:
        print('codex: WARNING weekly allowance unavailable; interactive session remains available', file=sys.stderr)
    if interactive:
        return None
    if 'calls_run' in limits:
        run_id = os.environ.get('RSTACK_RUN_ID', '').strip()
        if not run_id:
            return 'RSTACK_RUN_ID required for per-run limit in ' + lane
        # Count reservations as well as finished calls, under the admission lock.
        if sum(r.get('event') == 'start' and r.get('run_id') == run_id for r in rows) >= limits['calls_run']:
            return '{} calls/run limit for {}'.format(limits['calls_run'], lane)
    if len([r for r in history if now - 3600 < r['started_at'] <= now]) >= limits['calls_hour']:
        return '{} calls/hour limit for {}'.format(limits['calls_hour'], lane)
    daily = [r for r in history if now - 86400 < r['ts'] <= now]
    calibration = token_calibration(base, now, weekly)
    spent = sum(ledger_tokens(base, r) for r in daily if r.get('event') == 'finish') / calibration['tokens_per_point']
    pending = [r for r in daily if r.get('event') == 'start']
    for row in pending:
        if row.get('pid'):
            try:
                os.kill(row['pid'], 0)
            except ProcessLookupError:
                return 'previous wrapper run has incomplete accounting; reconcile its rollout before continuing'
    if budget and spent >= limits['weekly_percent_day']:
        return '{}% weekly allowance/day limit for {}'.format(limits['weekly_percent_day'], lane)
    if any(r.get('usage_missing') for r in daily):
        return 'previous successful run has unaccounted usage; reconcile its rollout before continuing'
    estimates = [r for r in rows if r.get('event') == 'estimate']
    estimate = estimates[-1] if estimates else None
    if budget and len(history) >= 50:
        if not estimate:
            return 'past 50 calls; record codex-budget estimate {} --calls N --tokens T'.format(lane)
        since = [r for r in history if estimate['ts'] <= r['started_at'] <= now]
        if len(since) >= estimate['calls'] or sum(r.get('input_tokens', 0) for r in since) >= estimate['total_tokens']:
            return 'bulk estimate exhausted; record a new finite estimate'
    similar = [r for r in history if r.get('prefix') == prefix and prefix and
               max(r.get('input_tokens', 0), r.get('prompt_tokens', 0)) > 20000 and
               r.get('cached_share', 0) < .2 and now - 3600 < r['started_at'] <= now]
    # Also catch the reported ~1/min incident: 20 calls cannot fit a literal 10-minute window.
    recent = [r for r in similar if now - 600 < r['started_at']]
    if len(recent) >= 19 or len(similar) >= 19:
        notify(cfg, base, lane, 'fanout:' + lane,
               'Codex cold long-prefix fan-out refused for {} (20th call; cwd recorded in ledger).'.format(lane),
               now, interval=600)
        return 'cold >20k-token prefix fan-out: 20th call within 10 minutes or sustained hour'
    if urgent and weekly and weekly['weekly_used_percent'] > 85:
        append(base, lane, dict(event='urgent', ts=now, reason=urgent, weekly_used_percent=weekly['weekly_used_percent']))
        if not notify(cfg, base, lane, 'urgent:' + str(uuid.uuid4()),
                      'Codex urgent run for {} above 85%: {}'.format(lane, urgent), now, owner=True):
            return 'urgent owner notification failed; run refused'
    return None


def agy_blocked_until(path=None):
    """{model: epoch until which agy refuses it} from the executor's 429 log (state_dir/agy-quota.jsonl).

    Each row is one refusal: utc, model (the route name, tier included), tier, and agy's error text, which
    says "Resets in 152h14m46s". A row without a reset time blocks nothing: how long is unknown.
    """
    blocked = {}
    try:
        lines = Path(path or state_dir() / 'agy-quota.jsonl').read_text().splitlines()
    except OSError:
        return blocked
    for line in lines:
        try:
            row = json.loads(line)
            at = datetime.fromisoformat(row['utc']).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        match = RESETS_IN.search(str(row.get('error', '')))
        if not match or not any(match.groups()):
            continue
        h, m, sec = match.groups()
        until = at + int(h or 0) * 3600 + int(m or 0) * 60 + float(sec or 0)
        model = str(row.get('model', ''))
        blocked[model] = max(until, blocked.get(model, 0))
    return blocked


def agy_gemini_candidates(cfg):
    """The agy routes that serve Gemini: referee_agy_candidates in the config, else the model leaderboard's
    routes with cli agy and a google/ canonical (RH_ROLES_FILE, else roles_file in the config)."""
    if isinstance(cfg.get('referee_agy_candidates'), list):
        return sorted(str(m) for m in cfg['referee_agy_candidates'])
    path = os.environ.get('RH_ROLES_FILE') or cfg.get('roles_file')
    if not path:
        return []
    try:
        routes = json.loads(Path(path).expanduser().read_text()).get('routes', {})
    except (OSError, ValueError, AttributeError):
        return []
    return sorted(name for name, route in routes.items() if isinstance(route, dict) and route.get('cli') == 'agy'
                  and str(route.get('canonical', '')).startswith('google/'))


def referee_bucket(cfg, lane, now):
    """(calls/day, why): the lane's referee bucket, open only while every agy Gemini candidate is blocked."""
    size = cfg['lanes'].get(lane, {}).get('referee_extra_per_day', cfg.get('referee_extra_per_day', 0))
    candidates = agy_gemini_candidates(cfg)
    if not candidates:
        return 0, 'no agy Gemini candidates known (roles_file or RH_ROLES_FILE)'
    blocked = agy_blocked_until()
    free = [m for m in candidates if blocked.get(m, 0) <= now]
    if free:
        return 0, 'agy Gemini not all blocked: {} free'.format(', '.join(free[:3]) + (' +{}'.format(len(free) - 3)
                                                                                    if len(free) > 3 else ''))
    until = min(blocked[m] for m in candidates)
    return size, 'every agy Gemini candidate ({}) blocked until at least {}'.format(
        len(candidates), datetime.fromtimestamp(until, timezone.utc).strftime('%Y-%m-%d %H:%MZ'))


def admit_call(cfg, base, lane, now, prefix, prompt_tokens, weekly, interactive=False, urgent='', role=''):
    """(reason or None, bucket, note). A referee call the lane's daily budget alone refuses runs on the
    referee bucket while it is open and has calls left today; every other check still applies."""
    reason = admit(cfg, base, lane, now, prefix, prompt_tokens, weekly, interactive, urgent)
    if not reason or role != 'referee' or interactive:
        return reason, 'lane', ''
    if admit(cfg, base, lane, now, prefix, prompt_tokens, weekly, interactive, urgent, budget=False):
        return reason, 'lane', ''
    size, why = referee_bucket(cfg, lane, now)
    used = sum(1 for r in lane_rows(base, lane) if r.get('event') == 'start' and r.get('bucket') == 'referee'
               and now - 86400 < r.get('ts', 0) <= now)
    if used >= size:
        return '{}; referee bucket {}'.format(reason, 'closed: ' + why if not size else
                                              'spent: {}/{} today'.format(used, size)), 'lane', why
    return None, 'referee', 'referee bucket call {}/{} today for {} (lane budget: {}; {})'.format(
        used + 1, size, lane, reason, why)


def native_link():
    """The ONLY way to the real CLI: a symlink, re-pointed after each brew upgrade, never a pinned version."""
    return Path(os.environ.get('CODEX_REAL') or str(Path.home() / '.local/libexec/codex-real')).expanduser()


def native_target(cfg):
    """Newest Caskroom binary; used only to (re-)point native_link, never executed directly."""
    choices = [Path(p) for p in glob.glob(cfg.get('native_glob', '/opt/homebrew/Caskroom/codex/*/bin/codex'))]
    choices = [p for p in choices if p.is_file() and os.access(p, os.X_OK) and p.resolve() != (TOOLS / 'codex').resolve()]
    if not choices:
        raise ValueError('native Codex not found under native_glob')
    return max(choices, key=lambda p: tuple(int(n) for n in re.findall(r'\d+', str(p))))


def point_native(cfg, base=None):
    """Point native_link at the newest Caskroom binary. Returns the new target if it changed, else None."""
    link, target = native_link(), native_target(cfg)
    if link.is_symlink() and Path(os.readlink(link)) == target:
        return None
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        backup = (base or state_dir() / 'codex-ledger') / 'entrypoint-backups' / (str(time.time_ns()) + '-' + link.name)
        backup.parent.mkdir(parents=True, exist_ok=True)
        link.rename(backup)
    tmp = link.with_name(link.name + '.tmp-' + str(os.getpid()))
    tmp.symlink_to(target)
    os.replace(tmp, link)
    return target


def native_binary(cfg):
    configured = cfg.get('native_binary')
    if configured:  # explicit host/test override
        path = Path(configured).expanduser()
    else:
        path = native_link()
        if not (path.is_file() and os.access(path, os.X_OK)):
            # Dangling after `brew upgrade` removed the old version: re-point, then still go through the link.
            with locked() as base:
                point_native(cfg, base)
    if not (path.is_file() and os.access(path, os.X_OK)) or path.resolve() == (TOOLS / 'codex').resolve():
        raise ValueError('native Codex not found; ' + str(path) + ' must link to the Caskroom binary')
    return path


def rollout_meta(path):
    # session_meta is first; cap lines so a giant prompt never loads into memory here.
    with path.open('rb') as stream:
        line = stream.readline(1024 * 1024)
    if not line.endswith(b'\n'):
        return {}
    row = json.loads(line)
    return row.get('payload', {}) if row.get('type') == 'session_meta' else {}


def weighted_tokens(row, model='gpt-6.1-sol', priority=False):
    """Sol-input-equivalent tokens; cached input is included in input_tokens already."""
    if '/' in model or (model not in RATES and not model.startswith('gpt')):
        return 0.0  # the 11-17 accounting excluded non-OpenAI providers
    rate = RATES.get(model, RATES['gpt-6.1-sol'])
    tokens = row.get('input_tokens', 0)
    cached = min(tokens, max(0, row.get('cached_input_tokens', tokens * row.get('cached_share', 0))))
    output = row.get('output_tokens', 0)  # includes reasoning tokens, never add them twice
    return ((tokens - cached) * rate[0] + cached * rate[1] + output * rate[2]) / 50 * (rate[3] if priority else 1)


def usage_at(path, offset=0, previous=None, model='gpt-6.1-sol', priority=False, end=None, since=None):
    total, snapshot, weighted = {}, None, 0.0
    prior = previous or {}
    model = prior.get('model', model)
    with path.open('rb') as stream:
        stream.seek(offset)
        while True:
            if end is not None and stream.tell() >= end:
                break
            line = stream.readline(1024 * 1024)
            if not line or (end is not None and stream.tell() > end):
                break
            if not line.endswith(b'\n'):
                while line and not line.endswith(b'\n'):
                    line = stream.readline(1024 * 1024)
                continue
            if b'"token_count"' not in line and b'"turn_context"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            payload = row.get('payload') or {}
            if row.get('type') == 'turn_context':
                model = payload.get('model') or model
                # The wrapper's effective priority policy is passed in; rollout context may refine it.
                if 'service_tier' in payload:
                    priority = payload['service_tier'] in ('priority', 'fast')
            if row.get('type') == 'event_msg' and payload.get('type') == 'token_count':
                info = payload.get('info') or {}
                current = info.get('total_token_usage')
                if current:
                    delta = {k: max(0, current.get(k, 0) - prior.get(k, 0))
                             for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')}
                    stamp = row.get('timestamp')
                    if since is None or (stamp and datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp() > since):
                        weighted += weighted_tokens(delta, model, priority)
                    prior = current
                    total = dict(current, weighted_tokens=weighted, model=model)
                root = next((p.parent for p in path.parents if p.name == 'sessions'), path.parent)
                found = allowance.snapshot(row, path, root, time.time())
                if found:
                    snapshot = found
    return total, snapshot


def own_rollouts(home, marker, started, cwd, before):
    found = []
    for path in (home / 'sessions').rglob('rollout-*.jsonl'):
        try:
            if path.stat().st_mtime < started:
                continue
            meta = rollout_meta(path)
            # originator is inherited on a resumed thread; match its existing file/offset instead.
            if meta.get('originator') == marker or str(path) in before:
                found.append(path)
        except (OSError, ValueError):
            continue
    return found


def prompt_input(args, batch):
    """Bounded spool for stdin, preserving exact bytes and streaming native output unchanged."""
    stream, prefix, count = None, '', 0
    if batch and not sys.stdin.isatty():
        stream = tempfile.TemporaryFile()
        while True:
            block = sys.stdin.buffer.read(65536)
            if not block:
                break
            stream.write(block)
            count += len(block)
            if len(prefix) < 4096:
                prefix += block.decode('utf-8', 'replace')[:4096 - len(prefix)]
        stream.seek(0)
    pos = command_position(args)
    rest, words, i = args[pos + 1:], [], 0
    while i < len(rest):
        arg = rest[i]
        if arg == '--':
            words.extend(rest[i + 1:]); break
        if arg in VALUE_OPTIONS:
            i += 2; continue
        if not arg.startswith('-'):
            words.append(arg)
        i += 1
    if words and words[0] in ('resume', 'fork'):
        words = words[1:]
        if words and re.fullmatch(r'[0-9a-f-]{36}', words[0]):
            words = words[1:]
    if words:
        text = ' '.join(words)
        prefix = text[:4096] if words[-1] != '-' else prefix
        count = max(count, len(text))
    return stream, hashlib.sha256(prefix.encode()).hexdigest() if prefix else '', count // 4


def supervise(native, args, cfg, lane, cwd, interactive, batch):
    stream, prefix, prompt_tokens = prompt_input(args, batch)
    home = Path(os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')).expanduser().resolve()
    started, call_id = time.time(), uuid.uuid4().hex
    marker = 'codex-rstack-' + call_id
    urgent = os.environ.get('LAUNCH_URGENT', '').strip()
    priority = bool(urgent) and strip_priority(args, '')[1]
    args, stripped = strip_priority(args, urgent)
    before, old_usage = {}, {}
    # Resume accounting is a delta, never the thread's lifetime total.
    if any(a in ('resume', 'fork') for a in args):
        for path in (home / 'sessions').rglob('rollout-*.jsonl'):
            if any(str(a) in path.name for a in args if re.fullmatch(r'[0-9a-f-]{36}', a)):
                before[str(path)] = path.stat().st_size
                old_usage[str(path)] = usage_at(path)[0]
        if '--last' in args:
            candidates = list((home / 'sessions').rglob('rollout-*.jsonl'))
            candidates = [p for p in candidates if rollout_meta(p).get('cwd') == cwd or '--all' in args]
            if candidates:
                path = max(candidates, key=lambda p: p.stat().st_mtime)
                before[str(path)] = path.stat().st_size
                old_usage[str(path)] = usage_at(path)[0]
    try:
        with locked() as base:
            # Waiting contenders must count reservations made since their invocation began.
            started = time.time()
            weekly = weekly_snapshot(cfg, started)
            role = os.environ.get('RSTACK_CALL_ROLE', '').strip()
            reason, bucket, note = (('--ephemeral disables required rollout accounting', 'lane', '')
                                    if batch and '--ephemeral' in args else
                                    admit_call(cfg, base, lane, started, prefix, prompt_tokens, weekly, interactive,
                                               urgent, role))
            if stripped:
                append(base, lane, dict(event='priority_stripped', ts=started, cwd=cwd))
            if reason:
                # 11-20 (general): the cap still holds on Codex, and the job does not fail on it. launch.sh reads
                # the REFUSED line below and reruns the job on claude (80% ceiling, lane shares) or agy, or queues
                # it while both are capped; so the ledger records a warning, not a block (codex-budget.limit).
                _warn('codex-budget.limit', reason + '; Codex is not run, launch.sh reruns the job on claude or agy',
                      lane=lane, fix='LAUNCH_URGENT=<reason> for an urgent job, or run it on another route '
                                     '(AGENT_BACKEND=claude|agy)')
                append(base, lane, dict(event='refused', ts=started, reason=reason, cwd=cwd, role=role))
                print('codex: REFUSED ' + reason, file=sys.stderr)
                return REFUSED
            if bucket == 'referee':
                print('codex: ' + note, file=sys.stderr)
            # Remember explicit homes for job-health even after this environment disappears.
            known = codex_homes(cfg) + [home]
            (state_dir() / 'codex-homes.json').write_text(json.dumps(sorted(set(map(str, known)))) + '\n')
            append(base, lane, dict(event='start', ts=started, call_id=call_id, marker=marker, cwd=cwd,
                                   run_id=os.environ.get('RSTACK_RUN_ID', '').strip(),
                                   pid=os.getpid(), codex_home=str(home), prefix=prefix,
                                   prompt_tokens=prompt_tokens, interactive=interactive, urgent=urgent, weekly_before=weekly,
                                   role=role, bucket=bucket, bucket_note=note,
                                   resume_rollouts=list(before)))
        env = dict(os.environ, CODEX_INTERNAL_ORIGINATOR_OVERRIDE=marker)
        process = subprocess.Popen([str(native)] + args, stdin=stream if stream else None, env=env)
        handlers = {}
        def forward(sig, frame):
            if process.poll() is None:
                process.send_signal(sig)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[sig] = signal.signal(sig, forward)
        try:
            code = process.wait()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        try:
            paths = own_rollouts(home, marker, started, cwd, before)
            tokens, cached, output, weighted, weekly_used = 0, 0, 0, 0.0, 0.0
            final_weekly = None
            for path in paths:
                old = old_usage.get(str(path), {})
                total, snapshot = usage_at(path, before.get(str(path), 0), previous=old, priority=priority)
                tokens += max(0, total.get('input_tokens', 0) - old.get('input_tokens', 0))
                cached += max(0, total.get('cached_input_tokens', 0) - old.get('cached_input_tokens', 0))
                output += max(0, total.get('output_tokens', 0) - old.get('output_tokens', 0))
                weighted += total.get('weighted_tokens', 0)
                if snapshot:
                    if final_weekly is None or snapshot['snapshot_at'] > final_weekly['snapshot_at']:
                        final_weekly = snapshot
            if final_weekly:
                if weekly and final_weekly['resets_at'] == weekly['resets_at']:
                    weekly_used = max(0, final_weekly['weekly_used_percent'] - weekly['weekly_used_percent'])
                else:
                    weekly_used = final_weekly['weekly_used_percent']
            with locked() as base:
                append(base, lane, dict(event='finish', call_id=call_id, ts=time.time(), exit_code=code,
                                       rollouts=list(map(str, paths)), rollout_sizes={str(p): p.stat().st_size for p in paths},
                                       input_tokens=tokens, cached_input_tokens=cached, output_tokens=output,
                                       weighted_tokens=weighted,
                                       cached_share=cached / tokens if tokens else 0, weekly_percent=weekly_used,
                                       weekly_before=weekly, weekly_after=final_weekly,
                                       usage_missing=(code == 0 or tokens > 0) and (not paths or not tokens or not final_weekly)))
                if final_weekly and final_weekly['resets_at'] > time.time():
                    account_alerts(cfg, base, lane, final_weekly, time.time())
        except (OSError, ValueError, TypeError, KeyError) as exc:
            # RULE #1: the run already happened; the harness failing to account for it is not the job's failure.
            _gate('codex-budget.accounting', 'completion accounting failed ({}); the run\'s own exit code stands'.format(
                type(exc).__name__), lane=lane)
        return code if code >= 0 else 128 - code
    finally:
        if stream:
            stream.close()


def _hb():
    """harness_blocks.py (RULE #1), from the repo (rstack/tools -> harness/) or the installed root. None if
    neither imports; callers then keep their old behaviour."""
    for cand in (TOOLS.parents[1] / 'harness', TOOLS.parents[1]):
        if (cand / 'harness_blocks.py').is_file():
            sys.path.insert(0, str(cand))
            try:
                import harness_blocks
                return harness_blocks
            except Exception:
                return None
    return None


def _gate(name, reason, lane='', fix=''):
    """True when the registry lets this refusal stand (rstack/gates.json); never raises."""
    hb = _hb()
    if hb is None:
        return True
    try:
        return hb.gate(name, reason, fix=fix, lane=lane)
    except Exception:
        return True


def _warn(name, reason, lane='', fix=''):
    """Log a warning for a check that does not refuse the work (rstack/gates.json); never raises."""
    hb = _hb()
    try:
        if hb is not None:
            hb.warn(name, reason, fix=fix, lane=lane)
    except Exception:
        pass


def wrapper_main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    triage = [a for a in raw if a not in ('--personal', '--clean')]
    sub = triage[command_position(triage):][:2]
    guarded = bool(sub) and (sub[0] in ('exec', 'e', 'review') or sub == ['debug', 'prompt-input'])
    interactive = sys.stdin.isatty() and not guarded
    try:
        args, batch, help_only, cwd = routing(raw)
        interactive = sys.stdin.isatty() and not batch
        cfg = config()
        native = native_binary(cfg)
        # Local CLI management cannot spend; keep original exec behavior for it.
        pos = command_position(args)
        cmd = args[pos] if pos < len(args) else ''
        option_args = args[:args.index('--')] if '--' in args else args
        # remote-control only starts/stops/pairs the phone daemon, which runs its own native binary; the
        # boot-time session recovery calls it from launchd and must not need a weekly snapshot (11-18).
        if help_only or any(a in ('--version', '-V') for a in option_args) or cmd in ('login', 'logout', 'completion', 'features', 'mcp', 'help', 'doctor', 'plugin', 'update', 'remote-control'):
            os.execv(str(native), [str(native)] + args)
        return supervise(native, args, cfg, lane_for(cwd, cfg, warn=not interactive), cwd, interactive, batch)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        refuse = not interactive and _gate('codex-budget.unavailable', 'codex accounting/config unavailable ({}); '
                                           'running without the spend wrapper\'s accounting'.format(type(exc).__name__),
                                           fix='codex-budget health')
        print('codex: {} accounting/config unavailable ({})'.format('REFUSED' if refuse else 'WARNING',
                                                                 type(exc).__name__), file=sys.stderr)
        if not refuse:
            # Interactive availability is unconditional, even with damaged accounting/config.
            fallback = native if 'native' in locals() else native_binary({})
            fallback_args = args if 'args' in locals() else [a for a in raw if a not in ('--personal', '--clean')]
            args, _ = strip_priority(fallback_args, os.environ.get('LAUNCH_URGENT', '').strip())
            os.execv(str(fallback), [str(fallback)] + args)
        return REFUSED


def deployment_file():
    return state_dir() / 'codex-deployment.json'


def repair_entrypoint(path, wrapper, base):
    """Preserve the replaced path, including a brew-created symlink; never unlink a binary."""
    path, wrapper = Path(path).expanduser(), Path(wrapper).expanduser().resolve()
    if path.is_symlink() and path.resolve() == wrapper:
        return False
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        raise ValueError('installed wrapper missing/not executable')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        backup = base / 'entrypoint-backups' / (str(time.time_ns()) + '-' + path.name)
        backup.parent.mkdir(parents=True, exist_ok=True)
        path.rename(backup)
    path.symlink_to(wrapper)
    return True


def health_problems(settings=None, now=None, repair=False):
    """Backstop invoked by job-health. Explicit activation avoids flagging legacy history.

    Every run inspects all new/updated rollouts in known homes since deployment;
    full home discovery is cached for six hours. In-flight starts cover long runs.
    """
    now = time.time() if now is None else now
    if settings is None:
        if not deployment_file().exists():
            return []
        settings = json.loads(deployment_file().read_text())
    cfg = config()
    rows = []
    wrapper = Path(settings.get('wrapper', str(TOOLS / 'codex'))).expanduser().resolve()
    for value in settings.get('entrypoints', []):
        path = Path(value).expanduser()
        if path.is_symlink() and path.resolve() == wrapper:
            continue
        detail = 'wrapper replaced/missing (brew upgrade or other installer)'
        if repair:
            try:
                repair_entrypoint(path, wrapper, state_dir() / 'codex-ledger')
                detail += '; wrapper restored, previous entry preserved'
            except (OSError, ValueError):
                detail += '; restore failed: operator action required'
        rows.append(('codex-install', str(path), detail))
    for value, target in (settings.get('shims') or {}).items():
        path, target = Path(value).expanduser(), Path(target).expanduser().resolve()
        if path.is_symlink() and path.resolve() == target:
            continue
        detail = 'shim replaced/missing'
        if repair:
            try:
                repair_entrypoint(path, target, state_dir() / 'codex-ledger')
                detail += '; shim restored, previous entry preserved'
            except (OSError, ValueError):
                detail += '; restore failed: operator action required'
        rows.append(('codex-install', str(path), detail))
    if settings.get('native_link'):
        link = native_link()
        try:
            want = native_target(cfg)
            if not (link.is_symlink() and Path(os.readlink(link)) == want):
                detail = 'codex-real does not point at the newest Caskroom binary ({})'.format(want)
                if repair:
                    point_native(cfg)
                    detail += '; re-pointed'
                rows.append(('codex-install', str(link), detail))
        except (OSError, ValueError) as exc:
            rows.append(('codex-install', str(link), 'native unavailable: ' + str(exc)))
    roots = health_homes(cfg, now, write=repair)
    if repair:
        state_dir().mkdir(parents=True, exist_ok=True)
        (state_dir() / 'codex-homes.json').write_text(json.dumps(list(map(str, roots))) + '\n')
    markers, active_paths, recorded, starts, finished = set(), set(), {}, {}, set()
    base = state_dir() / 'codex-ledger'
    for ledger in base.glob('*.jsonl'):
        for row in read_rows(ledger):
            if row.get('event') == 'start':
                starts[row['call_id']] = row
            elif row.get('event') == 'finish':
                finished.add(row['call_id'])
                recorded.update(row.get('rollout_sizes', {}))
    for call_id, row in starts.items():
        if call_id in finished:
            continue
        try:
            os.kill(row['pid'], 0)
        except (OSError, KeyError):
            continue
        markers.add(row.get('marker'))
        active_paths.update(row.get('resume_rollouts', []))
    since = settings.get('enabled_since', now - 86400)
    for home in roots:
        for path in (home / 'sessions').rglob('rollout-*.jsonl'):
            try:
                stat = path.stat()
                if stat.st_mtime < since or stat.st_size <= recorded.get(str(path), -1) or str(path) in active_paths:
                    continue
                meta = rollout_meta(path)
                if meta.get('originator') in markers:
                    continue
                rows.append(('codex-bypass', str(path), 'no wrapper ledger coverage for newest rollout bytes; cwd=' + str(meta.get('cwd', 'unknown'))))
            except (OSError, ValueError):
                rows.append(('codex-read', str(path), 'rollout metadata unreadable'))
    # Pending wrapper alerts remain actionable even if tell-general was unavailable at admission.
    notifications = read_rows(base / '.notifications.jsonl')
    for row in notifications:
        if not row.get('delivered'):
            delivered = any(r.get('key') == row['key'] and r.get('delivered')
                            for r in notifications)
            if not delivered:
                rows.append(('codex-alert', row['key'], 'wrapper notification failed; inspect lane ' + row['lane']))
    return rows


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    estimate = commands.add_parser('estimate', help='record a finite planned number of calls and input tokens/call')
    estimate.add_argument('lane', type=safe_lane)
    estimate.add_argument('--calls', type=int, required=True)
    estimate.add_argument('--tokens', type=int, required=True)
    check = commands.add_parser('check', help='inspect installation and unaccounted rollouts without changing anything')
    activate = commands.add_parser('activate', help='operator-only: install PATH symlinks after harness-sync')
    activate.add_argument('--wrapper', type=Path, default=TOOLS / 'codex')
    activate.add_argument('--entrypoint', action='append', type=Path, required=True)
    activate.add_argument('--npx', type=Path, help='npx entrypoint to replace with the codex-refusing shim')
    args = parser.parse_args(argv)
    try:
        if args.command == 'estimate':
            if args.calls <= 0 or args.tokens <= 0:
                parser.error('calls and tokens must be positive integers')
            with locked() as base:
                append(base, args.lane, dict(event='estimate', calls=args.calls, tokens_per_call=args.tokens,
                                            total_tokens=args.calls * args.tokens))
            print('{}: {} calls x {} input tokens = {} tokens; estimate only, limits still apply'.format(
                args.lane, args.calls, args.tokens, args.calls * args.tokens))
        elif args.command == 'activate':
            with locked() as base:
                target = point_native(config(), base)
                print('codex-real -> ' + os.readlink(native_link()) + (' (re-pointed)' if target else ''))
                for path in args.entrypoint:
                    repair_entrypoint(path, args.wrapper, base)
                shims = {}
                if args.npx:
                    npx, shim = args.npx.expanduser(), (args.wrapper.expanduser().resolve().parent / 'npx')
                    real = Path.home() / '.local/libexec/npx-real'
                    if not (npx.is_symlink() and npx.resolve() == shim.resolve()):
                        if not npx.exists():
                            raise ValueError('npx entrypoint missing')
                        if not npx.is_symlink():
                            raise ValueError('npx entrypoint is not a symlink; install the shim by hand')
                        source = Path(os.readlink(npx))
                        source = source if source.is_absolute() else (npx.parent / source)
                        real.parent.mkdir(parents=True, exist_ok=True)
                        if real.exists() or real.is_symlink():
                            real.rename(base / 'entrypoint-backups' / (str(time.time_ns()) + '-npx-real'))
                        real.symlink_to(source)
                        repair_entrypoint(npx, shim, base)
                    shims[str(npx)] = str(shim.resolve())
                try:
                    since = json.loads(deployment_file().read_text())['enabled_since']
                except FileNotFoundError:
                    since = time.time()
                deployment_file().write_text(json.dumps(dict(wrapper=str(args.wrapper.expanduser().resolve()),
                    entrypoints=list(map(lambda p: str(p.expanduser()), args.entrypoint)), enabled_since=since,
                    native_link=str(native_link()), shims=shims), indent=2) + '\n')
            print('Codex PATH entrypoints activated; backups in ' + str(base / 'entrypoint-backups'))
        else:
            rows = health_problems()
            for row in rows:
                print('\t'.join(row))
            return 1 if rows else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('codex-budget: REFUSED ({})'.format(type(exc).__name__), file=sys.stderr)
        return REFUSED
    return 0
