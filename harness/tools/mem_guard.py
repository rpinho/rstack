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

A whole-machine total too (11-10). On the 48 GB compute host no single process was huge (the
largest was 14.6 GB), but two six-hour jobs ran four workers each, and their footprints together
exhausted swap at 00:02. The kernel then suspended the largest apps (Chrome, Claude, Wispr Flow)
rather than the jobs, because it only suspends apps, and they stayed frozen until 08:30. So with
MEM_GUARD_TOTAL_GB set, after the per-process pass: while the footprints of all unspared processes
outside an app bundle add up to more than that, the largest of them is killed the same way. Apps
are neither counted nor killed by this rule; the per-process limit still applies to them.

And a per-job cap (11-10), the one that would have prevented that night. With MEM_GUARD_JOB_GB
set, every launcher job (launch.sh --host writes the job's pid to MEM_GUARD_JOBS_DIR/<job>.pid) is
measured as its whole process tree: the executor and every worker under it. A tree over the cap is
stopped whole, children first, TERM then KILL, and a MEMCAP line goes into the job's STATUS.md so
whoever reads the job sees why it ended. macOS ignores ulimit -v, so a watcher is the only cap there
is. A pid file is trusted only if its process started within two minutes of the file being written;
a stale file whose pid was reused by something else is ignored.

Spared by executable path or name, whatever their size: the window server, the agent sessions
(Claude Code and the Claude app), the browser, the tmux server that holds the sessions, the session
login machinery, and Apple's own binaries. Killing any of those costs more than the memory.

    mem_guard.py                 one pass: measure, kill, log, notify
    mem_guard.py --dry-run       one pass, printing what it would kill; kills nothing
    mem_guard.py --top 8         the largest footprints right now, with the verdict for each

Settings (environment):
    MEM_GUARD_LIMIT_GB   footprint limit per process (default 8)
    MEM_GUARD_TOTAL_GB   limit on all unspared non-app processes together (default: off)
    MEM_GUARD_JOB_GB     limit on one launcher job's whole process tree (default: off)
    MEM_GUARD_JOBS_DIR   the launcher's pid files (default ~/.local/state/research-harness/remote-jobs)
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
    total = float(os.environ.get('MEM_GUARD_TOTAL_GB', '') or 0)
    if total < 0:
        sys.exit('MEM_GUARD_TOTAL_GB must be positive, or unset for no total limit')
    job = float(os.environ.get('MEM_GUARD_JOB_GB', '') or 0)
    if job < 0:
        sys.exit('MEM_GUARD_JOB_GB must be positive, or unset for no per-job cap')
    jobs = Path(os.path.expanduser(os.environ.get('MEM_GUARD_JOBS_DIR', '') or
                                   '~/.local/state/research-harness/remote-jobs'))
    return dict(limit=int(limit * GIB), total=int(total * GIB), job=int(job * GIB), jobs=jobs,
                extra=extra, log=log,
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


# An app's own binaries, counted by neither the total nor its kills (the per-process limit still
# applies). Xcode's Python lives under Contents/Developer, so it is compute, not an app.
APP_BUNDLE = r'^/Applications/[^/]+\.app/Contents/(MacOS|Frameworks)/'


def cwd_of(pid):
    """The working directory, which names the job a worker belongs to. Read before the kill."""
    try:
        out = subprocess.run(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    return next((line[1:] for line in out.splitlines() if line.startswith('n')), '')


def record(row, how, cfg, rule='process', total=0, extra=None):
    row['parent_command'] = parent_command(row)
    cfg['log'].parent.mkdir(parents=True, exist_ok=True)
    entry = dict(time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), pid=row['pid'], name=name_of(row),
                 exe=row['exe'], command=row['command'][:500], ppid=row['ppid'],
                 parent_command=row['parent_command'][:500], cwd=row.get('cwd', ''),
                 footprint_gib=round(row['footprint'] / GIB, 2),
                 limit_gib=round({'total': cfg.get('total', 0), 'job': cfg.get('job', 0)}
                                 .get(rule, cfg['limit']) / GIB, 2),
                 rule=rule, signal=how)
    if rule in ('total', 'job'):
        entry['total_gib'] = round(total / GIB, 2)
    entry.update(extra or {})
    with cfg['log'].open('a') as fh:
        fh.write(json.dumps(entry) + '\n')
    return entry


def notify(entry, cfg):
    if not cfg['notify']:
        return
    parent = os.path.basename(entry['parent_command'].split(' ', 1)[0]) or '?'
    if entry.get('rule') == 'job':
        limit = 'whole job {} stopped at {:.1f} GB, cap {:.0f} GB'.format(
            entry.get('job', '?'), entry['total_gib'], entry['limit_gib'])
    elif entry.get('rule') == 'total':
        limit = 'largest of {:.1f} GB in jobs, limit {:.0f} GB total'.format(entry['total_gib'],
                                                                          entry['limit_gib'])
    else:
        limit = 'limit {:.0f} GB'.format(entry['limit_gib'])
    text = ('Memory guard {} {} (pid {}) at {:.1f} GB, {}. Parent: {} (pid {}).{}'
            .format('killed' if entry['signal'] else 'could NOT kill', entry['name'],
                    entry['pid'], entry['footprint_gib'], limit, parent, entry['ppid'],
                    ' Dir: ' + entry['cwd'] if entry.get('cwd') else ''))
    try:
        subprocess.run(cfg['notify'].split() + [text], timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass   # a failed push must never stop the next kill


def started(pid):
    """Process start time as epoch seconds, or None."""
    out = subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)], capture_output=True, text=True,
                         timeout=10).stdout.strip()
    try:
        return time.mktime(time.strptime(out, '%a %b %d %H:%M:%S %Y'))
    except ValueError:
        return None


