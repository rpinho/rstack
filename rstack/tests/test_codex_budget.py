"""Offline wrapper replay: no provider, login, notification, or installed file changes."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import pty
import signal
import subprocess
import sys
import time

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import _codex_budget as cb

NOW = 1800000000.0


def weekly(used=10, reset=NOW + 7 * 86400):
    return dict(weekly_used_percent=used, resets_at=reset, snapshot_at='2027-01-15T08:00:00+00:00')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def rollout(path, marker='', cwd='/test', tokens=27000, cached=0, used=10.1, stamp=None, output=0):
    stamp = time.time() if stamp is None else stamp
    iso = cb.datetime.fromtimestamp(stamp, cb.timezone.utc).isoformat()
    write_jsonl(path, [dict(type='session_meta', payload=dict(originator=marker, cwd=cwd, id=path.stem)),
        dict(timestamp=iso, type='event_msg', payload=dict(type='token_count',
             info=dict(total_token_usage=dict(input_tokens=tokens, cached_input_tokens=cached, output_tokens=output)),
             rate_limits=dict(limit_id='codex', primary=dict(used_percent=used, window_minutes=10080,
                                                          resets_at=stamp + 7 * 86400))))])


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith(('CODEX_', 'RSTACK_', 'LAUNCH_')) or key in ('RH_JOB', 'JOB_NAME', 'TMUX', 'RH_ROOT',
                                                                          'RH_LANE_REGISTRY'):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('RSTACK_LANE', 'normal')
    home = tmp_path / '.codex-clean'
    home.mkdir()
    monkeypatch.setenv('CODEX_HOME', str(home))
    notified = tmp_path / 'notified'
    notifier = tmp_path / 'notify'
    notifier.write_text('#!' + sys.executable + '\nimport sys\nfrom pathlib import Path\n'
                        'with Path(' + repr(str(notified)) + ').open("a") as f: f.write(repr(sys.argv[1:])+"\\n")\n')
    notifier.chmod(0o755)
    cfg = cb.config()
    cfg['notify_command'] = [str(notifier)]
    cfg['owner_command'] = [str(notifier), 'ricardo']
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg))
    monkeypatch.setenv('CODEX_BUDGET_CONFIG', str(config))
    return tmp_path, home, cfg, config, notified


def seed(base, lane, n, start=NOW - 300, step=1, tokens=100, cached_share=.9, prefix='prefix', percent=0):
    for i in range(n):
        cb.append(base, lane, dict(event='start', call_id='{}:{}'.format(start, i), ts=start + step * i,
                                  prefix=prefix, prompt_tokens=tokens))
        cb.append(base, lane, dict(event='finish', call_id='{}:{}'.format(start, i), ts=start + step * i + .5,
                                  input_tokens=tokens, cached_share=cached_share, weekly_percent=percent))


def test_normal_lane_and_hourly_limit(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        seed(base, 'normal', 59)
        cb.append(base, 'normal', dict(event='estimate', calls=100, total_tokens=100000, ts=NOW))
        assert cb.admit(cfg, base, 'normal', NOW, 'new', 100, weekly()) is None
        seed(base, 'normal', 1, start=NOW - 1)
        # Unique call IDs in production; add one distinct reservation here.
        cb.append(base, 'normal', dict(event='start', call_id='60', ts=NOW - 1))
        assert '60 calls/hour' in cb.admit(cfg, base, 'normal', NOW, 'new', 100, weekly())


def test_games_and_open_source_have_finite_higher_limits(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        for lane in ('games', 'open-source'):
            seed(base, lane, 61, percent=.1)
            cb.append(base, lane, dict(event='estimate', calls=200, total_tokens=200000, ts=NOW))
            assert cb.admit(cfg, base, lane, NOW, 'new', 100, weekly()) is None
        seed(base, 'normal', 4, tokens=30_000_000, percent=1)
        assert '3% weekly' in cb.admit(cfg, base, 'normal', NOW, 'new', 100, weekly())
        seed(base, 'games', 200, percent=0)
        assert '200 calls/hour' in cb.admit(cfg, base, 'games', NOW, 'new', 100, weekly())


def test_bio_alias_shares_open_source_budget_and_ledger(isolated, monkeypatch):
    monkeypatch.setenv('RSTACK_LANE', 'bio')
    assert cb.lane_for('/tmp/test') == 'open-source'
    monkeypatch.delenv('RSTACK_LANE')
    assert cb.lane_for('/tmp/open-science/bio_fix') == 'open-source'
    assert cb.lane_for('/tmp/lanes/bio') == 'open-source'
    with cb.locked() as base:
        seed(base, 'bio', 120)
        seed(base, 'open-source', 80, start=NOW - 200)
        assert '200 calls/hour' in cb.admit(isolated[2], base, 'open-source', NOW, 'new', 100, weekly())


def test_digest_run_cap_counts_pending_calls_across_hour_boundaries(isolated, monkeypatch):
    _, _, cfg, _, _ = isolated
    cfg['lanes']['digest'] = dict(calls_run=2, calls_hour=8, weekly_percent_day=1)
    with cb.locked() as base:
        assert 'RSTACK_RUN_ID required' in cb.admit(cfg, base, 'digest', NOW, 'x', 1, weekly())
        monkeypatch.setenv('RSTACK_RUN_ID', 'nightly-1')
        assert cb.admit(cfg, base, 'digest', NOW, 'x', 1, weekly()) is None
        for i in range(2):
            cb.append(base, 'digest', dict(event='start', call_id=str(i), run_id='nightly-1', ts=NOW - 7200 + i))
        assert '2 calls/run' in cb.admit(cfg, base, 'digest', NOW, 'x', 1, weekly())
        monkeypatch.setenv('RSTACK_RUN_ID', 'nightly-2')
        assert cb.admit(cfg, base, 'digest', NOW, 'x', 1, weekly()) is None


def test_health_caches_discovery_but_checks_new_homes_and_resumes_every_pass(isolated, monkeypatch):
    root, home, cfg, _, _ = isolated
    discoveries = []
    def discover():
        discoveries.append(True)
        return [home]
    monkeypatch.setattr(cb.allowance, 'homes', discover)
    now = time.time()
    settings = dict(enabled_since=now - 60)
    assert cb.health_problems(settings, now=now, repair=True) == []
    assert len(discoveries) == 1
    # Every known-home rollout is still checked, even a resume of an old session.
    path = home / 'sessions/rollout-resumed.jsonl'
    rollout(path)
    assert cb.health_problems(settings, now=now + 1, repair=True)[0][0] == 'codex-bypass'
    assert len(discoveries) == 1
    outside = root / 'new-explicit-home'
    rollout(outside / 'sessions/rollout-new.jsonl')
    monkeypatch.setenv('CODEX_HOMES', str(outside))
    rows = cb.health_problems(settings, now=now + 2, repair=True)
    assert len(rows) == 2 and len(discoveries) == 1
    assert cb.health_homes(cfg, now + 6 * 3600 + 1, write=True)
    assert len(discoveries) == 2


def test_dry_health_never_writes_discovery_cache(isolated, monkeypatch):
    monkeypatch.setattr(cb.allowance, 'homes', lambda: [])
    cb.health_problems(dict(enabled_since=time.time()), repair=False)
    assert not (cb.state_dir() / 'codex-home-discovery.json').exists()


@pytest.mark.parametrize('spacing', [20, 60])
def test_incident_replay_refused_on_call_20(isolated, spacing):
    """Literal 10-minute fan-out and incident's ~1/min calls both stop at 20."""
    _, _, cfg, _, notified = isolated
    with cb.locked() as base:
        for i in range(20):
            now = NOW + i * spacing
            reason = cb.admit(cfg, base, 'meccog', now, 'same-27k-prefix', 27000, weekly())
            if i == 19:
                assert '20th call' in reason
            else:
                assert reason is None
                cb.append(base, 'meccog', dict(event='start', call_id=str(i), ts=now, prefix='same-27k-prefix',
                                               prompt_tokens=27000))
                cb.append(base, 'meccog', dict(event='finish', call_id=str(i), ts=now + 1,
                                               input_tokens=27000, cached_share=0))
        assert '20th call' in cb.admit(cfg, base, 'meccog', now + 1, 'same-27k-prefix', 27000, weekly())
    assert notified.read_text().count('decision') == 1


