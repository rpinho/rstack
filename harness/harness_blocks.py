#!/usr/bin/env python3
"""harness-blocks: RULE #1, the harness never gets in the way of the work, and the one ledger it keeps.

Ricardo, 11-20: "Make sure the harness is not getting in our way. That should be rule number one of the
harness or rstack." Principle: rstack/principles/harness-never-in-the-way.md.

Every gate (hook, lint, launcher check, grader) has a class in ONE registry, rstack/gates.json:

  hard-line   may refuse. Only money, sign-ins and credentials, sends or posts in Ricardo's name,
              permanent deletes, privacy/IP egress and unsandboxed third-party code. A refusal names
              the fix (the exact command or edit), never a dead end.
  fail-open   warns, logs and lets the work continue. A crash inside it is a warning too.

The class lives in the registry, not in the gate: a gate asks `gate(name, reason, fix)` and only a
hard line gets True back. So downgrading a gate is one registry edit, and a gate cannot refuse on
its own say-so. A registry entry may also carry `pending` (a call left to general, with a
recommendation); such a gate keeps its old refusing behaviour until general decides, and every one of
its refusals is in the ledger like any other.

Every refusal AND every fail-open warning appends one line to
$RSTACK_STATE_DIR/harness-blocks.jsonl (default ~/.local/state/rstack/): utc, host, gate, class, job,
lane, outcome (block|warn|rerun|override|retract|heeded|ablated|allowed-override), reason, fix, and `pending` when the
gate's class is still general's call. A write failure never changes the
decision. The daily report counts a block that was later rerun, overridden or retracted as a harness
bug, and sends general the top three blockers.

  harness_blocks.py gate --gate NAME --reason TEXT [--fix CMD] [--job J] [--lane L]
        exit 0: carry on (a warning was logged); exit 3: refuse (a hard line; the fix was printed)
  harness_blocks.py mark --job J --outcome rerun|override|retract [--gate NAME] [--reason TEXT]
  harness_blocks.py mark --gate NAME --outcome heeded --reason TEXT
        heeded: a warning that made the agent change course. It is the proof a gate still changes outcomes
  harness_blocks.py admitted --job J        a job that was blocked before is now running: a rerun
  harness_blocks.py report [--days 1] [--peer HOST ...] [--tell]
  harness_blocks.py sunset [--days 14]      sunset gates that changed no outcome in DAYS days (read-only, exit 0)
  harness_blocks.py class NAME              print a gate's class

Rule #0 (11-21): rstack's goal is to delete itself. Every registry entry has `added`, `why`, `sunset` and
`last_changed_outcome`; a `sunset: true` gate stays only while it changes an outcome (a heeded, rerun,
override or retract row). Hard lines are `sunset: false`. docs/ablation.md: RSTACK_ABLATE=1 switches every
`sunset: true` gate off for a day (gate() and _hookfail return "allow", outcome `ablated`).
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

CLASSES = ('hard-line', 'fail-open')
# The only reasons a gate may refuse (Ricardo, 11-20). `pending` is a call left to general.
# 11-20: `general-keep` = a gate general reviewed under RULE #1 and decided keeps refusing (its `decided`
# field says why). It is a settled hard line, not a harness bug, in the daily report.
HARD_LINES = ('money', 'credentials', 'send-as-ricardo', 'permanent-delete', 'egress', 'third-party-code',
              'general-keep')
OUTCOMES = ('block', 'warn', 'rerun', 'override', 'retract', 'heeded', 'ablated', 'allowed-override')
HARNESS_BUG = ('rerun', 'override', 'retract')
# Outcomes that show a gate changed what happened: a heeded warning, or a block that was rerun, overridden
# or retracted. The sunset report keeps a gate only while it has one of these.
CHANGED = HARNESS_BUG + ('heeded',)
REFUSE = 3
LEDGER = 'harness-blocks.jsonl'
# Used only when the registry cannot be read at all: these gates still refuse, every other gate fails
# open. tests/test_gates_registry.py keeps this equal to the registry's refusing gates.
# 11-20: general moved codex-budget.limit, rounds.{repeat,dry-family,dead-end,baseline-drift},
# bughunt.coverage, lane-yield.hold, launch.host-memguard, sweep.host-headroom and upstream.live-claim to
# fail-open, so they left this set with the registry.
FALLBACK_REFUSING = frozenset((
    'bug-claims-check', 'claude-pace-gate.limit', 'codex-budget.npx',
    'conductor-inbox-gate.py', 'contact-gate', 'egress-gate', 'email-voice-gate.py', 'friend-reply-gate.py',
    'general-inbox-gate.py', 'general-relay-check.py', 'guard-main-tree.py', 'lan-proxy.allowlist',
    'lane-no-questions.py', 'launch.host-peak-cap',
    'launch.lane-hold', 'launch.lane-status', 'mem-guard', 'no-laptop-shell.py', 'osascript-shim',
    'outreach.send', 'pod-create-gate.py', 'pod-deadline-gate.py', 'protected-paths',
    'read-the-thread-first.py', 'result-gates', 'rounds.wrong-target', 'science-publish-gate.py',
    'selector.metered', 'sweep.disk-floor', 'sweep.engaged-only', 'third_party.run',
    'trash-guard.py', 'voice-lint', 'voice-send-gate.py', 'x-api-bypass-guard',
    'x-handle-guard', 'x-policy', 'x-submit-gate',
))


def _candidates():
    here = Path(__file__).resolve().parent
    env = os.environ.get('RH_GATES_REGISTRY')
    out = [Path(env).expanduser()] if env else []
    # Repo layout (harness/harness_blocks.py -> rstack/gates.json), then the installed root
    # (<root>/harness_blocks.py -> <root>/rstack/gates.json).
    out += [here.parent / 'rstack' / 'gates.json', here / 'rstack' / 'gates.json',
            Path.home() / '.local/share/research-harness/rstack/gates.json']
    return out


_REGISTRY = {}


def registry(path=None):
    """{gate name: entry}. Empty dict when no registry can be read (then FALLBACK_REFUSING decides)."""
    key = str(path or '')
    if key in _REGISTRY:
        return _REGISTRY[key]
    data = None
    for p in ([Path(path)] if path else _candidates()):
        try:
            data = json.loads(Path(p).read_text())
            break
        except (OSError, ValueError):
            continue
    gates = {}
    if isinstance(data, dict):
        for row in data.get('gates', []):
            if isinstance(row, dict) and row.get('gate'):
                gates[row['gate']] = row
    _REGISTRY[key] = gates
    return gates


def entry(name):
    return registry().get(name) or {}


def gate_class(name):
    """'hard-line', 'fail-open', or 'unclassified' (a gate the registry does not know)."""
    reg = registry()
    if not reg:
        return 'hard-line' if name in FALLBACK_REFUSING else 'fail-open'
    row = reg.get(name)
    if not row:
        return 'unclassified'
    return row.get('class') if row.get('class') in CLASSES else 'unclassified'


def refuses(name):
    """True when this gate may refuse: a hard line, or a gate the registry does not know yet (its old
    behaviour is kept, and the report names it until someone classifies it). Never raises."""
    try:
        return gate_class(name) in ('hard-line', 'unclassified')
    except Exception:
        return name in FALLBACK_REFUSING


def ablating(name):
    """RSTACK_ABLATE=1 (docs/ablation.md): this gate is switched off for the day. Only a `sunset: true` gate;
    a hard line, an unclassified gate and one the registry cannot name always run. Never raises."""
    try:
        return os.environ.get('RSTACK_ABLATE') == '1' and entry(name).get('sunset') is True
    except Exception:
        return False


def ledger_path():
    base = os.environ.get('RSTACK_STATE_DIR')
    if not base:
        base = str(Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack')
    return Path(base).expanduser() / LEDGER


def _context(job, lane):
    job = job or os.environ.get('RH_JOB') or os.environ.get('LAUNCH_JOB') or ''
    lane = lane or os.environ.get('RSTACK_LANE') or os.environ.get('LAUNCH_LANE') or ''
    return str(job)[:200], str(lane)[:100]


def record(gate, cls, reason, job='', lane='', outcome='', fix=''):
    """Append one ledger line. Never raises: a ledger that cannot be written never changes a decision."""
    try:
        job, lane = _context(job, lane)
        if not outcome:
            outcome = 'block' if cls in ('hard-line', 'unclassified') else 'warn'
        row = dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), host=socket.gethostname().split('.')[0],
                   gate=str(gate), **{'class': str(cls)}, job=job, lane=lane, outcome=outcome,
                   reason=' '.join(str(reason).split())[:500], fix=' '.join(str(fix or '').split())[:300])
        if entry(gate).get('pending'):
            row['pending'] = True
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a') as fh:
            fh.write(json.dumps(row, sort_keys=True) + '\n')
        return row
    except Exception as exc:
        try:
            print('[harness-blocks] could not write the ledger ({}); the decision stands'.format(type(exc).__name__),
                  file=sys.stderr)
        except Exception:
            pass
        return None


def fix_for(name, fix=''):
    return fix or entry(name).get('fix') or ''


def gate(name, reason, fix='', job='', lane='', stream=None):
    """The one call every gate makes when it would stop something. True means refuse (a hard line, or
    an unclassified gate keeping its old behaviour); False means the work goes on and a warning was
    logged and printed. Never raises."""
    stream = stream if stream is not None else sys.stderr
    try:
        cls = gate_class(name)
    except Exception:
        cls = 'hard-line' if name in FALLBACK_REFUSING else 'fail-open'
    fix = fix_for(name, fix)
    if ablating(name):   # the day's ablation pass: allow, say nothing, keep the ledger row
        record(name, cls, reason, job=job, lane=lane, outcome='ablated', fix=fix)
        return False
    record(name, cls, reason, job=job, lane=lane, fix=fix)
    try:
        if cls == 'fail-open':
            print('[{}] WARNING (fail-open, the work continues): {}{}'.format(
                name, reason, ' Fix: ' + fix if fix else ''), file=stream)
        else:
            row = entry(name)
            label = ('pending general\'s call (rstack/gates.json)' if row.get('pending') else
                     'hard line: ' + str(row.get('hard_line') or '?') if cls == 'hard-line'
                     else 'not yet classified in rstack/gates.json')
            print('[{}] REFUSED ({}): {} Fix: {}'.format(
                name, label, reason,
                fix or 'none named, which is a harness bug: add `fix` to rstack/gates.json'), file=stream)
    except Exception:
        pass
    return cls != 'fail-open'


def warn(name, reason, fix='', job='', lane='', stream=None):
    """A check that never refuses: log and print a warning."""
    stream = stream if stream is not None else sys.stderr
    if ablating(name):
        record(name, 'fail-open', reason, job=job, lane=lane, outcome='ablated', fix=fix)
        return
    record(name, 'fail-open', reason, job=job, lane=lane, outcome='warn', fix=fix)
    try:
        print('[{}] WARNING (fail-open, the work continues): {}'.format(name, reason), file=stream)
    except Exception:
        pass


def mark(job, outcome, gate='', reason='', lane=''):
    """A later event that shows an earlier block was the harness's fault (rerun, override, retract), or that
    a warning changed what the agent did (heeded: no job needed)."""
    if outcome not in CHANGED:
        raise ValueError('outcome must be one of ' + ', '.join(CHANGED))
    return record(gate or '*', gate_class(gate) if gate else '-', reason or outcome, job=job, lane=lane, outcome=outcome)


def read(path=None):
    rows = []
    try:
        with open(path or ledger_path()) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def admitted(job, lane='', days=7, path=None):
    """Called when a job starts. If the same job was blocked in the last `days`, record a rerun: the
    block did not hold, so it was in the way. Returns the number of earlier blocks it answers."""
    if not job:
        return 0
    cutoff = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - days * 86400))
    rows = [r for r in read(path) if r.get('job') == job and str(r.get('utc', '')) >= cutoff]
    last_answer = max([r.get('utc', '') for r in rows if r.get('outcome') in HARNESS_BUG] or [''])
    open_blocks = [r for r in rows if r.get('outcome') == 'block' and r.get('utc', '') > last_answer]
    if open_blocks:
        record('*', '-', 'job ran after {} block(s): {}'.format(
            len(open_blocks), ', '.join(sorted({r.get('gate', '?') for r in open_blocks}))),
            job=job, lane=lane, outcome='rerun')
    return len(open_blocks)


def summarize(rows, now=None, days=1.0):
    """Blocks, warnings, harness bugs (a block later answered by a rerun, override or retraction of the
    same job) and the top blockers, over the last `days`."""
    now = time.time() if now is None else now
    cutoff = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - days * 86400))
    recent = [r for r in rows if str(r.get('utc', '')) >= cutoff]
    blocks = [r for r in recent if r.get('outcome') == 'block']
    warns = [r for r in recent if r.get('outcome') == 'warn']
    bugs, answered = [], set()
    # A hard line that held and was then fixed and rerun is the system working. Every other block that a
    # rerun, override or retraction answered was in the way: fail-open and unclassified gates, and the
    # gates whose class general has not decided yet (`pending`). 11-22 (general, rule #0: the report said
    # "0 harness bugs" on a day full of them): a reroute or warning answered the same day counts too, and so
    # does a manual override or a retraction on its own (a grade charged to a model for a harness error, a job
    # relaunched with --model-override after the harness routed or failed it).
    for b in blocks + warns:
        if b.get('outcome') == 'block' and b.get('class') == 'hard-line' and not b.get('pending'):
            continue
        later = [r for r in rows if r.get('outcome') in HARNESS_BUG and r.get('job') and r.get('job') == b.get('job')
                 and str(r.get('utc', '')) >= str(b.get('utc', '')) and r.get('gate') in ('*', b.get('gate'))
                 and (b.get('outcome') == 'block' or str(r.get('utc', ''))[:10] == str(b.get('utc', ''))[:10])]
        if later:
            bugs.append(dict(b, answered_by=later[0].get('outcome')))
            answered.update(id(r) for r in later)
    for r in recent:
        if r.get('outcome') in ('override', 'retract') and r.get('job') and id(r) not in answered:
            bugs.append(dict(r, answered_by=r['outcome']))
    count = {}
    for r in blocks + warns:
        key = r.get('gate', '?')
        count[key] = count.get(key, 0) + 1
    top = sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    # Only a gate that refused or warned is one to register; a rerun, override or retraction mark names what
    # answered it (11-22: the marks for that day's harness bugs listed selector and sweep.* as unclassified).
    unclassified = sorted({r.get('gate', '?') for r in blocks + warns if r.get('class') == 'unclassified'})
    overrides = len([r for r in recent if r.get('outcome') == 'allowed-override'])
    return dict(blocks=len(blocks), warns=len(warns), harness_bugs=bugs, top=top, unclassified=unclassified,
                allowed_overrides=overrides, last_changed=last_changed(rows),
                by_gate_bugs=sorted({b.get('gate', '?') for b in bugs}))


def _gates_named(reason):
    """admitted() writes a rerun row under gate '*'; the gates it answers are in its reason."""
    head = 'job ran after '
    text = str(reason)
    if not text.startswith(head) or ': ' not in text:
        return []
    return [g.strip() for g in text.split(': ', 1)[1].split(',') if g.strip()]


def last_changed(rows):
    """{gate: latest UTC date (YYYY-MM-DD) of a heeded, rerun, override or retract row for it}."""
    out = {}
    for r in rows:
        if r.get('outcome') not in CHANGED:
            continue
        gates = _gates_named(r.get('reason')) if r.get('gate') == '*' else [r.get('gate')]
        day = str(r.get('utc', ''))[:10]
        for g in gates:
            if g and day and day > out.get(g, ''):
                out[g] = day
    return out


def sunset_candidates(rows, gates, days=14, now=None):
    """Every `sunset: true` gate added more than `days` days ago with no heeded/rerun/override/retract row in
    the last `days` days, as (gate, added, warnings in the window). Rule #0: it stays only while it changes
    an outcome."""
    now = time.time() if now is None else now
    cutoff = time.strftime('%Y-%m-%d', time.gmtime(now - days * 86400))
    changed = last_changed(rows)
    since = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now - days * 86400))
    warned = {}
    for r in rows:
        if r.get('outcome') == 'warn' and str(r.get('utc', '')) >= since:
            warned[r.get('gate')] = warned.get(r.get('gate'), 0) + 1
    out = []
    for name, row in sorted(gates.items()):
        added = str(row.get('added') or '')
        if row.get('sunset') is not True or not added or added >= cutoff:
            continue
        if changed.get(name, '') >= cutoff:
            continue
        out.append((name, added, warned.get(name, 0)))
    return out


def line(summary, days=1.0):
    s = summary
    top = ', '.join('{} ({})'.format(g, n) for g, n in s['top']) or 'none'
    text = 'harness-blocks {}h: {} block(s), {} fail-open warning(s); {} harness bug(s) (refused or rerouted, then ' \
           'rerun, overridden or retracted){}; top blockers: {}'.format(
               int(days * 24), s['blocks'], s['warns'], len(s['harness_bugs']),
               ' in ' + ', '.join(s['by_gate_bugs']) if s['by_gate_bugs'] else '', top)
    if s.get('allowed_overrides'):
        text += '; {} sanctioned model override(s) allowed'.format(s['allowed_overrides'])
    if s['unclassified']:
        text += '; unclassified gates (add them to rstack/gates.json): ' + ', '.join(s['unclassified'])
    if s['harness_bugs']:
        text += '. Each harness bug gets a fix or a downgrade to fail-open the same day (RULE #1).'
    return text


def peer_rows(host, timeout=20):
    """Another machine's ledger over ssh; unreadable is reported and skipped, never fatal."""
    try:
        out = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
                              'cat ~/.local/state/rstack/' + LEDGER], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        print('[harness-blocks] could not read the ledger on ' + host, file=sys.stderr)
        return []
    rows = []
    for raw in out.stdout.splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            row.setdefault('host', host)
            rows.append(row)
    return rows


