#!/usr/bin/env python3
"""Deny a lint/test/typecheck gate piped into tail/head/grep unless the command sets pipefail.

Why: a pipeline returns its LAST command's exit code. A lint gate piped into `tail -1` returned
tail's 0, the format failure was hidden, the PR merged and broke main. The prose rule "never pipe a
gate into tail" had already been broken more than once, so it is a hook. Fix: prefix
`set -o pipefail;`, or run the gate unpiped and read its exit code.

Wired to Bash, so it runs through _hookfail with triage (never fail_closed): if the hook itself
breaks, only commands that pipe something that looks like a gate are held.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

GATE = (r"(?:yarn|npm|pnpm|bun)\s+(?:run\s+)?(?:check(?::\w+)?|lint|test|typecheck|format(?::check)?)\b"
        r"|\b(?:pytest|ruff\s+(?:check|format)|mypy|tsc|eslint|prettier\s+--check|pre-commit\s+run"
        r"|cargo\s+(?:test|clippy|check)|go\s+test|make\s+(?:check|test|lint)|unittest)\b")
PIPED = re.compile(r"(?:" + GATE + r")[^|;&\n]*\|\s*(?:tail|head|grep|rg|ugrep)\b")
WORDS = ('pytest', 'ruff', 'mypy', 'tsc', 'eslint', 'prettier', 'pre-commit', 'cargo', 'go test',
         'make', 'unittest', 'lint', 'test', 'check')
REASON = ('gate-pipe-guard: a gate piped into tail/head/grep returns the pipe\'s exit code, so a failing '
          'check looks green. Prefix `set -o pipefail;` or run the gate unpiped and read its exit code.')


def triage(raw, event):
    return '|' in raw and any(w in raw for w in WORDS)


def body(event):
    cmd = (event.get('tool_input') or {}).get('command') or ''
    if not isinstance(cmd, str):
        raise ValueError('command is not a string')
    probe = re.sub(r'\d?>&\d', '', cmd)
    if 'pipefail' not in cmd and PIPED.search(probe):
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('gate-pipe-guard.py', body, triage, guards='checks piped into tail/head/grep'))
