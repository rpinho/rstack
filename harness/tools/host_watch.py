#!/usr/bin/env python3
"""Notice when the compute host's apps are frozen or a browser tab is spinning, and say so.

Why (2026-11-10). At 00:02 the 48 GB compute host ran out of swap: two six-hour jobs with four
workers each had filled it. The kernel's answer to swap exhaustion is to suspend the largest apps
(Chrome, Claude, Wispr Flow, Grok Bot, later Terminal), never command-line jobs. The jobs ended by
03:00 and memory recovered, but a suspended app stays suspended until someone resumes it. They sat
frozen, RSS near zero, until the owner sat down at 08:30. Separately, six renderers of the owner's
Chrome had been at 100% CPU for 12 to 19 hours, and nothing said so.

mem_guard.py (every few seconds) caps the jobs. This runs every 5 min (launchd) and does three things:

  1. memory pressure. Critical pressure, or swap past HOST_WATCH_SWAP_GB, pushes the owner once
     per episode with the largest footprints, so the cause is in the message;
  2. frozen apps. Apps the kernel suspended (it logs "suspending NAME [PID] due to swap
     exhaustion") and app main processes whose RSS collapsed under 2 MB with no CPU since the
     last pass are resumed with SIGCONT, which is what brought them back on 11-10 and is a no-op
     for a running process. Only once pressure is below critical: resuming into a full swap only
     gets them suspended again. Each resume is pushed;
  3. spinning renderers. A browser renderer or Chrome for Testing process using at least 90% of a
     core for an hour is pushed once, with the session that started it when its ancestors show
     one (a Claude Code or Codex session, with its working directory), or the owner's own browser.
     Nothing is killed: a tab may be the owner's.

    host_watch.py            one pass
    host_watch.py --status   what one pass would see, changing nothing

Settings (environment):
    HOST_WATCH_NOTIFY    command taking the message as its first argument; unset sends nothing
    HOST_WATCH_NAME      the machine's name in messages (default: its short host name)
    HOST_WATCH_STATE     state file (default ~/.local/state/host-watch/state.json)
    HOST_WATCH_LOG       JSONL log of every action (default ~/.local/state/host-watch/events.jsonl)
    HOST_WATCH_SWAP_GB   swap in use that counts as an episode (default 16)
    HOST_WATCH_SPIN_CPU  share of one core that counts as spinning (default 0.9)
    HOST_WATCH_SPIN_S    how long it must last (default 3600)

macOS only: pressure, swap and the kernel log are macOS interfaces.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

APP_MAIN = re.compile(r'^(/System)?/Applications/[^/]+\.app/Contents/MacOS/[^/]+$')
SPINNER = re.compile(r'--type=renderer|Helper \([^)]*Renderer\)|Chrome for Testing|chrome-headless-shell')
SUSPENDED = re.compile(r'suspending (.+?) \[(\d+)\] due to swap exhaustion')
SESSION = re.compile(r'(^|/)(claude|codex)( |$)|/claude/versions/|codex exec|claude -p')
CRITICAL = 4          # kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical
COLLAPSED_KB = 2048


def settings():
    env = os.environ.get
    home = Path(os.path.expanduser('~/.local/state/host-watch'))
    return dict(notify=env('HOST_WATCH_NOTIFY', '').strip(),
                name=env('HOST_WATCH_NAME', '') or os.uname().nodename.split('.')[0],
                state=Path(os.path.expanduser(env('HOST_WATCH_STATE', '') or home / 'state.json')),
                log=Path(os.path.expanduser(env('HOST_WATCH_LOG', '') or home / 'events.jsonl')),
                swap_gb=float(env('HOST_WATCH_SWAP_GB', '') or 16),
                spin_cpu=float(env('HOST_WATCH_SPIN_CPU', '') or 0.9),
                spin_s=float(env('HOST_WATCH_SPIN_S', '') or 3600))


# ---- reading the machine (each one small, so a test can hand in its own) ----

def sysctl(name):
    return subprocess.run(['sysctl', '-n', name], capture_output=True, text=True,
                          timeout=10).stdout.strip()


def pressure_level():
    try:
        return int(sysctl('kern.memorystatus_vm_pressure_level'))
    except ValueError:
        return 0


def swap_used_gb(text=None):
    """vm.swapusage reads 'total = 3072.00M  used = 1605.31M  free = ...'."""
    m = re.search(r'used = ([\d.]+)([MG])', text if text is not None else sysctl('vm.swapusage'))
    if not m:
        return 0.0
    return float(m.group(1)) / (1024 if m.group(2) == 'M' else 1)


def cpu_seconds(text):
    """ps time: [dd-][hh:]mm:ss.cc, where macOS lets minutes run past 59 ('364:16.15')."""
    days, _, rest = text.strip().rpartition('-')
    total = 0.0
    for part in rest.split(':'):
        total = total * 60 + float(part)
    return total + (int(days) * 86400 if days else 0)


def processes():
    """{pid: dict(ppid, uid, rss_kb, cpu_s, command)} for every process, from one ps call."""
    out = subprocess.run(['ps', '-axww', '-o', 'pid=,ppid=,uid=,rss=,time=,command='],
                         capture_output=True, text=True, timeout=30).stdout
    rows = {}
    for line in out.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        try:
            rows[int(parts[0])] = dict(ppid=int(parts[1]), uid=int(parts[2]), rss_kb=int(parts[3]),
                                       cpu_s=cpu_seconds(parts[4]), command=parts[5])
        except ValueError:
            continue
    return rows


def kernel_suspensions(seconds):
    """[(name, pid)] the kernel suspended for swap exhaustion in the last `seconds`."""
    pred = 'process == "kernel" AND eventMessage CONTAINS "due to swap exhaustion"'
    try:
        out = subprocess.run(['/usr/bin/log', 'show', '--last', '{}s'.format(int(seconds)),
                              '--style', 'compact', '--predicate', pred],
                             capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [(m.group(1), int(m.group(2))) for m in SUSPENDED.finditer(out)]


def cwd_of(pid):
    try:
        out = subprocess.run(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    return next((line[1:] for line in out.splitlines() if line.startswith('n')), '')


def largest(n=5):
    """The largest footprints right now, from mem_guard's reader, as 'name 12.3 GB' strings."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import mem_guard
        rows = mem_guard.survey(dict(extra=[]))
    except Exception:   # the pressure push matters more than its detail
        return []
    return ['{} {:.1f} GB'.format(mem_guard.name_of(r), r['footprint'] / 1024 ** 3) for r in rows[:n]]


