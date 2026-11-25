"""The codex wrapper is privacy routing only (11-24): no budget, no ledger."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'codex'
_loader = importlib.machinery.SourceFileLoader('codex_wrapper', str(TOOL))
codex = importlib.util.module_from_spec(importlib.util.spec_from_loader(_loader.name, _loader))
_loader.exec_module(codex)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('CODEX_HOME', raising=False)
    monkeypatch.setenv('CODEX_ROUTING_CONFIG', str(tmp_path / 'routing.json'))
    (tmp_path / 'routing.json').write_text(json.dumps({'personal_roots': ['~/notes']}))
    return tmp_path


def test_batch_is_clean_outside_the_personal_roots_and_personal_inside(home):
    assert codex.routing(['-m', 'some-model', 'exec', 'hi']) == ['-m', 'some-model', 'exec', 'hi']
    assert os.environ['CODEX_HOME'] == str(home / '.codex-clean')
    os.environ.pop('CODEX_HOME')
    (home / 'notes/sub').mkdir(parents=True)
    codex.routing(['exec', '--cd', str(home / 'notes/sub'), 'hi'])
    assert os.environ['CODEX_HOME'] == str(home / '.codex')


def test_flags_override_and_an_explicit_home_wins(home):
    assert '--personal' not in codex.routing(['--personal', 'exec', 'hi'])
    assert os.environ['CODEX_HOME'] == str(home / '.codex')
    os.environ.pop('CODEX_HOME')
    codex.routing(['--clean', 'exec', 'hi'])
    assert os.environ['CODEX_HOME'] == str(home / '.codex-clean')
    os.environ['CODEX_HOME'] = str(home / 'explicit')
    codex.routing(['--personal', 'exec', 'hi'])
    assert os.environ['CODEX_HOME'] == str(home / 'explicit')


def test_interactive_and_help_keep_the_home_unset(home):
    codex.routing(['exec', '--help'])
    codex.routing([])
    assert 'CODEX_HOME' not in os.environ


def test_a_personal_session_resumes_in_the_personal_home(home):
    session = home / '.codex/sessions/2026'
    session.mkdir(parents=True)
    (session / 'rollout-1-abc.jsonl').write_text('{}\n')
    codex.routing(['exec', 'resume', 'abc'])
    assert os.environ['CODEX_HOME'] == str(home / '.codex')


def test_native_is_never_the_wrapper_itself(monkeypatch):
    monkeypatch.setenv('CODEX_REAL', '/x/codex')
    assert codex.native() == '/x/codex'
