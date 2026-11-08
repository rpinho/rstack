#!/usr/bin/env python3
"""A beginner page must not send people into advanced-only material without saying "later".

Ricardo, 11-08: most people we share rstack with are beginners, and the full stack is overkill for
them. The beginner track is a tutorial; a link from it into hooks, lanes or the harness turns it
back into the whole stack. docs/onboarding/tracks.json lists the beginner pages and the
advanced-only paths. A link from a beginner page to an advanced-only path fails unless its
paragraph says "later". It also fails when the README's first screen stops pointing at /onboard.

    python3 rstack/tools/onboarding_lint.py [REPO_ROOT]      exit 0 PASS, 1 FAIL
"""
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys

LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)\)')
FIRST_SCREEN = 30   # lines of the README a newcomer sees without scrolling


def resolve(page, target, root):
    """The link target as a repo-relative path, or None for an external or anchor-only link."""
    target = target.split('#')[0]
    if not target or re.match(r'^[a-z][a-z0-9+.-]*:', target, re.I):
        return None
    joined = posixpath.normpath(posixpath.join(str(PurePosixPath(page).parent), target))
    return joined + ('/' if (root / joined).is_dir() else '')


def findings(root):
    root = Path(root)
    tracks = json.loads((root / 'docs/onboarding/tracks.json').read_text())
    advanced = tracks['advanced_only']
    out = []
    for page in tracks['beginner']:
        text = (root / page).read_text()
        for paragraph in re.split(r'\n\s*\n', text):
            for m in LINK.finditer(paragraph):
                path = resolve(page, m.group(1), root)
                if path is None:
                    continue
                hit = next((a for a in advanced if path == a or path.startswith(a.rstrip('/') + '/')
                            or (a.endswith('/') and path.rstrip('/') + '/' == a)), None)
                if hit and not re.search(r'\blater\b', paragraph, re.I):
                    out.append('{}: links to advanced-only {} without "later" in the paragraph'.format(page, path))
    readme = (root / 'README.md').read_text().splitlines()[:FIRST_SCREEN]
    if not any('/onboard' in line for line in readme):
        out.append('README.md: the first {} lines no longer point newcomers at /onboard'.format(FIRST_SCREEN))
    return out


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    problems = findings(root)
    for p in problems:
        print('FAIL ' + p)
    print('onboarding-lint: ' + ('PASS' if not problems else '{} problem(s)'.format(len(problems))))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
