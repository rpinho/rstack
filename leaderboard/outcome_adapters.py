"""Receipt-linked outcome readers. Inputs are private; only observations reach the ranker.

No model is inferred from prose, job naming conventions, or a worker exit status.
JSONL is streamed and malformed input fails the run with its file and line number.
"""
import collections
import datetime as dt
import json
from pathlib import Path
import re


def rows(path):
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('expected an object')
                except ValueError as exc:
                    raise ValueError(f'{path}:{number}: {exc}') from exc
                yield row


def job_name(value):
    name = Path(str(value or '').strip('` ')).name
    for suffix in ('.log.selection.json', '.selection.json', '.md', '.log'):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def verdict(value):
    value = str(value or '').strip().upper()
    if value in ('HOLDS', 'HOLDS WITH CAVEATS', 'HELD', 'CONFIRMED', 'CAUGHT'):
        return 'held'
    if value in ('FAILS', 'OVERTURNED', 'MISSED', 'NOT HELD'):
        return 'overturned'
    return None


def day(row):
    value = row.get('day') or row.get('date') or row.get('utc') or row.get('revised') or row.get('created')
    return dt.date.fromisoformat(str(value)[:10]).isoformat() if value else None


class Receipts:
    def __init__(self, root):
        self.jobs = {}
        self.ambiguous = set()
        self.workdirs = {}
        self.designs = {}
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f'launch receipts root is not a directory: {root}')
        for path in sorted(root.rglob('*.selection.json')):
            row = json.loads(path.read_text())
            job = job_name(row.get('job') or path.name)
            entry = dict(row, path=str(path), job=job)
            # Duplicate copies are fine; conflicting identity must never pick a winner.
            if job in self.jobs and any(self.jobs[job].get(k) != row.get(k) for k in ('model', 'role', 'canonical')):
                self.ambiguous.add(job)
            self.jobs[job] = entry
            spec = path.with_name(job + '.md')
            text = spec.read_text() if spec.is_file() else ''
            workdir = row.get('workdir') or row.get('work_dir')
            if not workdir:
                match = re.search(r'(?im)^\s*(?:Working dir(?:ectory)?|Work dir|Directory)\s*:\s*`?([^`\n]+)', text)
                workdir = re.split(r'\s+\(', match.group(1).strip())[0].rstrip('.') if match else None
            if workdir:
                self.workdirs[job] = Path(workdir).expanduser()
            self.designs[job] = re.findall(r'([^\s`\"<>(),;]+/DESIGN(?:_v\d+)?\.md)', text)

    def job_for_artifact(self, value, role=None):
        if not value or str(value).startswith(('http:', 'https:')):
            return None
        path = Path(str(value)).expanduser()
        candidates = {name for name in self.jobs if name in path.parts}
        candidates.update(name for name, root in self.workdirs.items() if path == root or root in path.parents)
        if role:
            candidates = {name for name in candidates if self.jobs[name].get('role') == role}
        return next(iter(candidates)) if len(candidates) == 1 else None

    def design_for_artifact(self, value):
        producer = self.job_for_artifact(value)
        receipt = self.get(producer)
        if receipt and receipt.get('role') == 'design':
            return producer
        designs = {self.job_for_artifact(p) for p in self.designs.get(producer, [])}
        designs.discard(None)
        return next(iter(designs)) if len(designs) == 1 else None

    def get(self, job):
        name = job_name(job)
        return None if name in self.ambiguous else self.jobs.get(name)


