#!/usr/bin/env python3
"""Deny a headless agent CLI (`codex exec`, `claude -p`) whose stdin is left open.

Why: both read stdin when it is not a tty. In an agent's shell stdin can be a pipe that never
closes, so the call prints "Reading additional input from stdin..." and waits forever. A prose rule
("always add </dev/null") was the only defence and did not hold, so it moved to the tool boundary.
Close stdin with `< /dev/null`, or pipe or heredoc the prompt in.

Only a command-position `codex ... exec` or `claude -p/--print` is checked; mentions inside quotes,
heredoc bodies or echo/grep arguments are ignored. Wired to Bash: triage, never fail_closed.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

HEREDOC = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*\n)(.*?)(\n\s*\3\b)", re.S)
SEPARATORS = re.compile(r"(&&|\|\||;|\n|\|)")
PREFIX_WORDS = {'env', 'command', 'sudo', 'time', 'nohup', 'nice', 'exec', 'timeout'}
ENV_ASSIGN = re.compile(r'^[A-Za-z_]\w*=')
SAFE_FLAGS = {'--help', '-h', '--version', '-V'}
REASON = ('agent-stdin-guard: `codex exec` and `claude -p` read stdin when it is not a tty and hang if '
          'the pipe never closes ("Reading additional input from stdin..."). Close it: add `< /dev/null`, '
          'or pipe or heredoc the prompt in, then rerun.')


def segments(command):
    """(tokens, piped_in, has_heredoc) for each simple command."""
    piped = False
    for part in SEPARATORS.split(command):
        if part in ('&&', '||', ';', '\n'):
            piped = False
            continue
        if part == '|':
            piped = True
            continue
        tokens = part.split()
        if tokens:
            yield tokens, piped
        piped = False


def start(tokens):
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in PREFIX_WORDS or ENV_ASSIGN.match(tok):
            i += 1
            while tok in ('env', 'timeout', 'nice') and i < len(tokens) and (
                    tokens[i].startswith('-') or ENV_ASSIGN.match(tokens[i]) or (tok == 'timeout' and tokens[i][0].isdigit())):
                i += 2 if tokens[i] in ('-u', '-n') else 1
            continue
        break
    return i


def headless(tokens):
    i = start(tokens)
    if i >= len(tokens):
        return False
    tool, rest = os.path.basename(tokens[i]), tokens[i + 1:i + 8]
    return (tool == 'codex' and 'exec' in rest) or (tool == 'claude' and ('-p' in rest or '--print' in rest))


def unsafe(tokens, piped):
    if not headless(tokens) or any(t in SAFE_FLAGS for t in tokens):
        return False
    return not (piped or any(t.startswith('<') for t in tokens))


def triage(raw, event):
    return 'codex' in raw or 'claude' in raw


def body(event):
    command = (event.get('tool_input') or {}).get('command')
    if not isinstance(command, str):
        raise ValueError('command is not a string')
    if 'codex' not in command and 'claude' not in command:
        return 0
    stripped = HEREDOC.sub(lambda m: m.group(1).rstrip('\n') + ' <heredoc\n', command)
    if any(unsafe(tokens, piped) for tokens, piped in segments(stripped)):
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('agent-stdin-guard.py', body, triage, guards='headless agent CLIs with open stdin'))
