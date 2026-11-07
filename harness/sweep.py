"""Outside-search stage: lane policy -> generated workers -> deterministic compiler.

Import has no side effects. Dry runs only read files. Stages run serially within
each lane; lanes start independently under per-lane locks.
"""
import settings
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
import lessons
import threading
from concurrent.futures import ThreadPoolExecutor
import idea_policy
import x_searches

UTC = dt.timezone.utc
# Queue intake uses UUIDs; manually authored search ideas also use BOARD-n.
# Every sweep report parser uses this same contract (no capturing groups).
ID_PATTERN = r'(?:[A-Z0-9]+-[0-9]+|[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})'
GITHUB_FIELDS = ('github_repo_queries', 'github_code_queries', 'github_watch_repos',
                 'github_fork_repos', 'github_import_queries')


def discovery_config(cfg):
    """Flat string arrays also work with the supported Python 3.9 TOML reader."""
    for key in GITHUB_FIELDS + ('x_queries',):
        cfg.setdefault(key, [])
        if not isinstance(cfg[key], list) or any(
                not isinstance(v, str) or not v.strip() or any(c in v for c in '\r\n\0')
                for v in cfg[key]):
            raise ValueError('SWEEP ' + key + ' must be a string array of nonempty single-line values')
    for key in ('github_watch_repos', 'github_fork_repos'):
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', repo)
               or repo.split('/')[1] in ('.', '..') for repo in cfg[key]):
            raise ValueError('SWEEP ' + key + ' must contain owner/repo names')


def github_commands(cfg):
    """Read-only discovery commands for workers; never execute during planning."""
    gh = os.environ.get('RH_GH', 'gh')
    commands = []
    for query in cfg.get('github_repo_queries', []):
        commands.append(('Repository search', [gh, 'search', 'repos', '--sort', 'updated',
                        '--order', 'desc', '--limit', '30', '--visibility', 'public', '--', query]))
    for key, label in (('github_code_queries', 'Code search'),
                       ('github_import_queries', 'Library importers (confirm actual imports)')):
        for query in cfg.get(key, []):
            commands.append((label, [gh, 'search', 'code', '--limit', '30', '--', query]))
    for repo in cfg.get('github_watch_repos', []):
        commands.append(('Watched repository', [gh, 'repo', 'view', repo]))
        for endpoint in ('commits', 'pulls', 'issues'):
            query = 'per_page=30' if endpoint == 'commits' else 'state=open&sort=updated&direction=desc&per_page=30'
            commands.append(('Watched ' + endpoint, [gh, 'api', '--method', 'GET',
                            'repos/{}/{}?{}'.format(repo, endpoint, query)]))
    for repo in cfg.get('github_fork_repos', []):
        commands.append(('Library forks', [gh, 'api', '--method', 'GET',
                        'repos/{}/forks?sort=newest&per_page=100'.format(repo)]))
    return ['{}: {}'.format(label, shlex.join(argv)) for label, argv in commands]


def x_query_text(lane, cfg):
    capture = cfg.get('x_capture_path')
    capture_step = ('# Capture metadata in ' + str(capture) + '\n' if capture else
                    '# General must configure x_local_file in INTAKE.toml before capturing results.\n')
    search_step = ('# Record a dated outcome, including zero hits: rh intake x-search '
                   + shlex.quote(lane.name) + ' --query Q [--subject S] --result none|hits --n N\n'
                   if capture else '')
    return ('# X browser queries: ' + lane.name + '\n'
            '# General session only; no X API. Workers have no route to X.\n'
            + capture_step
            + '# Then run rh intake ' + shlex.quote(lane.name) + ' --live.\n'
            '# Results reach workers only through intake in IDEAS.jsonl.\n'
            + search_step
            + '\n'.join(cfg.get('x_queries', [])) + '\n')


def stamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError):
        raise ValueError('invalid timestamp: ' + str(value))


def path_at(value, base):
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve()


def default_memory_floor(cfg):
    """A worker's memory_gib is its cap; it needs far less free to start. Never above 2 GiB by default."""
    return min(cfg['memory_gib'], 2)


def load(lane, rh):
    cfg = rh.config(lane / 'SWEEP.toml')
    if type(cfg.get('enabled')) is not bool:
        raise ValueError('SWEEP enabled must be true or false')
    cfg.setdefault('grandfather_max_age_days', 14)
    if type(cfg['grandfather_max_age_days']) is not int or cfg['grandfather_max_age_days'] < 0:
        raise ValueError('grandfather_max_age_days must be an integer >= 0')
    # Disabled lanes need no project, rules, launcher or report directories.
    if not cfg['enabled']:
        return cfg
    discovery_config(cfg)
    cfg['evidence_policy'] = idea_policy.enabled(lane)
    cfg.setdefault('worker_role', 'batch')
    if not isinstance(cfg['worker_role'], str) or not cfg['worker_role'].strip():
        raise ValueError('SWEEP worker_role must be a nonempty leaderboard role')
    if cfg.get('worker_model') and not str(cfg.get('model_override', '')).strip():
        raise ValueError('hard-coded worker_model refused: needs model_override reason')
    required = ('start_date', 'working_directory', 'rules_files', 'search_targets',
                'sources', 'banned_sources', 'allowed_tests', 'allowed_writes',
                'search_report', 'read_report', 'kill_report', 'launcher', 'run_directory')
    for key in required:
        if key not in cfg or not cfg[key]:
            raise ValueError('SWEEP missing ' + key)
    for key in ('rules_files', 'search_targets', 'sources', 'banned_sources', 'allowed_tests', 'allowed_writes'):
        if not isinstance(cfg[key], list) or not all(isinstance(v, str) and v.strip() for v in cfg[key]):
            raise ValueError('SWEEP ' + key + ' must be a nonempty string array')
    stamp(cfg['start_date'])
    for key, default, low, high in (
        ('testing_max_age_days', 3, 1, 365), ('max_load', 8, 1, 30),
        ('cores', 1, 1, 6), ('memory_gib', 6, 1, 6),
        ('min_free_gib', 30, 1, 1024), ('worker_timeout_minutes', 90, 1, 180),
        ('controller_min_free_gib', 2, 1, 1024),
        ('kill_test_max_minutes', 30, 1, 30), ('stagger_seconds', 60, 0, 3600), ('load_wait_minutes', 30, 0, 240)):
        cfg.setdefault(key, default)
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError('SWEEP {} must be an integer in [{}, {}]'.format(key, low, high))
    cfg.setdefault('max_cpu_busy_fraction', .85)
    if type(cfg['max_cpu_busy_fraction']) not in (int, float) or not 0 < cfg['max_cpu_busy_fraction'] <= 1:
        raise ValueError('SWEEP max_cpu_busy_fraction must be in (0, 1]')
    # memory_gib is a worker's CAP, not what it needs free to start; using it as the floor refused
    # sweeps on a 16 GB machine that the OS reported as half free. Default floor is 2 GiB.
    cfg.setdefault('min_free_memory_gib', default_memory_floor(cfg))
    if type(cfg['min_free_memory_gib']) not in (int, float) or cfg['min_free_memory_gib'] <= 0:
        raise ValueError('SWEEP min_free_memory_gib must be positive')
    cfg.setdefault('load_fallback', True)
    if type(cfg['load_fallback']) is not bool:
        raise ValueError('SWEEP load_fallback must be boolean')
    # Where this lane's workers run. Validated here, in the same shape launch.sh validates, so a
    # typo is a config error at sweep time rather than an ssh argument built from a bad string.
    cfg.setdefault('host', '')
    if not isinstance(cfg['host'], str) or (cfg['host'] and not HOST_RE.fullmatch(cfg['host'])):
        raise ValueError('SWEEP host must be an ssh alias or empty, got ' + repr(cfg['host']))
    if 'boards' in cfg and (not isinstance(cfg['boards'], list) or not cfg['boards'] or
                           any(not isinstance(b, str) or not re.fullmatch(r'[A-Z0-9]+', b) for b in cfg['boards'])):
        raise ValueError('SWEEP boards must be nonempty uppercase board names')
    if 'search_max_lines' in cfg and (type(cfg['search_max_lines']) is not int or cfg['search_max_lines'] < 1):
        raise ValueError('SWEEP search_max_lines must be a positive integer')
    cfg['cwd'] = path_at(cfg['working_directory'], lane)
    if not cfg['cwd'].is_dir():
        raise ValueError('sweep working directory missing: ' + str(cfg['cwd']))
    cfg['rules'] = []
    for name in cfg['rules_files']:
        p = path_at(name, lane)
        if not p.is_file() or not p.read_text().strip():
            raise ValueError('required rules file missing or empty: ' + str(p))
        cfg['rules'].append((str(p), p.read_text()))
    # Carry the complete current intake policy, including every banned reason,
    # into every worker. Never silently drop it when a file is missing.
    intake = lane / 'INTAKE.toml'
    if not intake.is_file():
        raise ValueError('required rules file missing: ' + str(intake))
    intake_cfg = rh.config(intake)
    rh.validate_config(intake_cfg)
    capture = intake_cfg.get('x_local_file', '')
    if not isinstance(capture, str) or any(c in capture for c in '\r\n\0'):
        raise ValueError('INTAKE x_local_file must be a single-line path string')
    cfg['x_capture_path'] = path_at(capture, lane) if capture else None
    cfg['rules'].append((str(intake), intake.read_text()))
    cfg['_lesson_rows'] = lessons.for_lane(lane, rh, n=12)
    cfg['launcher_path'] = path_at(cfg['launcher'], lane)
    cfg['run_path'] = path_at(cfg['run_directory'], cfg['cwd'])
    if not cfg['run_path'].is_relative_to(cfg['cwd']):
        raise ValueError('run_directory must be inside working_directory')
    return cfg


