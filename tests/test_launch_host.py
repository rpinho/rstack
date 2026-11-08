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
    # The launcher passes -o options on some calls and not others, so the stub skips them the way
    # ssh does. Before 11-08 it took $1 as the host unconditionally, which made a call with options
    # run "BatchMode=yes -o ... host cmd" through sh and look like a command that simply failed.
    ssh.write_text('#!/bin/sh\n'
                   'while [ "$1" = "-o" ]; do shift 2; done\n'
                   'printf "host=%s\\n" "$1" >> "$SSH_LOG"\n'
                   'host=$1; shift\nprintf "cmd=%s\\n" "$*" >> "$SSH_LOG"\n'
                   'if [ -n "$FAKE_SSH_LOAD" ] && [ "${1#*vm.loadavg}" != "$1" ]; then\n'
                   '  echo "$FAKE_SSH_LOAD"; exit 0\n'
                   'fi\n'
                   'if [ "$FAKE_SSH_DOWN" = 1 ]; then exit 255; fi\n'
                   'exec sh -c "$*"\n')
    ssh.chmod(0o755)
    root = tmp_path / 'runtime'
    (root / 'lanes' / lane).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(root),
               LAUNCH_SSH=str(ssh), SSH_LOG=str(tmp_path / 'ssh.log'),
               LAUNCH_REMOTE_EXECUTOR=str(REPO / 'harness/agent_executor.py'),
               LAUNCH_REMOTE_ATTEMPTS=str(tmp_path / 'remote-attempts'), LAUNCH_REMOTE_POLL_S='0.2')
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


def staged(tmp_path, job='fixture-job'):
    """The executor program as it landed on the host, and the prompt staged beside it.

    Since 11-08 the program reaches the host over stdin as run.sh in the attempt directory (it is
    started detached there, so it outlives the ssh session), not as an ssh argument. So tests read
    it where it lands, which is also the thing that runs.
    """
    runs = sorted((tmp_path / 'remote-attempts' / job).glob('*/run.sh'))
    assert runs, 'nothing was staged on the host'
    return runs[-1].read_text(), (runs[-1].parent / 'prompt').read_text()


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
    program, prompt = staged(tmp_path)
    assert '--backend claude' in program and '--directory ' + str(tmp_path) in program
    assert prompt == (tmp_path / 'jobs/fixture-job.log.prompt').read_text()
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
    sent = staged(tmp_path)[0].splitlines()[0]
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


# --- the hard-rule lint AGENTS.md has claimed since 11-04 --------------------------------------

def test_the_job_yield_ledger_records_both_hard_rule_lines(tmp_path):
    """AGENTS.md says the launcher lints every job for the restate-ask and shipped lines into a
    job-yield ledger. That was true of the host's own copy of launch.sh and not of this one, so
    the repository documented an enforcement it did not run."""
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'STATUS.md').write_text('# a comment first\n\nYou asked: for a better bound. I will: try.\n')
    (work / 'REPORT.md').write_text('Shipped: a bound of 0.2524 with a certificate.\n')
    ledger = tmp_path / 'yield.jsonl'
    proc, log, _ = run(tmp_path, workdir=work, env_extra={'LAUNCH_YIELD_LEDGER': str(ledger)})
    assert proc.returncode == 0, proc.stderr
    assert 'lint restate-ask=1 shipped-line=1' in log
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row['restated'] is True
    assert row['shipped'].startswith('Shipped: a bound of 0.2524')


def test_a_job_missing_the_lines_is_recorded_and_notified_without_failing(tmp_path):
    """A job that skips the lines still exits on its own result: the lint reports, it does not
    punish, and a missing notifier must not turn a finished job into a failed one."""
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'STATUS.md').write_text('Did some things.\n')
    told = tmp_path / 'told.txt'
    notifier = tmp_path / 'notify'
    notifier.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$TOLD"\n')
    notifier.chmod(0o755)
    ledger = tmp_path / 'yield.jsonl'
    proc, log, _ = run(tmp_path, workdir=work, env_extra={
        'LAUNCH_YIELD_LEDGER': str(ledger), 'LAUNCH_NOTIFY_COMMAND': str(notifier),
        'TOLD': str(told)})
    assert proc.returncode == 0, proc.stderr
    assert 'lint restate-ask=0 shipped-line=0' in log
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row['restated'] is False and row['shipped'] == ''
    assert 'without the hard-rule lines' in told.read_text()


