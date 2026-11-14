"""Fleet inventory and findings from recorded command shapes; never execute ssh in tests."""
import contextlib
import io
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

from rstack_hookcall import TOOLS

loader = importlib.machinery.SourceFileLoader('fleet_lint', str(TOOLS / 'fleet-lint'))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)
FIXTURES = Path(__file__).parent / 'fixtures/x-api'


@pytest.fixture
def host(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    (repo / 'rstack/tools').mkdir(parents=True)
    wrapper = tmp_path / 'bin/xurl'
    wrapper.parent.mkdir()
    wrapper.write_text('#!/bin/sh\nexit 86\n')
    wrapper.chmod(0o755)
    (repo / 'rstack/tools/xurl').write_bytes(wrapper.read_bytes())
    wrapper.with_name('xurl-policy').write_text('fixture policy')
    (repo / 'rstack/tools/xurl-policy').write_text('fixture policy')
    stamp = tmp_path / 'stamp.json'
    stamp.write_text(json.dumps({'commit': 'a' * 40}))
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'sessions': ['lane-a']}))
    cfg = {'repo': str(repo), 'wrapper': str(wrapper), 'harness_stamp': str(stamp),
           'lane_registry': str(registry), 'label_prefix': 'com.example.',
           'launchers': ['launch.sh'], 'install_map': {'rstack/tools/xurl': str(wrapper)}}
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        if argv == ['ps', '-axo', 'pid,ppid,command']:
            text = (FIXTURES / 'ps.txt').read_text()
        elif argv[:3] == ['ps', 'eww', '-p']:
            if argv[3] == '50':
                text = 'PID COMMAND\n50 codex PATH=/opt/homebrew/bin:/usr/bin HOME=/home/example\n'
            elif argv[3] == '60':
                text = 'PID COMMAND\n60 codex HOME=/home/example\n'
            else:
                text = 'PID COMMAND\n{} claude PATH={} HOME=/home/example\n'.format(argv[3], wrapper.parent)
        elif argv[:2] == ['tmux', 'list-sessions']:
            text = (FIXTURES / 'tmux-sessions.txt').read_text()
        elif argv[:2] == ['tmux', 'list-panes']:
            text = (FIXTURES / 'tmux-panes.txt').read_text()
        elif argv == ['launchctl', 'list']:
            text = (FIXTURES / 'launchctl.txt').read_text()
        elif argv == ['git', '-C', str(repo), 'rev-parse', 'origin/main^{commit}']:
            text = 'a' * 40 + '\n'
        else:
            raise AssertionError('unexpected subprocess (including any ssh): {!r}'.format(argv))
        return subprocess.CompletedProcess(argv, 0, text, '')
    monkeypatch.setattr(fleet.subprocess, 'run', run)
    return cfg, calls


def test_collect_lists_all_sessions_agents_and_prefix_jobs(host):
    cfg, calls = host
    snap = fleet.collect(cfg)
    assert [s['name'] for s in snap['sessions']] == ['lane-a', 'empty']
    assert [p['pid'] for p in snap['sessions'][0]['processes']] == [40, 50]
    assert [a['pid'] for a in snap['agents']] == [40, 50, 60, 80]
    assert [j['label'] for j in snap['launchd']] == ['com.example.daily', 'com.example.worker']
    assert not snap['errors']
    assert len([c for c in calls if c[:2] == ['ps', 'eww']]) == 4
    bad = fleet.findings(snap)
    assert [(r['check'], r['subject'].split()[0]) for r in bad] == [
        ('path', 'pid=50'), ('path', 'pid=60'), ('launcher', 'pid=60'), ('launcher', 'pid=80')]


def test_launcher_parent_chain_registry_and_prompt_mentions(host):
    cfg, _ = host
    snap = fleet.collect(cfg)
    a, b = snap['agents'][:2]
    assert fleet.launched(a, ['launch.sh'], [])
    assert fleet.launched(b, [], ['lane-a'])
    assert not fleet.launched(b, ['launch.sh'], [])
    assert not fleet.launched({'chain': ['codex exec "use launch.sh for work"']}, ['launch.sh'], [])
    assert not fleet.launched({'chain': ['bash -c "echo launch.sh"']}, ['launch.sh'], [])
    assert fleet.launched({'chain': ['/home/example/.local/bin/codex exec task']},
                          ['/home/example/.local/bin/codex'], [])


def test_stamp_and_each_installed_tool_report_drift(host):
    cfg, _ = host
    Path(cfg['harness_stamp']).write_text(json.dumps({'commit': 'b' * 40}))
    Path(cfg['wrapper']).write_text('changed')
    bad = fleet.findings(fleet.collect(cfg))
    assert [r['check'] for r in bad][-2:] == ['harness', 'tools']
    assert 'origin/main=' in bad[-2]['detail']


def test_config_errors_and_missing_installs_are_findings(host):
    cfg, _ = host
    cfg.update(harness_stamp=str(Path(cfg['repo']) / 'missing'), install_map={},
               lane_registry=str(Path(cfg['repo']) / 'missing-registry'), label_prefix='')
    snap = fleet.collect(cfg)
    assert len(snap['errors']) == 4
    assert any(r['check'] == 'harness' for r in fleet.findings(snap))


