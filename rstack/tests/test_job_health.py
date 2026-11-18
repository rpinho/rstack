"""job-health: a failed scheduled job or a stale required output reaches a person (11-12, twice in a day)."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from rstack_hookcall import TOOLS


def load():
    loader = importlib.machinery.SourceFileLoader('job_health', str(TOOLS / 'job-health'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


jh = load()
LISTING = ('PID\tStatus\tLabel\n'
           '-\t0\tcom.example.fine\n'
           '-\t78\tcom.example.preview\n'
           '412\t1\tcom.example.running-now\n'
           '-\t1\tcom.example.lane-yield\n'
           '-\t1\tcom.other.not-ours\n')


def test_a_failed_last_run_is_a_problem_unless_that_code_is_declared_fine():
    jobs = jh.launchd_jobs('com.example.', LISTING)
    rows = jh.exit_problems(jobs, {'com.example.lane-yield': {'codes': [1], 'why': 'its FAIL verdict'}})
    assert rows == [('exit', 'com.example.preview', 'last run exited 78')]


def test_a_missing_or_stale_required_output_is_a_problem(tmp_path):
    """The X case: the job kept running and exiting 0, but its bookmark list stopped being rebuilt."""
    now = time.time()
    fresh, old = tmp_path / 'fresh.md', tmp_path / 'BOOKMARKS_FRESH.md'
    fresh.write_text('x')
    old.write_text('x')
    os.utime(old, (now - 72 * 3600, now - 72 * 3600))
    rows = jh.fresh_problems([dict(path=str(fresh), max_hours=6), dict(path=str(old), max_hours=6, why='X rounds'),
                              dict(path=str(tmp_path / 'gone.md'), max_hours=6)], now)
    assert [(k, os.path.basename(w)) for k, w, _ in rows] == [('fresh', 'BOOKMARKS_FRESH.md'), ('fresh', 'gone.md')]
    assert '72.0 h old' in rows[0][2]


def test_a_new_problem_alerts_once_and_shows_until_it_clears(tmp_path, monkeypatch):
    state, sent = tmp_path / 'state', tmp_path / 'sent.txt'
    stale = tmp_path / 'out.md'
    stale.write_text('x')
    os.utime(stale, (time.time() - 10 * 3600,) * 2)
    reg = tmp_path / 'reg.json'
    reg.write_text(json.dumps({'fresh': [{'path': str(stale), 'max_hours': 6, 'why': 'test'}]}))
    alert = "/bin/sh -c 'echo \"$0\" >> {}'".format(sent)
    run = lambda: subprocess.run([sys.executable, str(TOOLS / 'job-health'), '--prefix', 'com.nothing-matches.',
                                  '--registry', str(reg), '--alert', alert],
                                 env=dict(os.environ, RSTACK_STATE_DIR=str(state)), capture_output=True, text=True)
    assert run().returncode == 0 and run().returncode == 0               # a run that reports is not a failed job
    assert sent.read_text().count('job-health:') == 1                     # once per new problem, not per run
    listed = list((state / 'asks-waiting').glob('*-jobs.tsv'))[0].read_text()
    assert 'out.md' in listed                                             # the conductor sees it every turn
    stale.touch()
    assert run().returncode == 0
    assert list((state / 'asks-waiting').glob('*-jobs.tsv'))[0].read_text() == ''
    assert 'RECOVERED' in (state / 'job-health' / 'log').read_text()


def test_an_unreadable_registry_is_a_problem_not_an_all_clear(tmp_path):
    reg = tmp_path / 'reg.json'
    reg.write_text('{broken')
    r = subprocess.run([sys.executable, str(TOOLS / 'job-health'), '--prefix', 'com.nothing-matches.',
                        '--registry', str(reg), '--dry'], capture_output=True, text=True)
    assert r.returncode == 1 and 'unreadable' in r.stdout


def test_freshness_is_only_checked_in_the_hours_its_producer_runs(tmp_path):
    """11-13: the bookmark list is rebuilt 08:15-20:15; at 04:00 it is 8 h old by design, not stale."""
    f = tmp_path / 'list.md'
    f.write_text('x')
    now = time.mktime((2026, 11, 13, 4, 0, 0, 0, 0, -1))
    os.utime(f, (now - 8 * 3600,) * 2)
    entry = dict(path=str(f), max_hours=6, check_hours=[9, 22])
    assert jh.fresh_problems([entry], now) == []
    noon = time.mktime((2026, 11, 13, 12, 0, 0, 0, 0, -1))
    os.utime(f, (noon - 8 * 3600,) * 2)
    assert len(jh.fresh_problems([entry], noon)) == 1


def test_apple_agents_are_never_listed_and_a_bare_run_writes_nothing(tmp_path):
    """11-13: a bare run (no --prefix) on the M4 wrote 121 com.apple.* "exited -9" rows into the conductor's
    asks-waiting list, and they flooded every prompt."""
    listing = 'PID\tStatus\tLabel\n-\t-9\tcom.apple.Safari.History\n-\t78\tcom.example.preview\n'
    assert jh.exit_problems(jh.launchd_jobs('com.', listing), {}) == [('exit', 'com.example.preview', 'last run exited 78')]
    state = tmp_path / 'state'
    env = dict(os.environ, RSTACK_STATE_DIR=str(state))
    env.pop('JOB_HEALTH_PREFIX', None)
    r = subprocess.run([sys.executable, str(TOOLS / 'job-health'), '--registry', str(tmp_path / 'none.json')],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0 and 'only printed' in r.stderr
    assert not (state / 'asks-waiting').exists()


def test_a_disk_under_its_floor_is_a_problem_before_jobs_refuse():
    """11-14: the M4 hit 97% (15 GiB free, under the deploy floor) and the first signal was a failed deploy."""
    from collections import namedtuple
    U = namedtuple('U', 'total used free')
    gib = 2 ** 30
    entry = dict(path='/', min_free_gib=25, why='deploys refuse under 15 GiB')
    assert jh.disk_problems([entry], usage=lambda p: U(500 * gib, 485 * gib, 15 * gib))[0][2].startswith('15.0 GiB free')
    assert jh.disk_problems([entry], usage=lambda p: U(500 * gib, 400 * gib, 100 * gib)) == []


def test_the_host_label_is_stable_not_the_network_name(monkeypatch):
    """11-17: an unset HostName made the m5 report as 'mac' (network name mac.lan); RSTACK_HOST wins."""
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader('jh_host', str(TOOLS / 'job-health'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.setenv('RSTACK_HOST', 'm5')
    assert mod.host_label() == 'm5'
    monkeypatch.delenv('RSTACK_HOST')
    assert mod.host_label() and '.' not in mod.host_label()


X_FIXTURE = Path(__file__).parent / 'fixtures' / 'x-engage' / '2026-11-17.jsonl'
X_NOW = datetime(2026, 11, 17, 21, tzinfo=timezone.utc).timestamp()


def x_row(action, hours_ago=1, **extra):
    utc = datetime.fromtimestamp(X_NOW - hours_ago * 3600, timezone.utc).isoformat()
    return dict(action=action, utc=utc, **extra)


def x_check(tmp_path, rows):
    log = tmp_path / 'x.jsonl'
    log.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return jh.x_engage_problems(dict(path=str(log)), X_NOW)


def test_real_1117_rounds_and_pendings_without_execution_trip(tmp_path):
    """M4 sample: only utc/action and refusal reason survive; no tweet text or personal fields."""
    rows = [json.loads(line) for line in X_FIXTURE.read_text().splitlines()]
    assert all(set(r) <= {'utc', 'action', 'reason'} for r in rows)
    assert any(r['action'] == 'round_summary' for r in rows)
    assert not any(r['action'] in jh.X_EXECUTED for r in rows)
    # Remove refusals so this specifically catches the silent output failure.
    problems = x_check(tmp_path, [r for r in rows if r['action'] != 'post_refused'])
    assert [(k, w) for k, w, _ in problems] == [('x-engage', 'X engagement stalled')]
    detail = problems[0][2]
    assert 'no like/follow executed in 12h' in detail
    assert 'draft_reply=7' in detail and 'like_pending=28' in detail and 'follow_pending=17' in detail
    assert 'like=never' in detail and 'reply=never' in detail


def test_healthy_engagement_does_not_trip(tmp_path):
    assert x_check(tmp_path, [x_row('like_pending'), x_row('follow_pending'), x_row('draft_reply'),
                              x_row('like', 0.5), x_row('follow', 0.5), x_row('reply', 0.5)]) == []


def test_three_same_reason_refusals_trip_without_pending_work(tmp_path):
    problems = x_check(tmp_path, [x_row('post_refused', h, text='media upload failed') for h in (1, 2, 3)])
    assert len(problems) == 1
    assert '3 same-reason refusals in 24h' in problems[0][2]
    assert 'media upload failed (3x)' in problems[0][2]


def test_distinct_or_old_refusals_do_not_trip(tmp_path):
    rows = [x_row('post_refused', 1, reason=r) for r in ('media upload failed', 'lint', 'approval')]
    rows += [x_row('post_refused', h, reason='media upload failed') for h in (25, 26)]
    assert x_check(tmp_path, rows) == []


@pytest.mark.parametrize('success', jh.X_REPLIES)
def test_reply_success_variants_clear_the_48h_draft_rule(tmp_path, success):
    rows = [x_row('draft_reply', 20), x_row('like', 1), x_row(success, 47)]
    assert x_check(tmp_path, rows) == []


def test_old_unposted_drafts_still_trip_after_48h(tmp_path):
    problems = x_check(tmp_path, [x_row('draft_reply', 72), x_row('like', 1), x_row('reply', 49)])
    assert len(problems) == 1
    assert 'no reply/reply_posted/self_reply executed in 48h' in problems[0][2]
    assert 'no like/follow' not in problems[0][2]
    assert 'pending/all: draft_reply=1' in problems[0][2]


def test_any_pending_kind_and_either_like_or_follow_count(tmp_path):
    assert x_check(tmp_path, [x_row('owner_pending'), x_row('follow', 11)]) == []
    problems = x_check(tmp_path, [x_row('owner_pending'), x_row('like', 13),
                                 x_row('round_summary', 0), x_row('like_error', 0)])
    assert 'owner_pending=1' in problems[0][2]
    # Future-dated successes cannot hide a stall.
    assert x_check(tmp_path, [x_row('like_pending'), x_row('like', -1)])
    assert x_check(tmp_path, [x_row('like_pending', 13)]) == []
    assert x_check(tmp_path, [x_row('like_pending'), x_row('like', 12)]) == []


def test_missing_log_or_unconfigured_source_is_skipped(tmp_path, capsys, monkeypatch):
    def unexpected_ssh(*args, **kwargs):
        pytest.fail('an unconfigured source must never SSH')
    monkeypatch.setattr(jh.subprocess, 'run', unexpected_ssh)
    assert jh.x_engage_problems(None, X_NOW) == []
    assert 'skipped: no log configured' in capsys.readouterr().err
    assert jh.x_engage_problems(dict(path=str(tmp_path / 'missing')), X_NOW) == []
    assert 'skipped:' in capsys.readouterr().err


def test_ssh_source_is_explicit_read_only_and_bounded(monkeypatch, capsys):
    calls = []
    def ssh(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(x_row('like_pending')), '')
    monkeypatch.setattr(jh.subprocess, 'run', ssh)
    assert jh.x_engage_problems(dict(host='m4', path='~/.local/share/x-engage/log.jsonl'), X_NOW)
    argv, kwargs = calls[0]
    assert argv == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'm4',
                    'cat -- "$HOME"/.local/share/x-engage/log.jsonl']
    assert kwargs['timeout'] == 30
    def failed(*args, **kwargs):
        raise subprocess.TimeoutExpired('ssh', 30)
    monkeypatch.setattr(jh.subprocess, 'run', failed)
    assert jh.x_engage_problems(dict(host='m4', path='log.jsonl'), X_NOW) == []
    assert 'skipped:' in capsys.readouterr().err


def test_generic_heartbeat_can_read_a_pr_followup_ledger():
    rows = [dict(kind='followup_queued', utc=x_row('', 2)['utc'])]
    reasons, detail = jh.output_heartbeat(rows, ('followup_queued',), ('followup_sent',),
        [dict(hours=6, queued=('followup_queued',), executed=('followup_sent',))], X_NOW)
    assert reasons == ['no followup_sent executed in 6h']
    assert 'followup_queued=1' in detail


def test_x_stall_uses_existing_alert_dedup_and_push(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('RSTACK_HOST', 'test')
    monkeypatch.setattr(jh, 'launchd_jobs', lambda prefix: {})
    monkeypatch.setattr(jh.time, 'time', lambda: X_NOW)
    calls = []
    monkeypatch.setattr(jh.subprocess, 'run', lambda argv, **kw: (calls.append(argv) or subprocess.CompletedProcess(argv, 0)))
    reg = tmp_path / 'reg.json'
    reg.write_text(json.dumps({'x_engage': {'path': str(X_FIXTURE)}}))
    args = ['--prefix', 'com.example.', '--registry', str(reg), '--alert', 'notify', '--push', 'conductor']
    assert jh.main(args) == 0 and jh.main(args) == 0
    assert len([c for c in calls if c[0] == 'notify']) == 1
    assert 'X engagement stalled' in next(c[-1] for c in calls if c[0] == 'notify')
    assert len([c for c in calls if c[0] == 'scp']) == 2
    assert 'X engagement stalled' in (tmp_path / 'state/asks-waiting/test-jobs.tsv').read_text()
    healthy = tmp_path / 'healthy.jsonl'
    healthy.write_text(json.dumps(x_row('reply')) + '\n')
    # An explicit local CLI path overrides even a registry SSH source.
    reg.write_text(json.dumps({'x_engage': {'path': 'remote-log', 'host': 'm4'}}))
    assert jh.main(args + ['--x-engage-log', str(healthy)]) == 0
    assert (tmp_path / 'state/asks-waiting/test-jobs.tsv').read_text() == ''
    assert 'RECOVERED x-engage' in (tmp_path / 'state/job-health/log').read_text()
    assert not any('cat --' in c[-1] for c in calls)


@pytest.mark.parametrize('network,minutes,alerts', [
    ('starlink', 61, True), ('starlink', 30, False), ('starlink', 60, False),
    ('spectrum', 61, False), (None, 61, False),
])
def test_backup_network_duration(tmp_path, network, minutes, alerts):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(current_net=network, network_since=X_NOW - minutes * 60)))
    rows = jh.net_failover_problems(dict(path=str(state), label='M4'), X_NOW)
    if alerts:
        assert rows == [('net-failover', 'M4', 'M4 on backup network for 61 min (starlink)')]
    else:
        assert rows == []


def test_missing_backup_state_is_skipped_and_logged(tmp_path, capsys):
    assert jh.net_failover_problems(dict(path=str(tmp_path / 'missing')), X_NOW) == []
    assert 'net-failover skipped:' in capsys.readouterr().err


@pytest.mark.parametrize('contents', [
    '{broken', '[]', '{"bad": 0, "last_switch": 100}',
    '{"current_net": "starlink"}',
    '{"current_net": "starlink", "network_since": "yesterday"}',
    '{"current_net": "starlink", "network_since": true}',
    '{"current_net": "starlink", "network_since": NaN}',
    '{"current_net": "starlink", "network_since": 9999999999}',
])
def test_unusable_backup_state_is_skipped_with_a_reason(tmp_path, capsys, contents):
    state = tmp_path / 'state.json'
    state.write_text(contents)
    assert jh.net_failover_problems(dict(path=str(state)), X_NOW) == []
    assert 'net-failover skipped:' in capsys.readouterr().err


def test_backup_check_is_opt_in_and_reads_locally_without_host(tmp_path, monkeypatch):
    monkeypatch.setattr(jh.subprocess, 'run', lambda *a, **k: pytest.fail('unexpected SSH'))
    assert jh.net_failover_problems(None, X_NOW) == []
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(current_net='starlink', network_since=X_NOW - 3660)))
    assert jh.net_failover_problems(dict(path=str(state), label='M4'), X_NOW)


def test_remote_backup_state_read_is_explicit_bounded_and_read_only(monkeypatch, capsys):
    calls = []
    def ssh(argv, **kwargs):
        calls.append((argv, kwargs))
        state = dict(current_net='starlink', network_since=X_NOW - 3660)
        return subprocess.CompletedProcess(argv, 0, json.dumps(state), '')
    monkeypatch.setattr(jh.subprocess, 'run', ssh)
    source = dict(host='m4', path='~/.local/state/net-failover/state.json', label='M4')
    assert jh.net_failover_problems(source, X_NOW)
    argv, kwargs = calls[0]
    assert argv == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'm4',
                    'cat -- "$HOME"/.local/state/net-failover/state.json']
    assert kwargs['timeout'] == 30
    monkeypatch.setattr(jh.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 1, '', 'missing'))
    assert jh.net_failover_problems(source, X_NOW) == []
    assert 'SSH state read failed' in capsys.readouterr().err


def test_backup_alarm_uses_existing_alert_dedup_push_and_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'report'))
    monkeypatch.setenv('RSTACK_HOST', 'test')
    monkeypatch.setattr(jh, 'launchd_jobs', lambda prefix: {})
    monkeypatch.setattr(jh.time, 'time', lambda: X_NOW)
    calls = []
    monkeypatch.setattr(jh.subprocess, 'run', lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, '', ''))
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(current_net='starlink', network_since=X_NOW - 3660)))
    reg = tmp_path / 'reg.json'
    reg.write_text(json.dumps({'net_failover': {'path': str(state), 'label': 'M4'}}))
    args = ['--prefix', 'com.example.', '--registry', str(reg), '--alert', 'notify', '--push', 'conductor']
    assert jh.main(args + ['--dry']) == 1
    assert calls == [] and not (tmp_path / 'report').exists()
    assert jh.main(args) == 0
    state.write_text(json.dumps(dict(current_net='starlink', network_since=X_NOW - 7200)))
    assert jh.main(args) == 0  # changing duration must not produce a second alert
    assert len([c for c in calls if c[0] == 'notify']) == 1
    assert 'M4 on backup network for 61 min' in next(c[-1] for c in calls if c[0] == 'notify')
    assert len([c for c in calls if c[0] == 'scp']) == 2
    listed = tmp_path / 'report/asks-waiting/test-jobs.tsv'
    assert 'M4 on backup network for 120 min' in listed.read_text()
    state.write_text(json.dumps(dict(current_net='spectrum', network_since=X_NOW)))
    assert jh.main(args) == 0 and listed.read_text() == ''
    assert 'RECOVERED net-failover' in (tmp_path / 'report/job-health/log').read_text()


def test_failed_alert_is_retried_instead_of_marked_delivered(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('RSTACK_HOST', 'test')
    rows = [('codex-bypass', '/rollout', 'cwd=/missed/lane')]
    jh.report(rows, 'job-health', 'jobs', 'job', '/usr/bin/false')
    seen = tmp_path / 'state/job-health/seen.json'
    assert json.loads(seen.read_text()) == []
    sent = tmp_path / 'sent'
    alert = "/bin/sh -c 'echo \"$0\" >> {}'".format(sent)
    jh.report(rows, 'job-health', 'jobs', 'job', alert)
    jh.report(rows, 'job-health', 'jobs', 'job', alert)
    assert sent.read_text().count('codex-bypass') == 1
