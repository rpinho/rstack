"""Fleet inventory and findings from recorded command shapes; never execute ssh in tests."""
import contextlib
import hashlib
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
def outputs():
    return {}


@pytest.fixture
def host(tmp_path, monkeypatch, outputs):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    # Fixture PIDs must never resolve to real Linux processes, including in the SSH source.
    path_exists = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: False if str(path).startswith('/proc/') else path_exists(path))
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
        if tuple(argv) in outputs:
            text = outputs[tuple(argv)]
        elif argv == ['ps', '-axo', 'pid,ppid,command']:
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
        elif argv == ['tmux', 'list-panes', '-a', '-F', '#{session_name}\t#{pane_current_path}']:
            text = 'lane-a\t{}\n'.format(tmp_path / 'work')
        elif argv[0] == 'lsof':
            text = 'p{}\nn{}\n'.format(argv[3], tmp_path / 'work')
        elif argv[:2] == ['tmux', 'list-panes']:
            text = (FIXTURES / 'tmux-panes.txt').read_text()
        elif argv == ['launchctl', 'list']:
            text = (FIXTURES / 'launchctl.txt').read_text()
        elif argv[:2] in (['zsh', '-lc'], ['zsh', '-ic']):
            if argv[2] == 'whence -p xurl':
                text = str(wrapper) + '\n'
            elif argv[2] == 'print -r -- "$PATH"':
                text = str(wrapper.parent) + ':/usr/bin:/bin\n'
            else:
                raise AssertionError(argv)
        elif argv[:5] == ['git', '-C', str(repo), 'rev-parse', '--verify']:
            text = ('d' if argv[5] == 'b' * 40 + ':harness' else 'c') * 40 + '\n'
        else:
            raise AssertionError('unexpected subprocess (including any ssh): {!r}'.format(argv))
        return subprocess.CompletedProcess(argv, 0, text, '')
    monkeypatch.setattr(fleet.subprocess, 'run', run)
    return cfg, calls


def checked(cfg):
    snapshot = fleet.collect(cfg)
    fleet.compare_with_repo(snapshot, cfg['repo'])
    return snapshot


def test_collect_lists_all_sessions_agents_and_prefix_jobs(host):
    cfg, calls = host
    snap = checked(cfg)
    assert [s['name'] for s in snap['sessions']] == ['lane-a', 'empty']
    assert [p['pid'] for p in snap['sessions'][0]['processes']] == [40, 50]
    assert [a['pid'] for a in snap['agents']] == [40, 50, 60, 80]
    assert [j['label'] for j in snap['launchd']] == ['com.example.daily', 'com.example.worker']
    assert not snap['errors']
    assert len([c for c in calls if c[:2] == ['ps', 'eww']]) == 4
    bad = fleet.findings(snap)
    assert [(r['check'], r['subject'].split()[0]) for r in bad] == [
        ('launcher', 'pid=60'), ('launcher', 'pid=80')]


def synthetic_skill_pack(dest):
    dest.mkdir(parents=True)
    (dest / 'passing').mkdir()
    (dest / 'passing/SKILL.md').write_text('---\nname: passing\n---\nLocal fixture only.\n')
    (dest / 'LICENSE').write_text('MIT License\n')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {'version': 1, 'repo': 'https://example.invalid/pack', 'commit': 'a' * 40,
                'tree': 'b' * 40, 'acceptance': {'state': 'accepted'},
                'license': {'spdx': 'MIT', 'path': 'LICENSE.md', 'sha256': sha(dest / 'LICENSE')},
                'skills': [{'name': 'passing', 'source': 'skills/passing',
                            'files': [{'path': 'SKILL.md', 'sha256': sha(dest / 'passing/SKILL.md')}]}]}
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    (dest / '.skills-vendor.json').write_text(json.dumps({
        'manifest': manifest, 'manifest_sha256': hashlib.sha256(canonical).hexdigest()}))


