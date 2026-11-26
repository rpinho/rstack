#!/usr/bin/env python3
"""Read agy driver outputs without changing driver sessions or lane files."""
from collections import defaultdict
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from run_grades import grade_ledgers, run_records, table, utc, job_key

DRIVER = re.compile(r'\bagy-[\w.-]+\b')
MODEL = re.compile(r'\bgemini-\d[\w.-]+-(?:low|medium|high|xhigh|max)\b', re.I)
SHA = re.compile(r'\b[0-9a-f]{7,40}\b')
LOCAL = re.compile(r'(?:~/|/Users/)[^\s`()<>,;]+')
GITHUB = re.compile(r'https://github\.com/[\w.-]+/([\w.-]+)')
AGY_AUTHOR = re.compile(r'\bagy\b|\bGemini\b|\bAntigravity\b', re.I)


def command(*args):
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ''


def pane_paths():
    paths = defaultdict(set)
    for line in command('tmux', 'list-panes', '-a', '-F', '#{session_name}\t#{pane_current_path}').splitlines():
        name, sep, path = line.partition('\t')
        if sep and DRIVER.fullmatch(name):
            paths[name].add(Path(path))
    return paths


def lane_repos(lane, evidence, panes):
    paths = set(panes) | {lane}
    paths.update(Path(path.rstrip('.')).expanduser() for path in LOCAL.findall(evidence))
    # Public links name a repository. Check for that checkout in the ordinary
    # local work roots without a repository crawl or a network lookup.
    roots = {Path.home() / 'dev', *panes}
    receipts = os.environ.get('RH_LAUNCH_RECEIPTS')
    if receipts:
        roots.add(Path(receipts).expanduser().parent)
    for name in GITHUB.findall(evidence):
        paths.update(root / name for root in roots)
    repos = set()
    for path in paths:
        path = path if path.is_dir() else path.parent
        if path.is_dir():
            repo = command('git', '-C', str(path), 'rev-parse', '--show-toplevel')
            if repo:
                repos.add(repo)
    return repos


def status_time(path):
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)


def matches_job(text, job):
    return bool(re.search(r'(?<![\w-])' + re.escape(job) + r'(?![\w-])', text))


def result_grade(row):
    verdict = str(row.get('referee') or row.get('outcome') or '').lower()
    if verdict.startswith('holds') or verdict in ('pass', 'merged', 'pushed'):
        return 'pass', 'lane result records ' + verdict
    if verdict in ('fails', 'fail', 'refuted', 'overturned'):
        return 'fail', 'lane result records ' + verdict
    return 'void: no downstream verdict', 'lane result has no downstream verdict'


def launch_receipts():
    root = os.environ.get('RH_LAUNCH_RECEIPTS')
    directories = {p.parent for p in grade_ledgers.ledgers(root) if p.name == grade_ledgers.NAME}
    if root:
        directories.add(Path(root).expanduser())
    for directory in directories:
        for path in directory.glob('*.log.selection.json'):
            try:
                row = json.loads(path.read_text(errors='replace'))
            except (OSError, ValueError):
                continue
            if isinstance(row, dict) and row.get('job') and utc(row.get('utc')):
                yield row, path


