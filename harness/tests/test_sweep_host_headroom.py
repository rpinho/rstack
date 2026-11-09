"""Memory, CPU and the work dir are read on the machine that runs the workers.

11-07, same incident as the disk floor and the same day. The science runs moved to a second
machine with 18 cores and 48 GB, and every precondition still measured the 10-core, 16 GB
controller: a lane on the m5 could be refused for "insufficient free memory" while the m5 had
tens of gigabytes spare, and could be admitted while the m5 was full.

The second half of this file is a near-miss rather than an outage. `launch.sh --host` checks that
the work dir exists on the host, and the m5 had directories sitting at the lane paths holding five
files and no IDEAS.jsonl, left over from the move. Pointing math at the m5 that afternoon would
have passed that check and run a worker against a stub.

`ssh` is a stub script here, so these exercise the real probe program and the real parsing.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sweep

GIB = 1024 ** 3


@pytest.fixture
def cfg(tmp_path):
    return {'cwd': str(tmp_path), 'min_free_gib': 30, 'controller_min_free_gib': 2, 'host': 'm5',
            'cores': 2, 'memory_gib': 6, 'min_free_memory_gib': 6, 'max_load': 8,
            'load_wait_minutes': 0, 'max_cpu_busy_fraction': .85}


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, 'DISK_MARK', tmp_path / 'mark')
    monkeypatch.delenv('LAUNCH_HOST', raising=False)
    monkeypatch.delenv('LAUNCH_SSH', raising=False)
    # The disk floor is tested next door; give it room so it never masks these refusals.
    monkeypatch.setattr(sweep.shutil, 'disk_usage',
                        lambda p: shutil._ntuple_diskusage(10_000 * GIB, 0, 9_000 * GIB))
    monkeypatch.setattr(sweep, 'host_free_bytes', lambda host, path: 800 * GIB)


def stub_ssh(tmp_path, monkeypatch, body, name='fake-ssh'):
    """A stub ssh that runs `body` locally instead of on a host.

    `sh -s` is the last argument and the probe arrives on stdin, so a stub that execs the given
    body reads the same stdin the real host would.
    """
    script = tmp_path / name
    script.write_text('#!/bin/sh\n' + body + '\n')
    script.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(script))
    return script


# The probe's own output shape, as a host would print it.
def answers(cores=18, free_gib=30.0, busy_pcpu=90.0):
    return ("printf 'cores=%s\\nfree_gib=%s\\nbusy_pcpu=%s\\n' {} {} {}"
            .format(cores, free_gib, busy_pcpu))


def test_the_probe_program_runs_and_parses(tmp_path, monkeypatch):
    """Run the real HOST_PROBE text through a local shell: this machine stands in for the host, so
    the shell program itself is exercised rather than a fixture of its output."""
    stub_ssh(tmp_path, monkeypatch, 'shift; exec /bin/sh -s')   # drop the host argument
    probe = sweep.host_probe('m5')
    assert probe is not None
    assert probe['cores'] == os.cpu_count()
    assert probe['free_gib'] > 0
    assert 0 <= probe['busy'] < 64            # a fraction, not a sum of percentages


def test_the_hosts_memory_is_the_floor_not_the_controllers(cfg, tmp_path, monkeypatch):
    """The refusal that stalled math, in the other direction: the controller is full, the host is
    not, and the work runs on the host."""
    monkeypatch.setattr(sweep, 'free_memory_gib', lambda: 0.2)
    monkeypatch.setattr(sweep, 'cpu_busy', lambda: 0.99)
    stub_ssh(tmp_path, monkeypatch, answers(free_gib=30.0, busy_pcpu=20.0))
    sweep.guard(cfg)                                            # no wait, no refusal


def test_a_full_host_is_not_admitted_because_the_controller_is_idle(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, 'free_memory_gib', lambda: 64.0)
    monkeypatch.setattr(sweep, 'cpu_busy', lambda: 0.01)
    stub_ssh(tmp_path, monkeypatch, answers(free_gib=0.4, busy_pcpu=10.0))
    with pytest.raises(ValueError) as e:
        sweep.guard(cfg)
    assert 'insufficient free memory' in str(e.value)


def test_a_busy_host_is_not_admitted_either(cfg, tmp_path, monkeypatch):
    stub_ssh(tmp_path, monkeypatch, answers(cores=18, free_gib=40.0, busy_pcpu=18 * 95))
    with pytest.raises(ValueError) as e:
        sweep.guard(cfg)
    assert 'insufficient CPU headroom' in str(e.value)


def test_busy_is_scaled_by_the_hosts_cores_not_this_machines(cfg, tmp_path, monkeypatch):
    """1,000% of CPU is idle on 18 cores and overloaded on 4. Reading the core count from the
    controller would make the same host look busy or free depending on which machine asked."""
    stub_ssh(tmp_path, monkeypatch, answers(cores=18, free_gib=40.0, busy_pcpu=1000.0))
    sweep.guard(cfg)
    stub_ssh(tmp_path, monkeypatch, answers(cores=4, free_gib=40.0, busy_pcpu=1000.0))
    with pytest.raises(ValueError) as e:
        sweep.guard(cfg)
    assert 'insufficient CPU headroom' in str(e.value)


@pytest.mark.parametrize('body', [
    'exit 255',                                   # ssh failed
    'true',                                       # no output
    "printf 'cores=18\\n'",                       # partial output
    "printf 'cores=0\\nfree_gib=1\\nbusy_pcpu=1\\n'",        # a machine with no cores
    "printf 'cores=x\\nfree_gib=1\\nbusy_pcpu=1\\n'",        # not a number
])
def test_an_unreadable_host_refuses_rather_than_assuming_headroom(cfg, tmp_path, monkeypatch, body):
    """A guard that passes when it cannot read the machine is not a guard. It must also not fall
    back to this machine's numbers, which is the whole bug."""
    monkeypatch.setattr(sweep, 'free_memory_gib', lambda: 64.0)
    monkeypatch.setattr(sweep, 'cpu_busy', lambda: 0.0)
    stub_ssh(tmp_path, monkeypatch, body)
    with pytest.raises(ValueError) as e:
        sweep.guard(cfg)
    assert 'cannot read memory or CPU on m5' in str(e.value)