def test_process_path_uses_environment_key_not_command_text():
    assert fleet.process_path('42 command --PATH=bad PATH=/good:/ok USER=test') == '/good:/ok'
    assert fleet.process_path('42 command MYPATH=/bad') is None
    assert fleet.process_path('42 cmd PATH=/a path:/b HOME=/home/example') == '/a path:/b'
    assert not fleet.is_agent('grep codex file')


def test_registry_formats(tmp_path):
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps(['a', {'tmux_session': 'b'}]))
    assert fleet.registry_sessions(str(registry)) == ['a', 'b']
    root = tmp_path / 'root'
    (root / 'lanes/toy').mkdir(parents=True)
    (root / 'lanes/toy/SESSION.json').write_text(json.dumps({'tmux_session': 'toy'}))
    assert fleet.registry_sessions(str(root)) == ['toy']


def test_main_two_hosts_json_alert_summary_and_remote_failure(host, monkeypatch, tmp_path, capsys):
    cfg, calls = host
    local_collect = fleet.collect
    local = local_collect(cfg)
    remote_calls = []
    def remote(name, settings):
        remote_calls.append((name, settings))
        return local
    monkeypatch.setattr(fleet, 'remote_collect', remote)
    # Snapshot collection was already tested; this checks routing and presentation only.
    monkeypatch.setattr(fleet, 'collect', lambda c: local)
    conf = tmp_path / 'fleet.json'
    conf.write_text(json.dumps(dict(cfg, ssh_host='worker')))
    alerts = []
    def notify(argv, **kw):
        assert argv[:2] == ['tell-general', 'fyi']
        alerts.append(argv)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(fleet.subprocess, 'run', notify)
    assert fleet.main(['--config', str(conf), '--json', '--alert']) == 1
    result = json.loads(capsys.readouterr().out)
    assert len(result['hosts']) == 2 and len(result['findings']) == 8
    assert remote_calls[0][0] == 'worker'
    assert len(alerts) == 1 and '8 findings on 2 hosts' in alerts[0][2]
    def unreachable(*args):
        raise subprocess.TimeoutExpired('ssh', 10)
    monkeypatch.setattr(fleet, 'remote_collect', unreachable)
    assert fleet.main(['--config', str(conf), '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert any(r['host'] == 'ssh' and r['check'] == 'collection' for r in result['findings'])


def test_clean_report_exit_zero_and_missing_config_exit_one(host, monkeypatch, tmp_path, capsys):
    cfg, _ = host
    snap = fleet.collect(cfg)
    snap['agents'] = snap['agents'][:1]
    monkeypatch.setattr(fleet, 'collect', lambda c: snap)
    conf = tmp_path / 'fleet.json'
    conf.write_text(json.dumps(dict(cfg, hosts=[{'name': 'local'}])))
    assert fleet.main(['--config', str(conf)]) == 0
    output = capsys.readouterr().out
    assert 'TMUX empty' in output and 'LAUNCHD com.example.daily' in output and 'pid=40' in output
    assert fleet.main(['--config', str(tmp_path / 'missing'), '--json']) == 1


def test_remote_command_is_read_only_python_no_real_ssh(monkeypatch):
    seen = []
    def run(argv, **kw):
        seen.append(argv)
        assert argv[:7] == ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10']
        assert argv[7:9] == ['--', 'worker']
        remote_words = fleet.shlex.split(argv[9])
        assert remote_words[:3] == ['python3', '-B', '-c']
        source = remote_words[3]
        assert 'print(json.dumps(collect(json.loads(sys.argv[1]))))' in source
        # The collector has no calls to this remote helper or main, and no file writes.
        assert "if __name__ == '__main__':\n    sys.exit(main())" not in source
        return subprocess.CompletedProcess(argv, 0, '{}', '')
    monkeypatch.setattr(fleet.subprocess, 'run', run)
    assert fleet.remote_collect('worker', {'repo': '~/src/rstack'}) == {}
    assert len(seen) == 1


def test_remote_collector_runs_standalone_with_fixture_commands(host, monkeypatch):
    cfg, calls = host
    fixture_run = fleet.subprocess.run
    def run(argv, **kw):
        if argv[0] != 'ssh':
            return fixture_run(argv, **kw)
        remote_words = fleet.shlex.split(argv[-1])
        output = io.StringIO()
        # SSH's interpreter has no local __file__ or imported fleet module.
        namespace = {'__name__': '__main__'}
        monkeypatch.setattr(fleet.sys, 'argv', ['-c', remote_words[4]])
        with contextlib.redirect_stdout(output):
            exec(remote_words[3], namespace)
        return subprocess.CompletedProcess(argv, 0, output.getvalue(), '')
    monkeypatch.setattr(fleet.subprocess, 'run', run)
    snapshot = fleet.remote_collect('worker', cfg)
    assert not snapshot['errors'] and len(snapshot['agents']) == 4
    assert snapshot['harness_commit'] == snapshot['origin_main']
