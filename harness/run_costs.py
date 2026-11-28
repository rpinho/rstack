"""Offline usage attribution and estimates for a single executor attempt.

Input includes reads and writes to the prompt cache. Output includes reasoning.
Only counters attributable to this attempt qualify. Source strings identify the
schema without copying transcript paths or contents into grade records.
"""
import __future__
from collections import defaultdict
from contextlib import closing
import datetime as dt
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

from model_slugs import canon

COUNTS = ('input', 'cached_input', 'cache_write', 'output', 'reasoning')
BILLABLE = COUNTS[:-1]
UNKNOWN = 'unknown'
SKEW = 5
START_SLACK = 90
CONFIG = Path(__file__).resolve().parent / 'leaderboard'
if not CONFIG.is_dir():  # source checkout; harness-sync installs the cards beside the modules
    CONFIG = CONFIG.parent.parent / 'leaderboard'
LOG = logging.getLogger(__name__)


class Unavailable(ValueError):
    """An expected, content-free reason to omit usage."""


def timestamp(value):
    try:
        if type(value) in (int, float):
            return value if math.isfinite(value) else None
        when = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)).timestamp()
    except (AttributeError, ValueError, OverflowError, OSError):
        return None


def mapping(value):
    return value if isinstance(value, dict) else {}


