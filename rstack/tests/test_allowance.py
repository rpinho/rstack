"""Allowance reading and real launcher admission: local fixtures only, no model/network calls."""
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'rstack/tools/allowance'
spec = spec_from_loader('allowance', SourceFileLoader('allowance', str(TOOL)))
allowance = module_from_spec(spec)
spec.loader.exec_module(allowance)
NOW = int(time.time())
RESET = int(NOW + 7 * 86400)


def event(used=72, age=0, slot='primary', reset=RESET, **extra):
    limits = {'limit_id': 'codex', 'primary': None, 'secondary': None}
    limits[slot] = dict(used_percent=used, window_minutes=10080, resets_at=reset)
    limits.update(extra)
    return dict(timestamp=datetime.fromtimestamp(NOW - age, timezone.utc).isoformat(),
                type='event_msg', payload=dict(type='token_count', rate_limits=limits))


def rollout(root, rows, name='rollout-fixture.jsonl'):
    path = root / 'sessions/2026/11/17' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    return path


def test_newest_event_across_all_homes_not_newest_file_or_largest_percentage(tmp_path):
    old = rollout(tmp_path / '.codex', [event(used=100, age=3600)])
    fresh = rollout(tmp_path / 'elsewhere/codex-home', [event(used=0, slot='secondary')])
    os.utime(old, (NOW + 1000, NOW + 1000))
    os.utime(fresh, (NOW - 1000, NOW - 1000))
    data = allowance.read_allowance([tmp_path / '.codex', tmp_path / 'elsewhere/codex-home'], NOW)
    weekly = data['codex']
    assert weekly['weekly_used_percent'] == 0 and weekly['window'] == 'secondary'
    assert weekly['snapshot_age_seconds'] == 0 and weekly['resets_at'] == RESET
    assert weekly['source'] == str(fresh) and data['claude'] == 'unavailable'


def test_discover_nested_and_explicit_homes_and_print_json(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'outside'))
    monkeypatch.setenv('CODEX_HOMES', str(tmp_path / 'custom1') + os.pathsep + str(tmp_path / 'custom2'))
    for name in ('.codex', '.codex-clean', 'project/job/codex-home', 'outside', 'custom1', 'custom2'):
        rollout(tmp_path / name, [event()])
    assert set(allowance.homes()) == {tmp_path / name for name in (
        '.codex', '.codex-clean', 'project/job/codex-home', 'outside', 'custom1', 'custom2')}
    result = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and json.loads(result.stdout)['codex']['weekly_used_percent'] == 72
    assert not (tmp_path / '.local').exists()  # Reading is entirely read-only.


def test_skips_partial_null_wrong_provider_and_nonweekly_snapshots(tmp_path):
    root = tmp_path / 'home'
    path = rollout(root, [event(71, age=100), event(99, age=90, limit_id='codex_other'),
                          event(98, age=80, primary=dict(used_percent=98, window_minutes=300, resets_at=RESET)),
                          {'type': 'event_msg', 'payload': {'type': 'token_count', 'rate_limits': None}}])
    with path.open('a') as stream:
        stream.write('{"type":"token_count","rate_limits":')
    weekly = allowance.read_allowance([root], NOW)['codex']
    assert weekly['weekly_used_percent'] == 71 and weekly['snapshot_age_seconds'] == 100


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -1, 101, True, '86'])
def test_malformed_percent_is_not_usage(tmp_path, bad):
    rollout(tmp_path, [event(bad)])
    assert allowance.read_allowance([tmp_path], NOW)['codex'] == 'unavailable'


def test_reverse_reader_bounds_huge_prompt_lines(tmp_path):
    path = tmp_path / 'rollout.jsonl'
    with path.open('wb') as stream:
        stream.write(json.dumps(event()).encode() + b'\n')
        for _ in range(11):
            stream.write(b'x' * 1024 * 1024)
        stream.write(b'\n' + json.dumps(event(73)).encode() + b'\n')
    lines = list(allowance.reverse_lines(path))
    assert len(lines) == 3  # trailing empty line and both events; oversized prompt skipped
    assert [json.loads(row)['payload']['rate_limits']['primary']['used_percent'] for row in lines if row] == [73, 72]


