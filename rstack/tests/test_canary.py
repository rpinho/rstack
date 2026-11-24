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


def push_cfg(tmp_path, **kw):
    return dict(push=dict(ok_file=str(tmp_path / 'ok'), failed_file=str(tmp_path / 'failed'),
                          down_file=str(tmp_path / 'st' / 'PUSH_DOWN'), min_remaining=25, **kw))


def account(left, reset=1795400000):
    return {'limits': {'messages': 250}, 'stats': {'messages_remaining': left, 'reset_at': reset}}


def test_push_probe_quota(tmp_path, monkeypatch):
    cfg = push_cfg(tmp_path)
    monkeypatch.setattr(c, 'fetch_account', lambda: account(200))
    assert c.probe_push(cfg)[:2] == (True, '')
    monkeypatch.setattr(c, 'fetch_account', lambda: account(3))
    ok, reason, _ = c.probe_push(cfg)
    assert not ok and 'quota 3 left of 250' in reason and 'resets 20' in reason and 'Z' in reason


def test_push_probe_marker_files(tmp_path, monkeypatch):
    cfg = push_cfg(tmp_path)
    monkeypatch.setattr(c, 'fetch_account', lambda: account(200))
    ok_f, bad_f = tmp_path / 'ok', tmp_path / 'failed'
    bad_f.write_text('2026-11-23T10:00:00Z 429 daily limit\nsecond line\n')
    ok, reason, _ = c.probe_push(cfg)
    assert not ok and reason == 'last push failed: 2026-11-23T10:00:00Z 429 daily limit'
    ok_f.write_text('x\n')
    os.utime(ok_f, (1, 1))
    os.utime(bad_f, (2, 2))
    assert c.probe_push(cfg)[0] is False
    os.utime(ok_f, (3, 3))
    assert c.probe_push(cfg)[0] is True


def test_push_probe_network_error_names_type_only(tmp_path, monkeypatch):
    def boom():
        raise OSError('secret-host-detail')
    monkeypatch.setattr(c, 'fetch_account', boom)
    ok, reason, _ = c.probe_push(push_cfg(tmp_path))
    assert not ok and reason == 'ntfy account unreadable: OSError'


def test_push_fail_writes_down_file_pass_leaves_it(tmp_path, monkeypatch):
    cfg = dict(push_cfg(tmp_path), host='h')
    down = tmp_path / 'st' / 'PUSH_DOWN'
    monkeypatch.setattr(c, 'fetch_account', lambda: account(0))
    row = c.run_probe('push', cfg)
    assert row['ok'] is False and 'quota 0 left' in down.read_text() and down.read_text().count('\n') == 1
    down.write_text('old\n')
    monkeypatch.setattr(c, 'fetch_account', lambda: account(0))
    c.run_probe('push', cfg)
    assert down.read_text() != 'old\n' and down.read_text().count('\n') == 1
    down.write_text('keep\n')
    monkeypatch.setattr(c, 'fetch_account', lambda: account(200))
    assert c.run_probe('push', cfg)['ok'] is True
    assert down.read_text() == 'keep\n'
