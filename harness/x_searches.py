"""Dated general-session X search outcomes. Local JSONL only; never fetch X."""
import datetime as dt
import json
from pathlib import Path

UTC = dt.timezone.utc


def validate(row, clock=None):
    """Reject incomplete, contradictory or undated search claims."""
    clock = clock or dt.datetime.now(UTC)
    required = {'utc', 'query', 'result', 'n_hits', 'captured_by'}
    optional = {'subject', 'evidence_file'}
    if not isinstance(row, dict) or not required <= row.keys() or row.keys() - (required | optional):
        raise ValueError('X search row requires utc, query, result, n_hits, captured_by; subject and evidence_file are optional')
    for key in ('utc', 'query', 'captured_by') + tuple(key for key in optional if key in row):
        if not isinstance(row[key], str) or not row[key].strip() or any(c in row[key] for c in '\r\n\0'):
            raise ValueError('X search ' + key + ' must be a nonempty single-line string')
    try:
        when = dt.datetime.fromisoformat(row['utc'].replace('Z', '+00:00'))
        if when.tzinfo is None or when > clock:
            raise ValueError('not a past timezone-aware timestamp')
    except (TypeError, ValueError):
        raise ValueError('X search utc must be a past ISO timestamp with timezone')
    if row['result'] not in ('none', 'hits'):
        raise ValueError('X search result must be none or hits')
    if type(row['n_hits']) is not int or row['n_hits'] < 0:
        raise ValueError('X search n_hits must be an integer >= 0')
    if (row['result'] == 'none') != (row['n_hits'] == 0):
        raise ValueError('X search result and n_hits disagree: none requires 0; hits requires > 0')
    return when.astimezone(UTC)


def recent(path, clock=None):
    """Validate the entire journal, then return only the last 14 days."""
    clock = clock or dt.datetime.now(UTC)
    path = Path(path)
    if not path.exists():
        return []
    cutoff = clock - dt.timedelta(days=14)
    result = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            when = validate(row, clock)
        except (TypeError, ValueError) as exc:
            raise ValueError('{}:{}: {}'.format(path, number, exc))
        if cutoff <= when <= clock:
            result.append(row)
    return result
