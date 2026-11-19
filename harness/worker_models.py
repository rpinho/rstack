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


# 11-19 Ricardo: "It's everyday work. That's why it's very, very important that we delegate to other models.
# That's how we get real data of their performance." A share of real lane work in these roles goes to the models
# below instead of the leaderboard's first pick, so they collect graded everyday outcomes. Explicit, never
# silent: RH_DELEGATE_SHARE (0..1, unset = 0) turns it on, and the receipt and the log name the draw. Kimi is
# left out: it exists only through OpenRouter, which is refused (no pay-as-you-go).
DELEGATE_ROLES = ('review', 'judge', 'audit', 'mechanical', 'builder', 'batch')
DELEGATE_MODELS = ('gemini-4-neon-low', 'gemini-4-neon-medium', 'gemini-4-argon-low', 'gemini-4-argon-medium',
                   'gemini-4-hydrogen-low', 'gemini-4-hydrogen-medium', 'gpt-6.2-sol', 'gpt-6.2-astra',
                   'claude-sonnet-5-5')


# A spec that needs its model (a sealed referee, a cross-family check) says so in one line, and is never delegated:
#   Model pin: sealed referee for batch 3, must stay Opus
PIN = re.compile(r'^[ \t]*[-*]?[ \t]*model pin:[ \t]*(\S.*)$', re.I | re.M)


def spec_pin(text):
    found = PIN.search(text or '')
    return ' '.join(found.group(1).split())[:200] if found else ''


def delegate(role, data, excluded, made_by, top, draw):
    """(model, note) when this selection is one of the delegated share, else None."""
    try:
        share = float(os.environ.get('RH_DELEGATE_SHARE') or 0)
    except ValueError:
        raise ValueError('RH_DELEGATE_SHARE must be a number from 0 to 1')
    roles = [r.strip() for r in (os.environ.get('RH_DELEGATE_ROLES') or ','.join(DELEGATE_ROLES)).split(',')]
    if share <= 0 or role not in roles or draw >= share:
        return None
    evidence = (data.get('evidence') or {}).get(ROLE_ROWS.get(role, role) if role not in data['roles'] else role, {})
    pool = []
    for m in DELEGATE_MODELS:
        route = data['routes'].get(m)
        if (m == top or not isinstance(route, dict) or route.get('cli') not in ('claude', 'codex', 'agy')
                or m in excluded or route.get('canonical') in excluded):
            continue
        if role in JUDGMENT and made_by and maker(m, route.get('canonical')) == maker(made_by):
            continue
        pool.append(m)
    if not pool:
        return None
    # Fewest graded outcomes first, so every delegate reaches n=5; the draw breaks ties.
    n = lambda m: (evidence.get(m) or {}).get('n', 0)
    pick = min(pool, key=lambda m: (n(m), hashlib.sha256((m + repr(draw)).encode()).hexdigest()))
    return pick, 'delegated share {:g} of {}: {} (everyday n={}) instead of the leaderboard pick {}'.format(
        share, role, pick, n(pick), top)


def select(role, executor, model='', override='', path=None, made_by='', job='', lane='', explore='', pin=''):
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
    delegated = None
    if not (explore or model or pin):
        delegated = delegate(role, data, excluded, made_by, chosen, int(uuid.uuid4().hex[:8], 16) / 2 ** 32)
        if delegated:
            chosen = delegated[0]
    route = data['routes'].get(chosen)
    if delegated:
        executor = route['cli']   # named in the receipt and the log below; not a silent swap
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
        model_override=override, source='explore' if explore else 'override' if model else 'delegate' if delegated else 'leaderboard', job=job, lane=lane, made_by=made_by)
    if delegated:
        receipt['delegate'] = delegated[1]
    if pin:
        receipt['model_pin'] = pin
    # 11-19: the receipt states what the pick rests on, everyday work first (n<5 = fewer than 5 graded tasks)
    # and the bench beside it, never instead of it.
    everyday = (data.get('evidence') or {}).get(row, {}).get(chosen) or {}
    receipt['everyday'] = ({'rate': everyday.get('rate'), 'n': everyday['n']}
                           if everyday.get('n', 0) >= 5 else 'n<5')
    bench = (data.get('bench') or {}).get(row, {}).get(chosen)
    if bench:
        receipt['bench'] = {'rate': bench.get('rate'), 'n': bench.get('n')}
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


