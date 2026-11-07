"""The disk floor measures the machine that runs the workers, not always the controller.

11-07: the science runs moved to a second machine, and the floor kept reading the controller's
disk. `rh sweep math` was refused for "less than 30 GiB free" while the machine actually doing the
work had hundreds of gigabytes spare, and the lane went to "deliverable cadence STALLED" because of
it. A guard measuring the wrong machine is worse than no guard: it stops real work and the message
sends you to look at the wrong disk.

`ssh` is replaced by a stub, so these tests exercise the real df parsing rather than a mock of it.
"""
import os
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sweep

GIB = 1024 ** 3


@pytest.fixture
def cfg(tmp_path):
    return {'cwd': str(tmp_path), 'min_free_gib': 30, 'controller_min_free_gib': 2}


@pytest.fixture(autouse=True)
def no_marker_or_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, 'DISK_MARK', tmp_path / 'mark')
    monkeypatch.delenv('LAUNCH_HOST', raising=False)
    monkeypatch.delenv('LAUNCH_SSH', raising=False)


def fake_ssh(tmp_path, monkeypatch, *, avail_kb=None, rc=0, output=None):
    """A stub ssh that answers `df -k` with the given available kilobytes."""
    script = tmp_path / 'fake-ssh'
    if output is None:
        output = ('Filesystem 1024-blocks Used Available Capacity Mounted on\n'
                  '/dev/disk3s5 482797044 100 {} 5% /\n'.format(avail_kb))
    script.write_text('#!/bin/sh\nprintf %s "$DF_OUT"\nexit {}\n'.format(rc))
    script.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(script))
    monkeypatch.setenv('DF_OUT', output)
    return script


def local_free(monkeypatch, gib):
    monkeypatch.setattr(sweep.shutil, 'disk_usage',
                        lambda p: shutil._ntuple_diskusage(10_000 * GIB, 0, int(gib * GIB)))


def test_without_a_host_the_controller_disk_is_the_floor(cfg, monkeypatch):
    local_free(monkeypatch, 12)
    with pytest.raises(ValueError) as e:
        sweep.disk_guard(cfg)
    assert 'this machine' in str(e.value) and '12.0 GiB' in str(e.value)
    local_free(monkeypatch, 31)
    sweep.disk_guard(cfg)


def test_with_a_host_the_hosts_disk_is_the_floor(cfg, tmp_path, monkeypatch):
    """The exact case that stalled math: 12 GiB here, hundreds there, work happens there."""
    local_free(monkeypatch, 12)
    monkeypatch.setenv('LAUNCH_HOST', 'm5')
    fake_ssh(tmp_path, monkeypatch, avail_kb=800 * 1024 * 1024)   # 800 GiB free on the host
    sweep.disk_guard(cfg)                                          # no refusal


def test_a_short_host_is_refused_and_named(cfg, tmp_path, monkeypatch):
    local_free(monkeypatch, 500)
    monkeypatch.setenv('LAUNCH_HOST', 'm5')
    fake_ssh(tmp_path, monkeypatch, avail_kb=5 * 1024 * 1024)      # 5 GiB free on the host
    with pytest.raises(ValueError) as e:
        sweep.disk_guard(cfg)
    assert 'm5' in str(e.value) and '5.0 GiB' in str(e.value) and 'workers need 30' in str(e.value)


def test_the_controller_still_needs_room_for_its_own_bookkeeping(cfg, tmp_path, monkeypatch):
    """Specs, logs, receipts and the pulled-back status files land here even when the work does
    not, so a controller with nothing left still refuses, with a smaller floor and its own words."""
    local_free(monkeypatch, 1)
    monkeypatch.setenv('LAUNCH_HOST', 'm5')
    fake_ssh(tmp_path, monkeypatch, avail_kb=800 * 1024 * 1024)
    with pytest.raises(ValueError) as e:
        sweep.disk_guard(cfg)
    assert 'this machine' in str(e.value) and 'controller needs 2' in str(e.value)


@pytest.mark.parametrize('kwargs', [
    dict(rc=255, avail_kb=1),                       # ssh failed
    dict(output='', avail_kb=None),                 # no output
    dict(output='Filesystem 1024-blocks\n', avail_kb=None),   # header only
    dict(output='/dev/disk3s5 482797044 100 notanumber 5% /\n', avail_kb=None),
])
def test_an_unreadable_host_disk_refuses_rather_than_assuming_room(cfg, tmp_path, monkeypatch, kwargs):
    """A guard that passes when it cannot read the disk is not a guard."""
    local_free(monkeypatch, 500)
    monkeypatch.setenv('LAUNCH_HOST', 'm5')
    fake_ssh(tmp_path, monkeypatch, **kwargs)
    with pytest.raises(ValueError) as e:
        sweep.disk_guard(cfg)
    assert 'cannot read the disk' in str(e.value)


def test_a_missing_ssh_binary_refuses_too(cfg, tmp_path, monkeypatch):
    local_free(monkeypatch, 500)
    monkeypatch.setenv('LAUNCH_HOST', 'm5')
    monkeypatch.setenv('LAUNCH_SSH', str(tmp_path / 'no-such-ssh'))
    with pytest.raises(ValueError) as e:
        sweep.disk_guard(cfg)
    assert 'cannot read the disk' in str(e.value)


def test_the_marker_clears_when_the_floor_is_met_again(cfg, tmp_path, monkeypatch):
    """The 11-06 behaviour: announce once per episode, and a new episode announces again."""
    sweep.DISK_MARK.parent.mkdir(parents=True, exist_ok=True)
    sweep.DISK_MARK.write_text('earlier')
    local_free(monkeypatch, 31)
    sweep.disk_guard(cfg)
    assert not sweep.DISK_MARK.exists()
