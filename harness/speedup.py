"""Speedups to someone's research code, verified before anyone is told about them.

Ricardo, 11-08: "not only find bugs in their code but also try to make them more efficient." A
speedup is only worth sending if it gives the same answers, on their latest code, by a margin they
would notice, from a hot spot that was measured rather than guessed. Each is checked here.

    rh bughunt speedup-verify LANE DIR

DIR holds SPEEDUP.json:

    {"target": "owner/repo",          the repository, as checked by rh bughunt target-check
     "repo": "/path/to/a/clone",      a local git clone of it
     "base": "<commit sha>",          their commit the patch applies to (their latest, when sent)
     "patch": "speedup.patch",        the change, relative to DIR
     "command": "...",                shell command run in each checkout; writes the outputs
     "outputs": ["out/result.csv"],   files the command writes, relative to the checkout
     "tolerance": null,               null: byte-identical; or {"rel": 1e-9, "abs": 0}
     "runs": 5,                       timed runs of each version, alternated
     "profile": "profile.txt",        the profile that found the hot spot, relative to DIR
     "hotspot": "f() 72% of 41 s"}    the hot spot, with its numbers

The verifier fetches `base` twice through tools/third_party.py (a pinned commit, into a scratch job
dir), applies the patch to one, runs the command in both `runs` times (alternating, so drift hits
both) with `third_party.py run`: sandbox-exec, no network, writes only the scratch job dir. It
compares every output and writes VERIFY.json: the verdict, every failure code, median wall time and
peak memory of each version, the speedup, the host, the hashes of the manifest and patch it
verified, and the third_party receipt rows of every run. There is no unsandboxed fallback (11-20:
it used to run their code in plain git worktrees with full network and write access). It refuses
to run where RH_NO_LOCAL_COMPUTE=1 (a controller that must not run other people's code at size).

Failure codes: SPEEDUP_PROFILE_MISSING, SPEEDUP_PATCH_FAILS, SPEEDUP_RUN_FAILED,
SPEEDUP_OUTPUT_MISMATCH, SPEEDUP_TOO_SMALL (under `speedup_min_ratio`, default 1.5, or saving
under `speedup_min_seconds`, default 1.0). `rh outreach lint` reads VERIFY.json for every
code-speedup email: SPEEDUP_UNVERIFIED, SPEEDUP_STALE (the patch or manifest changed since),
SPEEDUP_STALE_BASE (their code moved on), SPEEDUP_OVERLAP (they have open work on speed).
"""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import storage

UTC = dt.timezone.utc
FIELDS = ('target', 'repo', 'base', 'patch', 'command', 'outputs', 'runs', 'profile', 'hotspot')
# The child's peak resident memory and wall time, read by a tiny wrapper inside the sandbox so they are
# per run and per version, and the sandbox's own start-up is not timed.
PEAK = ('import resource, subprocess, sys, time\n'
        't = time.perf_counter()\n'
        'rc = subprocess.run(sys.argv[1], shell=True).returncode\n'
        'wall = time.perf_counter() - t\n'
        'peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n'
        'print("RH_PEAK", peak * (1 if sys.platform == "darwin" else 1024), wall, file=sys.stderr)\n'
        'sys.exit(rc)\n')
THIRD_PARTY_TOOL = Path(__file__).resolve().parent / 'tools' / 'third_party.py'