def test_without_a_host_nothing_is_probed(cfg, tmp_path, monkeypatch):
    cfg['host'] = ''
    stub_ssh(tmp_path, monkeypatch, 'echo should-not-run >&2; exit 1')
    monkeypatch.setattr(sweep, 'host_probe',
                        lambda host: pytest.fail('probed with no host: ' + repr(host)))
    monkeypatch.setattr(sweep, 'free_memory_gib', lambda: 64.0)
    monkeypatch.setattr(sweep, 'cpu_busy', lambda: 0.01)
    sweep.guard(cfg)


# --- the work dir on the host -------------------------------------------------------------------

def test_a_stub_work_dir_on_the_host_is_refused_by_name(cfg, tmp_path, monkeypatch):
    """The 11-07 near-miss. The m5 had the lane's path with five files in it and no ledger; the
    existence check launch.sh does would have passed and a worker would have run against it."""
    stub_ssh(tmp_path, monkeypatch, 'shift; exec /bin/sh -s')
    (tmp_path / 'RULES.md').write_text('rules\n')
    (tmp_path / 'INTAKE.toml').write_text('')            # present but empty counts as missing
    missing = sweep.host_workdir_missing('m5', tmp_path, ['RULES.md', 'INTAKE.toml', 'IDEAS.jsonl'])
    assert missing == ['INTAKE.toml', 'IDEAS.jsonl']


def test_a_complete_work_dir_on_the_host_passes(tmp_path, monkeypatch):
    stub_ssh(tmp_path, monkeypatch, 'shift; exec /bin/sh -s')
    for name in ('RULES.md', 'INTAKE.toml'):
        (tmp_path / name).write_text('x\n')
    assert sweep.host_workdir_missing('m5', tmp_path, ['RULES.md', 'INTAKE.toml']) == []


def test_an_unreadable_work_dir_is_not_an_empty_list(tmp_path, monkeypatch):
    """None and [] must not be confused: [] means checked and complete."""
    stub_ssh(tmp_path, monkeypatch, 'exit 255')
    assert sweep.host_workdir_missing('m5', tmp_path, ['RULES.md']) is None


def test_a_path_with_spaces_survives_the_remote_shell(tmp_path, monkeypatch):
    stub_ssh(tmp_path, monkeypatch, 'shift; exec /bin/sh -s')
    work = tmp_path / 'lane dir with spaces'
    work.mkdir()
    (work / 'RULES.md').write_text('x\n')
    assert sweep.host_workdir_missing('m5', work, ['RULES.md', 'INTAKE.toml']) == ['INTAKE.toml']


def test_run_worker_refuses_before_spend_when_the_host_lacks_the_lane(cfg, tmp_path, monkeypatch):
    launcher = tmp_path / 'launcher'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    spec = tmp_path / 'worker.md'
    spec.write_text('fixture')
    cfg.update(launcher_path=launcher, rules=[(str(tmp_path / 'RULES.md'), 'rules')],
               worker_timeout_minutes=1)
    monkeypatch.setattr(sweep, 'guard', lambda c: None)
    monkeypatch.setattr(sweep, 'host_sync', lambda c, h: True)
    monkeypatch.setattr(sweep, 'host_workdir_missing',
                        lambda host, cwd, names: ['RULES.md', 'INTAKE.toml'])
    monkeypatch.setattr(sweep.subprocess, 'Popen',
                        lambda *a, **k: pytest.fail('a worker was started against a stub work dir'))
    with pytest.raises(ValueError) as e:
        sweep.run_worker(spec, cfg)
    assert 'missing or empty: INTAKE.toml, RULES.md' in str(e.value)


