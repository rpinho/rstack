#!/usr/bin/env python3
"""Per-round ledger and the gate that makes a dry streak change direction.

Why (2026-11-06, the c5 postmortem). c5 ran about 80 rounds, R16 to R83, almost all in one
method family, printing "0 selective" round after round. It spent roughly $340 through an
external API, about $80 of it on R41-R57: seventeen dry rounds in a single day. It changed
method only when Ricardo stepped in, and its own account is that the KB bookmarks had already
identified the better family for this target and "I should have consulted them 38 rounds ago."

Every harness check was green, for four separate reasons, and this module answers them:

  1. The rounds were invisible. They ran in-session against an external API, so they never
     went through launch.sh, log-result or any spend ledger. c5's SPEND.md records ~$267 over
     17 rounds against the ~80 that happened, so even the yield test could not see them.
     `log-round` gives every paid round one row: round, family, spend, outcome.
  2. The verdict was not binding. c5 is report_only, so DRY_ROUNDS never did anything.
  3. Nothing forced a change of method. A dry streak in one family is evidence about that
     family, and the next round could be the same family again.
  4. Nothing made it read what we already knew.

The rule here is deliberately not "stop". Ricardo's lanes exist to spend and find things; a
dry streak means change direction, not halt. So the gate refuses the NEXT round in a family
that has just produced three dry rounds, and asks for a different one. A closed family goes in
the lane's dead-ends log and cannot be reopened without new evidence recorded against it.

A round is dry when it produced nothing selective: `--outcome dry`. The lane says which,
because only the lane knows what selective means for its target.

2026-11-07, the second time. c5 ran 66 more identical rounds ("same generator, same params, same
scorer"), nothing has beaten v25 since 11-05, and the ask was for a third mechanism. There was no
need: the rule above, lane-yield's DRY_STREAK, the direction file and the `rounds` globs in
~/.config/lane-yield.json were all already in place. What was missing was any row at all. No lane
had a ROUNDS.jsonl, nothing called `check` before a round, and nothing called `log` after one, so
every check read an empty ledger and found nothing to object to. A rule nothing calls is prose with
a shebang. Two changes fix that, and nothing else was added:

  * `start` does the gate and writes the row in one step, so the launcher can make the write
    unavoidable instead of asking the lane to volunteer it. A round cannot begin while the previous
    one has no outcome, which is what turns logging from a courtesy into a precondition.
  * the fingerprint is mechanical. `family` is a label the lane chooses, and a lane convinced it is
    varying enough will keep choosing a new one; a hash of (generator, params, scorer) does not
    care what the round is called. That is the specific hole c5's 66 rounds went through.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings
import toml_subset
import harness_blocks
sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec

ROUNDS = 'ROUNDS.jsonl'
DEAD_ENDS = 'DEAD_ENDS.jsonl'
RECEIPTS = 'KB_CONSULTS.jsonl'
OUTCOMES = ('selective', 'dry', 'failed')
DRY_LIMIT = 3
REPEAT_WINDOW = 5   # how far back an identical (generator, params, scorer) still counts as a repeat
STARTED = 'started'  # written by `start`; replaced when the lane records the real outcome

# 11-19. baseline.py `check` re-runs every registered baseline and fails on drift, and nothing called
# it, which is how planets compared against prior art it had never run and how a quoted number can rot
# for a month (see baseline.py's docstring). The round gate now runs it when the last pass is stale.
BASELINES = 'BASELINES.jsonl'
BASELINE_CACHE = '.baseline-check.json'
BASELINE_MAX_AGE_S = 7 * 86400
BASELINE_TIMEOUT_S = 3600
BASELINE_TOOL = Path(__file__).resolve().parent / 'baseline.py'
HOST_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z')   # an ssh alias, as launch.sh checks it

# RULE #1 (Ricardo, 11-20): each kind of error is its own gate in rstack/gates.json, and only the registry
# decides whether it refuses the round or is a warning the round runs past. The checks below still find
# everything they found; what they may stop changed.
GATE_OF = (('UNCLOSED', 'rounds.unclosed'), ('REPEAT', 'rounds.repeat'), ('DEAD_END', 'rounds.dead-end'),
           ('DRY_FAMILY', 'rounds.dry-family'), ('KB_UNREAD', 'rounds.kb-unread'),
           ('BASELINE_CHECK', 'rounds.baseline-check'), ('BASELINE_DRIFT', 'rounds.baseline-drift'),
           ('WRONG_TARGET', 'rounds.wrong-target'), ('WRONG_LENGTH', 'rounds.wrong-target'),
           ('SPEC capture CHANGED', 'rounds.wrong-target'))


def gate_name(error):
    """The registry gate an error belongs to. Anything about the SPEC file itself is `rounds.spec`."""
    if error.startswith('SPEC size_cap') and 'does not appear' in error:
        return 'rounds.wrong-target'
    for prefix, name in GATE_OF:
        if error.startswith(prefix):
            return name
    return 'rounds.spec'


def lane_host(lane):
    """Where this lane's work runs: LAUNCH_HOST, else `host` in its SWEEP.toml, else here.

    The baseline commands are the lane's own checkers (math's take minutes), and the controller
    is the 16 GB M4 that a local python run reset on 11-07, so they run where the lane runs.
    """
    host = os.environ.get('LAUNCH_HOST', '').strip()
    if host:
        return host
    sweep = Path(lane) / 'SWEEP.toml'
    if not sweep.exists():
        return ''
    try:
        return str(toml_subset.config(sweep).get('host') or '').strip()
    except Exception:  # a malformed SWEEP.toml is the sweep's error to report, not this gate's
        return ''


def fingerprint(generator='', params='', scorer=''):
    """A hash of what the round actually does, not what it is called.

    params is canonicalized when it parses as JSON, so {"a":1,"b":2} and {"b":2,"a":1} are the
    same round. An empty fingerprint (nothing supplied) is never compared against anything: a lane
    that cannot name its knobs should not be silently told its rounds all look alike.
    """
    if not any((generator, params, scorer)):
        return ''
    try:
        canonical = json.dumps(json.loads(params), sort_keys=True, separators=(',', ':'))
    except (ValueError, TypeError):
        canonical = (params or '').strip()
    blob = '\n'.join([(generator or '').strip(), canonical, (scorer or '').strip()])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def current(rows):
    """The last row per round id, in the order those rounds first appear.

    `start` writes a 'started' row and the lane later logs the outcome, so without this a single
    round would count twice in a dry streak and a streak would read as double its length.
    """
    out = {}
    for row in rows:
        key = str(row.get('round') or id(row))
        out[key] = row
    return list(out.values())


def read(path):
    """Rows in file order; a corrupt line is skipped rather than blinding the ledger."""
    out = []
    try:
        lines = Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return out
    for line in lines:
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def append(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


def dry_streak(rows, family=None):
    """Consecutive dry rounds at the end of the ledger, optionally within one family.

    `failed` rounds do not break a streak: a round that crashed produced nothing selective
    either, and treating a crash as a fresh start is how a streak hides.
    """
    streak = 0
    for row in reversed(current(rows)):
        if family is not None and row.get('family') != family:
            continue
        if row.get('outcome') == 'selective':
            break
        streak += 1
    return streak


def spend(rows):
    total = 0.0
    for row in rows:
        try:
            total += float(row.get('spend_usd') or 0)
        except (TypeError, ValueError):
            continue
    return total


def closed_families(lane):
    return {r.get('family') for r in read(Path(lane) / DEAD_ENDS)
            if r.get('status') == 'closed' and r.get('family')}


def consulted_since(lane, rounds_rows):
    """Is there a KB consult receipt at or after the last round in the ledger?

    Before round 1 there is no last round, so any receipt counts. After a dry streak the
    receipt has to be newer than the streak, or it is the reading that failed to help.
    """
    receipts = read(Path(lane) / RECEIPTS)
    if not receipts:
        return False
    last_receipt = max((str(r.get('utc') or '') for r in receipts), default='')
    last_round = max((str(r.get('utc') or '') for r in rounds_rows), default='')
    return bool(last_receipt) and last_receipt >= last_round


def baseline_errors(lane, now=None, timeout=None):
    """Errors that refuse a round because a registered baseline no longer reproduces.

    A lane without BASELINES.jsonl is untouched. Otherwise, when the last passing check cached in
    .baseline-check.json is missing or more than seven days old, `baseline.py check` runs with this
    interpreter (over ssh when the lane runs on a host) and a bounded timeout. The cache stays here,
    with the lane's other ledgers. A pass refreshes it; drift refuses the round and names
    what drifted. A check that times out or crashes also refuses: a check that could not run has
    shown nothing, and passing on it is how a baseline rots unseen.
    """
    lane = Path(lane)
    if not (lane / BASELINES).exists():
        return []
    now = time.time() if now is None else now
    cache = lane / BASELINE_CACHE
    try:
        last = json.loads(cache.read_text()).get('last_ok_epoch')
    except (OSError, ValueError, AttributeError):
        last = None
    if isinstance(last, (int, float)) and 0 <= now - last <= BASELINE_MAX_AGE_S:
        return []
    timeout = BASELINE_TIMEOUT_S if timeout is None else timeout
    cmd = [sys.executable, str(BASELINE_TOOL), '--lane', str(lane), 'check']
    host = lane_host(lane)
    if host:
        if not HOST_RE.fullmatch(host):
            return ['BASELINE_CHECK: baseline check could not run: host must be an ssh alias, got '
                    '{!r}'.format(host)]
        # Same absolute paths there, as launch.sh --host assumes; $HOME is expanded by that shell.
        remote = 'PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH" python3 ' + ' '.join(
            shlex.quote(c) for c in cmd[1:])
        cmd = (shlex.split(os.environ.get('LAUNCH_SSH') or 'ssh')
               + ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', host, remote])
    where = 'baseline.py --lane {} check'.format(lane)
    try:
        # Its own process group, so a timeout ends the baseline commands too, not only the checker.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                cwd=str(lane), start_new_session=True)
    except OSError as exc:
        return ['BASELINE_CHECK: baseline check could not run: {}'.format(exc)]
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            proc.kill()
        proc.communicate()
        return ['BASELINE_CHECK: baseline check could not run: `{}` timed out after {}s{}. Run it '
                'by hand and fix what hangs; the round waits until it passes.'
                .format(where, timeout, ' on ' + host if host else '')]
    if proc.returncode == 0:
        cache.write_text(json.dumps(dict(
            last_ok_epoch=now,
            last_ok_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))), sort_keys=True) + '\n')
        return []
    drifted = re.findall(r'^(\S+)\s+(?:DRIFT|SOURCE)\b', out or '', re.M)
    if drifted:
        return ['BASELINE_DRIFT: {} stopped reproducing (`{}`). Every comparison against it since the '
                'last check is against a number nothing here can produce. Fix the command or '
                're-register it with `baseline.py add`, and say which in the lane log.'
                .format(', '.join(dict.fromkeys(drifted)), where)]
    tail = ((err or '') + (out or '')).strip()[-300:]
    return ['BASELINE_CHECK: baseline check could not run{} (exit {}): {}'
            .format(' on ' + host if host else '', proc.returncode, tail)]


def gate(lane, family, new_evidence='', limit=DRY_LIMIT, fp='', hypothesis='',
         window=REPEAT_WINDOW):
    """Return (errors, warnings) for starting a round in `family`.

    Errors go through the registry (rstack/gates.json): one a hard line refuses the round, every
    other is a warning the round runs past and carries into its prompt (general, 11-20: repeat,
    dry family, dead end and baseline drift warn). The point is to redirect it, not to end the
    lane, so every error names what would let it proceed.
    """
    lane = Path(lane)
    rows = read(lane / ROUNDS)
    errors, warnings = [], []
    # 11-07, postmortem 3. Everything below this line compares the lane to itself: its own
    # families, its own streak, its own receipts. All of it stayed green through 115 rounds scored
    # against the wrong allele. The one check that would have caught it compares the lane's target
    # to the captured challenge, so it runs first and refuses the round on its own.
    errors.extend(spec.verify(lane))
    rounds = current(rows)
    # A round cannot begin while the one before it has no outcome. This is what makes the ledger
    # unavoidable rather than voluntary: skipping `log` blocks the next round instead of quietly
    # leaving the whole mechanism blind, which is how 66 rounds happened unseen.
    if rounds and rounds[-1].get('outcome') == STARTED:
        errors.append('UNCLOSED: round "{}" was started and never given an outcome. Record it '
                      'first: `rounds.py --lane {} log --round {} --family {} --outcome '
                      'selective|dry|failed`.'
                      .format(rounds[-1].get('round'), lane, rounds[-1].get('round'),
                              rounds[-1].get('family')))
    if fp:
        same = [r for r in rounds[-window:] if r.get('fingerprint') == fp]
        if same and not hypothesis.strip():
            errors.append('REPEAT: this exact (generator, params, scorer) already ran as {} of the '
                          'last {} rounds ({}). Repeating a method is not a test of it. Either '
                          'change a knob, or say what is different and what it would show: '
                          '--hypothesis "<...>". c5 ran 66 rounds on one fingerprint.'
                          .format(len(same), min(window, len(rounds)),
                                  ', '.join(str(r.get('round')) for r in same)))
    if family in closed_families(lane) and not new_evidence.strip():
        errors.append('DEAD_END: method family "{}" was closed in {} after a dry streak. '
                      'Reopening it needs new evidence: --new-evidence "<what changed>".'
                      .format(family, DEAD_ENDS))
    streak = dry_streak(rows, family)
    if streak >= limit:
        errors.append('DRY_FAMILY: the last {} rounds in family "{}" produced nothing '
                      'selective (${:.0f} spent in this lane so far). A dry streak is evidence '
                      'about the family: run a different one. Close this family with '
                      '`rounds.py close-family` and the reason.'
                      .format(streak, family, spend(rows)))
    overall = dry_streak(rows)
    if overall >= limit and not consulted_since(lane, rows):
        errors.append('KB_UNREAD: {} dry rounds and no KB consult receipt since the last one. '
                      'Search index.md, the wiki, raw/bookmarks and the sibling lanes for this '
                      'target and method, then record it with `rounds.py consult`. c5 spent 38 '
                      'rounds before reading what the KB already had.'.format(overall))
    if not rows and not consulted_since(lane, rows):
        errors.append('KB_UNREAD: no KB consult receipt before round 1. Search index.md, the '
                      'wiki, raw/bookmarks and the sibling lanes first, then record it with '
                      '`rounds.py consult`.')
    if 0 < overall < limit:
        warnings.append('{} dry round(s) in a row; {} more closes this family'
                        .format(overall, limit - overall))
    # Last, and only when nothing else refused: a check can take minutes, and a round already
    # refused for something else would spend them for nothing. 11-20: a warning does not count, the
    # round runs, so its baseline is checked.
    if not [e for e in errors if harness_blocks.refuses(gate_name(e))]:
        errors.extend(baseline_errors(lane))
    return errors, warnings


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--lane', required=True, type=Path, help='the lane directory')
    sub = p.add_subparsers(dest='action', required=True)

    def knobs(sp):
        # What the round actually does. The fingerprint is computed from these, so a lane cannot
        # relabel its way past the repeat check.
        sp.add_argument('--generator', default='', help='the generator or method, e.g. BoltzGen')
        sp.add_argument('--params', default='', help='its parameters; JSON is canonicalized')
        sp.add_argument('--scorer', default='', help='the scorer used to rank the output')
        return sp

    log = sub.add_parser('log', help='one row per paid round')
    log.add_argument('--round', required=True)
    log.add_argument('--family', required=True, help='method family, the unit a dry streak closes')
    log.add_argument('--outcome', required=True, choices=OUTCOMES)
    knobs(log)
    log.add_argument('--spend-usd', type=float, default=0.0)
    log.add_argument('--provider', default='')
    log.add_argument('--n-selective', type=int, default=0)
    log.add_argument('--what', default='')

    check = sub.add_parser('check', help='may a round in this family start?')
    check.add_argument('--family', required=True)
    check.add_argument('--new-evidence', default='')
    check.add_argument('--hypothesis', default='', help='what is different and what it would show')
    knobs(check)

    start = sub.add_parser('start', help='check, then open the round in one step')
    start.add_argument('--round', required=True)
    start.add_argument('--family', required=True)
    start.add_argument('--new-evidence', default='')
    start.add_argument('--hypothesis', default='')
    knobs(start)

    close = sub.add_parser('close-family', help='record a family as a dead end')
    close.add_argument('--family', required=True)
    close.add_argument('--reason', required=True)

    consult = sub.add_parser('consult', help='record a KB consult receipt')
    consult.add_argument('--source', action='append', default=[], required=True,
                         help='a KB path or sibling lane that was searched; repeatable')
    consult.add_argument('--took', required=True, help='what this round takes from it')

    a = p.parse_args(argv)

    # A bare lane name resolves under RH_ROOT/lanes, and a directory that is not a lane

    # is refused. One resolver for every tool that takes --lane: all four took it as a

    # bare path, and planets hit the trap on 11-07.

    try:

        a.lane = settings.lane_dir(a.lane)

    except ValueError as exc:

        # Not a lane the ledger can be written in: a harness or call error, never a reason to stop the
        # round (RULE #1), so it is a warning and the round runs unrecorded.
        if harness_blocks.gate('rounds.lane', 'cannot resolve --lane: {}'.format(exc),
                               fix='pass the lane directory, or a name under RH_ROOT/lanes'):
            return 2
        return 0
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if a.action == 'log':
        row = dict(utc=now, round=a.round, family=a.family, outcome=a.outcome,
                   spend_usd=a.spend_usd, provider=a.provider, n_selective=a.n_selective,
                   what=a.what,
                   fingerprint=fingerprint(a.generator, a.params, a.scorer),
                   generator=a.generator, scorer=a.scorer)
        append(a.lane / ROUNDS, row)
        print(json.dumps(row, sort_keys=True))
        return 0
    if a.action == 'close-family':
        append(a.lane / DEAD_ENDS, dict(utc=now, family=a.family, status='closed',
                                        reason=a.reason))
        print('closed family {} in {}'.format(a.family, DEAD_ENDS))
        return 0
    if a.action == 'consult':
        append(a.lane / RECEIPTS, dict(utc=now, sources=a.source, took=a.took))
        print('recorded a KB consult over {} source(s)'.format(len(a.source)))
        return 0
    fp = fingerprint(a.generator, a.params, a.scorer)
    errors, warnings = gate(a.lane, a.family, a.new_evidence, fp=fp, hypothesis=a.hypothesis)
    for w in warnings:
        print('WARN: ' + w, file=sys.stderr)
    refusing = [e for e in errors if harness_blocks.gate(gate_name(e), e, lane=a.lane.name)]
    if refusing:
        return 2
    if a.action == 'start':
        # Only now, and in the same command, so a caller cannot gate and then run something else.
        row = dict(utc=now, round=a.round, family=a.family, outcome=STARTED, fingerprint=fp,
                   generator=a.generator, scorer=a.scorer, hypothesis=a.hypothesis,
                   spend_usd=0.0, n_selective=0)
        # 11-20 (general): what warned stays on the round, so a later reader sees it ran past a repeat, a dry
        # family or a dead end, and that a comparison against a drifted baseline is flagged.
        if errors:
            row['warnings'] = ['{}: {}'.format(gate_name(e), e) for e in errors]
        drift = [e for e in errors if gate_name(e) == 'rounds.baseline-drift']
        if drift:
            row['baseline_drift'] = drift[0]
        append(a.lane / ROUNDS, row)
        print(json.dumps(row, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
