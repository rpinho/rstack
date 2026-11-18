#!/usr/bin/env python3
"""PreToolUse(Bash) guard: deny Finder-driven deletes on macOS; use /usr/bin/trash instead.

Why: deletes must be reversible, so agents were told to send files to the Trash rather than `rm`
them. They did it by scripting Finder (`osascript -e 'tell application "Finder" to delete ...'`),
and Finder plays the trash sound once per item. A cleanup of a few dozen files was a few dozen
sounds, and the owner had to ask twice, days apart, for the noise to stop. Prose did not hold.
`/usr/bin/trash` (macOS 14+) moves to the same Trash with Put Back, silently.

Only executed Bash commands are checked. Edit/Write contents, quoted mentions and
heredoc bodies are text. Protected cleanup operands still refuse on unreadable metadata.
"""
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

FINDER_DELETE = re.compile(r'application\s+\\?"Finder\\?"[^\n]*\bdelete\b', re.I)
REASON = 'Use /usr/bin/trash PATH instead: same Trash and Put Back, no sound.'


def triage(raw, event):
    if isinstance(event, dict) and event.get('tool_name') not in (None, 'Bash'):
        return False
    return re.search(r'\b(?:trash|rm|rmdir|unlink|delete)\b', raw, re.I) is not None


def body(event):
    if event.get('tool_name') not in (None, 'Bash'):
        return 0
    cmd = (event.get('tool_input') or {}).get('command', '')
    source = Path(__file__).resolve().parent
    sys.path[:0] = [str(source / '..' / 'tools'), os.path.expanduser('~/.local/bin')]
    from protected_paths import assert_shell_disposable, deletion_commands
    for argv in deletion_commands(cmd):
        name = Path(argv[0]).name
        if name == 'osascript' and FINDER_DELETE.search(' '.join(argv[1:])):
            _hookfail.decide('deny', REASON)
            return 0
        if name == 'rm':
            options = argv[1:argv.index('--')] if '--' in argv else argv[1:]
            recursive = any(a == '--recursive' or (a.startswith('-') and not a.startswith('--')
                                                     and set(a[1:]) & {'r', 'R'}) for a in options)
            force = any(a == '--force' or (a.startswith('-') and not a.startswith('--')
                                          and 'f' in a[1:]) for a in options)
            if recursive and force:
                _hookfail.decide('deny', 'Use /usr/bin/trash PATH instead: forced recursive rm is irreversible.')
                return 0
    try:
        assert_shell_disposable(cmd)
    except Exception:
        _hookfail.decide('deny', 'Cleanup refused: protected release overlap or unreadable protection metadata.')
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('trash-guard.py', body, triage,
                           guards='deletion commands and protected cleanup paths'))
