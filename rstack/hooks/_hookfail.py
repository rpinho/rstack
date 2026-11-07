#!/usr/bin/env python3
"""Make a PreToolUse hook fail safe instead of fail open.

Why: Claude Code blocks a tool call only on exit 2 or on a deny/ask JSON decision. Every other
outcome lets the action through. So a hook that raises on malformed input, a missing state file,
an unreadable config or an import error is not a weaker guard: it is no guard at all, and it fails
silently, which is worse than failing loudly. In the setup these hooks come from, five of the
guards ended `except Exception: sys.exit(0)`. One of them was the check that a rented machine must
carry its own shutoff: it crashed on an unexpected payload shape, and the machine was created with
no shutoff, which is the one outcome it existed to prevent.

The hard part is not catching the error. It is deciding what to do with a call you could not
read. A guard wired to `Bash` that denies on any internal error denies every shell command in the
session: safe, and also unusable. So each hook declares two things:

  triage(raw, event) -> bool   Is this call inside the set this hook guards? It runs on the RAW
                               stdin text with substring work only: no parsing, no file I/O, no
                               schema assumptions, so it keeps working exactly when the real check
                               has already failed. If triage itself raises, the answer is yes.
  guards='...'                 One clause naming the guarded set, for the refusal message.

An error on a call inside the guarded set is refused (`deny`, or `ask` where a false positive costs
more than the harm). An error on a call outside it is allowed, with the failure printed to stderr so
a broken guard is visible rather than silent.

The refusal names the hook and the exception TYPE only, never the exception text and never the
input: command payloads and env blocks hold API keys.

Usage, at the bottom of a hook:

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _hookfail
    sys.exit(_hookfail.run('my-hook.py', body, triage, guards='what it guards'))

`body(event)` emits its own decision (with `decide`) and returns an exit code.
"""
import json
import os
from pathlib import Path
import sys

EVENT = 'PreToolUse'


def state_dir(*parts):
    """Where hooks keep small state files: $RSTACK_STATE_DIR, else $XDG_STATE_HOME/rstack."""
    base = os.environ.get('RSTACK_STATE_DIR')
    if not base:
        xdg = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
        base = str(Path(xdg) / 'rstack')
    return Path(base).expanduser().joinpath(*parts)


def decide(decision, reason):
    """Emit a PreToolUse decision. 'deny' refuses; 'ask' puts it to the owner."""
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': EVENT,
        'permissionDecision': decision,
        'permissionDecisionReason': reason}}))


def run(name, body, triage=None, guards='this action', on_error='deny'):
    """Run `body(event)`; refuse rather than allow if it cannot be run to completion.

    Returns the exit code to hand to sys.exit.
    """
    raw = sys.stdin.read()
    event, why = None, None
    try:
        event = json.loads(raw)
        if not isinstance(event, dict):
            event, why = None, 'ValueError'
    except Exception as exc:
        why = type(exc).__name__

    if event is not None:
        try:
            return body(event) or 0
        except SystemExit:
            raise
        except Exception as exc:
            why = type(exc).__name__

    guarded = True
    if triage is not None:
        try:
            guarded = bool(triage(raw, event))
        except Exception:
            guarded = True

    if not guarded:
        print('[{}] internal error ({}); this call is not in the set it guards ({}), '
              'so it was allowed. The hook needs repair.'.format(name, why, guards),
              file=sys.stderr)
        return 0

    decide(on_error,
           '{} could not check this call ({} inside the hook). It guards {}, and a guard that '
           'cannot run must not authorize what it was meant to check, so this call is refused '
           'rather than allowed. Repair the hook, or ask the owner to decide.'.format(name, why, guards))
    return 0