def tell(text):
    tg = os.environ.get('RH_TELL_GENERAL') or str(Path.home() / '.local/bin/tell-general')
    try:
        subprocess.run([tg, '--from', 'harness-blocks', 'fyi', text], capture_output=True, text=True, timeout=60)
        return True
    except (OSError, subprocess.SubprocessError):
        print('[harness-blocks] tell-general unavailable; the report is above', file=sys.stderr)
        return False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('gate')
    g.add_argument('--gate', required=True)
    g.add_argument('--reason', required=True)
    g.add_argument('--fix', default='')
    g.add_argument('--job', default='')
    g.add_argument('--lane', default='')
    m = sub.add_parser('mark')
    m.add_argument('--job', default='', help='required for rerun|override|retract; not for heeded')
    m.add_argument('--outcome', required=True, choices=CHANGED)
    m.add_argument('--gate', default='')
    m.add_argument('--reason', default='')
    m.add_argument('--lane', default='')
    a = sub.add_parser('admitted')
    a.add_argument('--job', required=True)
    a.add_argument('--lane', default='')
    r = sub.add_parser('report')
    r.add_argument('--days', type=float, default=1.0)
    r.add_argument('--peer', action='append', default=[], help='also read this ssh host\'s ledger')
    r.add_argument('--tell', action='store_true', help='send the line to general (tell-general fyi)')
    s = sub.add_parser('sunset')
    s.add_argument('--days', type=float, default=14)
    s.add_argument('--peer', action='append', default=[], help='also read this ssh host\'s ledger')
    c = sub.add_parser('class')
    c.add_argument('name')
    args = p.parse_args(argv)
    if args.cmd == 'gate':
        return REFUSE if gate(args.gate, args.reason, args.fix, args.job, args.lane) else 0
    if args.cmd == 'mark':
        if args.outcome != 'heeded' and not args.job:
            p.error('--job is required for ' + args.outcome)
        mark(args.job, args.outcome, args.gate, args.reason, args.lane)
        return 0
    if args.cmd == 'admitted':
        admitted(args.job, args.lane)
        return 0
    if args.cmd == 'class':
        print(gate_class(args.name))
        return 0
    try:   # the host env file names the peers (RH_BLOCKS_PEERS), as for every scheduled harness job
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import settings  # noqa: F401
    except Exception:
        pass
    rows = read()
    for host in args.peer + [h for h in os.environ.get('RH_BLOCKS_PEERS', '').replace(',', ' ').split() if h]:
        rows += peer_rows(host)
    if args.cmd == 'sunset':
        for name, added, warns in sunset_candidates(rows, registry(), args.days):
            print('{}\tadded {}\t{} warning(s) in {:g}d, no heeded/rerun/override/retract'.format(
                name, added, warns, args.days))
        return 0
    text = line(summarize(rows, days=args.days), args.days)
    print(text)
    if args.tell:
        tell(text)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:   # a crash in the ledger tool is never a refusal
        print('[harness-blocks] internal error ({}); carrying on'.format(type(exc).__name__), file=sys.stderr)
        sys.exit(0)