@pytest.mark.parametrize('location', ['.claude', '.codex', '.agents', 'cwd'])
def test_skills_denied_in_every_global_location_and_agent_cwd(host, tmp_path, location):
    cfg, _ = host
    root = tmp_path / 'work/.claude/skills' if location == 'cwd' else Path.home() / location / 'skills'
    skill = root / 'paperclip'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: paperclip\n---\n')
    cfg['skills'] = {'denied': ['paperclip'], 'allowed_dirs': []}
    snapshot = checked(cfg)
    bad = [r for r in fleet.findings(snapshot) if r['check'] == 'skills']
    assert bad == [{'check': 'skills', 'subject': str(skill), 'detail': 'denied skill: paperclip'}]
    assert any(row['path'] == str(skill) for row in snapshot['skills']['directories'])


def test_skills_scans_tmux_pane_cwd_and_frontmatter_alias(host, outputs, tmp_path):
    cfg, _ = host
    skill = tmp_path / 'different/.claude/skills/renamed'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: paperclip\n---\n')
    outputs[('tmux', 'list-panes', '-a', '-F', '#{session_name}\t#{pane_current_path}')] = 'empty\t{}\n'.format(tmp_path / 'different')
    cfg['skills'] = {'denied': ['paperclip']}
    assert any(r['detail'] == 'denied skill: paperclip' for r in fleet.findings(checked(cfg)))


def test_skills_vendor_placement_and_failed_integrity_are_independent(host, tmp_path):
    cfg, _ = host
    dest = tmp_path / 'work/.claude/skills/vendor'
    synthetic_skill_pack(dest)
    cfg['skills'] = {'allowed_dirs': [str(tmp_path / 'other')]}
    bad = [r for r in fleet.findings(checked(cfg)) if r['check'] == 'skills']
    assert len(bad) == 1 and 'outside skills.allowed_dirs' in bad[0]['detail']
    cfg['skills']['allowed_dirs'] = [str(tmp_path / 'work')]
    assert not [r for r in fleet.findings(checked(cfg)) if r['check'] == 'skills']
    (dest / 'passing/extra').write_text('unexpected')
    bad = [r for r in fleet.findings(checked(cfg)) if r['check'] == 'skills']
    assert len(bad) == 1 and 'check failed' in bad[0]['detail'] and 'extra' in bad[0]['detail']
    (dest / 'passing/SKILL.md').write_text('tampered')
    snapshot = checked(cfg)
    assert not snapshot['skills']['packs'][0]['ok']


def test_skills_denied_directory_alias_cannot_hide_behind_seen_target(host, tmp_path):
    cfg, _ = host
    root = Path.home() / '.claude/skills'
    target = root / 'aaa'
    target.mkdir(parents=True)
    (target / 'SKILL.md').write_text('---\nname: passing\n---\n')
    (root / 'paperclip').symlink_to(target, target_is_directory=True)
    cfg['skills'] = {'denied': ['paperclip']}
    assert any(r['detail'] == 'denied skill: paperclip' for r in fleet.findings(checked(cfg)))


def test_skills_unreadable_agent_cwd_is_a_collection_finding(host, outputs):
    cfg, _ = host
    outputs[('lsof', '-a', '-p', '40', '-d', 'cwd', '-Fn')] = ''
    assert any('cwd for pid=40' in r['detail'] for r in fleet.findings(checked(cfg)))


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
    bad = fleet.findings(checked(cfg))
    assert [r['check'] for r in bad][-2:] == ['harness', 'tools']
    assert 'origin/main:harness=' in bad[-2]['detail']


