#!/usr/bin/env python3
"""The two-way grades feed between the owner's machines (11-22).

Ricardo: "use the grades from the mini here as well... and vice versa... We just combine them together."
Each machine sends a full snapshot of its graded model rows as one handoff item: `<stamp>-grades-feed.md`
(front matter with `type: grades-feed`) and a sibling folder `<stamp>-grades-feed/grades.tsv` with exactly
COLUMNS and nothing else. The receiver replaces that machine's previous snapshot, never appends.

Counting rule (both sides): everyday and judge rows count toward the everyday ranking, bench rows only as
bench, void and harness_fail rows never. A model id that resolves to no known model is skipped and reported.

    grades_feed.py ingest --inbox DIR --store DIR [--me mini] [--push HOST]
        every `type: grades-feed` item from another machine in DIR: validated, stored as DIR/<machine>.tsv
        (replacing the old one), then the item and its folder are moved to DIR/processed/.
    grades_feed.py rows --ledger evaluations.jsonl [--machine mini]
        this machine's rows as feed TSV on stdout, from the model scorer's own ledger.
    grades_feed.py stage --tsv FILE --staging DIR [--machine mini] [--to laptop]
        wraps a TSV as a handoff item in DIR and prints the manifest path (send it with handoff-send).
    grades_feed.py daily --inbox DIR --store DIR --ledger PATH --staging DIR [--rows-from HOST] [--push HOST]
        the standing rule, once a day: ingest, then this machine's snapshot staged and sent through
        handoff-send (which runs the handoff gate). --rows-from reads the ledger on the scorer's host.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

COLUMNS = ('date', 'machine', 'model', 'task_class', 'role', 'verdict', 'harness_fail')
MACHINES = ('laptop', 'mini')
CLASSES = ('everyday', 'judge', 'bench')
VERDICTS = ('pass', 'partial', 'fail', 'void')
POINTS = {'pass': 1.0, 'partial': 0.5, 'fail': 0.0}
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MODEL = re.compile(r'^[a-z0-9][a-z0-9._/-]{0,79}$')     # an id, never prose: no spaces, no capitals
ROLE = re.compile(r'^[a-z][a-z-]{0,23}$|^$')
# The sender's role words onto the scorer's roles. A judge row without a role is review work; any other row
# without a known role word is general agent work (builder).
ROLE_MAP = {'build': 'builder', 'builder': 'builder', 'session': 'builder',
            'review': 'review', 'referee': 'review', 'judge': 'review', 'audit': 'review', 'consult': 'ideation',
            'ideation': 'ideation', 'chore': 'mechanical', 'mechanical': 'mechanical', 'batch': 'batch',
            'cheap': 'cheap', 'writing': 'writing', 'taste': 'taste', 'design': 'taste', 'biology': 'biology'}


def parse(text, source='feed'):
    """Validated rows (dicts) of one grades.tsv; ValueError naming the line for anything else."""
    lines = text.splitlines()
    if not lines or tuple(lines[0].split('\t')) != COLUMNS:
        raise ValueError('{}: the header must be exactly: {}'.format(source, '\\t'.join(COLUMNS)))
    rows = []
    for number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        cells = line.split('\t')
        if len(cells) != len(COLUMNS):
            raise ValueError('{}:{}: {} cells, expected {}'.format(source, number, len(cells), len(COLUMNS)))
        row = dict(zip(COLUMNS, (c.strip() for c in cells)))
        checks = (DATE.match(row['date']), row['machine'] in MACHINES, MODEL.match(row['model']),
                  row['task_class'] in CLASSES, ROLE.match(row['role']), row['verdict'] in VERDICTS,
                  row['harness_fail'] in ('0', '1'))
        if not all(checks):
            bad = [c for c, ok in zip(('date', 'machine', 'model', 'task_class', 'role', 'verdict', 'harness_fail'),
                                      checks) if not ok]
            raise ValueError('{}:{}: not a feed value in {} (free text is refused)'.format(source, number, ', '.join(bad)))
        rows.append(row)
    return rows


def counts(row):
    """('everyday' | 'bench' | None, points) under the counting rule."""
    if row['harness_fail'] == '1' or row['verdict'] == 'void':
        return None, None
    return ('bench' if row['task_class'] == 'bench' else 'everyday'), POINTS[row['verdict']]


def role_for(row):
    return ROLE_MAP.get(row['role']) or ('review' if row['task_class'] == 'judge' else 'builder')


def snapshots(spec=None):
    """Rows of every stored snapshot named in MODEL_GRADES_FEED (colon-separated paths); unreadable or invalid
    files are skipped and reported on stderr, never raised (RULE #1)."""
    out = []
    for part in (spec if spec is not None else os.environ.get('MODEL_GRADES_FEED', '')).split(':'):
        path = Path(part.strip()).expanduser() if part.strip() else None
        if not path or not path.is_file():
            continue
        try:
            out.extend(parse(path.read_text(), str(path)))
        except (OSError, ValueError) as exc:
            print('grades-feed: skipped {}: {}'.format(path, exc), file=sys.stderr)
    return out


def manifest(path):
    """{key: value} of an item's front matter."""
    head = {}
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        return head
    if text.startswith('---'):
        for line in text.split('\n---', 1)[0].splitlines()[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                head[k.strip()] = v.strip()
    return head


def ingest(inbox, store, me='mini', push=None):
    """Every grades-feed item from another machine in `inbox`: validated, stored, filed. Returns report lines.
    An invalid item stays in the inbox, named in the report."""
    inbox, store = Path(inbox).expanduser(), Path(store).expanduser()
    report = []
    for md in sorted(inbox.glob('*.md')):
        head = manifest(md)
        if head.get('type') != 'grades-feed':
            continue
        sender = head.get('from', '')
        folder = md.with_suffix('')
        tsv = folder / 'grades.tsv'
        try:
            if sender == me or sender not in MACHINES:
                raise ValueError('from: {!r} is this machine or not a known machine'.format(sender))
            rows = parse(tsv.read_text(), str(tsv))
            others = {r['machine'] for r in rows} - {sender}
            if others:
                raise ValueError('rows for {} in a feed from {}'.format(', '.join(sorted(others)), sender))
        except (OSError, ValueError) as exc:
            report.append('REFUSED {}: {}'.format(md.name, exc))
            continue
        store.mkdir(parents=True, exist_ok=True)
        target = store / (sender + '.tsv')
        tmp = target.with_suffix('.tsv.tmp')
        tmp.write_text(tsv.read_text())
        os.replace(tmp, target)                    # a full snapshot: the newer one replaces the older
        if push:
            subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', push, 'mkdir -p ' + str(store)],
                           capture_output=True, timeout=60)
            r = subprocess.run(['scp', '-q', '-p', '-o', 'BatchMode=yes', str(target), '{}:{}'.format(push, target)],
                               capture_output=True, timeout=120)
            if r.returncode:
                report.append('WARNING {}: stored here, but the copy to {} failed'.format(md.name, push))
        processed = inbox / 'processed'
        processed.mkdir(exist_ok=True)
        for part in (md, folder):
            if part.exists():
                shutil.move(str(part), str(processed / part.name))
        report.append('ingested {}: {} rows from {} -> {}'.format(md.name, len(rows), sender, target))
    return report


def ledger_rows(ledger, machine='mini'):
    """This machine's feed rows from the model scorer's ledger (evaluations.jsonl): everyday, judge and bench."""
    rows = []
    try:
        lines = Path(ledger).expanduser().read_text().splitlines()
    except OSError:
        return rows
    data = [json.loads(l) for l in lines if l.strip()]
    retired = {r.get('supersedes') for r in data if r.get('supersedes')}
    judge = {'review', 'judge', 'audit', 'referee'}
    for r in data:
        if r.get('id') in retired or r.get('pick_role') == 'corrections' or not r.get('pick_role'):
            continue
        model, outcome = str(r.get('model') or ''), r.get('outcome')
        if not MODEL.match(model):
            continue
        verdict = {'held': 'pass', 'pass': 'pass', 'partial': 'partial', 'overturned': 'fail', 'fail': 'fail'}.get(outcome, 'void')
        bench = bool(r.get('bench')) or r.get('source') == 'receipt-review' or str(r.get('task_family', '')).startswith('bench')
        task_class = 'bench' if bench else 'judge' if r['pick_role'] in judge else 'everyday'
        role = r['pick_role'] if ROLE.match(r['pick_role']) else ''
        rows.append(dict(date=str(r.get('date', ''))[:10], machine=machine, model=model, task_class=task_class,
                         role=role, verdict=verdict, harness_fail='1' if outcome == 'harness_fail' else '0'))
    return [r for r in rows if DATE.match(r['date'])]


def tsv(rows):
    return '\t'.join(COLUMNS) + '\n' + ''.join('\t'.join(r[c] for c in COLUMNS) + '\n' for r in rows)


def stage(tsv_path, staging, machine='mini', to='laptop', now=None):
    """A handoff item in `staging` holding the TSV; returns the manifest path."""
    rows = parse(Path(tsv_path).read_text(), str(tsv_path))
    if {r['machine'] for r in rows} - {machine}:
        raise ValueError('a {} feed may hold only {} rows'.format(machine, machine))
    now = now or dt.datetime.now()
    stamp = now.strftime('%Y%m%d-%H%M') + '-grades-feed'
    staging = Path(staging).expanduser()
    folder = staging / stamp
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'grades.tsv').write_text(tsv(rows))
    md = staging / (stamp + '.md')
    md.write_text('\n'.join((
        '---', 'from: ' + machine, 'to: ' + to, 'type: grades-feed',
        'purpose: Daily model grades feed ({} rows) for the combined leaderboard'.format(machine),
        'ip_clean: yes',
        'sanitized_by: grades-feed (aggregate rows only: date, machine, model id, task class, role word, verdict, harness flag)',
        '---', '',
        '# Grades feed from the {} ({})'.format(machine, now.date().isoformat()), '',
        'Full snapshot of the {}\'s graded model rows, {} rows, in `{}/grades.tsv`. Columns: {}. No task text.'.format(
            machine, len(rows), stamp, ', '.join(COLUMNS)),
        'Dates are observation dates. A weekly tally needs explicit date bounds and counts pass, partial and fail separately. '
        'For everyday work, use everyday and judge rows with harness_fail=0 and a pass, partial or fail verdict. '
        'The leaderboard uses a run-based window and half credit for partial grades.',
        'Ingest it as the {} snapshot under the standing grades-feed rule (replace the previous one).'.format(machine),
        '')))
    return md


