#!/usr/bin/env python3
"""A published baseline a lane can RUN, not a number it quoted from a paper.

Why (2026-11-06, harness plan item 6, the Paper2Agent idea). Every lane here starts by finding
prior art and writing down what the best published number is. Then it spends weeks comparing
against that number as a string in a spec. Three things went wrong because of it:

  - planets reported four candidates, three of which were already in public community tables. The
    prior art had been found and read; it had never been RUN against our own targets.
  - c5 spent about 38 rounds in a method family after the KB already named a better one. Nothing
    could tell it that the family's published baseline was reachable in one command.
  - a quoted baseline silently rots. A dependency changes, the published script stops giving the
    published number, and the comparison we have been making for a month is against a number
    nothing on this machine can still produce.

So: a baseline is registered only if it REPRODUCES. `baseline add` runs the command, extracts the
number, and refuses to record anything unless it matches what the source published, within a
stated tolerance. That refusal is the feature. A lane cannot write down a baseline it has not
reproduced, which is the same rule as "the producer never grades itself" applied to prior art.

Afterwards any round can run it:

    baseline.py run --lane math --name orloski-2020     -> the published number, reproduced today
    baseline.py check --lane math                       -> every baseline, re-run; non-zero on drift

`check` is what makes it a tested tool rather than a cached number: when a baseline stops
reproducing, the lane hears about it instead of comparing against a fiction.

No network. The command is the lane's own; this module only runs it, reads a number out, and
remembers whether it matched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the harness, for settings
import settings

BASELINES = 'BASELINES.jsonl'
NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
DEFAULT_TOLERANCE = 1e-9
DEFAULT_TIMEOUT = 1800


def read(path):
    """Rows in file order, latest row per name winning; a corrupt line is skipped."""
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


def extract(text, json_key=None):
    """The number this run produced.

    With --json-key, the last JSON object on stdout must carry it; otherwise the LAST number in
    the output. Last, not first, because a script prints its progress before its answer.
    """
    if json_key:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith('{'):
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if json_key in data:
                    return float(data[json_key])
        raise ValueError('no JSON object on stdout carried the key ' + json_key)
    found = NUMBER.findall(text)
    if not found:
        raise ValueError('the command printed no number')
    return float(found[-1])


def dig(data, dotted):
    """Walk a dotted path, integers indexing lists: `candidates.0.period`."""
    node = data
    for part in dotted.split('.'):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                raise ValueError('no "{}" at {} (list of {})'.format(part, dotted, len(node)))
        elif isinstance(node, dict):
            if part not in node:
                raise ValueError('no key "{}" at {}; keys: {}'.format(
                    part, dotted, ', '.join(sorted(node)[:8])))
            node = node[part]
        else:
            raise ValueError('cannot descend into {} at "{}"'.format(type(node).__name__, part))
    return node


def published_from(spec, cwd=None):
    """FILE:dotted.path -> (value, path, sha256).

    planets asked for this (11-06) so a frozen table snapshot supplies its own known-good value
    instead of someone typing it in. A typed number is exactly what this module exists to replace,
    so taking it from the receipt is not a convenience, it is the same rule applied one level up.
    Accepts a JSON document or a JSONL file, where the last line that parses as an object is used.
    """
    path_part, _, key = spec.rpartition(':')
    if not path_part or not key:
        raise ValueError('--published-from wants FILE:dotted.path, got ' + spec)
    path = Path(os.path.expanduser(path_part))
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    raw = path.read_bytes()
    text = raw.decode('utf-8', 'replace')
    try:
        data = json.loads(text)
    except ValueError:
        data = None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    data = json.loads(line)
                    break
                except ValueError:
                    continue
        if data is None:
            raise ValueError('{} is neither JSON nor JSONL'.format(path))
    value = dig(data, key)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('{} is {}, not a number'.format(key, type(value).__name__))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError('{} is "{}", which is not a number'.format(key, value))
    return number, str(path), hashlib.sha256(raw).hexdigest()[:16]


def run_command(cmd, cwd=None, timeout=DEFAULT_TIMEOUT):
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def close_enough(got, published, tolerance, higher_is_better=None):
    """Within tolerance, or better than published in the stated direction.

    A reproduction that comes out BETTER than the paper is still a reproduction of the method, and
    refusing it would be the harness telling a lane its own improvement is a failure.
    """
    if abs(got - published) <= tolerance:
        return True
    if higher_is_better is True:
        return got > published
    if higher_is_better is False:
        return got < published
    return False


def reproduce(row, cwd=None):
    """-> (ok, value, detail). Runs the stored command and compares."""
    try:
        code, out, err = run_command(row['cmd'], cwd, row.get('timeout', DEFAULT_TIMEOUT))
    except subprocess.TimeoutExpired:
        return False, None, 'timed out after {}s'.format(row.get('timeout', DEFAULT_TIMEOUT))
    if code != 0:
        return False, None, 'command exited {}: {}'.format(code, (err or out).strip()[-200:])
    try:
        value = extract(out, row.get('json_key'))
    except ValueError as exc:
        return False, None, str(exc)
    ok = close_enough(value, row['published'], row.get('tolerance', DEFAULT_TOLERANCE),
                      row.get('higher_is_better'))
    detail = ('{} vs published {}'.format(value, row['published']) if ok else
              'got {}, published {}, tolerance {}'.format(value, row['published'],
                                                          row.get('tolerance', DEFAULT_TOLERANCE)))
    return ok, value, detail


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--lane', required=True, type=Path, help='the lane directory')
    p.add_argument('--cwd', type=Path, help='where to run the command (default: the lane dir)')
    sub = p.add_subparsers(dest='action', required=True)

    add = sub.add_parser('add', help='register a baseline, only if it reproduces')
    add.add_argument('--name', required=True)
    add.add_argument('--source', required=True, help='DOI, URL or citation the number comes from')
    add.add_argument('--published', type=float, help='the number the source reports')
    add.add_argument('--published-from', dest='pub_from', default='',
                     help='FILE:dotted.path -- take the number from a snapshot receipt instead of '
                          'typing it; the file is hashed, and a later change to it is reported')
    add.add_argument('--cmd', required=True, help='the command that reproduces it')
    add.add_argument('--metric', default='', help='what the number is (AUROC, bound, days)')
    add.add_argument('--tolerance', type=float, default=DEFAULT_TOLERANCE)
    add.add_argument('--json-key', default='', help='read the number from this key of a JSON line')
    add.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    add.add_argument('--tag', action='append', default=[],
                     help='label for filtering `check`, e.g. slow; repeatable')
    add.add_argument('--higher-is-better', dest='hib', action='store_true', default=None)
    add.add_argument('--lower-is-better', dest='hib', action='store_false')

    one = sub.add_parser('run', help='re-run one baseline and print its number')
    one.add_argument('--name', required=True)

    chk = sub.add_parser('check', help='re-run every baseline; non-zero if any stopped reproducing')
    chk.add_argument('--tag', action='append', default=[], help='only baselines with this tag')
    chk.add_argument('--skip-tag', action='append', default=[],
                     help='leave these out; math asked for it because one C86 check takes 5 min')
    sub.add_parser('list', help='what this lane can reproduce')

    a = p.parse_args(argv)

    # A bare lane name resolves under RH_ROOT/lanes, and a directory that is not a lane

    # is refused. One resolver for every tool that takes --lane: all four took it as a

    # bare path, and planets hit the trap on 11-07.

    try:

        a.lane = settings.lane_dir(a.lane)

    except ValueError as exc:

        print('REFUSED: ' + str(exc), file=sys.stderr)

        return 2
    ledger = a.lane / BASELINES
    rows = read(ledger)
    cwd = a.cwd or a.lane

    if a.action == 'add':
        pub, pub_src = a.published, None
        if a.pub_from:
            if a.published is not None:
                print('REFUSED: give --published or --published-from, not both', file=sys.stderr)
                return 2
            try:
                pub, path, digest = published_from(a.pub_from, cwd)
            except (OSError, ValueError) as exc:
                print('REFUSED: --published-from: {}'.format(exc), file=sys.stderr)
                return 2
            pub_src = dict(spec=a.pub_from, path=path, sha256=digest, value=pub)
        if pub is None:
            print('REFUSED: one of --published or --published-from is required', file=sys.stderr)
            return 2
        row = dict(name=a.name, source=a.source, published=pub, published_src=pub_src, cmd=a.cmd,
                   metric=a.metric, tolerance=a.tolerance, timeout=a.timeout,
                   json_key=a.json_key or None, higher_is_better=a.hib, tags=sorted(set(a.tag)),
                   cmd_sha256=hashlib.sha256(a.cmd.encode()).hexdigest()[:16])
        ok, value, detail = reproduce(row, cwd)
        if not ok:
            print('REFUSED: "{}" did not reproduce its published number: {}.\n'
                  'A baseline is only worth having if this machine can produce it. Fix the command '
                  'or the tolerance, or record honestly that the published result does not '
                  'reproduce, which is itself a finding worth sending.'.format(a.name, detail),
                  file=sys.stderr)
            return 2
        row.update(first_reproduced_utc=now(), last_ok_utc=now(), value=value)
        append(ledger, row)
        print('{} reproduces: {}'.format(a.name, detail))
        return 0

    if a.action == 'list':
        if not rows:
            print('no baselines yet. Register one with `baseline.py --lane L add`.')
            return 0
        for name, row in sorted(rows.items()):
            tags = ' '.join(row.get('tags') or [])
            print('{:28} {:<16} {}  [{}]{}'.format(name, row.get('metric') or '-',
                                                   row['published'], row.get('source', '')[:60],
                                                   '  tags: ' + tags if tags else ''))
        return 0

    if a.action == 'run' and a.name not in rows:
        print('no baseline called "{}" in {}'.format(a.name, ledger), file=sys.stderr)
        return 2
    targets = [rows[a.name]] if a.action == 'run' else sorted(rows.values(), key=lambda r: r['name'])
    if a.action == 'check':
        # A `run --name` is always honoured; only `check` filters, so a slow baseline can be
        # excluded from the routine pass without becoming unreachable.
        want, skip = set(a.tag or []), set(a.skip_tag or [])
        chosen = []
        for row in targets:
            tags = set(row.get('tags') or [])
            if want and not (tags & want):
                continue
            if tags & skip:
                print('{:28} skip     tags: {}'.format(row['name'], ' '.join(sorted(tags & skip))))
                continue
            chosen.append(row)
        targets = chosen
    if not targets:
        print('no baselines registered for this lane', file=sys.stderr)
        return 0

    failed = []
    for row in targets:
        src = row.get('published_src')
        if src:
            # The snapshot is authoritative, so if it has moved, the baseline has to be
            # re-registered rather than quietly compared against the new number. Loud, not silent:
            # moving the goalposts inside a `check` is how a comparison stops meaning anything.
            try:
                nowval, _, digest = published_from(src['spec'], cwd)
            except (OSError, ValueError) as exc:
                print('{:28} SOURCE  cannot re-read {}: {}'.format(row['name'], src['spec'], exc))
                failed.append(row['name'])
                continue
            if nowval != src.get('value') or digest != src.get('sha256'):
                print('{:28} SOURCE  {} changed: published was {}, now {}'.format(
                    row['name'], src['spec'], src.get('value'), nowval))
                failed.append(row['name'])
                continue
        ok, value, detail = reproduce(row, cwd)
        print('{:28} {}  {}'.format(row['name'], 'ok  ' if ok else 'DRIFT', detail))
        if ok:
            append(ledger, dict(row, last_ok_utc=now(), value=value))
        else:
            failed.append(row['name'])
    if failed:
        print('REFUSED: {} baseline(s) stopped reproducing: {}. Every comparison a round made '
              'against them since the last check is against a number nothing here can produce. '
              'Fix the command or re-register with the number it now gives, and say which in the '
              'lane log.'.format(len(failed), ', '.join(failed)), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
