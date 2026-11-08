#!/usr/bin/python3
"""Append-only research inputs. Python 3.9+, standard library only."""
import settings
import lane_setup
import argparse
import ast
import collections
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
import subprocess
from pathlib import Path
import re
import sqlite3
import shlex
import sys
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import time
import email.utils
import sweep
import lessons
import retro
import x_searches
import outreach
import bughunt
import cadence
import lane_alerts
import idea_policy
import selection_policy
import verification
from verification import verification_line
import pods
import publish_lint
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
# Standalone callers can choose a lane-specific science model in INTAKE.toml.
# cs.py hard-coded claude-opus-5 until then, which is why so many sessions ran on it.
CS_DEFAULT_MODEL = 'claude-opus-5-5'
CS_ALTERNATE_MODEL = 'claude-opus-4-6'
CS_BANNED_MODELS = {'claude-opus-5'}
CS_MODEL_RULE_MS = 1793387000000  # sessions before this are history, not violations
EXTERNAL = {'paper', 'community', 'x', 'claude-science', 'organiser', 'answers'}
# RH_OWNER_ALIASES: older ledgers recorded the operator by name; those names stay valid sources.
SOURCES = sorted(EXTERNAL | {'internal', 'owner'} | settings.names('RH_OWNER_ALIASES'))
STOP_PATTERNS = (r'no ideas', r'out of ideas', r'recommend stopping', r'we could stop', r'nothing left to try')
STATUSES = {'new', 'testing', 'closed', 'shipped'}
# Promote and close are taste calls (is it new, is it worth testing, is it dead), so they record who decided,
# and only these may decide. Sol may close an idea only mechanically: a result file showing the frozen bar failed.
TASTE_FALLBACK = ('claude-opus-5-5', 'claude-fable', 'claude-science')
ROLES_FILE = settings.path('RH_ROLES_FILE', Path('.runtime/roles.json'))


def taste_models(n=3):
    """Use the same roles file as worker_models; no model service or home executable."""
    try:
        data = json.loads(ROLES_FILE.read_text())
        top = data['roles']['taste'][:n]
        if top and all(isinstance(m, str) and m for m in top):
            return tuple(top) + ('claude-science',)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return TASTE_FALLBACK


TASTE_MODELS = TASTE_FALLBACK  # kept for imports; checks call taste_models()
TASTE_RULE_FROM = '2026-11-02T13:30:00'


def taste_error(decided_by):
    if not decided_by:
        return ('who decided? pass --decided-by (claude-opus-5-5, claude-fable-5-1 or claude-science:<frame url>); '
                'GPT-6.1 Sol does mechanical checks only (role policy)')
    if not decided_by.startswith(taste_models()):
        return 'decided_by={!r}: novelty and worth calls need a top taste model ({}), not {}'.format(
            decided_by, ', '.join(taste_models()), decided_by)
    return ''


def decider(arg):
    return (arg or os.environ.get('RH_DECIDED_BY') or session_model() or '').strip()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def recent(value, hours=24):
    try:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.timedelta(0) <= age <= dt.timedelta(hours=hours)
    except (ValueError, TypeError):
        return False


def rows(path):
    if not path.exists():
        return []
    result = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('expected an object')
                result.append(row)
            except (ValueError, TypeError) as e:
                raise ValueError('{}:{}: {}'.format(path, n, e))
    return result


def append(path, row):
    with path.open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


