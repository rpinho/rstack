"""canary: pass needs exit 0 and OK in the answer; alerts fire on transitions only; the report counts."""
import importlib.machinery
import importlib.util
import json
import os
import stat
from datetime import datetime, timezone

from rstack_hookcall import TOOLS


def load():
    loader = importlib.machinery.SourceFileLoader('canary', str(TOOLS / 'canary'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


c = load()


def test_judge_pass_and_fail_reasons():
    assert c.judge(0, '{"result": "OK"}', '', False, 120) == (True, '')
    assert c.judge(0, 'OK', 'Authentication required', False, 120) == (False, 'Authentication required')
    assert c.judge(1, '', 'Please sign in', False, 120)[1] == 'sign-in required'
    assert c.judge(0, '{"is_error": true, "result": "time limit"}', '', False, 120) == (False, 'time limit')
    assert c.judge(0, 'nope', '', False, 120)[0] is False
    assert c.judge(124, '', '', True, 5) == (False, 'timeout after 5s')


def test_clean_strips_urls_and_tokens():
    out = c.clean('visit https://x.example/a?b=1 key ' + 'a' * 40)
    assert 'http' not in out and 'a' * 40 not in out


def test_transitions_alert_once_then_daily_then_recover():
    st, row = {}, dict(host='h', probe='p', ok=False, reason='boom')
    assert c.transition(st, row, 1000) == 'canary h: p failed: boom'
    assert c.transition(st, row, 1000 + 3600) is None
    assert c.transition(st, row, 1000 + c.DAY + 1) is not None
    assert c.transition(st, dict(row, ok=True, reason=''), 1000 + c.DAY + 5) == 'canary h: p recovered'
    assert c.transition(st, dict(row, ok=True, reason=''), 1000 + c.DAY + 9) is None


def fake(path, body):
    path.write_text('#!/bin/sh\n' + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_run_and_report(tmp_path, monkeypatch):
    bin_ = tmp_path / 'bin'
    bin_.mkdir()
    fake(bin_ / 'claude', 'cat >/dev/null; echo \'{"result": "OK"}\'\n')
    fake(bin_ / 'agy', 'echo "Authentication required" >&2; exit 1\n')
    fake(bin_ / 'push', 'echo "$1" >> %s\n' % (tmp_path / 'pushed'))
    cfg = tmp_path / 'cfg.json'
    cfg.write_text(json.dumps(dict(host='h1', probes=['claude', 'agy'], timeout=20, notify='push')))
    monkeypatch.setenv('CANARY_CONFIG', str(cfg))
    monkeypatch.setenv('CANARY_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('PATH', str(bin_) + os.pathsep + os.environ['PATH'])
    assert c.main(['run']) == 0
    assert c.main(['run']) == 0
    assert (tmp_path / 'pushed').read_text().splitlines() == ['canary h1: agy failed: Authentication required']
    rows = [json.loads(l) for l in (tmp_path / 'state' / 'canary.jsonl').read_text().splitlines()]
    assert len(rows) == 4 and {r['probe']: r['ok'] for r in rows} == {'claude': True, 'agy': False}
    assert c.main(['report', '--hours', '24']) == 0


def test_report_ignores_old_rows(tmp_path, capsys):
    led = tmp_path / 'l.jsonl'
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    led.write_text(json.dumps(dict(ts='2020-01-01T00:00:00Z', host='h', probe='a', ok=False, reason='x')) + '\n'
                   + json.dumps(dict(ts=now, host='h', probe='a', ok=True, reason='')) + '\n')
    c.main(['report', '--ledger', str(led)])
    assert '1 pass' in capsys.readouterr().out