def jobs(cfg):
    """[(job name, root pid)] for pid files whose process is the one that wrote them."""
    found = []
    for f in sorted(cfg['jobs'].glob('*.pid')) if cfg['jobs'].is_dir() else []:
        try:
            pid = int(f.read_text().strip())
        except (OSError, ValueError):
            continue
        t = started(pid)
        if t is not None and abs(t - f.stat().st_mtime) <= 120:
            found.append((f.stem, pid))
    return found


def tree(root, rows):
    """root and every descendant among rows."""
    kids = {}
    for r in rows:
        kids.setdefault(r['ppid'], []).append(r['pid'])
    out, todo = [], [root]
    while todo:
        pid = todo.pop()
        out.append(pid)
        todo.extend(kids.get(pid, []))
    return out


def memcap_note(workdir, text):
    """One line in the job's STATUS.md, which is what the job's reader opens first."""
    if not workdir:
        return
    try:
        with open(os.path.join(workdir, 'STATUS.md'), 'a') as fh:
            fh.write('\n' + text + '\n')
    except OSError:
        pass


def over_job_caps(rows, cfg, dry_run, out):
    """Stop every launcher job whose whole tree is over the per-job cap."""
    by_pid = {r['pid']: r for r in rows}
    stopped = []
    for name, root in jobs(cfg):
        pids = tree(root, rows)
        members = [by_pid[p] for p in pids if p in by_pid]
        size = sum(r['footprint'] for r in members)
        if size <= cfg['job']:
            continue
        top = max(members, key=lambda r: r['footprint'])
        if dry_run:
            print('WOULD STOP job {} ({} processes, {:.1f} GiB over the {:.0f} GiB cap)'.format(
                name, len(members), size / GIB, cfg['job'] / GIB), file=out)
            for r in members:
                r['gone'] = True
            continue
        workdir = cwd_of(root)
        signals = []
        for r in sorted(members, key=lambda r: r['pid'] == root):   # workers first, executor last
            r['cwd'] = workdir
            signals.append(kill(r, cfg))
            r['gone'] = True
        how = 'TERM' if all(x in ('TERM', 'gone') for x in signals) else (
            'KILL' if all(signals) else None)
        text = ('MEMCAP {}: the memory guard stopped this job at {:.1f} GB, cap {:.0f} GB. '
                'Largest process: {} pid {} at {:.1f} GB. Measure peak memory '
                '(/usr/bin/time -l) before running that step unattended again.').format(
            time.strftime('%Y-%m-%d %H:%M %Z'), size / GIB, cfg['job'] / GIB, name_of(top),
            top['pid'], top['footprint'] / GIB)
        memcap_note(workdir, text)
        entry = record(dict(top, cwd=workdir), how, cfg, rule='job', total=size,
                       extra=dict(job=name, processes=len(members)))
        notify(entry, cfg)
        stopped.append(entry)
        print('stopped job {} ({} processes) at {:.1f} GiB with {}'.format(
            name, len(members), size / GIB, how), file=out)
    return stopped


def run_once(cfg, dry_run=False, uid=None, out=None):
    out = out or sys.stdout
    rows = survey(cfg, uid)
    killed = over_job_caps(rows, cfg, dry_run, out) if cfg.get('job') else []
    over = [r for r in rows if r['footprint'] > cfg['limit'] and not r.get('gone')]
    for row in over:
        size = row['footprint'] / GIB
        if row['spared_by']:
            print('spared {} pid {} at {:.1f} GiB ({})'.format(name_of(row), row['pid'], size,
                                                               row['spared_by']), file=out)
            continue
        if dry_run:
            print('WOULD KILL {} pid {} at {:.1f} GiB (parent {} {})'.format(
                name_of(row), row['pid'], size, row['ppid'], parent_command(row)[:80]), file=out)
            row['gone'] = True   # counted as killed, so the total pass does not name it twice
            continue
        row['cwd'] = cwd_of(row['pid'])
        how = kill(row, cfg)
        row['gone'] = bool(how)
        entry = record(row, how, cfg)
        notify(entry, cfg)
        killed.append(entry)
        print('killed {} pid {} at {:.1f} GiB with {}'.format(entry['name'], row['pid'], size,
                                                             how), file=out)
    if cfg.get('total'):
        killed += over_total(rows, cfg, dry_run, out)
    return killed


def over_total(rows, cfg, dry_run, out):
    """Kill the largest job processes until all of them together fit under the total."""
    pool = [r for r in rows if not r['spared_by'] and not r.get('gone')
            and not re.search(APP_BUNDLE, r['exe'] or r['command'])]
    total = sum(r['footprint'] for r in pool)
    killed = []
    for row in sorted(pool, key=lambda r: -r['footprint']):
        if total <= cfg['total']:
            break
        size = row['footprint'] / GIB
        if dry_run:
            print('WOULD KILL {} pid {} at {:.1f} GiB: jobs total {:.1f} GiB over {:.0f}'.format(
                name_of(row), row['pid'], size, total / GIB, cfg['total'] / GIB), file=out)
            total -= row['footprint']
            continue
        row['cwd'] = cwd_of(row['pid'])
        how = kill(row, cfg)
        entry = record(row, how, cfg, rule='total', total=total)
        notify(entry, cfg)
        killed.append(entry)
        print('killed {} pid {} at {:.1f} GiB with {}: jobs total {:.1f} GiB'.format(
            entry['name'], row['pid'], size, how, total / GIB), file=out)
        if how:
            total -= row['footprint']
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