def test_a_broken_notifier_does_not_fail_the_job(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    proc, log, _ = run(tmp_path, workdir=work, env_extra={
        'LAUNCH_YIELD_LEDGER': str(tmp_path / 'y.jsonl'),
        'LAUNCH_NOTIFY_COMMAND': str(tmp_path / 'does-not-exist')})
    assert proc.returncode == 0, proc.stderr
    assert 'lint restate-ask=0' in log


def test_the_pull_brings_back_a_sweep_workers_report(tmp_path):
    """A sweep worker's deliverable is <stage>.report.md: the controller reads it to admit ideas
    and to record reads and kills. The first pull list did not include it, so a lane moved to a
    host would have run all three stages and failed every one for a missing report.

    The include list is read out of launch.sh and handed to a real rsync between two directories,
    so this checks the patterns the launcher actually sends, not a copy of them.
    """
    import shlex
    text = LAUNCH.read_text()
    start = text.index('rsync -a --timeout')
    command = text[start:text.index('\n', text.index('--exclude=', start))].replace('\\\n', ' ')
    # Order matters to rsync, so the tokens are kept exactly as the launcher writes them. The one
    # token this cannot pass on is the zsh expansion of the job's own output file.
    includes = [token for token in shlex.split(command)
                if (token.startswith('--include=') or token.startswith('--exclude='))
                and '${out:t}' not in token]
    assert '--include=*.report.md' in includes, includes
    assert includes[-1] == '--exclude=*', includes
    src, dst = tmp_path / 'host', tmp_path / 'here'
    (src / 'work/runs/attempt').mkdir(parents=True)
    (src / 'work/runs/attempt/search.report.md').write_text('IDEA X-1: ...\nDONE\n')
    (src / 'work/runs/attempt/prior-art-X-1.json').write_text('{"schema": 1}')
    (src / 'work/runs/attempt/0-search.md').write_text('the spec')
    (src / 'STATUS.md').write_text('You asked: ... I will: ...\n')
    (src / 'huge.bin').write_bytes(b'0' * 1024)
    dst.mkdir()
    subprocess.run(['rsync', '-a', *includes, str(src) + '/', str(dst) + '/'],
                   check=True, timeout=60)
    assert (dst / 'work/runs/attempt/search.report.md').read_text().startswith('IDEA X-1')
    # The receipt admits the idea and its path goes in the ledger, so it has to be here too.
    assert (dst / 'work/runs/attempt/prior-art-X-1.json').exists()
    assert (dst / 'STATUS.md').exists()
    # The heavy outputs stay on the host: that is the point of the list.
    assert not (dst / 'huge.bin').exists()
    assert not (dst / 'work/runs/attempt/0-search.md').exists()


def test_the_output_directory_is_created_on_the_host(tmp_path):
    """A sweep worker's --output is inside the attempt directory the controller just made here,
    which does not exist on the host. Without this the executor's first write fails and nothing
    runs. The work dir itself is still never created: that refusal is a different rule."""
    nested = tmp_path / 'jobs/runs/20261107T000000-abc'
    nested.mkdir(parents=True)
    (nested / 'stage-job.md').write_text(ASK)
    jobs, env = harness(tmp_path)
    env['LAUNCH_ARTIFACT_DIR'] = str(nested)
    proc = subprocess.run(['zsh', str(LAUNCH), 'stage-job', str(tmp_path)],
                          env=dict(env, LAUNCH_HOST='m5'), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    # The command spans several lines, so the whole log is read: a per-line filter would see only
    # the `cd` and miss everything after it.
    sent = staged(tmp_path, 'stage-job')[0]
    assert 'mkdir -p ' + str(nested) in sent
    # Run the command block with the output directory removed: it must recreate it, not refuse.
    block = sent
    import shutil as sh
    sh.rmtree(nested)
    remote = subprocess.run(['sh', '-c', block], capture_output=True, text=True, timeout=60)
    assert nested.is_dir(), remote.stderr
    # And the work dir is never created for you: a missing lane on the host stays a refusal.
    gone = str(tmp_path / 'not-there')
    refused = subprocess.run(['sh', '-c', block.replace(str(tmp_path) + ' ', gone + ' ', 1)],
                             capture_output=True, text=True, timeout=60)
    assert refused.returncode == 2 and 'no work dir' in refused.stderr


def test_a_lanes_ledger_is_never_overwritten_by_the_hosts_copy(tmp_path):
    """math, 11-07, on moving its sweeps to the second machine: "never two live ledgers. This Mac
    stays the single authority for IDEAS.jsonl, RESULTS.jsonl ... If anything ever writes a ledger
    on the m5 side, the pull-back should refuse or flag it, not merge it."

    When the work dir IS a lane, RESULTS.jsonl there is that append-only ledger, and rsync would
    have replaced rows written here with the host's copy. The exclusion is keyed on the path, so
    a job with its own work dir still gets its own RESULTS.jsonl back.
    """
    import shlex
    text = LAUNCH.read_text()
    assert "[[ ${dir:A:h:t} != lanes ]] || ledger=(--exclude='/RESULTS.jsonl')" in text
    start = text.index('rsync -a --timeout')
    command = text[start:text.index('\n', text.index('--exclude=', start))].replace('\\\n', ' ')
    includes = [t for t in shlex.split(command)
                if (t.startswith('--include=') or t.startswith('--exclude='))
                and '${out:t}' not in t]
    src, dst = tmp_path / 'host', tmp_path / 'here'
    for d in (src, dst):
        d.mkdir()
    (src / 'RESULTS.jsonl').write_text('{"from": "the host"}\n')
    (dst / 'RESULTS.jsonl').write_text('{"from": "this machine, authoritative"}\n')
    (src / 'STATUS.md').write_text('You asked: ... I will: ...\n')
    # A lane work dir: the ledger exclusion is in front of the include list.
    subprocess.run(['rsync', '-a', "--exclude=/RESULTS.jsonl", *includes,
                    str(src) + '/', str(dst) + '/'], check=True, timeout=60)
    assert (dst / 'RESULTS.jsonl').read_text() == '{"from": "this machine, authoritative"}\n'
    assert (dst / 'STATUS.md').exists()
    # A job work dir: no exclusion, and the job's own results come home.
    other = tmp_path / 'job'
    other.mkdir()
    subprocess.run(['rsync', '-a', *includes, str(src) + '/', str(other) + '/'],
                   check=True, timeout=60)
    assert (other / 'RESULTS.jsonl').read_text() == '{"from": "the host"}\n'


def test_a_diverged_ledger_is_reported_rather_than_merged(tmp_path):
    """Silence would mean rows sitting on a machine nobody reads, which is how a result is lost."""
    text = LAUNCH.read_text()
    assert 'LEDGER DIVERGED' in text
    assert 'was NOT merged' in text
    # The report goes through the same notifier the hard-rule lint uses, and a missing notifier
    # must not fail a finished job.
    assert 'LAUNCH_NOTIFY_COMMAND' in text.split('LEDGER DIVERGED')[1][:400]


def test_the_marker_lands_under_the_remote_home_and_not_in_a_directory_called_HOME(tmp_path):
    """The bug this file shipped with on 11-07, found by friends within the hour.

    $HOME has to reach the REMOTE shell unquoted so it expands there. The first version quoted the
    whole path with ${(q)}, which escapes the dollar, so the remote shell created a directory
    literally named '$HOME' under the work dir and wrote the marker inside it. remote-stop then
    found no pid file and a job-stop left the executor running on the host.

    The test that let it through only checked that `echo $$` came before `exec`. Ordering was
    never the risk. This runs the command the launcher actually builds, with a stand-in HOME, and
    looks at where the file ends up: the one thing the old test did not do.
    """
    home = tmp_path / 'remote-home'
    home.mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'jobs').mkdir()
    (tmp_path / 'jobs').mkdir(exist_ok=True)
    jobs, env = harness(tmp_path)
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(work)],
                          env=dict(env, LAUNCH_HOST='m5'), capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    block = staged(tmp_path)[0]
    # Run it the way the host would, with HOME pointing somewhere this test can inspect.
    run = subprocess.run(['sh', '-c', block],
                         env=dict(os.environ, HOME=str(home), EXECUTOR_RAN=str(tmp_path / 'ran')),
                         capture_output=True, text=True, timeout=60, cwd=str(work))
    marker = home / '.local/state/research-harness/remote-jobs/fixture-job.pid'
    assert marker.is_file(), (
        'the marker did not land under the remote HOME; stray paths: '
        + repr(sorted(str(p.relative_to(work)) for p in work.rglob('*') if p.is_file()))
        + ' / ' + run.stderr[-200:])
    assert marker.read_text().strip().isdigit()
    # And nothing named like a literal variable was created anywhere.
    assert not (work / '$HOME').exists()
    assert not list(work.glob('**/$HOME'))


