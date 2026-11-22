#!/usr/bin/env python3
"""Read an opted-in job's result markers and record its one continuation."""
import json
from decimal import Decimal
from pathlib import Path
import re
import sys


def ledger_size(path):
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def new_result(path, offset, job, private):
    if ledger_size(path) < offset:
        raise ValueError(f'{path.name} was shortened during the job')
    try:
        stream = path.open('rb')
    except FileNotFoundError:
        return False
    with stream:
        stream.seek(offset)
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('new') is True and (row.get('job') == job or (private and 'job' not in row)):
                return True
    return False


def met_bar(report, ledgers, offsets, job):
    shipped = None
    for line in report.splitlines():
        line = line.strip().lower()
        if line in ('result: yes', 'verdict: pass'):
            return True
        if shipped is None and line.startswith('shipped:'):
            shipped = line.split(':', 1)[1].strip(' *_\x60')
    # 11-22 review: any Shipped line starting with nothing/none/no ("no new bound", "NO RESULT") is no result.
    if shipped and not re.match(r'^(?:nothing|none|no)\b', shipped):
        return True
    work, lane = ledgers
    return (new_result(work, offsets[0], job, work != lane)
            or (work != lane and new_result(lane, offsets[1], job, False)))


def minutes(seconds):
    return f'{seconds / 60:.2f}'


def update_receipt(path, receipt):
    tmp = path.with_suffix('.effort-floor.tmp')
    tmp.write_text(json.dumps(receipt, indent=2) + '\n')
    tmp.replace(path)


def main(argv):
    action, work, lane, *args = argv
    ledgers = tuple((Path(directory) / 'RESULTS.jsonl').resolve() for directory in (work, lane))
    if action == 'snapshot':
        print(*(ledger_size(path) for path in ledgers))
        return

    job, offsets, percent, elapsed, remaining, total, resumed, backend, budget, output, prompt, receipt = args
    percent, elapsed, remaining, total = map(int, (percent, elapsed, remaining, total))
    offsets = tuple(map(int, offsets.split()))
    report = Path(work) / 'REPORT.md'
    try:
        report_text = report.read_text(errors='replace')
    except FileNotFoundError:
        if resumed == '0':
            return
        report_text = ''
    if met_bar(report_text, ledgers, offsets, job):
        return

    receipt_path = Path(receipt)
    data = json.loads(receipt_path.read_text())
    if resumed == '1':
        data['effort_floor']['quit_at_seconds'] = elapsed
        update_receipt(receipt_path, data)
        return

    if backend == 'claude':
        spent = Decimal(str(json.loads(Path(output).read_text())['total_cost_usd']))
        available = Decimal(budget) - spent
        if not spent.is_finite() or spent < 0 or not available.is_finite() or available <= 0:
            raise ValueError('no verifiable Claude spend remains for a continuation')
        budget = str(available)

    with Path(prompt).open('a') as stream:
        stream.write(f'\n\ncontinue: you stopped at {minutes(elapsed)} of {minutes(total)} minutes with no result. '
                     f'You have {minutes(remaining)} minutes left. Do not repeat what your ledger or REPORT '
                     'already tried; widen or change the search, and say in REPORT.md what is different this time.\n')
    data['effort_floor'] = dict(percent=percent, resume_at_seconds=elapsed, budget_seconds=total,
                                remaining_seconds=remaining)
    update_receipt(receipt_path, data)
    print(budget)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, KeyError, AttributeError, ArithmeticError) as exc:
        print(f'effort floor: {exc}', file=sys.stderr)
        sys.exit(1)
