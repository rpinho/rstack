"""Shared run-to-grade join for the leaderboard and its canary."""
from collections import defaultdict
import datetime as dt
import os
import re
import shlex
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
import run_records  # noqa: E402
import grade_ledgers  # noqa: E402

from model_slugs import canon
import score_verdicts


def outcome(grade):
    return {'pass': 'held', 'partial': 'partial', 'fail': 'overturned'}.get(grade, grade or 'ungraded')


def run_id(row):
    return row.get('run_id') or '{}@{}'.format(row['job'], row['utc'])


def utc(value):
    try:
        when = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


def job_key(value):
    return Path(value or '').name


def model_key(value):
    return canon(value) or value


def table(runs_file=None, ledgers=None, receipts=None):
    """Return (run, grade record or None) pairs and unmatched historical grades.

    A grade record retains its source path and line number. Legacy rows may use
    job name once each. Take the most recent matching run first for repeated jobs.
    """
    runs_file = Path(runs_file or run_records.runs_path())
    runs, legacy_counts = {}, defaultdict(int)
    for row in run_records.read_jsonl(runs_file):
        if row.get('job') and row.get('model') and utc(row.get('utc')):
            ident, old = run_id(row), not row.get('run_id')
            if old:
                legacy_counts[ident] += 1
                if legacy_counts[ident] > 1:
                    ident = '{}#{}'.format(ident, legacy_counts[ident])
            runs[ident] = dict(row, model=model_key(row['model']), legacy=old, run_id=ident)
    if ledgers is None:
        ledgers = grade_ledgers.ledgers(receipts or os.environ.get('RH_LAUNCH_RECEIPTS'))
    locations = [*ledgers, runs_file.with_name('everyday-grades.jsonl')]
    locations.extend(row['grade_ledger'] for row in runs.values() if row.get('grade_ledger'))
    locations.extend(Path(row['transcript']).parent / grade_ledgers.NAME for row in runs.values()
                     if row['legacy'] and row.get('transcript'))
    records = grade_ledgers.rows(dict.fromkeys(Path(p).expanduser().resolve() for p in locations),
                                 include_run_retractions=True)
    exact, legacy = {}, defaultdict(list)
    for record in records:
        grade = record[0]
        if grade.get('run_id'):
            exact[grade['run_id']] = record
        else:
            legacy[job_key(grade.get('job'))].append(record)
    pairs, used = [], set()
    for run in sorted(runs.values(), key=lambda r: utc(r['utc']), reverse=True):
        record = exact.get(run['run_id'])
        if record is None and run['legacy']:
            for candidate in reversed(legacy[job_key(run['job'])]):
                grade, path, line = candidate
                if (path, line) not in used and (
                        not grade.get('model') or model_key(grade['model']) == model_key(run['model'])):
                    record = candidate
                    break
        if record:
            used.add(record[1:])
        if run_records.is_probe(run):
            # A read-time disposition for old probes; no mutation of historical ledgers.
            row = dict(record[0] if record else {}, grade='void: probe', reason='probe')
            record = (row, record[1] if record else runs_file, record[2] if record else 0)
        pairs.append((run, record))
    historical = [r for candidates in legacy.values() for r in candidates if r[1:] not in used]
    return pairs, historical


def execution_host(run, grade, ledger):
    """Read only metadata and the launch header, never execute a check or contact a host."""
    host = run.get('host') or run.get('run_host') or grade.get('execution_host')
    if host:
        return str(host)
    root = grade_ledgers.receipts_dir(ledger)
    job = job_key(run.get('job') or grade.get('job'))
    if not job:
        return ''
    for row in run_records.read_jsonl(root / (job + '.log.remote.json')):
        if row.get('host'):
            return str(row['host'])
    for name in (job + '.log.selection.json', job + '.selection.json'):
        for row in run_records.read_jsonl(root / name):
            host = row.get('host') or row.get('run_host')
            if host:
                return str(host)
    # Historical launchers recorded --host here, before receipts carried it.
    try:
        with (root / (job + '.log')).open(errors='replace') as stream:
            for line in stream:
                found = re.match(r'^=== attempt \d+ model \S+ host ([A-Za-z0-9._-]+)\b', line)
                if found:
                    return found.group(1)
    except OSError:
        pass
    return ''


