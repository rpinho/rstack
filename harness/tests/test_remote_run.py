"""A --host job outlives this machine's ssh session.

11-07: a network blip ended math's five-hour codetables job, because the executor was the
foreground command of one ssh. 11-08: the controller reset at 22:16 and every job on the host died
with its driver, on a host that had nothing wrong with it. These tests run the real remote_run.py
against an ssh stand-in that executes on this machine and can be switched "down", and they check
the effect where it lands: the executor's own output and exit code, and how many times it started.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'tools/remote_run.py'


def world(tmp_path, program):
    """An ssh stand-in, a host attempts root, a prompt and a remote program."""
    down = tmp_path / 'link-down'
    ssh = tmp_path / 'ssh'
    ssh.write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\n'
                   '[ -e ' + str(down) + ' ] && exit 255\nexec /bin/sh -c "$1"\n')
    ssh.chmod(0o755)
    (tmp_path / 'prompt').write_text('the prompt\n')
    (tmp_path / 'run.sh').write_text(program)
    env = dict(os.environ, LAUNCH_SSH=str(ssh),
               LAUNCH_REMOTE_ATTEMPTS=str(tmp_path / 'host-attempts'),
               LAUNCH_REMOTE_POLL_S='0.2', LAUNCH_REMOTE_UNREACHABLE_S='60')
    argv = [sys.executable, str(RUN), '--host', 'm5', '--job', 'j1',
            '--log', str(tmp_path / 'j1.log'), '--prompt', str(tmp_path / 'prompt'),
            '--command', str(tmp_path / 'run.sh'), '--state', str(tmp_path / 'j1.remote.json')]
    return argv, env, down


def counting(tmp_path, body):
    """A program that records each start, so a second copy of the job is visible."""
    return ('echo started >> ' + str(tmp_path / 'starts') + '\n'
            'read line; echo "got: $line"\n' + body)


def starts(tmp_path):
    f = tmp_path / 'starts'
    return len(f.read_text().splitlines()) if f.exists() else 0


def running_on_host(tmp_path):
    """Wait until the executor has really started on the host; returns the watcher pid."""
    for _ in range(100):
        pids = list((tmp_path / 'host-attempts' / 'j1').glob('*/watcher.pid'))
        if pids and pids[0].read_text().strip() and starts(tmp_path):
            return int(pids[0].read_text())
        time.sleep(0.1)
    raise AssertionError('the executor never started on the host')


def test_output_and_exit_code_come_back(tmp_path):
    argv, env, _ = world(tmp_path, counting(tmp_path, 'echo working\nexit 7\n'))
    rc = subprocess.run(argv, env=env, timeout=60).returncode
    log = (tmp_path / 'j1.log').read_text()
    assert rc == 7
    assert 'got: the prompt' in log and 'working' in log, 'the prompt arrives on stdin, output returns'
    assert not (tmp_path / 'j1.remote.json').exists(), 'a finished attempt is not reattached to later'


def test_a_dropped_connection_does_not_end_the_job(tmp_path):
    """The 11-07 failure. The link goes down mid-run; the job must finish anyway."""
    argv, env, down = world(tmp_path, counting(tmp_path, 'sleep 2\necho finished\nexit 0\n'))
    proc = subprocess.Popen(argv, env=env)
    running_on_host(tmp_path)
    down.write_text('')            # the network blip
    time.sleep(2.5)                # the job finishes on the host while the link is down
    down.unlink()
    assert proc.wait(timeout=60) == 0
    log = (tmp_path / 'j1.log').read_text()
    assert 'finished' in log and 'reachable again' in log
    assert starts(tmp_path) == 1


def test_a_restarted_controller_reattaches_instead_of_starting_a_second_copy(tmp_path):
    """The 11-08 failure. The controller side dies (here: killed); the executor keeps running on
    the host, and the restarted launcher follows the same attempt to its real exit code."""
    argv, env, _ = world(tmp_path, counting(tmp_path, 'sleep 2\necho done-on-host\nexit 3\n'))
    first = subprocess.Popen(argv, env=env)
    running_on_host(tmp_path)
    first.send_signal(signal.SIGKILL)   # the controller reset
    first.wait(timeout=10)
    assert (tmp_path / 'j1.remote.json').exists()
    rc = subprocess.run(argv, env=env, timeout=60).returncode
    log = (tmp_path / 'j1.log').read_text()
    assert rc == 3, 'the exit code is the executor\'s, from the attempt that was already running'
    assert 'reattached to attempt' in log and 'done-on-host' in log
    assert starts(tmp_path) == 1, 'a second copy of the job was started beside the first'
    assert log.count('got: the prompt') == 1, 'output was streamed twice'


def test_an_attempt_that_finished_while_nobody_watched_is_collected_not_rerun(tmp_path):
    argv, env, _ = world(tmp_path, counting(tmp_path, 'echo quick\nexit 0\n'))
    first = subprocess.Popen(argv, env=env)
    running_on_host(tmp_path)
    first.send_signal(signal.SIGKILL)
    first.wait(timeout=10)
    time.sleep(1.0)                     # it finishes on the host with no one polling
    if not (tmp_path / 'j1.remote.json').exists():
        return                          # the first poll already collected it; nothing to test
    assert subprocess.run(argv, env=env, timeout=60).returncode == 0
    assert starts(tmp_path) == 1
    assert 'quick' in (tmp_path / 'j1.log').read_text()


def test_an_attempt_lost_on_the_host_is_reported_not_waited_on_forever(tmp_path):
    argv, env, _ = world(tmp_path, counting(tmp_path, 'sleep 30\n'))
    proc = subprocess.Popen(argv, env=env)
    watcher = running_on_host(tmp_path)
    # A host restart: the watcher and the executor are gone and no exit code was written.
    subprocess.run(['pkill', '-KILL', '-P', str(watcher)])
    os.kill(watcher, signal.SIGKILL)
    assert proc.wait(timeout=60) == 255
    assert 'is gone on m5 with no exit code' in (tmp_path / 'j1.log').read_text()


def test_the_host_paths_expand_on_the_host():
    """$HOME has bitten this launcher twice in two days by expanding, or not, on the wrong side."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import remote_run
    assert remote_run.root_expr('.local/state/x') == '"$HOME"/.local/state/x'
    assert remote_run.root_expr('/abs/path') == '/abs/path'
    assert remote_run.root_expr('my dir/x') == '"$HOME"/\'my dir/x\''