# ---- deciding ----

def owner(pid, procs):
    """Who started this process: the nearest Claude Code or Codex session above it, else the app."""
    seen, p = set(), procs.get(pid, {}).get('ppid')
    app = None
    while p and p not in seen and p in procs:
        seen.add(p)
        cmd = procs[p]['command']
        if SESSION.search(cmd.split(' --', 1)[0]) or 'codex exec' in cmd or 'claude -p' in cmd:
            where = cwd_of(p)
            return 'session pid {} ({}){}'.format(p, cmd[:60], ', dir ' + where if where else '')
        if app is None and APP_MAIN.match(cmd.split(' -', 1)[0].rstrip()):
            app = cmd.split(' -', 1)[0].rstrip()
        p = procs[p]['ppid']
    if app and 'Google Chrome.app' in app:
        return "the owner's own Chrome (no session above it)"
    return os.path.basename(app) if app else 'no session found'


def app_main(cmd):
    exe = cmd.split(' -', 1)[0].rstrip()
    return exe if APP_MAIN.match(exe) else None


def spinners(procs, state, now, cfg):
    """Update per-pid CPU tracks; return the pids that have spun for spin_s and are not yet told."""
    tracks = state.setdefault('spin', {})
    live = set()
    due = []
    for pid, p in procs.items():
        if p['uid'] != os.getuid() or not SPINNER.search(p['command']):
            continue
        key = str(pid)
        live.add(key)
        t = tracks.get(key)
        if t is None or t.get('cmd') != p['command'][:200]:
            tracks[key] = dict(cmd=p['command'][:200], t=now, cpu=p['cpu_s'], since=None, told=False)
            continue
        dt = now - t['t']
        rate = (p['cpu_s'] - t['cpu']) / dt if dt > 0 else 0
        if rate >= cfg['spin_cpu']:
            t['since'] = t['t'] if t['since'] is None else t['since']
        else:
            t['since'], t['told'] = None, False
        t['t'], t['cpu'], t['rate'] = now, p['cpu_s'], round(rate, 2)
        if t['since'] is not None and now - t['since'] >= cfg['spin_s'] and not t['told']:
            due.append(pid)
    for key in list(tracks):
        if key not in live:
            del tracks[key]
    return due


def frozen(procs, state):
    """App main processes with collapsed RSS and no CPU since the last pass."""
    last = state.get('apps', {})
    now_apps, out = {}, []
    for pid, p in procs.items():
        if p['uid'] != os.getuid() or not app_main(p['command']):
            continue
        now_apps[str(pid)] = p['cpu_s']
        prev = last.get(str(pid))
        if prev is not None and p['cpu_s'] == prev and p['rss_kb'] < COLLAPSED_KB:
            out.append(pid)
    state['apps'] = now_apps
    return out


