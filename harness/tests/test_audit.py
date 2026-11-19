"""rh audit: a read-only agent answers from a lane's own files and saves the answer."""
import json
from pathlib import Path
import subprocess

import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit


def lane(tmp_path):
    l = tmp_path / 'lanes' / 'demo'
    (l / 'sweep-work' / 'runs' / '20261118T153226-3b8c6ec8').mkdir(parents=True)
    ev = tmp_path / 'work' / 'certificate'
    ev.mkdir(parents=True)
    (ev / 'final.json').write_text('{}')
    rows = [{'id': 'r1', 'result_path': str(ev / 'final.json')},
            {'id': 'r2', 'evidence': [{'path': str(tmp_path / 'missing')}]},
            {'id': 'r3', 'result_path': str(l / 'STATUS.md')}]
    (l / 'RESULTS.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (l / 'STATUS.md').write_text('log')
    return l, ev


def test_evidence_roots_are_existing_folders_outside_the_lane(tmp_path):
    l, ev = lane(tmp_path)
    assert audit.evidence_roots(l) == [ev.resolve()]


def test_claude_command_is_read_only(tmp_path):
    l, ev = lane(tmp_path)
    cmd = audit.command('claude', l, [ev], 'opus')
    allowed = cmd[cmd.index('--allowedTools') + 1].split()
    never = cmd[cmd.index('--disallowedTools') + 1].split()
    assert allowed == ['Read', 'Grep', 'Glob']
    assert {'Bash', 'Edit', 'Write', 'WebFetch'} <= set(never)
    assert cmd[cmd.index('--permission-mode') + 1] == 'default'
    assert ['--add-dir', str(ev)] == cmd[cmd.index('--add-dir'):cmd.index('--add-dir') + 2]


def test_codex_command_uses_the_read_only_sandbox(tmp_path):
    l, ev = lane(tmp_path)
    cmd = audit.command('codex', l, [ev], 'some-model')
    assert cmd[cmd.index('--sandbox') + 1] == 'read-only' and cmd[-1] == '-'
    assert '--dangerously-bypass-approvals-and-sandbox' not in cmd


def test_prompt_names_the_run_the_evidence_and_the_question(tmp_path):
    l, ev = lane(tmp_path)
    run = audit.run_dir(l, '20261118T1532')
    p = audit.build_prompt(l, 'Which baseline did round 3 beat?', [ev], run)
    assert 'run 20261118T153226-3b8c6ec8' in p and str(ev) in p and 'Which baseline did round 3 beat?' in p
    assert 'Do NOT add your own opinions' in p


def test_unknown_or_ambiguous_run_refuses(tmp_path):
    l, _ = lane(tmp_path)
    with pytest.raises(ValueError):
        audit.run_dir(l, 'nope')


def test_dry_run_calls_nothing_and_writes_nothing(tmp_path):
    l, _ = lane(tmp_path)
    called = []
    out = audit.audit(l, 'q?', dry_run=True, runner=lambda *a, **k: called.append(a))
    assert called == [] and out['saved'] is None and not (l / 'audits').exists()


def test_answer_is_saved_with_question_and_reads(tmp_path):
    l, ev = lane(tmp_path)
    seen = {}

    def runner(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout='In run 20261118T153226 the kill stage ...', stderr='')
    out = audit.audit(l, 'What did the kill stage reject?', runner=runner)
    text = Path(out['saved']).read_text()
    assert seen['cwd'] == str(l.resolve()) and 'What did the kill stage reject?' in seen['input']
    assert text.startswith('# Audit: What did the kill stage reject?') and str(ev.resolve()) in text
    assert 'the kill stage ...' in text


def test_agent_failure_is_an_error_not_a_saved_answer(tmp_path):
    l, _ = lane(tmp_path)
    runner = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout='', stderr='boom')
    with pytest.raises(RuntimeError):
        audit.audit(l, 'q?', runner=runner)
    assert not (l / 'audits').exists()
