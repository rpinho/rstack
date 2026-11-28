#!/usr/bin/env python3
"""Report grading gaps. Use --alert on the hourly tick, or run read-only by default."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
from pathlib import Path
import shutil
import subprocess
import sys

import run_grades
from run_grades import run_records


def is_routine(run):
    """A run from before the run table (fac78df) with no launch receipt: a routine job with no grader.
    New routine runs are closed by the executor as "void: no launcher acceptance checks"."""
    if not run.get('legacy'):
        return False
    transcript = run.get('transcript')
    if not transcript:
        return True
    return not (Path(transcript).parent / '{}.log.selection.json'.format(run['job'])).exists()


def report(pairs, now, owed=False):
    counts, recent, failures = defaultdict(Counter), defaultdict(list), {}
    overdue = 0

    def gap(code, run, detail):
        age = (now - run_grades.utc(run['utc'])).total_seconds() / 3600
        failures[(code, run['run_id'])] = (
            f"{detail}: run_id={run['run_id']} job={run['job']} model={run['model']} age={age:.2f}h")

    routine = 0
    for run, record in pairs:
        if run_records.is_probe(run):
            continue
        grade = record[0] if record else {}
        if not grade and is_routine(run):
            routine += 1
            continue
        age = now - run_grades.utc(run['utc'])
        if dt.timedelta(0) <= age <= dt.timedelta(hours=24):
            model = run['model']
            recent[model].append(run)
            counts[model]['runs'] += 1
            if grade:
                counts[model]['graded'] += 1
                counts[model]['void' if grade['grade'].startswith('void:') else grade['grade']] += 1
        if not grade and age > dt.timedelta(hours=24):
            overdue += 1
        # 11-28 (general: planets_tnodes_1127 flagged "missing grade 2.3 h" while its job was still running, waiting on
        # purpose for a data window): a run that has not closed is not owed a grade yet. One still open after 24 h is
        # flagged anyway, so a stuck run is not hidden.
        if not grade and age > dt.timedelta(hours=2) and (run.get('closed_at') or age > dt.timedelta(hours=24)):
            gap('no-grade', run, 'missing grade')
        reason = grade.get('reason') or grade.get('note') or ''
        if grade.get('missing_files') or reason.startswith('workdir incomplete:'):
            gap('incomplete', run, reason if reason.startswith('workdir incomplete:') else
                'workdir incomplete: ' + ', '.join(grade['missing_files']))
    for model, runs in sorted(recent.items()):
        row = counts[model]
        if not row['graded']:
            for run in runs:
                gap('zero-grades', run, 'model has zero grades in 24h')
        print(model, ' '.join(f'{key}={row[key]}'
                              for key in ('runs', 'graded', 'pass', 'partial', 'fail', 'harness_fail', 'void')))
    if owed:
        print(f'owed >24h: {overdue} ungraded runs (all listed below; hourly FAIL rules retained)')
    if routine:
        print(f'routine: {routine} legacy runs with no launch receipt (x-engage, nightly jobs...) have no grader; '
              'not owed. New routine runs close themselves as void.')
    for message in failures.values():
        print(message)
    print('FAIL' if failures else 'PASS')
    return failures


def alert(failures, history):
    command = shutil.which('tell-general')
    if not command:
        print('score canary: tell-general unavailable; no alert sent', file=sys.stderr)
        return
    sent = {(row.get('code'), row.get('run_id')) for row in run_records.read_jsonl(history)}
    pending = {key: value for key, value in failures.items() if key not in sent}
    if not pending:
        return
    try:
        completed = subprocess.run([command, 'fyi', 'score canary FAIL\n' + '\n'.join(pending.values())],
                                   timeout=30)
        if completed.returncode:
            print(f'score canary: tell-general exited {completed.returncode}', file=sys.stderr)
            return
        for code, run_id in pending:
            run_records.append(history, dict(code=code, run_id=run_id))
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'score canary: alert unavailable ({exc})', file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owed', action='store_true', help='list ungraded runs older than 24h; retain hourly FAIL rules')
    parser.add_argument('--alert', action='store_true')
    parser.add_argument('--runs', type=Path, default=run_records.runs_path())
    args = parser.parse_args(argv)
    pairs, _ = run_grades.table(args.runs)
    failures = report(pairs, dt.datetime.now(dt.timezone.utc), owed=args.owed)
    if failures and args.alert:
        alert(failures, args.runs.with_name('score-canary-alerts.jsonl'))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
