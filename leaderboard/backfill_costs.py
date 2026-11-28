#!/usr/bin/env python3
"""Backfill cost estimates to costs.jsonl beside the scorer's evaluations ledger."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path

import run_grades
from run_grades import run_costs


def backfill(evaluations, now, days=30, reader=None):
    evaluations = Path(evaluations)
    path = run_grades.costs_path(evaluations)
    if path == evaluations or path.is_symlink() or (
            path.is_file() and evaluations.is_file() and path.samefile(evaluations)):
        raise ValueError('costs.jsonl must be a separate sidecar file')
    start = now - dt.timedelta(days=days)
    reader = reader or run_costs.TokenReader()
    prices, plans = run_costs.config('prices'), run_costs.config('plans')
    pairs, _ = run_grades.table()
    records = {}
    for run, record in pairs:
        when = run_grades.utc(run.get('started_at') or run.get('utc'))
        if not record or not when or not start <= when <= now:
            continue
        grade = record[0]
        if grade.get('grade') not in ('pass', 'partial', 'fail'):
            continue
        key = run_grades.cost_key(run, grade)
        saved = run_grades.estimate(run, grade, {})
        if (used := run_costs.breakdown(saved.get('tokens'))) and not run_costs.breakdown(run.get('token_usage')):
            run = dict(run, token_usage=used)
        cost = run_costs.cost_for(run, reader, prices, plans)
        records[key] = dict(run_id=key[0], grade_id=key[1], model=key[2], run_started_at=when.isoformat(), cost_usd=cost)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open('a+b') as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        previous = run_grades.sidecar(path)
        # A killed writer can leave a partial final row. Preserve its bytes
        # and start the next complete row on a fresh line.
        output.seek(0, os.SEEK_END)
        unfinished = False
        if output.tell():
            output.seek(-1, os.SEEK_END)
            unfinished = output.read(1) != b'\n'
        for key, row in records.items():
            cost = row['cost_usd']
            old = previous.get(key)
            if cost == old or (old and run_costs.breakdown(old['tokens']) and not run_costs.breakdown(cost['tokens'])):
                continue
            if unfinished:
                output.write(b'\n')
                unfinished = False
            output.write((json.dumps(row, sort_keys=True, allow_nan=False) + '\n').encode())
            written += 1
        output.flush()
        os.fsync(output.fileno())
    return path, len(records), written


def main(argv=None):
    def end_time(value):
        when = run_grades.utc(value)
        if when is None:
            raise argparse.ArgumentTypeError('expected an ISO-8601 date or timestamp')
        return when

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--as-of', type=end_time, help='UTC window end (defaults to now)')
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error('--days must be positive')
    state = Path(os.environ.get('MODEL_STATE', '.runtime/leaderboard')).expanduser()
    evaluations = Path(os.environ.get('MODEL_LEDGER', str(state / 'evaluations.jsonl'))).expanduser()
    try:
        path, considered, written = backfill(evaluations, args.as_of or dt.datetime.now(dt.timezone.utc), args.days)
    except (OSError, ValueError) as exc:
        parser.exit(2, '{}\n'.format(exc))
    print('{}: {} graded runs, {} cost rows appended'.format(path, considered, written))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
