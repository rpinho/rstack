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
from bug_verdicts import maker

ROLES_FILE = settings.path('RH_ROLES_FILE', Path('.runtime/roles.json'))
JUDGMENT = frozenset(('review', 'judge', 'audit', 'taste', 'design', 'ideation'))
INDEPENDENT = frozenset(('review', 'judge', 'audit'))
ROLE_ROWS = {'judge': 'review', 'audit': 'review', 'design': 'taste'}
MODEL_NAMES = re.compile(r'\b(?:sonnet|haiku|opus|fable|astra|sol|deepseek|kimi|glm)\b|\b(?:gpt-|claude-)', re.I)
# Historical jobs also attach ref/rev/chk to a subject, e.g. c38ref or l1chk.
JUDGMENT_JOB = re.compile(
    r'(^|_)(?:ref|referee|review|rev|judge|audit|taste|design|chk|check|verify|'
    r'[a-z0-9]+(?:ref|rev|chk))(?=_|\d|$)', re.I)


def select(role, executor, model='', override='', path=None, made_by='', job='', lane=''):
    judgment_hint = ''
    if role == 'batch' and JUDGMENT_JOB.search(job):
        role = 'review'
        judgment_hint = ('job name {} makes this a judgment job; '
                         'pass --role review --made-by MODEL. '.format(job))
    path = path or ROLES_FILE
    override = (override or os.environ.get('MODEL_OVERRIDE_REASON', '')).strip()
    made_by = (made_by or os.environ.get('LAUNCH_MADE_BY', '')).strip()
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('roles'), dict) or not isinstance(data.get('routes'), dict):
        raise ValueError('leaderboard requires roles and routes objects')
    row = role if role in data['roles'] else ROLE_ROWS.get(role, role)
    ranked = data['roles'].get(row)
    if not isinstance(ranked, list) or not ranked or any(not isinstance(m, str) or not m for m in ranked):
        raise ValueError('missing/empty leaderboard role: ' + role)
    excluded = data.get('overrides', {}).get(row, {}).get('exclude', [])
    excluded = excluded + data.get('overrides', {}).get(role, {}).get('exclude', [])
    eligible = ranked
    if role in JUDGMENT:
        def canonical(model):
            route = data['routes'].get(model)
            return route.get('canonical') if isinstance(route, dict) else None

        eligible = [m for m in ranked if m not in excluded
                    and canonical(m) not in excluded
                    and (not made_by or maker(m, canonical(m)) != maker(made_by))]
        if not eligible:
            raise ValueError(judgment_hint + 'role {} has no eligible leaderboard pick for maker {}'.format(role, made_by))
        if model and not override.startswith('Ricardo:'):
            raise ValueError(judgment_hint + 'role {} hard-coded model refused; the leaderboard picks {}; '
                             '--model requires --model-override Ricardo: REASON'.format(role, eligible[0]))
    if role in INDEPENDENT and not made_by:
        raise ValueError(judgment_hint + 'role {} requires --made-by MODEL (LAUNCH_MADE_BY)'.format(role))
    if model and not override:
        raise ValueError('hard-coded model refused: --model requires --model-override REASON')
    if override and not model:
        raise ValueError('--model-override requires --model')
    chosen = model or eligible[0]
    route = data['routes'].get(chosen)
    if role in JUDGMENT and isinstance(route, dict):
        executor = route.get('cli')
        if executor not in ('codex', 'claude', 'openrouter'):
            raise ValueError('role {} selected {}; unsupported executor route'.format(role, chosen))
    if not isinstance(route, dict) or not route.get('canonical') or route.get('cli') != executor:
        raise ValueError('role {} selected {}; no compatible {} route (no silent fallback)'.format(role, chosen, executor))
    if chosen in excluded or route['canonical'] in excluded:
        raise ValueError('model excluded from role ' + role)
    if role in JUDGMENT and made_by and maker(chosen, route['canonical']) == maker(made_by):
        raise ValueError(judgment_hint + 'role {} requires a different model family from {}'.format(role, made_by))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.:-]*', chosen):
        raise ValueError('invalid native model id')
    receipt = dict(schema=1, selection_id=uuid.uuid4().hex, utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        role=role, model=chosen, canonical=route['canonical'], executor=executor,
        roles_sha256=hashlib.sha256(raw).hexdigest(), roles_updated=data.get('updated'),
        model_override=override, source='override' if model else 'leaderboard', job=job, lane=lane, made_by=made_by)
    if model:
        override_log = Path(os.environ.get('RH_MODEL_OVERRIDE_LOG') or Path(path).with_name('model-overrides.jsonl'))
        with override_log.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            entry = {k: receipt[k] for k in ('role', 'model', 'job', 'utc')}
            stream.write(json.dumps(dict(entry, reason=override), sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    return receipt


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
    parser.add_argument('--made-by', default='')
    parser.add_argument('--job', default='')
    parser.add_argument('--lane', default='')
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--print-route', action='store_true', help='print model then executor on separate lines')
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
        receipt = select(args.role, args.executor, args.model, args.model_override, args.roles_file,
                         args.made_by, args.job, args.lane)
        if receipt['role'] in JUDGMENT and args.spec and MODEL_NAMES.search(args.spec.read_text()):
            print('launch.sh refused {}: name the leaderboard role, not a model (LEADERBOARD.md); '
                  'the leaderboard picks {}'.format(args.job, receipt['model']), file=sys.stderr)
            return 2
        args.receipt.write_text(json.dumps(receipt, sort_keys=True) + '\n')
        log_record(args.log, 'MODEL_SELECTION', receipt)
        print(receipt['model'])
        if args.print_route:
            print(receipt['executor'])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('worker model: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