class Outcomes:
    def __init__(self, receipts, canon, make_observation):
        self.receipts, self.canon, self.make = receipts, canon, make_observation
        self.stats = collections.defaultdict(lambda: dict(resolved=0, pending=0, unlinked=0))
        self.observations = {}

    def emit(self, kind, item, job, outcome, row, path, role=None):
        stats = self.stats[kind]
        if outcome is None:
            stats['pending'] += 1
            return
        receipt = self.receipts.get(job)
        model = self.canon(receipt.get('canonical') or receipt.get('model')) if receipt else None
        if not receipt or not model or not receipt.get('role'):
            stats['unlinked'] += 1
            return
        date = day(row)
        if not date:
            stats['pending'] += 1
            return
        selected_role = role or receipt['role']
        observation = self.make('receipt-' + kind, str(item), model, selected_role,
                                outcome, date, [path, receipt['path']], f'{kind}: {outcome}')
        observation.update(role=selected_role, job=receipt['job'], source_kind=kind, day=date)
        if observation['id'] not in self.observations:
            stats['resolved'] += 1
        self.observations[observation['id']] = observation

    def design(self, row, path, item):
        outcome = verdict(row.get('referee') or row.get('verdict') or row.get('outcome'))
        self.emit('design', item, row.get('design_job') or row.get('job') or self.receipts.design_for_artifact(row.get('link') or row.get('result_path')), outcome, row, path, 'design')

    def judge(self, row, path, item):
        # This is a later referee's disposition of the ruling, not the ruling itself.
        outcome = verdict(row.get('judge_outcome') or row.get('ruling_outcome') or row.get('outcome'))
        self.emit('judge', item, row.get('judge_job') or row.get('job'), outcome, row, path, 'judge')

    def review(self, row, path, item):
        plant = row.get('plant_caught')
        outcome = ('held' if plant else 'overturned') if type(plant) is bool else verdict(row.get('plant_outcome') or row.get('outcome'))
        self.emit('review', item, row.get('review_job') or row.get('referee_job') or row.get('job'), outcome, row, path, 'review')

    def referee_batch(self, row, path, item):
        planted, caught, fooled = (row.get(k, 0) for k in ('planted', 'caught', 'fooled'))
        if any(type(n) is not int or n < 0 for n in (planted, caught, fooled)) or caught + fooled > planted:
            raise ValueError(f'{path}: invalid planted outcome counts')
        if not planted:
            return
        outcome = 'overturned' if fooled else 'held' if caught == planted else None
        job = row.get('review_job') or row.get('referee_job') or row.get('job') or self.receipts.job_for_artifact(row.get('file'))
        self.emit('review', item, job, outcome, row, path, 'review')

    def ideation(self, history, path, item):
        first, latest = history[0], history[-1]
        tested = any(r.get('status') in ('testing', 'shipped') or r.get('result_path') for r in history)
        fault = latest.get('close_kind') in ('prior-art', 'duplicate', 'rule-blocked')
        if not latest.get('close_kind'):
            fault = bool(re.search(r'prior art|duplicate|already known|not new', latest.get('closed_reason', ''), re.I))
        outcome = 'held' if tested else 'overturned' if latest.get('status') == 'closed' and fault else None
        producer = first.get('proposer_job') or first.get('design_job') or first.get('job') or self.receipts.job_for_artifact(first.get('source_path'))
        self.emit('ideation', item, producer, outcome, latest, path, 'ideation')

    def pull_request(self, row, path, item):
        merged = row.get('merged_at') or row.get('merged') is True
        closed = str(row.get('state', '')).lower() == 'closed'
        outcome = 'held' if merged else 'overturned' if closed else None
        dated = dict(row, day=row.get('merged_at') or row.get('closed_at') or row.get('day') or row.get('utc') or row.get('date'))
        producer = row.get('opened_by_job') or row.get('job')
        # A spec mentioning a PR is not proof that it opened it. Only explicit opening metadata qualifies.
        self.emit('pull-request', item, producer, outcome, dated, path)

    def taste(self, history, path, item):
        for index, decision in enumerate(history):
            if decision.get('event') not in ('promote', 'close') or decision.get('mechanical'):
                continue
            later = history[index + 1:]
            outcome = None
            if decision['event'] == 'promote':
                end = next((r for r in later if r.get('status') in ('closed', 'shipped')), None)
                if end and end['status'] == 'shipped':
                    outcome = 'held'
                elif end and (end.get('close_kind') in ('prior-art', 'duplicate', 'rule-blocked') or (not end.get('close_kind') and re.search(r'prior art|duplicate|already known|not new', end.get('closed_reason', ''), re.I))):
                    outcome = 'overturned'
            elif any(r.get('status') in ('new', 'testing', 'shipped') for r in later):
                outcome = 'overturned'
            else:
                date = day(decision)
                if date and (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(date)).days >= 14:
                    outcome = 'held'
            job = decision.get('decider_job') or decision.get('decision_job') or decision.get('job') or self.receipts.job_for_artifact(decision.get('decider_note') or decision.get('result_path'), role='taste') or decision.get('decided_by')
            self.emit('taste', f"{item}/{decision['event']}/{index}", job, outcome, decision, path, 'taste')

    def read_markdown(self, path):
        text = path.read_text()
        # Only labelled outcome fields qualify. Free-form mentions are not verdicts.
        fields = {}
        for line in text.splitlines():
            match = re.fullmatch(r'\s*([A-Za-z][A-Za-z _-]*):\s*(.*?)\s*', line)
            if match:
                fields[match.group(1).lower().replace(' ', '_').replace('-', '_')] = match.group(2).strip('`* ')
        outcome = fields.get('verdict') or fields.get('audit') or fields.get('outcome')
        if not outcome:
            first = text.splitlines()[0].strip() if text.splitlines() else ''
            outcome = first if verdict(first) else None
        date = fields.get('date') or fields.get('utc')
        if not date:
            match = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', text[:1500])
            date = match.group(1) if match else None
        row = dict(fields, date=date, verdict=outcome)
        item = str(path)
        if fields.get('design_job'):
            self.design(row, str(path), item)
        if fields.get('judge_job'):
            self.judge(row, str(path), item)
        if fields.get('review_job') or fields.get('referee_job'):
            self.review(row, str(path), item)
        # An unlabelled referee verdict still counts as unlinked, never as the author's score.
        if outcome and not any(fields.get(k) for k in ('design_job', 'judge_job', 'review_job', 'referee_job')):
            self.design(row, str(path), item)

    def read(self, path):
        path = Path(path)
        if path.suffix == '.md':
            self.read_markdown(path)
            return
        if path.suffix == '.json':
            data = json.loads(path.read_text())
            source_rows = [dict(r, date=r.get('date') or data.get('fetched')) for r in data['prs']] if isinstance(data, dict) and 'prs' in data else [data]
        else:
            source_rows = rows(path)
        ideas = collections.defaultdict(list)
        for number, row in enumerate(source_rows, 1):
            item = row.get('id') or row.get('url') or f'{path}:{number}'
            kind = row.get('source_kind') or row.get('outcome_kind')
            if path.name == 'IDEAS.jsonl':
                ideas[row['id']].append(row)
                continue
            if path.name == 'REFEREE.jsonl':
                self.referee_batch(row, str(path), row.get('batch') or item)
            elif kind == 'ideation':
                self.ideation([row], str(path), item)
            elif row.get('design_job') and row.get('judge_job'):
                self.design(row, str(path), item)
                self.judge(row, str(path), item)
            elif kind == 'judge' or row.get('judge_job'):
                self.judge(row, str(path), item)
            elif kind in ('review', 'referee') or 'plant_caught' in row:
                self.review(row, str(path), item)
            elif kind in ('pull-request', 'pr') or 'merged_at' in row or 'opened_by_job' in row:
                self.pull_request(row, str(path), item)
            elif kind == 'design' or path.name == 'RESULTS.jsonl' or 'design_job' in row:
                self.design(row, str(path), item)
        for idea, history in ideas.items():
            self.ideation(history, str(path), f'{path.parent.name}/{idea}')
            self.taste(history, str(path), f'{path.parent.name}/{idea}')


