"""The host watch: frozen apps resumed, pressure and spinning renderers pushed.

11-10: swap ran out at 00:02 on the compute host, the kernel suspended Chrome, Claude, Wispr Flow
and Grok Bot, memory recovered by 03:00, and the apps stayed frozen until 08:30. Six renderers of
the owner's Chrome had also spun at 100% CPU for 12 to 19 hours. The machine readings are handed
in, so these tests never depend on how loaded the test machine is; the resume test stops and
resumes a real process of its own.
"""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import host_watch as hw  # noqa: E402

UID = os.getuid()
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
RENDERER = ('/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/'
            'Helpers/Google Chrome Helper (Renderer).app/Contents/MacOS/Google Chrome Helper '
            '(Renderer) --type=renderer --lang=en-US')


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    pushed = tmp_path / 'pushed.txt'
    push = tmp_path / 'push'
    push.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> ' + str(pushed) + '\n')
    push.chmod(0o755)
    monkeypatch.setattr(hw, 'largest', lambda n=5: ['python3.12 14.6 GB'])
    c = dict(notify=str(push), state=tmp_path / 'state.json', log=tmp_path / 'events.jsonl',
             name='m5', swap_gb=16.0, spin_cpu=0.9, spin_s=3600.0)
    c['pushed'] = pushed
    return c


def pushes(cfg):
    return cfg['pushed'].read_text().splitlines() if cfg['pushed'].exists() else []


def proc(command, ppid=1, rss_kb=200000, cpu_s=10.0):
    return dict(ppid=ppid, uid=UID, rss_kb=rss_kb, cpu_s=cpu_s, command=command)


def test_ps_and_sysctl_formats():
    assert hw.cpu_seconds('0:11.21') == pytest.approx(11.21)
    assert hw.cpu_seconds('364:16.15') == pytest.approx(364 * 60 + 16.15)
    assert hw.cpu_seconds('1-02:03:04') == pytest.approx(86400 + 2 * 3600 + 3 * 60 + 4)
    assert hw.swap_used_gb('total = 3072.00M  used = 1605.31M  free = 1466.69M') == \
        pytest.approx(1605.31 / 1024)
    assert hw.swap_used_gb('total = 64.00G  used = 61.50G  free = 2.50G') == pytest.approx(61.5)


def stat(pid):
    return subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True,
                          text=True).stdout.strip()


def test_a_suspended_app_is_resumed_only_once_pressure_eases(cfg):
    """The 11-10 night: suspended at 00:02 under critical pressure, fine again by 03:00."""
    sleeper = subprocess.Popen(['sleep', '60'])
    try:
        os.kill(sleeper.pid, signal.SIGSTOP)        # the frozen app
        assert stat(sleeper.pid).startswith('T')
        procs = {sleeper.pid: proc(CHROME)}
        hw.run_once(cfg, procs=procs, level=4, swap=60, suspended=[('Google Chrome', sleeper.pid)],
                    now=1000)
        assert stat(sleeper.pid).startswith('T'), 'resuming into a full swap only re-suspends it'
        assert any('still critical' in p for p in pushes(cfg))
        hw.run_once(cfg, procs=procs, level=1, swap=4, suspended=[], now=1300)
        assert not stat(sleeper.pid).startswith('T')
        assert any('resumed 1 app' in p and 'Google Chrome [{}]'.format(sleeper.pid) in p
                   for p in pushes(cfg))
        before = len(pushes(cfg))
        hw.run_once(cfg, procs=procs, level=1, swap=4, suspended=[], now=1600)
        assert len(pushes(cfg)) == before, 'resumed once, not every pass'
    finally:
        sleeper.kill()


def test_an_app_with_collapsed_rss_and_no_cpu_is_resumed(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hw.os, 'kill', lambda pid, sig: sent.append((pid, sig)))
    procs = {101: proc('/Applications/Wispr Flow.app/Contents/MacOS/Wispr Flow', rss_kb=150, cpu_s=5),
             102: proc('/Applications/Wispr Flow.app/Contents/Frameworks/Wispr Flow Helper.app/'
                       'Contents/MacOS/Wispr Flow Helper --type=gpu', rss_kb=150, cpu_s=2),
             103: proc('/Applications/Busy.app/Contents/MacOS/Busy', rss_kb=150, cpu_s=5)}
    hw.run_once(cfg, procs=procs, level=1, swap=1, suspended=[], now=0)
    assert sent == [], 'one pass cannot tell idle from frozen'
    procs[103]['cpu_s'] = 6                          # it ran, so it is not frozen
    hw.run_once(cfg, procs=procs, level=1, swap=1, suspended=[], now=300)
    assert sorted(p for p, _ in sent) == [101, 102], 'the app and its helpers, not the busy one'
    assert any('Wispr Flow [101]' in p for p in pushes(cfg))


