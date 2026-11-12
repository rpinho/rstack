import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'harness'))
from agent_executor import codex_sandbox, command
import pytest


def test_codex_command_preserves_paths_and_sandbox():
    cmd = command('codex', '/tools/codex cli', 'gpt-6.1-sol', 'low', '/work with spaces', '/last message')
    assert cmd == ['/tools/codex cli', 'exec', '--ignore-user-config', '--skip-git-repo-check',
                   '--cd', '/work with spaces', '-m', 'gpt-6.1-sol', '-c', 'model_reasoning_effort=low',
                   '--sandbox', 'workspace-write', '-o', '/last message', '-']


def test_claude_command_has_budget_and_explicit_tools():
    cmd = command('claude', 'claude', 'claude-haiku-5-5', 'low', '/work', '/last', '.50')
    assert cmd[:5] == ['claude', '-p', '--model', 'claude-haiku-5-5', '--effort']
    assert cmd[cmd.index('--max-budget-usd')+1] == '.50'
    assert cmd[cmd.index('--permission-mode')+1] == 'acceptEdits'
    assert cmd[cmd.index('--allowedTools')+1] == 'Read,Write,Edit'
    assert '--no-session-persistence' in cmd and '--strict-mcp-config' in cmd
    with pytest.raises(ValueError):
        command('typo', 'cli', 'model', 'low', '/work', '/last')


def test_claude_launcher_binds_route_and_outcome(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    jobs = tmp_path/'jobs'; jobs.mkdir()
    (jobs/'fixture.md').write_text('synthetic fixture')
    roles = tmp_path/'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    fake = tmp_path/'fake-cli'
    fake.write_text('#!'+sys.executable+'\nimport sys\nprint("fixture")\nsys.exit(7)\n')
    fake.chmod(0o755)
    import os
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path/'registry'),
               RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1')
    proc = subprocess.run(['zsh', str(repo/'tools/launch.sh'), 'fixture', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 7, proc.stderr
    log = (jobs/'fixture.log').read_text()
    outcome = json.loads(next(line.split(' ', 1)[1] for line in log.splitlines() if line.startswith('MODEL_OUTCOME ')))
    assert outcome['executor'] == 'claude' and outcome['exit_code'] == 7
    assert (jobs/'fixture.last.md').read_text() == 'fixture\n'


def test_claude_result_error_cannot_be_a_successful_exit(tmp_path):
    import os
    repo = Path(__file__).resolve().parents[1]
    fake = tmp_path/'fake-cli'
    fake.write_text('#!'+sys.executable+'\nprint(\'{"is_error":true,"subtype":"error_max_budget_usd"}\')\n')
    fake.chmod(0o755)
    proc = subprocess.run([sys.executable, str(repo/'harness/agent_executor.py'),
        '--backend', 'claude', '--executable', str(fake), '--model', 'fixture',
        '--effort', 'low', '--directory', str(tmp_path), '--output', str(tmp_path/'last')],
        capture_output=True, timeout=10)
    assert proc.returncode == 1


def test_toy_timeout_terminates_its_owned_process_group(tmp_path):
    import os
    import signal
    import time
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'examples'))
    from toy_worker import launch
    pidfile = tmp_path/'pid'
    worker = tmp_path/'worker.py'
    worker.write_text('import os,time\nfrom pathlib import Path\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(60)\n')
    assert launch([sys.executable, str(worker)], dict(os.environ), timeout=.5) == 124
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_allowed_tools_defaults_to_read_write_edit_and_can_be_widened():
    from importlib import util as _u
    repo = Path(__file__).resolve().parents[1]
    s = _u.spec_from_file_location('ae2', repo / 'harness/agent_executor.py')
    ae = _u.module_from_spec(s); s.loader.exec_module(ae)
    default = ae.command('claude', 'cli', 'm', 'high', '/w', '/o')
    assert default[default.index('--allowedTools') + 1] == 'Read,Write,Edit'
    wide = ae.command('claude', 'cli', 'm', 'high', '/w', '/o', '1.00', 'Read,Write,Edit,Bash')
    assert wide[wide.index('--allowedTools') + 1] == 'Read,Write,Edit,Bash'
    # There is no --max-turns on this CLI; a run is bounded by spend and the clock.
    assert '--max-turns' not in default and '--max-budget-usd' in default


