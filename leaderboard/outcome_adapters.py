"""Receipt-linked outcome readers. Inputs are private; only observations reach the ranker.

No model is inferred from prose, job naming conventions, or a worker exit status.
JSONL is streamed and malformed input fails the run with its file and line number; the everyday
grade ledgers are the exception: a malformed line there is skipped (grade_ledgers.py, RULE #1).
"""
import collections
import functools
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import shlex


def _grade_ledgers():
    spec = importlib.util.spec_from_file_location('grade_ledgers', Path(__file__).with_name('grade_ledgers.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


grade_ledgers = _grade_ledgers()


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
    for suffix in ('.log.selection.json', '.selection.json', '.log.rcmd', '.last.md', '.md', '.log', '.json'):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def verdict(value):
    value = str(value or '').strip().upper()
    value = re.split(r'\s*\(', value, maxsplit=1)[0].strip()
    if value in ('HOLDS', 'HOLDS WITH CAVEATS', 'HELD', 'CONFIRMED', 'CAUGHT'):
        return 'held'
    if value in ('PARTIAL', 'PARTIALLY HOLDS'):
        return 'partial'
    if value in ('FAILS', 'OVERTURNED', 'MISSED', 'NOT HELD'):
        return 'overturned'
    return None


def day(row):
    value = row.get('day') or row.get('date') or row.get('utc') or row.get('revised') or row.get('created')
    return dt.date.fromisoformat(str(value)[:10]).isoformat() if value else None


class Receipts:
    """Receipt > saved launch command > launching transcript tool call.

    Only configured roots are read. Job prose supplies artifact links, never
    model identity. Conflicts at the best available rank remain unlinked.
    """
    PRIORITY = {'receipt': 0, 'launch-command': 1, 'transcript-call': 2}

    def __init__(self, root, launch_root=None, transcript_root=None):
        self.jobs, self.workdirs, self.specs, self.designs = {}, {}, {}, {}
        self.ambiguous = set()
        self.aliases = collections.defaultdict(set)
        self.outputs = collections.defaultdict(set)
        self.references = collections.defaultdict(set)
        self._roles = {}
        root = Path(root)
        self.root = root
        self.artifact_root = root.parent
        if not root.is_dir():
            raise ValueError(f'launch receipts root is not a directory: {root}')
        for path in sorted(root.rglob('*.selection.json')):
            row = json.loads(path.read_text())
            job = job_name(row.get('job') or path.name)
            spec = path.with_name(job + '.md')
            if not spec.is_file():
                spec = path.with_name(job + '.log.prompt')
            self.add(job, row, path, 'receipt', spec.read_text() if spec.is_file() else '')
        commands = set(root.glob('*.rcmd'))
        if launch_root:
            launch_root = Path(launch_root)
            if not launch_root.is_dir():
                raise ValueError(f'launch records root is not a directory: {launch_root}')
            commands.update(launch_root.glob('*/*/run.sh'))
            commands.update(launch_root.glob('*.rcmd'))
        for path in sorted(commands):
            command = self.command(path.read_text())
            if not command:
                continue
            job = command.pop('job', None) or (path.parent.parent.name if path.name == 'run.sh' else job_name(path.name))
            prompt = path.with_name('prompt') if path.name == 'run.sh' else path.with_suffix('.prompt')
            if path.name == 'run.sh':
                try:
                    command['utc'] = dt.datetime.strptime(path.parent.name.split('-')[0], '%Y%m%dT%H%M%S').isoformat()
                except ValueError:
                    pass
            self.add(job, command, path, 'launch-command', prompt.read_text() if prompt.is_file() else '')
        if transcript_root:
            transcript_root = Path(transcript_root)
            if not transcript_root.is_dir():
                raise ValueError(f'transcript root is not a directory: {transcript_root}')
            for path in sorted(transcript_root.rglob('*.jsonl')):
                for row in rows(path):
                    self.transcript(row, path)
        for job, text in self.specs.items():
            for value in re.findall(r'(?:~?/|/)[^\s`\"<>(),;]+', text):
                linked = self.job_for_artifact(value.rstrip('.:'))
                if linked and linked != job:
                    self.references[job].add(linked)

    @staticmethod
    def command(text):
        """Parse executor argv, excluding echoed commands and quoted prompts."""
        workdir = None
        for line in text.splitlines():
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if not tokens or tokens[0] in ('echo', 'printf'):
                continue
            if tokens[0] == 'cd' and len(tokens) > 1:
                workdir = tokens[1]
            for i, token in enumerate(tokens):
                executable = Path(token).name
                executor = ((executable == 'claude' and '-p' in tokens[i + 1:])
                            or (executable == 'codex' and tokens[i + 1:i + 2] == ['exec'])
                            or executable == 'agent_executor.py')
                if not executor:
                    continue
                options = tokens[i + 1:]
                def option(*names):
                    for n, value in enumerate(options):
                        if value in names and n + 1 < len(options):
                            return options[n + 1]
                        for name in names:
                            if value.startswith(name + '='):
                                return value[len(name) + 1:]
                    return None
                model = option('--model', '-m')
                if model:
                    workdir = option('--directory', '--cd', '--cwd') or workdir
                    job = next((v.split('=', 1)[1] for v in tokens[:i] if v.startswith('RH_JOB=')), None)
                    return dict(model=model, workdir=workdir, job=job)
        return None

    def transcript(self, row, path):
        payload = row.get('payload', {})
        if row.get('type') == 'response_item' and payload.get('type') == 'function_call':
            args = payload.get('arguments', {})
            if isinstance(args, str):
                args = json.loads(args)
            row = dict(message=dict(role='assistant', content=[dict(
                type='tool_use', name=payload.get('name', '').split('.')[-1], input=args)]))
        message = row.get('message', row)
        if message.get('role', row.get('type')) != 'assistant':
            return
        content = message.get('content', [])
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            args = block.get('input', {})
            if block.get('name') in ('Bash', 'exec_command'):
                command = self.command(args.get('command') or args.get('cmd') or '')
                if command and command.get('workdir'):
                    job = command.pop('job', None) or Path(command['workdir']).name
                    self.add(job, command, path, 'transcript-call', '')
            elif block.get('name') in ('Agent', 'Task') and args.get('model'):
                prompt = args.get('prompt', '')
                match = re.search(r'(?im)(?:Working dir(?:ectory)?|Job directory|Your directory|Work dir|Directory|Work in)\s*(?::|is)?\s+`?((?:~/|/)[^\s`;,]+)', prompt)
                if match:
                    workdir = match.group(1).rstrip('.')
                    self.add(Path(workdir).name, dict(model=args['model'], workdir=workdir), path, 'transcript-call', prompt)

    def add(self, job, row, path, kind, text):
        job = job_name(job)
        # launch.sh prepends shared rules, lane goals and lessons. Their paths
        # describe previous jobs, not inputs to this one.
        marker = '--- LESSONS THIS LANE ALREADY PAID FOR ---\n'
        if marker in text:
            text = text.split(marker, 1)[1].partition('\n---\n\n')[2]
        elif '--- LANE GOAL (' in text:
            text = text.split('--- LANE GOAL (', 1)[1].partition('\n---\n\n')[2]
        entry = dict(row, path=str(path), job=job, link_kind=kind)
        old = self.jobs.get(job)
        if old:
            before, after = self.PRIORITY[old['link_kind']], self.PRIORITY[kind]
            if before < after:
                return
            if before == after:
                def identity(r):
                    model = (r.get('canonical') or r.get('model') or '').removeprefix('anthropic/').removeprefix('openai/')
                    return re.sub(r'(?<=\d)-(?=\d)', '.', model)
                if identity(old) != identity(entry):
                    self.ambiguous.add(job)
                return
            self.ambiguous.discard(job)
        self.jobs[job] = entry
        self.specs[job] = text
        self.aliases[job].add(job)
        for key in ('job_id', 'round', 'round_id'):
            if row.get(key):
                self.aliases[str(row[key])].add(job)
        workdir = row.get('workdir') or row.get('work_dir')
        if not workdir:
            match = re.search(r'(?im)(?:Working dir(?:ectory)?|Job directory|Your directory|Work dir|Directory)\s*:\s*`?([^\s`;,]+)', text)
            workdir = match.group(1).rstrip('.') if match else None
        if workdir:
            self.workdirs[job] = Path(workdir).expanduser()
        self.designs[job] = re.findall(r'([^\s`\"<>(),;]+/DESIGN(?:_v\d+|_\d+)?\.md)', text)
        for value in re.findall(r'(?i)\bwrite(?:\s+to)?\s+`?((?:~/|/)[^\s`\"<>(),;]+)', text):
            output = Path(value.rstrip('.')).expanduser()
            self.outputs[output].add(job)
            if output.name == 'CLAIM.md':
                self.outputs[output.parent].add(job)

    def roles_for_job(self, job):
        if job in self._roles:
            return self._roles[job]
        entry = self.get(job)
        if not entry:
            return set()
        result = {entry['role']} if entry.get('role') else set()
        root = self.workdirs.get(job)
        names = {p.name.upper() for p in root.glob('*.md')} if root and root.is_dir() else set()
        text = self.specs.get(job, '')
        if 'IDEAS.MD' in names:
            result.add('ideation')
        if any(re.fullmatch(r'DESIGN(?:_V\d+|_\d+)?\.MD', n) for n in names):
            result.add('design')
            if re.search(r'(?i)\bpick\b|\branked\b', text):
                result.add('taste')
        if names & {'RULING.MD', 'JUDGEMENT.MD', 'JUDGMENT.MD'}:
            result.update(('judge', 'taste'))
        if re.search(r'(?i)you are (?:the |an? )?(?:independent )?(?:referee|reviewer)|reading the exact final bytes', text):
            result.add('review')
        self._roles[job] = result
        return result

    def resolve(self, *values, role=None):
        for value in values:
            if not value:
                continue
            direct = self.aliases.get(str(value), set()) | self.aliases.get(job_name(value), set())
            if len(direct) == 1:
                return next(iter(direct))
            linked = self.job_for_artifact(value, role)
            if linked:
                return linked
        return None

    @functools.lru_cache(maxsize=16384)
    def job_for_artifact(self, value, role=None):
        if not value or str(value).startswith(('http:', 'https:')):
            return None
        path = Path(str(value).strip('` ')).expanduser()
        if not path.is_absolute():
            path = self.artifact_root / path
        explicit = self.outputs.get(path, set())
        if role:
            explicit = {name for name in explicit if role in self.roles_for_job(name)}
        if len(explicit) == 1:
            return next(iter(explicit))
        candidates = {name for part in path.parts for name in self.aliases.get(job_name(part), ())}
        containing = {name: len(root.parts) for name, root in self.workdirs.items() if path == root or root in path.parents}
        if containing:
            depth = max(containing.values())
            candidates.update(name for name, length in containing.items() if length == depth)
        if role:
            candidates = {name for name in candidates if role in self.roles_for_job(name)}
        if not candidates:
            # A legacy snapshot can use the original job directory as its file stem.
            candidates = {name for name, root in self.workdirs.items() if root.name == path.stem and (not role or role in self.roles_for_job(name))}
        return next(iter(candidates)) if len(candidates) == 1 else None

    def design_jobs(self, job, seen=None):
        if not job or job in (seen or set()):
            return set()
        if 'design' in self.roles_for_job(job):
            return {job}
        seen = (seen or set()) | {job}
        direct = {self.job_for_artifact(p, 'design') for p in self.designs.get(job, [])}
        direct.discard(None)
        if direct:
            return direct
        return set().union(*(self.design_jobs(p, seen) for p in self.references[job])) if self.references[job] else set()

    def design_for_artifact(self, value):
        designs = self.design_jobs(self.resolve(value))
        return next(iter(designs)) if len(designs) == 1 else None

    def get(self, job):
        name = job_name(job)
        return None if name in self.ambiguous else self.jobs.get(name)

class Outcomes:
    def __init__(self, receipts, canon, make_observation):
        self.receipts, self.canon, self.make = receipts, canon, make_observation
        self.stats = collections.defaultdict(lambda: dict(resolved=0, pending=0, unlinked=0))
        self.observations = {}
        self.links = collections.defaultdict(collections.Counter)
        self.diagnostics = []
        self.mirrored = {}

    def producer(self, row, *keys, role=None, receipts=None):
        receipts = receipts or self.receipts
        return receipts.resolve(*(row.get(k) for k in (*keys, 'job', 'job_id', 'source_job', 'round', 'round_id', 'run_dir', 'path')), role=role)

    def emit(self, kind, item, job, outcome, row, path, role=None, receipts=None):
        receipts = receipts or self.receipts
        stats = self.stats[kind]
        if outcome is None:
            stats['pending'] += 1
            return
        job = receipts.resolve(job)
        receipt = receipts.get(job)
        model = self.canon(receipt.get('canonical') or receipt.get('model')) if receipt else None
        if not receipt or not model or not (role or receipt.get('role')):
            stats['unlinked'] += 1
            self.diagnostics.append(dict(kind=kind, item=item, path=str(path), job=job,
                                         reason='missing or ambiguous producing-job provenance', row=row))
            return
        date = day(row)
        if not date:
            stats['pending'] += 1
            return
        selected_role = role or receipt['role']
        observation = self.make('receipt-' + kind, str(item), model, selected_role,
                                outcome, date, [path, receipt['path']], f'{kind}: {outcome}')
        observation.update(role=selected_role, job=receipt['job'], source_kind=kind, day=date,
                           link_kind=receipt['link_kind'])
        if observation['id'] not in self.observations:
            stats['resolved'] += 1
        self.observations[observation['id']] = observation
        self.links[kind][receipt['link_kind']] += 1

    def design(self, row, path, item):
        outcome = verdict(row.get('referee') or row.get('verdict') or row.get('outcome'))
        job = self.producer(row, 'design_job') or self.receipts.design_for_artifact(row.get('link') or row.get('result_path'))
        if not job and row.get('link') and not row.get('source_kind'):
            # Older result rows name a claim, not a separate design. Credit the
            # launch-selected production role, rather than relabelling it design.
            producers = {self.receipts.job_for_artifact(row['link'], role) for role in ('batch', 'builder', 'ideation')}
            producers.discard(None)
            if len(producers) == 1:
                producer = next(iter(producers))
                self.emit('result', item, producer, outcome, row, path)
                return
        self.emit('design', item, job, outcome, row, path, 'design')

    def judge(self, row, path, item):
        # This is a later referee's disposition of the ruling, not the ruling itself.
        outcome = verdict(row.get('judge_outcome') or row.get('ruling_outcome') or row.get('outcome'))
        job = self.producer(row, 'judge_job')
        self.emit('judge', item, job, outcome, row, path, 'judge')

    def review(self, row, path, item):
        plant = row.get('plant_caught')
        outcome = ('held' if plant else 'overturned') if type(plant) is bool else verdict(row.get('plant_outcome') or row.get('outcome'))
        self.emit('review', item, self.producer(row, 'review_job', 'referee_job'), outcome, row, path, 'review')

    def referee_batch(self, row, path, item):
        planted, caught, fooled = (row.get(k, 0) for k in ('planted', 'caught', 'fooled'))
        if any(type(n) is not int or n < 0 for n in (planted, caught, fooled)) or caught + fooled > planted:
            raise ValueError(f'{path}: invalid planted outcome counts')
        if not planted:
            return
        outcome = 'overturned' if fooled else 'held' if caught == planted else None
        job = self.producer(row, 'review_job', 'referee_job') or self.receipts.job_for_artifact(row.get('file'))
        self.emit('review', item, job, outcome, row, path, 'review')

    def ideation(self, history, path, item):
        first, latest = history[0], history[-1]
        tested = any(r.get('status') in ('testing', 'shipped') or r.get('result_path') for r in history)
        fault = latest.get('close_kind') in ('prior-art', 'duplicate', 'rule-blocked')
        if not latest.get('close_kind'):
            fault = bool(re.search(r'prior art|duplicate|already known|not new', latest.get('closed_reason', ''), re.I))
        outcome = 'held' if tested else 'overturned' if latest.get('status') == 'closed' and fault else None
        producer = self.producer(first, 'proposer_job', 'design_job', 'proposed_by') or self.receipts.job_for_artifact(first.get('source_path'))
        self.emit('ideation', item, producer, outcome, latest, path, 'ideation')

    def pull_request(self, row, path, item):
        merged = row.get('merged_at') or row.get('merged') is True
        closed = str(row.get('state', '')).lower() == 'closed'
        outcome = 'held' if merged else 'overturned' if closed else None
        dated = dict(row, day=row.get('merged_at') or row.get('closed_at') or row.get('day') or row.get('utc') or row.get('date'))
        producer = self.producer(row, 'opened_by_job')
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
            paths = [r.get('result_path') for r in history[index:]]
            job = self.producer(decision, 'decider_job', 'decision_job', 'decided_by', role='taste') or self.receipts.resolve(*paths, role='taste')
            self.emit('taste', f"{item}/{decision['event']}/{index}", job, outcome, decision, path, 'taste')

    def everyday(self, row, path, item, receipts=None):
        # pass / partial / fail of a returned delegated job, credited to the model its receipt ran.
        grade = {'pass': 'held', 'partial': 'partial', 'fail': 'overturned', 'ungraded': 'ungraded'}.get(str(row.get('grade')).lower())
        self.emit('everyday', item, self.producer(row, receipts=receipts), grade, row, str(path), receipts=receipts)

    def grade_receipts(self, ledger):
        """The receipts a ledger's grades name: this reader's own when they sit beside it, else the ledger's
        receipt directory (a mirror of another Mac's), read once. None when that directory is missing."""
        directory = grade_ledgers.receipts_dir(ledger)
        try:
            if directory.resolve() == Path(self.receipts.root).resolve():
                return None
        except OSError:
            pass
        if directory not in self.mirrored:
            try:
                self.mirrored[directory] = Receipts(directory) if directory.is_dir() else None
            except (OSError, ValueError):
                self.mirrored[directory] = None
        return self.mirrored[directory]

    def read_grades(self, ledgers):
        """Everyday grades from every ledger, as one record: one row per grade id, a retraction in any ledger
        applies in all (grade_ledgers.rows). A grade links to the receipt beside its own ledger first."""
        for row, path, number in grade_ledgers.rows(ledgers):
            item = row.get('id') or f'{path}:{number}'
            own = self.grade_receipts(path)
            if own is not None and not own.get(self.producer(row, receipts=own) or ''):
                own = None      # not in its own directory's receipts: try this reader's
            self.everyday(row, path, item, receipts=own)

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
        issuing_job = self.receipts.resolve(str(path))
        if not issuing_job:
            issuing_job = self.receipts.resolve(str(path), role='mechanical') or self.receipts.resolve(str(path), role='review')
        issuing = self.receipts.get(issuing_job)
        if not date and issuing:
            row['date'] = day(issuing)
        # A partial opening is not a resolved verdict on the frozen full panel.
        if re.search(r'(?i)\bINTERIM\b', text.splitlines()[0] if text.splitlines() else ''):
            row['verdict'] = None
        item = str(path)
        if fields.get('design_job'):
            self.design(row, str(path), item)
        if fields.get('judge_job'):
            self.judge(row, str(path), item)
        if fields.get('review_job') or fields.get('referee_job'):
            self.review(row, str(path), item)
        # An unlabelled referee verdict still counts as unlinked, never as the author's score.
        if outcome and not any(fields.get(k) for k in ('design_job', 'judge_job', 'review_job', 'referee_job')):
            job = self.receipts.design_for_artifact(str(path))
            if job != issuing_job:
                row['design_job'] = job
            producers = {self.receipts.job_for_artifact(str(path.parent), role) for role in ('batch', 'builder')}
            producers.discard(None)
            if not job and len(producers) == 1:
                producer = next(iter(producers))
                if producer != issuing_job and issuing_job:
                    self.emit('result', str(path.parent), producer, verdict(row.get('verdict')), row, str(path))
                else:
                    self.design(row, str(path), item)
            else:
                self.design(row, str(path), f'design/{job}' if job else item)
        self.judge_disposition(path, text, issuing_job, row)

    def judge_disposition(self, path, text, issuing_job, row):
        """A verdict on a result does not settle every earlier ruling.

        Native audits explicitly name the judge they recompute. Final reads can
        explicitly correct an earlier judgement; without such a disposition the
        judge stays pending. One active observation is retained per ruling job.
        """
        spec = self.receipts.specs.get(issuing_job, '')
        matches = re.findall(r'(?im)(?:The judge|Your earlier judg(?:e)?ment(?: on the draft)?):\s*`?([^\s`]+)', spec)
        judges = {self.receipts.resolve(value.rstrip('.')) for value in matches}
        judges.discard(None)
        if len(judges) != 1:
            return
        judge = next(iter(judges))
        if judge == issuing_job:
            return
        # Include the paired judgement only for an explicit final-byte check.
        paired = path.with_name('JUDGEMENT.md')
        evidence = text
        if path.name == 'ledger_verdict.md' and paired.is_file():
            evidence += '\n' + paired.read_text()
        correction = re.search(
            r'(?im)^.*(?:judge.{0,140}(?:too lenient|miscalibrated|overturned|wrong)|'
            r'(?:wrong|incorrect).{0,100}(?:own earlier|earlier judg)|'
            r'(?:overturned|refuted)\s+ruling).*$', evidence)
        audit_of_judge = re.search(r'(?i)The judge:', spec) and re.search(r'(?i)recompute|audit|independent', spec)
        outcome = 'overturned' if correction else verdict(row.get('verdict')) if audit_of_judge else None
        if outcome:
            judged = dict(row, judge_job=judge, judge_outcome=outcome)
            self.judge(judged, str(path), f'ruling/{judge}')
            observation = next((r for r in self.observations.values() if r.get('source_kind') == 'judge' and r.get('job') == judge), None)
            if observation and correction:
                observation['disposition_evidence'] = correction.group(0).strip()
                if paired.is_file() and str(paired) not in observation['evidence']:
                    observation['evidence'].append(str(paired))

    def admissions(self):
        """A separately launched execution is evidence a design entered testing."""
        for runner, spec in self.receipts.specs.items():
            if 'design' in self.receipts.roles_for_job(runner):
                continue
            if not re.search(r'(?i)\b(?:run|execute)\b.{0,45}\b(?:frozen )?design\b|\bdesign\b.{0,25}\bexactly as written', spec):
                continue
            designs = self.receipts.design_jobs(runner)
            if len(designs) != 1:
                continue
            designer = next(iter(designs))
            receipt = self.receipts.get(runner)
            if receipt and 'ideation' in self.receipts.roles_for_job(designer):
                self.emit('ideation', f'admission/{designer}', designer, 'held', receipt, receipt['path'], 'ideation')

    def read(self, path):
        path = Path(path)
        if path.suffix == '.md':
            self.read_markdown(path)
            return
        if path.suffix == '.json':
            data = json.loads(path.read_text())
            source_rows = [dict(r, date=r.get('date') or data.get('fetched')) for r in data['prs']] if isinstance(data, dict) and 'prs' in data else [data]
        else:
            source_rows = list(rows(path))
        ideas = collections.defaultdict(list)
        # 11-20: a grade caused by a harness or launcher error is retracted by an appended row
        # (worker_models.py --retract); every everyday row for that job id is then left out.
        retracted = {r.get('id') for r in source_rows if isinstance(r, dict)
                     and r.get('source_kind') == 'everyday' and str(r.get('grade')).lower() == 'retracted'}
        for number, row in enumerate(source_rows, 1):
            item = row.get('id') or row.get('url') or f'{path}:{number}'
            kind = row.get('source_kind') or row.get('outcome_kind')
            if path.name == 'IDEAS.jsonl':
                ideas[row['id']].append(row)
                continue
            if kind == 'everyday':
                if row.get('id') in retracted:
                    continue
                self.everyday(row, path, item)
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


def collect(evidence_root, receipts_root, canon, make_observation, outcomes_root=None, upstream_root=None,
            launch_root=None, transcript_root=None, grades=None):
    reader = Outcomes(Receipts(receipts_root, launch_root, transcript_root), canon, make_observation)
    paths = set()
    if evidence_root:
        lanes = Path(evidence_root) / 'lanes'
        if not lanes.is_dir():
            raise ValueError(f'evidence root has no lanes directory: {evidence_root}')
        for name in ('IDEAS.jsonl', 'RESULTS.jsonl', 'REFEREE.jsonl', '.upstream-prs.json'):
            paths.update(lanes.glob('*/' + name))
    # Grades of returned delegated jobs (worker_models.py --grade) sit beside the receipts they name;
    # RH_EVERYDAY_GRADES adds other Macs' ledgers, mirrored read-only (grade_ledgers.py).
    if grades is None:
        grades = grade_ledgers.ledgers(receipts_root)
    if outcomes_root:
        root = Path(outcomes_root)
        if not root.is_dir():
            raise ValueError(f'outcomes root is not a directory: {root}')
        paths.update(root.glob('*.jsonl'))
        paths.update(root.glob('*.outcomes.json'))
        paths.update(root.glob('*/*.outcomes.jsonl'))
        paths.update(root.glob('*/*.outcomes.json'))
        for pattern in ('*.verdict.md', '*/referee*.md', '*/ledger_verdict.md', '*/claims/*/VERDICT.md'):
            paths.update(root.glob(pattern))
    if upstream_root:
        root = Path(upstream_root)
        if not root.is_dir():
            raise ValueError(f'upstream root is not a directory: {root}')
        paths.update(root.rglob('*.json'))
        paths.update(root.rglob('*.jsonl'))
    for path in sorted(paths):
        reader.read(path)
    reader.read_grades(grades)
    reader.admissions()
    stats = dict(reader.stats)
    # Counts describe active observations, not repeated reads of one verdict.
    for kind, counts in stats.items():
        counts['resolved'] = sum(r['source_kind'] == kind for r in reader.observations.values())
    links = collections.defaultdict(collections.Counter)
    for observation in reader.observations.values():
        links[observation['source_kind']][observation['link_kind']] += 1
    stats['_links'] = {kind: dict(counts) for kind, counts in links.items()}
    stats['_entries'] = []
    for job, receipt in reader.receipts.jobs.items():
        model = canon(receipt.get('canonical') or receipt.get('model')) if reader.receipts.get(job) else None
        if model:
            stats['_entries'].extend(dict(model=model, role=role, job=job, link_kind=receipt['link_kind'])
                                     for role in sorted(reader.receipts.roles_for_job(job)))
    return list(reader.observations.values()), stats
