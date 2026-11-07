#!/usr/bin/env python3
"""lane-yield: the harness integration test for "a lane spending money in circles".

Why (2026-11-04): a lane ran ~38 agent workers for two days, used a whole week of model allowance, logged
~7,000 ideas and 528 claims, and its referee passed 98% of them. Nothing was worth emailing. Every check
in the harness was green, because they all measured activity (workers alive, cadence, claims written,
verdicts written), never yield. This test measures yield.

For each configured lane, over a rolling window (default 48 h) it computes:
  job_hours   wall-clock hours of agent jobs, from launcher logs ("=== run/attempt ... <date>" .. "exit ... <date>")
  new_yes     claims that say NEW: yes, pass result-lint and have a HOLDS verdict (something new and refereed),
              plus lines in the lane's results ledgers (`results`: JSONL written by log_result.py) with
              new=true and a refereed verdict, for lanes whose results are PRs, notes or submissions, not claims
  verdicts    referee verdicts written in the window, and the share that pass
and FAILS the lane when
  BURNING        job_hours >= max_job_hours_without_new and new_yes == 0
  DRY_ROUNDS     attempts >= max_attempts_without_new and new_yes == 0 (a lane logging round after round
                 of the same approach with nothing to show; set max_attempts_without_new to enable)
  RUBBER_STAMP   verdicts >= min_verdicts and pass share >= max_pass_share (a referee that passes everything
                 is not refereeing)
  UNSURFACED     (lanes with `surface_audit`) a claim with a HOLDS verdict, at any time, that nobody
                 surfaced: its id is in no audit CSV and it is on no outreach record that went out.
                 Why (2026-11-05): an audit ran against a hand-picked subject list, so the great
                 majority of HOLDS claims were never audited at all. Coverage is every claim dir, so a new
                 subject can't be skipped. The outreach route was added 11-06 because the check was asking
                 for the same fact twice: `rh outreach draft --claim DIR` already records which claims
                 reached someone, and three emailed claims were being flagged as never audited. The CSV
                 stays the other route, for a claim surfaced without a message. This failure pushes
                 general but never writes the hold file: missing paperwork is not spending in circles.
Every research lane is configured, not only one: the point of a lane is something new.
A lane with `report_only: true` is pushed to general on FAIL but gets no hold file.
With --act, a failing lane gets its hold file written (its loops stop spending) and a push to general.
Exit 0 = all lanes PASS, 1 = some lane FAILS, 2 = config error.
"""
import argparse, glob, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
# result_lint sits beside this tool's directory in BOTH layouts: harness/tools in the
# repo, tools/ in the install. Before 11-06 this was parents[3]/'tools'/'result-lint',
# which only resolved in the repo, so ~/.local/bin/lane-yield had to symlink to the
# working tree and the installed copy could not even import. A yield test that fails
# to start is a dry lane spinning instead of being told to change direction.
LINT = HERE.parents[1]
sys.path.insert(0, str(LINT))
from result_lint import lint  # noqa: E402

DEFAULTS = dict(window_hours=48, max_job_hours_without_new=20, min_verdicts=20, max_pass_share=0.9,
                max_attempts_without_new=0, max_dry_streak=3)


def read_rounds(path):
    """Rows from a ROUNDS.jsonl, skipping corrupt lines rather than ignoring the file."""
    rows = []
    try:
        lines = open(path, errors='replace').read().splitlines()
    except OSError:
        return rows
    for line in lines:
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def dry_tail(rows):
    """(streak, family, spend) for the run of rounds since the last selective one.

    A `failed` round does not break the streak: it produced nothing selective either, and
    counting a crash as a fresh start is how seventeen dry rounds look like scattered bad luck.
    """
    rows = sorted(rows, key=lambda r: str(r.get('utc') or ''))
    # One row per round, keeping the latest. `rounds.py start` opens a round with outcome
    # "started" and the lane logs the real outcome afterwards, so without this collapse a single
    # round contributes twice and a streak reads as double its true length. A round still open
    # counts as not selective, for the same reason a crashed one does.
    latest = {}
    for row in rows:
        latest[str(row.get('round') or id(row))] = row
    rows = list(latest.values())
    streak, spend, families = 0, 0.0, []
    for row in reversed(rows):
        if row.get('outcome') == 'selective':
            break
        streak += 1
        families.append(row.get('family'))
        try:
            spend += float(row.get('spend_usd') or 0)
        except (TypeError, ValueError):
            pass
    same = families[0] if families and len(set(families)) == 1 else None
    return streak, same, spend
