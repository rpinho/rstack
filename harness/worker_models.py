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
import agy_quota
import claude_cap
from claude_cap import load_allowance as _allowance
import harness_blocks


class MeteredRefusal(ValueError):
    """The selector's one hard line: a pay-as-you-go route (money). main() exits 4 on it, and launch.sh
    reroutes every other selector refusal to the leaderboard pick instead of stopping (RULE #1)."""


class NoRoom(ValueError):
    """11-20 (general): the Codex wrapper refused this job on its cap (RH_CODEX_CLOSED), and Claude (80% ceiling,
    lane shares) and agy have no room for it either. main() exits 5, and launch.sh queues the job instead of
    failing it (codex-budget.limit)."""

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


def claude_overflow(executor, model):
    """(agy model, note) when a Claude job should overflow to agy's Claude; None leaves it unchanged."""
    limit = os.environ.get('RH_CLAUDE_OVERFLOW_PERCENT', '').strip()
    if executor != 'claude' or model not in AGY_CLAUDE or not limit:
        return None
    allowance = _allowance()
    weekly = allowance.claude_weekly() if allowance else None
    if not weekly or weekly['weekly_used_percent'] < max(float(limit), claude_cap.SPEND_DOWN_CEILING
                                                         if claude_cap.spend_down(weekly) else 0):
        return None   # 11-22: in the spend-down hours the agy brake moves with the ceiling
    effort = os.environ.get('LAUNCH_EFFORT', '')
    tier = effort if effort in ('low', 'medium', 'high') else 'high'
    return model + '-' + tier, 'claude overflow via agy (weekly at {:g}%)'.format(weekly['weekly_used_percent'])


# 11-19 Ricardo: "It's everyday work. That's why it's very, very important that we delegate to other models.
# That's how we get real data of their performance." A share of real lane work in these roles goes to the models
# below instead of the leaderboard's first pick, so they collect graded everyday outcomes. Explicit, never
# silent: RH_DELEGATE_SHARE (0..1, unset = 0) turns it on, and the receipt and the log name the draw. Kimi is
# left out: it exists only through OpenRouter, which is refused (no pay-as-you-go).
DELEGATE_ROLES = ('review', 'judge', 'audit', 'mechanical', 'builder', 'batch', 'biology')
# 11-20 (Ricardo): Neon is the main Gemini (judgment roles, medium), Hydrogen the cheap one (batch and mechanical,
# low or medium); Argon is in no pool and Carbon (Ultra only) stays out.
DELEGATE_MODELS = ('gemini-4-neon-medium', 'gemini-4-hydrogen-low', 'gemini-4-hydrogen-medium',
                   'gpt-6.2-sol', 'gpt-6.2-astra', 'claude-sonnet-5-5')
# 11-22 (Ricardo via general): Neon also builds a record in biology.
GEMINI_ROLES = {'neon': ('review', 'judge', 'audit', 'builder', 'biology'), 'hydrogen': ('batch', 'mechanical')}
NEVER_PICKED = ('gemini-4-argon', 'gemini-4-carbon')   # no role, no delegate draw, no headroom move


# A spec that needs its model (a sealed referee, a cross-family check) says so in one line, and is never delegated:
#   Model pin: sealed referee for batch 3, must stay Opus
PIN = re.compile(r'^[ \t]*[-*]?[ \t]*model pin:[ \t]*(\S.*)$', re.I | re.M)


# A review for the science-publish gate counts only when its reviewer is one the gate accepts (11-20, math:
# math_c82r12rvb2_1120 was delegated to claude-sonnet-5-5 and could never count toward the two accepts). The
# spec says so in one line, and the pick is then held to the gate's own REVIEWERS, read from the gate itself:
#   Gate: science-publish
GATE = re.compile(r'^[ \t]*[-*]?[ \t]*gate:[ \t]*science-publish\b', re.I | re.M)


def spec_gate(text):
    return 'science-publish' if GATE.search(text or '') else ''


def gate_reviewers():
    """The science-publish gate's REVIEWERS tuple, parsed from the gate's source (RH_SCIENCE_PUBLISH_GATE, else
    `science-publish-gate` on PATH) rather than copied here, so the two cannot drift. Unreadable is a refusal."""
    import ast
    import shutil
    path = os.environ.get('RH_SCIENCE_PUBLISH_GATE') or shutil.which('science-publish-gate')
    try:
        tree = ast.parse(Path(path).read_text())
        for node in tree.body:
            if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REVIEWERS' for t in node.targets)):
                names = ast.literal_eval(node.value)
                if names and all(isinstance(n, str) and n for n in names):
                    return tuple(names)
    except (OSError, TypeError, ValueError, SyntaxError):
        pass
    raise ValueError('Gate: science-publish, but the gate\'s REVIEWERS cannot be read from {} '
                     '(set RH_SCIENCE_PUBLISH_GATE); not picking a reviewer the gate may not count'.format(path))


def gate_reviewer(model, reviewers):
    """True when the model id names one of the gate's reviewers as a whole part (opus, astra, fable, ...)."""
    return any('-{}-'.format(r) in '-{}-'.format(model) for r in reviewers)


def claude_fallback(role, data, excluded, families, requested, follows_route, chosen, hold=False):
    """Where a job goes when Claude is closed to it (ceiling, pacing, lane share): (model, executor, route_model),
    Codex's default for the role first (unless Codex is itself past 95%), then agy's Sonnet 5.5. Never a family
    the job judges. None when neither is available. Under a Claude hold (a 0% lane share; 11-22, general) the
    agy leg is agy's Gemini for the role (Neon, or Hydrogen for batch and mechanical), never agy's Claude."""
    run = runnable(requested, follows_route)
    allowance = _allowance()
    codex_full = False
    try:
        row = (allowance.cached(__import__('time').time()) or {}).get('codex') if allowance else None
        codex_full = bool(row) and float(row.get('weekly_used_percent') or 0) >= 95
    except (AttributeError, TypeError, ValueError, OSError):
        pass
    pick = PROVIDER_DEFAULT['codex'].get(role) or PROVIDER_DEFAULT['codex']['*']
    r = data['routes'].get(pick)
    if ('codex' in run and not codex_full and isinstance(r, dict) and r.get('cli') == 'codex'
            and pick not in excluded and r.get('canonical') not in excluded and maker(pick, r.get('canonical')) not in families):
        return pick, 'codex', None
    if hold:
        gemini = 'gemini-4-hydrogen-medium' if role in GEMINI_ROLES['hydrogen'] else 'gemini-4-neon-medium'
        r = data['routes'].get(gemini)
        if ('agy' in run and isinstance(r, dict) and r.get('cli') == 'agy' and gemini not in excluded
                and r.get('canonical') not in excluded and maker(gemini, r.get('canonical')) not in families):
            return gemini, 'agy', gemini
        return None
    model = chosen if chosen in AGY_CLAUDE else claude_cap.SONNET
    r = data['routes'].get(model)
    if ('agy' in run and isinstance(r, dict) and model not in excluded
            and maker(model, r.get('canonical')) not in families):
        effort = os.environ.get('LAUNCH_EFFORT', '')
        return model, 'agy', model + '-' + (effort if effort in ('low', 'medium', 'high') else 'high')
    return None