@pytest.fixture
def env(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    bin_dir = home / '.local/bin'
    bin_dir.mkdir(parents=True)
    tmux = bin_dir / 'tmux'
    tmux.write_text('#!' + sys.executable + '''
import json, os, sys
args=sys.argv[1:]
with open(os.environ['TMUX_CALLS'], 'a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='display-message': print(os.environ.get('CURRENT_SESSION','job-this'))
elif args[0]=='list-panes':
    rows=os.environ.get('PANES','')
    if '#{@launch_lane}' in args[-1]:
        rows=''.join('\\t'.join(row.split('\\t')[:4]+['']+row.split('\\t')[4:])+'\\n' for row in rows.splitlines())
    print(rows,end='')
    if os.environ.get('TMUX_FAIL'):
        print(os.environ['TMUX_FAIL'], file=sys.stderr);sys.exit(1)
''')
    tmux.chmod(0o755)
    alert = bin_dir / 'tell-general'
    alert.write_text('#!' + sys.executable + '''
import json,os,sys
if os.environ.get('ALERT_FAIL'):sys.exit(1)
with open(os.environ['ALERT_CALLS'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
''')
    alert.chmod(0o755)
    clean = {k: v for k, v in os.environ.items() if not k.startswith((
        'LAUNCH_', 'CODEX_', 'AGENT_', 'TMUX', 'RH_', 'RSTACK_', 'XDG_'))}
    clean.update(HOME=str(home), PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                 CODEX_HOME=str(home / '.codex'), RSTACK_STATE_DIR=str(tmp_path / 'state'),
                 LAUNCH_TMUX=str(tmux), LAUNCH_ALLOWANCE_ALERT=str(alert),
                 TMUX_CALLS=str(tmp_path / 'tmux-calls'), ALERT_CALLS=str(tmp_path / 'alerts'))
    return clean


def run_guard(env, job='deliverable', role='batch'):
    return subprocess.run([sys.executable, str(TOOL), '--guard', job, '--role', role,
                           '--log', str(Path(env['HOME']) / 'guard.log')],
                          env=env, capture_output=True, text=True, timeout=10)


def alert_rows(env):
    path = Path(env['ALERT_CALLS'])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_72_warns_once_per_threshold_per_window_even_concurrently(env):
    root = Path(env['CODEX_HOME'])
    rollout(root, [event()])
    args = [sys.executable, str(TOOL), '--guard', 'deliverable']
    procs = [subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
    for proc in procs:
        _, err = proc.communicate(timeout=10)
        assert proc.returncode == 0, err
    rows = alert_rows(env)
    assert len(rows) == 1 and rows[0][0] == 'decision' and 'threshold 70%' in rows[0][1]
    rollout(root, [event(86)])
    assert run_guard(env).returncode == 0
    assert run_guard(env).returncode == 0 and len(alert_rows(env)) == 2
    rollout(root, [event(72, reset=RESET + 7 * 86400)])
    assert run_guard(env).returncode == 0 and len(alert_rows(env)) == 3


@pytest.mark.parametrize('job,role', [('lane-audit', 'batch'), ('AUDIT', 'batch'),
    ('deliver', 'audit'), ('lane-rescore', 'batch'), ('lane-review-sweep', 'batch'),
    ('lane-calibration', 'batch'), ('lane-leaderboard', 'batch')])
def test_86_refuses_nonurgent_job_or_role_and_logs_urgent_override(env, job, role):
    rollout(Path(env['CODEX_HOME']), [event(86)])
    refused = run_guard(env, job, role)
    assert refused.returncode == 75 and 'LAUNCH_URGENT' in refused.stderr
    assert len(alert_rows(env)) == 2
    urgent = dict(env, LAUNCH_URGENT='Ricardo: submission closes in one hour')
    admitted = run_guard(urgent, job, role)
    assert admitted.returncode == 0, admitted.stderr
    assert 'Ricardo: submission closes in one hour' in (Path(env['HOME']) / 'guard.log').read_text()
    assert len(alert_rows(env)) == 2


@pytest.mark.parametrize('used', [85, 86])
def test_deliverable_jobs_admitted_and_exact_85_audit_is_admitted(env, used):
    rollout(Path(env['CODEX_HOME']), [event(used)])
    assert run_guard(env).returncode == 0
    if used == 85:
        assert run_guard(env, 'audit').returncode == 0


def test_stale_snapshot_warns_but_freshness_does_not_refuse(env):
    rollout(Path(env['CODEX_HOME']), [event(20, age=6 * 3600 + 60)])
    result = run_guard(env)
    assert result.returncode == 0 and 'WARNING stale snapshot' in result.stderr
    assert not alert_rows(env)


def test_expired_window_does_not_refuse_or_alert_using_last_weeks_usage(env):
    rollout(Path(env['CODEX_HOME']), [event(100, age=8 * 86400, reset=int(NOW - 10))])
    result = run_guard(env, 'audit')
    assert result.returncode == 0 and 'window has reset' in result.stderr
    assert not alert_rows(env)


def test_alert_delivery_failure_is_visible_and_retried(env):
    rollout(Path(env['CODEX_HOME']), [event()])
    result = run_guard(dict(env, ALERT_FAIL='1'))
    assert result.returncode == 0 and 'decision failed' in result.stderr
    assert run_guard(env).returncode == 0 and len(alert_rows(env)) == 1


def pane(name, backend='codex', provider='', dead=0, command=''):
    return '{}\t{}\t{}\t{}\t{}\n'.format(name, dead, backend, provider, command)


def test_concurrency_refuses_fifth_counts_sessions_not_panes_excludes_current_and_claude(env):
    rollout(Path(env['CODEX_HOME']), [event(20)])
    rows = ''.join(pane('job-' + str(i)) for i in range(4))
    rows += pane('job-1') + pane('job-claude', 'claude') + pane('claude-interactive')
    rows += pane('job-old-claude', '', command='env LAUNCH_BACKEND=claude launch.sh')
    rows += pane('job-dead', dead=1) + pane('job-provider', provider='openrouter')
    rows += pane('job-this')
    env.update(PANES=rows, TMUX='fixture', TMUX_PANE='%42')
    result = run_guard(env)
    assert result.returncode == 75 and '4 other Codex job-*' in result.stderr
    assert run_guard(dict(env, LAUNCH_URGENT='deadline')).returncode == 75
    assert run_guard(dict(env, LAUNCH_MAX_CONCURRENT='5')).returncode == 0
    assert run_guard(dict(env, LAUNCH_MAX_CONCURRENT='')).returncode == 75
    env['PANES'] = rows.replace(pane('job-3'), '')
    assert run_guard(env).returncode == 0
    calls = [json.loads(row) for row in Path(env['TMUX_CALLS']).read_text().splitlines()]
    assert ['set-option', '-t', '=job-this', '@launch_backend', 'codex'] in calls


def test_unknown_job_routes_count_and_unreadable_tmux_refuses(env):
    rollout(Path(env['CODEX_HOME']), [event(20)])
    rows = ''.join(pane('job-' + str(i), '') for i in range(4))
    assert run_guard(dict(env, PANES=rows)).returncode == 75
    assert run_guard(dict(env, TMUX_FAIL='permission denied')).returncode == 75
    assert run_guard(dict(env, TMUX_FAIL='no server running on socket')).returncode == 0
    assert run_guard(dict(env, LAUNCH_MAX_CONCURRENT='0')).returncode == 2


def launcher(env, tmp_path, job, role='batch', selected='codex', requested='codex'):
    jobs = tmp_path / 'jobs'
    jobs.mkdir(exist_ok=True)
    (jobs / (job + '.md')).write_text('Ship the requested fix.\nPeak RSS: 1 GB\n')
    selector = tmp_path / 'selector.py'
    selector.write_text("import sys\nif '--print-route' in sys.argv: print('fixture\\n" + selected + "')\n")
    fake = tmp_path / 'fake-agent'
    fake.write_text('#!' + sys.executable + '''
import os,sys
from pathlib import Path
with open(os.environ['PAID_CALLS'],'a') as f:f.write('called\\n')
if '-o' in sys.argv:Path(sys.argv[sys.argv.index('-o')+1]).write_text('done')
import json
Path(os.environ['PAID_CALLS']+'.argv').write_text(json.dumps(sys.argv))
Path(os.environ['PAID_CALLS']+'.lane').write_text(os.environ.get('RSTACK_LANE',''))
print(os.environ.get('FAKE_OUTPUT','{"is_error":false,"subtype":"success","result":"done"}'))
sys.exit(int(os.environ.get('FAKE_EXIT','0')))
''')
    fake.chmod(0o755)
    env = dict(env, AGENT_BACKEND=requested, LAUNCH_SELECTOR=str(selector), LAUNCH_CODEX=str(fake),
               LAUNCH_CLAUDE=str(fake), LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               LAUNCH_LANE_ROOT=str(tmp_path / 'runtime'), FORCE_LAUNCH='1',
               PAID_CALLS=str(tmp_path / 'paid-calls'), LAUNCH_RETRY_SECONDS='0')
    result = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), job, str(tmp_path), '--role', role],
                            env=env, capture_output=True, text=True, timeout=15)
    return result, (tmp_path / 'paid-calls'), (jobs / (job + '.log'))


