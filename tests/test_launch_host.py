"""`launch.sh --host` runs the executor on another machine and leaves status readable here.

Ricardo, 11-07: "move the science runs to the m5". The controller is a 16 GB Mac mini that ran
out of memory under local rounds on 11-01; the second mini has 48 GB and 846 GiB free. Only the
executor step crosses the network, so admission, the spec word cap, the job registry, model
selection, the prompt and the log keep one source on the controller.

`ssh` is replaced by a stub that runs the command string through a local shell, so these tests
exercise the real quoting and the real missing-work-dir guard rather than a mock of them.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / 'tools/launch.sh'
ASK = 'Find a better bound for C44 than the printed one, or say plainly that you did not.'


def harness(tmp_path, lane='fixture'):
    """A launcher environment whose agent CLI and ssh are stubs: no model, no network, no spend."""
    jobs = tmp_path / 'jobs'
    jobs.mkdir(exist_ok=True)
    (jobs / (lane + '-job.md')).write_text(ASK)
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    fake = tmp_path / 'fake-cli'
    fake.write_text('#!' + sys.executable + '\nimport sys\n'
                    'print(\'{"is_error":false,"subtype":"success","result":"fixture"}\')\n'
                    'sys.exit(0)\n')
    fake.chmod(0o755)
    # Stands in for ssh: records the host and the command, then runs the command locally.
    ssh = tmp_path / 'fake-ssh'
    ssh.write_text('#!/bin/sh\nprintf "host=%s\\n" "$1" >> "$SSH_LOG"\n'
                   'host=$1; shift\nprintf "cmd=%s\\n" "$*" >> "$SSH_LOG"\nexec sh -c "$*"\n')
    ssh.chmod(0o755)
    root = tmp_path / 'runtime'
    (root / 'lanes' / lane).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(root),
               LAUNCH_SSH=str(ssh), SSH_LOG=str(tmp_path / 'ssh.log'),
               LAUNCH_REMOTE_EXECUTOR=str(REPO / 'harness/agent_executor.py'))
    env.pop('LAUNCH_RESUME', None)
    env.pop('SPEC_OVER_CAP', None)
    env.pop('LAUNCH_HOST', None)
    return jobs, env


def run(tmp_path, *args, lane='fixture', workdir=None, env_extra=None):
    jobs, env = harness(tmp_path, lane=lane)
    env.update(env_extra or {})
    proc = subprocess.run(['zsh', str(LAUNCH), lane + '-job', str(workdir or tmp_path), *args],
                          env=env, capture_output=True, text=True, timeout=120)
    log = jobs / (lane + '-job.log')
    return proc, (log.read_text() if log.exists() else ''), Path(env['SSH_LOG'])


def test_without_a_host_nothing_is_sent_anywhere(tmp_path):
    """The default stays local. A host option that quietly became the default would move every
    lane's work off this machine at once."""
    proc, log, ssh_log = run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert not ssh_log.exists()
    assert 'host' not in log.splitlines()[0]


def test_the_executor_runs_on_the_host_and_the_prompt_arrives_over_stdin(tmp_path):
    proc, log, ssh_log = run(tmp_path, '--host', 'm5')
    assert proc.returncode == 0, proc.stderr + log
    sent = ssh_log.read_text()
    assert 'host=m5' in sent
    assert '--backend claude' in sent and '--directory ' + str(tmp_path) in sent
    # The agent only ever sees the prompt the controller built, and it built it from the spec.
    assert ASK in (tmp_path / 'jobs/fixture-job.log.prompt').read_text()
    assert (tmp_path / 'jobs/fixture-job.last.md').exists()


def test_the_log_records_which_machine_ran_the_attempt(tmp_path):
    """A receipt that does not say where the work ran cannot be checked later. lane-yield's
    stamp grammar has to keep parsing the line, which is why the date stays last."""
    proc, log, _ = run(tmp_path, '--host', 'm5')
    assert proc.returncode == 0, proc.stderr
    assert '=== attempt 1 model fixture-claude host m5 ' in log
    sys.path.insert(0, str(REPO / 'harness/tools/lane-yield'))
    import lane_yield
    opened = [line for line in log.splitlines() if line.startswith('=== attempt')]
    assert lane_yield.parse_stamp(opened[0]) is not None, opened[0]


def test_a_missing_work_dir_on_the_host_refuses_instead_of_running_in_its_home(tmp_path):
    """The failure this guard exists for: ssh would otherwise land in the remote $HOME and the
    job would write its results somewhere nobody looks.

    The stub runs the command locally, where the work dir does exist, so the guard is checked
    against the real command line the launcher sent, with the work dir pointed somewhere absent.
    """
    proc, _, ssh_log = run(tmp_path, '--host', 'm5')
    assert proc.returncode == 0, proc.stderr
    sent = [line[len('cmd='):] for line in ssh_log.read_text().splitlines()
            if line.startswith('cmd=')][0]
    absent = str(tmp_path / 'not-there')
    assert str(tmp_path) in sent
    remote = subprocess.run(['sh', '-c', sent.replace(str(tmp_path), absent)],
                            capture_output=True, text=True, timeout=60)
    assert remote.returncode == 2, remote.stdout + remote.stderr
    assert 'no work dir' in remote.stderr and absent in remote.stderr


def test_a_host_that_is_not_an_ssh_alias_is_refused(tmp_path):
    """The host reaches an ssh argv and a remote shell line, so it is validated before either."""
    for bad in ('m5 -o ProxyCommand=sh', 'm5;id', '-oProxyCommand=id', 'm5$(id)', 'm5`id`'):
        proc, _, ssh_log = run(tmp_path, '--host', bad)
        assert proc.returncode == 2, (bad, proc.stdout, proc.stderr)
        assert 'must be an ssh alias' in proc.stderr, bad
        assert not ssh_log.exists(), bad


def test_a_failed_pull_does_not_fail_the_job(tmp_path):
    """The outputs are on the host either way. Losing the small bookkeeping copy is worth a line
    in the log, not throwing away a finished run."""
    proc, log, _ = run(tmp_path, '--host', 'm5',
                       env_extra={'LAUNCH_PULL_MAX_SIZE': 'not-a-size'})
    assert proc.returncode == 0, proc.stderr
    assert 'pull from m5 failed' in log