def spec_pin(text):
    found = PIN.search(text or '')
    return ' '.join(found.group(1).split())[:200] if found else ''


def producer_families(made_by='', workdir='', lane_dir=''):
    """({maker, ...}, [sources]) of the model that produced what this job judges.

    11-19, open-source lane: a delegate referee from the hunter's own family failed REFEREE_SAME_FAMILY. That
    check reads the hunter's family from the lane's PLANTS.jsonl (written by rh bughunt referee-prompt from the
    claims file), not from LAUNCH_MADE_BY, so both are read here, with the same maker() map."""
    families, sources = set(), []
    if made_by:
        families.add(maker(made_by))
        sources.append('made_by ' + made_by)
    if workdir and lane_dir:
        try:
            lines = (Path(lane_dir) / 'PLANTS.jsonl').read_text().splitlines()
        except OSError:
            lines = []
        target = os.path.realpath(str(workdir))
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('workdir') and os.path.realpath(row['workdir']) == target:
                family = row.get('hunter_maker') or maker(row.get('hunter_family'), row.get('hunter_model'))
                if family:
                    families.add(family)
                    sources.append('hunter {} (PLANTS batch {})'.format(family, row.get('batch')))
                break
    return families, sources


# 11-20 Ricardo: "If Codex is getting to the limit, you can just use my Claude. We have plenty of Claude...
# You can run everything at Claude now." The default executor goes to the provider with the most subscription
# headroom per hour left to its reset, read from the allowance reader. Explicit: the receipt and the log say
# "executor claude: headroom 100% / 63h to reset vs codex 43% / 98h". RH_HEADROOM_ROUTING=0 turns it off.
# agy publishes no figure, so it is never the default; it stays the 85% Claude brake (claude_overflow).
PROVIDER_DEFAULT = {
    'claude': {'batch': 'claude-sonnet-5-5', 'mechanical': 'claude-sonnet-5-5', 'cheap': 'claude-sonnet-5-5',
               '*': 'claude-opus-5-5'},
    'codex': {'review': 'gpt-6.2-astra', 'judge': 'gpt-6.2-astra', 'audit': 'gpt-6.2-astra', 'taste': 'gpt-6.2-astra',
              'design': 'gpt-6.2-astra', 'ideation': 'gpt-6.2-astra', '*': 'gpt-6.2-sol'}}
HEADROOM_HORIZON_H = 168   # a provider whose reset time is unknown is treated as a full week away


def headroom(now=None):
    """({provider: {used, hours, per_hour}}, None) for claude and codex from the allowance reader, or ({}, why)
    when either is unread. An unknown Claude reading also leaves one alert row for the conductor (11-20: it must
    never freeze silently)."""
    allowance = _allowance()
    if not allowance:
        return {}, 'allowance reader not found'
    import time
    now = time.time() if now is None else now
    data = allowance.cached(now)
    out = {}
    for provider in ('claude', 'codex'):
        row = data.get(provider)
        if not isinstance(row, dict) or row.get('weekly_used_percent') is None:
            why = '{} usage unknown'.format(provider)
            if provider == 'claude':
                why += ' ({})'.format(data.get('claude_unknown') or 'no reading')
                if hasattr(allowance, 'claude_unknown_alert'):
                    allowance.claude_unknown_alert(data.get('claude_unknown') or 'no reading', now)
            return {}, why
        resets = row.get('resets_at')
        hours = max((float(resets) - now) / 3600, 1.0) if resets else HEADROOM_HORIZON_H
        left = max(0.0, 100.0 - float(row['weekly_used_percent']))
        out[provider] = dict(used=float(row['weekly_used_percent']), hours=hours, per_hour=left / hours,
                             reset_known=bool(resets))
    return out, None


def headroom_line(order, rooms):
    parts = ['{} {:.0f}% / {:.0f}h to reset{}'.format(p, 100 - rooms[p]['used'], rooms[p]['hours'],
                                                       '' if rooms[p]['reset_known'] else ' (assumed)')
             for p in order]
    return 'executor {}: headroom {}'.format(order[0], parts[0].split(' ', 1)[1]) + ''.join(' vs ' + x for x in parts[1:])


def headroom_pick(role, chosen, data, excluded, families, rooms, unknown=None, executor=''):
    """(model, provider, line) when the headroom choice moves the pick to another provider's default, else
    (None, None, line); line is None when there is nothing to compare. With a reading unknown the last policy
    holds (the leaderboard pick on the requested executor) and the line says so."""
    route = data['routes'].get(chosen) or {}
    if os.environ.get('RH_HEADROOM_ROUTING', '1') == '0' or route.get('cli') not in ('claude', 'codex'):
        return None, None, None
    if not rooms:
        if not unknown:
            return None, None, None
        return None, None, 'executor {}: {}; last policy kept (leaderboard pick {}, no headroom move)'.format(
            route.get('cli') or executor, unknown, chosen)
    order = sorted(rooms, key=lambda p: rooms[p]['per_hour'], reverse=True)
    for provider in order:
        if provider == route.get('cli'):
            return None, None, headroom_line([provider] + [p for p in order if p != provider], rooms)
        pick = PROVIDER_DEFAULT[provider].get(role) or PROVIDER_DEFAULT[provider]['*']
        r = data['routes'].get(pick)
        if (isinstance(r, dict) and r.get('cli') == provider and pick not in excluded
                and r.get('canonical') not in excluded and maker(pick, r.get('canonical')) not in families):
            return pick, provider, headroom_line([provider] + [p for p in order if p != provider], rooms)
    return None, None, None