def test_short_or_well_cached_prompts_do_not_trigger_fanout(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        for tokens, cache, lane in [(20000, 0, 'short'), (27000, .8, 'cached')]:
            seed(base, lane, 20, tokens=tokens, cached_share=cache)
            assert cb.admit(cfg, base, lane, NOW, 'prefix', tokens, weekly()) is None


def test_estimate_gate_on_51_and_finite_estimate_exhaustion(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        seed(base, 'normal', 50, start=NOW - 7000)
        assert 'past 50 calls' in cb.admit(cfg, base, 'normal', NOW, 'x', 1, weekly())
    from unittest.mock import patch
    with patch.object(cb.time, 'time', return_value=NOW):
        assert cb.cli(['estimate', 'normal', '--calls', '2', '--tokens', '100']) == 0
    with cb.locked() as base:
        estimate = cb.read_rows(base / 'normal.jsonl')[-1]
        now = estimate['ts'] + 10
        assert cb.admit(cfg, base, 'normal', now, 'x', 1, weekly(reset=now + 1000)) is None
        seed(base, 'normal', 2, start=estimate['ts'] + 1)
        assert 'estimate exhausted' in cb.admit(cfg, base, 'normal', now, 'x', 1, weekly(reset=now + 1000))


def test_account_thresholds_urgent_and_owner_notification(isolated):
    _, _, cfg, _, notified = isolated
    with cb.locked() as base:
        assert 'LAUNCH_URGENT' in cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(86))
        assert 'LAUNCH_URGENT' in cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(86))
        assert cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(86), urgent='production fix') is None
        events = cb.read_rows(base / 'normal.jsonl')
    messages = notified.read_text()
    assert messages.count('threshold') == 3
    assert 'ricardo' in messages and 'production fix' in messages
    assert events[-1]['event'] == 'urgent'


def test_interactive_is_never_blocked_by_lane_or_account(isolated, capsys):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        seed(base, 'normal', 200, percent=2)
        assert cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(99), interactive=True) is None
        assert cb.admit(cfg, base, 'normal', NOW, '', 0, None, interactive=True) is None
    assert 'WARNING' in capsys.readouterr().err


@pytest.mark.parametrize('option', [['-c', 'service_tier=priority'], ['--config=service_tier="priority"'],
                                   ['-cservice_tier="priority"'], ['--config', 'profiles.foo.service_tier="priority"']])
def test_priority_is_stripped_unless_urgent(option):
    args = ['exec'] + option + ['hello']
    clean, stripped = cb.strip_priority(args, '')
    assert stripped and all('priority' not in a for a in clean)
    assert 'service_tier=""' in clean
    assert cb.strip_priority(args, 'fix')[0] == args


def fake_native(isolated, code=0, with_weekly=True, after_percent=10.1):
    root, home, cfg, config, _ = isolated
    native = root / 'native'
    native.write_text('#!' + sys.executable + '''
import json,os,sys,time
from pathlib import Path
h=Path(os.environ['CODEX_HOME'])
p=h/'sessions'/('rollout-'+os.environ.get('CODEX_INTERNAL_ORIGINATOR_OVERRIDE','bare')+'.jsonl')
p.parent.mkdir(parents=True,exist_ok=True)
rows=[dict(type='session_meta',payload=dict(originator=os.environ.get('CODEX_INTERNAL_ORIGINATOR_OVERRIDE'),cwd=os.getcwd())),
 dict(type='event_msg',payload=dict(type='token_count',info=dict(total_token_usage=dict(input_tokens=27000,cached_input_tokens=5400,output_tokens=1000))))]
if WITH_WEEKLY:
 limits=json.loads((h/'sessions/rollout-before.jsonl').read_text().splitlines()[-1])['payload']['rate_limits']
 limits['primary']['used_percent']=AFTER_PERCENT
 rows[-1]['timestamp']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
 rows[-1]['payload']['rate_limits']=limits
p.write_text(''.join(json.dumps(r)+'\\n' for r in rows))
print(json.dumps(dict(args=sys.argv[1:],home=str(h),stdin=sys.stdin.read())))
sys.exit(''' + str(code) + ')\n')
    native.write_text(native.read_text().replace('WITH_WEEKLY', repr(with_weekly)).replace('AFTER_PERCENT', repr(after_percent)))
    native.chmod(0o755)
    cfg['native_binary'] = str(native)
    config.write_text(json.dumps(cfg))
    rollout(home / 'sessions/rollout-before.jsonl', used=10, stamp=time.time() - 10)
    return native