def reports(cfg, day):
    return {stage: path_at(cfg[stage + '_report'].replace('{date}', day), cfg['cwd'])
            for stage in ('search', 'read', 'kill')}


def complete(text):
    return bool(re.search(r'(?:^|\n)DONE\s*$', text))


def read_evidence(report, idea_id):
    if not re.fullmatch(ID_PATTERN, idea_id):
        raise ValueError('invalid idea id: ' + idea_id)
    text = Path(report).read_text()
    if not complete(text) or not re.search(r'^READ ' + re.escape(idea_id) + r':[ \t]*\S[^\n]+$', text, re.M):
        raise ValueError('read evidence requires READ {}: <judgment> and final DONE'.format(idea_id))
    return hashlib.sha256(text.encode()).hexdigest()


def mark_read(lane, idea_id, report, rh):
    report = Path(report).expanduser().resolve()
    digest = read_evidence(report, idea_id)
    with rh.locked(lane):
        current = rh.latest(rh.rows(lane / 'IDEAS.jsonl'))
        if idea_id not in current:
            raise ValueError('unknown idea id: ' + idea_id)
        row = dict(current[idea_id], read_at=rh.now(), read_report=str(report),
                   read_report_sha256=digest, revised=rh.now(), event='read')
        rh.append(lane / 'IDEAS.jsonl', row)


def valid_read(row):
    try:
        return (stamp(row['read_at']) <= dt.datetime.now(UTC)
                and read_evidence(row['read_report'], row['id']) == row['read_report_sha256'])
    except (OSError, KeyError, ValueError, TypeError):
        return False


def obligations(lane, cfg, rh, clock=None, history=None):
    """Current rows, but the original creation/promotion clocks from all history."""
    clock = clock or stamp(rh.now())
    history = rh.rows(lane / 'IDEAS.jsonl') if history is None else history
    start = stamp(cfg['start_date'])
    first, promoted = {}, {}
    for r in history:
        key = r['id']
        if key not in first:
            first[key] = stamp(r.get('created') or r.get('date') or r.get('ts'))
        if key not in promoted and (r.get('event') == 'promote' or r.get('status') == 'testing'):
            promoted[key] = stamp(r.get('testing_started') or r.get('revised') or r.get('created') or r.get('date') or r.get('ts'))
    due, errors, legacy = [], [], []
    max_age = cfg.get('grandfather_max_age_days', 14)
    if type(max_age) is not int or max_age < 0:
        raise ValueError('grandfather_max_age_days must be an integer >= 0')
    expired = clock >= start + dt.timedelta(days=max_age)
    old = [key for key, born in first.items() if born < start]
    if first and len(old) == len(first) and expired:
        errors.append('entire idea set is grandfathered and its exemption expired: {} rows; {} days from lane start_date'.format(len(old), max_age))
    for key, row in rh.latest(history).items():
        born = first[key]
        if born < start and not expired:
            legacy.append(key)
            continue
        if born > clock:
            errors.append('idea {} has a future creation timestamp'.format(key))
            continue
        # Closing a row doesn't erase an overdue read obligation.
        if not valid_read(row):
            due.append(key)
            if clock - born > dt.timedelta(days=3):
                errors.append('idea {} unread after 3 days'.format(key))
        if row.get('status') == 'testing':
            since = promoted[key]
            result = row.get('result_path')
            has_result = bool(result and Path(result).expanduser().is_file() and Path(result).expanduser().stat().st_size)
            if clock - since > dt.timedelta(days=cfg['testing_max_age_days']) and not has_result:
                errors.append('idea {} testing without a result after {} days'.format(key, cfg['testing_max_age_days']))
    return due, errors, legacy


def stage_snapshot(lane, cfg, rh):
    """Freeze obligations from one queue read at the start of each stage."""
    history = rh.rows(lane / 'IDEAS.jsonl')
    clock = stamp(rh.now())
    due, _, legacy = obligations(lane, cfg, rh, clock=clock, history=history)
    queue = rh.latest(history)
    cutoff = clock - dt.timedelta(days=3)
    for row in queue.values():
        if stamp(row.get('created') or row.get('date') or row.get('ts')) >= cutoff and row['id'] not in due:
            due.append(row['id'])
    return due, queue, legacy


