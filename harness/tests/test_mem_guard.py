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
