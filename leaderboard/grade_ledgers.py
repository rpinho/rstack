#!/usr/bin/env python3
"""The everyday grade ledgers the model scorer reads (11-20).

Each Mac owns its ledgers: worker_models.py --grade writes everyday-grades.jsonl beside the job's launch
receipt. Another Mac's ledgers reach the scorer only as read-only mirror copies (grades-mirror.sh), never
merged into a local ledger. RH_EVERYDAY_GRADES lists every ledger to read: colon-separated paths or globs,
from the environment or the host env file. Unset, it is the one ledger beside RH_LAUNCH_RECEIPTS, as before.

Receipts: a ledger named everyday-grades.jsonl has its launch receipts beside it. A mirrored ledger
<dir>/<slug>.jsonl has them in <dir>/<slug>.receipts/ (the *.selection.json files and log-mtimes.tsv,
the job logs' last-write times, since the logs themselves are not copied).

Union: one row per grade id, the last one read, except that an "ungraded" row never replaces a grade.
A retraction (grade=retracted) in any ledger retracts that id in every ledger. RULE #1: a missing or
unreadable file is skipped, never raised; `grade_ledgers.py check` warns once per scorer tick about a
configured ledger that is missing or a mirror that has not synced for STALE_HOURS, and always exits 0.
"""
import glob
import json
import os
from pathlib import Path
import sys
import time

NAME = 'everyday-grades.jsonl'
MANIFEST = 'log-mtimes.tsv'     # "<mtime seconds>\t<file name>" per job log, written by the mirror
STAMP = '.synced'               # touched by the mirror after every complete sync
STALE_HOURS = 2.0               # the mirror runs every 10 minutes
KEY = 'RH_EVERYDAY_GRADES'


def _env_file():
    explicit = os.environ.get('RH_ENV_FILE')
    if explicit:
        return Path(explicit).expanduser()
    config = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(config).expanduser() / 'research-harness/env'


def configured():
    """RH_EVERYDAY_GRADES from the environment, else from the host env file (only this key is read)."""
    if KEY in os.environ:
        return os.environ[KEY]
    try:
        text = _env_file().read_text()
    except OSError:
        return ''
    value = ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        key, sep, rest = line.partition('=')
        if sep and key.strip() == KEY:
            rest = rest.strip()
            if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in '\'"':
                rest = rest[1:-1]
            value = rest
    return value


def _parts(spec):
    return [p.strip() for p in spec.split(':') if p.strip()]


def _expand(part):
    pattern = os.path.expanduser(part)
    return [Path(m) for m in sorted(glob.glob(pattern))] if glob.has_magic(pattern) else [Path(pattern)]


def ledgers(receipts=None, spec=None):
    """[Path] of the ledgers to read, in order. Paths that do not exist are kept (reading skips them)."""
    spec = configured() if spec is None else spec
    if not spec:
        return [Path(receipts) / NAME] if receipts else []
    out, seen = [], set()
    for part in _parts(spec):
        for path in _expand(part):
            try:
                key = path.resolve()
            except OSError:
                key = path
            if key not in seen:     # one file reached twice (a symlinked directory) is read once
                seen.add(key)
                out.append(path)
    return out


def receipts_dir(ledger):
    """The directory holding the launch receipts a ledger's grades name."""
    ledger = Path(ledger)
    return ledger.parent if ledger.name == NAME else ledger.with_name(ledger.stem + '.receipts')


def _grade(row):
    return str(row.get('grade')).lower()


def rows(paths):
    """[(row, path, line number)] of the active everyday grade rows across every ledger: one per grade id,
    every retracted id left out. Never raises."""
    read = []
    for path in paths:
        try:
            text = Path(path).read_text(errors='replace')
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('source_kind') == 'everyday':
                read.append((row, Path(path), number))
    retracted = {r.get('id') for r, _, _ in read if r.get('id') and _grade(r) == 'retracted'}
    best = {}
    for row, path, number in read:
        if _grade(row) == 'retracted' or row.get('id') in retracted:
            continue
        key = row.get('id') or (str(path), number)
        old = best.get(key)
        if old and _grade(row) == 'ungraded' and _grade(old[0]) != 'ungraded':
            continue
        best[key] = (row, path, number)
    return list(best.values())


def log_mtimes(directory):
    """{file name: mtime} from a mirror's manifest; {} when there is none."""
    out = {}
    try:
        text = (Path(directory) / MANIFEST).read_text(errors='replace')
    except OSError:
        return out
    for line in text.splitlines():
        stamp, sep, name = line.partition('\t')
        name = name[2:] if name.startswith('./') else name
        try:
            if sep and name:
                out[name] = float(stamp)
        except ValueError:
            continue
    return out


def problems(spec=None, now=None, stale_hours=STALE_HOURS):
    """Plain-language problems with the configured ledgers: missing files and stale mirrors."""
    spec = configured() if spec is None else spec
    if not spec:
        return []
    now = time.time() if now is None else now
    out, stamps = [], []
    for part in _parts(spec):
        found = [p for p in _expand(part) if p.is_file()]
        if not found:
            out.append('no everyday grade ledger at {} (RH_EVERYDAY_GRADES); the scorer reads the others'.format(part))
        for path in found:
            if (path.parent / STAMP).exists() and path.parent not in stamps:
                stamps.append(path.parent)
    for directory in stamps:
        try:
            age = (now - (directory / STAMP).stat().st_mtime) / 3600
        except OSError:
            continue
        if age > stale_hours:
            out.append('grade mirror {} last synced {:.1f} h ago; the scorer reads the copy it has'.format(directory, age))
    return out


def warn(text):
    fix = 'run leaderboard/grades-mirror.sh (or its LaunchAgent) and read its log'
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'harness'))
        import harness_blocks
        harness_blocks.warn('grades-mirror', text, fix=fix)
    except Exception:
        print('[grades-mirror] WARNING (fail-open, the work continues): ' + text, file=sys.stderr)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ['check']:
        print('usage: grade_ledgers.py check', file=sys.stderr)
        return 2
    try:
        found = problems()
    except Exception as exc:        # never in the way
        found = ['grade ledger check failed ({})'.format(type(exc).__name__)]
    for text in found:
        warn(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
