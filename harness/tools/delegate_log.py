#!/usr/bin/env python3
"""Record one driver session's shipped unit in the executor/scorer ledgers."""
import argparse
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_slugs import canon
import run_records
import score_verdicts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('model', 'task', 'verdict', 'asked', 'did', 'shipped'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--source', choices=['session'], required=True)
    parser.add_argument('--role', default='builder')
    parser.add_argument('--session', default='', help='agy-<lane> or claude-<lane> session name')
    parser.add_argument('--run-id', default='', help='stable unit id for retrying the same wrap-up')
    args = parser.parse_args(argv)
    try:
        verdict = score_verdicts.validate(args.verdict)
        model = canon(args.model)
        if not model:
            raise ValueError('unknown model: ' + args.model)
        ident = args.run_id or 'delegate-' + uuid.uuid4().hex
        row = dict(run_id=ident, utc=run_records.utc_now(), job=args.task, model=model,
                   effort='as run', role=args.role, backend='session', source=args.source,
                   driver=args.session, asked=args.asked, did=args.did, shipped=args.shipped)
        if not any(r.get('run_id') == ident for r in run_records.read_jsonl(run_records.runs_path())):
            run_records.append(run_records.runs_path(), dict(row, started_at=row['utc'], closed_at=row['utc'],
                                                           wall_seconds=None, tokens=None, cost_usd=None, rc=None))
        grade = run_records.grade_fields(ident, args.task, model, args.role, verdict, args.shipped,
                                        asked=args.asked, did=args.did, shipped=args.shipped, source=args.source)
        existing = any(r.get('run_id') == ident for r in run_records.read_jsonl(run_records.grades_path()))
        if not existing:
            run_records.append(run_records.grades_path(), grade)
        print(f'{ident}: {model} {verdict}')
    except (ValueError, OSError) as exc:
        # Refuse only this write. A wrap-up never fails the driver's completed work.
        print('delegate-log: ' + str(exc), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