# The exit reason is free text, not one token: the launcher writes "exit 0", "exit stopped by
# job-stop" and "exit stopped by signal". Before 11-06 this read `exit \S+ `, so every job a
# human or a job-stop ended never closed its run, and job_hours counted it as still running
# until now. Three stopped virtual-embryo jobs added 216 h and marked the lane BURNING with
# nothing running. A yield test that invents spending stops a lane that should be working.
STAMP = re.compile(r'^(?:=== (?:run|attempt) .*?|exit .*?)([A-Z][a-z]{2} [A-Z][a-z]{2} +\d+ \d\d:\d\d:\d\d) \S+ (\d{4})\s*$')


def parse_stamp(line):
    m = STAMP.match(line)
    if not m:
        return None
    return datetime.strptime(f'{" ".join(m.group(1).split())} {m.group(2)}', '%a %b %d %H:%M:%S %Y').timestamp()


def job_hours(paths, start, end):
    total = 0.0
    for p in paths:
        open_at = None
        try:
            lines = open(p, errors='replace').read().splitlines()
        except OSError:
            continue
        for line in lines:
            t = parse_stamp(line)
            if t is None:
                continue
            if line.startswith('==='):
                open_at = t
            elif open_at is not None:
                total += max(0.0, min(t, end) - max(open_at, start))
                open_at = None
        if open_at is not None and open_at < end:
            total += max(0.0, end - max(open_at, start))  # still running
    return total / 3600


def verdict_head(d):
    try:
        return next((l.strip() for l in open(d / 'VERDICT.md', errors='replace') if l.strip()), '')
    except OSError:
        return None


def surfaced_by_outreach(globs):
    """Claim dirs named by an outreach record that actually went out.

    `rh outreach draft --claim DIR` is what puts a claim dir on a message, so the outreach
    ledger already knows which claims reached someone. Reading it here is what stops this
    check from asking for the same fact twice (friends, 11-05: three claims were flagged as
    never audited while all three had been emailed, and clearing it meant hand-writing CSV
    rows for messages the ledger had already recorded).

    The signal is the record's own `sent` stamp, not its status string: a row can be closed or
    dropped without ever having been sent, and a row recorded after the fact with
    `rh outreach record-sent` did go out. A bad line is skipped rather than blinding the file.
    """
    sent = set()
    for g in globs or []:
        for p in glob.glob(os.path.expanduser(g)):
            try:
                lines = open(p, errors='replace').read().splitlines()
            except OSError:
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(r, dict) or not (r.get('sent') or {}).get('utc'):
                    continue
                for claim in r.get('claims') or []:
                    sent.add(Path(str(claim)).name)
    return sent


def unsurfaced(audit):
    """HOLDS claims nobody surfaced: in no audit CSV (first column `id`) and on no message that
    went out. audit = {claims: [globs], csv: [globs], outreach: [globs]}."""
    seen = surfaced_by_outreach(audit.get('outreach', []))
    for g in audit.get('csv', []):
        for p in glob.glob(os.path.expanduser(g)):
            try:
                import csv
                with open(p, newline='', errors='replace') as f:
                    seen.update((r.get('id') or '').strip() for r in csv.DictReader(f))
            except OSError:
                continue
    missing = {}
    for g in audit.get('claims', []):
        for p in glob.glob(os.path.expanduser(g)):
            d = Path(p)
            if d.is_dir() and d.name not in seen and (verdict_head(d) or '').upper().startswith('HOLDS'):
                missing.setdefault(d.name.split('_')[0], []).append(d.name)
    return missing