def test_config_errors_and_missing_installs_are_findings(host):
    cfg, _ = host
    cfg.update(harness_stamp=str(Path(cfg['repo']) / 'missing'), install_map={},
               lane_registry=str(Path(cfg['repo']) / 'missing-registry'), label_prefix='')
    snap = checked(cfg)
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
    fixture_run = fleet.subprocess.run
    def notify(argv, **kw):
        if argv[:2] != ['tell-general', 'fyi']:
            return fixture_run(argv, **kw)
        assert argv[:2] == ['tell-general', 'fyi']
        alerts.append(argv)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(fleet.subprocess, 'run', notify)
    assert fleet.main(['--config', str(conf), '--json', '--alert']) == 1
    result = json.loads(capsys.readouterr().out)
    assert len(result['hosts']) == 2 and len(result['findings']) == 4
    assert remote_calls[0][0] == 'worker'
    assert len(alerts) == 1 and '4 findings on 2 hosts' in alerts[0][2]
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
    assert snapshot['harness_commit'] == 'a' * 40
    assert snapshot['installed'][0]['sha256']
    assert not any(argv[0] == 'git' for argv in calls)


def test_remote_skills_use_controller_checker_without_remote_install(host, monkeypatch, tmp_path):
    cfg, _ = host
    dest = tmp_path / 'work/.claude/skills/vendor'
    synthetic_skill_pack(dest)
    (dest / 'passing/SKILL.md').write_text('tampered')
    cfg['skills'] = {'denied': ['passing'], 'allowed_dirs': [str(tmp_path / 'work')]}
    fixture_run = fleet.subprocess.run

    def remote(argv, **kw):
        if argv[0] != 'ssh':
            return fixture_run(argv, **kw)
        remote_words = fleet.shlex.split(argv[-1])
        namespace = {'__name__': '__main__'}
        monkeypatch.setattr(fleet.sys, 'argv', ['-c', remote_words[4]])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(remote_words[3], namespace)
        return subprocess.CompletedProcess(argv, 0, output.getvalue(), '')

    monkeypatch.setattr(fleet.subprocess, 'run', remote)
    snapshot = fleet.remote_collect('worker', cfg)
    rows = snapshot['skills']['findings']
    assert len(rows) == 2
    assert any('denied skill: passing' in row['detail'] for row in rows)
    assert any('sha256 mismatch' in row['detail'] for row in rows)


def test_bare_process_path_with_no_xurl_passes(host, outputs):
    cfg, _ = host
    outputs[('ps', 'eww', '-p', '40')] = '40 claude PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME=/home/example\n'
    snapshot = checked(cfg)
    assert not [row for row in fleet.findings(snapshot) if row['check'] == 'path']
    assert [shell['xurl'] for shell in snapshot['shells']] == [cfg['wrapper']] * 2


@pytest.mark.parametrize('path_source', ['login', 'interactive', 'process'])
def test_stray_xurl_on_any_path_fails_even_when_shadowed(host, outputs, tmp_path, path_source):
    cfg, _ = host
    stray = tmp_path / 'opt/homebrew/bin/xurl'
    stray.parent.mkdir(parents=True)
    stray.write_text('#!/bin/sh\nexit 0\n')
    stray.chmod(0o755)
    path = str(Path(cfg['wrapper']).parent) + ':' + str(stray.parent)
    if path_source == 'process':
        outputs[('ps', 'eww', '-p', '40')] = '40 claude PATH=' + path + ' HOME=/home/example\n'
    else:
        mode = '-lc' if path_source == 'login' else '-ic'
        outputs[('zsh', mode, 'print -r -- "$PATH"')] = path + '\n'
    snapshot = checked(cfg)
    bad = [row for row in fleet.findings(snapshot) if row['check'] == 'path']
    assert bad == [{'check': 'path', 'subject': str(stray), 'detail': 'another xurl exists on PATH'}]
    assert {row['path'] for row in snapshot['xurls']} == {cfg['wrapper'], str(stray)}


@pytest.mark.parametrize('mode', ['-lc', '-ic'])
@pytest.mark.parametrize('resolved', ['', '/opt/homebrew/bin/xurl'])
def test_each_shell_must_resolve_the_wrapper(host, outputs, mode, resolved):
    cfg, _ = host
    outputs[('zsh', mode, 'whence -p xurl')] = resolved + '\n'
    bad = [row for row in fleet.findings(checked(cfg)) if row['check'] == 'path']
    assert len(bad) == 1 and bad[0]['subject'] == 'zsh ' + mode