# 11-19 (general): grading never blocks a lane ("lanes never stop") and never depends on anyone remembering.
# A returned delegated job without a grade is recorded "ungraded" at once (counted, outside the rate) and listed
# for the morning report; a later grade for the same selection replaces it.
UNGRADED_HOURS = 24


def _grades(receipts_dir):
    done = set()
    try:
        for line in (Path(receipts_dir) / 'everyday-grades.jsonl').read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                done.add(row.get('id'))
    except OSError:
        pass
    return done


def _finished(log, selection_id):
    """When the launcher recorded this selection's exit, or None while it runs."""
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith('MODEL_OUTCOME '):
            try:
                row = json.loads(line.split(' ', 1)[1])
            except ValueError:
                continue
            if row.get('selection_id') == selection_id:
                return dt.datetime.fromisoformat(row['finished'])
    return None


def grade_command(receipt_path):
    log = str(receipt_path)[:-len('.selection.json')]
    return '{} {} --grade pass|partial|fail --note WHY --receipt {} --log {}'.format(
        Path(sys.executable).name, Path(__file__).resolve(), receipt_path, log)


def ungraded(receipts_dir, lane='', skip_job='', now=None):
    """[(job, model, receipt path, finished)] for returned delegated jobs with no grade, oldest first.
    Jobs ungraded for UNGRADED_HOURS are recorded "ungraded" here and no longer listed."""
    now = now or dt.datetime.now(dt.timezone.utc)
    receipts_dir = Path(receipts_dir)
    done = _grades(receipts_dir)
    out = []
    for path in sorted(receipts_dir.glob('*.log.selection.json')):
        try:
            r = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (not isinstance(r, dict) or r.get('source') != 'delegate' or r.get('job') == skip_job
                or (lane and r.get('lane') != lane) or 'grade-' + str(r.get('selection_id')) in done):
            continue
        finished = _finished(str(path)[:-len('.selection.json')], r.get('selection_id'))
        if not finished:
            continue
        if now - finished > dt.timedelta(hours=UNGRADED_HOURS):
            log_record(receipts_dir / 'everyday-grades.jsonl', '', dict(
                id='grade-' + r['selection_id'], date=now.date().isoformat(), source_kind='everyday', job=r['job'],
                grade='ungraded', model=r.get('route_model') or r['model'], role=r.get('role'),
                note='not graded within {} h of its return'.format(UNGRADED_HOURS)))
            UNGRADED_TODAY.append((r['job'], r.get('lane'), r.get('route_model') or r['model']))
            continue
        out.append((r['job'], r.get('route_model') or r['model'], path, finished))
    return sorted(out, key=lambda x: x[3])


UNGRADED_TODAY = []


