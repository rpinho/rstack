"""Offline resource headroom, independent starts, and durable receipt regression tests."""
import contextlib
import datetime as dt
import fcntl
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rh
import sweep


@pytest.fixture
def cfg(tmp_path):
    return dict(cwd=tmp_path, min_free_gib=30, min_free_memory_gib=6, memory_gib=6,
                max_load=8, max_cpu_busy_fraction=.85, cores=1, load_wait_minutes=0,
                worker_timeout_minutes=90, stagger_seconds=0)


@pytest.fixture
def lane(tmp_path):
    lane = tmp_path / 'lanes/test'
    lane.mkdir(parents=True)
    return lane


def test_network_bound_high_load_does_not_block_worker(cfg):
    with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', return_value=.1),\
            patch.object(sweep, 'free_memory_gib', return_value=12), patch.object(sweep.os, 'cpu_count', return_value=10),\
            patch.object(sweep.os, 'getloadavg', side_effect=AssertionError('load must not be read')):
        sweep.guard(cfg)


@pytest.mark.parametrize('busy,free,reason', [(.91, 12, 'CPU headroom'), (.1, 2, 'free memory'), (.1, None, 'memory unavailable')])
def test_cpu_or_memory_pressure_refuses(cfg, busy, free, reason):
    with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', return_value=busy),\
            patch.object(sweep, 'free_memory_gib', return_value=free), patch.object(sweep.os, 'cpu_count', return_value=10),\
            pytest.raises(ValueError, match=reason):
        sweep.guard(cfg)


def test_reserve_requested_worker_cores(cfg):
    cfg['cores'] = 3
    with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', return_value=.75),\
            patch.object(sweep, 'free_memory_gib', return_value=12), patch.object(sweep.os, 'cpu_count', return_value=10),\
            pytest.raises(ValueError, match='CPU headroom'):
        sweep.guard(cfg)


def test_headroom_waits_then_proceeds(cfg):
    cfg['load_wait_minutes'] = 1
    with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', side_effect=[.99, .1]),\
            patch.object(sweep, 'free_memory_gib', return_value=12), patch.object(sweep.os, 'cpu_count', return_value=10),\
            patch.object(sweep.time, 'sleep') as sleep:
        sweep.guard(cfg)
    sleep.assert_called_once_with(30)


def test_load_fallback_is_configurable(cfg):
    with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', return_value=None),\
            patch.object(sweep, 'free_memory_gib', return_value=12), patch.object(sweep.os, 'getloadavg', return_value=(10, 10, 10)):
        with pytest.raises(ValueError, match='fallback 5-min load'):
            sweep.guard(cfg)
        cfg['max_load'] = 12
        sweep.guard(cfg)
        cfg['load_fallback'] = False
        with pytest.raises(ValueError, match='fallback disabled'):
            sweep.guard(cfg)


def test_cpu_busy_sums_process_utilization_per_core():
    with patch.object(sweep.subprocess, 'check_output', return_value='90.0\n25.0\n10.0\n') as ps,\
            patch.object(sweep.os, 'cpu_count', return_value=10):
        assert sweep.cpu_busy() == .125
        assert ps.call_args[0][0] == ['ps', '-A', '-o', 'pcpu=']


@pytest.mark.parametrize('output', ['', 'not a number', 'nan', '-1'])
def test_cpu_unavailable_requests_fallback(output):
    with patch.object(sweep.subprocess, 'check_output', return_value=output):
        assert sweep.cpu_busy() is None


def test_vm_stat_available_memory_without_double_counting():
    output = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
              'Pages free: 100000.\nPages inactive: 200000.\nPages speculative: 300000.\n'
              'Pages purgeable: 400000.\nPages wired down: 500000.\n')
    with patch.object(sweep.sys, 'platform', 'darwin'), patch.object(sweep.subprocess, 'check_output', return_value=output):
        assert sweep.free_memory_gib() == 600000 * 16384 / 1024**3


def test_memory_unavailable_refuses_instead_of_guessing():
    with patch.object(sweep.sys, 'platform', 'darwin'), patch.object(sweep.subprocess, 'check_output', return_value='bad'):
        assert sweep.free_memory_gib() is None


def test_started_receipt_exists_before_guard_and_is_finished_on_refusal(lane, cfg):
    def guard(_):
        rows = rh.rows(lane / 'SWEEP_RUNS.jsonl')
        assert len(rows) == 1 and rows[0]['status'] == 'started' and rows[0]['ok'] is None
        raise ValueError('no CPU')
    with patch.object(sweep, 'guard', side_effect=guard), patch.object(sweep, 'run_lane', side_effect=AssertionError('must not launch')):
        assert sweep.run_locked(lane, cfg, rh, threading.Event()) == 1
    rows = rh.rows(lane / 'SWEEP_RUNS.jsonl')
    assert rows[-1]['status'] == 'finished' and rows[-1]['ok'] is False
    assert rows[0]['id'] == rows[-1]['id'] and rows[-1]['finished']
    assert sweep.receipt_health(lane, rh) == []


def test_started_receipt_finishes_on_interrupt(lane, cfg):
    with patch.object(sweep, 'guard', side_effect=KeyboardInterrupt()), pytest.raises(KeyboardInterrupt):
        sweep.run_locked(lane, cfg, rh, threading.Event())
    rows = rh.rows(lane / 'SWEEP_RUNS.jsonl')
    assert rows[0]['ok'] is None and rows[-1]['ok'] is False
    assert sweep.receipt_health(lane, rh) == []


