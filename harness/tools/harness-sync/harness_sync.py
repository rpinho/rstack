#!/usr/bin/env python3
"""harness-sync: install the harness from one source, the repo, and notice any drift.

The installed copy and the repo drifted for days: fixes went straight into the installed
files, other fixes went only into the repo, and each copy aged differently. This makes the
committed repo the only source. It installs the git-tracked files under harness/ at a
committed ref (default: main), never the working tree, so a half-finished edit cannot reach
running lanes. Installed code is made read-only so a hand edit fails loudly instead of
drifting quietly. Lanes, ledgers and other runtime state in the installed root are never
touched.

  harness-sync --check   report drift, change nothing; exit 2 if any
  harness-sync --auto    install only when the installed copy is merely behind the ref
                         (no hand edits, no stray modules, no harness job running);
                         otherwise report and exit 2. Run by the scheduled tick.
  harness-sync           install the ref; hand-edited and stray files are backed up first

Every file it replaces or removes is copied to --backups/<utc>/ first; removals go to Trash.
The installed commit is recorded in <root>/.harness-sync.json.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import storage  # noqa: E402  (Trash-only deletion; refuses when no Trash command exists)

RECEIPT = '.harness-sync.json'
CODE_SUFFIXES = {'.py', '.sh'}
SKIP_DIRS = {'lanes', '__pycache__', 'alerts', '.pytest_cache'}
HOST_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}\Z')


def git(repo, *args, data=None):
    return subprocess.run(['git', '-C', str(repo), *args], input=data, capture_output=True,
                          check=True).stdout


def blob_id(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def manifest(repo, ref):
    """{relative path: (mode, blob id)} for tracked files under harness/ at ref."""
    out = git(repo, 'ls-tree', '-r', '-z', '--full-tree', ref, 'harness/')
    files = {}
    for entry in filter(None, out.split(b'\0')):
        meta, path = entry.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        if kind == 'blob' and mode != '120000':
            files[path.decode()[len('harness/'):]] = (mode, oid)
    return files


def contents(repo, oids):
    """Read blobs in one git cat-file --batch call."""
    if not oids:
        return {}
    out = git(repo, 'cat-file', '--batch', data=''.join(o + '\n' for o in oids).encode())
    blobs, at = {}, 0
    for oid in oids:
        header_end = out.index(b'\n', at)
        size = int(out[at:header_end].split()[2])
        blobs[oid] = out[header_end + 1:header_end + 1 + size]
        at = header_end + 1 + size + 1
    return blobs


def stray_code(root, expected):
    """Installed code files the ref does not have (a module added by hand, say).
    Backup copies (*.bak*) and runtime state are ignored."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        # stale-lanes-*: archived lane copies kept under the root (the m5's stale-lanes-1107 is 11 GB).
        # They are data, not stray modules; on 11-10 a run retired 4,454 of their scripts to the Trash.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')
                       and not d.startswith('stale-lanes')]
        for name in filenames:
            rel = (rel_dir / name).as_posix()
            if '.bak' in name or Path(name).suffix not in CODE_SUFFIXES or rel in expected:
                continue
            found.append(rel)
    return sorted(found)


def running_jobs():
    """launchd harness jobs that currently have a PID (label only, never command lines)."""
    try:
        out = subprocess.run(['launchctl', 'list'], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    jobs = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0] != '-' and 'research-harness' in parts[2]:
            jobs.append(parts[2])
    return jobs


def plan(repo, root, ref):
    files = manifest(repo, ref)
    receipt = {}
    try:
        receipt = json.loads((root / RECEIPT).read_text())
    except (FileNotFoundError, ValueError):
        pass
    previous = {}
    if receipt.get('commit'):
        try:
            previous = manifest(repo, receipt['commit'])
        except subprocess.CalledProcessError:
            previous = {}
    rows = []  # (status, path)
    for rel, (mode, oid) in sorted(files.items()):
        dest = root / rel
        if not dest.is_file():
            rows.append(('missing', rel))
            continue
        have = blob_id(dest.read_bytes())
        if have == oid:
            if (mode == '100755') != os.access(dest, os.X_OK):
                rows.append(('behind', rel))
            continue
        # Matches what the last install wrote (or the file did not exist then): the
        # installed copy is just older than the ref. Anything else was edited in place.
        old = previous.get(rel)
        rows.append(('behind' if old and old[1] == have else 'edited', rel))
    for rel in sorted(set(previous) - set(files)):
        if (root / rel).is_file():
            rows.append(('removed', rel))
    for rel in stray_code(root, set(files) | set(previous)):
        rows.append(('stray', rel))
    return files, receipt, rows