def collect(lanes, pairs, previous, now):
    panes = pane_paths()
    cutoff = now - dt.timedelta(hours=24)
    existing = {run['run_id']: run for run, _ in pairs if run.get('backend') == 'agy-driver'}
    markers = dict(previous)
    events = {}
    receipts = list(launch_receipts())
    launched = {}
    for run, record in pairs:  # newest attempts first
        if run.get('backend') != 'agy-driver':
            launched.setdefault(run.get('launch_group') or run['run_id'], (run, record))
    known_launches = {(row['driver'], row['downstream_launch']) for row in existing.values()
                      if row.get('downstream_launch')}

    for status in sorted(Path(lanes).glob('*/DRIVER_STATUS.md')):
        try:
            text, stamp = status.read_text(errors='replace'), status_time(status)
        except OSError:
            continue
        lane = status.parent.name
        found = DRIVER.search(text)
        driver = found.group() if found else 'agy-' + lane
        model_match = MODEL.search(text)
        # Live status files name the Neon route; when no tier is given the
        # workstation's driver route is Neon High.
        model = model_match.group().lower() if model_match else 'gemini-4-neon-high'
        fingerprint = hashlib.sha256(text.encode()).hexdigest()
        checkpoint = previous.get(driver, {})
        since = utc(checkpoint.get('utc')) or cutoff
        revision = fingerprint != checkpoint.get('fingerprint')
        emitted = []

        def event(kind, key, when, evidence, grade, reason, **fields):
            ident = 'driver-' + hashlib.sha256(f'{driver}/{kind}/{key}'.encode()).hexdigest()[:32]
            row = existing.get(ident) or dict(
                run_id=ident, utc=when.isoformat(), job=f'{driver}/{kind}/{key}', lane=lane, model=model,
                effort=model.rsplit('-', 1)[-1], role='batch', backend='agy-driver', driver=driver,
                transcript=str(evidence), rc=None, **fields)
            if ident not in existing and (when > since or (revision and when == since)):
                emitted.append(when)
            grade_row = run_records.grade_fields(ident, row['job'], row['model'], row['role'], run_records.score_verdicts.migrate(grade, dict(reason=reason)), reason)
            grade_row['date'] = utc(row['utc']).date().isoformat()
            events[ident] = row, grade_row

        evidence = [text]
        ledger = status.with_name('RESULTS.jsonl')
        for index, row in enumerate(run_records.read_jsonl(ledger), 1):
            when = utc(row.get('utc'))
            attributed = row.get('driver')
            if not when or when < min(since, cutoff) or (attributed and attributed != driver):
                continue
            link = str(row.get('link') or '')
            evidence.append(link)
            event('result', str(index), when, ledger, *result_grade(row))

        def attributed(row):
            source = row.get('driver')
            return source == driver if source else matches_job(text, job_key(row['job']))

        for group, (run, raw_grade) in launched.items():
            when = utc(run['utc'])
            if (driver, group) not in known_launches and not (when >= min(since, cutoff) and attributed(run)):
                continue
            grade = raw_grade[0]['grade'] if raw_grade else 'ungraded'
            reason = 'downstream job: ' + (grade if raw_grade else 'awaiting grade')
            if grade == 'ungraded' and raw_grade:
                reason += ' (' + (raw_grade[0].get('reason') or raw_grade[0].get('note') or 'no verdict') + ')'
            event('launch', group, when, run.get('transcript', status), grade, reason, downstream_launch=group)

        for receipt, path in receipts:
            group = receipt.get('launch_group')
            if group and group not in launched and attributed(receipt):
                when = utc(receipt['utc'])
                if when >= min(since, cutoff):
                    event('launch', group, when, path, 'ungraded', 'downstream job: awaiting grade',
                          downstream_launch=group)

        named = set(SHA.findall(' '.join(evidence)))
        repos = lane_repos(status.parent, ' '.join(evidence), panes[driver])
        commits = {}
        for repo in sorted(repos):
            listing = command('git', '-C', repo, 'log', '--all', '--max-count=500',
                              '--since=' + min(since, cutoff).isoformat(),
                              '--format=%H%x09%cI%x09%an%x09%(trailers:key=Co-authored-by,valueonly,separator=%x20)')
            for line in listing.splitlines():
                parts = line.split('\t', 3)
                if len(parts) < 3:
                    continue
                oid, date, author = parts[:3]
                if any(oid.startswith(sha) for sha in named) or AGY_AUTHOR.search(' '.join(parts[2:])):
                    commits[oid] = repo, utc(date)
        for row in existing.values():
            if row.get('driver') == driver and row.get('commit'):
                commits.setdefault(row['commit'], (row['transcript'], utc(row['utc'])))
        for oid, (repo, when) in commits.items():
            if not when:
                continue
            pushed = bool(command('git', '-C', repo, 'for-each-ref', '--count=1', '--contains=' + oid,
                                  '--format=%(refname)', 'refs/remotes'))
            grade, reason = ('pass', 'commit reachable from a remote-tracking ref') if pushed else (
                'ungraded', 'local commit awaiting push or merge')
            event('commit', oid, when, repo, grade, reason, commit=oid)

        if revision:
            if stamp >= since and not any(since <= when <= stamp for when in emitted):
                event('round', fingerprint, stamp, status, 'partial', 'no output')
            markers[driver] = dict(fingerprint=fingerprint, utc=stamp.isoformat())

    return events, markers


def main():
    runs = run_records.runs_path()
    lanes = Path(os.environ.get('RH_EVIDENCE_ROOT') or Path.home() / '.local/share/research-harness') / 'lanes'
    runs.parent.mkdir(parents=True, exist_ok=True)
    state = runs.with_name('driver-grades-state.json')
    with state.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            previous = json.loads(state.read_text()) if state.is_file() else {}
            pairs, _ = table(runs)
            events, markers = collect(lanes, pairs, previous, dt.datetime.now(dt.timezone.utc))
            seen = {run['run_id']: record[0] if record else {} for run, record in pairs}
            for ident, (row, grade) in events.items():
                if ident not in seen:
                    run_records.append(runs, row)
                old = seen.get(ident, {})
                if (old.get('grade'), old.get('reason')) != (grade['grade'], grade['reason']):
                    run_records.append(run_records.grades_path(), grade)
            if markers != previous:
                pending = state.with_suffix('.tmp')
                pending.write_text(json.dumps(markers) + '\n')
                pending.replace(state)
        except (OSError, ValueError) as exc:
            run_records.warn(exc)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
