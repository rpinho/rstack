"""resets-check: an unused reset is shown when it nears expiry or the week runs low (Ricardo, 11-19)."""
from datetime import date
import importlib.machinery
import importlib.util
import json
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'resets-check'
_loader = importlib.machinery.SourceFileLoader('resets_check', str(TOOL))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
rc = importlib.util.module_from_spec(_spec)
_loader.exec_module(rc)

TODAY = date(2026, 11, 19)
WEEKLY = {'provider': 'claude', 'kind': 'weekly reset', 'expires': '2026-12-10', 'how_to_use': 'claude.ai/settings/usage'}
FABLE = {'provider': 'claude', 'kind': 'Fable reset', 'expires': '2027-03-09', 'how_to_use': 'claude.ai/settings/usage'}


def test_expiry_trigger_is_seven_days_inclusive():
    near = dict(WEEKLY, expires='2026-11-26')      # 7 days out: shown
    far = dict(WEEKLY, expires='2026-11-27')       # 8 days out: quiet
    out, _ = rc.rows([near, far], TODAY, {})
    assert len(out) == 1 and 'expires in 7 d' in out[0] and '2026-11-26' in out[0]


def test_usage_trigger_is_seventy_percent_inclusive():
    out, _ = rc.rows([WEEKLY, FABLE], TODAY, {'claude': 70})
    assert len(out) == 2 and all('claude weekly usage at 70%' in l for l in out)
    out, _ = rc.rows([WEEKLY, FABLE], TODAY, {'claude': 69.9})
    assert out == []


def test_unknown_usage_and_far_expiry_stay_quiet():
    out, notify = rc.rows([WEEKLY, FABLE], TODAY, {'claude': None})
    assert out == [] and notify == []


def test_used_or_expired_resets_never_show():
    used = dict(WEEKLY, expires='2026-11-20', used=True)
    gone = dict(WEEKLY, expires='2026-11-18')
    out, notify = rc.rows([used, gone], TODAY, {'claude': 99})
    assert out == [] and notify == []


def test_phone_notice_two_days_before_expiry_only():
    two = dict(WEEKLY, expires='2026-11-21')
    three = dict(WEEKLY, expires='2026-11-22')
    _, notify = rc.rows([two, three], TODAY, {})
    assert notify == [two]


def test_row_shape_fits_the_asks_waiting_hook():
    out, _ = rc.rows([dict(WEEKLY, expires='2026-11-20')], TODAY, {})
    fields = out[0].split('\t')
    assert fields[0] == 'reset' and fields[1] == 'claude weekly reset' and 'use it: claude.ai/settings/usage' in fields[2]


def test_usage_file_is_read_only_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv('RESETS_USAGE_DIR', str(tmp_path))
    (tmp_path / 'claude.json').write_text(json.dumps({'weekly_percent': 81, 'at': 1000.0}))
    assert rc.usage('claude', 1000.0 + 3600) == 81
    assert rc.usage('claude', 1000.0 + 25 * 3600) is None


def test_mark_used_and_full_run_write_the_list(tmp_path, monkeypatch):
    reg = tmp_path / 'resets.json'
    reg.write_text(json.dumps({'resets': [dict(WEEKLY, expires=date.today().isoformat())]}))
    state = tmp_path / 'state'
    sent = tmp_path / 'sent.txt'
    stub = tmp_path / 'notify'
    stub.write_text('#!/bin/sh\necho "$1" >> {}\n'.format(sent))
    stub.chmod(0o755)
    for k, v in dict(RESETS_REGISTRY=str(reg), RSTACK_STATE_DIR=str(state), RSTACK_HOST='testhost',
                     RESETS_NOTIFY=str(stub), RESETS_USAGE_DIR=str(tmp_path / 'none')).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(rc, 'codex_percent', lambda now: None)
    assert rc.main([]) == 0
    listed = (state / 'asks-waiting' / 'testhost-resets.tsv').read_text()
    assert 'claude weekly reset' in listed and 'expires in 0 d' in listed
    assert sent.read_text().count('Unused claude weekly reset') == 1
    assert rc.main([]) == 0                      # a second run does not notify again
    assert sent.read_text().count('Unused claude weekly reset') == 1
    assert rc.main(['--mark-used', 'claude', 'weekly reset']) == 0
    assert rc.main([]) == 0
    assert (state / 'asks-waiting' / 'testhost-resets.tsv').read_text() == ''