def test_remote_runner_executor_and_tmux_app_server_chains(host, outputs):
    cfg, _ = host
    cfg.pop('launchers')
    outputs[('ps', '-axo', 'pid,ppid,command')] = (FIXTURES / 'ps-launchers.txt').read_text()
    outputs[('tmux', 'list-panes', '-a', '-F',
             '#{session_name}\t#{pane_pid}\t#{pane_start_command}')] = (FIXTURES / 'tmux-panes-launchers.txt').read_text()
    outputs[('tmux', 'list-sessions', '-F', '#{session_name}')] = 'app-session\nbare-session\n'
    snapshot = checked(cfg)
    bad = fleet.findings(snapshot)
    assert len(bad) == 1 and bad[0]['check'] == 'launcher' and bad[0]['subject'] == 'pid=110 session=bare-session'
    assert {agent['pid'] for agent in snapshot['agents']} == {40, 60, 70, 80, 90, 110}
    assert all(fleet.launched(agent, snapshot['launchers'], []) for agent in snapshot['agents'][:-1])


@pytest.mark.parametrize('command', [
    '/bin/sh /opt/state/job/run.sh',
    '/bin/sh -c \'/bin/sh "$1/run.sh" < "$1/prompt" > "$1/out.log" 2>&1; echo $?\' sh /opt/state/job',
    '/bin/sh -c /bin/sh "$1/run.sh" < "$1/prompt" > "$1/out.log" 2>&1; echo $? sh /opt/state/job',
    'python3 /opt/harness/agent_executor.py --backend claude',
])
def test_launcher_script_positions(command):
    assert fleet.launched({'chain': [command]}, fleet.DEFAULT_LAUNCHERS, [])


@pytest.mark.parametrize('command', [
    'codex exec "use run.sh or agent_executor.py"',
    '/bin/sh -c "echo run.sh"',
    '/bin/sh -c echo agent_executor.py',
    'python3 -c "print(\'agent_executor.py\')"',
])
def test_launcher_names_in_arguments_do_not_count(command):
    assert not fleet.launched({'chain': [command]}, fleet.DEFAULT_LAUNCHERS, [])


@pytest.mark.parametrize('command', ['codex app-server', 'codex resume task --remote unix:///tmp/server.sock'])
def test_app_server_needs_a_configured_launcher(command):
    agent = {'command': command, 'chain': [command, '/bin/zsh'], 'session': 'bare', 'pane_command': '/bin/zsh'}
    assert not fleet.launched(agent, ['/home/example/.local/bin/codex'], [])
    agent['pane_command'] = '/home/example/.local/bin/codex --some-option'
    assert fleet.launched(agent, ['/home/example/.local/bin/codex'], [])
    agent.update(command='codex exec task', chain=['codex exec task', '/bin/zsh'])
    assert not fleet.launched(agent, ['/home/example/.local/bin/codex'], [])