@contextlib.contextmanager
def locked(lane):
    with (lane / '.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def latest(history):
    return {r['id']: r for r in history}


def depth(history):
    return sum(r['status'] in {'new', 'testing'} for r in latest(history).values())


def promotion_error(row):
    if row.get('board', '').strip() == 'none':
        return '' if row.get('route', '').strip() else 'board=none requires route (expert/organiser/community path)'
    missing = [k for k in ('board', 'test', 'bar') if not row.get(k, '').strip()]
    return 'promotion requires ' + ', '.join(missing) if missing else ''


def title_hash(title):
    normalized = ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', title).casefold()))
    return hashlib.sha256(normalized.encode()).hexdigest()


def new_idea(source_type, source_url, claim, session='', **fields):
    if source_type not in SOURCES:
        raise ValueError('invalid source_type')
    if source_type in EXTERNAL and not source_url.strip():
        raise ValueError('external source_type {} requires source_url'.format(source_type))
    row = dict(id=uuid.uuid4().hex, created=now(), session=session,
               source_type=source_type, source_url=source_url.strip(), claim=claim,
               question_it_answers='', board='', test='', bar='', status='new',
               result_path='', closed_reason='', data_tags=[])
    row.update(fields)
    return row


from toml_subset import config, config_value  # noqa: E402,F401  (moved; rh.config stays)


def validate_config(cfg):
    if type(cfg.get('lessons_required', False)) is not bool:
        raise ValueError('lessons_required must be true or false')
    for field in ('lesson_tags', 'tags'):
        if field in cfg and (not isinstance(cfg[field], list) or any(not isinstance(v, str) for v in cfg[field])):
            raise ValueError(field + ' must be an array of strings')
    if not isinstance(cfg.get("verification_required", False), bool):
        raise ValueError("verification_required must be true or false")
    # board-deciding questions through a Claude Science session; lint and promote enforce it.
    if not isinstance(cfg.get('claude_science_required', False), bool):
        raise ValueError('claude_science_required must be true or false')
    age = cfg.get('claude_science_max_age_days', 2)
    if type(age) is not int or age < 1:
        raise ValueError('claude_science_max_age_days must be an integer >= 1')
    project = cfg.get('claude_science_project', '')
    if project and not re.match(r'https?://(localhost|127\.0\.0\.1)(:\d+)?/', project):
        raise ValueError('claude_science_project must be a localhost URL')
    model = cfg.get('claude_science_model', CS_DEFAULT_MODEL)
    if not isinstance(model, str) or not model.startswith('claude-'):
        raise ValueError('claude_science_model must be a Claude model id')
    if model in CS_BANNED_MODELS:
        raise ValueError('claude_science_model: {} is banned (configured model policy); use {} (alternate {})'.format(
            model, CS_DEFAULT_MODEL, CS_ALTERNATE_MODEL))
    # Optional tag-specific queue floors; tags are lane-defined strings.
    if 'depth_per_tag' in cfg and (type(cfg['depth_per_tag']) is not int or cfg['depth_per_tag'] < 1):
        raise ValueError('depth_per_tag must be an integer >= 1')
    if 'depth_tag_status' in cfg and not (isinstance(cfg['depth_tag_status'], list) and set(cfg['depth_tag_status']) <= STATUSES):
        raise ValueError('depth_tag_status must be a list of statuses')
    if 'depth_tags' in cfg and not (isinstance(cfg['depth_tags'], list) and all(isinstance(t, str) for t in cfg['depth_tags'])):
        raise ValueError('depth_tags must be a list of tag strings')
    if 'minimum_attempts' in cfg and (type(cfg['minimum_attempts']) is not int or cfg['minimum_attempts'] < 2):
        raise ValueError('minimum_attempts must be an integer >= 2')
    for key, minimum in (('selection_min_measurements', 2), ('selection_sealed_budget', 1), ('selection_submissions', 1)):
        if key in cfg and (type(cfg[key]) is not int or cfg[key] < minimum):
            raise ValueError('{} must be an integer >= {}'.format(key, minimum))
    for rule in cfg.get('banned_patterns', []):
        # TOML scopes every key after a [[banned_patterns]] header INTO that table, so a lane key
        extra = sorted(k for k in rule if k not in ('pattern', 'reason'))
        if extra:
            raise ValueError('{} landed inside a [[banned_patterns]] table (TOML scopes keys to the table '
                             'above them): move it above the first [[banned_patterns]]'.format(', '.join(extra)))
        if not rule.get('pattern') or not rule.get('reason', '').strip():
            raise ValueError('banned_patterns require non-empty pattern and reason')
        re.compile(rule['pattern'], re.I)


def ingest(lane, hits, cfg, dry_run=False, session='intake'):
    history = rows(lane / 'IDEAS.jsonl')
    urls = {r.get('source_url') for r in history if r.get('source_url')}
    hashes = {r.get('title_hash') or title_hash(r.get('title', r.get('claim', ''))) for r in history}
    count = 0
    for hit in hits:
        title = hit.get('title', hit.get('claim', '')).strip()
        url = hit.get('source_url', hit.get('url', '')).strip()
        if not title or not url:
            raise ValueError('intake hit requires title and source_url')
        digest = title_hash(title)
        if url in urls or digest in hashes:
            continue
        row = new_idea(hit.get('source_type', 'paper'), url, title, session,
                       title=title, title_hash=digest,
                       question_it_answers=hit.get('question_it_answers', ''),
                       source_published=hit.get('published', ''))
        searchable = title + '\n' + url + '\n' + hit.get('summary', '')
        reasons = [rule['reason'] for rule in cfg.get('banned_patterns', [])
                   if re.search(rule['pattern'], searchable, re.I)]
        if reasons:
            row.update(status='closed', closed_reason='; '.join(reasons),
                       data_tags=['BANNED:' + reason for reason in reasons],
                       no_test_reason='metadata excluded by lane rule: ' + '; '.join(reasons))
            if cfg.get('verification_required', False):
                row.update(verification='L0', finite_component='none', verification_policy_version=1,
                           verification_required_at_close=True)
        print(('WOULD ADD ' if dry_run else 'ADDED ') + json.dumps(row, ensure_ascii=False))
        if not dry_run:
            append(lane / 'IDEAS.jsonl', row)
        urls.add(url)
        hashes.add(digest)
        count += 1
    return count


def get_url(url):
    # This is the only network boundary, reached only by intake --live.
    request = urllib.request.Request(url, headers={'User-Agent': 'research-harness/1.0 (metadata intake)'})
    # Apple's Python 3.9 redirect handler predates HTTP 308 support.
    # Keep urllib's normal redirect limits and URL-scheme validation.
    class Redirects(urllib.request.HTTPRedirectHandler):
        def http_error_308(self, request, response, code, message, headers):
            return self.http_error_302(request, response, 307, message, headers)

    opener = urllib.request.build_opener(Redirects())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                return response.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise
            retry = error.headers.get('Retry-After', '')
            try:
                delay = int(retry)
            except ValueError:
                try:
                    until = email.utils.parsedate_to_datetime(retry)
                    delay = int((until - dt.datetime.now(dt.timezone.utc)).total_seconds()) + 1
                except (ValueError, TypeError, OverflowError):
                    delay = 5 * (attempt + 1)
            # Do not ignore a server's longer cooling-off request by retrying early.
            if delay > 60:
                raise
            error.close()
            time.sleep(max(3, delay))


def feed_hits(payload, source_type='paper'):
    root = ET.fromstring(payload)
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    if root.tag.endswith('feed'):
        for entry in root.findall('a:entry', ns):
            title = entry.findtext('a:title', '', ns)
            url = entry.findtext('a:id', '', ns)
            for link in entry.findall('a:link', ns):
                if link.get('rel', 'alternate') == 'alternate':
                    url = link.get('href', url)
                    break
            yield dict(title=title, source_url=url, source_type=source_type,
                       summary=entry.findtext('a:summary', '', ns),
                       published=entry.findtext('a:published', '', ns))
    else:
        for entry in root.findall('.//item'):
            yield dict(title=entry.findtext('title', ''), source_url=entry.findtext('link', ''),
                       source_type=source_type, summary=entry.findtext('description', ''))


ARXIV_FIELDS = ('all:', 'ti:', 'abs:', 'au:', 'cat:', 'co:', 'jr:', 'rn:', 'id:')


def arxiv_search_query(query):
    """Field-qualify a bare phrase.

    Unfielded queries can produce off-topic hits. A query that already names a field is
    passed through untouched; a bare phrase becomes an AND of all:"term" clauses, the same
    shape the keywords fallback uses.
    """
    low = query.lower()
    if any(f in low for f in ARXIV_FIELDS):
        return query
    terms = [t for t in re.split(r'\s+', query.replace('"', '').strip()) if t and t.upper() not in ('AND', 'OR', 'NOT')]
    if not terms:
        return query
    return ' AND '.join('all:"{}"'.format(t) for t in terms)


def fetch_sources(cfg):
    """Each yielded item is (source, hits, error). Zero-hit reads still count."""
    queries = [arxiv_search_query(q) for q in cfg.get('arxiv_queries', [])]
    if not queries and cfg.get('keywords'):
        queries = [' OR '.join('all:"{}"'.format(k.replace('"', '')) for k in cfg['keywords'])]
    for query_index, query in enumerate(queries):
        if query_index:
            time.sleep(3)  # arXiv asks clients to space API requests by at least 3 s.
        start = (dt.date.today() - dt.timedelta(days=548)).strftime('%Y%m%d')
        query += ' AND submittedDate:[{}0000 TO 999912312359]'.format(start)
        url = 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode(
            dict(search_query=query, start=0, max_results=cfg.get('max_results', 50), sortBy='submittedDate', sortOrder='descending'))
        try:
            yield 'arxiv', list(feed_hits(get_url(url))), ''
        except Exception as e:
            yield 'arxiv', [], str(e)
    terms = cfg.get('biorxiv_queries', []) or cfg.get('keywords', [])
    if terms:
        start = dt.date.today() - dt.timedelta(days=548)
        cursor, backwards = 0, False
        for page in range(cfg.get('biorxiv_pages', 3)):
            url = 'https://api.biorxiv.org/details/biorxiv/{}/{}/{}'.format(start, dt.date.today(), cursor)
            try:
                data = json.loads(get_url(url))
                messages = data.get('messages', [])
                if messages and messages[0].get('status') != 'ok':
                    raise ValueError('bioRxiv API: ' + str(messages[0]))
                entries = data['collection']
                hits = [dict(title=e['title'], source_url='https://www.biorxiv.org/content/10.1101/' + e['doi'].removeprefix('10.1101/'),
                             source_type='paper', summary=e.get('abstract', ''), published=e.get('date', ''))
                        for e in entries if any(t.casefold() in (e['title'] + ' ' + e.get('abstract', '')).casefold() for t in terms)]
                yield 'biorxiv', hits, ''
                total = int(messages[0].get('total', 0)) if messages else 0
                if page == 0 and total > 100:
                    # Probe establishes total; spend remaining budget on newest pages,
                    # rather than repeatedly reading only the oldest part of the window.
                    cursor = ((total - 1) // 100) * 100
                    backwards = True
                elif backwards:
                    cursor -= 100
                    if cursor <= 0:
                        break  # Cursor zero was already read by the probe.
                elif len(entries) < 100:
                    break
                else:
                    cursor += 100
            except Exception as e:
                yield 'biorxiv', [], str(e)
                break
    for url in cfg.get('community_urls', []):
        try:
            payload = get_url(url)
            try:
                hits = list(feed_hits(payload, 'community'))
            except ET.ParseError:
                match = re.search(r'<title[^>]*>(.*?)</title>', payload.decode('utf-8', 'replace'), re.I | re.S)
                if not match:
                    raise ValueError('community URL needs RSS/Atom or HTML title')
                hits = [dict(title=html.unescape(match[1]).strip(), source_url=url, source_type='community')]
            yield 'community:' + url, hits, ''
        except Exception as e:
            yield 'community:' + url, [], str(e)
    # Open pull requests can update the live record before a commit feed shows them.
    include = cfg.get('github_pr_include', '')
    for repo in cfg.get('github_pr_repos', []):
        url = 'https://api.github.com/repos/{}/pulls?state=open&sort=created&direction=desc&per_page=100'.format(repo)
        try:
            hits = [dict(title=p['title'], source_url=p['html_url'], source_type='community',
                         summary=(p.get('body') or '')[:2000], published=p.get('created_at', ''))
                    for p in json.loads(get_url(url))
                    if not include or re.search(include, p['title'] + '\n' + (p.get('body') or ''), re.I)]
            yield 'github-prs:' + repo, hits, ''
        except Exception as e:
            yield 'github-prs:' + repo, [], str(e)


def intake(lane, args):
    cfg = config(lane / 'INTAKE.toml')
    validate_config(cfg)
    dry = not args.live
    with locked(lane):
        added, reads, errors = 0, [], []
        if args.hits_file:
            added += ingest(lane, rows(Path(args.hits_file)), cfg, dry)
            # Fixtures never certify an external read.
        local = cfg.get('x_local_file', '')
        if local:
            path = Path(local).expanduser()
            if not path.is_absolute():
                path = lane / path
            if path.exists():
                xhits = rows(path)
                for h in xhits:
                    h['source_type'] = 'x'
                added += ingest(lane, xhits, cfg, dry)
                # Re-reading stale local captures must not renew external freshness.
                if not dry and xhits and recent(dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()):
                    reads.append('x-local')
        if dry:
            print('DRY RUN: network disabled; configured arXiv/bioRxiv/community fetchers would run with --live')
        else:
            for source, hits, error in fetch_sources(cfg):
                if error:
                    errors.append(source + ': ' + error)
                else:
                    reads.append(source)
                    added += ingest(lane, hits, cfg)
            append(lane / 'INTAKE_RUNS.jsonl', dict(created=now(), sources_read=reads, errors=errors, added=added))
        print('{}: {} ideas; {} external reads{}'.format(lane.name, added, len(reads), ' (dry-run)' if dry else ''))
        for error in errors:
            print('intake error: ' + error, file=sys.stderr)
        return 1 if errors else 0


def intake_x_search(lane, args):
    """Append a browser search outcome without inventing a URL or idea."""
    cfg = config(lane / 'INTAKE.toml')
    validate_config(cfg)
    capture = cfg.get('x_local_file', '')
    if not isinstance(capture, str) or not capture.strip() or any(c in capture for c in '\r\n\0'):
        raise ValueError('intake x-search requires a configured x_local_file')
    row = dict(utc=now(), query=args.query, result=args.result, n_hits=args.n,
               captured_by=os.environ.get('RH_CAPTURED_BY') or os.environ.get('USER') or 'general-session')
    if args.subject is not None:
        row['subject'] = args.subject
    x_searches.validate(row)
    with locked(lane):
        path = lane / 'X_SEARCHES.jsonl'
        x_searches.recent(path)  # Do not append to a malformed journal.
        append(path, row)
    print('RECORDED X SEARCH ' + json.dumps(row, ensure_ascii=False))
    return 0


def session_model():
    """The current model of the Claude Code session calling us, or None outside one.

    Read from its transcript, not its settings, so a /model change counts."""
    session = os.environ.get('CLAUDE_CODE_SESSION_ID')
    if not session:
        return None
    transcripts = os.environ.get('RH_TRANSCRIPTS_ROOT')
    if not transcripts or not re.fullmatch(r'[A-Za-z0-9-]+', session):
        return None
    for path in Path(transcripts).expanduser().glob('*/{}.jsonl'.format(session)):
        with path.open('rb') as handle:
            handle.seek(max(0, path.stat().st_size - 4000000))
            lines = handle.read().decode('utf-8', 'ignore').splitlines()
        for line in reversed(lines):
            if '"assistant"' not in line:
                continue
            try:
                model = json.loads(line).get('message', {}).get('model', '')
            except ValueError:
                continue
            if model.startswith('claude-'):
                return model.split('[')[0]
    return None


def banned_cs_sessions(project_url):
    """Root sessions in this project that ran on a banned model, read from the daemon's own database.

    A session started in the browser never passes through cs.py, so its refusal alone can't hold the rule."""
    project = project_url.rstrip('/').rsplit('/', 1)[-1]
    if not project:
        return []
    marks = ','.join('?' for _ in CS_BANNED_MODELS)
    found = []
    db_root = os.environ.get('RH_CS_DB_ROOT')
    if not db_root:
        return []
    for db in Path(db_root).expanduser().glob('orgs/*/operon-cli.db'):
        con = sqlite3.connect('file:{}?mode=ro'.format(db), uri=True, timeout=5)
        try:
            found += [r[0] for r in con.execute(
                'select id from frames where parent_frame_id is null and project_id = ? and created_at >= ? '
                'and model in ({})'.format(marks), [project, CS_MODEL_RULE_MS] + sorted(CS_BANNED_MODELS))]
        finally:
            con.close()
    return found


def lane_config(lane):
    path = lane / 'INTAKE.toml'
    if not path.is_file():
        return {}
    cfg = config(path)
    validate_config(cfg)
    return cfg


class LintErrors(list):
    """Human diagnostics stay local; only static check names leave the machine."""
    def __init__(self):
        super().__init__()
        self.failures = []

    def add(self, check, message, fingerprint=None):
        self.append(message)
        failure = dict(check=check, message=message)
        if fingerprint is not None:
            failure['fingerprint'] = fingerprint
        self.failures.append(failure)

    def add_many(self, check, messages):
        for message in messages:
            name, fingerprint = check, None
            if check == 'sweep-obligations':
                if message.startswith('sweep-hung'):
                    name = 'sweep-hung'
                elif 'unread after 3 days' in message:
                    name = 'unread-deadline'
                elif 'testing without a result' in message:
                    name = 'testing-deadline'
                elif message.startswith('entire idea set is grandfathered'):
                    name = 'grandfather-expired'
                elif message == 'no successful sweep report in 26 hours':
                    name = 'sweep-freshness'
            elif check == 'lane-cadence':
                name = ('cadence-config-invalid' if 'broken' in message else
                        'cadence-unconfigured' if 'missing' in message else 'cadence-stalled')
            elif check == 'pod-health' and message.startswith('underused pod '):
                # Percentages fluctuate every poll; the failed check is still this pod.
                name, fingerprint = 'pod-utilization', message.split(':', 1)[0]
            self.add(name, message, fingerprint)



def outreach_only(lane):
    """11-03: a lane may hold only an OUTREACH ledger (X post history). It is not a research
    lane, so the queue, intake and sweep checks don't apply; only outreach health does."""
    return (lane / 'OUTREACH.jsonl').is_file() and not any(
        (lane / f).exists() for f in ('IDEAS.jsonl', 'INTAKE.toml', 'SWEEP.toml', 'INTAKE_RUNS.jsonl'))


def lint_result(lane, report=None):
    if outreach_only(lane):
        errs = outreach.health(lane, sys.modules[__name__])
        return dict(lane=lane.name, status='FAIL' if errs else 'OK', depth=None, failure_count=len(errs),
                    failures=[dict(check='outreach', message=m) for m in errs], warnings=[], grandfathered=[],
                    outreach=dict(status='FAIL' if errs else 'OK', count=len(outreach.current(lane, sys.modules[__name__]))))
    history = rows(lane / 'IDEAS.jsonl')
    cfg = lane_config(lane)
    runs = rows(lane / 'INTAKE_RUNS.jsonl')
    errors, n = LintErrors(), depth(history)
    errors.add_many('lane-declarations', lane_setup.audit(lane, sys.modules[__name__]))
    setup = lane_setup.in_setup(lane, sys.modules[__name__])
    if n < 3 and not setup:
        errors.add('queue-depth', 'queue depth(new|testing)={} < 3'.format(n))
    recent_runs = [r for r in runs if recent(r.get('created', ''))]
    external = any(r.get('source_type') in EXTERNAL and recent(r.get('created', '')) for r in history)
    read = any(r.get('sources_read') for r in recent_runs)
    if not setup and not external and not read:
        errors.add('external-reading', 'no external source added or successfully read in last 24 h')
    if not recent_runs and not setup:
        errors.add('intake-freshness', 'no intake run recorded in last 24 h')
    elif not read and not setup:
        errors.add('intake-reading', 'intake read no external sources in last 24 h')
    if cfg.get('depth_tags'):
        current = latest(history)
        need = cfg.get('depth_per_tag', 3)
        for tag in cfg['depth_tags']:
            statuses = tuple(cfg.get('depth_tag_status', ['new', 'testing']))
            k = sum(1 for r in current.values() if r.get('status') in statuses and tag in r.get('data_tags', []))
            if k < need:
                errors.add('tag-depth', 'depth for {} = {} < {} targets in {}'.format(tag, k, need, '|'.join(statuses)))
    if cfg.get('claude_science_required'):
        days = cfg.get('claude_science_max_age_days', 2)
        if not any(r.get('source_type') == 'claude-science' and recent(r.get('created', ''), 24 * days) for r in history):
            errors.add('claude-science-freshness', 'no claude-science idea added in last {} day(s) (claude_science_required)'.format(days))
    banned = banned_cs_sessions(cfg.get('claude_science_project', ''))
    if banned:
        errors.add('claude-science-model', '{} Claude Science session(s) ran on a banned model ({}): restart on {}'.format(
            len(banned), ', '.join(sorted(CS_BANNED_MODELS)), cfg.get('claude_science_model', CS_DEFAULT_MODEL)))
    if report:
        text = Path(report).read_text()
        for pattern in STOP_PATTERNS:
            if n > 0 and re.search(pattern, text, re.I):
                errors.add('report-stop-pattern', 'report {} matches stop-pattern {!r} while depth={}'.format(report, pattern, n))
    for i, row in enumerate(history, 1):
        if row.get('status') == 'testing' or row.get('event') == 'promote' or row.get('status') == 'shipped':
            error = promotion_error(row)
            if error:
                errors.add('idea-promotion-or-taste', 'IDEAS.jsonl row {} id={}: {}'.format(i, row.get('id'), error))
        if row.get('event') == 'promote' and row.get('revised', '') >= TASTE_RULE_FROM \
                and not (row.get('prior_art') and Path(row['prior_art']).is_file()):
            errors.add('prior-art', 'IDEAS.jsonl row {} id={}: promoted without a prior-art file'.format(i, row.get('id')))
        if row.get('event') in ('promote', 'close') and row.get('revised', '') >= TASTE_RULE_FROM \
                and not (row.get('event') == 'close' and row.get('mechanical')):
            error = taste_error(row.get('decided_by', ''))
            if error:
                errors.add('idea-promotion-or-taste', 'IDEAS.jsonl row {} id={}: {}'.format(i, row.get('id'), error))
        if row.get('status') == 'closed' and not (row.get('closed_reason', '').strip() or (row.get('result_path') and Path(row['result_path']).is_file())):
            errors.add('closed-evidence', 'IDEAS.jsonl row {}: closed requires existing result_path or closed_reason'.format(i))
        if row.get('source_type') in EXTERNAL and not row.get('source_url', '').strip():
            errors.add('source-url', 'IDEAS.jsonl row {}: external source requires source_url'.format(i))
    for i, row in enumerate(history, 1):
        if row.get('event') in ('result', 'close') or row.get('status') == 'closed':
            required = cfg.get('verification_required', False) and verification.new_close(row)
            for error in verification.validate_row(row, lane, required=required):
                errors.add('verification', 'IDEAS.jsonl row {} id={}: {}'.format(i, row.get('id'), error))
    policy_errors, policy_warnings = idea_policy.audit(history, lane, cfg.get('minimum_attempts', 2), selection_config=cfg)
    errors.add_many('idea-policy', policy_errors)
    sweep_errors, grandfathered = sweep.lint(lane, sys.modules[__name__])
    errors.add_many('sweep-obligations', sweep_errors)
    if not setup:
        errors.add_many('lane-cadence', cadence.lint(lane, sys.modules[__name__]))
    info = []
    pod_warnings = []
    errors.add_many('pod-health', pods.lint(lane, sys.modules[__name__], info=info, warnings=pod_warnings))
    outreach_errors = outreach.health(lane, sys.modules[__name__])
    errors.add_many('outreach', outreach_errors)
    return dict(lane=lane.name, status='FAIL' if errors else 'OK', depth=n, setup=setup,
                failure_count=len(errors), failures=errors.failures,
                warnings=policy_warnings + lessons.warnings(lane, sys.modules[__name__]) + pod_warnings,
                grandfathered=grandfathered, info=info,
                outreach=dict(status='FAIL' if outreach_errors else 'OK', count=len(outreach.current(lane, sys.modules[__name__]))))


def checked_lint(lane, report=None):
    # A broken lane must neither stop --all nor leak parser/file contents to pushes.
    try:
        return lint_result(lane, report)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, SyntaxError, sqlite3.Error):
        return dict(lane=lane.name, status='FAIL', depth=None, failure_count=1,
                    failures=[dict(check='lint-input-invalid', message='lint input unreadable or invalid')],
                    warnings=[], grandfathered=[])


def print_lint(result):
    lane = result['lane']
    for message in result.get('info', []):
        print('INFO {}: {}'.format(lane, message))
    if 'outreach' in result:
        print('{} {}: outreach ({} messages)'.format(result['outreach']['status'], lane, result['outreach']['count']))
    for warning in result['warnings']:
        print('WARN {}: {}'.format(lane, warning))
    if result['grandfathered']:
        print('GRANDFATHERED {}: {}'.format(lane, ','.join(result['grandfathered'])))
    for failure in result['failures']:
        print('FAIL {}: {}'.format(lane, failure['message']))
    if not result['failures']:
        if result['depth'] is None:
            print('OK {}: outreach-only lane'.format(lane))
        elif result.get('setup'):
            print('OK {}: setup grace (24h maximum); frozen declarations valid; no reading or results claimed'.format(lane))
        else:
            print('OK {}: depth={}; external reading and intake fresh'.format(lane, result['depth']))


def lint(lane, report=None):
    result = checked_lint(lane, report)
    print_lint(result)
    return int(bool(result['failure_count']))


def lint_all(root, report=None):
    return [checked_lint(lane, report) for lane in cadence.lanes(root)]


def lint_monitor(root):
    # No lane locks: only alert state is locked, never research/queue files.
    return lane_alerts.monitor(root, 'lint', lint_all(root))


def answers_sync(lane, path):
    if not path.is_file():
        return 0
    cfg = config(lane / 'INTAKE.toml')
    validate_config(cfg)
    tags = set(cfg.get('answers_tags', [lane.name]))
    hits = []
    pattern = r'^- (\d{4}-\d{2}-\d{2})\s*\|\s*(https?://\S+)\s*\|\s*([^\n|]+)\|\s*([^\n]+)\n(.*?)(?=^- \d{4}-\d{2}-\d{2}\s*\||\Z)'
    for match in re.finditer(pattern, path.read_text(), re.M | re.S):
        date, url, author, tag, body = match.groups()
        if tag.strip() not in tags:
            continue
        claim = re.split(r'\n\s*For us:', body.strip(), maxsplit=1)[0].strip()
        claim = re.sub(r'^Answer[^:]*:\s*', '', claim)
        hits.append(dict(title=claim, source_url=url, source_type='answers', summary=body))
    if hits:
        with locked(lane):
            ingest(lane, hits, cfg, session='answers-sync')
    return 0


def prior_art_hint(row):
    return shlex.join(['rh', 'prior-art', 'receipt', row['id'], row['prior_art'],
                       '--baseline', 'BEST_PUBLIC_METHOD_AND_NUMBER',
                       '--query', row.get('claim') or row['id']])


def show_idea(root, key):
    """Read-only lookup by unique ID/prefix across eligible lanes."""
    if not key.strip():
        raise ValueError('idea id must be nonempty')
    matches = []
    for lane in sorted((root.expanduser() / 'lanes').iterdir()):
        if lane.is_dir() and idea_policy.enabled(lane):
            for row in latest(rows(lane / 'IDEAS.jsonl')).values():
                if row.get('id', '').startswith(key):
                    matches.append(dict(row, lane=lane.name))
    if len(matches) != 1:
        raise ValueError('idea id must match exactly one idea: {} ({} matches)'.format(key, len(matches)))
    print(json.dumps(matches[0], ensure_ascii=False))
    return 0


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=settings.path('RH_ROOT', ROOT),
                   help='isolated harness root (default: installed root); X outreach quotas span all lanes in this root')
    sub = p.add_subparsers(dest='command', required=True)
    lane_setup.arguments(sub)
    lessons.arguments(sub)
    retro.arguments(sub)
    pods.arguments(sub)
    cadence.arguments(sub)
    outreach.arguments(sub)
    bughunt.arguments(sub)
    publish_lint.arguments(sub)
    receipt = sub.add_parser('prior-art', help='shared prior-art searches and receipt').add_subparsers(dest='action', required=True)
    a = receipt.add_parser('receipt')
    a.add_argument('key', metavar='KEY')
    a.add_argument('md', metavar='PRIOR_ART_MD')
    a.add_argument('--baseline', required=True)
    a.add_argument('--query', required=True)
    a.add_argument('--paper-query')
    selection = sub.add_parser('selection', help='v2 trial accounting and sealed selection').add_subparsers(dest='action', required=True)
    for action in ('trial', 'score'):
        a = selection.add_parser(action)
        a.add_argument('lane')
        a.add_argument('id')
        if action == 'trial':
            a.add_argument('--trial-id', required=True)
            a.add_argument('--name', required=True)
            a.add_argument('--status', required=True, choices=('completed', 'pruned'))
            a.add_argument('--tuned-score', type=float)
        else:
            a.add_argument('--evidence', type=Path, required=True)
            a.add_argument('--output', type=Path, required=True)
    ideas = sub.add_parser('ideas', aliases=['idea']).add_subparsers(dest='action', required=True)
    a = ideas.add_parser('show', help='show one idea by unique ID/prefix across lanes (JSON)')
    a.add_argument('id')
    for action in ('add', 'list', 'close', 'promote', 'depth', 'read', 'result', 'freeze', 'reopen'):
        a = ideas.add_parser(action)
        a.add_argument('lane')
        if action == 'depth':
            a.add_argument('--quiet', action='store_true', help='print only the integer; no breakdown on stderr')
        if action == 'add':
            a.add_argument('--source-type', required=True, choices=SOURCES)
            a.add_argument('--source-url', default='')
            a.add_argument('--claim', required=True)
            a.add_argument('--session', default=os.environ.get('RH_SESSION', 'manual'))
            for field in ('question-it-answers', 'board', 'test', 'bar', 'route'):
                a.add_argument('--' + field, default='')
            a.add_argument('--data-tag', action='append', default=[])
            # 11-03 general: native model id that proposed the idea, so ideation can score proposers
            # (model-leaderboard adapter reads proposed_by). Lane throughput isn't judgement: a kill at
            # the idea's own kill line must not count against its proposer.
            a.add_argument('--proposed-by', default=os.environ.get('RH_PROPOSED_BY', ''),
                           help='native model id that proposed this idea (env RH_PROPOSED_BY)')
        if action in ('close', 'promote', 'read', 'result', 'freeze', 'reopen'):
            a.add_argument('id')
        if action == 'read':
            a.add_argument('--report', type=Path, required=True)
        if action == 'result':
            a.add_argument('--result-path', type=Path, required=True)
        if action in ('result', 'close'):
            a.add_argument('--verification', choices=verification.LEVELS)
            a.add_argument('--finite-component', choices=verification.LEVELS + ('none',))
            a.add_argument('--verification-evidence', type=Path, help='verification metadata JSON; evidence paths relative to the lane')
            a.add_argument('--config-path', type=Path, help='nonempty JSON configuration used for this attempt')
        if action == 'close':
            lesson = a.add_mutually_exclusive_group()
            lesson.add_argument('--lesson', help='one evidence-backed claim, at most two sentences')
            lesson.add_argument('--no-lesson', metavar='REASON', help='why this close has no transferable lesson')
            a.add_argument('--lesson-tags', nargs='+', default=[])
            a.add_argument('--attempts', type=int, help='number of recorded attempts; needs >= lane minimum distinct configs')
            a.add_argument('--no-test-reason', default='', help='explicit reason for a close without a test (e.g. source/rule exclusion)')
            a.add_argument('--result-path', default='')
            a.add_argument('--closed-reason', default='')
            # 11-03 general: structured close kind so ideation scoring needn't match prose (model-leaderboard).
            a.add_argument('--close-kind', default='', choices=['', 'bar-failed', 'prior-art', 'duplicate',
                           'rule-blocked', 'infeasible', 'superseded', 'other'],
                           help='why it closed: bar-failed (killed at its own bar), prior-art/duplicate (already known), '
                                'rule-blocked, infeasible, superseded, other')
            a.add_argument('--mechanical', action='store_true', help='closed because the frozen bar failed '
                           '(needs --result-path); no taste call, so any model may record it')
        if action in ('close', 'promote', 'freeze'):
            a.add_argument('--decided-by', default='', help='model that made the call (env RH_DECIDED_BY, else this Claude session)')
        if action in ('promote', 'freeze'):
            a.add_argument('--policy-version', type=int, choices=(1, 2), default=1)
            a.add_argument('--selection-policy', type=Path, help='v2 freeze declaration JSON')
            holdout = a.add_mutually_exclusive_group()
            holdout.add_argument('--sealed-holdout', action='store_true', help='targets are sealed from the producing worker; lane gate still enforces access')
            holdout.add_argument('--no-holdout-reason', default='', help='why this experiment has no statistical holdout, e.g. exact certificate')
            for field in ('board', 'test', 'bar', 'route'):
                a.add_argument('--' + field)
            a.add_argument('--prior-art', help='file naming the best public method and its number (prior-art-first, '
                           'prior-art policy); required to promote')
            a.add_argument('--review-url', help='Claude Science review of this idea; required when the lane sets claude_science_required')
            a.add_argument('--independent-check', help='what we re-verified ourselves on a better model or from primary sources; '
                           'required to promote a claude-science idea')
        if action == 'list':
            a.add_argument('--status', choices=sorted(STATUSES))
    a = sub.add_parser('sweep', help='outside search, read, kill tests and compiler; launches workers unless --dry-run')
    a.add_argument('lane', nargs='?')
    a.add_argument('--all', action='store_true', help='independent staggered sweeps of all enabled lanes')
    a.add_argument('--dry-run', action='store_true', help='read-only plan and generated specs, no workers or network')
    a = sub.add_parser('lint')
    a.add_argument('lane', nargs='?')
    a.add_argument('--all', action='store_true', help='check every lane, including disabled workers')
    a.add_argument('--json', action='store_true', help='machine-readable results')
    a.add_argument('--report', type=Path)
    a = sub.add_parser('intake', description='Fetch intake with LANE --live, or record a browser outcome with x-search LANE --query Q [--subject S] --result none|hits --n N.')
    a.add_argument('lane')
    # Preserve `intake LANE --live` while adding `intake x-search LANE ...`.
    a.add_argument('x_search_lane', nargs='?', help='lane for the x-search action')
    a.add_argument('--query', help='actual X browser query (x-search only)')
    a.add_argument('--subject', help='optional author or topic scope (x-search only)')
    a.add_argument('--result', choices=('none', 'hits'), help='recorded outcome (x-search only)')
    a.add_argument('--n', type=int, help='hit count: 0 for none, positive for hits (x-search only)')
    group = a.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true', help='default; no network and no writes')
    group.add_argument('--live', action='store_true', help='fetch metadata and append ideas/intake audit')
    a.add_argument('--hits-file', help='local JSONL fixture; never counts as an external read')
    a = sub.add_parser('cs-url', help="print a fresh Claude Science login link and the lane's project URL")
    a.add_argument('lane')
    a = sub.add_parser('voice-cuts', help='check a draft is cut from the author\'s own messages (DRAFT.cuts)',
                       add_help=False)
    a.add_argument('rest', nargs=argparse.REMAINDER)
    a = sub.add_parser('answers-sync')
    a.add_argument('lane')
    a.add_argument('--answers-file', type=Path, default=settings.path('RH_ANSWERS_FILE', Path('.runtime/ANSWERS.md')))
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == 'idea':
        args.command = 'ideas'
    try:
        if args.command == 'voice-cuts':
            import voice_cuts
            return voice_cuts.main(args.rest)
        if args.command == 'lessons':
            return lessons.main(args.root, args, sys.modules[__name__])
        if args.command == 'retro':
            return retro.main(args.root, args, sys.modules[__name__])
        if args.command == 'intake':
            if args.lane == 'x-search':
                if not args.x_search_lane or args.query is None or args.result is None or args.n is None:
                    raise ValueError('intake x-search requires LANE --query Q [--subject S] --result none|hits --n N')
                if args.live or args.dry_run or args.hits_file:
                    raise ValueError('intake x-search records a local outcome; do not combine with intake fetch flags')
                args.lane, args.intake_action = args.x_search_lane, 'x-search'
            elif args.x_search_lane or any(value is not None for value in (args.query, args.subject, args.result, args.n)):
                raise ValueError('X search flags require intake x-search LANE')
        if args.command == 'publish-lint':
            return publish_lint.main(args)
        if args.command == 'lane':
            return lane_setup.main(args.root, args, sys.modules[__name__])
        if args.command == 'outreach':
            return outreach.main(args.root, args, sys.modules[__name__])
        if args.command == 'bughunt':
            return bughunt.main(args.root, args, sys.modules[__name__])
        if args.command == 'prior-art':
            command = [sys.executable, str(ROOT / 'tools' / 'prior_art_receipt.py'),
                       args.key, args.md, '--baseline', args.baseline, '--query', args.query]
            if args.paper_query is not None:
                command += ['--paper-query', args.paper_query]
            return subprocess.run(command).returncode
        if args.command == 'ideas' and args.action == 'show':
            return show_idea(args.root, args.id)
        if args.command == 'lanes':
            return cadence.main(args.root, args, sys.modules[__name__])
        if args.command == 'pods':
            return pods.main(args.root, args, sys.modules[__name__])
        if args.command == 'sweep':
            if args.all == bool(args.lane):
                raise ValueError('sweep requires either LANE or --all')
            if args.lane and not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.lane):
                raise ValueError('invalid lane name')
            if args.lane and not (args.root.expanduser() / 'lanes' / args.lane).is_dir():
                raise ValueError('lane directory missing: ' + args.lane)
            return sweep.main(args.root, args, sys.modules[__name__])
        if args.command == 'lint':
            if args.all == bool(args.lane):
                raise ValueError('lint requires either LANE or --all')
            selected = cadence.lanes(args.root, args.lane)
            results = [checked_lint(lane, args.report) for lane in selected]
            if args.json:
                print(json.dumps(results, indent=2, sort_keys=True))
            else:
                for result in results:
                    print_lint(result)
            return int(any(result['failure_count'] for result in results))
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.lane):
            raise ValueError('invalid lane name')
        lane = args.root.expanduser() / 'lanes' / args.lane
        if not lane.is_dir():
            raise ValueError('lane directory missing: ' + str(lane))
        if args.command == 'intake':
            if getattr(args, 'intake_action', '') == 'x-search':
                return intake_x_search(lane, args)
            return intake(lane, args)
        if args.command == 'cs-url':
            # The login link is single-use and expires in ~3 min, so it is minted on demand, never stored.
            binary = os.environ.get('CS_BIN', 'claude-science')
            link = os.popen(str(binary) + ' url 2>&1').read().strip() if binary.exists() else 'claude-science not installed'
            print(link)
            project = lane_config(lane).get('claude_science_project', '')
            print(project or 'no claude_science_project set in INTAKE.toml')
            return 0
        if args.command == 'answers-sync':
            return answers_sync(lane, args.answers_file.expanduser())
        if args.command == 'selection':
            with locked(lane):
                history = rows(lane/'IDEAS.jsonl')
                current = latest(history)
                if args.id not in current:
                    raise ValueError('unknown idea id: ' + args.id)
                row = dict(current[args.id])
                if args.action == 'trial':
                    trial = dict(id=args.trial_id, name=args.name, status=args.status)
                    if args.tuned_score is not None:
                        trial['tuned_score'] = args.tuned_score
                    selection_policy.add_trial(row, trial)
                else:
                    decision = selection_policy.score(row, lane, args.evidence, args.output, lane_config(lane))
                    print(json.dumps(decision, sort_keys=True))
                row.update(revised=now(), event='selection-' + args.action)
                append(lane/'IDEAS.jsonl', row)
            return 0
        if args.action == 'read':
            sweep.mark_read(lane, args.id, args.report, sys.modules[__name__])
            print(args.id + ' read')
            return 0
        with locked(lane):
            history = rows(lane / 'IDEAS.jsonl')
            current = latest(history)
            if args.action == 'depth':
                # Print active depth first; report closed/history counts separately.
                by_status = collections.Counter(r['status'] for r in current.values())
                print(depth(history))
                if not args.quiet:
                    print('open(new|testing)={} closed={} shipped={} total_ids={}'.format(
                        depth(history), by_status['closed'], by_status['shipped'], len(current)),
                        file=sys.stderr)
            elif args.action == 'list':
                for row in current.values():
                    if not args.status or row['status'] == args.status:
                        print(json.dumps(row, ensure_ascii=False))
            elif args.action == 'add':
                row = new_idea(args.source_type, args.source_url, args.claim, args.session,
                               question_it_answers=args.question_it_answers, board=args.board,
                               test=args.test, bar=args.bar, route=args.route, data_tags=args.data_tag,
                               proposed_by=args.proposed_by.strip())
                append(lane / 'IDEAS.jsonl', row)
                print(row['id'])
            else:
                if args.id not in current:
                    raise ValueError('unknown idea id: ' + args.id)
                row = dict(current[args.id])
                if args.action in ('result', 'close'):
                    verification.apply_metadata(row, args, lane, required=(args.action == 'close' and lane_config(lane).get('verification_required', False)))
                if args.action == 'reopen':
                    if row['status'] != 'closed':
                        raise ValueError('reopen requires status=closed')
                    if not idea_policy.enabled(lane):
                        raise ValueError('reopen is unavailable for excluded lanes')
                    # A new lifecycle needs fresh evidence. Copy only source/routing
                    # metadata, never old result, prior-art, freeze or attempt receipts.
                    fields = {k: row[k] for k in ('question_it_answers', 'board', 'test', 'bar',
                              'route', 'data_tags', 'review_url', 'independent_check', 'proposed_by') if k in row}
                    row = new_idea(row['source_type'], row.get('source_url', ''), row['claim'],
                                   session='reopen', reopens=args.id, **fields)
                elif args.action == 'result':
                    result = args.result_path.expanduser().resolve()
                    if row['status'] != 'testing' or not result.is_file() or not result.read_text().strip():
                        raise ValueError('result requires status=testing and a nonempty existing result file')
                    if idea_policy.enabled(lane) or row.get('policy_version') == 2:
                        idea_policy.record_result(row, result, args.config_path)
                    else:
                        row.update(result_path=str(result))
                elif args.action in ('promote', 'freeze'):
                    if args.action == 'promote' and row['status'] != 'new':
                        raise ValueError('promote requires status=new')
                    if args.action == 'freeze' and (row['status'] != 'testing' or any(r.get('result_path') or r.get('frozen_bar') for r in history if r['id'] == args.id)):
                        raise ValueError('freeze requires testing, with no prior result or freeze; use a new idea for a new protocol')
                    for key in ('board', 'test', 'bar', 'route'):
                        if getattr(args, key) is not None:
                            row[key] = getattr(args, key).strip()
                    if args.review_url is not None:
                        row['review_url'] = args.review_url.strip()
                    if lane_config(lane).get('claude_science_required') and not row.get('review_url', '').strip():
                        raise ValueError('lane requires a Claude Science review: pass --review-url (claude_science_required)')
                    if args.independent_check is not None:
                        row['independent_check'] = args.independent_check.strip()
                    if row.get('source_type') == 'claude-science' and not row.get('independent_check', '').strip():
                        # conclusions as leads until something outside it has checked them.
                        raise ValueError('claude-science idea: pass --independent-check (what we re-verified outside Claude Science)')
                    if args.prior_art is not None:
                        row['prior_art'] = str(Path(args.prior_art).expanduser().resolve())
                    if not (row.get('prior_art') and Path(row['prior_art']).is_file()):
                        raise ValueError('promote needs --prior-art FILE: the best public method and its number, '
                                         'reproduced as the baseline (prior-art-first)')
                    if idea_policy.enabled(lane) or args.policy_version == 2:
                        try:
                            receipt = idea_policy.prior_art(row['prior_art'])
                        except ValueError as exc:
                            raise ValueError(str(exc) + '\nRun: ' + prior_art_hint(row) +
                                             '\nReplace the baseline placeholder with the best public method and its number; '
                                             'X also requires a real capture for this KEY.') from exc
                        row['prior_art_sha256'] = receipt['sha256']
                        if row.get('board', '').strip() != 'none':
                            declaration = json.loads(args.selection_policy.expanduser().read_text()) if args.selection_policy else None
                            if args.policy_version == 2:
                                selection_policy.lane_policy(declaration, lane_config(lane))
                            idea_policy.freeze(row, args.sealed_holdout, args.no_holdout_reason,
                                               policy_version=args.policy_version, selection=declaration)
                    who = decider(args.decided_by)
                    error = taste_error(who) or promotion_error(row)
                    if error:
                        raise ValueError(error)
                    row['decided_by'] = who
                    row['board'] = row['board'].strip()
                    if args.action == 'promote':
                        row['testing_started'] = now()
                    row.update(status='testing', runnable=row['board'] != 'none')
                else:
                    lessons.close_options(args, lane_config(lane).get('lessons_required', False))
                    if row['status'] not in ('new', 'testing'):
                        raise ValueError('close requires status=new or testing')
                    result = Path(args.result_path).expanduser().resolve() if args.result_path else None
                    if args.result_path and not result.is_file():
                        raise ValueError('result_path must point to an existing file')
                    if not result and not args.closed_reason.strip() and not ((idea_policy.enabled(lane) or row.get('policy_version') == 2) and args.no_test_reason.strip()):
                        raise ValueError('close requires existing result_path or non-empty closed_reason')
                    who = decider(args.decided_by)
                    if args.mechanical:
                        if not result:
                            raise ValueError('--mechanical close needs --result-path showing the bar failed')
                    else:
                        error = taste_error(who)
                        if error:
                            raise ValueError(error)
                    if idea_policy.enabled(lane) or row.get('policy_version') == 2:
                        if result:
                            if row.get('result_path') != str(result) or not row.get('attempt_records'):
                                if row['status'] != 'testing':
                                    raise ValueError('result close requires a frozen testing idea; promote before running')
                                idea_policy.record_result(row, result, args.config_path)
                            elif idea_policy.file_hash(result)[1] != row.get('result_sha256'):
                                raise ValueError('recorded result bytes changed')
                        error = idea_policy.close_error(row, args.attempts, args.no_test_reason, lane_config(lane).get('minimum_attempts', 2), bool(result))
                        if error:
                            raise ValueError(error)
                        row.update(no_test_reason=args.no_test_reason.strip(), attempts_declared=args.attempts, close_result_supplied=bool(result))
                    row.update(status='closed', result_path=str(result) if result else row.get('result_path', ''), closed_reason=args.closed_reason.strip() or (args.no_test_reason.strip() if idea_policy.enabled(lane) or row.get('policy_version') == 2 else ''),
                               decided_by=who, mechanical=bool(args.mechanical),
                               close_kind=args.close_kind or ('bar-failed' if args.mechanical else ''))
                if args.action == 'close':
                    lessons.close_record(lane, row, args, sys.modules[__name__])
                row.update(revised=now(), event=args.action)
                append(lane / 'IDEAS.jsonl', row)
                print(row['id'] + ' ' + row['status'])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as e:
        print('rh: ' + str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