# The load guard, which until 11-08 measured the wrong machine. math: "c47r5 and c22br4 were
# refused at load 77 (M4 at 89) while the m5 sat at 1.5. I relaunched with FORCE_LAUNCH=1."
# planets hit the same thing in the same hour. FORCE_LAUNCH also turns off the disk and memory
# floors, so a guard that measures the wrong machine does not just annoy: it talks lanes into
# disabling the guards that were right.


def test_a_host_job_is_gated_by_the_hosts_load_not_this_machines(tmp_path):
    jobs, env = harness(tmp_path)
    env.pop('FORCE_LAUNCH')
    # A cap of 0 refuses any machine with load above 0, and this one always has some. The host
    # reports 0.00, so only a launcher that reads the HOST lets this job through.
    env['LAUNCH_MAX_LOAD'] = '0'
    env['FAKE_SSH_LOAD'] = '0.00'
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path), '--host', 'm5'],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert 'refused' not in proc.stderr


def test_a_host_job_is_refused_when_the_host_is_the_busy_one(tmp_path):
    jobs, env = harness(tmp_path)
    env.pop('FORCE_LAUNCH')
    env['LAUNCH_MAX_LOAD'] = '30'
    env['FAKE_SSH_LOAD'] = '94.20'
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path), '--host', 'm5'],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 75
    assert 'load 94 on m5' in proc.stderr


def test_a_host_whose_load_cannot_be_read_is_refused_not_measured_here(tmp_path):
    """The whole class of bug: a precondition that cannot be evaluated on the execution host must
    refuse. Falling back to the controller's number is what sent two lanes to FORCE_LAUNCH."""
    jobs, env = harness(tmp_path)
    env.pop('FORCE_LAUNCH')
    env['FAKE_SSH_DOWN'] = '1'
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path), '--host', 'm5'],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 75
    assert 'cannot read the load on m5' in proc.stderr


def test_a_local_job_still_reads_this_machine(tmp_path):
    """No host, no ssh: the 10-30 failure that put the guard there was eight local jobs."""
    jobs, env = harness(tmp_path)
    env.pop('FORCE_LAUNCH')
    env['LAUNCH_MAX_LOAD'] = '0'           # this machine's load is above 0 by definition
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 75
    assert 'on this machine' in proc.stderr
    assert not Path(env['SSH_LOG']).exists(), 'a local job asked a host about its load'
