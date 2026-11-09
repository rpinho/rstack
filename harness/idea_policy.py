"""Local evidence contracts; no network, workers, review steps or queue rewrites."""
import settings
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import selection_policy

EXCLUDED = settings.names('RH_POLICY_EXCLUDED')
SOURCES = ('github', 'x', 'papers', 'leaderboards')
# New admission requirements are prospective. Historical defects remain visible.
FROM = '2026-11-03T00:16:02+00:00'
# Only these historical admission defects can be downgraded. Integrity,
# promotion, source, taste and lane-health failures never use these mechanisms.
RECEIPT_ERRORS = frozenset((
    'result lacks frozen bar receipt',
    'result has no earlier frozen bar event',
    'result lacks config and result hash receipt',
    'no silent close: pass --attempts N with distinct recorded configs, or explicit --no-test-reason',
))
STRONG_DECIDERS = ('claude-opus-5-5', 'claude-fable-5-1', 'gpt-6-astra')


def enabled(lane):
    return lane.name not in EXCLUDED


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    if not path: raise ValueError("evidence file path is required")
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError('evidence file must exist and be nonempty: ' + str(path))
    data = path.read_bytes()
    if not data.strip():
        raise ValueError('evidence file must exist and be nonempty: ' + str(path))
    return str(path), hashlib.sha256(data).hexdigest()


def prior_art(path, x_pending_ok=False):
    """Structured receipt, with a baseline and an honest disposition for every source.

    Markdown can embed one fenced rh-prior-art JSON block. Failed/incomplete
    searches may be preserved as blocked, but cannot satisfy promotion.

    X_PENDING_OK is for the sweep compiler only, for a lead whose X search the worker asked for
    with `X QUERY` (planets, 11-09: every pass found one fresh lead and failed on its X source
    until someone ran the query). An X source that is missing or blocked is then accepted as
    pending and every other source is still checked; the result says x_pending=True. Promotion
    never passes it, so a lead with no X search still cannot be promoted.
    """
    path, sha = file_hash(path)
    text = Path(path).read_text()
    if not text.lstrip().startswith('{'):
        match = re.search(r'^```rh-prior-art\s*\n(.*?)\n```\s*$', text, re.M | re.S)
        if not match:
            raise ValueError('prior-art needs JSON or a fenced rh-prior-art JSON receipt')
        text = match.group(1)
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError('prior-art invalid JSON: ' + str(exc))
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise ValueError('prior-art requires schema=1')
    if not isinstance(data.get('baseline'), str) or not data['baseline'].strip():
        # Say what was found: friends, 11-09, wrote an object here and spent a repair pass per stage
        # learning that the field is one string.
        found = type(data.get('baseline')).__name__ if 'baseline' in data else 'missing'
        raise ValueError('prior-art baseline must be one string naming the best public method and its number '
                         '(found {}; structured details may go in baseline_details)'.format(found))
    searches = data.get('sources')
    if not isinstance(searches, dict):
        raise ValueError('prior-art sources must cover GitHub, X, papers and leaderboards')
    pending = False
    for source in SOURCES:
        entry = searches.get(source)
        if (source == 'x' and x_pending_ok
                and (entry is None or (isinstance(entry, dict) and entry.get('status') == 'blocked'))):
            pending = True
            continue
        if not isinstance(entry, dict) or entry.get('status') not in ('hits', 'none'):
            raise ValueError('prior-art {}: list hits or searched, none (blocked/missing is incomplete)'.format(source))
        if not isinstance(entry.get('query'), str) or not entry['query'].strip():
            raise ValueError('prior-art {} requires the actual query/scope'.format(source))
        try:
            searched = dt.datetime.fromisoformat(entry['searched_at'].replace('Z', '+00:00'))
            if searched.tzinfo is None or searched > dt.datetime.now(dt.timezone.utc):
                raise ValueError('not a past timezone-aware time')
        except (KeyError, AttributeError, TypeError, ValueError):
            raise ValueError('prior-art {} requires a past searched_at with timezone'.format(source))
        hits = entry.get('hits')
        if not isinstance(hits, list) or any(not isinstance(url, str) or not re.match(r'https?://\S+$', url) for url in hits):
            raise ValueError('prior-art {} hits must be a URL list'.format(source))
        if bool(hits) != (entry['status'] == 'hits'):
            raise ValueError('prior-art {}: hits/none disagrees with hit list'.format(source))
        if not isinstance(entry.get('note'), str) or not entry['note'].strip():
            raise ValueError('prior-art {} requires a search outcome note'.format(source))
        if source == 'x':
            # This is captured intake, never permission for a worker to search X.
            capture, capture_sha = file_hash(entry.get('capture_path'))
            if capture_sha != entry.get('capture_sha256'):
                raise ValueError('prior-art x capture hash mismatch')
    out = dict(path=path, sha256=sha, baseline=data['baseline'])
    if pending:
        out['x_pending'] = True
    return out


