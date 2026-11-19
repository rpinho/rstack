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
import shlex
from shell_commands import shell_commands, command_argv
import sys
import uuid
from bug_verdicts import maker
from agent_executor import metered_refusal

ROLES_FILE = settings.path('RH_ROLES_FILE', Path('.runtime/roles.json'))
JUDGMENT = frozenset(('review', 'judge', 'audit', 'taste', 'design', 'ideation'))
INDEPENDENT = frozenset(('review', 'judge', 'audit'))
ROLE_ROWS = {'judge': 'review', 'audit': 'review', 'design': 'taste'}
# Historical jobs also attach ref/rev/chk to a subject, e.g. c38ref or l1chk.
JUDGMENT_JOB = re.compile(
    r'(^|_)(?:ref|referee|review|rev|judge|audit|taste|design|chk|check|verify|'
    r'[a-z0-9]+(?:ref|rev|chk))(?=_|\d|$)', re.I)


# Keep instruction detection shared by launch specs and the interactive hook. Model
# mentions in reports, questions and historical examples are not assignments.
_MODEL = (r'(?:[\w.-]+/)?(?:gpt-[\w.-]+|claude-[\w.-]+|'
          r'gemini(?:[- ][\w.-]+){0,2}|sonnet|haiku|opus|fable|astra|sol|deepseek|kimi|glm)')
_ACTION = r'(?:review|judge|referee|audit|taste|design)'
_ROLE = r'(?:reviews?|judges?|referees?|audits?|taste|design)'
_ASSIGNMENT = re.compile(
    r'^(?:please\s+)?(?:then\s+|now\s+)?(?:'
    r'(?:use|have|let|ask|assign)\s+[\"\x27`]?' + _MODEL + r'[\"\x27`]?\s+'
    r'(?:(?:to|for|as)\s+)?(?:(?:the|a|an|next)\s+){0,2}' + _ROLE + r'\b|'
    + _MODEL + r'\s+(?:should|must)\s+' + _ACTION + r'\b)', re.I)
_SHORT_ASSIGNMENT = re.compile(r'^' + _MODEL + r'\s+for\s+(?:the\s+)?' + _ROLE + r'\s*$', re.I)
_SELF_ASSIGNMENT = re.compile(
    r'^' + _MODEL + r'\s*\(you\)\s+for\s+[^.!?]*\b' + _ROLE + r'\b', re.I)
_REQUIRED_REVIEW = re.compile(
    r'^(?:same bar|require|obtain|ensure)\b[^.!?]*\b' + _MODEL + r'-confirmed\s+' + _ROLE + r'\b', re.I)
_JUDGMENT_TASK = re.compile(r'^(?:please\s+)?(?:then\s+|now\s+)?' + _ACTION + r'\b', re.I)
_REPORT = re.compile(r'\b(?:caught|completed|passed|scores?|results?)\s*:|\b\d+\s*/\s*\d+|'
                     r'\b(?:has been|have been|was|were)\b', re.I)


def instruction_clauses(text):
    """Keep wrapped instructions together and skip questions, including their lead-in."""
    for sentence in re.split(r'(?<=[.!?])\s+|;', text):
        if sentence.rstrip().endswith('?'):
            continue
        for clause in re.split(r'\n\s*(?:[-*]|\d+[.)])\s+', sentence):
            yield ' '.join(clause.replace('**', '').strip(' \t\r\n-*').split())


def model_assignment(text):
    """An imperative naming a judgment model, rather than a nearby model mention."""
    return any(_ASSIGNMENT.search(c) or _REQUIRED_REVIEW.search(c)
               or _SHORT_ASSIGNMENT.fullmatch(c.rstrip('.')) or _SELF_ASSIGNMENT.search(c)
               for c in instruction_clauses(text))


def judgment_task(text):
    """A direct judgment instruction to an already pinned executor/Agent."""
    return any(_JUDGMENT_TASK.search(c) and not _REPORT.search(c)
               for c in instruction_clauses(text))


def pinned_models(args):
    for i, arg in enumerate(args):
        if arg == '--':
            break
        if arg in ('--model', '-m') and i + 1 < len(args):
            yield args[i + 1]
        elif arg.startswith(('--model=', 'model=')):
            yield arg.split('=', 1)[1]
        elif arg.startswith('-m') and len(arg) > 2:
            yield arg[2:]


def judgment_command(args, piped=''):
    """Only executable launch/exec/run commands can pin a judgment worker."""
    argv = command_argv(args)
    if not argv:
        return False
    name = Path(argv[0]).name
    launch = (name in ('claude', 'launch.sh', 'launch', 'exec', 'run')
              or name.startswith(('launch-', 'run-'))
              or (name == 'codex' and argv[1:2] == ['exec'])
              or (len(argv) > 1 and argv[1] in ('launch', 'exec', 'run')))
    if not launch or not any(pinned_models(args)):
        return False
    for i, arg in enumerate(argv[1:], 1):
        if arg.startswith('--job=') and JUDGMENT_JOB.search(arg.split('=', 1)[1]):
            return True
        if arg.startswith('--role=') and arg.split('=', 1)[1] in JUDGMENT | {'referee'}:
            return True
        if arg == '--role' and i + 1 < len(argv) and argv[i + 1] in JUDGMENT | {'referee'}:
            return True
        if JUDGMENT_JOB.search(arg) and not arg.startswith('-') and not any(c.isspace() for c in arg):
            return True
        if judgment_task(arg.strip('\"\x27')) or model_assignment(arg):
            return True
    return '-' in argv and judgment_task(piped)


def assigns_judgment_model(text):
    return model_assignment(text) or any(judgment_command(args, piped)
                                         for args, piped in shell_commands(text))