def collect(evidence_root, receipts_root, canon, make_observation, outcomes_root=None, upstream_root=None):
    reader = Outcomes(Receipts(receipts_root), canon, make_observation)
    paths = set()
    if evidence_root:
        lanes = Path(evidence_root) / 'lanes'
        if not lanes.is_dir():
            raise ValueError(f'evidence root has no lanes directory: {evidence_root}')
        for name in ('IDEAS.jsonl', 'RESULTS.jsonl', 'REFEREE.jsonl', '.upstream-prs.json'):
            paths.update(lanes.glob('*/' + name))
    if outcomes_root:
        root = Path(outcomes_root)
        if not root.is_dir():
            raise ValueError(f'outcomes root is not a directory: {root}')
        paths.update(root.glob('*.jsonl'))
        paths.update(root.glob('*.outcomes.json'))
        paths.update(root.glob('*/*.outcomes.jsonl'))
        paths.update(root.glob('*/*.outcomes.json'))
        for pattern in ('*.verdict.md', '*/referee*.md', '*/ledger_verdict.md'):
            paths.update(root.glob(pattern))
    if upstream_root:
        root = Path(upstream_root)
        if not root.is_dir():
            raise ValueError(f'upstream root is not a directory: {root}')
        paths.update(root.rglob('*.json'))
        paths.update(root.rglob('*.jsonl'))
    for path in sorted(paths):
        reader.read(path)
    return list(reader.observations.values()), dict(reader.stats)