def frozen_payload(row):
    keys = ('board', 'test', 'bar', 'holdout_policy', 'holdout_reason')
    if row.get('policy_version') == 2:
        keys += ('policy_version', 'selection_policy')
    return {k: row.get(k, '') for k in keys}


def freeze(row, sealed=False, no_holdout_reason='', clock=None, *, policy_version=None, selection=None):
    if bool(sealed) == bool(no_holdout_reason.strip()):
        raise ValueError('declare --sealed-holdout OR --no-holdout-reason (e.g. exact certificate); never self-score a holdout')
    version = row.get('policy_version', 1) if policy_version is None else policy_version
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported policy_version')
    if version == 2:
        selection = selection if selection is not None else row.get('selection_policy')
        selection_policy.validate(selection)
        selection = json.loads(json.dumps(selection, allow_nan=False))
        row.update(policy_version=2, selection_policy=selection,
                   n_trials_total=selection['n_trials_total'], trial_records=selection.get('trials', []))
    elif selection is not None:
        raise ValueError('selection declaration requires policy_version=2')
    row.update(holdout_policy='sealed' if sealed else 'not-applicable',
               holdout_reason=no_holdout_reason.strip(), sealed_holdout=bool(sealed))
    payload = frozen_payload(row)
    row['frozen_bar'] = dict(payload, at=clock or dt.datetime.now(dt.timezone.utc).isoformat())
    row['frozen_bar_sha256'] = digest(payload)
    return row


def frozen_error(row):
    frozen = row.get('frozen_bar')
    if not isinstance(frozen, dict) or not frozen.get('at'):
        return 'missing frozen bar receipt; freeze the bar and holdout disposition before the first result'
    try:
        when = dt.datetime.fromisoformat(frozen['at'].replace('Z', '+00:00'))
        if when.tzinfo is None or when > dt.datetime.now(dt.timezone.utc):
            return 'frozen bar timestamp must be in the past and include timezone'
    except (AttributeError, TypeError, ValueError):
        return 'invalid frozen bar timestamp'
    if row.get('policy_version') == 2:
        try:
            selection_policy.validate(row.get('selection_policy'))
        except (ValueError, TypeError, KeyError) as exc:
            return str(exc)
    payload = frozen_payload(row)
    if row.get('frozen_bar_sha256') != digest(payload) or any(frozen.get(k) != v for k,v in payload.items()):
        return 'frozen bar changed (board, test, bar or holdout disposition)'
    if not all(isinstance(payload[k], str) and payload[k].strip() for k in ('board', 'test', 'bar')):
        return 'frozen bar requires board, test and bar'
    if payload['holdout_policy'] == 'sealed':
        if row.get('sealed_holdout') is not True or payload['holdout_reason']:
            return 'sealed holdout disposition inconsistent'
    elif payload['holdout_policy'] == 'not-applicable':
        if row.get('sealed_holdout') is not False or not payload['holdout_reason'].strip():
            return 'non-holdout work requires an explicit reason'
    else:
        return 'missing sealed-holdout disposition'
    return ''


def record_result(row, result, config, clock=None):
    error = frozen_error(row)
    if error:
        raise ValueError(error)
    if row.get('board') == 'none' or row.get('runnable') is False:
        raise ValueError('board=none is routing only; it cannot record an experiment')
    result, result_sha = file_hash(result)
    config, config_sha = file_hash(config)
    try:
        parameters = json.loads(Path(config).read_text())
        if not isinstance(parameters, dict) or not parameters:
            raise ValueError('expected nonempty object')
    except (ValueError, TypeError) as exc:
        raise ValueError('--config-path requires a nonempty JSON configuration object: ' + str(exc))
    selection_policy.check_config(row, parameters)
    semantic_sha = digest(parameters)  # Cosmetic JSON formatting is not another config.
    records = list(row.get('attempt_records', []))
    # One artifact cannot manufacture a second attempt. Distinct runs may measure the same value.
    if any(r['result_path'] == result for r in records):
        raise ValueError('result path already recorded; use a separate immutable result artifact per attempt')
    records.append(dict(config_path=config, config_file_sha256=config_sha,
        config_sha256=semantic_sha, result_path=result, result_sha256=result_sha,
        at=clock or dt.datetime.now(dt.timezone.utc).isoformat(), frozen_bar_sha256=row['frozen_bar_sha256']))
    row.update(result_path=result, result_sha256=result_sha, attempt_records=records)
    return row