def test_the_wall_clock_cap_stops_a_hanging_job_without_killing_the_launcher(tmp_path):
    """The cap must signal the CLI's own process group. If it signalled ours, it would take
    the launcher with it, which is how a bounded job turns into a dead lane.
    """
    import os
    repo = Path(__file__).resolve().parents[1]
    fake = tmp_path / 'hang-cli'
    fake.write_text('#!' + sys.executable + '\nimport time, sys\n'
                    'sys.stdout.write(\'{"partial":true}\'); sys.stdout.flush()\n'
                    'time.sleep(600)\n')
    fake.chmod(0o755)
    proc = subprocess.run([sys.executable, str(repo / 'harness/agent_executor.py'),
                           '--backend', 'claude', '--executable', str(fake), '--model', 'm',
                           '--effort', 'low', '--directory', str(tmp_path),
                           '--output', str(tmp_path / 'last'), '--timeout-seconds', '2'],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 124, proc.stderr
    assert 'wall-clock cap' in proc.stderr


def test_the_codex_sandbox_defaults_to_workspace_write(monkeypatch):
    """A public tool must not ship with the sandbox off. 11-07: the launcher the lanes run passes
    --dangerously-bypass-approvals-and-sandbox, and unifying the two launchers without noticing
    would have moved every lane job into a sandbox it had never run in."""
    monkeypatch.delenv('LAUNCH_CODEX_SANDBOX', raising=False)
    assert '--sandbox' in command('codex', 'codex', 'm', 'high', '/w', '/o')
    assert 'workspace-write' in command('codex', 'codex', 'm', 'high', '/w', '/o')
    assert '--dangerously-bypass-approvals-and-sandbox' not in command(
        'codex', 'codex', 'm', 'high', '/w', '/o')


def test_bypass_is_one_flag_and_not_a_sandbox_level(monkeypatch):
    """`bypass` turns off approvals AND the sandbox together; the others are --sandbox levels.
    Emitting `--sandbox bypass` would be silently accepted as an unknown value by nothing."""
    monkeypatch.delenv('LAUNCH_CODEX_SANDBOX', raising=False)
    argv = command('codex', 'codex', 'm', 'high', '/w', '/o', sandbox='bypass')
    assert '--dangerously-bypass-approvals-and-sandbox' in argv
    assert '--sandbox' not in argv


def test_the_host_can_set_the_sandbox_from_the_environment(monkeypatch):
    monkeypatch.setenv('LAUNCH_CODEX_SANDBOX', 'bypass')
    assert '--dangerously-bypass-approvals-and-sandbox' in command(
        'codex', 'codex', 'm', 'high', '/w', '/o')
    monkeypatch.setenv('LAUNCH_CODEX_SANDBOX', 'read-only')
    assert ['--sandbox', 'read-only'] == command(
        'codex', 'codex', 'm', 'high', '/w', '/o')[-5:-3]


def test_an_unknown_sandbox_is_refused_rather_than_passed_through(monkeypatch):
    monkeypatch.setenv('LAUNCH_CODEX_SANDBOX', 'off')
    with pytest.raises(ValueError):
        command('codex', 'codex', 'm', 'high', '/w', '/o')
    with pytest.raises(ValueError):
        codex_sandbox('--sandbox=none')


def test_a_headless_claude_job_is_marked_unattended(tmp_path):
    """11-11: a hook's ask prompts even with permissions bypassed, and nobody answers a headless job.
    RSTACK_UNATTENDED=1 makes every rstack hook deny with a reason instead."""
    repo = Path(__file__).resolve().parents[1]
    fake = tmp_path/'fake-cli'
    fake.write_text('#!'+sys.executable+'\nimport json, os\n'
                    'print(json.dumps({"is_error": False, "subtype": "success",'
                    ' "result": os.environ.get("RSTACK_UNATTENDED", "")}))\n')
    fake.chmod(0o755)
    subprocess.run([sys.executable, str(repo/'harness/agent_executor.py'),
        '--backend', 'claude', '--executable', str(fake), '--model', 'fixture',
        '--effort', 'low', '--directory', str(tmp_path), '--output', str(tmp_path/'last')],
        capture_output=True, timeout=10)
    assert json.loads((tmp_path/'last').read_text())['result'] == '1'


def test_a_job_runs_only_where_the_osascript_shim_comes_first(tmp_path):
    """11-12: a Codex job deleted through Finder and the owner heard the trash sound. The shim in
    ~/.local/bin makes that silent, but only when it is the osascript the job finds."""
    from agent_executor import shim_first
    home = tmp_path / 'home'
    shim = home / '.local/bin/osascript'
    assert shim_first(home, lambda name: '/usr/bin/osascript') is None          # no shim installed: no rule
    shim.parent.mkdir(parents=True)
    shim.write_text('#!/bin/sh\n')
    assert shim_first(home, lambda name: str(shim)) is None
    assert '/usr/bin/osascript' in shim_first(home, lambda name: '/usr/bin/osascript')