def run_wrapper(*args, env=None, stdin=''):
    return subprocess.run([sys.executable, str(TOOLS / 'codex'), *args], env=env, input=stdin,
                          text=True, capture_output=True, timeout=30)


def test_wrapper_records_actual_tokens_stdin_priority_and_exit(isolated):
    fake_native(isolated, code=7)
    r = run_wrapper('exec', '-c', 'service_tier=priority', '-', stdin='x' * 9000)
    assert r.returncode == 7, r.stderr
    output = json.loads(r.stdout)
    assert output['stdin'] == 'x' * 9000
    assert all('priority' not in a for a in output['args'])
    rows = cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl')
    assert any(r['event'] == 'priority_stripped' for r in rows)
    finish = rows[-1]
    assert finish['event'] == 'finish' and finish['input_tokens'] == 27000
    assert finish['cached_share'] == .2 and len(finish['rollouts']) == 1
    assert finish['output_tokens'] == 1000
    assert finish['weighted_tokens'] == pytest.approx(21870 + 5000)
    assert 'x' * 50 not in json.dumps(rows)


def test_minimal_env_python_subprocess_uses_brew_entrypoint(isolated):
    root, _, _, config, _ = isolated
    fake_native(isolated)
    # Simulate the proposed absolute layout below a temporary prefix, never the live brew bin.
    brew = root / 'opt/homebrew/bin'
    brew.mkdir(parents=True)
    brew.joinpath('codex').symlink_to(TOOLS / 'codex')
    env = dict(HOME=str(root), RSTACK_STATE_DIR=str(root / 'state'), CODEX_BUDGET_CONFIG=str(config),
               PATH='/usr/bin:/bin:' + str(brew))
    r = subprocess.run(['codex', 'exec', 'hello'], env=env, input='', capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    rows = list((root / 'state/codex-ledger').glob('*.jsonl'))
    assert len(rows) == 1 and '"event": "finish"' in rows[0].read_text()


def test_privacy_routing_preserved(isolated, monkeypatch):
    root, home, _, _, _ = isolated
    monkeypatch.delenv('CODEX_HOME')
    assert cb.routing(['-m', 'some-model', 'exec', 'hi'])[1]
    assert os.environ['CODEX_HOME'] == str(home)
    cfg = json.loads(isolated[3].read_text())
    cfg['personal_roots'] = ['~/.worktrees/notes']
    isolated[3].write_text(json.dumps(cfg))
    monkeypatch.setenv('CODEX_HOME', str(root / '.codex'))
    cb.routing(['exec', '--cd', str(root / '.worktrees/notes/games'), 'hi'])
    assert os.environ['CODEX_HOME'] == str(root / '.codex')
    explicit = root / 'explicit'
    monkeypatch.setenv('CODEX_HOME', str(explicit))
    cb.routing(['--personal', 'exec', 'hi'])
    assert os.environ['CODEX_HOME'] == str(explicit)


def test_lane_precedence_and_path_inference(isolated, monkeypatch):
    monkeypatch.delenv('RSTACK_LANE')
    cfg = json.loads(isolated[3].read_text())
    cfg['lane_anchors'] = ['notes']
    isolated[3].write_text(json.dumps(cfg))
    for path, expected in [('/Users/x/dev/open-science/meccog_1117', 'meccog'),
                           ('/Users/x/.worktrees/notes/games', 'games'),
                           ('/root/runtime/lanes/planets/work', 'planets')]:
        assert cb.lane_for(path) == expected
    # A job name no lane claims no longer becomes a lane of its own (11-18); the cwd decides.
    monkeypatch.setenv('RH_JOB', 'launch-job')
    assert cb.lane_for('/tmp/other') == 'other'
    monkeypatch.setenv('RSTACK_LANE', 'explicit')
    assert cb.lane_for('/tmp/other') == 'explicit'


def lane_registry_file(tmp_path, monkeypatch):
    path = tmp_path / 'REGISTRY.json'
    path.write_text(json.dumps({'lanes': {
        'digest': {'status': 'active', 'sessions': ['digest'], 'job_prefixes': ['nightly']},
        'open-source': {'status': 'active', 'sessions': ['open-source', 'bio'], 'aliases': ['bio'],
                        'job_prefixes': ['hunt', 'ref', 'bio']},
        'math': {'status': 'active', 'sessions': ['math']}}}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(path))
    return path


def test_registry_job_prefixes_map_nightly_to_digest_and_bio_jobs_to_open_source(isolated, monkeypatch, capsys):
    """11-18: nightly-20261118 and bio's hunt_/ref_ jobs were refused under the 3%/day default."""
    lane_registry_file(isolated[0], monkeypatch)
    monkeypatch.delenv('RSTACK_LANE')
    for key, job, expected in [('JOB_NAME', 'nightly-20261118', 'digest'),
                               ('RH_JOB', 'hunt_scrna_round3', 'open-source'),
                               ('RH_JOB', 'ref_pmc_1118', 'open-source'),
                               ('LAUNCH_JOB', 'bio_fix', 'open-source'),
                               ('RH_JOB', 'math-r12', 'math')]:
        monkeypatch.setenv(key, job)
        assert cb.lane_for('/Users/x/notes') == expected, job
        monkeypatch.delenv(key)
    assert capsys.readouterr().err == ''
    # This morning's case: no job variable, the lane came from the nightly worktree under a lane anchor.
    cfg = json.loads(isolated[3].read_text())
    cfg['lane_anchors'] = ['notes']
    isolated[3].write_text(json.dumps(cfg))
    assert cb.lane_for('/Users/x/.worktrees/notes/nightly-20261118') == 'digest'
    assert cb.lane_for('/Users/x/dev/open-science/hunt_scrna') == 'open-source'
    assert capsys.readouterr().err == ''
    # RSTACK_LANE still wins, through the registry's aliases.
    monkeypatch.setenv('RH_JOB', 'nightly-20261118')
    monkeypatch.setenv('RSTACK_LANE', 'bio')
    assert cb.lane_for('/tmp/other') == 'open-source'
    # An unknown job falls to the cwd, keeps default limits and gets one line naming it.
    monkeypatch.delenv('RSTACK_LANE')
    monkeypatch.setenv('RH_JOB', 'mystery_1118')
    assert cb.lane_for('/tmp/other') == 'other'
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "job 'mystery_1118'" in err[0] and 'default limits' in err[0]
    # A broken registry warns and still resolves by cwd rather than refusing.
    monkeypatch.setenv('RH_LANE_REGISTRY', str(isolated[0] / 'missing.json'))
    monkeypatch.setenv('RH_JOB', 'nightly-20261118')
    assert cb.lane_for('/tmp/lanes/planets/w') == 'planets'


def test_nightly_job_is_charged_to_the_digest_ledger_and_limits(isolated, monkeypatch):
    lane_registry_file(isolated[0], monkeypatch)
    _, _, cfg, config, _ = isolated
    cfg['lanes']['digest'] = dict(calls_run=8, calls_hour=8, weekly_percent_day=1)
    config.write_text(json.dumps(cfg))
    fake_native(isolated)
    monkeypatch.delenv('RSTACK_LANE')
    monkeypatch.setenv('JOB_NAME', 'nightly-20261118')
    monkeypatch.setenv('RSTACK_RUN_ID', 'nightly-20261118')
    r = run_wrapper('exec', 'hello')
    assert r.returncode == 0, r.stderr
    assert 'nightly-20261118' not in r.stderr
    rows = cb.read_rows(cb.state_dir() / 'codex-ledger/digest.jsonl')
    assert rows[-1]['event'] == 'finish'
    assert not (cb.state_dir() / 'codex-ledger/nightly-20261118.jsonl').exists()


def test_backstop_flags_unledgered_and_ignores_inflight_marked_session(isolated):
    _, home, _, _, _ = isolated
    now = time.time()
    bad = home / 'sessions/rollout-bypass.jsonl'
    good = home / 'sessions/rollout-wrapped.jsonl'
    rollout(bad, cwd='/a/missed/lane')
    rollout(good, marker='our-call')
    with cb.locked() as base:
        cb.append(base, 'normal', dict(event='start', call_id='a', marker='our-call', pid=os.getpid()))
    rows = cb.health_problems(dict(enabled_since=now - 60), now=now)
    assert len(rows) == 1 and rows[0][0] == 'codex-bypass'
    assert '/a/missed/lane' in rows[0][2]


def test_post_brew_upgrade_reasserts_and_preserves_previous_symlink(isolated):
    root, _, _, _, _ = isolated
    native = fake_native(isolated)
    brew = root / 'brew/bin/codex'
    brew.parent.mkdir(parents=True)
    brew.symlink_to(native)
    settings = dict(wrapper=str(TOOLS / 'codex'), entrypoints=[str(brew)], enabled_since=time.time() + 60)
    assert cb.health_problems(settings, repair=False)[0][0] == 'codex-install'
    assert brew.resolve() == native
    rows = cb.health_problems(settings, repair=True)
    assert 'wrapper restored' in rows[0][2] and brew.resolve() == TOOLS / 'codex'
    assert len(list((cb.state_dir() / 'codex-ledger/entrypoint-backups').iterdir())) == 1
    assert cb.health_problems(settings, repair=True) == []


def test_unavailable_weekly_refuses_batch_and_invalid_config_is_one_line(isolated):
    fake_native(isolated)
    home = isolated[1]
    # Created in this test session: move the synthetic snapshot rather than deleting it.
    (home / 'sessions/rollout-before.jsonl').rename(home / 'old-snapshot')
    r = run_wrapper('exec', 'hello')
    assert r.returncode == 75 and 'allowance unavailable' in r.stderr
    isolated[3].write_text('{broken')
    r = run_wrapper('exec', 'hello')
    # RULE #1 (11-20): a config the wrapper cannot read is its own error, never a refusal: the native codex
    # runs, and the warning is logged to harness-blocks.jsonl.
    assert r.returncode != 75 and 'WARNING accounting/config unavailable' in r.stderr
    rows = (isolated[0] / 'state/harness-blocks.jsonl').read_text().splitlines()
    assert '"gate": "codex-budget.unavailable"' in rows[-1] and '"outcome": "warn"' in rows[-1]


def test_call_reservations_close_parallel_hourly_race(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        for i in range(60):
            cb.append(base, 'normal', dict(event='start', call_id=str(i), ts=NOW - 1, prefix='x'))
        assert '60 calls/hour' in cb.admit(cfg, base, 'normal', NOW, 'y', 100, weekly())


def test_prompt_prefix_hashes_only_first_4096_chars(isolated, monkeypatch):
    import io
    for suffix in ('first', 'second'):
        monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'')))
        stream, prefix, tokens = cb.prompt_input(['exec', 'p' * 108000 + suffix], True)
        assert prefix == cb.hashlib.sha256(('p' * 4096).encode()).hexdigest()
        assert tokens > 20000
        stream.close()