def test_remote_tools_use_controller_repo_hashes_once_per_file(host, monkeypatch, tmp_path, capsys):
    cfg, calls = host
    source = 'rstack/tools/fixture-tool'
    repo_tool = Path(cfg['repo']) / source
    repo_tool.write_text('controller version\n')
    local_target = Path(cfg['wrapper']).with_name('fixture-tool')
    local_target.write_bytes(repo_tool.read_bytes())
    cfg['install_map'][source] = str(local_target)
    stale_repo = tmp_path / 'stale-checkout'
    (stale_repo / source).parent.mkdir(parents=True)
    (stale_repo / source).write_text('stale version\n')
    remote_target = tmp_path / 'remote/bin/fixture-tool'
    remote_target.parent.mkdir(parents=True)
    remote_target.write_bytes((stale_repo / source).read_bytes())
    remote_cfg = dict(cfg, repo=str(stale_repo), install_map=dict(cfg['install_map'], **{source: str(remote_target)}))
    local = fleet.collect(cfg)
    remote = fleet.collect(remote_cfg)
    assert not any(argv[0] == 'git' for argv in calls)
    remote_tool = next(tool for tool in remote['installed'] if tool['target'] == str(remote_target))
    assert remote_tool['sha256'] == fleet.digest(stale_repo / source)
    monkeypatch.setattr(fleet, 'collect', lambda settings: local)
    monkeypatch.setattr(fleet, 'remote_collect', lambda host, settings: remote)
    conf = tmp_path / 'fleet.json'
    conf.write_text(json.dumps(dict(cfg, hosts=[{'name': 'local'},
        {'name': 'worker', 'ssh': 'worker', 'repo': str(stale_repo), 'install_map': remote_cfg['install_map']}])))
    assert fleet.main(['--config', str(conf), '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    bad = [row for row in result['findings'] if row['check'] == 'tools']
    assert bad == [{'host': 'worker', 'check': 'tools', 'subject': str(remote_target),
                    'detail': 'differs from repo ' + source}]
    assert all(argv[2] == cfg['repo'] for argv in calls if argv[0] == 'git')
    assert remote_tool['repo_sha256'] == fleet.digest(repo_tool) != remote_tool['sha256']


def test_install_target_aliases_report_drift_once_per_file(host):
    cfg, _ = host
    wrapper = Path(cfg['wrapper'])
    cfg['install_map']['rstack/tools/xurl'] = str(wrapper.parent / '..' / 'bin/xurl')
    wrapper.write_text('changed\n')
    snapshot = checked(cfg)
    assert len(snapshot['installed']) == 2  # Wrapper and policy, even with the aliased map entry.
    bad = [row for row in fleet.findings(snapshot) if row['check'] == 'tools']
    assert len(bad) == 1 and bad[0]['subject'] == cfg['wrapper']


def test_stamp_compares_real_harness_trees_not_commit_ids(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
            '-c', 'core.hooksPath=/dev/null', *args], check=True, text=True, capture_output=True).stdout.strip()
    git('init', '-q')
    (repo / 'harness').mkdir()
    (repo / 'harness/example.py').write_text('original\n')
    git('add', '.')
    git('commit', '-qm', 'initial harness')
    installed = git('rev-parse', 'HEAD')
    (repo / 'rstack').mkdir()
    (repo / 'rstack/example').write_text('tool-only change\n')
    git('add', '.')
    git('commit', '-qm', 'rstack only')
    git('update-ref', 'refs/remotes/origin/main', 'HEAD')
    snapshot = {'harness_commit': installed, 'installed': [], 'errors': [], 'agents': [],
                'shells': [], 'xurls': []}
    fleet.compare_with_repo(snapshot, repo)
    assert installed != git('rev-parse', 'origin/main')
    assert not fleet.findings(snapshot)
    (repo / 'harness/example.py').write_text('changed harness\n')
    git('add', '.')
    git('commit', '-qm', 'harness change')
    git('update-ref', 'refs/remotes/origin/main', 'HEAD')
    fleet.compare_with_repo(snapshot, repo)
    assert [row['check'] for row in fleet.findings(snapshot)] == ['harness']


def test_quoted_exec_pane_and_late_resume_count_as_launched():
    """11-14 live run: tmux showed a pane as '"exec ~/.local/bin/codex --remote SOCK -m M resume ID "'."""
    import runpy
    m = runpy.run_path(str(TOOLS / "fleet-lint"))
    pane = '"exec /home/u/.local/bin/codex --remote unix:///s.sock -m some-model resume 1 -C /w "'
    assert m['launcher_command'](pane, ['/home/u/.local/bin/codex'])
    assert m['attached_codex']('/opt/codex --remote unix:///s.sock -c k=v -m some-model resume 1')
    assert m['app_server_command']('/x/codex app-server daemon pid-update-loop')
