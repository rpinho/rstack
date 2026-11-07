#!/usr/bin/env python3
"""Keep the files every session reloads free of your own working detail.

Why: some files are re-read at session start AND after every compaction (a CLAUDE.md, an index, a
state file). When a project's working detail gets written into one of them, every general-purpose
session inherits it on every wake, and compacting does not help: the summary is rebuilt from files
that put it straight back. In the setup this came from, an index entry for a postmortem carried a
sensitive project's working detail (identifiers, scores, raw data) in a single table cell; the
conductor session tripped a safety classifier and stalled repeatedly until the line was found. It
was then fixed BY HAND, which is prose: nothing stopped the next entry doing the same. This lint
is that nothing, run from a pre-commit hook.

The judgment it encodes, and the reason it is not a word list: the vocabulary ALONE is fine. An
index may legitimately mention a field's published work, and the same words appear in unrelated
pages. Blocking those words would wreck real content. What is never right in a reloaded file is a
term NEXT TO your own working detail: run IDs, score deltas, size ranges, whatever your markers
describe. So a line is blocked only on the CO-OCCURRENCE of a term and a marker, plus any
`standalone` pattern you mark as never right on its own. The lint names which marker fired, so a
false positive is arguable rather than mysterious.

rstack ships NO terms and NO markers (a list of them would itself describe what you work on).
Supply them with --terms FILE or $RSTACK_TERMS_FILE, in the format documented in _terms.py and
shown in terms.example.txt. With no file it checks nothing and says so. A configured file that
cannot be read blocks, because a lint that silently stopped checking is the failure it prevents.

Its output names files, lines, marker labels and a COUNT of matched terms. It never prints the
terms or the offending line: the output lands in the same session context the lint protects.

Usage:
    reload-lint.py                     staged additions only (the pre-commit path)
    reload-lint.py --all               audit the whole of each guarded file
    reload-lint.py --files a.md b.md   audit these files
Guarded files: --guard, else $RSTACK_RELOADED_FILES (':'-separated), else CLAUDE.md and AGENTS.md.
Exit 0 = clean, 1 = blocked.

The detail is not being deleted: it belongs in the project's own repo. This only keeps it out of
the files every session reloads whether it wants them or not.
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _terms  # noqa: E402

DEFAULT_GUARDED = ['CLAUDE.md', 'AGENTS.md']


def guarded_files(explicit):
    if explicit:
        return explicit
    env = os.environ.get('RSTACK_RELOADED_FILES', '')
    listed = [p for p in env.split(os.pathsep) if p.strip()]
    return listed or DEFAULT_GUARDED


def check_line(line, terms):
    """Reasons this line may not go in a reloaded file. Never includes the terms themselves."""
    reasons = []
    found = terms.term_hits(line)
    markers = terms.marker_hits(line)
    if found and markers:
        reasons.append('{} configured term(s) next to working detail ({})'.format(
            len(found), ', '.join(markers)))
    for label in terms.standalone_hits(line):
        reasons.append('standalone pattern: ' + label)
    return reasons


def staged_additions(paths):
    """(file, line number in the new file, text) for every added line in the staged diff."""
    try:
        diff = subprocess.run(['git', 'diff', '--cached', '--unified=0', '--'] + paths,
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError):
        return []
    out, cur, lineno = [], None, 0
    for line in diff.splitlines():
        if line.startswith('+++ '):
            cur = line[6:] if line.startswith('+++ b/') else None
        elif line.startswith('@@'):
            mo = re.search(r'\+(\d+)', line)
            lineno = int(mo.group(1)) if mo else 0
        elif line.startswith('+') and cur is not None:
            out.append((cur, lineno, line[1:]))
            lineno += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--all', action='store_true', help='audit whole files, not staged additions')
    ap.add_argument('--files', nargs='*', help='audit these files')
    ap.add_argument('--guard', nargs='*', help='the reloaded files to guard')
    ap.add_argument('--terms', help='terms file (default $%s)' % _terms.ENV)
    args = ap.parse_args(argv)

    try:
        terms = _terms.load(args.terms)
    except _terms.TermsUnreadable as exc:
        print('reload-lint: BLOCKED, the configured terms file is unusable ({}). Fix it; a lint '
              'that silently stopped checking is the failure this prevents.'.format(
                  str(exc).split(':')[-1].strip()), file=sys.stderr)
        return 1
    if not terms:
        print('reload-lint: no terms file configured (--terms or ${}); nothing was checked.'
              .format(_terms.ENV), file=sys.stderr)
        return 0
    if terms.terms and not terms.markers and not terms.standalone:
        print('reload-lint: terms are configured but no markers, so no term can fire (a term only '
              'fires next to a marker). Add `marker LABEL = REGEX` lines.', file=sys.stderr)

    findings = []
    if args.files or args.all:
        for f in (args.files or guarded_files(args.guard)):
            if not os.path.exists(f):
                continue
            with open(f, encoding='utf-8', errors='replace') as fh:
                for i, line in enumerate(fh, 1):
                    findings += [(f, i, r) for r in check_line(line, terms)]
    else:
        for f, i, line in staged_additions(guarded_files(args.guard)):
            findings += [(f, i, r) for r in check_line(line, terms)]

    if not findings:
        return 0
    print('BLOCKED: working detail in a file every session reloads.\n', file=sys.stderr)
    for f, i, reason in findings[:20]:
        print('  {}:{}  {}'.format(f, i, reason), file=sys.stderr)
    if len(findings) > 20:
        print('  ... and {} more'.format(len(findings) - 20), file=sys.stderr)
    print('\nThese files are re-read at session start and after every compaction, so this reaches '
          'every session on every wake. Write the summary-level fact here and link to where the '
          'detail lives. A term alone is fine; what fired is a term next to a marker, or a '
          'standalone pattern. A genuine false positive: say so in the commit and use --no-verify.',
          file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
