"""Tests for the general worktree hook, using local subprocess payloads only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

GATE = Path(__file__).resolve().parents[2] / 'tools/email-voice-gate.py'
spec = importlib.util.spec_from_file_location('outreach_gate_under_test', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def ledger(tmp_path):
    lane = tmp_path / 'lanes/test'
    lane.mkdir(parents=True)
    draft = tmp_path / 'draft.txt'
    draft.write_text('Which landmark would you measure?\n')
    digest = hashlib.sha256(draft.read_bytes()).hexdigest()
    row = dict(id='approved-one', status='approved', draft_path=str(draft), approval=dict(sha256=digest, quote='Send this one'))
    path = lane / 'OUTREACH.jsonl'
    path.write_text(json.dumps(row) + '\n')
    return tmp_path, path, draft, row


def pipe(root, text, mode='warn', **extra):
    env = dict(os.environ, RH_OUTREACH_ROOT=str(root), RH_OUTREACH_GATE=mode)
    payload = {'tool_input': dict(body=text, **extra)}
    run = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload), text=True, capture_output=True, env=env, timeout=10)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) if run.stdout else None


def test_pipe_allows_approved_exact_body(ledger):
    root, _, draft, _ = ledger
    assert pipe(root, draft.read_text(), 'enforce') is None


def test_pipe_warns_unknown_by_default(ledger, monkeypatch):
    root, _, _, _ = ledger
    monkeypatch.delenv('RH_OUTREACH_GATE', raising=False)
    event = io.StringIO(json.dumps({'tool_input': {'body': 'A different question?'}}))
    out = io.StringIO()
    with patch.object(gate, 'HARNESS', root), patch.object(sys, 'stdin', event), contextlib.redirect_stdout(out):
        assert gate.main() == 0
    result = json.loads(out.getvalue())
    assert 'WARNING' in result['systemMessage'] and 'rh outreach approve' in result['systemMessage']
    assert 'permissionDecision' not in out.getvalue()


def test_pipe_denies_unknown_in_enforce(ledger):
    root, _, _, _ = ledger
    result = pipe(root, 'A different question?', 'enforce')
    assert result['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert 'rh outreach lint' in result['hookSpecificOutput']['permissionDecisionReason']


@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_pipe_denies_xlint_fail_in_both_modes(ledger, mode):
    root, _, _, _ = ledger
    result = pipe(root, 'Hello! Can you help?', mode)
    assert result['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert 'xlint' in result['hookSpecificOutput']['permissionDecisionReason']


def test_changed_file_and_changed_payload_invalidate_approval(ledger):
    root, _, draft, _ = ledger
    original = draft.read_text()
    assert not gate.approved_body({'body': original.strip()}, root)
    assert not gate.approved_body({'body': original + 'More.'}, root)
    draft.write_text('Changed on disk.')
    assert not gate.approved_body({'body': original}, root)


@pytest.mark.parametrize('status', ['sent', 'drafted', 'linted', 'closed', 'dropped'])
def test_latest_row_wins_gate(ledger, status):
    root, path, draft, row = ledger
    with path.open('a') as f:
        f.write(json.dumps(dict(row, status=status)) + '\n')
    assert not gate.approved_body({'body': draft.read_text()}, root)


def test_gate_does_not_approve_normalized_history_html_or_multiple_bodies(ledger):
    root, _, draft, _ = ledger
    original = draft.read_text()
    for payload in ({'htmlBody': '<p>' + original + '</p>'}, {'body': original + '\n> history'},
                    {'body': original, 'text': 'different body'}):
        assert not gate.approved_body(payload, root)


def test_voice_failure_denies_even_approved_hash(ledger):
    root, path, draft, row = ledger
    draft.write_text('Hello! Can you help?')
    row['approval']['sha256'] = hashlib.sha256(draft.read_bytes()).hexdigest()
    path.write_text(json.dumps(row) + '\n')
    assert pipe(root, draft.read_text(), 'enforce')['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_missing_xlint_fails_closed(ledger):
    root, _, draft, _ = ledger
    event = io.StringIO(json.dumps({'tool_input': {'body': draft.read_text()}}))
    out = io.StringIO()
    with patch.object(gate, 'VOICE_COMMAND', [str(root / 'missing-checker')]), patch.object(sys, 'stdin', event), contextlib.redirect_stdout(out):
        assert gate.main() == 0
    assert json.loads(out.getvalue())['hookSpecificOutput']['permissionDecision'] == 'deny'


def paper_cut_env(tmp_path, root):
    bank = tmp_path / 'bank.jsonl'
    bank.write_text(json.dumps({'text': 'thanks, that makes sense'}) + '\n')
    spec = tmp_path / 'banks.json'
    spec.write_text(json.dumps({'v2': {'path': str(bank), 'lang': 'en'}}))
    state = tmp_path / 'cuts-state'
    return dict(os.environ, RH_OUTREACH_ROOT=str(root), RH_OUTREACH_GATE='warn', RH_VOICE_BANKS=str(spec),
                RH_VOICE_CUTS_STATE=str(state), RH_ENV_FILE=os.devnull), state


def run_gate(env, text):
    run = subprocess.run([sys.executable, str(GATE)], input=json.dumps({'tool_input': {'body': text}}),
                         text=True, capture_output=True, env=env, timeout=10)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) if run.stdout else None


def test_with_banks_a_body_needs_a_paper_cut_pass_or_an_approved_draft(ledger, tmp_path):
    root, _, draft, _ = ledger
    env, state = paper_cut_env(tmp_path, root)
    denied = run_gate(env, 'thanks, that makes sense')
    assert denied['hookSpecificOutput']['permissionDecision'] == 'deny' and 'paper-cut' in str(denied)
    assert run_gate(env, draft.read_text()) is None, 'an approved draft already passed lint'
    sys.path.insert(0, str(GATE.parents[1] / 'harness'))
    import voice_cuts
    voice_cuts.record_pass(tmp_path / 'x.txt', 'thanks, that makes sense', {'cuts': 1}, state=state)
    result = run_gate(env, 'thanks,  that makes sense\n\nOn Mon, someone wrote:\n> old')
    assert result is None or 'permissionDecision' not in str(result)


def test_without_banks_the_paper_cut_rule_is_off(ledger, tmp_path):
    root, _, _, _ = ledger
    env, _ = paper_cut_env(tmp_path, root)
    del env['RH_VOICE_BANKS']
    result = run_gate(env, 'A different question?')
    assert result is None or 'paper-cut' not in str(result)