@pytest.mark.parametrize('job,role,urgent,admit', [('lane-audit', 'batch', '', True),
    ('lane-deliver', 'audit', '', True), ('lane-deliver', 'batch', '', True),
    ('lane-audit', 'batch', 'deadline today', True)])
def test_real_launcher_leaves_allowance_admission_to_wrapper(env, tmp_path, job, role, urgent, admit):
    rollout(Path(env['CODEX_HOME']), [event(86)])
    result, calls, log = launcher(dict(env, LAUNCH_URGENT=urgent), tmp_path, job, role)
    assert (result.returncode == 0) == admit, result.stderr + log.read_text()
    assert calls.exists() == admit
    if urgent:
        assert urgent in log.read_text()
    assert not alert_rows(env)


def test_route_switch_to_codex_checks_concurrency_and_claude_is_exempt(env, tmp_path):
    rollout(Path(env['CODEX_HOME']), [event(86)])
    env['PANES'] = ''.join(pane('job-' + str(i)) for i in range(4))
    result, calls, _ = launcher(env, tmp_path, 'lane-audit', selected='codex', requested='claude')
    assert result.returncode == 75 and not calls.exists()
    result, calls, _ = launcher(env, tmp_path, 'lane-audit', selected='claude')
    assert result.returncode == 0 and calls.exists(), result.stderr