def install(repo, root, ref, files, rows, backups):
    commit = git(repo, 'rev-parse', ref + '^{commit}').decode().strip()
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_root = backups / stamp
    todo = {rel for status, rel in rows if status in ('missing', 'behind', 'edited')}
    blobs = contents(repo, sorted({files[rel][1] for rel in todo}))

    def back_up(rel):
        src = root / rel
        if src.is_file():
            dest = backup_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    for rel in sorted(todo):
        mode, oid = files[rel]
        dest = root / rel
        back_up(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name('.' + dest.name + '.harness-sync-tmp')
        tmp.write_bytes(blobs[oid])
        os.chmod(tmp, 0o555 if mode == '100755' else 0o444)
        os.replace(tmp, dest)  # atomic: a running process keeps the file it opened
        print('installed ' + rel)
    for status, rel in rows:
        if status in ('removed', 'stray'):
            back_up(rel)
            storage.trash(root / rel)  # recoverable from Trash, and copied to the backup directory
            print('retired   {} ({})'.format(rel, status))
    receipt = dict(commit=commit, ref=ref, utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                   repo=str(repo), files=len(files))
    (root / RECEIPT).write_text(json.dumps(receipt, indent=1) + '\n')
    if backup_root.exists():
        print('backups in ' + str(backup_root))
    print('installed {} at {}'.format(ref, commit[:12]))



# --- the same install, on another machine ------------------------------------------------------
#
# 11-07, general: "the m5's harness checkout is 16 commits behind main, and nothing keeps it
# current." Half right, and the half that matters is elsewhere. A `--host` job does not run the
# host's CHECKOUT: launch.sh runs $HOME/.local/share/research-harness/agent_executor.py there,
# which is the host's INSTALLED harness. On 11-07 that was at 906efdc while main was at ff47140,
# and the one commit between them touching agent_executor.py was a73a033, the codex sandbox fix.
# So --host jobs were running an executor the controller had already fixed. Meanwhile the host's
# checkout was at dee270d, OLDER than what was installed there, so having the host follow
# origin/main and install for itself would have installed older code than it was already running.
#
# The one-source rule extends outward instead of being duplicated: this controller turns committed
# main into installed files, here and on the host, and the host never installs for itself. Nothing
# is removed on the host, because a deletion over ssh is a deletion nobody watched; a file the ref
# no longer has is reported for a person.

PROBE_LOOP = [
    'while IFS= read -r rel; do',
    '  [ -n "$rel" ] || continue',
    '  if [ -f "$rel" ]; then',
    '    oid=$(git hash-object -- "$rel") || oid=UNREADABLE',
    '    if [ -x "$rel" ]; then ex=x; else ex=-; fi',
    '    printf "%s %s %s\\n" "$oid" "$ex" "$rel"',
    '  else',
    '    printf "MISSING - %s\\n" "$rel"',
    '  fi',
    "done <<'HARNESS_SYNC_PATHS'",
]


def host_probe_program(root, paths):
    """A shell program printing `blobid x|- rel` for each path under root on the host.

    `git hash-object` computes exactly the blob id blob_id() computes here, so the two sides are
    compared by content and neither side's bookkeeping has to be trusted.
    """
    head = 'cd ' + shlex.quote(str(root)) + ' 2>/dev/null || { echo NOROOT; exit 0; }'
    return '\n'.join([head] + PROBE_LOOP + sorted(paths) + ['HARNESS_SYNC_PATHS', ''])


def ssh_argv(ssh=None):
    return shlex.split(ssh or os.environ.get('LAUNCH_SSH', 'ssh')) + ['-o', 'BatchMode=yes']


def host_state(host, root, paths, ssh=None):
    """{rel: (blob id or None, executable)} for `paths` on the host. Raises on an unusable host."""
    out = subprocess.run(ssh_argv(ssh) + [host, 'sh -s'],
                         input=host_probe_program(root, paths),
                         capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise ValueError('cannot read the harness on {}: {}'.format(host, out.stderr.strip()[:200]))
    if out.stdout.split('\n')[0].strip() == 'NOROOT':
        raise ValueError('{} has no harness root at {}'.format(host, root))
    state = {}
    for line in out.stdout.splitlines():
        parts = line.split(' ', 2)
        if len(parts) != 3:
            continue
        oid, ex, rel = parts
        state[rel] = (None if oid in ('MISSING', 'UNREADABLE') else oid, ex == 'x')
    return state


def host_receipt(host, root, ssh=None):
    """The host's install receipt, or {} when it has none or it is unreadable."""
    out = subprocess.run(ssh_argv(ssh) + [host, 'cat ' + shlex.quote(str(Path(root) / RECEIPT))],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return {}
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def host_plan(repo, ref, host, root, ssh=None):
    """(files, rows) for the host, in plan()'s shape: (status, rel)."""
    files = manifest(repo, ref)
    state = host_state(host, root, files, ssh=ssh)
    rows = []
    for rel, (mode, oid) in sorted(files.items()):
        have, executable = state.get(rel, (None, False))
        if have is None:
            rows.append(('missing', rel))
        elif have != oid:
            # No per-file history is kept for the host, so this says "not the ref" and no more.
            # Calling it "edited" would claim to know something this cannot see.
            rows.append(('behind', rel))
        elif (mode == '100755') != executable:
            rows.append(('behind', rel))
    return files, rows


def install_host(repo, root, ref, files, rows, host, ssh=None):
    """Write the ref's files to the host, verified by hash there before the receipt is written."""
    commit = git(repo, 'rev-parse', ref + '^{commit}').decode().strip()
    todo = sorted({rel for status, rel in rows if status in ('missing', 'behind', 'edited')})
    if not todo:
        print('{}: already at {}'.format(host, commit[:12]))
        return 0
    blobs = contents(repo, sorted({files[rel][1] for rel in todo}))
    rsh = ssh or os.environ.get('LAUNCH_SSH', 'ssh')
    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging)
        for rel in todo:
            mode, oid = files[rel]
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blobs[oid])
            os.chmod(dest, 0o555 if mode == '100755' else 0o444)
        listing = stage / '.harness-sync-files'
        listing.write_text('\n'.join(todo) + '\n')
        send = subprocess.run(['rsync', '-a', '--timeout=120', '-e', rsh,
                               '--files-from=' + str(listing), str(stage) + '/',
                               host + ':' + str(root).rstrip('/') + '/'],
                              capture_output=True, text=True, timeout=1800)
    if send.returncode != 0:
        raise ValueError('rsync to {} failed: {}'.format(host, send.stderr.strip()[:300]))
    # Verified by content on the host, never by rsync's exit status: a transfer tool's exit code
    # says it did what it decided to do. The receipt is written only after this passes, so a
    # half-arrived install cannot claim a commit.
    after = host_state(host, root, todo, ssh=ssh)
    bad = [rel for rel in todo
           if after.get(rel, (None, False))[0] != files[rel][1]
           or after.get(rel, (None, False))[1] != (files[rel][0] == '100755')]
    if bad:
        raise ValueError('{}: {} file(s) did not arrive as the ref has them, so the receipt was '
                         'NOT written: {}'.format(host, len(bad), ', '.join(bad[:5])))
    receipt = dict(commit=commit, ref=ref,
                   utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                   repo=str(repo), files=len(files), installed_from='controller')
    write = subprocess.run(ssh_argv(ssh) + [host, 'cat > ' + shlex.quote(str(Path(root) / RECEIPT))],
                           input=json.dumps(receipt, indent=1) + '\n',
                           capture_output=True, text=True, timeout=120)
    if write.returncode != 0:
        raise ValueError('{}: the files are installed but the receipt could not be written, so the '
                         'host still reads as behind: {}'.format(host, write.stderr.strip()[:200]))
    for rel in todo:
        print('installed {}:{}'.format(host, rel))
    print('{}: installed {} at {} ({} file(s))'.format(host, ref, commit[:12], len(todo)))
    return 0

def configured_hosts():
    """Hosts this controller keeps up to date, from RH_HARNESS_HOSTS (comma or space separated).

    Kept here rather than in a second scheduled job: the tick already runs `harness-sync --auto`,
    and the machine that turns committed main into installed files is the only machine that should
    be deciding what the host runs. A host that cannot be reached is reported, not fatal, because
    the launch path refuses a drifted host at use time anyway, which is the guarantee that matters.
    """
    raw = os.environ.get('RH_HARNESS_HOSTS', '')
    return [h for h in re.split(r'[,\s]+', raw) if h and HOST_RE.fullmatch(h)]


def follow_hosts(repo, root, ref):
    """Bring every configured host to `ref`. Returns the number that could not be brought there."""
    bad = 0
    for host in configured_hosts():
        try:
            files, rows = host_plan(repo, ref, host, root)
            if not rows:
                print('{} already matches {}'.format(host, ref))
                continue
            install_host(repo, root, ref, files, rows, host)
        except (ValueError, subprocess.SubprocessError, OSError) as exc:
            bad += 1
            print('{}: NOT brought to {}: {}'.format(host, ref, str(exc)[:200]))
            print('{}: --host jobs there will refuse until this is fixed, which is the intended '
                  'outcome rather than running old code.'.format(host))
    return bad


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', default='~/.local/share/research-harness', help='installed harness root')
    p.add_argument('--repo', default=str(Path(__file__).resolve().parents[3]), help='source repo')
    p.add_argument('--ref', default='main', help='committed ref to install (never the working tree)')
    p.add_argument('--backups', default='~/.local/state/harness-sync/backups')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='report drift, change nothing; exit 2 if any')
    mode.add_argument('--auto', action='store_true', help='install only a clean fast-forward; else exit 2')
    p.add_argument('--allow-running', action='store_true', help='install even while a harness job runs')
    p.add_argument('--host', default='', help='install onto another machine over ssh, at the same '
                                              'root; the host never installs for itself')
    a = p.parse_args(argv)
    root = Path(a.root).expanduser()
    repo = Path(a.repo).expanduser()

    if a.host:
        # The host's copy is only ever written from here, from a committed ref, and the controller
        # has to be at that ref itself first: installing outward from a drifted controller would
        # spread the drift rather than fix it.
        own_files, own_receipt, own_rows = plan(repo, root, a.ref)
        commit = git(repo, 'rev-parse', a.ref + '^{commit}').decode().strip()
        if own_rows:
            print('not installing onto {}: this machine is not at {} yet ({} file(s) differ). Run '
                  'harness-sync here first.'.format(a.host, a.ref, len(own_rows)))
            return 2
        try:
            files, rows = host_plan(repo, a.ref, a.host, root, ssh=None)
        except ValueError as exc:
            print('REFUSED: ' + str(exc))
            return 2
        remote = host_receipt(a.host, root)
        print('repo {} {} | {} installed {}'.format(
            a.ref, commit[:12], a.host, (remote.get('commit') or 'unknown')[:12]))
        for status, rel in rows:
            print('{:<9} {}:{}'.format(status.upper(), a.host, rel))
        if not rows:
            print('{} matches {} ({} files)'.format(a.host, a.ref, len(files)))
            return 0
        if a.check:
            return 2
        try:
            return install_host(repo, root, a.ref, files, rows, a.host, ssh=None)
        except ValueError as exc:
            print('REFUSED: ' + str(exc))
            return 2

    files, receipt, rows = plan(repo, root, a.ref)
    commit = git(repo, 'rev-parse', a.ref + '^{commit}').decode().strip()
    print('repo {} {} | installed {}'.format(a.ref, commit[:12], (receipt.get('commit') or 'unknown')[:12]))
    for status, rel in rows:
        print('{:<9} {}'.format(status.upper(), rel))
    if not rows:
        print('installed copy matches {} ({} files)'.format(a.ref, len(files)))
        follow_hosts(repo, root, a.ref)
        return 0
    if a.check:
        return 2
    unsafe = [r for r in rows if r[0] in ('edited', 'stray')]
    if a.auto and unsafe:
        print('not installing: {} file(s) were changed in the installed copy; '
              'commit them to the repo or run harness-sync by hand'.format(len(unsafe)))
        return 2
    jobs = running_jobs()
    if jobs and not a.allow_running:
        print('not installing: harness job running: ' + ', '.join(jobs))
        return 2
    install(repo, root, a.ref, files, rows, Path(a.backups).expanduser())
    # Outward, in the same breath: the hosts run what this machine just installed, or they refuse.
    follow_hosts(repo, root, a.ref)
    return 0


if __name__ == '__main__':
    sys.exit(main())