def receipt_health(lane, rh):
    runs = {}
    for i, row in enumerate(rh.rows(lane / 'SWEEP_RUNS.jsonl')):
        runs[row.get('id') or row.get('started') or str(i)] = row
    errors = []
    for row in runs.values():
        if row.get('status') != 'started' or row.get('finished'):
            continue
        try:
            timeout = row.get('worker_timeout_minutes', 90)
            if type(timeout) not in (int, float) or timeout <= 0:
                raise ValueError('invalid timeout')
            if stamp(rh.now()) - stamp(row['started']) > dt.timedelta(minutes=3 * timeout + 30):
                errors.append('sweep-hung {}: started without finish for over {} minutes'.format(
                    row.get('id', '?'), 3 * timeout + 30))
        except (KeyError, ValueError, TypeError):
            errors.append('sweep-hung: invalid started receipt')
    return errors


def lint(lane, rh):
    hung = receipt_health(lane, rh)
    if not (lane / 'SWEEP.toml').exists():
        return hung, []  # Older harness fixtures and lanes without the stage.
    cfg = load(lane, rh)
    if 'start_date' not in cfg:
        raise ValueError('SWEEP missing start_date for lint')
    stamp(cfg['start_date'])
    cfg.setdefault('testing_max_age_days', 3)
    if type(cfg['testing_max_age_days']) is not int or cfg['testing_max_age_days'] < 1:
        raise ValueError('testing_max_age_days must be an integer >= 1')
    _, errors, legacy = obligations(lane, cfg, rh)
    errors.extend(hung)
    if not cfg['enabled']:
        return errors, legacy
    clock = stamp(rh.now())
    # A deliberate 26h bootstrap grace. Old rows are listed separately.
    if clock - stamp(cfg['start_date']) > dt.timedelta(hours=26):
        good = False
        for run in reversed(rh.rows(lane / 'SWEEP_RUNS.jsonl')):
            try:
                age = clock - stamp(run['finished'])
                if run.get('ok') and dt.timedelta(0) <= age <= dt.timedelta(hours=26):
                    paths = {k: Path(v) for k, v in run['reports'].items()}
                    good = all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == run['report_sha256'][k]
                               for k, p in paths.items()) and set(paths) == {'search', 'read', 'kill'}
                    if good and run.get('evidence_policy'):
                        ids = re.findall(r'^IDEA (' + ID_PATTERN + r'):', paths['search'].read_text(), re.M)
                        receipts = run.get('prior_art_receipts', {})
                        good = isinstance(receipts, dict) and set(receipts) == set(ids)
                        if good:
                            for receipt in receipts.values():
                                verified = idea_policy.prior_art(receipt['path'])
                                if verified['sha256'] != receipt['sha256']:
                                    good = False
                                    break
                    if good:
                        break
            except (OSError, KeyError, ValueError, TypeError):
                continue
        if not good:
            errors.append('no successful sweep report in 26 hours')
    return errors, legacy


def generate(stage, lane, cfg, paths, day, due, failures=()):
    x_outcomes_policy = (
        ' Dated X search outcomes also arrive through intake in X_SEARCHES.jsonl; '
        'applicable negative receipts establish coverage for their recorded date and scope.'
        if cfg.get('x_capture_path') else '')
    intro = [
        '# Harness outside search: {} / {} / {}'.format(lane.name, stage, day),
        'Working directory: ' + str(cfg['cwd']),
        'This is the {} stage. Run synchronously; no background workers.'.format(stage),
        'One worker at a time; low CPU priority (niceness 10 or higher is fine; never raise it, and never block because of it); <= {} cores; total process-tree RSS <= {} GiB; keep >= {} GiB free.'.format(
            cfg['cores'], cfg['memory_gib'], cfg['min_free_gib']),
        'Each kill test has at most {} minutes; GPU or larger jobs are BLOCKED.'.format(cfg['kill_test_max_minutes']),
        'No submissions, posting, paid APIs, pods, secrets, or sealed-data/board scoring.',
        'X POLICY (overrides all legacy source-spec X instructions): X results arrive ONLY through intake in IDEAS.jsonl.'
        + x_outcomes_policy
        + ' Workers have no other route to X. Do not search, browse, fetch or follow X/Twitter links, use any X API, or use web search, mirrors or proxies to reach X. Only the general session performs the browser step and supplies captured metadata through intake. Judge X intake metadata without opening its X source URL.',
        'Do not edit harness code, lane configs or queue files. Write only configured artifacts; the harness records explicit read receipts.',
        'Embedded source specs provide binding policy and formats. Execute only the current stage objective; other stages handle their own duties. Search/kill report line limits do not limit the READ report.',
        'Resolved operational paths below replace legacy report/queue paths in the source specs; all binding scientific and safety rules still apply.',
        'IDEAS queue: ' + str(lane / 'IDEAS.jsonl'),
    ]
    intro += ['## Shared lessons', 'rh lessons for {} -n 12'.format(lane.name),
              lessons.render(cfg.get('_lesson_rows', [])).rstrip() or '(no lessons yet)',
              'Promoted lessons name the enforcing code in promoted_to; follow that code.']
    intro += ['{} report: {}'.format(k, v) for k, v in paths.items()]
    for key in ('search_targets', 'sources', 'banned_sources', 'allowed_tests', 'allowed_writes'):
        intro.append(key + ':\n' + '\n'.join('- ' + v for v in cfg[key]))
    commands = github_commands(cfg)
    if commands:
        intro.append('First-class GitHub sources (search stage only; use the configured GitHub CLI):\n'
                     + '\n'.join(commands)
                     + '\nRead public methods and source, not predictions or scores. These are bounded first pages; report coverage/rate-limit failures honestly, use further read-only pages only when needed, and inspect prior seen repositories for recent changes. Code-search matches are leads: read the file to verify an actual library import and deduplicate by repository. Do not execute discovered code without the lane screens.')
    intro.append('X browser handoff for general only: ' + str(lane / 'X_QUERIES.txt')
                 + '\n' + x_query_text(lane, cfg))
    if stage == 'search' and cfg.get('x_capture_path'):
        journal = lane / 'X_SEARCHES.jsonl'
        entries = x_searches.recent(journal)
        intro.append('General-session X search outcomes from the last 14 days: ' + str(journal)
                     + '\n' + '\n'.join(json.dumps(row, ensure_ascii=False) for row in entries)
                     + '\nThese are dated search receipts, not posts or permission to search X. '
                     'For a relevant result=none row, cite "X searched on <utc date>, none on topic" '
                     'with its exact query and optional subject. Only claim the recorded scope; '
                     'missing, stale or unrelated rows do not establish coverage. '
                     'For result=hits use captured post metadata from intake; the hit count alone is not source evidence.')
    if stage == 'search' and cfg.get('evidence_policy'):
        negative_receipt = (
            'For a relevant dated result=none in X_SEARCHES.jsonl, instead copy that journal to the run directory '
            'and bind its capture_path/capture_sha256; set X status=none, hits=[], query and searched_at '
            'to the recorded query and utc, and cite its date/subject in note. '
            if cfg.get('x_capture_path') else '')
        intro.append('For every IDEA <ID>, write ' + str(paths['search'].parent / 'prior-art-<ID>.json')
                     + ' as schema=1 JSON with baseline (best public method and number), sources {github, x, papers, leaderboards}. '
                     'Each source needs status hits|none, query, searched_at (UTC ISO), hits (URL list), note. '
                     'X additionally needs capture_path and capture_sha256 for the existing general-session intake capture. '
                     'First copy the general-session capture bytes to this run directory under allowed_writes and reference that stable copy. '
                     + negative_receipt
                     + 'Use ONLY that captured metadata or the supplied dated outcomes; a missing/stale/inapplicable capture is blocked, never invent a search. '
                     'Record blocked sources honestly: incomplete coverage fails the compiler and stays queued for another pass. '
                     'For competition leaderboards use only lane-permitted public methods/rules; never prohibited predictions or scores. '
                     'The receipt is machine-checked with idea_policy.prior_art; a source name without a query/outcome is insufficient.')
    if stage == 'search':
        intro += ['Search outside sources for new methods, competitors, runnable public code, recent papers and community discussions. Read prior seen material first; append what you searched to the configured seen file if provided.',
                  'Follow the lane search spec verbatim, using the resolved report path. Use IDEA <id>: lines with URL, added signal, metric, first kill test and rules risk. IDs may be BOARD-n or UUID (32 hexadecimal digits or standard hyphenated UUID); preserve queue IDs exactly. With no new ideas, document the actual search and NOTHING NEW. End DONE or BLOCKED.']
    elif stage == 'read':
        intro += ['Read and judge every listed queue id, follow its source within the lane rules except X/Twitter URLs (intake metadata only); also inspect newest intake rows from the last 3 days. A judged lead may be rejected; give the reason.',
                  'Required queue ids (all unmarked rows since stage start): ' + json.dumps(due),
                  'Write one explicit READ <queue-id>: <substantive judgment> per judged row, including every required id, to the read report. Do not mark a row you did not read. End DONE or BLOCKED.',
                  'If configured, also append every judged id, one per line, to seen_ideas. This compatibility file alone does not satisfy harness lint.']
    else:
        intro += ['Read the search report and run the first kill test for EVERY IDEA, in order. Fix the numerical pass line in writing before each run under allowed_writes. Apply every lane screen before using any data.',
                  'Write RESULT <idea-id>: KILLED|SURVIVED|BLOCKED then the number and pass line (or the concrete blocking need). Preserve BOARD-n or UUID ids exactly. Results for existing queue ids are also accepted; never invent an id. With no results write RESULT NONE. End DONE or BLOCKED.']
    if cfg.get('boards'):
        intro.append('Boards: ' + ', '.join(cfg['boards']) + '; at most 2 ideas each; account for every board with ideas or NOTHING NEW for that board.')
    if cfg.get('search_max_lines'):
        intro.append('Search report must have at most {} lines.'.format(cfg['search_max_lines']))
    for key in ('seen_file', 'seen_ideas'):
        if cfg.get(key):
            intro.append(key + ': ' + str(path_at(cfg[key], cfg['cwd'])))
    if failures:
        intro.append('ONE REPAIR PASS. Correct these compiler failures without relaxing policy:\n' + '\n'.join(failures))
    for name, text in cfg['rules']:
        intro.append('\n--- BEGIN VERBATIM LANE POLICY: {} ---\n{}\n--- END VERBATIM LANE POLICY ---'.format(name, text))
    return '\n\n'.join(intro) + '\n'


