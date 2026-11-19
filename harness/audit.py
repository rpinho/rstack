"""rh audit LANE "question": a read-only agent answers questions about a lane's work from its own files.

Adapted from DiscoveryAgent's Audit Agent (Queen, Gorrell et al., arXiv 2611.21950; code
github.com/evangorrell/DiscoveryAgent-app, application/frontend/AIR/utils/code_chat.py, MIT). Their
human study is the one piece of that paper with a measured effect: people with the audit agent found
3.5 of 36 planted errors on average against 0.25 with code alone (8 participants; small). What carries
over: an agent pointed at a run's reports, code and evidence with READ-ONLY tools, told to answer what
was done, objectively, citing files and rounds, and to add no opinions of its own. What changes: our
layout (LANE.json, IDEAS/RESULTS/REFEREE ledgers, sweep runs, evidence paths) and our two backends.

It is a question-answering tool for Ricardo and general, not a referee: it never writes a verdict,
a ledger row or a result. Every answer is saved under LANE/audits/ with the question and what it read.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess

LEDGERS = ('LANE.json', 'SELECTION.json', 'RULES.md', 'STATUS.md', 'IDEAS.jsonl', 'RESULTS.jsonl',
           'REFEREE.jsonl', 'DELIVERIES.jsonl', 'TARGETS.jsonl', 'PLANTS.jsonl', 'COVERAGE.jsonl',
           'LESSONS.jsonl', 'OUTREACH.jsonl', 'HOLD', 'SWEEP.toml', 'INTAKE.toml', 'CADENCE.toml')
READ_ONLY_TOOLS = 'Read Grep Glob'
NEVER_TOOLS = 'Bash Edit Write NotebookEdit WebFetch WebSearch Task'
PATH_KEYS = re.compile(r'(path|evidence|report|receipt|dir|file)', re.I)
MAX_ROOTS = 12

PROMPT = """You are the audit agent for one research lane of an AI research harness. A human expert (the
lane's owner, or the conductor acting for him) is asking questions about work AI agents did. Answer what was
actually done: background, method, results and their evidence, and how a claim was checked. Be objective and
precise. Do NOT add your own opinions or interpretations, and do not judge whether a result is good; say what
the files show, and say plainly when the files do not show something. Your answer will guide real decisions,
so a wrong answer is worse than "the files do not say".

Where things are (lane folder: {lane}):
- LANE.json and SELECTION.json: the frozen problem, metric, splits and selection rules (frozen before any result).
- IDEAS.jsonl: every idea the lane considered, one JSON row per change; the newest row for an id wins.
- RESULTS.jsonl: results the lane logged, with verification level and evidence paths. REFEREE.jsonl: referee
  verdicts on them. DELIVERIES.jsonl / OUTREACH.jsonl: what was delivered or sent.
- STATUS.md: the lane's running log. RULES.md: its rules.
- sweep-work/runs/<run id>/: one folder per sweep run. REPORT.md and STATUS.md summarize it; <stage>.report.md
  are the search, read and kill reports; *.prompt is the exact prompt each worker got; *.selection.json is the
  model route it ran on.
{extra}
Read only what you need (Grep first; ledgers can be large). Cite the file and, for ledgers, the row id or line,
e.g. "RESULTS.jsonl row r-12ab: ...", "run 20261118T153226 kill.report.md: ...". When you quote numbers, quote
them from a file. Format the answer as plain GitHub markdown, short headings and bullets, no ASCII tables.

Question: {question}
"""


def _existing(p):
    p = Path(os.path.expanduser(str(p)))
    return p if p.exists() else None


def evidence_roots(lane, limit=MAX_ROOTS):
    """Folders outside the lane that its ledgers cite as evidence (result_path, evidence, report ...)."""
    roots, lane = [], Path(lane).resolve()
    for name in ('RESULTS.jsonl', 'REFEREE.jsonl', 'DELIVERIES.jsonl'):
        f = lane / name
        if not f.is_file():
            continue
        for line in f.read_text(errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            stack = [row]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    for k, v in item.items():
                        if isinstance(v, str) and PATH_KEYS.search(k) and v.startswith(('/', '~')):
                            hit = _existing(v)
                            if hit:
                                root = (hit if hit.is_dir() else hit.parent).resolve()
                                if lane not in (root, *root.parents) and root not in roots:
                                    roots.append(root)
                        elif isinstance(v, (dict, list)):
                            stack.append(v)
                elif isinstance(item, list):
                    stack.extend(item)
    return roots[-limit:]   # the newest rows are last, so the newest evidence wins the cap


def run_dir(lane, run_id):
    runs = Path(lane) / 'sweep-work' / 'runs'
    hits = sorted(p for p in runs.glob(run_id + '*') if p.is_dir()) if runs.is_dir() else []
    if len(hits) != 1:
        raise ValueError('run id {!r}: {} matching run folders in {}'.format(run_id, len(hits), runs))
    return hits[0]


def build_prompt(lane, question, roots, run=None):
    extra = ''
    if run is not None:
        extra += '- The question is about run {}; start there.\n'.format(Path(run).name)
    if roots:
        extra += ('- Evidence outside the lane that its ledgers cite (code, reports, certificates):\n'
                  + ''.join('  - {}\n'.format(r) for r in roots))
    return PROMPT.format(lane=lane, extra=extra, question=question.strip())


def command(backend, lane, roots, model, executable=None):
    """The read-only agent command. The prompt goes on stdin."""
    if backend == 'claude':
        cmd = [executable or 'claude', '-p', '--model', model, '--output-format', 'text',
               '--permission-mode', 'default', '--allowedTools', READ_ONLY_TOOLS,
               '--disallowedTools', NEVER_TOOLS, '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
               '--setting-sources', '', '--disable-slash-commands', '--no-session-persistence']
        for r in roots:
            cmd += ['--add-dir', str(r)]
        return cmd
    if backend == 'codex':
        cmd = [executable or 'codex', 'exec', '--ignore-user-config', '--skip-git-repo-check',
               '--sandbox', 'read-only', '--cd', str(lane), '-m', model]
        for r in roots:
            cmd += ['--add-dir', str(r)]
        return cmd + ['-']
    raise ValueError('backend must be claude or codex')


def slug(text, n=40):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:n] or 'question'


def audit(lane, question, backend='claude', model=None, run_id=None, dry_run=False,
          timeout=1800, runner=subprocess.run, executable=None):
    lane = Path(lane).resolve()
    if not question.strip():
        raise ValueError('ask a question')
    model = model or os.environ.get('RH_AUDIT_MODEL') or ('opus' if backend == 'claude' else os.environ.get('CODEX_MODEL', ''))
    if not model:
        raise ValueError('no model: pass --model or set RH_AUDIT_MODEL')
    run = run_dir(lane, run_id) if run_id else None
    roots = evidence_roots(lane)
    prompt = build_prompt(lane, question, roots, run)
    cmd = command(backend, lane, roots, model, executable)
    if dry_run:
        return dict(command=cmd, prompt=prompt, roots=[str(r) for r in roots], saved=None, answer=None)
    done = runner(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=str(lane))
    if done.returncode != 0:
        raise RuntimeError('audit agent exit {}: {}'.format(done.returncode, (done.stderr or '').strip()[-400:]))
    answer = done.stdout.strip()
    out = lane / 'audits'
    out.mkdir(exist_ok=True)
    path = out / '{}-{}.md'.format(datetime.now().strftime('%Y%m%dT%H%M%S'), slug(question))
    head = ['# Audit: {}'.format(question.strip()), '',
            '- lane: `{}`{}'.format(lane.name, '; run `{}`'.format(run.name) if run else ''),
            '- agent: {} `{}`, read-only tools ({})'.format(backend, model,
                                                            READ_ONLY_TOOLS if backend == 'claude' else 'sandbox read-only'),
            '- evidence folders it could read: {}'.format(', '.join('`{}`'.format(r) for r in roots) or 'none'),
            '- asked: {}'.format(datetime.now().isoformat(timespec='seconds')), '', '## Answer', '']
    path.write_text('\n'.join(head) + answer + '\n')
    return dict(command=cmd, prompt=prompt, roots=[str(r) for r in roots], saved=str(path), answer=answer)