def codex_delegates_today(add=False):
    """How many delegate picks went to a Codex route today; Sol and Astra draw on the Codex budget."""
    base = Path(os.environ.get('RSTACK_STATE_DIR') or
                Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack').expanduser()
    path = base / 'delegate' / 'codex-{}.count'.format(dt.date.today().isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        count = int(stream.read().strip() or 0)
        if add:
            stream.seek(0)
            stream.truncate()
            stream.write(str(count + 1))
            count += 1
    return count


def runnable(executor, follows_route=True):
    """The executors the calling launcher can actually run.

    11-19 23:52, games lane: a batch job was delegated to gemini-4-neon-medium (route agy), and the lanes'
    launcher, which ran only codex and claude, started Codex with that model; it exited in 17 s. The stopgap
    (829d256) kept a delegate on the executor the selection was asked for. 11-20: the lanes' launcher is now
    a thin exec into rstack tools/launch.sh, which runs codex, claude and agy, so a caller that follows the
    route it is given (--print-route, or select() from Python) may get any of the three. A caller that reads
    only the model name still gets its own executor or claude, as before. RH_LAUNCHER_EXECUTORS, when set,
    names exactly what the launcher can run (a host without one of the CLIs)."""
    named = os.environ.get('RH_LAUNCHER_EXECUTORS', '')
    named = {e.strip() for e in named.split(',') if e.strip()}
    run = named or ({'codex', 'claude', 'agy'} if follows_route else {executor, 'claude'})
    # 11-20 (general): RH_CODEX_CLOSED is set by launch.sh after the Codex wrapper refused this job on its cap;
    # the job is asked for again on what is left.
    return run - {'codex'} if os.environ.get('RH_CODEX_CLOSED', '').strip() else run


def codex_closed_pick(role, data, ranked, excluded, families):
    """Where a Codex pick goes when Codex refused the job on its cap: Claude's default for the role, the same pick
    the headroom choice moves work to (PROVIDER_DEFAULT), else the role's first Claude model. None when Claude is
    not open to it (excluded, or the family the job judges)."""
    def open_to(m):
        r = data['routes'].get(m)
        return (isinstance(r, dict) and r.get('cli') == 'claude' and m not in excluded and m not in NEVER_PICKED
                and r.get('canonical') not in excluded and maker(m, r.get('canonical')) not in families)
    first = PROVIDER_DEFAULT['claude'].get(role) or PROVIDER_DEFAULT['claude']['*']
    return next((m for m in [first] + list(ranked) if open_to(m)), None)


HYDROGEN_LOW, HYDROGEN_MEDIUM = 'gemini-4-hydrogen-low', 'gemini-4-hydrogen-medium'


def prefer_hydrogen_medium(pool, evidence, cost, min_n=5):
    """11-20: Hydrogen-medium is drawn before Hydrogen-low until low earns it on everyday work. Low leaves the
    pool while medium has under `min_n` graded tasks (medium is tried first), and again once both have enough
    unless low's everyday rate beats medium's, or ties it at a lower cost per passed task. Never raises and
    never empties a pool: a missing figure keeps both."""
    try:
        if HYDROGEN_LOW not in pool or HYDROGEN_MEDIUM not in pool:
            return pool
        low, med = evidence.get(HYDROGEN_LOW) or {}, evidence.get(HYDROGEN_MEDIUM) or {}
        if (med.get('n') or 0) < min_n:
            return [m for m in pool if m != HYDROGEN_LOW]
        if (low.get('n') or 0) < min_n:
            return pool               # medium is established; low gets its n=5 to earn the place
        lr, mr = low.get('rate'), med.get('rate')
        if lr is None or mr is None:
            return pool
        lc = ((cost or {}).get(HYDROGEN_LOW) or {}).get('pct_per_pass')
        mc = ((cost or {}).get(HYDROGEN_MEDIUM) or {}).get('pct_per_pass')
        earned = lr > mr or (lr == mr and lc is not None and mc is not None and lc < mc)
        return pool if earned else [m for m in pool if m != HYDROGEN_LOW]
    except (AttributeError, TypeError):
        return pool


# 11-22 (Ricardo, via general: "Have we been using Gemini Neon? ... We need to test it."): a paired trial on
# everyday work. ~/.config/rstack/model-trial.json = {"name": N, "role": ROLE, "models": [A, B], "n": 20} gives
# the next n jobs of that role to A and B by turns, ahead of the delegate draw. A job keeps its arm when it is
# selected again (a retry, a reroute). Graded as usual; `worker_models.py --trial-report` reads the results.
# Trash the file to end the trial; nothing else reads it.
# 11-23 (Ricardo via general: "Keep using Neon. People just rave about it."): the 11-22 trial drew one job in a
# day, because it covered builder only and lanes launch most builder jobs with --explore, which skipped it. Now
# "roles": [...] runs the trial in several roles with n jobs EACH, "@leaderboard" as an arm means the model the
# job would have run anyway (so a review job pits Neon against the review pick, not Opus), and an --explore job
# joins the trial too. An explicit --model or a spec's model pin is still the operator's choice and never enters.
TRIAL_TOP = '@leaderboard'


def _trial():
    path = Path(os.environ.get('RH_MODEL_TRIAL') or Path.home() / '.config/rstack/model-trial.json')
    try:
        t = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(t, dict):
        return None
    roles = t.get('roles') or ([t['role']] if t.get('role') else [])
    ok = t.get('name') and isinstance(roles, list) and roles and len(t.get('models') or ()) >= 2
    return dict(t, roles=roles) if ok else None


def trial_ledger():
    return Path(os.environ.get('RH_MODEL_TRIAL_LEDGER') or Path(os.environ.get('RSTACK_STATE_DIR') or
                Path.home() / '.local/state/rstack') / 'model-trial.jsonl')


def trial_rows(name, paths=None):
    rows = []
    for path in paths or [trial_ledger()]:
        try:
            lines = Path(path).read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and (not name or row.get('trial') == name):
                rows.append(row)
    return rows


def trial_pick(role, data, excluded, families, executors, quota, job, top=''):
    """(model, note, trial name) when this job is one of the trial's, else None. n counts per role."""
    t = _trial()
    if not t or role not in t['roles'] or not job:
        return None
    rows = trial_rows(t['name'])
    mine = next((r for r in rows if r.get('job') == job), None)
    jobs = list(dict.fromkeys(r.get('job') for r in rows if r.get('role', role) == role))
    if not mine and len(jobs) >= int(t.get('n') or 20):
        return None
    k = jobs.index(job) + 1 if mine and job in jobs else len(jobs) + 1
    # An arm listed twice gets two turns in each cycle (11-23: Neon at volume, 'models': [neon, neon, @leaderboard]).
    # 11-23 (general): "role_models": {role: [...]} gives a role its own arms (Fable 1 in 6 in review and judge).
    arms = (t.get('role_models') or {}).get(role) or t['models']
    models = [top if m == TRIAL_TOP else m for m in arms if m != TRIAL_TOP or top]
    if len(set(models)) < 2:
        return None                    # the job's own pick is the trial model: nothing to compare here
    first = mine['model'] if mine else models[(k - 1) % len(models)]
    for m in [first] + list(dict.fromkeys(x for x in models if x != first)):
        route = data['routes'].get(m)
        if (not isinstance(route, dict) or route.get('cli') not in executors or m in excluded
                or route.get('canonical') in excluded or maker(m, route.get('canonical')) in families):
            continue
        if route.get('cli') == 'agy' and quota and agy_quota.blocked_until(m, os.environ.get('LAUNCH_EFFORT'), table=quota):
            continue
        return m, 'model trial {} ({} job {} of {}): {} by turns{}'.format(
            t['name'], role, k, int(t.get('n') or 20), m, '' if m == first else ' ({} unavailable)'.format(first)), t['name']
    return None


def trial_report(name, ledgers, roles_file=None):
    """Lines: per model, graded jobs, pass/partial/fail, rate, median wall minutes and the leaderboard's cost."""
    rows = trial_rows(name, ledgers)
    latest = {}
    for row in rows:
        latest[row.get('job')] = row
    try:
        cost = (json.loads(Path(roles_file).read_text()).get('cost') or {}) if roles_file else {}
    except (OSError, ValueError):
        cost = {}
    stats = {}
    for job, row in latest.items():
        s = stats.setdefault((row.get('role') or '', row.get('model')),
                             dict(pass_=0, partial=0, fail=0, other=0, pending=0, wall=[], role=row.get('role')))
        try:
            receipt = json.loads(Path(row['receipt']).read_text())
        except (OSError, ValueError, KeyError):
            s['pending'] += 1
            continue
        grade = None
        try:
            for line in Path(row['receipt']).with_name('everyday-grades.jsonl').read_text().splitlines():
                try:
                    g = json.loads(line)
                except ValueError:
                    continue
                if isinstance(g, dict) and g.get('id') == 'grade-' + str(receipt.get('selection_id')):
                    grade = g.get('grade')
        except OSError:
            pass
        finished = _finished(str(row['receipt'])[:-len('.selection.json')], receipt.get('selection_id'))
        if finished and receipt.get('utc'):
            s['wall'].append((finished - dt.datetime.fromisoformat(receipt['utc'])).total_seconds() / 60)
        if grade == 'pass':
            s['pass_'] += 1
        elif grade in ('partial', 'fail'):
            s[grade] += 1
        elif grade:
            s['other'] += 1
        else:
            s['pending'] += 1
    out = []
    for (role, model), s in sorted(stats.items()):
        graded = s['pass_'] + s['partial'] + s['fail']
        wall = sorted(s['wall'])
        c = ((cost.get(s['role']) or {}).get(model) or {}).get('pct_per_pass')
        out.append('{} {}: {} graded (pass {}, partial {}, fail {}), rate {}, {} ungraded/retracted, {} pending; '
                   'median wall {}; leaderboard cost {}'.format(
                       role, model, graded, s['pass_'], s['partial'], s['fail'],
                       '{:.2f}'.format((s['pass_'] + .5 * s['partial']) / graded) if graded else 'n/a',
                       s['other'], s['pending'], '{:.0f} min'.format(wall[len(wall) // 2]) if wall else 'n/a',
                       '{}%/pass'.format(c) if c is not None else 'n/a'))
    return out


def delegate(role, data, excluded, made_by, top, draw, families=frozenset(), executors=('codex', 'claude', 'agy'),
             quota=None, skipped=None, job=''):
    """(model, note) when this selection is one of the delegated share, else None. An agy model whose logged quota
    reset has not passed is left out of the pool (quota: agy_quota.blocked()), and `skipped` gets a line for it."""
    trial = trial_pick(role, data, excluded, families, executors, quota, job, top=top)
    if trial:
        return trial
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
        gem = re.match(r'gemini-4-(\w+)', m)
        if gem and role not in GEMINI_ROLES.get(gem.group(1), ()):
            continue
        if (m == top or not isinstance(route, dict) or route.get('cli') not in executors
                or m in excluded or route.get('canonical') in excluded):
            continue
        if maker(m, route.get('canonical')) in families:
            continue
        held = agy_quota.blocked_until(m, os.environ.get('LAUNCH_EFFORT'), table=quota) if (
            route.get('cli') == 'agy' and quota) else None
        if held:
            if skipped is not None:
                skipped.append(agy_quota.skip_note(m, held))
            continue
        if route.get('cli') == 'codex' and codex_delegates_today() >= int(os.environ.get('RH_DELEGATE_CODEX_PER_DAY') or 6):
            continue   # Sol and Astra draw on the Codex budget: at most this many delegate picks a day
        pool.append(m)
    if not pool:
        return None
    n = lambda m: (evidence.get(m) or {}).get('n', 0)
    pool = prefer_hydrogen_medium(pool, evidence, (data.get('cost') or {}).get(
        ROLE_ROWS.get(role, role) if role not in data['roles'] else role, {}))
    # Fewest graded outcomes first, so every delegate reaches n=5; the draw breaks ties.
    pick = min(pool, key=lambda m: (n(m), hashlib.sha256((m + repr(draw)).encode()).hexdigest()))
    if data['routes'][pick].get('cli') == 'codex':
        codex_delegates_today(add=True)
    return pick, 'delegated share {:g} of {}: {} (everyday n={}) instead of the leaderboard pick {}'.format(
        share, role, pick, n(pick), top)


def select(role, executor, model='', override='', path=None, made_by='', job='', lane='', explore='', pin='',
           workdir='', lane_dir='', follows_route=True, gate=''):
    requested = executor
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
    families, family_sources = producer_families(made_by, workdir, lane_dir)
    # A job that judges another model's work: a judgment role, or a referee batch the lane planted.
    judging = role in JUDGMENT or any(src.startswith('hunter ') for src in family_sources)
    if judging and families and role not in JUDGMENT:
        def route_maker(m):
            route = data['routes'].get(m)
            return maker(m, route.get('canonical') if isinstance(route, dict) else None)
        eligible = [m for m in ranked if route_maker(m) not in families] or eligible
        if route_maker(eligible[0]) in families:
            raise ValueError('job {} judges {} work and every {} pick is from that family'.format(
                job, '/'.join(sorted(families)), role))
    if role in JUDGMENT:
        def canonical(model):
            route = data['routes'].get(model)
            return route.get('canonical') if isinstance(route, dict) else None

        eligible = [m for m in ranked if m not in excluded
                    and canonical(m) not in excluded
                    and maker(m, canonical(m)) not in families]
        if not eligible:
            raise ValueError(judgment_hint + 'role {} has no eligible leaderboard pick for maker {}'.format(role, made_by))
        # 11-20 (general, on the RULE #1 audit): any non-empty --model-override pins a judgment role, as for
        # every other role. It used to need "Ricardo: REASON", so math's Sonnet control arm, launched as a
        # review, ran on the leaderboard pick instead. The pin is logged as allowed-override.
        if model and not override.strip():
            raise ValueError(judgment_hint + 'role {} hard-coded model refused; the leaderboard picks {}; '
                             '--model requires --model-override REASON'.format(role, eligible[0]))
        if model:
            harness_blocks.record('selector.judgment-pin', 'fail-open', 'role {} pinned to {} instead of the '
                                  'leaderboard pick {}: {}'.format(role, model, eligible[0], override),
                                  job=job, outcome='allowed-override')
    if gate == 'science-publish':
        reviewers = gate_reviewers()
        eligible = [m for m in eligible if gate_reviewer(m, reviewers)]
        if not eligible:
            raise ValueError('role {}: no leaderboard pick is a science-publish gate reviewer ({})'.format(
                role, ', '.join(reviewers)))
        if (explore or model) and not gate_reviewer(explore or model, reviewers):
            raise ValueError('{} is not a science-publish gate reviewer ({})'.format(explore or model, ', '.join(reviewers)))
        # Held like a pinned spec: no headroom move and no delegation outside the gate's reviewers.
        pin = pin or 'science-publish gate: reviewers {}'.format(', '.join(reviewers))
    if role in INDEPENDENT and not made_by:
        raise ValueError(judgment_hint + 'role {} requires --made-by MODEL (LAUNCH_MADE_BY)'.format(role))
    if model and not override:
        raise ValueError('hard-coded model refused: --model requires --model-override REASON')
    if override and not model:
        raise ValueError('--model-override requires --model')
    # 11-20 (general): an explore pick is a deliberate experiment, so a model outside the role's pool runs as asked,
    # warned, and the receipt says so (math: `--explore claude-sonnet-5-5` for builder was rerouted to the
    # leaderboard pick, so the experiment never ran). It still needs a route.
    explore_outside = bool(explore) and explore not in ranked
    if explore_outside:
        if not isinstance(data['routes'].get(explore), dict):
            raise ValueError('--explore model {} is not in the role {} pool and has no route in the leaderboard'.format(
                explore, role))
        if harness_blocks.gate('selector.explore-pool', '--explore {} is not in the role {} pool; it runs as '
                               'asked'.format(explore, role), job=job, lane=lane):
            raise ValueError('--explore model is not in the role {} pool: {}'.format(role, explore))
    # 11-20: an agy model whose quota reset (agy-quota.jsonl) has not passed fails at once, so it is not picked.
    # The default pick moves to the next leaderboard model, the receipt says why; a named model is refused.
    quota, quota_skipped = agy_quota.blocked(), []
    effort = os.environ.get('LAUNCH_EFFORT')

    def held(m):
        route = data['routes'].get(m)
        return (agy_quota.blocked_until(m, effort, table=quota)
                if quota and isinstance(route, dict) and route.get('cli') == 'agy' else None)
    if explore or model:
        if held(explore or model):
            raise ValueError('role {}: {}; name another model'.format(role, agy_quota.skip_note(
                explore or model, held(explore or model))))
    else:
        for m in eligible:
            if not held(m):
                break
            quota_skipped.append(agy_quota.skip_note(m, held(m)))
        eligible = [m for m in eligible if not held(m)]
        if not eligible:
            raise ValueError('role {}: every leaderboard pick is blocked by agy quota ({})'.format(
                role, '; '.join(quota_skipped)))
    chosen = explore or model or eligible[0]
    switched, executor_choice = None, None
    if not (explore or model or pin):
        rooms, unknown = headroom() if os.environ.get("RH_HEADROOM_ROUTING", "1") != "0" else ({}, None)
        switched, provider, executor_choice = headroom_pick(role, chosen, data, excluded,
                                                            families if judging else frozenset(), rooms, unknown, executor)
        if switched:
            chosen = switched
            executor = provider
    # 11-20 (general): the Codex wrapper refused this job on its cap (codex-budget.limit) and launch.sh asks again
    # with RH_CODEX_CLOSED set. A Codex pick moves to Claude; the ceiling and lane shares below still apply, with
    # agy past them. A pick held to Codex (a pin, an explicit model) waits for Codex instead: NoRoom, queued.
    codex_closed = os.environ.get('RH_CODEX_CLOSED', '').strip()
    if codex_closed and (data['routes'].get(chosen) or {}).get('cli') == 'codex':
        moved = None
        if not (explore or model or pin) and 'claude' in runnable(requested, follows_route):
            moved = codex_closed_pick(role, data, eligible, excluded, families if judging else frozenset())
        if not moved:
            raise NoRoom('role {}: Codex refused this job ({}) and {}'.format(
                role, codex_closed, '{} is held to Codex'.format(chosen) if (explore or model or pin)
                else 'no Claude pick is open to it'))
        chosen = switched = moved
        executor = 'claude'
        executor_choice = 'executor claude: Codex refused this job ({})'.format(codex_closed)
    delegated, delegate_skip = None, ''
    if judging and not families:
        delegate_skip = 'judging job with an unknown producer family: not delegated'
    elif not (explore or model or pin):
        delegated = delegate(role, data, excluded, made_by, chosen, int(uuid.uuid4().hex[:8], 16) / 2 ** 32,
                             families if judging else frozenset(),
                             runnable(requested, follows_route) & {'claude', 'codex', 'agy'},
                             quota=quota, skipped=quota_skipped, job=job)
        if delegated:
            chosen = delegated[0]
    elif explore and not (model or pin):
        delegated = trial_pick(role, data, excluded, families if judging else frozenset(),
                               runnable(requested, follows_route) & {'claude', 'codex', 'agy'}, quota, job, top=chosen)
        if delegated:
            chosen = delegated[0]
    route = data['routes'].get(chosen)
    if (delegated or switched or gate or (quota_skipped and chosen != ranked[0])
            or (judging and families and chosen != (explore or model or ranked[0]))):
        executor = route['cli']   # named in the receipt and the log below; not a silent swap
    # 11-20: an explored model runs on its own CLI when the launcher can run it, as a delegate does; before, a
    # Claude model explored from a Codex job failed "no compatible codex route" and was rerouted away.
    if explore and isinstance(route, dict) and route.get('cli') in runnable(requested, follows_route):
        executor = route['cli']
    if isinstance(route, dict) and (role in JUDGMENT or (not model and route.get('cli') in ('openrouter', 'gemini'))):
        executor = route.get('cli')
        if executor not in ('codex', 'claude', 'agy', 'openrouter', 'gemini'):
            raise ValueError('role {} selected {}; unsupported executor route'.format(role, chosen))
    # 11-20: Claude ceiling, pacing, Sonnet default and lane share (claude_cap.py), before the route is fixed.
    cap, cap_route = None, None
    if executor == 'claude' and route and route.get('cli') == 'claude' and claude_cap.enabled():
        held = bool(explore or model or pin or gate)
        cap = claude_cap.decide(chosen, lane, role, claude_cap.SONNET in data['routes'], _allowance(), pinned=held)
        if cap['model'] != chosen:
            chosen, route = cap['model'], data['routes'][cap['model']]
        if cap['leave']:
            if held:
                raise ValueError('role {} selected {}: {}; a pinned or explicit model has no fallback'.format(
                    role, chosen, cap['leave']))
            cap_route = claude_fallback(role, data, excluded, families if judging else frozenset(), requested,
                                        follows_route, chosen, hold=cap.get('hold', False))
            if not cap_route and codex_closed:
                # 11-20 (general): Codex refused this job and Claude is past its ceiling or the lane's share, so the
                # job queues (launch.sh) rather than taking Claude past the line.
                raise NoRoom('role {} selected {}: {}; Codex refused this job ({}) and agy is not open to it'.format(
                    role, chosen, cap['leave'], codex_closed))
            if not cap_route:
                # RULE #1: the ceiling reroutes work; with nowhere to reroute it to, the job stays on Claude.
                if harness_blocks.gate('selector.claude-ceiling', 'role {} selected {}: {}; no Codex or agy fallback '
                                       'is available'.format(role, chosen, cap['leave']), job=job, lane=lane):
                    raise ValueError('role {} selected {}: {}; no Codex or agy fallback is available'.format(
                        role, chosen, cap['leave']))
                cap['notes'].append('{}; no fallback route, so it stays on {} (fail-open)'.format(cap['leave'], chosen))
            else:
                chosen = cap_route[0]
                route = data['routes'][chosen]
                executor = cap_route[1]
                cap['notes'].append('{}; moved to {}{}'.format(cap['leave'], chosen, ' on agy' if cap_route[1] == 'agy' else ''))
    # 11-19: refused here, before any receipt, as well as in the executor. Not a fallback: the
    # leaderboard names a subscription route, or this job does not run.
    why = metered_refusal(executor)
    if why:
        raise MeteredRefusal('role {} selected {}: {}'.format(role, chosen, why))
    if cap_route and cap_route[1] == 'agy':
        pass   # agy's Claude is reached through the claude route entry; the receipt names agy below
    elif not isinstance(route, dict) or not route.get('canonical') or route.get('cli') != executor:
        raise ValueError('role {} selected {}; no compatible {} route (no silent fallback)'.format(role, chosen, executor))
    if chosen in excluded or route['canonical'] in excluded:
        raise ValueError('model excluded from role ' + role)
    if role in JUDGMENT and made_by and maker(chosen, route['canonical']) == maker(made_by):
        raise ValueError(judgment_hint + 'role {} requires a different model family from {}'.format(role, made_by))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.:-]*', chosen):
        raise ValueError('invalid native model id')
    # The 85% brake moves Claude work to agy's Claude, only where the launcher can run agy.
    overflow = claude_overflow(executor, chosen) if 'agy' in runnable(requested, follows_route) else None
    if cap_route and cap_route[1] == 'agy':
        overflow = (cap_route[2], 'claude cap: ' + cap['leave'])
    if overflow and agy_quota.blocked_until(overflow[0], effort, table=quota):
        quota_skipped.append(agy_quota.skip_note(overflow[0], agy_quota.blocked_until(overflow[0], effort, table=quota)))
        if cap_route and cap_route[1] == 'agy':
            raise (NoRoom if codex_closed else ValueError)('role {} selected {}: {}; agy\'s Claude is out of quota too ({})'.format(
                role, chosen, cap['leave'], quota_skipped[-1]))
        overflow = None   # stays on Claude: agy's Claude is out of quota until then
    receipt = dict(schema=1, selection_id=uuid.uuid4().hex, utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        role=role, model=chosen, canonical=route['canonical'], executor=executor,
        roles_sha256=hashlib.sha256(raw).hexdigest(), roles_updated=data.get('updated'),
        model_override=override, source='delegate' if delegated else 'explore' if explore else 'override' if model else 'leaderboard', job=job, lane=lane, made_by=made_by)
    # 11-20: what the Codex wrapper is told this call is (launch.sh exports it as RSTACK_CALL_ROLE). A referee
    # (an independent judgment role, or a referee batch on a hunter's claims) may use the referee bucket.
    receipt['call_role'] = ('referee' if role in INDEPENDENT | {'referee'}
                            or any(src.startswith('hunter ') for src in family_sources) else role)
    if delegated:
        receipt['delegate'] = delegated[1]
        if len(delegated) > 2:
            receipt['trial'] = delegated[2]
    if pin:
        receipt['model_pin'] = pin
    if judging:
        receipt['producer_family'] = sorted(families) or 'unknown'
        if family_sources:
            receipt['producer_family_source'] = family_sources
    if cap and (cap['notes'] or cap['warning']):
        receipt['claude_cap'] = '; '.join(cap['notes'])
        if cap['warning']:
            receipt['claude_warning'] = cap['warning']
    if codex_closed:
        receipt['codex_refused'] = codex_closed
    if explore_outside:
        receipt['explore_outside_pool'] = '{} is not in the role {} pool; explored as asked'.format(explore, role)
    if delegate_skip:
        receipt['delegate_skipped'] = delegate_skip
    if quota_skipped:
        receipt['quota_skipped'] = quota_skipped
    if executor_choice:
        receipt['executor_choice'] = executor_choice + ('; leaderboard pick {} moved to {}'.format(
            eligible[0] if not (explore or model) else chosen, switched) if switched else '')
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


# 11-20: a job that ran into agy's quota tells nothing about the model, like a launcher error (--retract, 35454e6).
# It is recorded "ungraded" with note "quota", never pass, partial or fail, whoever grades it.
AGY_QUOTA_TEXT = re.compile(r'RESOURCE_EXHAUSTED|Individual quota reached', re.I)


def quota_failure(log, receipt):
    """A short reason when this selection's agy run hit the quota, else None. Reads the job log from the
    selection's MODEL_SELECTION line to its MODEL_OUTCOME: the executor's AGY_QUOTA line, or agy's own error
    text from an executor older than that line. On the way it copies AGY_QUOTA rows into this machine's quota
    log, so a controller whose --host job hit the quota on the host stops picking that model too."""
    if receipt.get('executor') != 'agy':
        return None
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return None
    sid, inside, part = receipt.get('selection_id'), False, []
    for line in lines:
        if line.startswith(('MODEL_SELECTION ', 'MODEL_OUTCOME ')):
            try:
                mine = json.loads(line.split(' ', 1)[1]).get('selection_id') == sid
            except (ValueError, AttributeError):
                mine = False
            if mine and line.startswith('MODEL_SELECTION '):
                inside = True
            elif mine:
                break
            continue
        if inside:
            part.append(line)
    text = '\n'.join(part)
    rows = agy_quota.hit(text)
    for row in rows:
        try:
            agy_quota.record(row)
        except OSError:
            pass
    if rows:
        row = agy_quota.annotate(dict(rows[-1]))
        return 'quota: agy {} {}'.format(row.get('model'), (
            '{} window until {}'.format(row.get('window'), row['blocked_until']) if row.get('blocked_until')
            else ' '.join(str(row.get('error')).split())[:120]))
    found = AGY_QUOTA_TEXT.search(text)
    return 'quota: agy ' + ' '.join(text[found.start():].splitlines()[0].split())[:120] if found else None


# 11-19 (general): grading never blocks a lane ("lanes never stop") and never depends on anyone remembering.
# A returned delegated job without a grade is recorded "ungraded" at once (counted, outside the rate) and listed
# for the morning report; a later grade for the same selection replaces it.
UNGRADED_HOURS = 24


def gradeable(receipt):
    """A returned job that owes a grade: a delegated pick, and (11-22, Ricardo via general) every judgment-role
    job however it was picked. A referee or reviewer passes when its verdict held (the other referee, the exact
    checker or a maintainer agreed) and fails when it was overturned; a consult passes when the session acted on
    it. Before this only delegates were asked, so the leaderboard's own review picks (Astra) were never graded."""
    return receipt.get('source') == 'delegate' or receipt.get('role') in JUDGMENT | {'referee'}


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
        # 11-23: receipts with no job field (the schema before the 11-19 grading gate) never owed a grade; one
        # of them stopped the whole nightly sweep with KeyError 'job' once judgment roles owed grades (53e55eb).
        if (not isinstance(r, dict) or 'job' not in r or not gradeable(r) or r.get('job') == skip_job
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


def _ungraded_tsv(state=None, host=None):
    import socket
    base = Path(state or os.environ.get('RSTACK_STATE_DIR') or
                Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack').expanduser()
    return base / 'asks-waiting' / '{}-ungraded.tsv'.format(host or socket.gethostname().split('.')[0])


def clear_ungraded(job, state=None, host=None):
    """A grade recorded later removes the job's morning-report row (11-19: a graded pass still showed)."""
    target = _ungraded_tsv(state, host)
    try:
        lines = target.read_text().splitlines(keepends=True)
    except OSError:
        return
    keep = [line for line in lines if line.split('\t', 1)[0] != job]
    if len(keep) != len(lines):
        target.write_text(''.join(keep))


def morning_report(rows, state=None, host=None, reason=None):
    """Write ungraded delegated jobs to the asks-waiting queue the morning report reads."""
    target = _ungraded_tsv(state, host)
    target.parent.mkdir(parents=True, exist_ok=True)
    # 11-19: a job recorded at return said 'not graded within 24 h' hours after launch; say which case it is.
    reason = reason or 'not graded within {} h'.format(UNGRADED_HOURS)
    with target.open('a') as stream:
        for job, lane, model in rows:
            stream.write('{}\tungraded delegated job {} ({}, lane {})\tgrade: {}; '
                         'counted, outside the rate until graded\n'.format(job, job, model, lane, reason))
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
    parser.add_argument('--workdir', default='', help='the job work dir: finds a referee batch\'s hunter in PLANTS.jsonl')
    parser.add_argument('--lane-dir', default='')
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
    parser.add_argument('--retract', metavar='JOB',
                        help='retract every grade of JOB (with --receipt-dir or --receipt, and --reason): a harness or '
                             'launcher error never counts against a model; the grade stays in the file, marked retracted')
    parser.add_argument('--reason', default='')
    parser.add_argument('--receipt-dir', type=Path)
    parser.add_argument('--trial-report', metavar='NAME', help='the paired model trial\'s results ("" = all)')
    parser.add_argument('--trial-ledger', type=Path, action='append', help='another Mac\'s model-trial.jsonl')
    args = parser.parse_args(argv)
    try:
        if args.trial_report is not None:
            for line in trial_report(args.trial_report, [trial_ledger()] + (args.trial_ledger or []), args.roles_file):
                print(line)
            return 0
        if args.retract:
            if not args.reason.strip():
                raise ValueError('--retract needs --reason (why the grade is not the model\'s)')
            where = args.receipt_dir or (args.receipt.parent if args.receipt else None)
            if not where:
                raise ValueError('--retract needs --receipt-dir or --receipt')
            path = Path(where) / 'everyday-grades.jsonl'
            hits = []
            for line in path.read_text().splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get('job') == args.retract and row.get('grade') != 'retracted':
                    hits.append(row)
            if not hits:
                raise ValueError('no grade for job {} in {}'.format(args.retract, path))
            for row in {r['id']: r for r in hits}.values():
                log_record(path, '', dict(id=row['id'], date=dt.date.today().isoformat(), source_kind='everyday',
                                          job=row['job'], grade='retracted', model=row.get('model'), role=row.get('role'),
                                          retracted=row.get('grade'), note=' '.join(args.reason.split())[:300]))
                print('retracted {} {} ({}): {}'.format(row['job'], row.get('grade'), row.get('model'), args.reason))
                harness_blocks.mark(row['job'], 'retract', 'auto-grade', args.reason)   # 11-22: counted as a harness bug
            clear_ungraded(args.retract)
            return 0
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
            if gradeable(receipt) and 'grade-' + str(receipt.get('selection_id')) not in _grades(args.receipt.parent):
                row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(),
                           source_kind='everyday', job=receipt.get('job'), grade='ungraded',
                           model=receipt.get('route_model') or receipt['model'], role=receipt.get('role'),
                           note=(quota_failure(args.log, receipt) if args.log else None) or 'returned without a grade')
                log_record(args.receipt.with_name('everyday-grades.jsonl'), '', row)
                if not row['note'].startswith('quota'):
                    morning_report([(row['job'], receipt.get('lane'), row['model'])], reason='returned without a grade')
                print('recorded ungraded: ' + row['job'])
            return 0
        if not args.log or not args.receipt:
            raise ValueError('--log and --receipt are required')
        if args.grade:
            receipt = json.loads(args.receipt.read_text())
            quota = quota_failure(args.log, receipt)
            row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(),
                       source_kind='everyday', job=receipt.get('job') or args.job,
                       grade='ungraded' if quota else args.grade,
                       model=receipt.get('route_model') or receipt['model'], role=receipt['role'],
                       note=' '.join(('{} (given {}: {})'.format(quota, args.grade, args.note) if quota
                                      else args.note).split())[:300])
            if quota:
                print('{} hit the agy quota, so it is recorded ungraded, not {}'.format(row['job'], args.grade),
                      file=sys.stderr)
            # The grade lands where the job's outcome is already recorded (its log), and in the grades file
            # beside its receipt, which the daily model scorer reads.
            log_record(args.log, 'MODEL_GRADE', row)
            log_record(args.receipt.with_name('everyday-grades.jsonl'), '', row)
            clear_ungraded(row['job'])
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
                         spec_pin(args.spec.read_text()) if args.spec and args.spec.is_file() else '',
                         args.workdir, args.lane_dir, follows_route=args.print_route,
                         gate=spec_gate(args.spec.read_text()) if args.spec and args.spec.is_file() else '')
        if receipt['role'] in JUDGMENT and args.spec and assigns_judgment_model(args.spec.read_text()):
            # RULE #1: the leaderboard's pick runs anyway; the spec's named model is only a warning.
            if harness_blocks.gate('selector.judgment-spec-model', '{}: the spec names a model for a judgment role; '
                                   'the leaderboard picks {} and that is what runs'.format(args.job, receipt['model']),
                                   job=args.job, lane=args.lane):
                return 2
        args.receipt.write_text(json.dumps(receipt, sort_keys=True) + '\n')
        log_record(args.log, 'MODEL_SELECTION', receipt)
        if receipt.get('trial') and str(args.receipt).endswith('.log.selection.json'):
            log_record(trial_ledger(), '', dict(trial=receipt['trial'], job=args.job, lane=args.lane,
                                                model=receipt['model'], role=receipt['role'], utc=receipt['utc'],
                                                receipt=str(args.receipt.resolve())))
        if receipt.get('executor_choice'):
            with Path(args.log).open('a') as stream:
                stream.write('{} job={}\n'.format(receipt['executor_choice'], args.job))
        for line in receipt.get('quota_skipped') or ():
            with Path(args.log).open('a') as stream:
                stream.write('{} job={}\n'.format(line, args.job))
            print('worker model: ' + line, file=sys.stderr)
        if receipt.get('delegate'):
            with Path(args.log).open('a') as stream:
                stream.write('{} job={}\n'.format(receipt['delegate'], args.job))
            print('worker model: ' + receipt['delegate'], file=sys.stderr)
        for key in ('explore_outside_pool', 'claude_cap', 'claude_warning'):
            if receipt.get(key):
                with Path(args.log).open('a') as stream:
                    stream.write('{}: {} job={}\n'.format(key, receipt[key], args.job))
                print('worker model: ' + receipt[key], file=sys.stderr)
        if receipt.get('overflow'):
            with Path(args.log).open('a') as stream:
                stream.write('{} job={} model={} route={}\n'.format(receipt['overflow'], args.job, receipt['model'],
                                                                     receipt['route_model']))
            print('worker model: ' + receipt['overflow'], file=sys.stderr)
        print(receipt.get('route_model') or receipt['model'])
        if args.print_route:
            print(receipt['executor'])
        return 0
    except MeteredRefusal as exc:
        harness_blocks.gate('selector.metered', str(exc), job=getattr(args, 'job', ''), lane=getattr(args, 'lane', ''))
        return 4
    except NoRoom as exc:
        print('worker model: no room: ' + str(exc), file=sys.stderr)
        return 5
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('worker model: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
