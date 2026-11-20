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


def _launch_claude_fixture(tmp_path, **extra):
    """Run tools/launch.sh with a fake claude CLI that records its argv; returns (proc, argv)."""
    import os
    repo = Path(__file__).resolve().parents[1]
    jobs = tmp_path / 'jobs'; jobs.mkdir(exist_ok=True)
    (jobs / 'fixture.md').write_text('synthetic fixture')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    argv_file = tmp_path / 'argv.json'
    fake = tmp_path / 'fake-cli'
    fake.write_text('#!' + sys.executable + '\nimport json, sys\n'
                    'open(' + repr(str(argv_file)) + ', "w").write(json.dumps(sys.argv[1:]))\n'
                    'print(\'{"is_error":false,"subtype":"success","result":"ok"}\')\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ('AGENT_BACKEND', 'LAUNCH_BACKEND')}
    env.update(LAUNCH_CLAUDE=str(fake), LAUNCH_ARTIFACT_DIR=str(jobs),
               LAUNCH_STATE=str(tmp_path / 'registry'), RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1')
    env.update(extra)
    proc = subprocess.run(['zsh', str(repo / 'tools/launch.sh'), 'fixture', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=30)
    argv = json.loads(argv_file.read_text()) if argv_file.exists() else None
    return proc, argv


def test_launch_backend_selects_claude_and_passes_its_bounds(tmp_path):
    """LAUNCH_BACKEND is the launcher's own name for AGENT_BACKEND. A Claude job gets the tool list
    and the wall-clock cap from the launcher, not just the executor's defaults."""
    proc, argv = _launch_claude_fixture(tmp_path, LAUNCH_BACKEND='claude',
                                        LAUNCH_CLAUDE_TOOLS='Read,Write,Edit,Bash')
    assert proc.returncode == 0, proc.stderr
    assert argv[argv.index('--allowedTools') + 1] == 'Read,Write,Edit,Bash'
    log = (tmp_path / 'jobs' / 'fixture.log').read_text()
    outcome = json.loads(next(l.split(' ', 1)[1] for l in log.splitlines() if l.startswith('MODEL_OUTCOME ')))
    assert outcome['executor'] == 'claude'


def test_launch_backend_names_that_disagree_refuse_before_any_run(tmp_path):
    proc, argv = _launch_claude_fixture(tmp_path, LAUNCH_BACKEND='claude', AGENT_BACKEND='codex')
    assert proc.returncode == 2 and 'disagree' in proc.stderr and argv is None
    proc, argv = _launch_claude_fixture(tmp_path, LAUNCH_BACKEND='claude', LAUNCH_TIMEOUT_SECONDS='soon')
    assert proc.returncode == 2 and 'whole seconds' in proc.stderr and argv is None


def test_launch_timeout_reaches_the_executor(tmp_path):
    """The clock cap is passed through: a hanging Claude job launched with a 2 s cap stops with 124."""
    import os
    repo = Path(__file__).resolve().parents[1]
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    (jobs / 'fixture.md').write_text('synthetic fixture')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    fake = tmp_path / 'hang-cli'
    fake.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(600)\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ('AGENT_BACKEND', 'LAUNCH_BACKEND')}
    env.update(LAUNCH_BACKEND='claude', LAUNCH_CLAUDE=str(fake), LAUNCH_ARTIFACT_DIR=str(jobs),
               LAUNCH_STATE=str(tmp_path / 'registry'), RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1',
               LAUNCH_TIMEOUT_SECONDS='2')
    proc = subprocess.run(['zsh', str(repo / 'tools/launch.sh'), 'fixture', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 124, proc.stderr


@pytest.mark.parametrize('provider,flag', [('openrouter', 'RH_ALLOW_OPENROUTER'), ('gemini', 'RH_ALLOW_GEMINI_API')])
def test_a_metered_route_is_refused_unless_its_in_flight_override_is_set(tmp_path, monkeypatch, provider, flag):
    # 11-19 Ricardo: "No pay-as-you-go. Do NOT top up OpenRouter."
    import os
    monkeypatch.setenv('LAUNCH_PROVIDER', provider)
    monkeypatch.delenv(flag, raising=False)
    with pytest.raises(ValueError, match='pay-as-you-go.*' + flag + '=1'):
        command('codex', 'codex', 'vendor/model', 'low', '/w', '/o')
    repo = Path(__file__).resolve().parents[1]
    fake = tmp_path / 'fake-codex'
    fake.write_text('#!' + sys.executable + '\nraise SystemExit("must not run")\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != flag}
    proc = subprocess.run([sys.executable, str(repo/'harness/agent_executor.py'), '--backend', 'codex',
        '--executable', str(fake), '--model', 'vendor/model', '--effort', 'low',
        '--directory', str(tmp_path), '--output', str(tmp_path/'last')],
        input='', env=dict(env, LAUNCH_PROVIDER=provider), capture_output=True, text=True, timeout=10)
    assert proc.returncode == 78 and 'pay-as-you-go' in proc.stderr and 'must not run' not in proc.stderr
    monkeypatch.setenv(flag, '1')
    assert 'model_provider="{}"'.format(provider) in command('codex', 'codex', 'm', 'low', '/w', '/o')


def test_agy_command_is_print_mode_with_the_prompt_as_its_argument():
    cmd = command('agy', 'agy', 'gemini-fixture', 'high', '/w', '/o', prompt='Referee this.')
    assert cmd[:5] == ['agy', '-p', 'Referee this.', '--output-format', 'json']
    assert cmd[cmd.index('--model') + 1] == 'gemini-fixture' and cmd[cmd.index('--effort') + 1] == 'high'
    assert '--model' not in command('agy', 'agy', 'default', 'none', '/w', '/o', prompt='x')
    plain = command('agy', 'agy', 'm', 'low', '/w', '/o', prompt='x')
    assert json.loads(plain[plain.index('--settings') + 1]) == {'permissions': {'allow': ['read_file(*)']}}
    # 11-19: agy refused --model gemini-3.8-flash-low with --effort high; the tier is the effort.
    assert '--effort' not in command('agy', 'agy', 'gemini-3.8-flash-low', 'high', '/w', '/o', prompt='x')
    shell = command('agy', 'agy', 'm', 'low', '/w', '/o', tools='Read,Write,Edit,Bash', prompt='x')
    assert json.loads(shell[shell.index('--settings') + 1]) == {'permissions': {'allow': ['read_file(*)', 'command(*)']}}


FAKE_TMUX = (
    'import os, subprocess, sys\n'
    'a = sys.argv[1:]\n'
    'if a[0] == "has-session":\n'
    '    sys.exit(0 if os.environ.get("FAKE_TMUX_SESSION") == "1" else 1)\n'
    'if a[0] == "new-window":\n'
    '    w = subprocess.Popen(a[-1], shell=True, start_new_session=True, stdin=subprocess.DEVNULL,\n'
    '                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, IN_TMUX_WINDOW="1"))\n'
    '    open(sys.argv[0] + ".pid", "w").write(str(w.pid))\n'
    '    print("@9")\n'
    'if a[0] == "kill-window":\n'
    '    import signal\n'
    '    os.killpg(int(open(sys.argv[0] + ".pid").read()), signal.SIGKILL)\n'
    'sys.exit(0)\n')
# Signed in, but only a tmux window can read the Keychain (the m5 on 11-19); SIGNED_OUT=1 means signed out everywhere.
KEYCHAIN_AGY = (
    'import json, os, sys, time\n'
    'if os.environ.get("IN_TMUX_WINDOW") != "1" or os.environ.get("SIGNED_OUT") == "1":\n'
    '    sys.stderr.write("Authentication required. Please visit the URL to log in:\\n")\n'
    '    sys.stderr.flush(); time.sleep(60)\n'
    'print(json.dumps({"status": "SUCCESS", "response": "via tmux: " + sys.argv[2], "error": ""}))\n')


def agy_run(tmp_path, body, timeout='0', **env):
    import os
    repo = Path(__file__).resolve().parents[1]
    fake = tmp_path / 'fake-agy'
    fake.write_text('#!' + sys.executable + '\n' + body)
    fake.chmod(0o755)
    tmux = tmp_path / 'fake-tmux'
    tmux.write_text('#!' + sys.executable + '\n' + FAKE_TMUX)
    tmux.chmod(0o755)
    return subprocess.run([sys.executable, str(repo/'harness/agent_executor.py'), '--backend', 'agy',
        '--executable', str(fake), '--model', 'gemini-fixture', '--effort', 'low',
        '--directory', str(tmp_path), '--output', str(tmp_path/'last'), '--timeout-seconds', timeout],
        input='the prompt', env=dict(os.environ, HOME=str(tmp_path), RH_AGY_TMUX=str(tmux), **env),
        capture_output=True, text=True, timeout=30)


def test_without_the_keychain_and_no_tmux_session_agy_says_where_to_run_it(tmp_path):
    proc = agy_run(tmp_path, KEYCHAIN_AGY)
    assert proc.returncode == 76
    assert 'no keychain access' in proc.stderr and "Ricardo's" not in proc.stderr


def test_agy_is_relayed_through_the_tmux_session_that_holds_the_keychain(tmp_path):
    proc = agy_run(tmp_path, KEYCHAIN_AGY, FAKE_TMUX_SESSION='1')
    assert proc.returncode == 0, proc.stderr
    assert json.loads((tmp_path/'last').read_text())['response'] == 'via tmux: the prompt'


def test_a_signed_out_agy_stops_at_once_and_names_ricardos_sign_in(tmp_path):
    # The real CLI prints an OAuth URL and then waits 60 s for a code nobody will paste.
    proc = agy_run(tmp_path, KEYCHAIN_AGY, FAKE_TMUX_SESSION='1', SIGNED_OUT='1')
    assert proc.returncode == 77
    assert "agy needs Ricardo's one-time interactive sign-in" in proc.stderr


def test_an_agy_result_is_saved_and_an_error_result_fails(tmp_path):
    ok = agy_run(tmp_path, 'import json, sys\nassert sys.argv[2] == "the prompt"\n'
                 'print(json.dumps({"status": "SUCCESS", "response": "fine", "error": ""}))\n')
    assert ok.returncode == 0, ok.stderr
    assert json.loads((tmp_path/'last').read_text())['response'] == 'fine'
    bad = agy_run(tmp_path, 'print(\'{"status":"ERROR","response":"","error":"quota"}\')\n')
    assert bad.returncode == 1 and 'quota' in bad.stderr
    denied = agy_run(tmp_path, 'print(\'{"status":"SUCCESS","response":"","denied_actions":[{"action":"read_file"}]}\')\n')
    assert denied.returncode == 1 and 'denied: read_file' in denied.stderr


def test_an_agy_quota_error_is_logged_with_its_model_and_tier(tmp_path):
    state = tmp_path / 'state'
    proc = agy_run(tmp_path, 'import sys\nsys.stderr.write("HTTP 429: RESOURCE_EXHAUSTED, try again in 5h\\n")\n'
                   'print(\'{"status":"ERROR","response":"","error":"429 quota exceeded"}\')\nsys.exit(1)\n',
                   RSTACK_STATE_DIR=str(state), RH_JOB='fixture-job')
    assert proc.returncode == 1
    row = json.loads((state / 'agy-quota.jsonl').read_text().splitlines()[-1])
    assert (row['model'], row['tier'], row['job']) == ('gemini-fixture', 'low', 'fixture-job')
    assert '429' in row['error'] and row['utc']
    ok = agy_run(tmp_path, 'print(\'{"status":"SUCCESS","response":"fine"}\')\n', RSTACK_STATE_DIR=str(state))
    assert ok.returncode == 0 and len((state / 'agy-quota.jsonl').read_text().splitlines()) == 1


@pytest.mark.parametrize('cap,expected', [('0', 'claude overflow via agy (weekly at 90%)'),
                                          ('1', 'claude cap: claude weekly at 90% >= 80% ceiling')])
def test_the_launcher_runs_a_claude_overflow_on_agy_and_logs_why(tmp_path, cap, expected):
    import os, time
    repo = Path(__file__).resolve().parents[1]
    jobs = tmp_path/'jobs'; jobs.mkdir()
    (jobs/'fixture.md').write_text('synthetic fixture')
    roles = tmp_path/'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['claude-opus-5-5']}, routes={
        'claude-opus-5-5': {'canonical': 'anthropic/claude-opus-5.5', 'cli': 'claude'}})))
    state = tmp_path/'state'; (state/'usage').mkdir(parents=True)
    (state/'usage/claude.json').write_text(json.dumps({'weekly_percent': 90, 'at': time.time()}))
    fake = tmp_path/'fake-agy'
    fake.write_text('#!'+sys.executable+'\nimport json, sys\nfrom pathlib import Path\n'
                    'Path(sys.argv[0] + ".argv").write_text(json.dumps(sys.argv))\n'
                    'print(json.dumps({"status": "SUCCESS", "response": "ok"}))\n')
    fake.chmod(0o755)
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_AGY=str(fake), LAUNCH_CLAUDE='/nonexistent-claude',
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path/'registry'), RH_ROLES_FILE=str(roles),
               FORCE_LAUNCH='1', RSTACK_STATE_DIR=str(state), RH_CLAUDE_OVERFLOW_PERCENT='85', RH_CLAUDE_CAP=cap)
    proc = subprocess.run(['zsh', str(repo/'tools/launch.sh'), 'fixture', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr
    argv = json.loads(Path(str(fake) + '.argv').read_text())
    assert argv[argv.index('--model') + 1] == 'claude-opus-5-5-high'
    log = (jobs/'fixture.log').read_text()
    assert expected in log
    receipt = json.loads((jobs/'fixture.log.selection.json').read_text())
    assert receipt['executor'] == 'agy' and receipt['model'] == 'claude-opus-5-5'


def test_codex_runs_without_an_openai_api_key_or_base_url(tmp_path):
    # 11-20: the lanes' launcher ran codex under `env -u OPENAI_BASE_URL -u OPENAI_API_KEY`; with either set,
    # codex can bill the API instead of the subscription. Now that the lanes run this executor, it does that.
    seen = tmp_path / 'env.json'
    fake = tmp_path / 'codex'
    fake.write_text('#!' + sys.executable + '\nimport json, os, sys\nsys.stdin.read()\n'
                    'json.dump(dict(os.environ), open(' + repr(str(seen)) + ', "w"))\n')
    fake.chmod(0o755)
    env = dict(__import__('os').environ, OPENAI_API_KEY='sk-should-not-pass', OPENAI_BASE_URL='http://x',
               KEEP_ME='1', LAUNCH_CODEX_SANDBOX='bypass')
    env.pop('LAUNCH_PROVIDER', None)
    done = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'harness/agent_executor.py'),
                           '--backend', 'codex', '--executable', str(fake), '--model', 'gpt-x', '--effort', 'low',
                           '--directory', str(tmp_path), '--output', str(tmp_path / 'last.md')],
                          input='prompt', env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    got = json.loads(seen.read_text())
    assert 'OPENAI_API_KEY' not in got and 'OPENAI_BASE_URL' not in got and got['KEEP_ME'] == '1'
