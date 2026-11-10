"""The memory guard, tested on a real throwaway allocator rather than on a mock of one.

11-08: two local processes grew to about 47 GB and 35 GB on a 16 GB controller, the kernel killed
system daemons instead of them, and the machine reset. These tests start a process that really
allocates and touches memory, then run a real pass with a limit below it. The only seam is the
candidate list, which is cut down to the allocator so a test can never kill anything else of the
user's: footprint, signals, log and push are the production code.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='footprint comes from libproc')

import mem_guard  # noqa: E402

MIB = 1024 ** 2

ALLOCATE = '''
import signal, sys, time
if sys.argv[2] == "ignore-term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
block = bytearray({size})
for i in range(0, len(block), 4096):
    block[i] = 1                     # touch every page, so it is footprint and not a promise
print("ready", flush=True)
time.sleep(120)
'''


def allocator(tmp_path, mib, mode='plain'):
    script = tmp_path / 'allocate.py'
    script.write_text(ALLOCATE.format(size=mib * MIB))
    proc = subprocess.Popen([sys.executable, str(script), 'x', mode], stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == 'ready'
    return proc


def only(monkeypatch, *procs):
    """Restrict the pass to these pids. Everything else about it is real."""
    real = mem_guard.processes
    pids = {p.pid for p in procs}
    monkeypatch.setattr(mem_guard, 'processes',
                        lambda uid: [r for r in real(uid) if r[0] in pids])


def config(tmp_path, monkeypatch, limit_mib, **env):
    monkeypatch.setenv('MEM_GUARD_LIMIT_GB', str(limit_mib / 1024))
    monkeypatch.setenv('MEM_GUARD_LOG', str(tmp_path / 'kills.jsonl'))
    monkeypatch.setenv('MEM_GUARD_GRACE_S', '1')
    pushed = tmp_path / 'pushed.txt'
    push = tmp_path / 'push'
    push.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> ' + str(pushed) + '\n')
    push.chmod(0o755)
    monkeypatch.setenv('MEM_GUARD_NOTIFY', str(push))
    monkeypatch.delenv('MEM_GUARD_SPARE', raising=False)
    monkeypatch.delenv('MEM_GUARD_TOTAL_GB', raising=False)
    monkeypatch.delenv('MEM_GUARD_JOB_GB', raising=False)
    monkeypatch.setenv('MEM_GUARD_JOBS_DIR', str(tmp_path / 'remote-jobs'))
    for k in ('MEM_GUARD_MIN_FREE_PCT', 'MEM_GUARD_TELL', 'MEM_GUARD_TELL_HOST'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('MEM_GUARD_HEARTBEAT', str(tmp_path / 'heartbeat'))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return mem_guard.settings(), pushed


def wait_gone(proc):
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail('the allocator is still alive')


def test_footprint_sees_what_was_allocated(tmp_path):
    proc = allocator(tmp_path, 300)
    try:
        size = mem_guard.footprint(proc.pid)
        assert size is not None and size > 250 * MIB, size
    finally:
        proc.kill()


def test_a_process_over_the_limit_is_killed_logged_and_pushed(tmp_path, monkeypatch):
    proc = allocator(tmp_path, 300)
    only(monkeypatch, proc)
    cfg, pushed = config(tmp_path, monkeypatch, limit_mib=150)
    killed = mem_guard.run_once(cfg)
    wait_gone(proc)
    assert [k['pid'] for k in killed] == [proc.pid]
    row = json.loads((tmp_path / 'kills.jsonl').read_text().splitlines()[-1])
    assert row['pid'] == proc.pid and row['signal'] == 'TERM'
    assert row['ppid'] == os.getpid(), 'the parent is what tells you who started it'
    assert row['name'].lower().startswith('python') and row['footprint_gib'] > 0.2
    assert row['parent_command'], 'the parent command is the lead to the owner'
    message = pushed.read_text()
    assert 'killed' in message and str(proc.pid) in message and 'Parent:' in message


def test_a_process_under_the_limit_is_left_alone(tmp_path, monkeypatch):
    proc = allocator(tmp_path, 100)
    try:
        only(monkeypatch, proc)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=400)
        assert mem_guard.run_once(cfg) == []
        assert proc.poll() is None
        assert not pushed.exists()
    finally:
        proc.kill()


def test_a_process_that_ignores_term_gets_kill(tmp_path, monkeypatch):
    proc = allocator(tmp_path, 300, mode='ignore-term')
    only(monkeypatch, proc)
    cfg, _ = config(tmp_path, monkeypatch, limit_mib=150)
    killed = mem_guard.run_once(cfg)
    wait_gone(proc)
    assert killed[0]['signal'] == 'KILL'


def test_a_spared_process_is_never_killed_whatever_its_size(tmp_path, monkeypatch):
    proc = allocator(tmp_path, 300)
    try:
        only(monkeypatch, proc)
        exe = mem_guard.exe_path(proc.pid)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=150,
                             MEM_GUARD_SPARE='^' + exe.replace('.', r'\.') + '$')
        assert mem_guard.run_once(cfg) == []
        assert proc.poll() is None and not pushed.exists()
    finally:
        proc.kill()


def test_jobs_over_the_total_lose_their_largest_process_only(tmp_path, monkeypatch):
    """11-10: no process passed the per-process limit, but eight workers together exhausted swap."""
    big, small = allocator(tmp_path, 300), allocator(tmp_path, 120)
    try:
        only(monkeypatch, big, small)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=1024, MEM_GUARD_TOTAL_GB=str(380 / 1024))
        killed = mem_guard.run_once(cfg)
        wait_gone(big)
        assert [k['pid'] for k in killed] == [big.pid]
        assert small.poll() is None, 'one kill brought the total under; the rest keep running'
        row = json.loads((tmp_path / 'kills.jsonl').read_text().splitlines()[-1])
        assert row['rule'] == 'total' and row['total_gib'] > row['footprint_gib']
        assert row['cwd'] == os.getcwd(), 'the working directory names the job'
        message = pushed.read_text()
        assert 'GB total' in message and 'Dir: ' + os.getcwd() in message
    finally:
        big.kill(); small.kill()


def test_the_total_never_counts_or_kills_an_app(tmp_path, monkeypatch):
    """The kernel already suspends apps under swap exhaustion; the total is about jobs."""
    big, small = allocator(tmp_path, 300), allocator(tmp_path, 120)
    try:
        only(monkeypatch, big, small)
        real = mem_guard.exe_path
        monkeypatch.setattr(mem_guard, 'exe_path', lambda pid: (
            '/Applications/Some App.app/Contents/MacOS/Some App' if pid == big.pid else real(pid)))
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=1024, MEM_GUARD_TOTAL_GB=str(380 / 1024))
        assert mem_guard.run_once(cfg) == []
        assert big.poll() is None and small.poll() is None and not pushed.exists()
    finally:
        big.kill(); small.kill()


JOB = '''
import subprocess, sys, time
kids = [subprocess.Popen([sys.executable, sys.argv[1], "x", "plain"], stdout=subprocess.PIPE, text=True)
        for _ in range(2)]
for k in kids:
    k.stdout.readline()
print("ready", flush=True)
time.sleep(120)
'''


def job(tmp_path, mib_each, name='math_c47r14_1110', stale=False):
    """A launcher job as launch.sh leaves it: a root process in its work dir, two workers under
    it, and its pid in remote-jobs/<job>.pid, written as it starts."""
    (tmp_path / 'allocate.py').write_text(ALLOCATE.format(size=mib_each * MIB))
    (tmp_path / 'job.py').write_text(JOB)
    work = tmp_path / 'work'
    work.mkdir()
    root = subprocess.Popen([sys.executable, str(tmp_path / 'job.py'), str(tmp_path / 'allocate.py')],
                            cwd=work, stdout=subprocess.PIPE, text=True)
    marks = tmp_path / 'remote-jobs'
    marks.mkdir(exist_ok=True)
    pidfile = marks / (name + '.pid')
    pidfile.write_text(str(root.pid) + '\n')
    if stale:
        old = time.time() - 3600
        os.utime(pidfile, (old, old))
    assert root.stdout.readline().strip() == 'ready'
    kids = [int(x) for x in subprocess.run(['pgrep', '-P', str(root.pid)], capture_output=True,
                                           text=True).stdout.split()]
    assert len(kids) == 2
    return root, kids, work


def only_pids(monkeypatch, pids):
    real = mem_guard.processes
    monkeypatch.setattr(mem_guard, 'processes', lambda uid: [r for r in real(uid) if r[0] in pids])


def running(pid):
    return mem_guard.alive(pid)


def test_a_job_over_its_cap_is_stopped_whole_and_says_so_in_status(tmp_path, monkeypatch):
    """11-10: the C47 producer reached 18 GB in 15 s inside a job; the job is the unit to stop."""
    root, kids, work = job(tmp_path, 200)
    try:
        only_pids(monkeypatch, {root.pid, *kids})
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_JOB_GB=str(300 / 1024))
        killed = mem_guard.run_once(cfg)
        wait_gone(root)
        assert not any(running(k) for k in kids), 'the workers go with the job'
        assert len(killed) == 1 and killed[0]['rule'] == 'job'
        assert killed[0]['job'] == 'math_c47r14_1110' and killed[0]['processes'] == 3
        assert killed[0]['total_gib'] > 0.35 and killed[0]['cwd'] == str(work)
        status = (work / 'STATUS.md').read_text()
        assert status.lstrip().startswith('MEMKILL ') and 'per-job cap' in status
        assert 'peak' in status and '/usr/bin/time -l' in status
        assert 'whole job math_c47r14_1110 stopped' in pushed.read_text()
    finally:
        for p in [root.pid, *kids]:
            try:
                os.kill(p, 9)
            except ProcessLookupError:
                pass


def test_a_job_under_its_cap_runs_on(tmp_path, monkeypatch):
    root, kids, work = job(tmp_path, 50)
    try:
        only_pids(monkeypatch, {root.pid, *kids})
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_JOB_GB='1')
        assert mem_guard.run_once(cfg) == []
        assert running(root.pid) and all(running(k) for k in kids)
        assert not (work / 'STATUS.md').exists() and not pushed.exists()
    finally:
        root.kill()
        for k in kids:
            os.kill(k, 9)


def test_a_stale_pid_file_never_names_a_job(tmp_path, monkeypatch):
    """remote-jobs keeps files from jobs long gone; their pids get reused by other processes."""
    root, kids, work = job(tmp_path, 200, stale=True)
    try:
        only_pids(monkeypatch, {root.pid, *kids})
        cfg, _ = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_JOB_GB=str(300 / 1024))
        assert mem_guard.pid_jobs(cfg) == {}
        assert mem_guard.run_once(cfg) == [] and running(root.pid)
    finally:
        root.kill()
        for k in kids:
            os.kill(k, 9)


def marked(tmp_path, mib, job, cwd=None):
    """A worker carrying the launcher's RH_JOB mark, with no pid file and no parent in any job:
    what a detached worker looks like once launchd has adopted it."""
    script = tmp_path / ('allocate-%d.py' % mib)
    script.write_text(ALLOCATE.format(size=mib * MIB))
    proc = subprocess.Popen([sys.executable, str(script), 'x', 'plain'], stdout=subprocess.PIPE,
                            text=True, env=dict(os.environ, RH_JOB=job), cwd=cwd or tmp_path)
    assert proc.stdout.readline().strip() == 'ready'
    return proc


def test_a_detached_worker_is_found_by_its_job_mark(tmp_path, monkeypatch):
    worker = marked(tmp_path, 250, 'math_c47r15_1110')
    try:
        only(monkeypatch, worker)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_JOB_GB=str(150 / 1024))
        found = mem_guard.jobs(cfg, mem_guard.survey(cfg))
        assert [r['pid'] for r in found['math_c47r15_1110']] == [worker.pid]
        killed = mem_guard.run_once(cfg)
        wait_gone(worker)
        assert killed[0]['job'] == 'math_c47r15_1110' and killed[0]['why'].startswith('over the')
    finally:
        worker.kill()


def test_low_free_memory_stops_the_largest_job_only_and_waits(tmp_path, monkeypatch):
    """Under the free-memory floor the largest JOB goes, not the largest process: a bigger
    process that belongs to no job, and an app inside a job, are left alone."""
    big = marked(tmp_path, 200, 'big_job')
    small = marked(tmp_path, 60, 'small_job')
    app = marked(tmp_path, 120, 'small_job')
    loner = allocator(tmp_path, 300)
    try:
        only(monkeypatch, big, small, app, loner)
        real = mem_guard.exe_path
        monkeypatch.setattr(mem_guard, 'exe_path', lambda pid: (
            '/Applications/Some App.app/Contents/MacOS/Some App' if pid == app.pid else real(pid)))
        monkeypatch.setattr(mem_guard, 'free_pct', lambda: 6)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_MIN_FREE_PCT='15',
                             MEM_GUARD_COOLDOWN_S='60')
        state = {}
        killed = mem_guard.run_once(cfg, state=state)
        wait_gone(big)
        assert [k['job'] for k in killed] == ['big_job'] and 'free memory 6%' in killed[0]['why']
        assert small.poll() is None and app.poll() is None and loner.poll() is None
        assert mem_guard.run_once(cfg, state=state) == [], 'one stop per cooldown'
        assert small.poll() is None
    finally:
        for p in (big, small, app, loner):
            p.kill()


def test_the_conductor_is_told(tmp_path, monkeypatch):
    worker = marked(tmp_path, 250, 'tell_job')
    told = tmp_path / 'told.txt'
    teller = tmp_path / 'tell'
    teller.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$1" "$2" >> ' + str(told) + '\n')
    teller.chmod(0o755)
    try:
        only(monkeypatch, worker)
        cfg, _ = config(tmp_path, monkeypatch, limit_mib=4096, MEM_GUARD_JOB_GB=str(150 / 1024),
                        MEM_GUARD_TELL=str(teller) + ' --from')
        mem_guard.run_once(cfg)
        wait_gone(worker)
        line = told.read_text()
        assert line.startswith('--from|mem-guard: MEMKILL') and 'job tell_job' in line
    finally:
        worker.kill()


def test_the_loop_writes_a_heartbeat_every_pass(tmp_path):
    """launch.sh refuses a job on a host whose heartbeat is stale, so the loop must beat."""
    beat = tmp_path / 'heartbeat'
    env = dict(os.environ, MEM_GUARD_LIMIT_GB='100000', MEM_GUARD_HEARTBEAT=str(beat),
               MEM_GUARD_LOG=str(tmp_path / 'kills.jsonl'), HOST_WATCH_STATE=str(tmp_path / 'hw.json'),
               HOST_WATCH_LOG=str(tmp_path / 'hw.jsonl'))
    for k in ('MEM_GUARD_JOB_GB', 'MEM_GUARD_TOTAL_GB', 'MEM_GUARD_MIN_FREE_PCT', 'MEM_GUARD_NOTIFY',
              'MEM_GUARD_TELL', 'HOST_WATCH_NOTIFY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(ROOT / 'tools/mem_guard.py'), '--every', '0.5'], env=env)
    try:
        deadline = time.time() + 20
        while not beat.exists() and time.time() < deadline:
            time.sleep(0.1)
        first = beat.read_text()
        deadline = time.time() + 20
        while beat.read_text() == first and time.time() < deadline:
            time.sleep(0.1)
        assert beat.read_text() != first, 'a second pass beat again'
        assert json.loads(beat.read_text())['pid'] == proc.pid
    finally:
        proc.kill()


def test_no_total_is_the_default(tmp_path, monkeypatch):
    cfg, _ = config(tmp_path, monkeypatch, limit_mib=1024)
    assert cfg['total'] == 0 and cfg['job'] == 0


def test_dry_run_kills_nothing(tmp_path, monkeypatch, capsys):
    proc = allocator(tmp_path, 300)
    try:
        only(monkeypatch, proc)
        cfg, pushed = config(tmp_path, monkeypatch, limit_mib=150)
        assert mem_guard.run_once(cfg, dry_run=True) == []
        time.sleep(0.5)
        assert proc.poll() is None and not pushed.exists()
        assert 'WOULD KILL' in capsys.readouterr().out
    finally:
        proc.kill()


@pytest.mark.parametrize('path', [
    '/System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer',
    '/System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow',
    '/Users/u/.local/share/claude/versions/2.1.319',
    '/Users/u/.local/bin/claude',
    '/Applications/Claude.app/Contents/Frameworks/Claude Helper (Renderer).app/Contents/MacOS/x',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/'
    'Versions/1/Helpers/Google Chrome Helper (Renderer).app/Contents/MacOS/x',
    '/opt/homebrew/bin/tmux',
    '/Users/u/.local/bin/tmux',
])
def test_the_named_never_kill_list(path):
    """general's list: never the window server, Claude Code, Chrome or the tmux server."""
    assert mem_guard.spared(path, path) is not None, path


@pytest.mark.parametrize('path', [
    '/Users/u/.local/share/whisper-env/bin/python',
    '/opt/homebrew/bin/python3.11',
    '/Users/u/dev/open-science/.venv/bin/python3',
    '/Users/u/.local/lib/node-v22/bin/node',
])
def test_ordinary_compute_is_not_spared(path):
    assert mem_guard.spared(path, path) is None, path


def test_a_bad_spare_pattern_refuses_at_start_not_mid_kill(monkeypatch):
    monkeypatch.setenv('MEM_GUARD_SPARE', '([')
    with pytest.raises(Exception):
        mem_guard.settings()