def check(paths, due, cfg=None, known_ids=None):
    errors, texts = [], {}
    for stage, p in paths.items():
        try:
            texts[stage] = p.read_text()
        except OSError:
            errors.append('no {} report'.format(stage))
            continue
        if not re.search(r'(?:^|\n)(DONE|BLOCKED)\s*$', texts[stage]):
            errors.append(stage + ' report unfinished')
        elif re.search(r'(?:^|\n)BLOCKED\s*$', texts[stage]):
            errors.append(stage + ' report BLOCKED')
    s, k, r = (texts.get(x, '') for x in ('search', 'kill', 'read'))
    ids = re.findall(r'^IDEA (' + ID_PATTERN + r'):[ \t]*\S[^\n]+$', s, re.M)
    malformed = [line for line in s.splitlines() if line.startswith('IDEA ') and not re.fullmatch(r'IDEA ' + ID_PATTERN + r':[ \t]*\S[^\n]+', line)]
    if malformed or len(ids) != len(set(ids)):
        errors.append('malformed or duplicate IDEA lines')
    results = re.findall(r'^RESULT (' + ID_PATTERN + r'): (KILLED|SURVIVED|BLOCKED)(?:[ \t]+([^\n]+))?$', k, re.M)
    got = {v[0] for v in results}
    if set(ids) - got:
        errors.append('ideas without a result: ' + ','.join(sorted(set(ids) - got)))
    if got - (set(ids) | set(known_ids or ())) or len(results) != len(got):
        errors.append('unexpected or duplicate RESULT lines')
    malformed_results = [line for line in k.splitlines() if line.startswith('RESULT ') and line != 'RESULT NONE' and not re.fullmatch(r'RESULT ' + ID_PATTERN + r': (KILLED|SURVIVED|BLOCKED)(?:[ \t]+[^\n]+)?', line)]
    if malformed_results:
        errors.append('malformed RESULT lines')
    if any(not detail.strip() for _, _, detail in results):
        errors.append('result missing number/pass line or blocking need')
    if not ids and not results and 'RESULT NONE' not in k.splitlines():
        errors.append('kill report empty')
    if not ids and 'NOTHING NEW' not in s:
        errors.append('search report has neither IDEA nor NOTHING NEW')
    read_pattern = r'READ (' + ID_PATTERN + r'):[ \t]*\S[^\n]+'
    read_ids = set(re.findall('^' + read_pattern + '$', r, re.M))
    if any(line.startswith('READ ') and not re.fullmatch(read_pattern, line) for line in r.splitlines()):
        errors.append('malformed READ lines')
    if known_ids is not None and read_ids - set(known_ids):
        errors.append('read judgments for unknown queue ids: ' + ','.join(sorted(read_ids - set(known_ids))))
    if set(due) - read_ids:
        errors.append('queue ids without a read judgment: ' + ','.join(sorted(set(due) - read_ids)))
    cfg = cfg or {}
    if cfg.get('search_max_lines') and len(s.splitlines()) > cfg['search_max_lines']:
        errors.append('search report exceeds lane line limit')
    for board in cfg.get('boards', []):
        count = sum(key.startswith(board + '-') for key in ids)
        if count > 2:
            errors.append('more than 2 ideas for ' + board)
        if not count and not any(board in line and 'NOTHING NEW' in line for line in s.splitlines()):
            errors.append('board unaccounted for: ' + board)
    if cfg.get('boards') and any(re.fullmatch(r'[A-Z0-9]+-[0-9]+', key)
                                 and key.rsplit('-', 1)[0] not in cfg['boards'] for key in ids):
        errors.append('unknown idea board')
    if cfg.get('evidence_policy'):
        for key in ids:
            try:
                idea_policy.prior_art(paths['search'].parent / ('prior-art-' + key + '.json'))
            except (OSError, ValueError, TypeError) as exc:
                errors.append('prior-art {}: {}'.format(key, exc))
    return errors