def check_lane(name, cfg, now):
    c = {**DEFAULTS, **cfg}
    # A row, log line or verdict written in the same second as this run is inside the window.
    # Float seconds round to the nearest microsecond on the way into a timestamp, so an exact
    # `t <= now` comparison drops the newest row about half the time.
    end = now + 1
    start = now - c['window_hours'] * 3600
    logs = [p for g in c.get('logs', []) for p in glob.glob(os.path.expanduser(g))]
    hours = job_hours(logs, start, end)
    claims = [Path(p) for g in c.get('claims', []) for p in glob.glob(os.path.expanduser(g)) if Path(p).is_dir()]
    verdicts = passes = new_yes = 0
    for d in claims:
        v = d / 'VERDICT.md'
        if v.is_file() and start <= v.stat().st_mtime <= end:
            verdicts += 1
            head = verdict_head(d) or ''
            ok = head.upper().startswith('HOLDS')
            passes += ok
            if ok and not lint(d, new_only=True):
                new_yes += 1
    attempts = 0
    for g in c.get('results', []):
        for p in glob.glob(os.path.expanduser(g)):
            try:
                rows = [json.loads(l) for l in open(p, errors='replace') if l.strip()]
            except (OSError, json.JSONDecodeError):
                continue
            for r in rows:
                try:
                    t = datetime.fromisoformat(str(r['utc']).replace('Z', '+00:00')).timestamp()
                except (KeyError, ValueError):
                    continue
                if not (start <= t <= end):
                    continue
                attempts += 1
                # A reproduction is not a new result (LANE_RULES_COMMON.md, FRONT.md rule 3), and
                # the referee never sees this ledger. log-result refuses `--new yes --kind rerun`
                # from 11-06, but rows written before that are still in the ledgers, so skip them
                # here too rather than count history as yield.
                if (r.get('new') is True and r.get('kind') != 'rerun'
                        and str(r.get('referee', '')).upper().startswith('HOLDS')):
                    new_yes += 1
    share = passes / verdicts if verdicts else 0.0
    fails = []
    if hours >= c['max_job_hours_without_new'] and new_yes == 0:
        fails.append(f'BURNING: {hours:.0f} job-hours in {c["window_hours"]} h and nothing new (0 refereed NEW: yes claims)')
    if c['max_attempts_without_new'] and attempts >= c['max_attempts_without_new'] and new_yes == 0:
        fails.append(f'DRY_ROUNDS: {attempts} logged attempts in {c["window_hours"]} h and nothing new. '
                     'Repeating an approach that is not working is activity, not progress: change the approach.')
    if verdicts >= c['min_verdicts'] and share >= c['max_pass_share']:
        fails.append(f'RUBBER_STAMP: referee passed {passes}/{verdicts} ({share:.0%}); a referee that passes everything is not refereeing')
    # Rounds the harness can see (c5, 11-06): its rounds ran in-session against an external
    # API, so launch.sh, log-result and the spend ledger all missed them and the yield test was
    # blind to ~80 rounds and ~$340. `rounds.py log` writes one row per paid round.
    round_rows = []
    for g in c.get('rounds', []):
        for p in glob.glob(os.path.expanduser(g)):
            round_rows += read_rounds(p)
    streak, family, round_spend = dry_tail(round_rows)
    if streak >= c['max_dry_streak']:
        fails.append(f'DRY_STREAK: {streak} rounds in a row produced nothing selective'
                     + (f' (family "{family}", ${round_spend:.0f} logged)' if family else '')
                     + '. A dry streak is evidence about the method, not bad luck: the next '
                       'round must use a different family.')
    missing = unsurfaced(c['surface_audit']) if c.get('surface_audit') else {}
    if missing:
        n = sum(len(v) for v in missing.values())
        # Name breaks a tie on count: glob order is not stable, and a message that reorders
        # itself between runs reads as a new failure each time it is pushed to general.
        per = ', '.join(f'{k} {len(v)}' for k, v in sorted(missing.items(), key=lambda kv: (-len(kv[1]), kv[0])))
        fails.append(f'UNSURFACED: {n} HOLDS claims of {len(missing)} subjects never audited ({per})')
    return dict(lane=name, as_of=datetime.fromtimestamp(now).isoformat(timespec='minutes'), job_hours=round(hours, 1),
                attempts=attempts, new_yes=new_yes, verdicts=verdicts, pass_share=round(share, 3), status='FAIL' if fails else 'PASS', fails=fails)