def attempts_error(row):
    records = row.get('attempt_records', [])
    if not isinstance(records, list) or any(not isinstance(a, dict) for a in records):
        return 'attempt_records must be a list of evidence objects'
    if records and (row.get('result_path') != records[-1].get('result_path') or
                    row.get('result_sha256') != records[-1].get('result_sha256')):
        return 'current result pointer disagrees with its attempt receipt'
    for attempt in records:
        if attempt.get('frozen_bar_sha256') != row.get('frozen_bar_sha256'):
            return 'attempt does not match frozen bar'
        try:
            frozen_at = dt.datetime.fromisoformat(row['frozen_bar']['at'].replace('Z', '+00:00'))
            ran_at = dt.datetime.fromisoformat(attempt['at'].replace('Z', '+00:00'))
            if ran_at.tzinfo is None or frozen_at > ran_at or ran_at > dt.datetime.now(dt.timezone.utc):
                return 'attempt timestamp precedes its frozen bar or is in the future'
        except (KeyError, AttributeError, TypeError, ValueError):
            return 'invalid attempt/frozen timestamp'
        for field, hashfield in (('result_path','result_sha256'), ('config_path','config_file_sha256')):
            try:
                if file_hash(attempt.get(field))[1] != attempt.get(hashfield):
                    return 'attempt {} hash mismatch'.format(field)
            except (OSError, ValueError) as exc:
                return str(exc)
        try:
            if digest(json.loads(Path(attempt['config_path']).read_text())) != attempt.get('config_sha256'):
                return 'attempt configuration identity mismatch'
        except (KeyError, OSError, ValueError, TypeError):
            return 'invalid attempt configuration identity'
    return ''


def close_error(row, declared, reason, minimum=2, result_supplied=False):
    if declared is not None and (type(declared) is not int or declared < minimum):
        return '--attempts must be >= lane minimum {}'.format(minimum)
    if declared is not None:
        records = row.get('attempt_records', [])
        configs = {r['config_sha256'] for r in records}
        if declared > len(records) or len(configs) < minimum:
            return '--attempts needs recorded runs in at least {} distinct configs'.format(minimum)
        return attempts_error(row)
    if not reason.strip() and not result_supplied:
        return 'no silent close: pass --attempts N with distinct recorded configs, or explicit --no-test-reason'
    if result_supplied:
        error = frozen_error(row)
        if error:
            return error
        if not row.get('attempt_records'):
            return 'result close needs a recorded configuration and result receipt'
    return attempts_error(row)


def parse_event_time(row):
    return dt.datetime.fromisoformat(str(row.get('revised') or row.get('created') or
        row.get('date') or row.get('ts') or '').replace('Z', '+00:00'))