DISK_MARK = settings.path('RH_SWEEP_DISK_MARK', Path('.runtime/sweep-disk-refused'))


HOST_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z')


def execution_host(cfg):
    """The machine this lane's workers run on: '' for here.

    11-07: the science runs moved to a second machine with more memory and disk, and the only way
    to say so was `--host` on each launch or LAUNCH_HOST in the environment of whatever started the
    sweep. A lane whose data lives on the other machine should not depend on being remembered, so
    where the work runs is a lane setting (`host` in SWEEP.toml) like the cores and the memory cap.

    An explicit LAUNCH_HOST in the environment still wins, because that is how one run gets moved
    without editing the lane. The lane setting is the default, not an override.

    The work dir must exist at the same absolute path there; `launch.sh --host` refuses rather than
    running in the remote home, so a wrong host here stops the lane instead of writing elsewhere.
    """
    env = os.environ.get('LAUNCH_HOST', '').strip()
    if env:
        return env
    return str(cfg.get('host', '') or '').strip()


def host_free_bytes(host, path):
    """Free bytes at `path` on `host`, or None when it cannot be determined.

    None is not "fine": the caller refuses on it. A disk guard that passes when it cannot read
    the disk is not a guard, and an unreachable host would fail the sweep a minute later anyway.
    """
    try:
        out = subprocess.run(ssh_argv() + [host, 'df -k ' + shlex.quote(str(path))],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    # df -k columns: Filesystem 1024-blocks Used Available ... Available is the fourth.
    fields = lines[-1].split()
    try:
        return int(fields[3]) * 1024
    except (IndexError, ValueError):
        return None


def disk_guard(cfg):
    """Refuse below the disk floor, and say so once per episode.

    11-07: the floor checked the controller's disk, and the workers had just moved to another
    machine. math's sweeps were refused for "less than 30 GiB free" while the machine actually
    doing the work had hundreds of gigabytes spare, and the lane went to "deliverable cadence
    STALLED" for it. So min_free_gib now applies to the machine that runs the workers, which is
    the host when LAUNCH_HOST is set, and the controller keeps a smaller floor of its own
    (controller_min_free_gib) because the specs, logs, receipts and pulled-back status files still
    land here. The same variable that decides where the work runs decides which disk is measured;
    two settings that could disagree about that would be worse than one wrong one.

    Why (2026-11-06): the daily sweep refused every lane on this floor for a whole day and
    nothing said so. The lanes looked stopped, the cause was one line in a log nobody reads,
    and the conductor spent the next morning looking for a model shortage instead. A refusal
    that stops every lane has to announce itself.

    Once per episode, not once per lane per run: five lanes refusing the same full disk is one
    fact. The marker clears the first time the floor is met, so a new episode alerts again.
    """
    host = execution_host(cfg)
    local = shutil.disk_usage(cfg['cwd']).free
    if host:
        remote = host_free_bytes(host, cfg['cwd'])
        if remote is None:
            raise ValueError('sweep refused: cannot read the disk on {} (workers run there); '
                             'not assuming it has room'.format(host))
        needed = cfg['min_free_gib']
        floor = cfg['controller_min_free_gib']
        short = ('{} ({:.1f} GiB free, workers need {} GiB)'.format(host, remote / 1024**3, needed)
                 if remote < needed * 1024**3 else
                 'this machine ({:.1f} GiB free, the controller needs {} GiB for specs, logs and '
                 'pulled-back status)'.format(local / 1024**3, floor)
                 if local < floor * 1024**3 else '')
    else:
        needed = cfg['min_free_gib']
        short = ('this machine ({:.1f} GiB free, needs {} GiB)'.format(local / 1024**3, needed)
                 if local < needed * 1024**3 else '')
    if not short:
        try:
            DISK_MARK.unlink()
        except OSError:
            pass
        return
    if not DISK_MARK.exists():
        try:
            DISK_MARK.parent.mkdir(parents=True, exist_ok=True)
            DISK_MARK.write_text(dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
        except OSError:
            pass
        try:
            import lane_alerts
            lane_alerts.push(
                'sweep refused on the disk floor: {}. Every lane stays stopped until this '
                'clears.'.format(short))
        except (ImportError, OSError):
            pass
    raise ValueError('sweep refused on the disk floor: ' + short)


# Free memory, core count and CPU busy fraction, computed ON the machine that will run the work.
# One ssh for all three: the guard loop asks again every time it waits, and three round trips per
# wait would be three times the chance of a transient ssh failure stopping a lane.
#
# The macOS branch deliberately uses vm_stat alone, where the local probe takes the larger of
# vm_stat and memory_pressure. A smaller free-memory figure can only make the guard wait; a larger
# one could let a worker start on a machine that cannot hold it, and the m5 exists because the m4
# could not hold these jobs.
HOST_PROBE = r'''
if [ -r /proc/meminfo ]; then
  cores=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN)
  free=$(awk '/^MemAvailable:/ {printf "%.3f", $2/1048576}' /proc/meminfo)
else
  cores=$(sysctl -n hw.ncpu)
  free=$(vm_stat | awk '
    /page size of/ { for (k = 1; k <= NF; k++) if ($k == "of") ps = $(k+1) }
    $1 == "Pages" && $2 == "free:" { f = $3 }
    $1 == "Pages" && $2 == "inactive:" { n = $3 }
    $1 == "Pages" && $2 == "speculative:" { s = $3 }
    END { gsub(/\./, "", f); gsub(/\./, "", n); gsub(/\./, "", s)
          printf "%.3f", (f + n + s) * ps / 1073741824 }')
fi
busy=$(ps -A -o pcpu= 2>/dev/null | awk '{ s += $1 } END { printf "%.4f", s }')
printf 'cores=%s\nfree_gib=%s\nbusy_pcpu=%s\n' "$cores" "$free" "$busy"
'''


def ssh_argv():
    return shlex.split(os.environ.get('LAUNCH_SSH', 'ssh')) + ['-o', 'BatchMode=yes']


def host_probe(host):
    """{'cores', 'free_gib', 'busy'} for `host`, or None when any of it cannot be read.

    None is a refusal at the caller, never an assumption of headroom: the same discipline as
    host_free_bytes, and for the same reason. 11-07: the disk floor measured the controller while
    the work ran on another machine, math's sweeps were refused on a disk nothing was writing to,
    and the lane stalled for a day. Memory and CPU were measuring the wrong machine in exactly the
    same way, in the other direction: a 16 GB controller can refuse work that a 48 GB host has
    room for.
    """
    try:
        out = subprocess.run(ssh_argv() + [host, 'sh -s'], input=HOST_PROBE,
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    values = dict(line.split('=', 1) for line in out.stdout.splitlines() if '=' in line)
    try:
        cores = int(values['cores'])
        free_gib = float(values['free_gib'])
        busy = float(values['busy_pcpu']) / (100 * cores)
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    if cores < 1 or free_gib < 0 or not 0 <= busy < float('inf'):
        return None
    return dict(cores=cores, free_gib=free_gib, busy=busy)


def host_sync(cfg, host):
    """Refresh the lane onto the host, one way, before any worker reads it. True when it worked.

    math, 11-07, deciding how its sweeps move to the m5: "yes, but only as a one-way mirror, never
    as two live ledgers. This Mac stays the single authority for IDEAS.jsonl, RESULTS.jsonl,
    OUTREACH.jsonl, HANDOFF.md, SWEEP_RUNS.jsonl and reads/." So the controller pushes and the
    host never pushes back: a worker there reads the current queue and the current SEEN_IDEAS
    instead of whatever the lane looked like when it was last copied.

    The run directory and the lane's allowed writes are excluded, because those hold the worker's
    own outputs on the host and the pull brings back the parts the controller reads. No --delete,
    for the same reason: this refreshes what the worker reads, it does not reach into what the
    worker writes.
    """
    excludes = []
    for name in [cfg.get('run_directory', '')] + list(cfg.get('allowed_writes') or []):
        top = str(name).strip('/').split('/')[0]
        if top and '--exclude=/' + top + '/' not in excludes:
            excludes.append('--exclude=/' + top + '/')
    source = str(cfg['cwd']).rstrip('/') + '/'
    try:
        out = subprocess.run(['rsync', '-a', '--timeout=120', '-e',
                              os.environ.get('LAUNCH_SSH', 'ssh')] + excludes +
                             [source, host + ':' + source],
                             capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def host_workdir_missing(host, cwd, names):
    """Which of `names` are missing or empty under `cwd` on `host`; None when it cannot be read.

    `launch.sh --host` checks only that the work dir EXISTS there, and on 11-07 that was not
    enough: the m5 had directories at the lane paths holding five files and no IDEAS.jsonl, left
    over from the move. A lane pointed at that host would have passed the existence check and run
    a worker against a stub, which is worse than a refusal because the job would look like it ran.
    The sweep already refuses a missing or empty rules file on the controller; this is the same
    requirement, asked of the machine that will actually read them.
    """
    listing = '\n'.join('[ -s ' + shlex.quote(str(Path(cwd) / n)) + ' ] || echo ' + shlex.quote(n)
                        for n in names)
    try:
        out = subprocess.run(ssh_argv() + [host, 'sh -s'], input=listing + '\nexit 0\n',
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def cpu_busy():
    """Fraction of machine CPU in use; runnable/network-bound process count is irrelevant."""
    try:
        output = subprocess.check_output(['ps', '-A', '-o', 'pcpu='], text=True, timeout=10)
        values = [float(line.strip()) for line in output.splitlines() if line.strip()]
        cores = os.cpu_count()
        if not values or not cores or any(not 0 <= v < float('inf') for v in values):
            return None
        return sum(values) / (100 * cores)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def free_memory_gib():
    """Available/reclaimable RAM, not disk space; no GPU or external dependencies."""
    try:
        if sys.platform == 'darwin':
            output = subprocess.check_output(['vm_stat'], text=True, timeout=10)
            size = int(re.search(r'page size of (\d+) bytes', output).group(1))
            counts = {k: int(v) for k, v in re.findall(r'^(Pages [\w ]+):\s+(\d+)\.', output, re.M)}
            if not all(k in counts for k in ('Pages free', 'Pages inactive', 'Pages speculative')):
                raise ValueError('incomplete vm_stat')
            vm_gib = sum(counts[k] for k in ('Pages free', 'Pages inactive', 'Pages speculative')) * size / 1024**3
            # The kernel's own view (memory_pressure) also counts reclaimable file cache; take the larger.
            try:
                mp = subprocess.check_output(['memory_pressure', '-Q'], text=True, timeout=10)
                pct = int(re.search(r'free percentage:\s*(\d+)%', mp).group(1))
                total = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True, timeout=10))
                return max(vm_gib, pct / 100 * total / 1024**3)
            except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
                return vm_gib
        output = settings.path('RH_MEMINFO', Path('/proc/meminfo')).read_text()
        return int(re.search(r'^MemAvailable:\s+(\d+)', output, re.M).group(1)) / 1024**2
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None


def cancelled(cfg):
    if cfg.get('_cancel') is not None and cfg['_cancel'].is_set():
        raise ValueError('sweep cancelled')


def guard(cfg):
    deadline = time.monotonic() + cfg.get('load_wait_minutes', 30) * 60
    while True:
        cancelled(cfg)
        disk_guard(cfg)  # Preserve min_free_gib as the existing disk-space floor.
        # Memory and CPU headroom belong to the machine that runs the workers, like the disk floor.
        # A lane on the m5 must not be held back by the controller's 16 GB, and must not start
        # because the controller is idle while the m5 is full.
        host = execution_host(cfg)
        cores = os.cpu_count()
        if host:
            probe = host_probe(host)
            if probe is None:
                raise ValueError('sweep refused: cannot read memory or CPU on {} (workers run '
                                 'there); not assuming it has headroom'.format(host))
            memory, busy, cores = probe['free_gib'], probe['busy'], probe['cores']
        else:
            memory = free_memory_gib()
            busy = cpu_busy()
        reasons = []
        if memory is None:
            reasons.append('free memory unavailable')
        elif memory < cfg.get('min_free_memory_gib', cfg.get('memory_gib', 6)):
            reasons.append('insufficient free memory')
        if busy is None:
            # The load-average fallback reads this machine, so it is only a fallback for this
            # machine. With a host, an unreadable probe already refused above.
            if not cfg.get('load_fallback', True):
                reasons.append('CPU headroom unavailable (load fallback disabled)')
            elif os.getloadavg()[1] > cfg['max_load']:
                reasons.append('fallback 5-min load above {}'.format(cfg['max_load']))
        elif busy > min(cfg.get('max_cpu_busy_fraction', .85), 1 - cfg.get('cores', 1) / (cores or 1)):
            reasons.append('insufficient CPU headroom')
        if not reasons:
            return
        if time.monotonic() >= deadline:
            raise ValueError('sweep refused: ' + '; '.join(reasons))
        pause = min(30, max(0, deadline - time.monotonic()))
        if cfg.get('_cancel') is not None:
            cfg['_cancel'].wait(pause)
        else:
            time.sleep(pause)


def process_rss(pgid):
    data = subprocess.check_output(['/bin/ps', '-axo', 'pgid=,rss='], text=True)
    return sum(int(parts[1]) for line in data.splitlines()
               if len(parts := line.split()) == 2 and int(parts[0]) == pgid) * 1024


def run_worker(spec, cfg):
    """launch.sh derives spec/log names from $job relative to its own directory.

    A relative job path keeps generated prompts and launcher artifacts in the
    configured run directory, without modifying the launcher or shared specs.
    """
    guard(cfg)
    host = execution_host(cfg)
    if host:
        # Push before checking: the refresh is what makes the host's copy current, and the check
        # then confirms it arrived. A failed push means the worker would read a stale lane, which
        # is the failure this exists to prevent, so it refuses rather than running anyway.
        if not host_sync(cfg, host):
            raise ValueError('sweep refused: cannot refresh {} onto {} (workers read it there); '
                             'not running against a stale copy'.format(cfg['cwd'], host))
        # A lane may already list INTAKE.toml among its rules files; dedupe so the refusal does not
        # name the same file twice.
        names = list(dict.fromkeys([Path(p).name for p, _ in cfg.get('rules', [])] + ['INTAKE.toml']))
        missing = host_workdir_missing(host, cfg['cwd'], names)
        if missing is None:
            raise ValueError('sweep refused: cannot read {} on {} (workers run there)'
                             .format(cfg['cwd'], host))
        if missing:
            raise ValueError('sweep refused: {} on {} is missing or empty: {}. The work dir must be '
                             'the lane, not a directory at the lane\'s path.'
                             .format(cfg['cwd'], host, ', '.join(sorted(missing))))
    launcher = cfg['launcher_path']
    if not launcher.is_file():
        raise ValueError('launcher missing: ' + str(launcher))
    job = os.path.relpath(spec.with_suffix(''), launcher.parent)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS=str(cfg['cores']),
               OPENBLAS_NUM_THREADS=str(cfg['cores']), MKL_NUM_THREADS=str(cfg['cores']),
               VECLIB_MAXIMUM_THREADS=str(cfg['cores']), NUMEXPR_NUM_THREADS=str(cfg['cores']))
    env.pop('FORCE_LAUNCH', None)
    env.update(LAUNCH_ROLE=cfg.get('worker_role', 'batch'), LAUNCH_MODEL=cfg.get('worker_model', ''),
               LAUNCH_MODEL_OVERRIDE=cfg.get('model_override', ''),
               LAUNCH_HOST=execution_host(cfg))
    with spec.with_suffix('.worker.log').open('a') as log:
        # 11-02: no nice here; launch.sh already runs codex at nice 10 and the daily plist runs rh at nice 10.
        # Stacked nices reached 20 and workers refused to run (lane sweep BLOCKED).
        p = subprocess.Popen([str(launcher), job, str(cfg['cwd'])],
                             env=env, stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic() + cfg['worker_timeout_minutes'] * 60
        try:
            while p.poll() is None:
                cancelled(cfg)
                if time.monotonic() > deadline:
                    raise ValueError('worker timeout')
                if process_rss(p.pid) > cfg['memory_gib'] * 1024**3:
                    raise ValueError('worker process tree exceeded memory limit')
                disk_guard(cfg)
                time.sleep(2)
            return p.returncode
        finally:
            # launch.sh is synchronous. Clean any lingering processes even on
            # failure, interruption, or a launcher which unexpectedly detaches.
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            if p.poll() is None:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
            # Descendants may ignore TERM after their launcher already exited.
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def notify(lane, errors):
    command = settings.command('RH_NOTIFY_COMMAND', 'notify-agent')
    try:
        result = subprocess.run([*command, 'rh sweep {} failed: {}'.format(lane.name, '; '.join(errors))], timeout=30)
        if result.returncode:
            print('notification failed: exit {}'.format(result.returncode), file=sys.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        print('notification failed: ' + str(e), file=sys.stderr)


def run_lane(lane, cfg, rh, dry=False):
    # One immutable snapshot goes into every stage/repair and its receipt.
    cfg['_lesson_rows'] = lessons.for_lane(lane, rh, n=12)
    cfg['_lesson_ids_shown'] = []
    day = dt.date.today().isoformat()
    paths = reports(cfg, day)
    due, queue, legacy = stage_snapshot(lane, cfg, rh)
    print('{}: {} rows to read; grandfathered: {}'.format(lane.name, len(due), ','.join(legacy) or 'none'))
    if dry:
        print('Worker configuration: workers_enabled={}{}'.format(
            str(cfg.get('workers_enabled', True)).lower(),
            ' (explicit)' if 'workers_enabled' in cfg else ' (legacy default)'))
        print('Queue rows are queued ideas, not a count of configured sources.')
        print('DRY RUN: no workers, network, writes or notifications; search -> read -> kill -> check -> at most one repair')
        print('Would write browser handoff: ' + str(lane / 'X_QUERIES.txt'))
        for stage in ('search', 'read', 'kill'):
            print(generate(stage, lane, cfg, paths, day, due))
        return 0
    # The supervisor owns this artifact, including clearing obsolete queries on
    # an empty configuration. Dry runs preview it without creating/changing it.
    (lane / 'X_QUERIES.txt').write_text(x_query_text(lane, cfg))
    # Fresh attempt paths prevent yesterday's files (or a same-day rerun) from
    # passing a failed launcher. Canonical reports are only updated on success.
    attempt = cfg['run_path'] / (dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    attempt.mkdir(parents=True)
    scratch = {stage: attempt / (stage + '.report.md') for stage in paths}
    # Lane's canonical report directories may be outside its working directory.
    # They are explicit config writes, as in the original lane chain.
    errors = []
    started = rh.now()
    try:
        for pass_number in range(2):
            worker_errors = []
            for stage in ('search', 'read', 'kill'):
                stage_due, queue, _ = stage_snapshot(lane, cfg, rh)
                if stage == 'read':
                    due = stage_due
                spec = attempt / ('{}-{}.md'.format(pass_number, stage))
                spec.write_text(generate(stage, lane, cfg, scratch, day, stage_due, errors))
                cfg['_lesson_ids_shown'] = [row['id'] for row in cfg['_lesson_rows']]
                try:
                    rc = run_worker(spec, cfg)
                    if rc:
                        worker_errors.append('{} worker exit {}'.format(stage, rc))
                except (OSError, ValueError) as e:
                    worker_errors.append(stage + ': ' + str(e))
            # Freeze required reads at READ admission, but recognize genuine rows
            # arriving during any worker. Unjudged late arrivals wait for next run.
            queue = rh.latest(rh.rows(lane / 'IDEAS.jsonl'))
            errors = worker_errors + check(scratch, due, cfg, queue)
            if not errors:
                break
        if not errors:
            # Copy into immutable evidence before updating date-based reports.
            for stage, dest in paths.items():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(scratch[stage].read_text())
            judged = re.findall(r'^READ (' + ID_PATTERN + r'):[ \t]*\S[^\n]+$', scratch['read'].read_text(), re.M)
            for key in dict.fromkeys(judged):
                mark_read(lane, key, scratch['read'], rh)
    except (OSError, ValueError, KeyError) as e:
        errors.append(str(e))
    carried = carry_over(lane, scratch, rh, started, preserve_all=bool(errors))
    if carried:
        print('{}: re-queued unsettled ideas {}'.format(lane.name, ','.join(carried)))
    prior_receipts = {}
    if cfg.get('evidence_policy'):
        for idea_id in re.findall(r'^IDEA (' + ID_PATTERN + r'):', scratch['search'].read_text() if scratch['search'].is_file() else '', re.M):
            try:
                prior_receipts[idea_id] = idea_policy.prior_art(attempt / ('prior-art-' + idea_id + '.json'))
            except (OSError, ValueError, TypeError):
                pass  # check() already records the failure; do not manufacture a receipt.
    run = dict(id=cfg.get('_run_id', uuid.uuid4().hex), status='finished',
               started=cfg.get('_started', started), finished=rh.now(), ok=not errors,
               worker_timeout_minutes=cfg['worker_timeout_minutes'],
               evidence_policy=cfg.get('evidence_policy', False), prior_art_receipts=prior_receipts,
               lesson_ids=cfg['_lesson_ids_shown'], lessons_sha256=lessons.snapshot(cfg['_lesson_rows']),
               lessons_command='rh lessons for {} -n 12'.format(lane.name),
               reports={k: str(v) for k, v in scratch.items()}, errors=errors, carried=carried,
               rules_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in cfg['rules']},
               report_sha256={k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in scratch.items() if v.is_file()})
    with rh.locked(lane):
        rh.append(lane / 'SWEEP_RUNS.jsonl', run)
    cfg['_receipt_finished'] = True
    if errors:
        print('FAIL {}: {}'.format(lane.name, '; '.join(errors)))
        notify(lane, errors)
        return 1
    print('OK {}: sweep complete'.format(lane.name))
    return 0


def carry_over(lane, scratch, rh, started, preserve_all=False):
    """11-02 (lane): an idea a search found but no kill test settled (run failed, or RESULT BLOCKED) was orphaned:
    the worker marked it seen, so the next clean run never re-proposed it. Put each one in the lane queue as a
    new idea instead, once per sweep idea id and text."""
    try:
        s = scratch['search'].read_text() if scratch['search'].is_file() else ''
        k = scratch['kill'].read_text() if scratch['kill'].is_file() else ''
    except OSError:
        return []
    settled = {i for i, verdict in re.findall(r'^RESULT (' + ID_PATTERN + r'): (KILLED|SURVIVED)', k, re.M)}
    have = {(r.get('sweep_idea_id'), r.get('title_hash')) for r in rh.rows(lane / 'IDEAS.jsonl')}
    added = []
    for idea_id, text in re.findall(r'^IDEA (' + ID_PATTERN + r'):[ \t]*(\S[^\n]+)$', s, re.M):
        if idea_id in settled and not preserve_all:
            continue
        digest = rh.title_hash(text)
        if (idea_id, digest) in have:
            continue
        row = rh.new_idea('internal', '', text.strip()[:500], 'sweep-carryover', sweep_idea_id=idea_id,
                          title_hash=digest, carried_from_run=started)
        prior = scratch['search'].parent / ('prior-art-' + idea_id + '.json')
        if prior.is_file():
            row['prior_art'] = str(prior.resolve())
        with rh.locked(lane):
            # Dedup under the append lock too: concurrent/manual calls stay idempotent.
            if any(r.get('sweep_idea_id') == idea_id and r.get('title_hash') == digest
                   for r in rh.rows(lane / 'IDEAS.jsonl')):
                continue
            rh.append(lane / 'IDEAS.jsonl', row)
        added.append(idea_id)
    return added


def interrupted(signum, frame):
    raise KeyboardInterrupt('sweep interrupted by signal {}'.format(signum))


def run_locked(lane, config, rh, cancel):
    """One lane owns its lock and receipt even while waiting for machine resources."""
    import fcntl
    cfg = dict(config, _cancel=cancel, _run_id=uuid.uuid4().hex, _started=rh.now())
    with (lane / '.sweep-run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('REFUSED {}: another sweep is running for this lane'.format(lane.name), file=sys.stderr)
            return 1
        start = dict(id=cfg['_run_id'], status='started', started=cfg['_started'], ok=None,
                     worker_timeout_minutes=cfg['worker_timeout_minutes'])
        with rh.locked(lane):
            rh.append(lane / 'SWEEP_RUNS.jsonl', start)
        result, errors = 1, ['sweep interrupted before completion']
        try:
            guard(cfg)
            result = run_lane(lane, cfg, rh)
            errors = [] if not result else ['lane failed']
            return result
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors = [str(e)]
            print('REFUSED {}: {}'.format(lane.name, e), file=sys.stderr)
            return 1
        finally:
            if not cfg.get('_receipt_finished'):
                with rh.locked(lane):
                    rh.append(lane / 'SWEEP_RUNS.jsonl', dict(start, status='finished', finished=rh.now(),
                                                            ok=not result, errors=errors,
                                                            lesson_ids=cfg.get('_lesson_ids_shown', []),
                                                            lessons_sha256=lessons.snapshot(cfg.get('_lesson_rows', []))))


def main(root, args, rh):
    root = root.expanduser().resolve()
    lanes = sorted((root / 'lanes').iterdir()) if args.all else [root / 'lanes' / args.lane]
    selected, failed = [], False
    # Preflight all policy before starting anything; a missing file is a refusal.
    for lane in lanes:
        if not lane.is_dir():
            continue
        try:
            import lane_setup
            declaration_errors = lane_setup.audit(lane, rh)
            if declaration_errors:
                raise ValueError('; '.join(declaration_errors))
            cfg = load(lane, rh)
            if not args.dry_run and cfg.get('workers_enabled', True) is not True:
                raise ValueError('workers disabled; review the dry-run plan and configure SWEEP.toml workers_enabled=true before a real run')
            if not cfg['enabled']:
                print('SKIP {}: sweep disabled'.format(lane.name))
                continue
            selected.append((lane, cfg))
        except (OSError, ValueError, TypeError) as e:
            print('REFUSED {}: {}'.format(lane.name, e), file=sys.stderr)
            failed = True
    if not selected:
        return int(failed)
    if args.dry_run:
        results = [run_lane(lane, cfg, rh, True) for lane, cfg in selected]
        return int(failed or any(results))
    # Never open/touch the old root .sweep.lock: an old supervisor may still own it.
    # Thread supervisors perform I/O; each actual worker remains a separate nice-10 process.
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    cancel = threading.Event()
    try:
        if not args.all:
            failed |= bool(run_locked(*selected[0], rh, cancel))
        else:
            with ThreadPoolExecutor(max_workers=len(selected), thread_name_prefix='rh-sweep') as pool:
                futures = []
                try:
                    for i, (lane, cfg) in enumerate(selected):
                        if i:
                            time.sleep(cfg['stagger_seconds'])
                        futures.append(pool.submit(run_locked, lane, cfg, rh, cancel))
                    for future in futures:
                        failed |= bool(future.result())
                finally:
                    cancel.set()
    finally:
        cancel.set()
        signal.signal(signal.SIGTERM, previous_term)
    return int(failed)