def test_real_launcher_concurrency_refusal_happens_before_executor(env, tmp_path):
    rollout(Path(env['CODEX_HOME']), [event(20)])
    env['PANES'] = ''.join(pane('job-' + str(i)) for i in range(4))
    result, calls, log = launcher(env, tmp_path, 'lane-deliver')
    assert result.returncode == 75 and not calls.exists() and 'LAUNCH_MAX_CONCURRENT=4' in log.read_text()


def test_real_launcher_capacity_retries_do_not_read_allowance(env, tmp_path):
    root = Path(env['CODEX_HOME'])
    path = rollout(root, [event(72)])
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    (jobs / 'lane-audit.md').write_text('Ship the fix.\n')
    selector = tmp_path / 'selector.py'
    selector.write_text("import sys\nif '--print-route' in sys.argv: print('fixture\\ncodex')\n")
    fake = tmp_path / 'fake-agent'
    fake.write_text('#!' + sys.executable + '\n' + '''
import json,os,sys
from pathlib import Path
with open(os.environ['PAID_CALLS'],'a') as f:f.write('called\\n')
Path(os.environ['ROLLOUT']).write_text(os.environ['NEXT_EVENT']+'\\n')
print('at capacity')
sys.exit(1)
''')
    fake.chmod(0o755)
    env = dict(env, AGENT_BACKEND='codex', LAUNCH_SELECTOR=str(selector), LAUNCH_CODEX=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               LAUNCH_LANE_ROOT=str(tmp_path / 'runtime'), FORCE_LAUNCH='1', LAUNCH_RETRY_SECONDS='0',
               ROLLOUT=str(path), NEXT_EVENT=json.dumps(event(86)), PAID_CALLS=str(tmp_path / 'paid-calls'))
    result = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), 'lane-audit', str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1, result.stderr
    assert (tmp_path / 'paid-calls').read_text().splitlines() == ['called'] * 5
    assert not alert_rows(env)