def test_started_hung_threshold_latest_finish_and_static_check(lane):
    clock = dt.datetime(2026, 11, 3, 18, tzinfo=dt.timezone.utc)
    row = dict(id='hung', status='started', ok=None, worker_timeout_minutes=10,
               started=(clock - dt.timedelta(minutes=60)).isoformat())
    rh.append(lane / 'SWEEP_RUNS.jsonl', row)
    with patch.object(rh, 'now', return_value=clock.isoformat()):
        assert sweep.lint(lane, rh) == ([], [])
    with patch.object(rh, 'now', return_value=(clock + dt.timedelta(seconds=1)).isoformat()):
        errors = sweep.receipt_health(lane, rh)
        assert len(errors) == 1 and errors[0].startswith('sweep-hung')
        kinds = rh.LintErrors()
        kinds.add_many('sweep-obligations', errors)
        assert kinds.failures[0]['check'] == 'sweep-hung'
        rh.append(lane / 'SWEEP_RUNS.jsonl', dict(row, status='finished', finished=clock.isoformat(), ok=False))
        assert sweep.receipt_health(lane, rh) == []


def test_lane_lock_refuses_only_same_lane(lane, cfg):
    with (lane / '.sweep-run.lock').open('a') as lock, patch.object(sweep, 'guard'), patch.object(sweep, 'run_lane', return_value=0):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert sweep.run_locked(lane, cfg, rh, threading.Event()) == 1
        other = lane.parent / 'other'
        other.mkdir()
        assert sweep.run_locked(other, cfg, rh, threading.Event()) == 0


def test_legacy_root_lock_is_not_opened_or_modified(lane, cfg):
    root = lane.parent.parent
    legacy = root / '.sweep.lock'
    legacy.write_text('legacy lock sentinel')
    before = legacy.stat()
    with legacy.open('r') as lock, patch.object(sweep, 'guard'), patch.object(sweep, 'run_lane', return_value=0):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert sweep.run_locked(lane, cfg, rh, threading.Event()) == 0
    assert legacy.read_text() == 'legacy lock sentinel'
    assert legacy.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize('first_failure', [False, True])
def test_all_starts_next_lane_while_first_waits_or_fails(lane, cfg, first_failure):
    root = lane.parent.parent
    other = lane.parent / 'zz'
    other.mkdir()
    next_started = threading.Event()
    visits = []
    def run(which, *args):
        visits.append(which.name)
        if which == lane:
            assert next_started.wait(2), 'second lane was starved by first'
            if first_failure:
                raise ValueError('first failed')
        else:
            next_started.set()
        return 0
    args = type('Args', (), dict(all=True, dry_run=False))()
    with patch.object(sweep, 'load', return_value=dict(cfg, enabled=True)), patch.object(sweep, 'guard'),\
            patch.object(sweep, 'run_lane', side_effect=run), patch.object(sweep.time, 'sleep') as sleep:
        assert sweep.main(root, args, rh) == int(first_failure)
    assert set(visits) == {'test', 'zz'}
    sleep.assert_called_once_with(0)
    for which in (lane, other):
        rows = rh.rows(which / 'SWEEP_RUNS.jsonl')
        assert rows[0]['ok'] is None and rows[-1]['status'] == 'finished'


def test_cancelled_wait_and_worker_guard_refuse_immediately(cfg):
    event = threading.Event()
    event.set()
    cfg['_cancel'] = event
    with pytest.raises(ValueError, match='cancelled'):
        sweep.guard(cfg)


def test_darwin_memory_uses_kernel_free_percentage_when_larger():
    vm = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
          'Pages free: 100000.\nPages inactive: 100000.\nPages speculative: 0.\n')
    def fake(cmd, **kw):
        return {'vm_stat': vm, 'memory_pressure': 'System-wide memory free percentage: 50%\n',
                'sysctl': str(16 * 1024**3)}[cmd[0]]
    with patch.object(sweep.sys, 'platform', 'darwin'), patch.object(sweep.subprocess, 'check_output', side_effect=fake):
        assert sweep.free_memory_gib() == 8.0


def test_memory_floor_defaults_below_worker_cap():
    assert sweep.default_memory_floor({'memory_gib': 6}) == 2
    assert sweep.default_memory_floor({'memory_gib': 1}) == 1


def test_the_disk_floor_announces_itself_once_per_episode(tmp_path, monkeypatch):
    """11-06: the daily sweep refused every lane on this floor for a whole day in silence.
    The lanes looked stopped and the conductor went looking for a model shortage.
    """
    import sweep as sw
    queue = tmp_path / 'alerts.jsonl'
    mark = tmp_path / 'mark'
    monkeypatch.setenv('RH_AGENT_ALERTS', str(queue))
    monkeypatch.setattr(sw, 'DISK_MARK', mark)
    cfg = {'cwd': str(tmp_path), 'min_free_gib': 30, 'controller_min_free_gib': 2}

    class Usage:
        free = 5 * 1024**3

    monkeypatch.setattr(sw.shutil, 'disk_usage', lambda p: Usage())
    for _ in range(3):  # five lanes refusing one full disk is one fact
        with pytest.raises(ValueError, match='this machine .5.0 GiB free, needs 30 GiB'):
            sw.disk_guard(cfg)
    rows = [json.loads(l) for l in queue.read_text().splitlines() if l.strip()]
    assert len(rows) == 1, 'alerted once, not once per lane'
    assert '5.0 GiB free' in rows[0]['message'] and 'needs 30 GiB' in rows[0]['message']
    assert mark.exists()

    # Clearing the floor retires the marker, so the next episode alerts again.
    Usage.free = 80 * 1024**3
    sw.disk_guard(cfg)
    assert not mark.exists()
    Usage.free = 5 * 1024**3
    with pytest.raises(ValueError):
        sw.disk_guard(cfg)
    assert len([l for l in queue.read_text().splitlines() if l.strip()]) == 2