def third_party():
    spec = importlib.util.spec_from_file_location('rh_third_party', THIRD_PARTY_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NUMBER = re.compile(r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$')


def defaults():
    return dict(speedup_min_ratio=1.5, speedup_min_seconds=1.0)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(directory):
    path = Path(directory) / 'SPEEDUP.json'
    data = json.loads(path.read_text())
    missing = [f for f in FIELDS if f not in data]
    if missing:
        raise ValueError('SPEEDUP.json is missing ' + ', '.join(missing))
    if type(data['runs']) is not int or data['runs'] < 3:
        raise ValueError('SPEEDUP.json runs must be 3 or more')
    if not isinstance(data['outputs'], list) or not data['outputs']:
        raise ValueError('SPEEDUP.json outputs must name at least one file')
    tol = data.get('tolerance')
    if tol is not None and (not isinstance(tol, dict) or set(tol) - {'rel', 'abs'}):
        raise ValueError('SPEEDUP.json tolerance is null or {"rel": R, "abs": A}')
    return data


def same(left, right, tolerance):
    """True when two output files agree: byte-identical, or token by token within tolerance."""
    a, b = Path(left).read_bytes(), Path(right).read_bytes()
    if a == b:
        return True
    if tolerance is None:
        return False
    ta = re.split(r'[\s,;]+', a.decode('utf-8', errors='replace').strip())
    tb = re.split(r'[\s,;]+', b.decode('utf-8', errors='replace').strip())
    if len(ta) != len(tb):
        return False
    rel, abs_ = float(tolerance.get('rel', 0)), float(tolerance.get('abs', 0))
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if not (NUMBER.match(x) and NUMBER.match(y)):
            return False
        fx, fy = float(x), float(y)
        if abs(fx - fy) > max(abs_, rel * max(abs(fx), abs(fy))):
            return False
    return True


def timed(tp, job, repo, base, name, command, timeout):
    """Run COMMAND in JOB's NAME checkout of BASE through third_party.run: (rc, wall, peak, stderr tail)."""
    err_path = Path(job).parent / '{}.stderr'.format(name)
    start = time.perf_counter()
    with open(err_path, 'w') as err:
        rc = tp.run(job, repo, base, [sys.executable, '-c', PEAK, command], subdir=name, timeout=timeout,
                    stderr=err)
    wall = time.perf_counter() - start
    text = err_path.read_text(errors='replace')
    line = next((line.split() for line in text.splitlines() if line.startswith('RH_PEAK ')), None)
    peak = int(line[1]) if line else None
    if line and len(line) > 2:
        wall = float(line[2])
    return rc, wall, peak, text[-2000:]


def verify(directory, cfg=None, clock=None, timeout=6 * 3600):
    """Run the check and return the VERIFY.json row (also written to DIRECTORY)."""
    if os.environ.get('RH_NO_LOCAL_COMPUTE') == '1':
        raise ValueError('this machine is a controller (RH_NO_LOCAL_COMPUTE=1); run speedup-verify '
                         'on the compute host, as a job')
    tp = third_party()
    if not Path(tp.SANDBOX).exists():
        raise ValueError('NO_SANDBOX: {} not found; their code runs only through third_party.py run '
                         '(sandbox-exec, no network), never unsandboxed'.format(tp.SANDBOX))
    cfg = dict(defaults(), **(cfg or {}))
    directory = Path(directory).expanduser().resolve()
    data = manifest(directory)
    clock = clock or dt.datetime.now(UTC)
    patch = directory / data['patch']
    row = dict(utc=clock.isoformat(), host=platform.node(), target=data['target'], base=data['base'],
               manifest_sha256=sha(directory / 'SPEEDUP.json'), patch_sha256=sha(patch),
               hotspot=data['hotspot'], runs=data['runs'], codes=[])
    profile = directory / data['profile']
    if not profile.is_file() or not profile.stat().st_size or not re.search(r'\d', data['hotspot']):
        row['codes'].append('SPEEDUP_PROFILE_MISSING: profile on a representative input first, and '
                            'name the hot spot with its numbers')
    work = Path(tempfile.mkdtemp(prefix='rh-speedup-'))
    job = work / 'job'
    job.mkdir()
    # 11-20: Path() collapses 'https://' to 'https:/', so a URL failed tp.fetch before any run (open-source, CellularAI).
    repo = data['repo'] if '://' in str(data['repo']) else str(Path(data['repo']).expanduser())
    try:
        trees = {}
        try:
            for name in ('before', 'after'):
                trees[name] = tp.fetch(job, repo, data['base'], subdir=name)
        except (ValueError, RuntimeError) as error:
            row['codes'].append('SPEEDUP_PATCH_FAILS: their commit {} could not be checked out pinned: {}'.format(
                data['base'][:12], str(error)[:200]))
            return finish(directory, row)
        applied = subprocess.run(['git', '-C', str(trees['after']), 'apply', str(patch)],
                                 capture_output=True, text=True)
        if applied.returncode:
            row['codes'].append('SPEEDUP_PATCH_FAILS: the patch does not apply to {}: {}'.format(
                data['base'][:12], applied.stderr.strip()[:200]))
            return finish(directory, row)
        times = dict(before=[], after=[])
        peaks = dict(before=[], after=[])
        for _ in range(data['runs']):
            for name in ('before', 'after'):
                rc, wall, peak, err = timed(tp, job, repo, data['base'], name, data['command'], timeout)
                row['third_party'] = tp._rows(job / tp.RECEIPTS)
                if rc:
                    row['codes'].append('SPEEDUP_RUN_FAILED: the {} version exited {}: {}'.format(
                        name, rc, err.strip()[-200:]))
                    return finish(directory, row)
                times[name].append(wall)
                if peak is not None:
                    peaks[name].append(peak)
        kept = directory / 'outputs'
        mismatched = []
        for out in data['outputs']:
            a, b = trees['before'] / out, trees['after'] / out
            for name, path in (('before', a), ('after', b)):
                if path.is_file():
                    (kept / name / out).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, kept / name / out)
            if not (a.is_file() and b.is_file() and same(a, b, data.get('tolerance'))):
                mismatched.append(out)
        if mismatched:
            row['codes'].append('SPEEDUP_OUTPUT_MISMATCH: {} differ{} ({})'.format(
                ', '.join(mismatched), 's' if len(mismatched) == 1 else '',
                'byte-identical required' if data.get('tolerance') is None
                else 'tolerance {}'.format(data['tolerance'])))
        before, after = statistics.median(times['before']), statistics.median(times['after'])
        row.update(median_seconds=dict(before=round(before, 4), after=round(after, 4)),
                   peak_bytes=dict(before=max(peaks['before'], default=None),
                                   after=max(peaks['after'], default=None)),
                   speedup=round(before / after, 3) if after > 0 else None,
                   saving_seconds=round(before - after, 4))
        if (row['speedup'] or 0) < cfg['speedup_min_ratio'] or row['saving_seconds'] < cfg['speedup_min_seconds']:
            row['codes'].append('SPEEDUP_TOO_SMALL: {}x and {:.2f} s saved (needs {}x and {} s)'.format(
                row['speedup'], row['saving_seconds'], cfg['speedup_min_ratio'], cfg['speedup_min_seconds']))
        return finish(directory, row)
    finally:
        # The checkouts were fetched into the scratch dir; it goes to the Trash, never a recursive
        # delete (harness rule: reversible disposal only).
        try:
            storage.trash(work)
        except (OSError, subprocess.SubprocessError):
            pass


def finish(directory, row):
    row['verdict'] = 'FAIL' if row['codes'] else 'PASS'
    (Path(directory) / 'VERIFY.json').write_text(json.dumps(row, indent=2) + '\n')
    return row


def current(directory):
    """(VERIFY row, problem) for a speedup directory as it stands now."""
    directory = Path(directory)
    try:
        row = json.loads((directory / 'VERIFY.json').read_text())
    except (OSError, ValueError):
        return None, 'SPEEDUP_UNVERIFIED: {} has no VERIFY.json; run rh bughunt speedup-verify'.format(directory)
    if row.get('verdict') != 'PASS':
        return row, 'SPEEDUP_UNVERIFIED: {} failed verification: {}'.format(
            directory, '; '.join(c.split(':')[0] for c in row.get('codes', [])))
    try:
        data = manifest(directory)
        if sha(directory / 'SPEEDUP.json') != row['manifest_sha256'] or \
                sha(directory / data['patch']) != row['patch_sha256']:
            return row, 'SPEEDUP_STALE: {} changed since it was verified; verify again'.format(directory)
    except (OSError, ValueError, KeyError) as error:
        return row, 'SPEEDUP_STALE: {}: {}'.format(directory, error)
    return row, None


def patch_hashes(path):
    """sha256 of every .diff/.patch in PATH: the file itself, or the members of a tar or zip."""
    import tarfile
    import zipfile
    path = Path(path)
    is_patch = lambda name: name.endswith(('.diff', '.patch'))
    if is_patch(path.name):
        return {sha(path)}
    found = set()
    try:
        if tarfile.is_tarfile(str(path)):
            with tarfile.open(str(path)) as bundle:
                for member in bundle.getmembers():
                    if member.isfile() and is_patch(member.name):
                        found.add(hashlib.sha256(bundle.extractfile(member).read()).hexdigest())
        elif zipfile.is_zipfile(str(path)):
            with zipfile.ZipFile(str(path)) as bundle:
                for name in bundle.namelist():
                    if is_patch(name):
                        found.add(hashlib.sha256(bundle.read(name)).hexdigest())
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        return set()
    return found


def covered_attachments(row):
    """Attachments that are a verified speedup's own patch (alone or bundled with its scripts).

    11-08: the patch bundle a recipient asked for went through the paper-result checks (adversarial
    reviews, the useful-or-slop question), which are for claims about results. A patch whose bytes
    are the ones VERIFY.json passed is already checked by its equality test and benchmark. Only an
    exact hash match counts, and every patch in a bundle must be one: a bundle that also carries
    other patches (bug fixes, say) is not covered by a speedup's verification and is checked whole.
    Anything else in the email still goes through the science check.
    """
    verified = set()
    for d in row.get('speedups', []):
        result, problem = current(d)
        if result and not problem:
            verified.add(result['patch_sha256'])
    if not verified:
        return []
    covered = []
    for a in row.get('attachments', []):
        found = patch_hashes(a)
        if found and found <= verified:
            covered.append(a)
    return covered


def findings(row, contact, lane, rh, latest_verdict, extra_needed):
    """(failures, warnings, independent PASS count) for a code-speedup email."""
    failures, warnings, good = [], [], {}
    dirs = row.get('speedups', [])
    if not dirs:
        return ['SPEEDUP_UNVERIFIED: a code-speedup email names its verified speedup with --speedup DIR'], [], 0
    for d in dirs:
        verified, problem = current(d)
        if problem:
            failures.append(problem)
            continue
        good.setdefault(verified['patch_sha256'], set()).add(str(Path(d).resolve()))
        verdict = latest_verdict(lane, rh, verified['target'])
        head = ((verdict or {}).get('numbers') or {}).get('last_commit_sha')
        if not head:
            failures.append('SPEEDUP_STALE_BASE: no target-check with a commit for {}; run rh bughunt '
                            'target-check'.format(verified['target']))
        elif head != verified['base']:
            failures.append('SPEEDUP_STALE_BASE: {} verified on {} but their latest commit is {}; '
                            'rebase the patch and verify again'.format(d, verified['base'][:12], head[:12]))
        busy = ((verdict or {}).get('numbers') or {}).get('optimizing') or []
        if busy and not row.get('overlap_checked'):
            failures.append('SPEEDUP_OVERLAP: {} already has work on speed ({}); check with them first '
                            'and say so with --overlap-checked'.format(verified['target'], '; '.join(busy[:3])))
        elif busy:
            warnings.append('their own speed work: {} (checked: {})'.format('; '.join(busy[:3]),
                                                                          row['overlap_checked']))
    count = max((len(v) for v in good.values()), default=0)
    return failures, warnings, count