def test_a_healthy_app_is_left_alone(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hw.os, 'kill', lambda pid, sig: sent.append(pid))
    procs = {201: proc('/Applications/Claude.app/Contents/MacOS/Claude', rss_kb=400000, cpu_s=9)}
    for now in (0, 300, 600):
        hw.run_once(cfg, procs=procs, level=1, swap=1, suspended=[], now=now)
    assert sent == [] and pushes(cfg) == []


def test_pressure_is_pushed_once_per_episode_with_the_largest(cfg):
    for now in (0, 300):
        hw.run_once(cfg, procs={}, level=4, swap=60, suspended=[], now=now)
    assert len(pushes(cfg)) == 1 and 'python3.12 14.6 GB' in pushes(cfg)[0]
    hw.run_once(cfg, procs={}, level=1, swap=2, suspended=[], now=600)
    hw.run_once(cfg, procs={}, level=1, swap=30, suspended=[], now=900)   # swap alone counts
    assert len(pushes(cfg)) == 2 and 'memory high (swap 30 GB)' in pushes(cfg)[1]


def spin(cfg, procs, renderer_pid, rate, times):
    for now in times:
        procs[renderer_pid]['cpu_s'] = 100 + rate * now
        hw.run_once(cfg, procs=procs, level=1, swap=1, suspended=[], now=now)


def test_a_renderer_spinning_for_an_hour_is_pushed_once_with_its_session(cfg, monkeypatch):
    monkeypatch.setattr(hw, 'cwd_of', lambda pid: '/Users/x/dev/lane' if pid == 10 else '')
    procs = {10: proc('/Users/x/.local/bin/claude --resume abc'),
             11: proc('node /Users/x/.npm/_npx/playwright-mcp/cli.js', ppid=10),
             12: proc('/Users/x/Library/Caches/ms-playwright/chromium-1/Google Chrome for Testing.app/'
                      'Contents/MacOS/Google Chrome for Testing --headless', ppid=11)}
    spin(cfg, procs, 12, 0.97, [0, 1800, 3000])
    assert pushes(cfg) == [], 'under an hour is not yet a spin'
    spin(cfg, procs, 12, 0.97, [3700, 4000])
    said = pushes(cfg)
    assert len(said) == 1 and 'pid 12 at 97% CPU' in said[0]
    assert 'session pid 10' in said[0] and 'dir /Users/x/dev/lane' in said[0]


def test_his_own_chrome_is_named_and_a_dip_restarts_the_clock(cfg):
    procs = {4853: proc(CHROME), 17068: proc(RENDERER, ppid=4853)}
    spin(cfg, procs, 17068, 0.95, [0, 1800])
    procs[17068]['cpu_s'] += 10                       # 2100 s with ~10 s of CPU: it idled
    hw.run_once(cfg, procs=procs, level=1, swap=1, suspended=[], now=2100)
    spin(cfg, procs, 17068, 0.95, [2400, 4000])
    assert pushes(cfg) == [], 'the hour restarted at the dip'
    spin(cfg, procs, 17068, 0.95, [6100])
    assert len(pushes(cfg)) == 1 and "the owner's own Chrome" in pushes(cfg)[0]


def test_a_busy_but_not_spinning_renderer_is_quiet(cfg):
    procs = {4853: proc(CHROME), 17068: proc(RENDERER, ppid=4853)}
    spin(cfg, procs, 17068, 0.5, [0, 1800, 3600, 5400, 7200])
    assert pushes(cfg) == []


def test_status_changes_nothing(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(hw.os, 'kill', lambda pid, sig: sent.append(pid))
    said = hw.run_once(cfg, procs={5: proc(CHROME)}, level=1, swap=1,
                       suspended=[('Google Chrome', 5)], now=0, dry_run=True)
    assert said == ['would resume 5'] and sent == []
    assert not cfg['state'].exists() and pushes(cfg) == []


def test_every_action_is_logged(cfg):
    hw.run_once(cfg, procs={}, level=4, swap=60, suspended=[], now=0)
    row = json.loads(cfg['log'].read_text().splitlines()[-1])
    assert row['kind'] == 'pressure' and row['level'] == 4 and row['top'] == ['python3.12 14.6 GB']