def test_selected_claude_route_updates_tmux_metadata_without_codex_refusal(env, tmp_path):
    rollout(Path(env['CODEX_HOME']), [event(86)])
    env.update(TMUX='fixture', TMUX_PANE='%42')
    result, calls, _ = launcher(env, tmp_path, 'lane-audit', selected='claude')
    assert result.returncode == 0 and calls.exists(), result.stderr
    tmux_calls = [json.loads(row) for row in Path(env['TMUX_CALLS']).read_text().splitlines()]
    assert ['set-option', '-t', '=job-this', '@launch_backend', 'claude'] in tmux_calls
    assert not alert_rows(env)


def test_conventional_symlink_home_is_discovered_without_active_codex_home(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    storage = tmp_path / 'external-storage'
    rollout(storage, [event(3)])
    (home / '.codex-linked').symlink_to(storage, target_is_directory=True)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.delenv('CODEX_HOME', raising=False)
    monkeypatch.delenv('CODEX_HOMES', raising=False)
    assert allowance.homes() == [storage]


def test_snapshot_age_includes_time_spent_reading(tmp_path, monkeypatch):
    rollout(tmp_path, [event(used=1, age=3)])
    ticks = iter([NOW, NOW + 10])
    monkeypatch.setattr(allowance.time, 'time', lambda: next(ticks))
    assert allowance.read_allowance([tmp_path])['codex']['snapshot_age_seconds'] == 13


def test_files_last_written_before_the_newest_snapshot_are_not_read(tmp_path, monkeypatch):
    """11-18: reading every rollout in full took minutes per call on an 8 GB home."""
    fresh = rollout(tmp_path / '.codex', [event(used=11)], name='rollout-fresh.jsonl')
    os.utime(fresh, (NOW, NOW))
    for i in range(30):
        old = rollout(tmp_path / '.codex', [event(used=90, age=86400)], name='rollout-old{}.jsonl'.format(i))
        os.utime(old, (NOW - 86400, NOW - 86400))
    opened = []
    real = allowance.reverse_lines
    monkeypatch.setattr(allowance, 'reverse_lines', lambda path: opened.append(path) or real(path))
    assert allowance.read_allowance([tmp_path / '.codex'], NOW)['codex']['weekly_used_percent'] == 11
    assert opened == [fresh]


@pytest.mark.parametrize('job', ['games_build', 'open-source_fix', 'bio_fix'])
def test_real_launcher_exempts_games_and_open_source(env, tmp_path, job):
    env['PANES'] = ''.join(pane('job-' + str(i)) for i in range(4))
    result, calls, _ = launcher(env, tmp_path, job)
    assert result.returncode == 0 and calls.exists(), result.stderr


def test_urgent_selects_priority_and_passes_canonical_lane(env, tmp_path):
    result, calls, log = launcher(dict(env, LAUNCH_URGENT='deadline today'), tmp_path, 'bio_fix')
    assert result.returncode == 0, result.stderr
    assert 'service_tier=priority' in json.loads(Path(str(calls)+'.argv').read_text())
    assert Path(str(calls)+'.lane').read_text() in ('bio', 'open-source')
    assert 'deadline today' in log.read_text()


def test_launcher_cap_excludes_exempt_sessions_and_counts_unknown_routes_once(env, tmp_path):
    env['PANES'] = (''.join(pane('job-' + str(i), '') for i in range(3))
                    + pane('job-1', '') + pane('job-games_build') + pane('job-open-source_fix')
                    + pane('job-bio_fix') + pane('job-claude', 'claude')
                    + pane('job-provider', provider='gemini') + pane('job-dead', dead=1))
    result, calls, _ = launcher(env, tmp_path, 'lane-deliver')
    assert result.returncode == 0 and calls.exists(), result.stderr


def test_urgency_does_not_override_concurrency(env, tmp_path):
    env['PANES'] = ''.join(pane('job-' + str(i)) for i in range(4))
    result, calls, _ = launcher(dict(env, LAUNCH_URGENT='deadline'), tmp_path, 'lane-deliver')
    assert result.returncode == 75 and not calls.exists()


def test_no_urgent_reason_leaves_service_tier_unset(env, tmp_path):
    result, calls, _ = launcher(dict(env, LAUNCH_URGENT='  '), tmp_path, 'lane-deliver')
    assert result.returncode == 0, result.stderr
    assert 'service_tier=priority' not in json.loads(Path(str(calls) + '.argv').read_text())


@pytest.mark.parametrize('rc', [0, 1, 42])
def test_cybersecurity_policy_flag_keeps_exit_prefix_and_stops_retry(env, tmp_path, rc):
    output = 'This content was flagged for possible cybersecurity risk\n' + 'noise\n' * 70 + 'at capacity'
    result, calls, log = launcher(dict(env, FAKE_OUTPUT=output, FAKE_EXIT=str(rc)), tmp_path, 'lane-deliver')
    assert result.returncode == rc, result.stderr
    assert calls.read_text().splitlines() == ['called']
    exits = [line for line in log.read_text().splitlines() if line.startswith('exit ')]
    assert len(exits) == 1 and exits[0].startswith('exit {} codex-policy-flag '.format(rc))
    status = (tmp_path / 'STATUS.md').read_text().splitlines()
    assert len(status) == 1 and 'Codex policy flag' in status[0]


def test_the_claude_weekly_reading_and_the_latest_agy_quota_error_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.delenv('RESETS_USAGE_DIR', raising=False)
    assert allowance.claude_weekly() is None and allowance.agy_quota_latest() is None
    (tmp_path / 'usage').mkdir()
    (tmp_path / 'usage/claude.json').write_text(json.dumps({'weekly_percent': 86, 'at': NOW - 600, 'source': 'footer'}))
    got = allowance.claude_weekly(NOW)
    assert got['weekly_used_percent'] == 86 and got['source'] == 'footer'
    assert allowance.claude_weekly(NOW + 3 * 3600) is None  # over 2 h old: the 15-min reader stopped
    assert 'h old' in allowance.claude_status(NOW + 3 * 3600)[1]
    (tmp_path / 'agy-quota.jsonl').write_text('{"utc": "a", "model": "m1"}\n{"utc": "b", "model": "m2", "tier": "medium"}\n')
    assert allowance.agy_quota_latest()['model'] == 'm2'
    data = allowance.read_allowance([], now=NOW)
    assert data['claude']['weekly_used_percent'] == 86 and data['agy_quota']['tier'] == 'medium'