def legacy_incomplete(run, grade, ledger):
    """Reconstruct an old zero-exit/no-headers grader's workdir from raw launch files.

    Missing headers alone are not missing files. Require a directory named by
    the original spec/command, then check both files. Never run the command.
    """
    note = str(grade.get('reason') or grade.get('note') or '')
    if not (grade.get('auto') and grade.get('grader') == 'checks' and not grade.get('grade_host')
            and note.startswith('exit 0; Shipped line no; You asked line no')):
        return False
    directories = {str(d) for d in (grade.get('grade_dir'), run.get('workdir')) if d}
    job = Path(grade.get('job') or run.get('job') or '')
    stem = job if job.is_absolute() else grade_ledgers.receipts_dir(ledger) / job.name
    for suffix in ('.md', '.log.prompt'):
        try:
            text = Path(str(stem) + suffix).read_text(errors='replace')
        except OSError:
            continue
        found = re.search(r'(?im)(?:Working dir(?:ectory)?|Job directory|Your directory|Work dir|Directory)\s*:\s*`?([^\s`;,]+)', text)
        if found:
            directories.add(found.group(1).rstrip('.'))
    # Mirrored receipts predate workdir/host fields. The configured launch root
    # retains detached-host run.sh files. Match the full output path, never the
    # reused sweep basename (0-read, etc.).
    root = os.environ.get('MODEL_LAUNCH_ROOT')
    if root and job.is_absolute() and not directories:
        targets = {str(Path(str(job) + suffix).resolve()) for suffix in ('.last.md', '.last')}
        for script in Path(root).expanduser().glob(job.name + '/*/run.sh'):
            try:
                tokens = shlex.split(script.read_text())
            except (OSError, ValueError):
                continue
            outputs = {str(Path(t).resolve()) for t in tokens if t.startswith('/') and t.endswith(('.last.md', '.last'))}
            if targets & outputs and len(tokens) > 1 and tokens[0] == 'cd':
                directories.add(tokens[1])
    return bool(directories) and all(not (Path(d).expanduser() / name).is_file()
                                     for d in directories for name in ('STATUS.md', 'REPORT.md'))


def exclusion_reason(run, grade, ledger):
    """Reasons a recorded outcome cannot enter the public pass-rate denominator."""
    if run_records.is_probe(run) or run_records.is_probe(grade) or grade.get('grade') == 'void: probe':
        return 'probe'
    reason = str(grade.get('reason') or '') + '\n' + str(grade.get('note') or '')
    if grade.get('missing_files') or re.search(r'workdir incomplete:', reason, re.I) or legacy_incomplete(run, grade, ledger):
        return 'workdir incomplete'
    verdict = score_verdicts.migrate(grade.get('grade'), grade)
    # Explicit quota metadata, not an incidental mention of quota in a review.
    if (run.get('reason') == 'quota' or grade.get('grader') == 'quota' or verdict == 'void: quota'
            or any(str(grade.get(k) or '').strip().lower() == 'quota' for k in ('reason', 'note'))
            or re.search(r'AGY_QUOTA |RESOURCE[_ ]EXHAUSTED|Individual quota reached|usage_limit_reached|insufficient_quota', reason, re.I)):
        return 'quota'
    if verdict == 'fail':
        host = execution_host(run, grade, ledger)
        graded_on = grade.get('grade_host')
        if host and (not graded_on or str(graded_on).split('.')[0] != host.split('.')[0]):
            return 'remote controller grade'
    if verdict == 'harness_fail':
        return 'harness failure'
    if verdict.startswith('void:'):
        return 'void'
    return ''