def test_priority_in_config_and_profile_is_overridden_and_logged(isolated):
    _, home, _, _, _ = isolated
    fake_native(isolated, code=7)
    (home / 'nightly.config.toml').write_text('service_tier = "priority"\n')
    r = run_wrapper('-p', 'nightly', 'exec', 'hello')
    assert r.returncode == 7, r.stderr
    assert json.loads(r.stdout)['args'][:2] == ['-c', 'service_tier=""']
    assert any(r['event'] == 'priority_stripped' for r in cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl'))


def test_success_without_accounting_prevents_next_batch(isolated):
    fake_native(isolated, with_weekly=False)  # No weekly snapshot in this fake's completion.
    assert run_wrapper('exec', 'hello').returncode == 0
    r = run_wrapper('exec', 'hello')
    assert r.returncode == 75 and 'unaccounted usage' in r.stderr


def test_ephemeral_batch_cannot_disable_rollout_accounting(isolated):
    fake_native(isolated)
    r = run_wrapper('exec', '--ephemeral', 'hello')
    assert r.returncode == 75 and '--ephemeral' in r.stderr


def test_backstop_detects_unwrapped_resume_of_accounted_session(isolated):
    _, home, _, _, _ = isolated
    path = home / 'sessions/rollout-resumed.jsonl'
    rollout(path, marker='previously-wrapped')
    with cb.locked() as base:
        cb.append(base, 'normal', dict(event='start', call_id='old', marker='previously-wrapped', pid=os.getpid()))
        cb.append(base, 'normal', dict(event='finish', call_id='old', rollouts=[str(path)],
                                      rollout_sizes={str(path): path.stat().st_size}))
    settings = dict(enabled_since=time.time() - 60)
    assert cb.health_problems(settings) == []
    with path.open('a') as stream:
        stream.write('{"type":"event_msg","payload":{}}\n')
    rows = cb.health_problems(settings)
    assert rows[0][0] == 'codex-bypass'


def test_interactive_tty_executes_above_85_without_urgent(isolated):
    root, home, _, _, notified = isolated
    native = fake_native(isolated)
    native.write_text(native.read_text().replace('sys.stdin.read()', "sys.stdin.read() if not sys.stdin.isatty() else ''"))
    rollout(home / 'sessions/rollout-before.jsonl', used=99, stamp=time.time() - 1)
    master, slave = pty.openpty()
    try:
        result = subprocess.run([sys.executable, str(TOOLS / 'codex')], stdin=slave, stdout=slave,
                                stderr=subprocess.PIPE, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert 'interactive session remains available' in result.stderr
    finally:
        os.close(slave)
        os.close(master)
    assert 'ricardo' not in notified.read_text()


def test_signal_reaches_native_and_completion_is_recorded(isolated):
    root, _, _, _, _ = isolated
    native = fake_native(isolated)
    native.write_text(native.read_text().replace("print(json.dumps", "print('READY',flush=True)\ntime.sleep(30)\nprint(json.dumps"))
    out = root / 'output'
    with out.open('w') as stream:
        proc = subprocess.Popen([sys.executable, str(TOOLS / 'codex'), 'exec', 'hello'],
                                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 10
            while time.time() < deadline and 'READY' not in out.read_text():
                time.sleep(.02)
            assert 'READY' in out.read_text()
            proc.terminate()
            _, err = proc.communicate(timeout=10)
            assert proc.returncode == 143, err
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    finish = cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl')[-1]
    assert finish['event'] == 'finish' and finish['exit_code'] == -signal.SIGTERM


def test_job_health_reports_bypass_to_general_once(isolated, monkeypatch):
    root, home, _, _, notified = isolated
    loader = importlib.machinery.SourceFileLoader('job_health_codex_test', str(TOOLS / 'job-health'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    health = importlib.util.module_from_spec(spec)
    loader.exec_module(health)
    monkeypatch.setattr(health, 'launchd_jobs', lambda prefix: {})
    reg = root / 'health.json'
    reg.write_text(json.dumps(dict(codex=dict(enabled_since=time.time() - 30))))
    rollout(home / 'sessions/rollout-absolute-path.jsonl', cwd='/missed/lane')
    alert = str(root / 'notify') + ' decision'
    args = ['--prefix', 'com.test.', '--registry', str(reg), '--alert', alert]
    assert health.main(args) == 0
    assert health.main(args) == 0
    assert notified.read_text().count('codex-bypass') == 1
    assert '/missed/lane' in notified.read_text()


def test_resumed_usage_counts_only_new_tokens(isolated):
    _, home, _, _, _ = isolated
    path = home / 'sessions/rollout-old.jsonl'
    rollout(path, tokens=100000, cached=70000, output=1000)
    offset = path.stat().st_size
    old, _ = cb.usage_at(path)
    with path.open('a') as stream:
        stream.write(json.dumps(dict(type='event_msg', payload=dict(type='token_count',
            info=dict(total_token_usage=dict(input_tokens=127000, cached_input_tokens=75400, output_tokens=2000))))) + '\n')
    new, _ = cb.usage_at(path, offset, previous=old)
    assert new['output_tokens'] - old['output_tokens'] == 1000
    assert new['weighted_tokens'] == 26870
    assert new['input_tokens'] - old['input_tokens'] == 27000
    assert new['cached_input_tokens'] - old['cached_input_tokens'] == 5400


def test_tiny_lane_is_admitted_after_five_point_account_jump(isolated):
    fake_native(isolated, after_percent=15)
    first = run_wrapper('exec', 'hello')
    assert first.returncode == 0, first.stderr
    rows = cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl')
    assert rows[-1]['weekly_percent'] == pytest.approx(5)
    assert rows[-1]['weighted_tokens'] / cb.FALLBACK_TOKENS_PER_POINT < .01
    second = run_wrapper('exec', 'hello')
    assert second.returncode == 0, second.stderr


def test_failed_owner_push_refuses_urgent_and_keeps_it_logged(isolated):
    _, _, cfg, _, _ = isolated
    cfg['owner_command'] = ['/usr/bin/false']
    with cb.locked() as base:
        reason = cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(90), urgent='fix')
        assert 'owner notification failed' in reason
        assert cb.read_rows(base / 'normal.jsonl')[-1]['event'] == 'urgent'


def test_finished_today_counts_even_if_started_yesterday(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        cb.append(base, 'normal', dict(event='start', call_id='long', ts=NOW - 90000))
        cb.append(base, 'normal', dict(event='finish', call_id='long', ts=NOW - 10, input_tokens=15_000_000, weekly_percent=0))
        assert '3% weekly' in cb.admit(cfg, base, 'normal', NOW, '', 0, weekly())


def test_account_alerts_share_launcher_dedup_state(isolated):
    _, _, cfg, _, notified = isolated
    folder = cb.state_dir() / 'allowance'
    folder.mkdir(parents=True)
    (folder / 'alerts.json').write_text(json.dumps({str(weekly()['resets_at']) + ':70': NOW,
                                                   str(weekly()['resets_at']) + ':85': NOW}))
    with cb.locked() as base:
        cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(86))
    assert notified.read_text().count('threshold') == 1
    assert '50% threshold' in notified.read_text()


def test_live_pending_run_does_not_charge_account_movement(isolated):
    _, _, cfg, _, _ = isolated
    with cb.locked() as base:
        cb.append(base, 'normal', dict(event='start', call_id='pending', ts=NOW - 10,
                                      pid=os.getpid(), weekly_before=weekly(10)))
        assert cb.admit(cfg, base, 'normal', NOW, '', 0, weekly(15)) is None


def test_prompt_named_version_after_separator_does_not_bypass_guard(isolated):
    fake_native(isolated)
    rollout(isolated[1] / 'sessions/rollout-before.jsonl', used=99, stamp=time.time() - 1)
    r = run_wrapper('exec', '--', '--version')
    assert r.returncode == 75 and 'LAUNCH_URGENT' in r.stderr


def test_account_crossing_alerts_at_completion_without_needing_another_call(isolated):
    fake_native(isolated, after_percent=70)
    first = run_wrapper('exec', 'hello')
    assert first.returncode == 0, first.stderr
    messages = isolated[4].read_text()
    assert '50% threshold' in messages and '70% threshold' in messages


def test_simultaneous_processes_cannot_race_the_call_cap(isolated):
    from concurrent.futures import ThreadPoolExecutor
    _, _, cfg, config, _ = isolated
    fake_native(isolated)
    cfg['defaults']['calls_hour'] = 2
    config.write_text(json.dumps(cfg))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: run_wrapper('exec', 'prompt ' + str(i)), range(4)))
    assert sorted(r.returncode for r in results) == [0, 0, 75, 75], [r.stderr for r in results]


def test_damaged_accounting_config_does_not_block_tty(isolated, monkeypatch):
    from types import SimpleNamespace
    class NativeExec(BaseException):
        pass
    captured = []
    isolated[3].write_text('{broken')
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cb, 'native_binary', lambda cfg: Path('/fake/native'))
    def execv(path, args):
        captured.append(args)
        raise NativeExec()
    monkeypatch.setattr(cb.os, 'execv', execv)
    with pytest.raises(NativeExec):
        cb.wrapper_main(['--personal'])
    assert captured == [['/fake/native', '-c', 'service_tier=""']]


def test_waiting_invocation_counts_calls_reserved_after_it_started(isolated, monkeypatch):
    """Deterministic regression for the pre-lock clock race found by the process replay."""
    _, _, cfg, _, _ = isolated
    cfg['defaults']['calls_hour'] = 1
    with cb.locked() as base:
        cb.append(base, 'normal', dict(event='start', call_id='reserved', ts=NOW + .5))
    ticks = iter([NOW, NOW + 1])
    monkeypatch.setattr(cb.time, 'time', lambda: next(ticks, NOW + 2))
    monkeypatch.setattr(cb, 'weekly_snapshot', lambda cfg, now: weekly())
    monkeypatch.setattr(cb, 'prompt_input', lambda args, batch: (None, 'x', 100))
    result = cb.supervise(Path('/must-not-be-executed'), ['exec', 'hello'], cfg, 'normal', '/tmp', False, True)
    assert result == 75
    rows = cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl')
    assert rows[-1]['event'] == 'refused' and 'calls/hour' in rows[-1]['reason']


def test_failed_native_with_spent_tokens_still_requires_accounting(isolated):
    fake_native(isolated, code=7, with_weekly=False)
    first = run_wrapper('exec', 'hello')
    assert first.returncode == 7
    second = run_wrapper('exec', 'hello')
    assert second.returncode == 75 and 'unaccounted usage' in second.stderr


def caskroom(root, *versions):
    out = []
    for v in versions:
        p = root / 'Caskroom/codex' / v / 'bin/codex'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('#!/bin/sh\necho native ' + v + '\n')
        p.chmod(0o755)
        out.append(p)
    return out


def test_native_is_reached_only_through_codex_real_and_follows_upgrades(isolated):
    root, _, cfg, config, _ = isolated
    old, = caskroom(root, '0.167.0')
    cfg.pop('native_binary', None)
    cfg['native_glob'] = str(root / 'Caskroom/codex/*/bin/codex')
    link = root / '.local/libexec/codex-real'
    # First use creates the link; the wrapper runs the link path, not a pinned version.
    assert cb.native_binary(cfg) == link and os.readlink(link) == str(old)
    # brew upgrade: a newer version appears and the old directory is moved away.
    new, = caskroom(root, '0.170.0')
    (root / 'Caskroom/codex/0.167.0').rename(root / 'old-version')
    assert not link.exists() and link.is_symlink()  # dangling
    assert cb.native_binary(cfg) == link and os.readlink(link) == str(new)
    # job-health reports and re-points a link that lags behind the newest version.
    newer, = caskroom(root, '0.171.0')
    settings = dict(wrapper=str(TOOLS / 'codex'), entrypoints=[], enabled_since=time.time() + 60,
                    native_link=str(link))
    config.write_text(json.dumps(cfg))
    assert cb.health_problems(settings, repair=False)[0][0] == 'codex-install'
    assert os.readlink(link) == str(new)
    rows = cb.health_problems(settings, repair=True)
    assert 're-pointed' in rows[0][2] and os.readlink(link) == str(newer)
    assert cb.health_problems(settings, repair=True) == []


def test_activation_installs_wrapper_codex_real_and_npx_shim(isolated):
    root, _, cfg, config, _ = isolated
    native, = caskroom(root, '0.167.0')
    cfg.pop('native_binary', None)
    cfg['native_glob'] = str(root / 'Caskroom/codex/*/bin/codex')
    config.write_text(json.dumps(cfg))
    node = root / 'node/bin/npx'
    node.parent.mkdir(parents=True)
    node.write_text('#!/bin/sh\necho real-npx "$@"\n')
    node.chmod(0o755)
    bindir = root / '.local/bin'
    bindir.mkdir(parents=True)
    (bindir / 'npx').symlink_to(node)
    brew = root / 'brew/codex'
    brew.parent.mkdir()
    brew.symlink_to(native)
    assert cb.cli(['activate', '--wrapper', str(TOOLS / 'codex'), '--entrypoint', str(bindir / 'codex'),
                   '--entrypoint', str(brew), '--npx', str(bindir / 'npx')]) == 0
    assert brew.resolve() == (TOOLS / 'codex').resolve() and (bindir / 'codex').resolve() == (TOOLS / 'codex').resolve()
    assert os.readlink(root / '.local/libexec/codex-real') == str(native)
    env = dict(HOME=str(root), PATH='/usr/bin:/bin')
    for spec in ('codex', '@openai/codex', '@openai/codex@latest', '--package=@openai/codex'):
        r = subprocess.run([str(bindir / 'npx'), '-y', spec, 'exec', 'hi'], env=env, capture_output=True, text=True)
        assert r.returncode == 75 and 'REFUSED' in r.stderr
    r = subprocess.run([str(bindir / 'npx'), 'prettier', 'codex.md'], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == 'real-npx prettier codex.md'
    # An npm reinstall that restores the original npx symlink is undone by job-health.
    (bindir / 'npx').rename(root / 'moved-shim')
    (bindir / 'npx').symlink_to(node)
    settings = json.loads(cb.deployment_file().read_text())
    rows = cb.health_problems(settings, repair=True)
    assert any(r[1] == str(bindir / 'npx') and 'shim restored' in r[2] for r in rows)
    assert (bindir / 'npx').resolve() == (TOOLS / 'npx').resolve()


def test_phone_daemon_management_needs_no_snapshot_or_ledger_row(isolated):
    """Boot recovery runs `codex remote-control start --json` from launchd, with no TTY."""
    fake_native(isolated, with_weekly=False)
    home = isolated[1]
    (home / 'sessions/rollout-before.jsonl').rename(home / 'old-snapshot')  # no weekly snapshot
    r = run_wrapper('remote-control', 'start', '--json')
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['args'] == ['remote-control', 'start', '--json']
    assert not list((cb.state_dir() / 'codex-ledger').glob('*.jsonl'))


def snapshot_at(ts, used=10, reset=NOW + 7 * 86400):
    return dict(weekly_used_percent=used, resets_at=reset,
                snapshot_at=cb.datetime.fromtimestamp(ts, cb.timezone.utc).isoformat())


def calibration_rows():
    # Concurrent lane deltas grossly overlap; only the 10 -> 20 account change counts.
    return [dict(event='finish', call_id=str(i), ts=NOW - 7200 + i,
                 weighted_tokens=1_000_000, weekly_percent=10,
                 weekly_before=snapshot_at(NOW - 8 * 3600, 10),
                 weekly_after=snapshot_at(NOW - 1, 20)) for i in range(10)]


def test_calibration_uses_total_tokens_over_one_account_window():
    rows = calibration_rows()
    result = cb.calibration_from_rows(rows, NOW, snapshot_at(NOW, 20))
    assert result['weighted_tokens'] == 10_000_000
    assert result['weekly_points'] == 10
    assert result['tokens_per_point'] == 1_000_000
    assert result['calls'] == 10
    # A different reset is never part of this fit.
    rows.append(dict(weekly_before=snapshot_at(NOW - 2 * 86400, 99, reset=NOW)))
    assert cb.calibration_from_rows(rows, NOW, snapshot_at(NOW, 20)) == result


@pytest.mark.parametrize('case', ['short', 'quantized', 'few_calls', 'decreasing', 'missing'])
def test_calibration_requires_enough_same_window_evidence(case):
    rows = calibration_rows()
    if case == 'short':
        for row in rows:
            row['weekly_before'] = snapshot_at(NOW - 3600, 10)
    elif case == 'quantized':
        for row in rows:
            row['weekly_after'] = snapshot_at(NOW - 1, 11)
    elif case == 'few_calls':
        rows.pop()
    elif case == 'decreasing':
        rows.append(dict(weekly_after=snapshot_at(NOW - 60, 25)))
    else:
        rows[0]['usage_missing'] = True
    assert cb.calibration_from_rows(rows, NOW, snapshot_at(NOW, 20)) is None


def test_calibration_stored_and_refreshed_daily(isolated):
    with cb.locked() as base:
        initial = cb.token_calibration(base, NOW, snapshot_at(NOW))
        assert initial['tokens_per_point'] == 5_000_000
        assert '250 credits/point' in initial['source']
        for row in calibration_rows():
            cb.append(base, 'other', dict(event='start', call_id=row['call_id'], ts=row['ts'] - 1))
            cb.append(base, 'other', dict(row, weighted_tokens=6_000_000))
        assert cb.token_calibration(base, NOW + 1, snapshot_at(NOW, 20)) == initial
        refreshed = cb.token_calibration(base, NOW + 86400, snapshot_at(NOW + 86400, 20))
        assert refreshed['source'] == 'ledger/account-window'
        assert refreshed['tokens_per_point'] == 6_000_000
        assert json.loads((base / '.token-calibration.json').read_text()) == refreshed
        # No suitable new window: keep the previous empirical calibration.
        assert cb.token_calibration(base, NOW + 8 * 86400, snapshot_at(NOW + 8 * 86400, 20))['tokens_per_point'] == 6_000_000


@pytest.mark.parametrize('lane', ['normal', 'open-source'])
def test_own_weighted_output_and_cached_input_exhaust_lane_cap(isolated, lane):
    cfg = isolated[2]
    cfg['lanes'][lane] = dict(calls_hour=60, weekly_percent_day=1)
    with cb.locked() as base:
        seed(base, 'bio' if lane == 'open-source' else lane, 1, tokens=1_000_000, cached_share=1)
        row = dict(event='finish', call_id='output', ts=NOW - 1, input_tokens=0, output_tokens=1_000_000)
        cb.append(base, lane, dict(event='start', call_id='output', ts=NOW - 2))
        cb.append(base, lane, row)
        assert '1% weekly allowance/day' in cb.admit(cfg, base, lane, NOW, '', 0, weekly())
        # The fully cached legacy input row is only 0.01 points; output contributes 1 point.
        assert cb.ledger_tokens(base, cb.calls(cb.read_rows(base / ('bio.jsonl' if lane == 'open-source' else lane + '.jsonl')))[0]) == 50_000


def test_rate_card_model_cache_and_priority_weights():
    tokens = dict(input_tokens=1_000_000, cached_input_tokens=800_000, output_tokens=10_000)
    assert cb.weighted_tokens(tokens) == 290_000
    assert cb.weighted_tokens(tokens, 'gpt-6.2-astra') == 1_160_000
    assert cb.weighted_tokens(tokens, 'gpt-6.2-astra', priority=True) == 2_320_000
    assert cb.weighted_tokens(dict(input_tokens=100, cached_share=.9)) == pytest.approx(14.5)


def test_legacy_usage_recovered_at_saved_size_and_cached(isolated):
    _, home, _, _, _ = isolated
    path = home / 'sessions/rollout-legacy.jsonl'
    rollout(path, tokens=100000, cached=80000, stamp=NOW - 5)
    with path.open('a') as stream:
        stream.write(json.dumps(dict(timestamp=cb.datetime.fromtimestamp(NOW - 3, cb.timezone.utc).isoformat(),
            type='event_msg', payload=dict(type='token_count', info=dict(total_token_usage=dict(
                input_tokens=127000, cached_input_tokens=85400, output_tokens=1000))))) + '\n')
    row = dict(event='finish', call_id='old', ts=NOW - 1, started_at=NOW - 4,
               input_tokens=27000, cached_input_tokens=5400, rollouts=[str(path)],
               rollout_sizes={str(path): path.stat().st_size})
    # An unwrapped later resume must never inflate this finish.
    with path.open('a') as stream:
        stream.write(json.dumps(dict(type='event_msg', payload=dict(type='token_count', info=dict(
            total_token_usage=dict(input_tokens=9000000, output_tokens=999999))))) + '\n')
    with cb.locked() as base:
        assert cb.ledger_tokens(base, row) == 26870
        path.rename(path.with_suffix('.saved'))
        assert cb.ledger_tokens(base, row) == 26870


def test_partial_host_calibration_does_not_bill_other_machines(isolated):
    with cb.locked() as base:
        for row in calibration_rows():
            cb.append(base, 'other', dict(event='start', call_id=row['call_id'], ts=row['ts'] - 1))
            cb.append(base, 'other', row)
        calibration = cb.token_calibration(base, NOW, snapshot_at(NOW, 20))
        assert calibration['tokens_per_point'] == cb.FALLBACK_TOKENS_PER_POINT
        assert 'fallback' in calibration['source']


def test_token_weights_follow_turn_models_and_priority(isolated):
    path = isolated[1] / 'sessions/rollout-model-switch.jsonl'
    rollout(path, tokens=100, output=10)
    with path.open('a') as stream:
        stream.write(json.dumps(dict(type='turn_context', payload=dict(model='gpt-6-astra', service_tier='priority'))) + '\n')
        stream.write(json.dumps(dict(type='event_msg', payload=dict(type='token_count', info=dict(total_token_usage=dict(
            input_tokens=200, cached_input_tokens=50, output_tokens=25))))) + '\n')
    total, _ = cb.usage_at(path)
    assert total['weighted_tokens'] == 150 + 650 * 2.5
    assert cb.weighted_tokens(dict(input_tokens=1_000_000), 'other/provider') == 0


# ---- the referee bucket (11-20) --------------------------------------------------------------

GEMINI = ['gemini-3.8-flash-high', 'gemini-4-argon-medium']


def agy_refusals(models, at=NOW - 3600, resets='152h14m46s'):
    write_jsonl(cb.state_dir() / 'agy-quota.jsonl', [dict(
        utc=cb.datetime.fromtimestamp(at, cb.timezone.utc).isoformat(), model=m, tier=m.rsplit('-', 1)[1],
        job='j', error='Individual quota reached. Resets in {}.'.format(resets)) for m in models])


def roles(tmp_path, cfg):
    path = tmp_path / 'roles.json'
    path.write_text(json.dumps(dict(roles={}, routes=dict(
        {m: dict(cli='agy', canonical='google/' + m) for m in GEMINI},
        **{'claude-opus-5-5-high': dict(cli='agy', canonical='anthropic/claude-opus-5-5'),
           'gpt-6.2-astra': dict(cli='codex', canonical='openai/gpt-6.2-astra')}))))
    cfg['roles_file'] = str(path)
    return cfg


def test_agy_reset_times_are_read_per_model(isolated):
    agy_refusals(['gemini-4-argon-medium'], resets='4h52m1s')
    assert cb.agy_blocked_until()['gemini-4-argon-medium'] == pytest.approx(NOW - 3600 + 4 * 3600 + 52 * 60 + 1)
    assert cb.agy_gemini_candidates(roles(isolated[0], isolated[2])) == GEMINI


def test_a_referee_past_the_lane_budget_runs_on_the_referee_bucket_only_while_agy_gemini_is_out(isolated):
    root, _, cfg, _, _ = isolated
    cfg = roles(root, dict(cfg, referee_extra_per_day=2))
    with cb.locked() as base:
        seed(base, 'open-source', 50, start=NOW - 7000)
        args = (cfg, base, 'open-source', NOW, 'x', 1, weekly())
        # One Gemini candidate still free: no bucket, the lane's own refusal stands.
        agy_refusals(GEMINI[1:])
        reason, bucket, _ = cb.admit_call(*args, role='referee')
        assert 'past 50 calls' in reason and 'referee bucket closed' in reason and bucket == 'lane'
        # Every candidate blocked: referees run on the bucket, hunts do not.
        agy_refusals(GEMINI)
        assert 'past 50 calls' in cb.admit_call(*args, role='batch')[0]
        for n in (1, 2):
            reason, bucket, note = cb.admit_call(*args, role='referee')
            assert reason is None and bucket == 'referee' and 'call {}/2'.format(n) in note
            cb.append(base, 'open-source', dict(event='start', call_id='ref{}'.format(n), ts=NOW - 1, bucket='referee'))
        assert 'referee bucket spent: 2/2' in cb.admit_call(*args, role='referee')[0]
        # The bucket is the lane budget only: the hourly cap still refuses a referee.
        cfg['lanes']['open-source'] = dict(cfg['lanes']['open-source'], calls_hour=2)
        assert '2 calls/hour' in cb.admit_call(*args, role='referee')[0]
    # After agy's reset the bucket closes again.
    agy_refusals(GEMINI, at=NOW - 200 * 3600)
    assert cb.referee_bucket(cfg, 'open-source', NOW)[0] == 0


def test_the_wrapper_says_which_bucket_a_referee_used(isolated, monkeypatch):
    root, _, cfg, config, _ = isolated
    fake_native(isolated)
    cfg = json.loads(config.read_text())
    config.write_text(json.dumps(roles(root, cfg)))
    agy_refusals(GEMINI, at=time.time() - 60)
    with cb.locked() as base:
        seed(base, 'normal', 50, start=time.time() - 7000)
    env = dict(os.environ, RSTACK_CALL_ROLE='referee')
    r = run_wrapper('exec', 'hello', env=env)
    assert r.returncode == 0, r.stderr
    assert 'referee bucket call 1/40 today for normal' in r.stderr
    start = [row for row in cb.read_rows(cb.state_dir() / 'codex-ledger/normal.jsonl') if row['event'] == 'start'][-1]
    assert start['bucket'] == 'referee' and start['role'] == 'referee'
    r = run_wrapper('exec', 'hello', env=dict(os.environ, RSTACK_CALL_ROLE='batch'))
    assert r.returncode == cb.REFUSED and 'past 50 calls' in r.stderr
