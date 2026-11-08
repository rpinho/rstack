"""Claude Science runs on the machine that holds the science.

Ricardo, 11-08: "Make sure that the research harness knows to use Claude Science in the m5." The
compute and the data moved there on 11-07, so the instance that reads that filesystem has to be
the one on that machine. cs.py drove only a local daemon.

Three things these pin, each from something that actually went wrong:

  * the port is never assumed. The daemon does not keep one (8765 -> 8000 was seen on 10-30 and
    again on 11-08), so the CLI is asked, on whichever machine owns the instance, and there is no
    fallback: a stale fallback is a connection refused with a misleading message.
  * 127.0.0.1 and a per-host cookie jar. Cookies ignore the port, so a session minted against
    localhost:18000 collides with this machine's own instance on localhost:8000. general lost a
    login to that on 11-08.
  * a host grant is checked on the host. CS_AUTO_READ is configured here but names paths THERE,
    and on 11-08 one of the configured roots did not exist on the host, so that grant would have
    been approved and read nothing. A review that reads nothing looks like a review that found
    nothing, which is the worst way for this to fail.
"""
import importlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(monkeypatch, **env):
    """cs.py reads its settings at import, so each case imports it fresh."""
    for key in ('CS_HOST', 'CS_BASE', 'CS_REMOTE_BIN', 'CS_TUNNEL_PORT', 'LAUNCH_SSH'):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop('cs', None)
    return importlib.import_module('cs')


def stub_ssh(tmp_path, monkeypatch, body):
    s = tmp_path / 'fake-ssh'
    s.write_text('#!/bin/sh\n' + body + '\n')
    s.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(s))
    return s


def test_a_tilde_in_the_remote_binary_is_expanded_by_the_remote_shell(monkeypatch):
    """shlex.quote('~/x') quotes the tilde, and the remote shell then looks for a file literally
    called '~'. That broke the first version of this against the real m5."""
    cs = load(monkeypatch, CS_HOST='m5')
    assert cs._remote_path('~/.claude-science/bin/claude-science') == \
        '$HOME/.claude-science/bin/claude-science'
    assert cs._remote_path('/opt/bin/cs') == '/opt/bin/cs'
    # A path needing quotes still gets them; only the home prefix is handed over bare.
    assert cs._remote_path('~/my bin/cs') == "$HOME/'my bin/cs'"


def test_the_cookie_jar_is_per_instance(monkeypatch):
    local = load(monkeypatch)
    remote = load(monkeypatch, CS_HOST='m5')
    assert Path(local.JAR).name == 'cookies.txt'
    assert Path(remote.JAR).name == 'cookies-m5.txt'
    assert local.JAR != remote.JAR, 'one jar for two instances is how a session gets crossed'


def test_a_host_that_is_not_an_ssh_alias_is_refused_at_import(monkeypatch):
    for bad in ('m5 -o ProxyCommand=id', 'm5;id', '-oProxyCommand=id'):
        with pytest.raises(SystemExit) as e:
            load(monkeypatch, CS_HOST=bad)
        assert 'CS_HOST must be an ssh alias' in str(e.value)


def test_the_remote_port_is_asked_for_not_assumed(tmp_path, monkeypatch):
    cs = load(monkeypatch, CS_HOST='m5')
    stub_ssh(tmp_path, monkeypatch, 'printf \'{"running": true, "port": 8000, "version": "0.1.72"}\'')
    cs.CS_SSH = str(tmp_path / 'fake-ssh')
    assert cs._remote_status()['port'] == 8000


@pytest.mark.parametrize('body,expect', [
    ('exit 255', 'cannot reach Claude Science on m5'),
    ("printf 'not json'", 'did not answer with JSON'),
    ("printf '{\"running\": false}'", 'is not running on m5'),
    ("printf '{\"running\": true}'", 'is not running on m5'),
])
def test_an_unusable_host_daemon_says_which_way_it_failed(tmp_path, monkeypatch, body, expect):
    cs = load(monkeypatch, CS_HOST='m5')
    stub_ssh(tmp_path, monkeypatch, body)
    cs.CS_SSH = str(tmp_path / 'fake-ssh')
    with pytest.raises(SystemExit) as e:
        cs._remote_status()
    assert expect in str(e.value)


def test_there_is_no_port_to_fall_back_to(monkeypatch):
    """8765 was the fallback and the daemon has moved twice since. A wrong port fails as a refused
    connection, which sends you to look at the network instead of at the daemon."""
    cs = load(monkeypatch)
    source = (ROOT / 'cs.py').read_text()
    assert 'localhost:8765' not in source, 'the stale fallback is gone'
    monkeypatch.setattr(cs, 'CS_BIN', '/nonexistent/claude-science')
    monkeypatch.delenv('CS_BASE', raising=False)
    with pytest.raises(SystemExit) as e:
        cs._discover_base()
    assert 'cannot ask' in str(e.value) and 'no port to fall back to' in str(e.value)