def resolutions(history, lane):
    """Validate links and lane-owned exceptions without changing any evidence.

    Positions bound downgrades to the original close, so a later result/close
    under the same id cannot inherit a historical exception.
    """
    groups = {}
    for pos, row in enumerate(history):
        groups.setdefault(row['id'], []).append((pos, row))
    superseded, exceptions, errors = {}, {}, []
    seen = set()
    for pos, row in enumerate(history):
        if 'reopens' not in row:
            if row.get('event') == 'reopen_link':
                errors.append('idea {}: reopen_link requires reopens'.format(row['id']))
            continue
        original, child = row['reopens'], row['id']
        label = 'idea {}: invalid reopen link: '.format(child)
        if not isinstance(original, str) or not original or original == child or original not in groups:
            errors.append(label + 'reopens must name a different existing idea')
            continue
        if (original, child) in seen:
            continue
        seen.add((original, child))
        first_pos, first = groups[child][0]
        prior = [(i, r) for i, r in groups[original] if i < first_pos]
        try:
            close_pos, closed = prior[-1]
            if closed.get('status') != 'closed' or parse_event_time(first) <= parse_event_time(closed):
                raise ValueError('reopen must be a later row after the original close')
            if parse_event_time(row) < parse_event_time(first):
                raise ValueError('link predates the reopen')
            targets = {r.get('reopens') for _, r in groups[child] if isinstance(r.get('reopens'), str)}
            if len(targets) != 1:
                raise ValueError('reopen has conflicting original ids')
        except (IndexError, TypeError, ValueError) as exc:
            errors.append(label + str(exc))
            continue
        name = child + (' (' + first['friend_queue_id'] + ')' if first.get('friend_queue_id') else '')
        superseded.setdefault(original, []).append((close_pos, 'superseded by reopen ' + name))

    path = lane / 'lint_exceptions.jsonl'
    if not path.exists():
        return superseded, exceptions, errors
    start = dt.datetime.fromisoformat(FROM)
    end = start + dt.timedelta(hours=2)
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        label = '{}:{}: '.format(path, line_no)
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not entry[k].strip()
                    for k in ('id', 'reason', 'evidence_path', 'decided_by', 'utc')):
                raise ValueError('exception requires nonempty id, reason, evidence_path, decided_by and utc')
            decided = entry['decided_by'].strip()
            owners = '|'.join(re.escape(n) for n in ('operator', *sorted(settings.names('RH_OWNER_ALIASES'))))
            if not (re.match(r'^(?:' + owners + r')(?:\b|$)', decided, re.I) or any(
                    re.search(r'(?<![\w-])' + re.escape(model) + r'(?![\w-])', decided)
                    for model in STRONG_DECIDERS)):
                raise ValueError('exception decided_by must identify Operator or a strong model: ' + ', '.join(STRONG_DECIDERS))
            when = dt.datetime.fromisoformat(entry['utc'].replace('Z', '+00:00'))
            if when.tzinfo is None or when.utcoffset() != dt.timedelta(0) or when > dt.datetime.now(dt.timezone.utc):
                raise ValueError('exception utc must be a past UTC timestamp')
            evidence = Path(entry['evidence_path']).expanduser()
            if not evidence.is_absolute():
                evidence = lane / evidence
            verdicts = [p for p in evidence.glob('VERDICT*')
                        if p.is_file() and (p.name == 'VERDICT' or p.name.startswith('VERDICT.'))] if evidence.is_dir() else []
            holds = False
            for verdict in verdicts:
                lines = [s.strip() for s in verdict.read_text().splitlines() if s.strip()]
                if lines and re.fullmatch(r'(?:VERDICT\s*:\s*)?HOLDS(?: WITH CAVEATS)?',
                        lines[0].strip('#*` ').upper()):
                    holds = True
            if not holds:
                raise ValueError('exception evidence_path must be a directory containing a VERDICT file with HOLDS or HOLDS WITH CAVEATS as its verdict')
            eligible, previous = [], None
            for index, item in groups.get(entry['id'], []):
                if item.get('status') == 'closed' and (previous is None or previous.get('status') != 'closed'):
                    closed_at = parse_event_time(item)
                    if closed_at.tzinfo is not None and start <= closed_at <= end and closed_at <= when:
                        eligible.append(index)
                previous = item
            if not eligible:
                raise ValueError('exception id has no close in [cutover, cutover + 2 h] before its decision')
            citation = 'lint exception {} ({}; {}; evidence={})'.format(label.rstrip(': '),
                entry['reason'], decided, evidence)
            for index in eligible:
                exceptions.setdefault(entry['id'], []).append((index, citation))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            errors.append(label + str(exc))
    return superseded, exceptions, errors