def morning_report(rows, state=None, host=None):
    """Write the jobs that timed out ungraded to the asks-waiting queue the morning report reads."""
    import socket
    base = Path(state or os.environ.get('RSTACK_STATE_DIR') or
                Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack').expanduser()
    target = base / 'asks-waiting' / '{}-ungraded.tsv'.format(host or socket.gethostname().split('.')[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a') as stream:
        for job, lane, model in rows:
            stream.write('{}\tungraded delegated job {} ({}, lane {})\tgrade: not graded within {} h; '
                         'counted, outside the rate\n'.format(job, job, model, lane, UNGRADED_HOURS))
    return target


def log_record(path, event, record):
    with Path(path).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write((event + ' ' if event else '') + json.dumps(record, sort_keys=True) + '\n')
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
    parser.add_argument('--log', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--record-ungraded', action='store_true',
                        help='at return: record a delegated job with no grade as "ungraded" and list it for the morning')
    parser.add_argument('--sweep-ungraded', type=Path, metavar='RECEIPTS_DIR',
                        help='record jobs ungraded for 24 h as "ungraded" and list them for the morning report')
    parser.add_argument('--outcome', type=int)
    parser.add_argument('--grade', choices=('pass', 'partial', 'fail'),
                        help='grade a returned job: credited to the model its --receipt ran, as everyday work')
    parser.add_argument('--note', default='')
    args = parser.parse_args(argv)
    try:
        if args.sweep_ungraded:
            ungraded(args.sweep_ungraded)
            if UNGRADED_TODAY:
                where = morning_report(UNGRADED_TODAY)
                for job, lane, model in UNGRADED_TODAY:
                    print('ungraded after {} h: {} ({}, lane {})'.format(UNGRADED_HOURS, job, model, lane))
                print('listed in ' + str(where))
            return 0
        if args.record_ungraded:
            receipt = json.loads(args.receipt.read_text())
            if receipt.get('source') == 'delegate' and 'grade-' + str(receipt.get('selection_id')) not in _grades(args.receipt.parent):
                row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(),
                           source_kind='everyday', job=receipt.get('job'), grade='ungraded',
                           model=receipt.get('route_model') or receipt['model'], role=receipt.get('role'),
                           note='returned without a grade')
                log_record(args.receipt.with_name('everyday-grades.jsonl'), '', row)
                morning_report([(row['job'], receipt.get('lane'), row['model'])])
                print('recorded ungraded: ' + row['job'])
            return 0
        if not args.log or not args.receipt:
            raise ValueError('--log and --receipt are required')
        if args.grade:
            receipt = json.loads(args.receipt.read_text())
            row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(),
                       source_kind='everyday', job=receipt.get('job') or args.job, grade=args.grade,
                       model=receipt.get('route_model') or receipt['model'], role=receipt['role'],
                       note=' '.join(args.note.split())[:300])
            # The grade lands where the job's outcome is already recorded (its log), and in the grades file
            # beside its receipt, which the daily model scorer reads.
            log_record(args.log, 'MODEL_GRADE', row)
            log_record(args.receipt.with_name('everyday-grades.jsonl'), '', row)
            print('graded {} {} ({})'.format(row['job'], args.grade, row['model']))
            return 0
        if args.outcome is not None:
            receipt = json.loads(args.receipt.read_text())
            receipt.update(exit_code=args.outcome, finished=dt.datetime.now(dt.timezone.utc).isoformat(),
                signal='executor_exit_only', quality='unscored')
            # Exit status is operational evidence, never a scientific quality score.
            log_record(args.log, 'MODEL_OUTCOME', receipt)
            return 0
        receipt = select(args.role, args.executor, args.model, args.model_override, args.roles_file,
                         args.made_by, args.job, args.lane, args.explore,
                         spec_pin(args.spec.read_text()) if args.spec and args.spec.is_file() else '')
        if receipt['role'] in JUDGMENT and args.spec and assigns_judgment_model(args.spec.read_text()):
            print('launch.sh refused {}: name the leaderboard role, not a model (LEADERBOARD.md); '
                  'the leaderboard picks {}'.format(args.job, receipt['model']), file=sys.stderr)
            return 2
        args.receipt.write_text(json.dumps(receipt, sort_keys=True) + '\n')
        log_record(args.log, 'MODEL_SELECTION', receipt)
        if receipt.get('delegate'):
            with Path(args.log).open('a') as stream:
                stream.write('{} job={}\n'.format(receipt['delegate'], args.job))
            print('worker model: ' + receipt['delegate'], file=sys.stderr)
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
