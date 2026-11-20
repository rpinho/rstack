#!/usr/bin/env python3
"""Run someone else's code only from a pinned commit, in a sandbox with no network that writes only the job dir.

Why (11-20): a math sweep's kill stage fetched two files of a public repo (a SAT driver and a C witness finder
at a pinned commit), compiled one and ran an adapted copy of the other with full network and write access. The
result was a bounded negative and nothing cites it, but downloaded code had run unreviewed with the run's own
permissions. Running published code is still the normal thing to do (normal-first runs the stock method
first; baseline.py and the bug referee run published code on purpose), so this does not stop it. It makes the
one safe way the only way that passes:

    third_party.py run --workdir JOB --url URL --commit SHA40 [--subdir NAME] -- CMD ARGS...

fetches URL at exactly SHA40 into JOB/third_party/NAME-SHA12/ (the tool fetches; the code never touches the
network), then runs CMD there under macOS sandbox-exec: no network at all, file writes only inside JOB. Each
run appends a receipt row to JOB/third_party.jsonl (url, commit, dir, command, rc). There is no unsandboxed
fallback: without sandbox-exec it refuses.

    third_party.py check JOB

is the controller's check (sweep.py calls it on every run directory). It fails when
  - a git checkout sits in JOB outside third_party/, or a third_party/ folder has no receipt;
  - code fetched from a code host (sources.jsonl rows from GitHub/GitLab raw or blob URLs with a code
    extension) is in JOB under a runnable name, or copied byte for byte to one, outside third_party/.
Fetched code stays readable as data: save it as NAME.txt (e.g. gridcegar.py.txt).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse

RECEIPTS = 'third_party.jsonl'
DIR = 'third_party'
SHA40 = re.compile(r'[0-9a-f]{40}')
CODE_HOSTS = ('raw.githubusercontent.com', 'github.com', 'gist.githubusercontent.com', 'gitlab.com',
              'codeberg.org', 'bitbucket.org')
CODE_EXT = {'.py', '.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.rs', '.go', '.jl', '.js', '.mjs', '.ts', '.sh',
            '.zsh', '.bash', '.pl', '.rb', '.r', '.java', '.kt', '.scala', '.m', '.f90', '.f', '.lean', '.hs',
            '.ml', '.swift', '.cu', '.ipynb', '.sage', '.gp', '.mpl', '.wl', '.lua', '.php', '.cs', '.zig'}
SANDBOX = '/usr/bin/sandbox-exec'


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def profile(job):
    """Deny all network; deny every file write except inside JOB and the standard devices."""
    job = str(Path(job).resolve())
    q = job.replace('\\', '\\\\').replace('"', '\\"')
    return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            '(allow file-write* (subpath "{}") (literal "/dev/null") (literal "/dev/zero") '
            '(literal "/dev/stdout") (literal "/dev/stderr") (literal "/dev/dtracehelper") '
            '(regex #"^/dev/tty") (regex #"^/dev/fd/"))\n').format(q)


def slug(url):
    name = Path(urlparse(url).path.rstrip('/')).name or 'repo'
    return re.sub(r'[^A-Za-z0-9._-]+', '-', name[:-4] if name.endswith('.git') else name)


def git(*args, cwd=None):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('git {}: {}'.format(' '.join(args), r.stderr.strip()[-300:]))
    return r.stdout.strip()


def fetch(job, url, commit, subdir=None):
    """URL at exactly COMMIT into JOB/third_party/NAME-SHA12/; an existing checkout must already be at COMMIT."""
    if not SHA40.fullmatch(commit or ''):
        raise ValueError('UNPINNED: --commit must be a full 40-character commit sha, not a branch or tag')
    dest = Path(job) / DIR / '{}-{}'.format(subdir or slug(url), commit[:12])
    if (dest / '.git').exists():
        head = git('rev-parse', 'HEAD', cwd=dest)
        if head != commit:
            raise ValueError('CHECKOUT_MOVED: {} is at {}, not {}'.format(dest, head, commit))
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    git('init', '-q', cwd=dest)
    git('fetch', '-q', '--depth', '1', url, commit, cwd=dest)
    git('checkout', '-q', '--detach', 'FETCH_HEAD', cwd=dest)
    head = git('rev-parse', 'HEAD', cwd=dest)
    if head != commit:
        raise ValueError('PIN_MISMATCH: fetched {} for {}'.format(head, commit))
    return dest


def run(job, url, commit, cmd, subdir=None, timeout=None, sandbox=SANDBOX, stdout=None, stderr=None):
    job = Path(job).resolve()
    if not cmd:
        raise ValueError('no command')
    if not (sandbox and Path(sandbox).exists()):
        raise RuntimeError('NO_SANDBOX: {} not found; third-party code never runs unsandboxed'.format(sandbox))
    dest = fetch(job, url, commit, subdir)
    tmp = job / '.third_party_tmp'
    tmp.mkdir(exist_ok=True)
    env = dict(os.environ, TMPDIR=str(tmp), HOME=str(tmp), PYTHONDONTWRITEBYTECODE='1')
    prof = profile(job)
    r = subprocess.run([sandbox, '-p', prof, *cmd], cwd=dest, env=env, timeout=timeout, stdout=stdout, stderr=stderr)
    row = dict(utc=now(), url=url, commit=commit, dir=str(dest.relative_to(job)), command=cmd, rc=r.returncode,
               sandbox='sandbox-exec: no network, writes only ' + str(job),
               profile_sha256=hashlib.sha256(prof.encode()).hexdigest())
    with open(job / RECEIPTS, 'a') as f:
        f.write(json.dumps(row) + '\n')
    return r.returncode


def _rows(path):
    out = []
    try:
        lines = Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def code_url(url):
    p = urlparse(str(url or ''))
    return p.hostname in CODE_HOSTS and Path(p.path).suffix.lower() in CODE_EXT and (
        p.hostname != 'github.com' or '/blob/' in p.path or '/raw/' in p.path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(job):
    """Errors for third-party code in JOB that did not come through `run` (empty list = clean)."""
    job = Path(job)
    errors = []
    if not job.is_dir():
        return errors
    tp = job / DIR
    receipted = {r.get('dir') for r in _rows(job / RECEIPTS)}
    if tp.is_dir():
        for d in sorted(p for p in tp.iterdir() if p.is_dir()):
            if str(d.relative_to(job)) not in receipted:
                errors.append('THIRD_PARTY_UNRECEIPTED: {} has no row in {}; fetch and run it with '
                              'third_party.py run'.format(d.relative_to(job), RECEIPTS))
    for g in job.rglob('.git'):
        rel = g.parent.relative_to(job)
        if not rel.parts or rel.parts[0] != DIR:
            errors.append('CHECKOUT_OUTSIDE_SANDBOX: git checkout at {}; third-party code runs only through '
                          'third_party.py run (pinned commit, no network, writes only the job dir)'.format(rel or '.'))
    fetched = {}
    for row in _rows(job / 'sources.jsonl'):
        name = row.get('name')
        if code_url(row.get('url')) and isinstance(name, str) and (job / name).is_file():
            fetched[sha(job / name)] = row['url']
    if fetched:
        for f in job.rglob('*'):
            rel = f.relative_to(job)
            if (rel.parts[0] == DIR or '.git' in rel.parts or not f.is_file() or f.is_symlink()
                    or f.suffix.lower() not in CODE_EXT or f.stat().st_size > 50_000_000):
                continue
            digest = sha(f)
            if digest in fetched:
                errors.append('FETCHED_CODE_RUNNABLE: {} is {} as downloaded; keep fetched code as data ({}.txt) '
                              'and run it only with third_party.py run --url ... --commit <sha>'.format(
                                  rel, fetched[digest], f.name))
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--workdir', required=True, type=Path)
    r.add_argument('--url', required=True)
    r.add_argument('--commit', required=True)
    r.add_argument('--subdir')
    r.add_argument('--timeout', type=float)
    r.add_argument('argv', nargs=argparse.REMAINDER)
    c = sub.add_parser('check')
    c.add_argument('workdir', type=Path)
    a = p.parse_args(argv)
    if a.cmd == 'check':
        errs = check(a.workdir)
        print('\n'.join(errs) or 'THIRD-PARTY-OK')
        return 1 if errs else 0
    cmd = a.argv[1:] if a.argv[:1] == ['--'] else a.argv
    try:
        return run(a.workdir, a.url, a.commit, cmd, a.subdir, a.timeout)
    except (ValueError, RuntimeError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