def audit(history, lane, minimum=2, selection_config=None):
    """Aggregate by idea, preserving original freeze and result bytes across revisions."""
    if not enabled(lane):
        return selection_policy.audit(history, lane, selection_config), []
    groups = {}
    for row in history:
        groups.setdefault(row['id'], []).append(row)
    superseded, exceptions, errors = resolutions(history, lane)
    positions = {id(row): index for index, row in enumerate(history)}
    warnings = []
    def receipt_error(key, row, message, new=True):
        label = 'idea {}: '.format(key)
        if new and message in RECEIPT_ERRORS:
            candidates = superseded.get(key, [])
            # Referee exceptions are restricted by both close position and gap time.
            try:
                when = parse_event_time(row)
                start = dt.datetime.fromisoformat(FROM)
                if when.tzinfo is not None and start <= when <= start + dt.timedelta(hours=2):
                    candidates = candidates + exceptions.get(key, [])
            except (TypeError, ValueError):
                pass
            for close_pos, citation in candidates:
                if positions[id(row)] <= close_pos:
                    warnings.append(label + message + ' [WARNING: ' + citation + ']')
                    return
        (errors if new else warnings).append(label + message)
    for key, group in groups.items():
        prior_freeze = None; result_bar = None; results = {}; attempts = []
        previous = None
        for row in group:
            earlier_freeze = prior_freeze
            try:
                event_time = dt.datetime.fromisoformat(str(row.get('revised') or row.get('created') or row.get('date') or row.get('ts') or '').replace('Z', '+00:00'))
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=dt.timezone.utc)
                new = event_time >= dt.datetime.fromisoformat(FROM)
            except (TypeError, ValueError):
                new = False
                errors.append('idea {}: invalid policy event timestamp'.format(key))
            label = 'idea {}: '.format(key)
            if prior_freeze and not row.get('frozen_bar'):
                errors.append(label + 'original frozen bar receipt removed')
            if result_bar is not None and frozen_payload(row) != result_bar:
                errors.append(label + 'bar edited after first result')
            if attempts and row.get('attempt_records', [])[:len(attempts)] != attempts:
                errors.append(label + 'attempt history removed or replaced')
            if row.get('frozen_bar'):
                error = frozen_error(row)
                if error: errors.append(label + error)
                if prior_freeze and row['frozen_bar'] != prior_freeze:
                    errors.append(label + 'original frozen bar receipt was replaced')
                prior_freeze = prior_freeze or row['frozen_bar']
            started = row.get('status') in ('testing', 'shipped') and (previous is None or previous.get('status') not in ('testing', 'shipped'))
            if row.get('event') in ('promote', 'freeze') or started:
                try:
                    receipt = prior_art(row.get('prior_art'))
                    if receipt['sha256'] != row.get('prior_art_sha256'):
                        (errors if new else warnings).append(label + 'prior-art receipt hash mismatch')
                except (OSError, ValueError, TypeError) as exc:
                    (errors if new else warnings).append(label + 'prior-art: ' + str(exc))
                error = frozen_error(row) if row.get('board') != 'none' else ''
                if error: (errors if new else warnings).append(label + error)
            if row.get('result_path'):
                admission = previous is None or previous.get('result_path') != row['result_path'] or len(row.get('attempt_records', [])) > len(previous.get('attempt_records', []))
                if result_bar is None:
                    result_bar = frozen_payload(row)
                    if not row.get('frozen_bar'):
                        receipt_error(key, row, 'result lacks frozen bar receipt', new)
                elif frozen_payload(row) != result_bar:
                    errors.append(label + 'bar edited after first result')
                if new and admission and not earlier_freeze:
                    receipt_error(key, row, 'result has no earlier frozen bar event')
                if new and admission and not row.get('attempt_records'):
                    receipt_error(key, row, 'result lacks config and result hash receipt')
                for attempt in row.get('attempt_records', []):
                    old = results.get(attempt.get('result_path'))
                    if old and old != attempt.get('result_sha256'):
                        errors.append(label + 'original result bytes replaced')
                    results[attempt.get('result_path')] = attempt.get('result_sha256')
                error = attempts_error(row)
                if error: receipt_error(key, row, error)
                current_attempts = row.get('attempt_records', [])
                if current_attempts[:len(attempts)] != attempts:
                    errors.append(label + 'attempt history removed or replaced')
                attempts = current_attempts
            if row.get('status') == 'closed' and new and (previous is None or previous.get('status') != 'closed'):
                error = close_error(row, row.get('attempts_declared'), row.get('no_test_reason',''), minimum, bool(row.get('close_result_supplied')))
                if error: receipt_error(key, row, error)
            if row.get('status') == 'closed' and not row.get('mechanical') and row.get('decided_by') and not row.get('result_path'):
                warnings.append(label + 'taste close with no run; no-test reason: ' + (row.get('no_test_reason') or 'UNRECORDED'))
            previous = row
        last = group[-1]
        if last.get('status') == 'closed' and last.get('attempt_records'):
            configs = {r['config_sha256'] for r in last['attempt_records']}
            if len(configs) < minimum:
                warnings.append('idea {}: closed after only one distinct config; no second variant recorded'.format(key))
    errors.extend(selection_policy.audit(history, lane, selection_config))
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))
