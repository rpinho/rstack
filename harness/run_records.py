"""Local run, grade and quota records shared by the executor and scorer."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys

import agy_quota
from model_slugs import canon
import run_costs
import score_verdicts


def runs_path():
    return Path(os.environ.get('RH_MODEL_RUNS_LOG') or Path.home() / '.local/state/model-runs.jsonl').expanduser()


def grades_path():
    return runs_path().with_name('everyday-grades.jsonl')


def read_jsonl(path):
    try:
        with Path(path).open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def append(path, row):
    row = score_verdicts.row(row)
    row = dict(row)
    if row.get('model'):
        row['model'] = canon(row['model']) or row['model']
    if row.get('run_id') and 'grade' in row and not isinstance(row.get('cost_usd'), dict):
        row['cost_usd'] = grade_cost(row['run_id'])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(row, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def is_probe(row):
    """Health calls never measure model work, including pre-purpose canary rows."""
    return row.get('purpose') == 'probe' or Path(str(row.get('job') or '')).name.startswith('canary-')


QUOTA_TEXT = {
    'agy': re.compile(r'AGY_QUOTA |RESOURCE[_ ]EXHAUSTED|Individual quota reached|\b429\b|quota|rate.?limit|too many requests|usage limit', re.I),
    'codex': re.compile(r'usage limit|usage_limit_reached|insufficient_quota|rate.?limit|429 too many', re.I),
    'claude': re.compile(r'hit (?:your |the )?limit|out of (?:usage|quota)|usage limit|usage_limit|rate.?limit|quota|\b429\b|too many requests', re.I),
}
RESET_EPOCH = re.compile(r'["\']?resets_at["\']?\s*:\s*(\d{10})\b', re.I)
RESET_AT = re.compile(r'\b(?:resets?(?:\s+(?:at|on))?|try again at)\s*:?\s*([^\n";]+)', re.I)


def quota_message(backend, text):
    pattern = QUOTA_TEXT.get(backend)
    lines = (text or '').strip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if pattern and pattern.search(lines[index]):
            return '\n'.join(lines[index:index + 3])
    return ''


def record_quota(run, message):
    seconds = agy_quota.reset_seconds(message)
    if seconds is not None:
        reset = dt.datetime.fromisoformat(run['utc'].replace('Z', '+00:00')) + dt.timedelta(seconds=seconds)
        reset = reset.isoformat()
    elif found := RESET_EPOCH.search(message):
        reset = dt.datetime.fromtimestamp(int(found.group(1)), dt.timezone.utc).isoformat()
    else:
        found = RESET_AT.search(message)
        reset = found.group(1).strip()[:120] if found else None
    row = {k: run.get(k) for k in ('run_id', 'model', 'lane', 'utc')}
    row['reset_time'] = reset
    append(runs_path().with_name('quota-hits.jsonl'), row)


def grade_fields(run_id, job, model, role, grade, reason, **extra):
    return dict(id='grade-' + run_id, run_id=run_id, date=dt.date.today().isoformat(), source_kind='everyday',
                job=job, model=canon(model) or model, role=role, grade=score_verdicts.validate(grade), note=reason, reason=reason, **extra)


def grade_cost(run_id, run=None, *, local=True):
    """Fail open even if the run ledger or the usage reader is unavailable."""
    try:
        if run is None and run_id:
            for candidate in read_jsonl(runs_path()):
                if candidate.get('run_id') == run_id:
                    run = candidate
        if not local and run and not run_costs.breakdown(run.get('token_usage')):
            return dict(api='unknown', plan='unknown', tokens={'reason': 'execution-host usage unavailable'})
        if run and is_probe(run):
            return dict(api='unknown', plan='unknown', tokens={'reason': 'probe'})
        return run_costs.cost_for(run)
    except Exception as exc:
        return dict(api='unknown', plan='unknown', tokens={'reason': 'grade cost failed ({})'.format(type(exc).__name__)})


def warn(error):
    print('run records: {}'.format(error), file=sys.stderr)


def open_run(row):
    """Persist before invoking the executor. Updates share the same run identity."""
    existing = next((r for r in read_jsonl(runs_path()) if r.get('run_id') == row['run_id']), None)
    if existing is not None:
        return existing
    row = dict(row, started_at=row['utc'], closed_at=None, wall_seconds=None,
               tokens=None, cost_usd=None, rc=None)
    if os.environ.get('RH_RUN_PURPOSE') == 'probe' or is_probe(row):
        row['purpose'] = 'probe'
    append(runs_path(), row)
    return row


def close_run(run_id, **fields):
    """Append the first close only, under the same lock as concurrent closers."""
    path = runs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        latest = None
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('run_id') == run_id:
                latest = row
        if latest is None or latest.get('closed_at'):
            return latest
        ended = fields.pop('closed_at', None) or utc_now()
        start = dt.datetime.fromisoformat(latest.get('started_at', latest['utc']).replace('Z', '+00:00'))
        if start.tzinfo is None:
            start = start.replace(tzinfo=dt.timezone.utc)
        elapsed = (dt.datetime.fromisoformat(ended.replace('Z', '+00:00')) - start).total_seconds()
        latest.update(fields, closed_at=ended, wall_seconds=fields.pop('wall_seconds', max(0, elapsed)))
        stream.write(json.dumps(latest, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        return latest
