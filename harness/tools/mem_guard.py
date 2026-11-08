#!/usr/bin/env python3
"""Kill a runaway user process before it takes the whole machine down.

Why (2026-11-08). Two local python3.11 processes grew to about 47 GB and 35 GB of footprint on a
16 GB controller. The kernel's memory killer took system daemons instead of them, the window server
hung, and the hardware watchdog reset the machine at 22:16. It came back to a disk-encryption login
screen and sat there until morning, so nothing ran overnight, and every job on the compute host died
with its driver here. The load guard in launch.sh only looks at admission; nothing watched a
process that was admitted small and then grew.

So, every 30 s (launchd), for each process owned by this user:

  * measure its physical footprint, the number the kernel's memory killer uses. Not RSS: a process
    that has been compressed and swapped shows a small RSS, and on 11-08 a 6.3 GB process showed
    27 MB of RSS. Read with proc_pid_rusage, which is a syscall per process, not a 5 s `top`;
  * over the limit, and not spared: SIGTERM, then SIGKILL if it is still alive after a grace.
    SIGTERM first because the launcher and its watchdog read TERM as a deliberate stop and do not
    resume it, so a job killed here is not restarted into the same leak;
  * log one JSON row (name, pid, parent and its command, footprint, signal) and push the owner.

Spared by executable path or name, whatever their size: the window server, the agent sessions
(Claude Code and the Claude app), the browser, the tmux server that holds the sessions, the session
login machinery, and Apple's own binaries. Killing any of those costs more than the memory.

    mem_guard.py                 one pass: measure, kill, log, notify
    mem_guard.py --dry-run       one pass, printing what it would kill; kills nothing
    mem_guard.py --top 8         the largest footprints right now, with the verdict for each

Settings (environment):
    MEM_GUARD_LIMIT_GB   footprint limit per process (default 8)
    MEM_GUARD_SPARE      extra regexes, os.pathsep separated, matched against the executable path
    MEM_GUARD_LOG        JSONL log (default ~/.local/state/mem-guard/kills.jsonl)
    MEM_GUARD_NOTIFY     a command taking the message as its first argument; unset sends nothing
    MEM_GUARD_GRACE_S    seconds between TERM and KILL (default 5)

macOS only: the footprint comes from libproc. On anything else it refuses rather than guessing.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

GIB = 1024 ** 3
DEFAULT_LIMIT_GB = 8.0

# Never killed, whatever the size. Matched against the full executable path.
SPARE = [
    r'/WindowServer$',
    r'/loginwindow$',
    r'^/System/',                        # Apple's own binaries: Finder, Dock, daemons
    r'^/usr/(libexec|sbin|bin)/',
    r'^/Library/Apple/',
    r'/Claude\.app/',                    # the Claude desktop app and its helpers
    r'/\.local/(bin|share)/claude(/|$)',  # Claude Code: the launcher and its versioned binaries
    r'/claude/versions/',
    r'/Google Chrome[^/]*\.app/',
    r'/tmux$',
]


class RusageInfoV0(ctypes.Structure):
    _fields_ = [('ri_uuid', ctypes.c_uint8 * 16),
                ('ri_user_time', ctypes.c_uint64),
                ('ri_system_time', ctypes.c_uint64),
                ('ri_pkg_idle_wkups', ctypes.c_uint64),
                ('ri_interrupt_wkups', ctypes.c_uint64),
                ('ri_pageins', ctypes.c_uint64),
                ('ri_wired_size', ctypes.c_uint64),
                ('ri_resident_size', ctypes.c_uint64),
                ('ri_phys_footprint', ctypes.c_uint64),
                ('ri_proc_start_abstime', ctypes.c_uint64),
                ('ri_proc_exit_abstime', ctypes.c_uint64)]


_LIBPROC = None


def libproc():
    global _LIBPROC
    if _LIBPROC is None:
        if sys.platform != 'darwin':
            sys.exit('mem_guard: macOS only (footprint comes from libproc); refusing to guess')
        _LIBPROC = ctypes.CDLL(ctypes.util.find_library('proc') or '/usr/lib/libproc.dylib',
                               use_errno=True)
    return _LIBPROC


def footprint(pid):
    """Physical footprint in bytes, or None when the process is gone or not ours."""
    info = RusageInfoV0()
    if libproc().proc_pid_rusage(int(pid), 0, ctypes.byref(info)) != 0:
        return None
    return int(info.ri_phys_footprint)


def exe_path(pid):
    buf = ctypes.create_string_buffer(4096)
    n = libproc().proc_pidpath(int(pid), buf, ctypes.sizeof(buf))
    return buf.value.decode(errors='replace') if n > 0 else ''


def processes(uid):
    """(pid, ppid, command) for every process owned by uid, from one ps call."""
    out = subprocess.run(['ps', '-axww', '-o', 'pid=,ppid=,uid=,command='],
                         capture_output=True, text=True, timeout=30).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit() or int(parts[2]) != uid:
            continue
        rows.append((int(parts[0]), int(parts[1]), parts[3]))
    return rows


def spared(path, command, extra=()):
    """The pattern that spares this process, or None."""
    target = path or command.split(' ', 1)[0]
    for pattern in list(SPARE) + list(extra):
        if re.search(pattern, target):
            return pattern
    return None


def settings():
    limit = float(os.environ.get('MEM_GUARD_LIMIT_GB', '') or DEFAULT_LIMIT_GB)
    if not limit > 0:
        sys.exit('MEM_GUARD_LIMIT_GB must be positive')
    extra = [p for p in os.environ.get('MEM_GUARD_SPARE', '').split(os.pathsep) if p]
    for p in extra:
        re.compile(p)   # a bad pattern is a refusal now, not a crash mid-kill
    log = Path(os.path.expanduser(os.environ.get('MEM_GUARD_LOG',
                                                 '~/.local/state/mem-guard/kills.jsonl')))
    return dict(limit=int(limit * GIB), extra=extra, log=log,
                notify=os.environ.get('MEM_GUARD_NOTIFY', '').strip(),
                grace=float(os.environ.get('MEM_GUARD_GRACE_S', '') or 5))


def survey(cfg, uid=None):
    """Every process of this user with its footprint and verdict, largest first."""
    uid = os.getuid() if uid is None else uid
    me = os.getpid()
    rows = []
    commands = {}
    for pid, ppid, command in processes(uid):
        commands[pid] = command
        if pid == me:
            continue
        size = footprint(pid)
        if size is None:
            continue
        path = exe_path(pid)
        rows.append(dict(pid=pid, ppid=ppid, command=command, exe=path, footprint=size,
                         spared_by=spared(path, command, cfg['extra'])))
    for r in rows:
        r['parent_command'] = commands.get(r['ppid'], '')
    rows.sort(key=lambda r: -r['footprint'])
    return rows


def alive(pid):
    """Still running. A zombie is not: it holds no memory, and it stays a zombie until its own
    parent reaps it, which may be never. Counting it as alive made a TERM that worked look like a
    survivor that needed KILL."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    stat = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True,
                          text=True, timeout=10).stdout.strip()
    return bool(stat) and not stat.startswith('Z')