def daily(inbox, store, ledger, staging, me='mini', to='laptop', rows_from=None, push=None, send='handoff-send'):
    """Report lines for one day's run. Never raises: each step that fails says so and the next one runs."""
    report = []
    try:
        report += ingest(inbox, store, me, push)
    except OSError as exc:
        report.append('ingest failed: {}'.format(exc))
    try:
        if rows_from:
            remote = '~/.local/share/research-harness/leaderboard/grades_feed.py'
            r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', rows_from,
                                'python3 {} rows --ledger {} --machine {}'.format(remote, ledger, me)],
                               capture_output=True, text=True, timeout=300)
            if r.returncode:
                raise OSError('rows from {} exited {}: {}'.format(rows_from, r.returncode, r.stderr.strip()[:200]))
            text = r.stdout
        else:
            text = tsv(ledger_rows(ledger, me))
        rows = parse(text, 'export')
        staging = Path(staging).expanduser()
        staging.mkdir(parents=True, exist_ok=True)
        tmp = staging / '.grades-feed.tsv'
        tmp.write_text(text)
        md = stage(tmp, staging, me, to)
        tmp.unlink()
        report.append('staged {} with {} rows'.format(md.name, len(rows)))
        if shutil.which(send):
            r = subprocess.run([send, str(md)], capture_output=True, text=True, timeout=300)
            report.append((r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip()
                          else '{} exited {}'.format(send, r.returncode))
        else:
            report.append('{} not found: the item stays in {}'.format(send, staging))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.append('export failed: {}'.format(exc))
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('ingest')
    i.add_argument('--inbox', required=True)
    i.add_argument('--store', required=True)
    i.add_argument('--me', default='mini')
    i.add_argument('--push')
    r = sub.add_parser('rows')
    r.add_argument('--ledger', required=True)
    r.add_argument('--machine', default='mini')
    s = sub.add_parser('stage')
    s.add_argument('--tsv', required=True)
    s.add_argument('--staging', required=True)
    s.add_argument('--machine', default='mini')
    s.add_argument('--to', default='laptop')
    d = sub.add_parser('daily')
    for k in ('--inbox', '--store', '--ledger', '--staging'):
        d.add_argument(k, required=True)
    d.add_argument('--me', default='mini')
    d.add_argument('--to', default='laptop')
    d.add_argument('--rows-from')
    d.add_argument('--push')
    a = p.parse_args(argv)
    try:
        if a.cmd == 'ingest':
            for line in ingest(a.inbox, a.store, a.me, a.push):
                print(line)
        elif a.cmd == 'daily':
            for line in daily(a.inbox, a.store, a.ledger, a.staging, a.me, a.to, a.rows_from, a.push):
                print(line)
        elif a.cmd == 'rows':
            sys.stdout.write(tsv(ledger_rows(a.ledger, a.machine)))
        else:
            print(stage(a.tsv, a.staging, a.machine, a.to))
        return 0
    except (OSError, ValueError) as exc:
        print('grades-feed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
