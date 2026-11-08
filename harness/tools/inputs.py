#!/usr/bin/env python3
"""Public inputs, staged once and pinned, so a worker that may not download can still run.

Why (2026-11-06). The friends kill test for idea abaeaf1e has now returned BLOCKED twice in one
day for the same reason: "Exact public XTW-n308 fixture needed locally; none found. Downloads
prohibited, so solver not run." The input is public and free. The lane is not allowed to fetch it,
correctly, because a worker with network access is a worker that can exfiltrate and can be fed
anything. So the lane simply cannot produce a result, and nothing in the harness was responsible
for closing that gap.

This closes it the same way the X policy does: the step that reaches the network is not the
worker's. Someone stages the file once, by name, with its hash recorded; the worker asks for a
path and gets one, offline, forever after.

    inputs.py --lane L add  --name XTW-n308 --url https://.../X-n308-k13.vrp \\
              --sha256 <expected> --source "CVRPLIB"      # the staging step; network
    inputs.py --lane L path --name XTW-n308                # what a worker calls; no network
    inputs.py --lane L check                               # every input re-hashed
    inputs.py --lane L list

`--sha256` is what makes it a pin. Without it the file is still staged and its hash recorded, but
the row is marked unpinned and `list` says so, because nothing verified that this is the file the
source published. `check` always verifies against the recorded hash, which is what protects a
comparison made weeks apart: an input that changed under a lane invalidates every round that used
it, silently, and that is the failure this exists to prevent.

Deliberately small: http(s) only, no auth, no redirect to a non-http scheme, a size cap, and the
file lands under the lane's own inputs/ directory. It is not a package manager and it does not run
anything it downloads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the harness, for settings
import settings

INPUTS = 'INPUTS.jsonl'
STORE = 'inputs'
MAX_BYTES = 512 * 1024 * 1024
TIMEOUT = 120
AGENT = 'research-harness-inputs/1'


def read(path):
    out = {}
    try:
        lines = Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('name'):
            out[row['name']] = row
    return out


def append(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url, dest, max_bytes=None):
    """Download to dest. Returns (bytes, sha256). Raises ValueError on anything unexpected.

    max_bytes is read at call time, not bound as a default: a default would freeze the cap at
    import and make it unconfigurable, which my own test caught by patching it and watching a
    too-large file be staged anyway.
    """
    max_bytes = MAX_BYTES if max_bytes is None else max_bytes
    if not url.lower().startswith(('http://', 'https://')):
        raise ValueError('only http(s) URLs are staged, got: ' + url[:60])
    req = urllib.request.Request(url, headers={'User-Agent': AGENT})
    tmp = Path(str(dest) + '.part')
    tmp.parent.mkdir(parents=True, exist_ok=True)
    h, total = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if not str(r.geturl()).lower().startswith(('http://', 'https://')):
                raise ValueError('redirected off http(s)')
            with tmp.open('wb') as f:
                for block in iter(lambda: r.read(1 << 20), b''):
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError('larger than the {} byte cap'.format(max_bytes))
                    h.update(block)
                    f.write(block)
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise ValueError('download failed: {}'.format(getattr(exc, 'reason', exc)))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if total == 0:
        tmp.unlink(missing_ok=True)
        raise ValueError('the URL returned an empty body')
    os.replace(str(tmp), str(dest))
    return total, h.hexdigest()


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def safe_name(name):
    if not name or '/' in name or name.startswith('.') or any(c in name for c in '\\:'):
        raise ValueError('a name is a plain filename fragment, not a path: ' + str(name))
    return name


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--lane', required=True, type=Path)
    sub = p.add_subparsers(dest='action', required=True)

    add = sub.add_parser('add', help='stage a public input (this is the step with network)')
    add.add_argument('--name', required=True)
    add.add_argument('--url', required=True)
    add.add_argument('--sha256', default='', help='the expected hash; without it the row is '
                                                  'recorded as unpinned')
    add.add_argument('--source', default='', help='where it is published, for the receipt')
    add.add_argument('--filename', default='', help='local filename (default: the name)')

    one = sub.add_parser('path', help='the local path, for a worker; no network')
    one.add_argument('--name', required=True)

    sub.add_parser('check', help='re-hash every staged input; non-zero if any changed')
    sub.add_parser('list', help='what is staged for this lane')

    a = p.parse_args(argv)

    # A bare lane name resolves under RH_ROOT/lanes, and a directory that is not a lane

    # is refused. One resolver for every tool that takes --lane: all four took it as a

    # bare path, and planets hit the trap on 11-07.

    try:

        a.lane = settings.lane_dir(a.lane)

    except ValueError as exc:

        print('REFUSED: ' + str(exc), file=sys.stderr)

        return 2
    ledger = a.lane / INPUTS
    rows = read(ledger)

    if a.action == 'add':
        try:
            name = safe_name(a.name)
            dest = a.lane / STORE / safe_name(a.filename or a.name)
        except ValueError as exc:
            print('REFUSED: ' + str(exc), file=sys.stderr)
            return 2
        try:
            size, got = fetch(a.url, dest)
        except (ValueError, OSError) as exc:
            print('REFUSED: ' + str(exc), file=sys.stderr)
            return 2
        want = a.sha256.strip().lower()
        if want and want != got:
            Path(dest).unlink(missing_ok=True)
            print('REFUSED: hash mismatch for {}.\n  expected {}\n  got      {}\n'
                  'The file was not kept. Either the source changed or this is not the file the '
                  'lane means; both need a person, not a retry.'.format(name, want, got),
                  file=sys.stderr)
            return 2
        append(ledger, dict(name=name, url=a.url, source=a.source, sha256=got, bytes=size,
                            path=str(dest), staged_utc=now(), pinned=bool(want)))
        print('staged {} ({} bytes)\n  sha256 {}\n  at     {}{}'.format(
            name, size, got, dest,
            '' if want else '\n  UNPINNED: nothing verified this is the published file. Re-add '
                            'with --sha256 ' + got + ' once someone has checked it against the '
                            'source.'))
        return 0

    if a.action == 'list':
        if not rows:
            print('nothing staged for this lane')
            return 0
        for name, row in sorted(rows.items()):
            print('{:24} {:>12}  {}{}'.format(name, row.get('bytes', '?'),
                                              row.get('sha256', '')[:16],
                                              '' if row.get('pinned') else '  (unpinned)'))
        return 0

    if a.action == 'path':
        row = rows.get(a.name)
        if not row:
            print('{} is not staged for this lane. Someone with network access runs:\n'
                  '  inputs.py --lane {} add --name {} --url <public url> --sha256 <hash>\n'
                  'A worker does not download it.'.format(a.name, a.lane, a.name), file=sys.stderr)
            return 2
        target = Path(row['path'])
        if not target.is_file():
            print('{} is recorded but its file is gone: {}'.format(a.name, target), file=sys.stderr)
            return 2
        print(str(target))
        return 0

    bad = []
    for name, row in sorted(rows.items()):
        target = Path(row.get('path', ''))
        if not target.is_file():
            print('{:24} MISSING  {}'.format(name, target))
            bad.append(name)
            continue
        got = digest(target)
        if got != row.get('sha256'):
            print('{:24} CHANGED  recorded {}, now {}'.format(name, row.get('sha256', '')[:16],
                                                              got[:16]))
            bad.append(name)
        else:
            print('{:24} ok       {}'.format(name, got[:16]))
    if bad:
        print('REFUSED: {} input(s) are missing or changed: {}. Every round that used them since '
              'the last check compared against something else. Re-stage, and say so in the lane '
              'log.'.format(len(bad), ', '.join(bad)), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