# --- the one-way mirror ------------------------------------------------------------------------

def test_the_lane_is_pushed_to_the_host_before_a_worker_reads_it(cfg, tmp_path, monkeypatch):
    """math, 11-07: "only as a one-way mirror, never as two live ledgers". The worker has to read
    the current queue, so the controller refreshes the host before the run."""
    lane, host_copy = tmp_path / 'lane', tmp_path / 'hostcopy'
    lane.mkdir(); host_copy.mkdir()
    (lane / 'IDEAS.jsonl').write_text('{"id": "A-1"}\n')
    (lane / 'RULES.md').write_text('rules\n')
    (lane / 'work').mkdir()
    (lane / 'work/worker-output.txt').write_text('written on the host\n')
    (host_copy / 'IDEAS.jsonl').write_text('stale\n')
    (host_copy / 'work').mkdir()
    (host_copy / 'work/worker-output.txt').write_text('the host wrote this; do not clobber it\n')
    # A stub ssh for rsync: it rewrites the host-side path to the local copy, so a real rsync runs.
    stub = tmp_path / 'rsync-ssh'
    stub.write_text('#!/bin/sh\nshift\nexec /bin/sh -c "$*"\n')
    stub.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(stub))
    cfg.update(cwd=str(lane), run_directory='work/runs', allowed_writes=['work/'])
    calls = {}
    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        calls['argv'] = argv
        return real_run([a.replace('m5:' + str(lane) + '/', str(host_copy) + '/') for a in argv],
                        **kwargs)

    monkeypatch.setattr(sweep.subprocess, 'run', fake_run)
    assert sweep.host_sync(cfg, 'm5') is True
    assert '--exclude=/work/' in calls['argv']
    assert (host_copy / 'IDEAS.jsonl').read_text() == '{"id": "A-1"}\n'
    assert (host_copy / 'RULES.md').exists()
    # What the worker writes there is left alone: the mirror refreshes reads, it does not reach
    # into the run directory, and it never deletes.
    assert 'do not clobber' in (host_copy / 'work/worker-output.txt').read_text()


def test_a_failed_refresh_refuses_instead_of_running_on_a_stale_lane(cfg, tmp_path, monkeypatch):
    launcher = tmp_path / 'launcher'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    spec = tmp_path / 'worker.md'
    spec.write_text('fixture')
    cfg.update(launcher_path=launcher, rules=[], worker_timeout_minutes=1)
    monkeypatch.setattr(sweep, 'guard', lambda c: None)
    monkeypatch.setattr(sweep, 'host_sync', lambda c, h: False)
    monkeypatch.setattr(sweep, 'host_workdir_missing',
                        lambda *a: pytest.fail('checked the host after a failed refresh'))
    monkeypatch.setattr(sweep.subprocess, 'Popen',
                        lambda *a, **k: pytest.fail('a worker ran against a stale lane'))
    with pytest.raises(ValueError) as e:
        sweep.run_worker(spec, cfg)
    assert 'cannot refresh' in str(e.value) and 'stale copy' in str(e.value)


def test_the_host_check_asks_for_files_the_work_dir_really_has(tmp_path):
    """virtual-embryo, 11-08: its work dir is a project directory, and its rules files live in the lane
    directory, in neither copy of the work dir, so asking the host for them could never pass. They
    travel inside the prompt anyway; the check proves the host copy is not a stub."""
    lane, project = tmp_path / 'lane', tmp_path / 'project'
    lane.mkdir(); project.mkdir()
    for name in ('SWEEP_KILL_RULES.md', 'INTAKE.toml'):
        (lane / name).write_text('x\n')
    rules = [(str(lane / 'SWEEP_KILL_RULES.md'), 'x'), (str(lane / 'INTAKE.toml'), 'x')]
    assert sweep.host_check_names(dict(cwd=str(lane), rules=rules)) == ['SWEEP_KILL_RULES.md', 'INTAKE.toml']
    (project / 'README.md').write_text('x\n')
    (project / 'model.py').write_text('x\n')
    (project / 'empty.txt').write_text('')
    (project / '.hidden').write_text('x\n')
    (project / 'runs').mkdir()
    names = sweep.host_check_names(dict(cwd=str(project), rules=rules, run_directory='runs'))
    assert names == ['README.md', 'model.py']
