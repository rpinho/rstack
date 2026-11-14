#!/usr/bin/env python3
"""Keep the always-reloaded KB files free of your own projects' working detail.

Why: state.md, index.md and goals.md are re-read at session start AND after every compaction.
When a project's working detail lands in one of them, every general-purpose session inherits it on
every wake, and compacting does not help: the summary is rebuilt from files that put it straight
back. In the KB this comes from, an index entry for a postmortem carried a sensitive project's
identifiers, raw data and scores in one table cell; the general session tripped a safety
classifier three times in one evening until the line was found. It was then fixed by hand, which
is prose: nothing stopped the next entry. This lint, run from pre-commit check 8, is that nothing.

The judgment, and the reason it is not a word list: the vocabulary ALONE is fine. An index may
mention a field's published work, and the same words turn up on unrelated pages. What is never
right in these files is a term NEXT TO your own working detail (run ids, score fields, size
ranges: whatever your markers describe). So a line is blocked only on the CO-OCCURRENCE of a term
and a marker, plus any `standalone` pattern you mark as never right on its own.

The KB ships NO terms and NO markers: a list of them would itself describe what you work on.
Supply a file with --terms or $KB_CONTEXT_TERMS (else $RSTACK_TERMS_FILE, so one file serves this
and rstack's reload-lint). Format, one entry per line, `#` comments:

    projectcodename                          a term (case-insensitive, word-bounded)
    marker run id = \\brun-\\d{3}\\b           working detail that makes a nearby term a problem
    standalone raw dump = \\bDUMP-\\d{6}\\b    never right in a reloaded file, term or not

No file: nothing is checked, and it says so. A configured file that cannot be read blocks: a lint
that silently stopped checking is the failure it exists to prevent. The output names files, lines,
marker labels and a COUNT of matched terms, never the terms or the line, because it lands in the
same session context the lint protects.

Usage:
    context-hygiene-lint.py            # staged additions only (the pre-commit path)
    context-hygiene-lint.py --all      # audit the whole of each guarded file
    context-hygiene-lint.py --files a.md b.md
Exit 0 = clean, 1 = blocked.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

GUARDED = ['state.md', 'index.md', 'goals.md']


class Unreadable(Exception):
    pass


def terms_path(explicit=None):
    value = explicit or os.environ.get('KB_CONTEXT_TERMS') or os.environ.get('RSTACK_TERMS_FILE')
    return Path(value).expanduser() if value else None


def labelled(rest, path, n):
    label, sep, rx = rest.partition(' = ')
    if not sep or not label.strip() or not rx.strip():
        raise Unreadable('{}:{}: expected "KIND LABEL = REGEX"'.format(path, n))
    try:
        return label.strip(), re.compile(rx.strip(), re.I)
    except re.error:
        raise Unreadable('{}:{}: bad regex'.format(path, n))


def load(path):
    """(terms, markers, standalone): lists of compiled patterns (markers and standalone labelled)."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        raise Unreadable('{}: cannot be read'.format(path))
    terms, markers, standalone = [], [], []
    for n, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith('#'):
            continue
        head, _, rest = entry.partition(' ')
        if head == 'marker':
            markers.append(labelled(rest, path, n))
        elif head == 'standalone':
            standalone.append(labelled(rest, path, n))
        else:
            left = r'\b' if entry[:1].isalnum() else ''
            right = r'\b' if entry[-1:].isalnum() else ''
            terms.append(re.compile(left + re.escape(entry) + right, re.I))
    return terms, markers, standalone


def check_line(line, terms, markers, standalone):
    """Reasons this line may not go in a guarded file. Never includes the terms themselves."""
    reasons = []
    count = sum(1 for rx in terms if rx.search(line))
    fired = [label for label, rx in markers if rx.search(line)]
    if count and fired:
        reasons.append('{} withheld term(s) next to your own working detail ({})'.format(count, ', '.join(fired)))
    reasons += ['standalone: {}'.format(label) for label, rx in standalone if rx.search(line)]
    return reasons


def staged_additions(paths):
    """(file, line number in the new file, text) for every added line in the staged diff."""
    diff = subprocess.run(['git', 'diff', '--cached', '--unified=0', '--'] + paths,
                          capture_output=True, text=True, check=True).stdout
    out, cur, lineno = [], None, 0
    for line in diff.splitlines():
        if line.startswith('+++ '):
            cur = line[6:] if line.startswith('+++ b/') else None
        elif line.startswith('@@'):
            mo = re.search(r'\+(\d+)', line)
            lineno = int(mo.group(1)) if mo else 0
        elif line.startswith('+') and cur:
            out.append((cur, lineno, line[1:]))
            lineno += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--all', action='store_true', help='audit whole files, not staged additions')
    ap.add_argument('--files', nargs='*', help='audit these files instead of the guarded list')
    ap.add_argument('--terms', help='terms file (default $KB_CONTEXT_TERMS, else $RSTACK_TERMS_FILE)')
    args = ap.parse_args(argv)
    path = terms_path(args.terms)
    if path is None:
        print('context-hygiene-lint: no terms file configured (--terms or KB_CONTEXT_TERMS); nothing checked.',
              file=sys.stderr)
        return 0
    try:
        terms, markers, standalone = load(path)
    except Unreadable as e:
        print('context-hygiene-lint: BLOCKED, the configured terms file is unusable ({}). Fix it, or unset '
              'KB_CONTEXT_TERMS to stop checking on purpose.'.format(e), file=sys.stderr)
        return 1
    files = args.files or GUARDED
    if args.all or args.files:
        rows = [(f, i, line) for f in files if Path(f).exists()
                for i, line in enumerate(Path(f).read_text(encoding='utf-8').splitlines(), 1)]
    else:
        rows = staged_additions(files)
    findings = [(f, i, r) for f, i, line in rows for r in check_line(line, terms, markers, standalone)]
    if not findings:
        return 0
    print('BLOCKED: working detail in a file every session reloads.\n', file=sys.stderr)
    for f, i, reason in findings[:20]:
        print('  {}:{}  {}'.format(f, i, reason), file=sys.stderr)
    if len(findings) > 20:
        print('  ... and {} more'.format(len(findings) - 20), file=sys.stderr)
    print('\nThese files are re-read at session start and after every compaction. Keep the summary-level '
          'fact here and the detail in the project\'s own repo or its postmortem; link to it.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