# 11-19 Ricardo: agy serves Opus 5.5 and Sonnet 5.5 on a quota apart from the Claude Max weekly limit, to be
# used as overflow when that limit is tight. Explicit, never silent: only above RH_CLAUDE_OVERFLOW_PERCENT
# (unset = off), read from the allowance reader, and the receipt and the log both say so.
AGY_CLAUDE = {'claude-opus-5-5', 'claude-sonnet-5-5'}


def _allowance():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    here = Path(__file__).resolve().parent
    for tool in (here / 'rstack/tools/allowance', here.parent / 'rstack/tools/allowance'):
        if tool.is_file():
            spec = spec_from_loader('allowance', SourceFileLoader('allowance', str(tool)))
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


def claude_overflow(executor, model):
    """(agy model, note) when a Claude job should overflow to agy's Claude; None leaves it unchanged."""
    limit = os.environ.get('RH_CLAUDE_OVERFLOW_PERCENT', '').strip()
    if executor != 'claude' or model not in AGY_CLAUDE or not limit:
        return None
    allowance = _allowance()
    weekly = allowance.claude_weekly() if allowance else None
    if not weekly or weekly['weekly_used_percent'] < float(limit):
        return None
    effort = os.environ.get('LAUNCH_EFFORT', '')
    tier = effort if effort in ('low', 'medium', 'high') else 'high'
    return model + '-' + tier, 'claude overflow via agy (weekly at {:g}%)'.format(weekly['weekly_used_percent'])


def select(role, executor, model='', override='', path=None, made_by='', job='', lane='', explore=''):
    judgment_hint = ''
    if role == 'batch' and JUDGMENT_JOB.search(job):
        role = 'review'
        judgment_hint = ('job name {} makes this a judgment job; '
                         'pass --role review --made-by MODEL. '.format(job))
    path = path or ROLES_FILE
    override = (override or os.environ.get('MODEL_OVERRIDE_REASON', '')).strip()
    made_by = (made_by or os.environ.get('LAUNCH_MADE_BY', '')).strip()
    if explore and (model or override):
        raise ValueError('--explore cannot be combined with --model or --model-override')
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
    if explore and explore not in ranked:
        raise ValueError('--explore model is not in the role {} pool: {}'.format(role, explore))
    chosen = explore or model or eligible[0]
    route = data['routes'].get(chosen)
    if isinstance(route, dict) and (role in JUDGMENT or (not model and route.get('cli') in ('openrouter', 'gemini'))):
        executor = route.get('cli')
        if executor not in ('codex', 'claude', 'agy', 'openrouter', 'gemini'):
            raise ValueError('role {} selected {}; unsupported executor route'.format(role, chosen))
    # 11-19: refused here, before any receipt, as well as in the executor. Not a fallback: the
    # leaderboard names a subscription route, or this job does not run.
    why = metered_refusal(executor)
    if why:
        raise ValueError('role {} selected {}: {}'.format(role, chosen, why))
    if not isinstance(route, dict) or not route.get('canonical') or route.get('cli') != executor:
        raise ValueError('role {} selected {}; no compatible {} route (no silent fallback)'.format(role, chosen, executor))
    if chosen in excluded or route['canonical'] in excluded:
        raise ValueError('model excluded from role ' + role)
    if role in JUDGMENT and made_by and maker(chosen, route['canonical']) == maker(made_by):
        raise ValueError(judgment_hint + 'role {} requires a different model family from {}'.format(role, made_by))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.:-]*', chosen):
        raise ValueError('invalid native model id')
    overflow = claude_overflow(executor, chosen)
    receipt = dict(schema=1, selection_id=uuid.uuid4().hex, utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        role=role, model=chosen, canonical=route['canonical'], executor=executor,
        roles_sha256=hashlib.sha256(raw).hexdigest(), roles_updated=data.get('updated'),
        model_override=override, source='explore' if explore else 'override' if model else 'leaderboard', job=job, lane=lane, made_by=made_by)
    if overflow:
        # Same model, other route: evidence still credits the canonical model; the receipt shows the route.
        receipt.update(executor='agy', route_model=overflow[0], overflow=overflow[1])
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
    # agy: Gemini on the Antigravity subscription (`agy -p`). openrouter and gemini are metered API routes,
    # refused since 11-19 unless RH_ALLOW_OPENROUTER=1 / RH_ALLOW_GEMINI_API=1 (work already in flight).
    parser.add_argument('--executor', choices=('codex','claude','agy','openrouter','gemini'), default='codex')
    parser.add_argument('--model', default='')
    parser.add_argument('--explore', default='', help='select a candidate from this role pool without an override')
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
                         args.made_by, args.job, args.lane, args.explore)
        if receipt['role'] in JUDGMENT and args.spec and assigns_judgment_model(args.spec.read_text()):
            print('launch.sh refused {}: name the leaderboard role, not a model (LEADERBOARD.md); '
                  'the leaderboard picks {}'.format(args.job, receipt['model']), file=sys.stderr)
            return 2
        args.receipt.write_text(json.dumps(receipt, sort_keys=True) + '\n')
        log_record(args.log, 'MODEL_SELECTION', receipt)
        if receipt.get('overflow'):
            with Path(args.log).open('a') as stream:
                stream.write('{} job={} model={} route={}\n'.format(receipt['overflow'], args.job, receipt['model'],
                                                                     receipt['route_model']))
            print('worker model: ' + receipt['overflow'], file=sys.stderr)
        print(receipt.get('route_model') or receipt['model'])
        if args.print_route:
            print(receipt['executor'])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('worker model: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