def amount(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def config(name):
    try:
        return mapping(json.loads((CONFIG / (name + '.json')).read_text()))
    except (OSError, ValueError):
        return {}


def events(path, markers=()):
    """Stream records, avoiding JSON decoding unrelated prompt and tool-output lines."""
    try:
        with Path(path).open('rb') as stream:
            for line in stream:
                if markers and not any(marker in line for marker in markers):
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def tokens(source, counts, **extra):
    if (any(type(n) is not int or n < 0 for n in counts)
            or counts[1] + counts[2] > counts[0] or counts[4] > counts[3]):
        raise Unavailable('invalid token counters')
    return dict(zip(COUNTS, counts), source=source, **extra)


def breakdown(value):
    """Validate an already captured breakdown without trusting unrelated ledger fields."""
    if not isinstance(value, dict) or not value.get('source'):
        return None
    try:
        extra = {key: value[key] for key in ('served_models',) if key in value}
        return tokens(value['source'], [value[key] for key in COUNTS], **extra)
    except (KeyError, Unavailable):
        return None


def workspace(value):
    if not value:
        return ''
    path = os.path.realpath(os.path.expanduser(value))
    return path.removeprefix('/private') if path.startswith(('/private/tmp/', '/private/var/')) else path


def bounds(run):
    start = timestamp(run.get('started_at') or run.get('utc'))
    end = timestamp(run.get('closed_at'))
    if start is None or end is None or end < start:
        raise Unavailable('run has no closed time interval')
    return start, end


def starts_in(at, start, end):
    return at is not None and start - SKEW <= at <= min(start + START_SLACK, end + SKEW)


def artifact(run, start, end):
    """A shared .last.md may already belong to another attempt."""
    if not run.get('transcript'):
        return {}
    path = Path(run['transcript']).expanduser()
    try:
        if not start - SKEW <= path.stat().st_mtime <= end + SKEW:
            return {}
        return mapping(json.loads(path.read_text(errors='replace')))
    except (ValueError, OSError):
        return {}


def claude_counts(usage):
    plain = usage.get('input_tokens')
    read = usage.get('cache_read_input_tokens', 0)
    write = usage.get('cache_creation_input_tokens', 0)
    output = usage.get('output_tokens')
    reasoning = mapping(usage.get('output_tokens_details')).get('thinking_tokens', 0)
    if any(type(n) is not int or n < 0 for n in (plain, read, write)):
        raise Unavailable('invalid Claude input counters')
    return plain + read + write, read, write, output, reasoning


def claude_scalar_agrees(run, used):
    scalar = run.get('tokens')
    return type(scalar) is not int or scalar == (
        used['input'] - used['cached_input'] - used['cache_write'] + used['output'])


def sum_counts(parts):
    return [sum(ns) for ns in zip(*parts)]


def codex_events(path):
    for row in events(path, (b'"token_count"', b'"turn_context"')):
        payload = mapping(row.get('payload'))
        if row.get('type') == 'turn_context' or (
                row.get('type') == 'event_msg' and payload.get('type') == 'token_count'):
            yield row, payload


def codex_counts(usage):
    reasoning = usage.get('reasoning_output_tokens', 0)
    output = usage.get('output_tokens')
    counts = tokens('codex rollout', (usage.get('input_tokens'), usage.get('cached_input_tokens', 0),
                                     usage.get('cache_write_input_tokens', 0), output, reasoning))
    total = usage.get('total_tokens')
    if total is not None and (type(total) is not int or total != counts['input'] + counts['output']):
        raise Unavailable('Codex total disagrees with input plus output')
    return counts


class TokenReader:
    """Reuse discovery across a batch. Reads are local and never launch a provider."""
    def __init__(self, codex_sessions=None, claude_projects=None, agy_decoder=None, agy_dirs=None):
        home = Path.home()
        agy_project = home / 'dev/open-science/gemini_usage_1127'
        configured = codex_sessions or os.environ.get('RH_CODEX_SESSIONS')
        if configured:
            roots = os.fspath(configured).split(os.pathsep)
        elif os.environ.get('CODEX_HOME'):
            roots = (Path(os.environ['CODEX_HOME']) / 'sessions',)
        else:
            # The Codex wrapper keeps ordinary batch rollouts in its clean home.
            roots = (home / '.codex/sessions', home / '.codex-clean/sessions')
        self.codex_sessions = tuple(dict.fromkeys(Path(root).expanduser().resolve() for root in roots if root))
        self.claude_projects = Path(claude_projects or os.environ.get('RH_CLAUDE_PROJECTS') or home / '.claude/projects').expanduser()
        self.agy_decoder = Path(agy_decoder or os.environ.get('RH_AGY_USAGE_DECODER') or agy_project / 'usage.py').expanduser()
        directories = os.environ.get('RH_AGY_CONVERSATIONS')
        if agy_dirs is None:
            agy_dirs = directories.split(os.pathsep) if directories else (
                home / '.gemini/antigravity-cli/conversations',
                agy_project / 'data/m5/conversations', agy_project / 'data/m4/conversations')
        self.agy_dirs = [Path(path).expanduser() for path in agy_dirs]
        self.codex_days = {}
        self.agy_index = None
        self.decoder = None

    def measure(self, run):
        try:
            run = run or {}
            saved = breakdown(run.get('token_usage')) or breakdown(run.get('tokens'))
            if saved:
                return saved, None
            reader = {'claude': self.claude, 'codex': self.codex, 'agy': self.agy}.get(run.get('backend'))
            if reader is None:
                raise Unavailable('unsupported or missing run backend')
            start, end = bounds(run)
            if not run.get('workdir'):
                raise Unavailable('run has no work directory')
            return reader(run, start, end), None
        except Unavailable as exc:
            return None, str(exc)
        except Exception as exc:  # telemetry cannot interfere with grading
            return None, 'usage reader failed ({})'.format(type(exc).__name__)

    def claude(self, run, start, end):
        result = artifact(run, start, end)
        artifact_disagrees = False
        if result.get('type') == 'result' and isinstance(result.get('usage'), dict):
            try:
                used = tokens('claude result', claude_counts(result['usage']),
                              served_models=sorted(mapping(result.get('modelUsage'))))
                artifact_disagrees = not claude_scalar_agrees(run, used)
                if not artifact_disagrees and (used['input'] or used['output']):
                    return used
            except Unavailable:
                artifact_disagrees = True
        session = result.get('session_id')
        if isinstance(session, str) and re.fullmatch(r'[\w-]+', session):
            paths = list(self.claude_projects.glob('*/' + session + '.jsonl'))
        else:
            directories = {os.path.abspath(run['workdir']), os.path.realpath(run['workdir'])}
            projects = {self.claude_projects / re.sub(r'[^a-zA-Z0-9-]', '-', d) for d in directories}
            paths = [path for project in projects for path in project.glob('*.jsonl')]
        candidates = []
        for path in paths:
            first = next((row for row in events(path) if row.get('cwd') and row.get('timestamp')), {})
            if workspace(first.get('cwd')) == workspace(run['workdir']) and starts_in(timestamp(first.get('timestamp')), start, end):
                candidates.append(path)
        if len(candidates) != 1:
            if candidates:
                raise Unavailable('ambiguous Claude sessions')
            if artifact_disagrees:
                raise Unavailable('Claude result counters disagree or are invalid')
            raise Unavailable('no matching Claude usage')
        messages = {}
        for row in events(candidates[0], (b'"assistant"',)):
            message = mapping(row.get('message'))
            if row.get('type') != 'assistant' or not message.get('usage') or message.get('model') == '<synthetic>':
                continue
            at = timestamp(row.get('timestamp'))
            if at is None or not start - SKEW <= at <= end + SKEW or not message.get('id'):
                raise Unavailable('Claude session usage exceeds the attempt bounds')
            messages[message['id']] = message
        if not messages:
            raise Unavailable('no measured Claude messages')
        measured = [tokens('claude session', claude_counts(msg['usage'])) for msg in messages.values()]
        used = tokens('claude session', sum_counts([[item[key] for key in COUNTS] for item in measured]),
                      served_models=sorted({m.get('model') or UNKNOWN for m in messages.values()}))
        if not claude_scalar_agrees(run, used):
            raise Unavailable('Claude session totals disagree with executor counters')
        return used

    def rollouts(self, start):
        day = dt.datetime.fromtimestamp(start).date()
        for offset in (-1, 0, 1):
            date = day + dt.timedelta(days=offset)
            if date not in self.codex_days:
                index = defaultdict(list)
                for path in self.rollout_paths(date.strftime('%Y/%m/%d')):
                    record = next(events(path), {})
                    meta = mapping(record.get('payload'))
                    if record.get('type') != 'session_meta' or meta.get('source') not in (None, 'exec'):
                        continue
                    if meta.get('model_provider') not in (None, 'openai'):
                        continue
                    index[workspace(meta.get('cwd'))].append((timestamp(meta.get('timestamp') or record.get('timestamp')), path))
                self.codex_days[date] = index
            yield self.codex_days[date]

    def rollout_paths(self, date_pattern='????/??/??'):
        for root in self.codex_sessions:
            yield from root.glob(date_pattern + '/rollout-*.jsonl')

    def codex(self, run, start, end):
        cwd = workspace(run.get('workdir'))
        paths = [path for index in self.rollouts(start) for at, path in index.get(cwd, ()) if starts_in(at, start, end)]
        if len(paths) != 1:
            raise Unavailable('ambiguous Codex rollouts' if paths else 'no matching Codex rollout')
        seen_models, latest = set(), None
        for row, payload in codex_events(paths[0]):
            if row['type'] == 'turn_context' and payload.get('model'):
                seen_models.add(payload['model'])
            info = mapping(payload.get('info'))
            if info.get('total_token_usage'):
                at = timestamp(row.get('timestamp'))
                if at is None or not start - SKEW <= at <= end + SKEW:
                    raise Unavailable('Codex usage exceeds the attempt bounds')
                # The cumulative value already includes older events. The inclusion flag
                # describes last_token_usage only; the cumulative output is inclusive.
                latest = codex_counts(info['total_token_usage'])
        if not latest:
            raise Unavailable('no measured Codex usage')
        scalar = run.get('tokens')
        # The CLI's "tokens used" is uncached prompt input plus output.
        if type(scalar) is int and scalar != latest['input'] - latest['cached_input'] + latest['output']:
            raise Unavailable('Codex rollout totals disagree with executor counters')
        return dict(latest, served_models=sorted(seen_models))

    def agy_library(self):
        if self.decoder is not None:
            return self.decoder
        if not self.agy_decoder.is_file():
            raise Unavailable('agy decoder unavailable')
        spec = importlib.util.spec_from_file_location('_rstack_agy_usage_' + str(id(self)), self.agy_decoder)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # the decoder uses dataclasses
        # The separately maintained decoder uses newer annotation syntax.
        # Postpone evaluation so it also loads under the harness's Python 3.9.
        try:
            exec(compile(self.agy_decoder.read_bytes(), str(self.agy_decoder), 'exec',
                         flags=__future__.annotations.compiler_flag, dont_inherit=True), mod.__dict__)
        finally:
            sys.modules.pop(spec.name, None)
        self.decoder = mod
        return mod

    def agy_metadata(self, library, path):
        with closing(library.connect(path)) as db:
            row = db.execute("SELECT data FROM trajectory_metadata_blob WHERE id = 'main'").fetchone()
        if not row:
            return None, ''
        meta = library.fields(row[0])
        cwd = library.text(meta.get(7)) or library.text(library.fields(meta.get(1, b'')).get(1))
        return library.timestamp(meta.get(2, b'')), library.workspace_path(cwd)

    def agy(self, run, start, end):
        library = self.agy_library()
        cwd = library.workspace_path(run['workdir'])
        result = artifact(run, start, end)
        recorded = result.get('conversation_id')
        if not isinstance(recorded, str) or not re.fullmatch(r'[\w-]+', recorded):
            recorded = None
        if recorded:
            paths = [d / (recorded + '.db') for d in self.agy_dirs]
            candidates = [p for p in paths if p.is_file()]
        else:
            if self.agy_index is None:
                self.agy_index = defaultdict(list)
                for directory in self.agy_dirs:
                    for path in directory.glob('*.db'):
                        try:
                            at, directory_key = self.agy_metadata(library, path)
                            self.agy_index[directory_key].append((at, path))
                        except (OSError, ValueError, sqlite3.Error):
                            continue
            candidates = [path for at, path in self.agy_index.get(cwd, ()) if starts_in(at, start, end)]
        matched = {}
        for path in candidates:
            try:
                created, directory_key = self.agy_metadata(library, path)
                if cwd != directory_key or not starts_in(created, start, end):
                    continue
                data = self.agy_generations(library, path, created, start, end)
            except (OSError, ValueError, sqlite3.Error):
                continue
            if data and (recorded or library.model_family(run.get('model') or '') == data[1]):
                previous = matched.setdefault(path.stem, data[0])
                if previous != data[0]:
                    raise Unavailable('agy snapshots disagree')
        if len(matched) != 1:
            raise Unavailable('ambiguous agy conversations' if matched else 'no matching measured agy conversation')
        used = next(iter(matched.values()))
        scalar = run.get('tokens')
        if type(scalar) is int and scalar != used['input'] - used['cached_input'] + used['output']:
            raise Unavailable('agy generation totals disagree with executor counters')
        thinking = mapping(result.get('usage')).get('thinking_tokens')
        if type(thinking) is int and thinking != used['reasoning']:
            raise Unavailable('agy reasoning disagrees with executor counters')
        return used

    @staticmethod
    def agy_generations(library, path, created, start, end):
        with closing(library.connect(path)) as db:
            steps, requests = {}, defaultdict(list)
            for index, kind, blob in db.execute('SELECT idx, step_type, metadata FROM steps WHERE metadata IS NOT NULL'):
                meta = library.fields(blob)
                steps[index] = (kind, meta)
                if meta.get(35):
                    requests[meta[35]].append((index, kind, meta))
            parts, served, seen = [], set(), set()
            first_model = None
            for index, blob in db.execute('SELECT idx, data FROM gen_metadata ORDER BY idx'):
                gen = library.generation(index, blob)
                if not gen.measured:
                    # A quota rejection without counters does not represent a generation.
                    if b'resource_exhausted' in library.fields(blob).get(5, b'').lower():
                        continue
                    raise Unavailable('agy generation missing counters')
                at, method, _ = library.generation_time(gen, steps, requests, created)
                if (method == 'trajectory-created' or at is None or not start - SKEW <= at <= end + SKEW
                        or (gen.request and gen.request in seen)):
                    raise Unavailable('unattributed agy generation')
                if gen.repeated_usage and library.fields(gen.repeated_usage) != gen.tokens:
                    raise Unavailable('agy duplicate usage fields disagree')
                seen.add(gen.request)
                first_model = first_model or gen.model
                served.add(gen.api_model or gen.label or UNKNOWN)
                full, output, read = gen.counts
                # The CLI result's thinking_tokens agrees with field 9 of the
                # saved usage. Field 10 is the other output component.
                reasoning = gen.tokens.get(9, 0)
                if output != reasoning + gen.tokens.get(10, 0):
                    raise Unavailable('agy output split disagrees with total')
                parts.append((full, read, 0, output, reasoning))
        if parts:
            return tokens('agy conversation', sum_counts(parts), served_models=sorted(served)), first_model


def tokens_for(run):
    """Return complete counters or None. Log the reason at debug level on a miss."""
    try:
        usage, reason = TokenReader().measure(run)
    except Exception as exc:
        usage, reason = None, 'usage reader initialization failed ({})'.format(type(exc).__name__)
    if reason:
        LOG.debug('Run cost unavailable: %s', reason)
    return usage


def cost_for(run, reader=None, prices=None, plans=None):
    """Estimate USD using configured rates only. Always return a serializable grade field."""
    result = dict(api=UNKNOWN, plan=UNKNOWN, tokens={'reason': 'usage unavailable'})
    try:
        run = run or {}
        used, reason = (reader or TokenReader()).measure(run)
        result['tokens'] = used if used is not None else {'reason': reason}
        if used is None:
            return result
        model = canon(run.get('model'))
        served = {canon(name) if name != UNKNOWN else None for name in used.get('served_models', [])}
        if served:
            # Usage from multiple model versions has no single price. A saved
            # Gemini API name may omit the effort suffix of the requested route.
            model = next(iter(served)) if len(served) == 1 else None
        prices = config('prices') if prices is None else prices
        rates = mapping(prices.get(model))
        quantities = (used['input'] - used['cached_input'] - used['cache_write'],
                      used['cached_input'], used['cache_write'], used['output'])
        if model and rates and all(not n or amount(rates.get(key)) for key, n in zip(BILLABLE, quantities)):
            api = sum(n * rates[key] for key, n in zip(BILLABLE, quantities) if n) / 1_000_000
            if amount(api):
                result['api'] = api
        provider = {'claude': 'anthropic', 'codex': 'openai', 'agy': 'google'}.get(run.get('backend'))
        plans = config('plans') if plans is None else plans
        plan = mapping(plans.get(provider))
        monthly, calibration = plan.get('usd_per_month'), plan.get('tokens_per_weekly_percent')
        if amount(monthly) and amount(calibration) and calibration > 0:
            share = (used['input'] + used['output']) / calibration / 100 * (monthly * 12 / 52)
            if amount(share):
                result['plan'] = share
                day = valid_date(plan.get('calibration_as_of'))
                if day:
                    result['plan_as_of'] = day
    except Exception:  # config, unreadable files, or schema drift leave dollars unknown
        pass
    return result


def valid_date(value):
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None


def valid_cost(value):
    """An estimate record is separate from any provider-reported USD scalar."""
    return (isinstance(value, dict) and isinstance(value.get('tokens'), dict)
            and all(value.get(key) == UNKNOWN or amount(value.get(key)) for key in ('api', 'plan')))
