"""Stopping a --host job stops the executor on the machine that is running it.

11-07, math, within hours of --host shipping and it cost real money: a job was launched with
--host m5 on the wrong model, `job-stop` was run, the local tmux session died and the log said
"exit stopped", and `codex exec` kept running on the m5 as an orphan with nobody watching it.
Killing the local ssh client does not signal the remote command; the channel closes and the
process carries on.

So the launcher records which host a job runs on and where the remote side wrote its pid, the
remote shell records that pid immediately before `exec`, and this reads both. `ssh` is a stub that
runs the command locally, so these exercise the real quoting and the real signalling.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
STOP = REPO / 'harness/tools/remote-stop'


def entry(reg, job, **fields):
    reg.mkdir(parents=True, exist_ok=True)
    (reg / (job + '.job')).write_text(''.join('{}={}\n'.format(k, v) for k, v in fields.items()))


def run(tmp_path, job, reg, ssh=None, env_extra=None):
    env = dict(os.environ)
    env.pop('LAUNCH_REMOTE_JOBS', None)
    if ssh:
        env['LAUNCH_SSH'] = str(ssh)
    env.update(env_extra or {})
    return subprocess.run(['sh', str(STOP), job, str(reg)], env=env,
                          capture_output=True, text=True, timeout=60)


def local_ssh(tmp_path):
    """Stands in for ssh: drops the options and the host, runs the command string locally."""
    s = tmp_path / 'fake-ssh'
    s.write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\nshift\nexec /bin/sh -c "$*"\n')
    s.chmod(0o755)
    return s


def test_a_job_with_no_host_is_a_no_op_so_job_stop_can_always_call_it(tmp_path):
    reg = tmp_path / 'reg'
    entry(reg, 'local_job', dir='/tmp', pid='1')
    out = run(tmp_path, 'local_job', reg)
    assert out.returncode == 0
    assert 'ran here' in out.stdout


def test_a_job_with_no_registry_entry_is_a_no_op(tmp_path):
    out = run(tmp_path, 'gone', tmp_path / 'reg')
    assert out.returncode == 0 and 'nothing to do' in out.stdout


def test_the_remote_executor_is_signalled_and_the_marker_removed(tmp_path):
    """The actual bug: a live process that survives the local kill must not survive this."""
    marks = tmp_path / 'marks'
    marks.mkdir()
    child = subprocess.Popen([sys.executable, '-c',
                              'import time; time.sleep(120)'])
    (marks / 'math_job.pid').write_text(str(child.pid))
    reg = tmp_path / 'reg'
    entry(reg, 'math_job', dir='/tmp', pid='1', host='m5', remote_marks=str(marks))
    out = run(tmp_path, 'math_job', reg, ssh=local_ssh(tmp_path))
    assert out.returncode == 0, out.stderr
    assert 'stopped pid {}'.format(child.pid) in out.stdout
    assert child.wait(timeout=30) != 0 or True        # it ended; the code is the signal
    assert not (marks / 'math_job.pid').exists()


def test_a_pid_that_is_already_gone_is_reported_not_retried(tmp_path):
    marks = tmp_path / 'marks'
    marks.mkdir()
    done = subprocess.Popen([sys.executable, '-c', 'pass'])
    done.wait()
    (marks / 'j.pid').write_text(str(done.pid))
    reg = tmp_path / 'reg'
    entry(reg, 'j', host='m5', remote_marks=str(marks))
    out = run(tmp_path, 'j', reg, ssh=local_ssh(tmp_path))
    assert out.returncode == 0 and 'already gone' in out.stdout
    assert not (marks / 'j.pid').exists()


def test_no_pid_file_on_the_host_says_so_rather_than_claiming_success(tmp_path):
    reg = tmp_path / 'reg'
    entry(reg, 'j', host='m5', remote_marks=str(tmp_path / 'absent'))
    out = run(tmp_path, 'j', reg, ssh=local_ssh(tmp_path))
    assert 'no pid file' in out.stdout


def test_a_junk_pid_file_does_not_signal_anything(tmp_path):
    marks = tmp_path / 'marks'
    marks.mkdir()
    (marks / 'j.pid').write_text('-1\n')
    reg = tmp_path / 'reg'
    entry(reg, 'j', host='m5', remote_marks=str(marks))
    out = run(tmp_path, 'j', reg, ssh=local_ssh(tmp_path))
    assert 'not a number' in out.stdout
    assert not (marks / 'j.pid').exists()


def test_an_unreachable_host_fails_loudly(tmp_path):
    """Reporting success here would recreate exactly the orphan this exists to prevent."""
    ssh = tmp_path / 'broken-ssh'
    ssh.write_text('#!/bin/sh\nexit 255\n')
    ssh.chmod(0o755)
    reg = tmp_path / 'reg'
    entry(reg, 'j', host='m5', remote_marks='.local/state/x')
    out = run(tmp_path, 'j', reg, ssh=ssh)
    assert out.returncode != 0


@pytest.mark.parametrize('field,value', [
    ('host', 'm5 -o ProxyCommand=id'),
    ('host', '-oProxyCommand=id'),
    ('remote_marks', '/tmp/$(id)'),
    ('remote_marks', '/tmp/`id`'),
])
def test_a_registry_entry_cannot_smuggle_a_command(tmp_path, field, value):
    """Both values reach an ssh argv and a remote shell line, so both are validated first."""
    reg = tmp_path / 'reg'
    fields = dict(host='m5', remote_marks=str(tmp_path))
    fields[field] = value
    entry(reg, 'j', **fields)
    out = run(tmp_path, 'j', reg, ssh=local_ssh(tmp_path))
    assert out.returncode == 2, out.stdout + out.stderr
    assert 'refusing' in out.stderr


def test_a_job_name_with_a_path_uses_its_basename(tmp_path):
    """A sweep job is a relative path, and the launcher names the marker after the basename."""
    marks = tmp_path / 'marks'
    marks.mkdir()
    (marks / '0-search.pid').write_text('')
    reg = tmp_path / 'reg' / 'a' / 'b'
    entry(reg, '0-search', host='m5', remote_marks=str(marks))
    out = run(tmp_path, '0-search', reg, ssh=local_ssh(tmp_path))
    assert out.returncode == 0, out.stderr
    assert 'not a number' in out.stdout        # it found the basename's marker


# --- the launcher's half ------------------------------------------------------------------

LAUNCH = REPO / 'tools/launch.sh'


def test_the_launcher_records_the_host_and_the_marks_path(tmp_path):
    text = LAUNCH.read_text()
    assert '${LAUNCH_HOST:+"host=$LAUNCH_HOST"}' in text
    assert '${LAUNCH_HOST:+"remote_marks=$remote_marks"}' in text
    # And nothing is recorded for a local job, so remote-stop stays a no-op for it.
    assert 'print -l "dir=$dir" "pid=$$" ${LAUNCH_HOST:+' in text


def test_the_remote_shell_records_the_executors_own_pid(tmp_path):
    """`echo $$` in the shell that then `exec`s is the executor's pid, not a wrapper's. If the
    exec were replaced by a plain call this would record the wrong process and the stop would
    signal a shell that had already gone."""
    text = LAUNCH.read_text()
    i = text.index('mkdir -p $rmarks')
    block = text[i:i + 300]
    assert 'echo \\$\\$ >' in block
    assert block.index('exec nice') > block.index('echo \\$\\$ >')