def act(row, cfg):
    hold = cfg.get('hold')
    # DRY_STREAK binds on every lane, report_only included (c5, 11-06: it is report_only, so
    # DRY_ROUNDS never did anything through about 80 rounds in one method family). It writes a
    # direction requirement rather than a hold, because the answer to a dry streak is a
    # different method, not a stopped lane: `rounds.py check` refuses the next round in that
    # family until the lane closes it and picks another.
    streaks = [f for f in row['fails'] if f.startswith('DRY_STREAK')]
    direction = cfg.get('direction_file')
    if streaks and direction:
        d = Path(os.path.expanduser(direction))
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text('CHANGE DIRECTION, set by lane-yield {}: {}\nThe next round must use a '
                         'different method family. Close this one with `rounds.py close-family` '
                         'and record what the KB already knew with `rounds.py consult`.\n'
                         .format(row['as_of'], '; '.join(streaks)))
        except OSError:
            pass
    # A paperwork gap and a direction change are not spending in circles, so neither holds.
    spending = [f for f in row['fails']
                if not f.startswith('UNSURFACED') and not f.startswith('DRY_STREAK')]
    if hold and spending and not cfg.get('report_only'):
        p = Path(os.path.expanduser(hold))
        if not p.exists():
            p.write_text(f'HOLD by lane-yield {row["as_of"]}: ' + '; '.join(row['fails']) + '\nOnly general removes this file.\n')
    tg = Path.home() / '.claude/skills/orchestrator/scripts/tell-general'
    if tg.exists():
        subprocess.run([str(tg), 'ricardo', f'lane-yield FAIL {row["lane"]}: ' + '; '.join(row['fails'])], capture_output=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--config', default=os.path.expanduser('~/.config/lane-yield.json'))
    p.add_argument('--as-of', help='ISO time to evaluate at (backtest), default now')
    p.add_argument('--lane', action='append')
    p.add_argument('--act', action='store_true', help='write the hold file and push general for failing lanes')
    p.add_argument('--json', action='store_true')
    a = p.parse_args(argv)
    try:
        conf = json.load(open(a.config))
    except (OSError, json.JSONDecodeError) as e:
        print(f'config error: {e}', file=sys.stderr)
        return 2
    now = datetime.fromisoformat(a.as_of).timestamp() if a.as_of else time.time()
    rows = [check_lane(n, c, now) for n, c in conf.items() if not a.lane or n in a.lane]
    for r in rows:
        if a.act and r['status'] == 'FAIL':
            act(r, conf[r['lane']])
        if a.json:
            print(json.dumps(r))
        else:
            print(f'{r["status"]} {r["lane"]} @{r["as_of"]}: {r["job_hours"]} job-h, {r["new_yes"]} new, '
                  f'{r["verdicts"]} verdicts ({r["pass_share"]:.0%} pass)' + ''.join(f'\n  - {f}' for f in r['fails']))
    return 1 if any(r['status'] == 'FAIL' for r in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