def test_cs_base_still_wins_over_everything(monkeypatch):
    cs = load(monkeypatch, CS_BASE='http://example.invalid:9', CS_HOST='m5')
    assert cs._discover_base() == 'http://example.invalid:9'


def test_a_host_grant_for_a_path_that_is_not_there_is_held(tmp_path, monkeypatch, capsys):
    """general's ask, and live in the real config on 11-08: an auto-readable root existed on the
    controller and not on the host."""
    cs = load(monkeypatch, CS_HOST='m5')
    inside = '/work/certificates'
    monkeypatch.setattr(cs, 'AUTO_READ', (inside + '/',))
    row = dict(requestId='r1', kind='host', tool_id='t', tool='host',
               requested_mode='ro', target=inside + '/cert.txt')
    monkeypatch.setattr(cs, 'pending', lambda fid: [row])
    monkeypatch.setattr(cs, 'host_has', lambda target: False)
    monkeypatch.setattr(cs, 'call', lambda *a, **k: pytest.fail('granted a read of nothing'))
    ok, held = cs.approve('f1')
    assert ok == [] and [r['kind'] for r in held] == ['host']
    out = capsys.readouterr().out
    assert 'is missing on m5' in out and 'read of nothing' in out


def test_an_unverifiable_path_is_held_too(tmp_path, monkeypatch, capsys):
    cs = load(monkeypatch, CS_HOST='m5')
    monkeypatch.setattr(cs, 'AUTO_READ', ('/data/',))
    monkeypatch.setattr(cs, 'pending', lambda fid: [dict(
        requestId='r1', kind='host', tool_id='t', requested_mode='ro', target='/data/x')])
    monkeypatch.setattr(cs, 'host_has', lambda target: None)
    monkeypatch.setattr(cs, 'call', lambda *a, **k: pytest.fail('granted an unverifiable read'))
    assert cs.approve('f1')[0] == []
    assert 'unverifiable on m5' in capsys.readouterr().out


def test_a_grant_for_a_path_that_is_there_goes_through(monkeypatch):
    cs = load(monkeypatch, CS_HOST='m5')
    monkeypatch.setattr(cs, 'AUTO_READ', ('/work/science/',))
    row = dict(requestId='r1', kind='host', tool_id='t', requested_mode='ro',
               target='/work/science/wave_1030')
    granted = set()

    def call(path, data=None, form=False):
        granted.update(r['requestId'] for r in data['responses'])
        return 200, '{}'

    monkeypatch.setattr(cs, 'host_has', lambda target: True)
    monkeypatch.setattr(cs, 'pending', lambda fid: [r for r in [row] if r['requestId'] not in granted])
    monkeypatch.setattr(cs, 'call', call)
    ok, held = cs.approve('f1')
    assert [r['kind'] for r in ok] == ['host'] and held == []


def test_without_a_host_nothing_is_checked_over_ssh(monkeypatch):
    cs = load(monkeypatch)
    monkeypatch.setattr(cs, 'AUTO_READ', ('/tmp/',))
    monkeypatch.setattr(cs, 'host_has', lambda target: pytest.fail('asked a host about a local run'))
    granted = set()
    monkeypatch.setattr(cs, 'pending', lambda fid: [r for r in [dict(
        requestId='r1', kind='host', tool_id='t', requested_mode='ro', target='/tmp/x')]
        if r['requestId'] not in granted])
    monkeypatch.setattr(cs, 'call', lambda path, data=None, form=False: (
        granted.update(r['requestId'] for r in data['responses']), (200, '{}'))[1])
    assert [r['kind'] for r in cs.approve('f1')[0]] == ['host']


def test_importing_cs_does_not_need_a_daemon(tmp_path, monkeypatch):
    """The first version of this change resolved the base at import. With no fallback port left,
    that made `import cs` exit, and 12 of these 14 tests died before their first assertion. Any
    module that only wants model_for() or approve() must be able to import this one."""
    stub_ssh(tmp_path, monkeypatch, 'exit 255')
    cs = load(monkeypatch, CS_HOST='m5', LAUNCH_SSH=str(tmp_path / 'fake-ssh'))
    assert cs._BASE is None, 'importing resolved the base; nothing asked for it yet'
    assert callable(cs.base)


def test_the_base_is_resolved_once_and_kept(monkeypatch):
    """The resolution opens an ssh tunnel under CS_HOST, so it must not happen per request."""
    cs = load(monkeypatch)
    calls = []
    monkeypatch.setattr(cs, '_discover_base', lambda: (calls.append(1), 'http://127.0.0.1:18000')[1])
    assert cs.base() == 'http://127.0.0.1:18000'
    assert cs.base() == 'http://127.0.0.1:18000'
    assert calls == [1]