def kill(row, cfg):
    """TERM, wait, KILL if still there. Returns the signal that ended it, or None if it survived."""
    pid = row['pid']
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return 'gone'
    deadline = time.time() + cfg['grace']
    while time.time() < deadline:
        if not alive(pid):
            return 'TERM'
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return 'TERM'
    for _ in range(25):
        if not alive(pid):
            return 'KILL'
        time.sleep(0.2)
    return None


def name_of(row):
    return os.path.basename(row['exe']) if row['exe'] else row['command'].split(' ', 1)[0]


def parent_command(row):
    """The parent's command line, read directly: the parent may belong to another user (launchd,
    a root daemon), so it is not always in this user's process list."""
    if row.get('parent_command'):
        return row['parent_command']
    return subprocess.run(['ps', '-ww', '-o', 'command=', '-p', str(row['ppid'])],
                          capture_output=True, text=True, timeout=10).stdout.strip()


def record(row, how, cfg):
    row['parent_command'] = parent_command(row)
    cfg['log'].parent.mkdir(parents=True, exist_ok=True)
    entry = dict(time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), pid=row['pid'], name=name_of(row),
                 exe=row['exe'], command=row['command'][:500], ppid=row['ppid'],
                 parent_command=row['parent_command'][:500],
                 footprint_gib=round(row['footprint'] / GIB, 2),
                 limit_gib=round(cfg['limit'] / GIB, 2), signal=how)
    with cfg['log'].open('a') as fh:
        fh.write(json.dumps(entry) + '\n')
    return entry


def notify(entry, cfg):
    if not cfg['notify']:
        return
    parent = os.path.basename(entry['parent_command'].split(' ', 1)[0]) or '?'
    text = ('Memory guard {} {} (pid {}) at {:.1f} GB, limit {:.0f} GB. Parent: {} (pid {}).'
            .format('killed' if entry['signal'] else 'could NOT kill', entry['name'],
                    entry['pid'], entry['footprint_gib'], entry['limit_gib'], parent,
                    entry['ppid']))
    try:
        subprocess.run(cfg['notify'].split() + [text], timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass   # a failed push must never stop the next kill


def run_once(cfg, dry_run=False, uid=None, out=None):
    out = out or sys.stdout
    over = [r for r in survey(cfg, uid) if r['footprint'] > cfg['limit']]
    killed = []
    for row in over:
        size = row['footprint'] / GIB
        if row['spared_by']:
            print('spared {} pid {} at {:.1f} GiB ({})'.format(name_of(row), row['pid'], size,
                                                               row['spared_by']), file=out)
            continue
        if dry_run:
            print('WOULD KILL {} pid {} at {:.1f} GiB (parent {} {})'.format(
                name_of(row), row['pid'], size, row['ppid'], parent_command(row)[:80]), file=out)
            continue
        how = kill(row, cfg)
        entry = record(row, how, cfg)
        notify(entry, cfg)
        killed.append(entry)
        print('killed {} pid {} at {:.1f} GiB with {}'.format(entry['name'], row['pid'], size,
                                                             how), file=out)
    return killed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--top', type=int, default=0)
    args = ap.parse_args(argv)
    cfg = settings()
    if args.top:
        for r in survey(cfg)[:args.top]:
            verdict = ('spared' if r['spared_by'] else
                       'OVER' if r['footprint'] > cfg['limit'] else 'ok')
            print('{:>8} {:>7.2f} GiB  {:<6} {}'.format(r['pid'], r['footprint'] / GIB, verdict,
                                                        name_of(r)))
        return 0
    run_once(cfg, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
