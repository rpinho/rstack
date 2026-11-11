#!/usr/bin/env python3
"""PreToolUse(Bash) guard: deny Finder-driven deletes on macOS; use /usr/bin/trash instead.

Why: deletes must be reversible, so agents were told to send files to the Trash rather than `rm`
them. They did it by scripting Finder (`osascript -e 'tell application "Finder" to delete ...'`),
and Finder plays the trash sound once per item. A cleanup of a few dozen files was a few dozen
sounds, and the owner had to ask twice, days apart, for the noise to stop. Prose did not hold.
`/usr/bin/trash` (macOS 14+) moves to the same Trash with Put Back, silently.

It used to end `except Exception: sys.exit(0)`, so unreadable input allowed the delete. Now an
error on a command that mentions Finder and a delete is refused; anything else passes untouched.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

FINDER_DELETE = re.compile(r'application\s+\\?"Finder\\?"[^\n]*\bdelete\b', re.I)
REASON = 'Use /usr/bin/trash PATH instead: same Trash and Put Back, no sound.'


def triage(raw, event):
    return 'Finder' in raw and re.search(r'\bdelete\b', raw, re.I) is not None


def body(event):
    if event.get('tool_name') not in (None, 'Bash'):
        return 0
    cmd = (event.get('tool_input') or {}).get('command', '')
    if FINDER_DELETE.search(str(cmd)):
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('trash-guard.py', body, triage,
                           guards='Finder-driven deletes, which must go through /usr/bin/trash'))
