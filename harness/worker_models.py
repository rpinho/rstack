#!/usr/bin/env python3
"""Resolve execution roles locally and bind outcome receipts to that selection.

No inference/API calls. Call before an executor; do not silently substitute models.
"""
import settings
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROLES_FILE = settings.path('RH_ROLES_FILE', Path('.runtime/roles.json'))


def select(role, executor, model='', override='', path=None):
    path = path or ROLES_FILE
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('roles'), dict) or not isinstance(data.get('routes'), dict):
        raise ValueError('leaderboard requires roles and routes objects')
    ranked = data['roles'].get(role)
    if not isinstance(ranked, list) or not ranked or any(not isinstance(m, str) or not m for m in ranked):
        raise ValueError('missing/empty leaderboard role: ' + role)
    if model and not override.strip():
        raise ValueError('hard-coded model refused: --model requires --model-override REASON')
    if override.strip() and not model:
        raise ValueError('--model-override requires --model')
    chosen = model or ranked[0]
    route = data['routes'].get(chosen)
    if not isinstance(route, dict) or not route.get('canonical') or route.get('cli') != executor:
        raise ValueError('role {} selected {}; no compatible {} route (no silent fallback)'.format(role, chosen, executor))
    excluded = data.get('overrides', {}).get(role, {}).get('exclude', [])
    if chosen in excluded or route['canonical'] in excluded:
        raise ValueError('model excluded from role ' + role)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.:-]*', chosen):
        raise ValueError('invalid native model id')
    return dict(schema=1, selection_id=uuid.uuid4().hex, utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        role=role, model=chosen, canonical=route['canonical'], executor=executor,
        roles_sha256=hashlib.sha256(raw).hexdigest(), roles_updated=data.get('updated'),
        model_override=override.strip(), source='override' if model else 'leaderboard')


def log_record(path, event, record):
    with Path(path).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(event + ' ' + json.dumps(record, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', default='batch')
    # openrouter: a model routed through OpenRouter (run by codex with LAUNCH_PROVIDER=openrouter), e.g. a
    # third-family referee when the GPT referees fail their plants (11-09: 3 of 12 caught).
    parser.add_argument('--executor', choices=('codex','claude','openrouter'), default='codex')
    parser.add_argument('--model', default='')
    parser.add_argument('--model-override', default='')
    parser.add_argument('--roles-file', type=Path, default=ROLES_FILE)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--outcome', type=int)
    args = parser.parse_args(argv)
    try:
        if args.outcome is not None:
            receipt = json.loads(args.receipt.read_text())
            receipt.update(exit_code=args.outcome, finished=dt.datetime.now(dt.timezone.utc).isoformat(),
                signal='executor_exit_only', quality='unscored')
            # Exit status is operational evidence, never a scientific quality score.
            log_record(args.log, 'MODEL_OUTCOME', receipt)
            return 0
        receipt = select(args.role, args.executor, args.model, args.model_override, args.roles_file)
        args.receipt.write_text(json.dumps(receipt, sort_keys=True) + '\n')
        log_record(args.log, 'MODEL_SELECTION', receipt)
        print(receipt['model'])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('worker model: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
