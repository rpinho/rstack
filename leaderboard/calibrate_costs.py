#!/usr/bin/env python3
"""Report local evidence for a tokens-per-weekly-percentage-point calibration."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path

import run_grades
from run_grades import run_costs

WEEK_MINUTES = 10080


def calibration(pairs, omitted, reasons):
    """Summarize a weighted ratio and expose which observations were rejected."""
    total_tokens = sum(tokens for tokens, _ in pairs)
    points = sum(points for _, points in pairs)
    positive = sum(points > 0 for _, points in pairs)
    coverage = points / (points + omitted) if points + omitted else 0
    candidate = total_tokens / points if points else None
    return dict(paired_intervals=len(pairs), positive_intervals=positive, tokens=total_tokens,
                weekly_points=round(points, 4), omitted_weekly_points=round(omitted, 4),
                positive_delta_coverage=round(coverage, 4), candidate=candidate,
                tokens_per_weekly_percent=candidate if positive >= 3 and points >= 5 and coverage >= .75 else None,
                omitted_intervals=dict(reasons))


def claude(usage_dir, runs, reader, since, until):
    samples = {}
    try:
        current = run_costs.mapping(json.loads((usage_dir / 'claude.json').read_text()))
    except (OSError, ValueError):
        current = {}
    for row in (*run_costs.events(usage_dir / 'claude-history.jsonl'), current):
        at, reset = (run_costs.timestamp(row.get(key)) for key in ('at', 'resets_at'))
        used = row.get('weekly_percent')
        if at is not None and reset is not None and since <= at <= until and run_costs.amount(used) and used <= 100:
            # The existing Claude collector stamps an approximate reset with
            # fractional seconds from each observation.
            samples[at] = used, round(reset / 60)
    windows = []
    for run in runs:
        if run.get('backend') != 'claude':
            continue
        start = run_costs.timestamp(run.get('started_at') or run.get('utc'))
        end = run_costs.timestamp(run.get('closed_at'))
        if start is not None and start <= until and (end is None or end >= since):
            windows.append((start, end, run))
    boundaries, reasons = [], Counter()
    pairs, omitted = [], 0
    if windows:
        first_start = min(start for start, _, _ in windows)
        last_end = max(end or until for _, end, _ in windows)
        # Keep the nearest outer readings so a completed run can be bracketed.
        for at, (percent, reset) in sorted(samples.items()):
            if not first_start - 1800 <= at <= last_end + 1800:
                continue
            if any(start <= at < (end or until) for start, end, _ in windows):
                reasons['reading inside logged run'] += 1
                continue
            boundaries.append((at, percent, reset))
    for before, after in zip(boundaries, boundaries[1:]):
        start, lower, window = before
        end, upper, next_window = after
        points = upper - lower
        if window != next_window or points < 0:
            reasons['reset or falling reading'] += 1
            continue
        inside = [run for s, e, run in windows if start < s <= end and e is not None and e <= end]
        if end - start > 6 * 3600 or (upper >= 100 and lower >= 100):
            reasons['gap or saturated reading'] += 1
            omitted += points
            continue
        counts = [reader.measure(run)[0] for run in inside]
        if any(used is None for used in counts) or (not counts and points):
            reasons['unmeasured or unlogged consumption'] += 1
            omitted += points
            continue
        pairs.append((sum(used['input'] + used['output'] for used in counts), points))
    evidence = calibration(pairs, omitted, reasons)
    evidence.update(snapshots=len(samples), bounded_snapshots=len(boundaries), logged_runs=len(windows))
    return evidence


def weekly(limits, at):
    if limits.get('limit_id') not in (None, 'codex'):
        return None
    for key in ('primary', 'secondary'):
        row = run_costs.mapping(limits.get(key))
        used, reset = row.get('used_percent'), row.get('resets_at')
        if (row.get('window_minutes') == WEEK_MINUTES and run_costs.amount(used)
                and used <= 100 and run_costs.amount(reset) and at <= reset):
            return used, reset, limits.get('plan_type')


def codex(reader, since, until):
    by_account = defaultdict(list)
    seen, reasons, plans = set(), Counter(), set()
    for path in reader.rollout_paths():
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if modified < since:
            continue
        first = next(run_costs.events(path), {})
        meta = run_costs.mapping(first.get('payload'))
        if first.get('type') != 'session_meta' or meta.get('model_provider') not in (None, 'openai'):
            continue
        appeared = run_costs.timestamp(meta.get('timestamp') or first.get('timestamp'))
        if appeared is None or appeared > until:
            continue
        account, session = meta.get('creator_account_id'), meta.get('id') or meta.get('session_id')
        if not account or not session or session in seen:
            reasons['missing identity or duplicate rollout'] += 1
            continue
        seen.add(session)
        old_total = 0
        for row, payload in run_costs.codex_events(path):
            if row['type'] != 'event_msg':
                continue
            at = run_costs.timestamp(row.get('timestamp'))
            if at is None or at > until:
                continue
            usage = run_costs.mapping(payload.get('info')).get('total_token_usage')
            delta = 0
            if usage is not None:
                try:
                    counts = run_costs.codex_counts(usage)
                    total = counts['input'] + counts['output']
                    delta = total - old_total if total >= old_total else None
                    old_total = total
                except (ValueError, TypeError, AttributeError):
                    delta = None
            if at >= since:
                snapshot = weekly(run_costs.mapping(payload.get('rate_limits')), at)
                if snapshot and isinstance(snapshot[2], str) and snapshot[2]:
                    plans.add(snapshot[2])
                by_account[account].append((at, delta, snapshot))
    pairs, omitted, observed = [], 0, 0
    for stream in by_account.values():
        pending, complete, previous = 0, True, None
        for at, delta, snapshot in sorted(stream, key=lambda item: item[0]):
            complete = complete and delta is not None
            pending += delta or 0
            if snapshot is None:
                continue
            observed += 1
            upper, window, plan = snapshot
            if previous:
                last, lower, last_window, last_plan = previous
                points = upper - lower
                if window != last_window or plan != last_plan or points < 0:
                    reasons['reset, tier change or falling reading'] += 1
                elif (at - last > 1800 or not complete or (not pending and points)
                      or (upper >= 100 and lower >= 100)):
                    reasons['gap, missing tokens or saturated reading'] += 1
                    omitted += points
                else:
                    pairs.append((pending, points))
            previous, pending, complete = (at, upper, window, plan), 0, True
    evidence = calibration(pairs, omitted, reasons)
    if sum(any(item[2] for item in stream) for stream in by_account.values()) != 1 or len(plans) != 1:
        evidence['tokens_per_weekly_percent'] = None
    evidence.update(rollouts=len(seen), accounts_with_events=len(by_account), snapshots=observed, plan_labels=sorted(plans))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=run_grades.utc)
    parser.add_argument('--days', type=int, default=30)
    args = parser.parse_args()
    now = args.as_of or dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=args.days)).timestamp()
    until = now.timestamp()
    root = Path(os.environ.get('RSTACK_STATE') or '~/.local/state/rstack').expanduser()
    reader = run_costs.TokenReader()
    runs = {}
    for run in run_costs.events(run_grades.run_records.runs_path()):
        key = run.get('run_id') or (run.get('job'), run.get('utc'))
        runs[key] = run
    print(json.dumps(dict(as_of=now.isoformat(), days=args.days,
                          anthropic=claude(root / 'usage', runs.values(), reader, since, until),
                          openai=codex(reader, since, until)), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