def bundle_of(cmd):
    m = re.match(r'^((/System)?/Applications/[^/]+\.app)/', cmd)
    return m.group(1) if m else None


def resume(pids, procs):
    """SIGCONT each pid and every process of the same app bundle (its helpers). Returns names."""
    bundles = {bundle_of(procs[p]['command']) for p in pids if p in procs} - {None}
    targets = set(pids) | {q for q, p in procs.items()
                           if p['uid'] == os.getuid() and bundle_of(p['command']) in bundles}
    done = []
    for pid in sorted(targets):
        try:
            os.kill(pid, signal.SIGCONT)
        except (ProcessLookupError, PermissionError):
            continue
        if pid in pids:
            done.append('{} [{}]'.format(os.path.basename(app_main(procs[pid]['command']) or
                                                          procs[pid]['command'].split(' ')[0]), pid))
    return done


# ---- one pass ----

def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def emit(cfg, kind, text, **fields):
    cfg['log'].parent.mkdir(parents=True, exist_ok=True)
    with cfg['log'].open('a') as fh:
        fh.write(json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), kind=kind,
                                 text=text, **fields)) + '\n')
    if cfg['notify']:
        try:
            subprocess.run(cfg['notify'].split() + [text], timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass
    return text


def run_once(cfg, procs=None, level=None, swap=None, suspended=None, now=None, dry_run=False):
    now = time.time() if now is None else now
    state = load(cfg['state'])
    procs = processes() if procs is None else procs
    level = pressure_level() if level is None else level
    swap = swap_used_gb() if swap is None else swap
    last = state.get('last_run', now - 360)
    if suspended is None:
        suspended = kernel_suspensions(min(max(now - last + 60, 360), 86400))
    said = []

    # 1. pressure episode
    hot = level >= CRITICAL or swap >= cfg['swap_gb']
    if hot and state.get('episode') is None:
        state['episode'] = now
        top = largest()
        text = '{} memory {} (swap {:.0f} GB). Largest: {}.'.format(
            cfg['name'], 'critical' if level >= CRITICAL else 'high', swap, ', '.join(top) or 'unknown')
        said.append(text if dry_run else
                    emit(cfg, 'pressure', text, level=level, swap_gb=round(swap, 1), top=top))
    elif not hot and state.get('episode') is not None:
        state['episode'] = None

    # 2. frozen apps: remember what the kernel suspended, resume once pressure allows
    pending = {int(k): v for k, v in state.get('pending', {}).items()}
    for name, pid in suspended:
        if pid in procs:
            pending[pid] = name
    pending.update({pid: app_main(procs[pid]['command']) or '?' for pid in frozen(procs, state)})
    pending = {pid: n for pid, n in pending.items() if pid in procs}
    if pending and level < CRITICAL:
        if dry_run:
            said.append('would resume ' + ', '.join(str(p) for p in sorted(pending)))
        else:
            names = resume(sorted(pending), procs)
            if names:
                said.append(emit(cfg, 'resume', '{}: resumed {} app(s) frozen by low memory: {}.'
                                 .format(cfg['name'], len(names), ', '.join(names)), pids=sorted(pending)))
            pending = {}
    elif pending and state.get('told_frozen') is None:
        state['told_frozen'] = now
        if not dry_run:
            said.append(emit(cfg, 'frozen', '{}: {} app(s) frozen by low memory, memory still '
                             'critical, resuming when it eases.'.format(cfg['name'], len(pending)),
                             pids=sorted(pending)))
    if not pending:
        state['told_frozen'] = None
    state['pending'] = {str(k): v for k, v in pending.items()}

    # 3. spinning renderers
    for pid in spinners(procs, state, now, cfg):
        t = state['spin'][str(pid)]
        hours = (now - t['since']) / 3600
        text = ('{}: renderer pid {} at {:.0f}% CPU for {:.1f} h. Owner: {}. {}'.format(
            cfg['name'], pid, 100 * t.get('rate', 0), hours, owner(pid, procs), t['cmd'].split(' --', 1)[0][-70:]))
        if dry_run:
            said.append(text)
        else:
            t['told'] = True
            said.append(emit(cfg, 'spin', text, pid=pid))

    state['last_run'] = now
    if not dry_run:
        cfg['state'].parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg['state'].with_suffix('.tmp')
        tmp.write_text(json.dumps(state))
        tmp.replace(cfg['state'])
    return said


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--status', action='store_true', help='one pass that changes nothing')
    args = ap.parse_args(argv)
    if sys.platform != 'darwin':
        sys.exit('host_watch: macOS only (pressure, swap and the kernel log); refusing to guess')
    for line in run_once(settings(), dry_run=args.status):
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
