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

Two more cases, each with its own answer:

  lookup(what, fn, ...)        A guard that must ask something outside itself (git, gh, the forge,
                               a ledger) wraps that call in `lookup`. If the lookup fails, the hook
                               answers `ask` and names what could not be read: the guard is fine
                               and the world is unreadable, so the owner decides, rather than the
                               hook guessing either way.
  fail_closed=True             For guards whose matcher IS the dangerous act (send, merge, push,
                               delete, publish). Any parse error or exception refuses, whatever the
                               triage says. Do not set it on a guard wired to every shell command:
                               a broken one would refuse the whole session. Those keep triage.

The refusal names the hook and the exception TYPE only, never the exception text and never the
input: command payloads and env blocks hold API keys.

Usage, at the bottom of a hook:

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _hookfail
    sys.exit(_hookfail.run('my-hook.py', body, triage, guards='what it guards'))

`body(event)` emits its own decision (with `decide`) and returns an exit code.

Two more (11-11, adopted from the laptop's copy of this contract):

  timeout=SECONDS              A hook that hangs is killed by Claude Code at its settings timeout, and a
                               killed hook is an allow. With a timeout, run() stops the body itself a little
                               earlier and treats it as an error (triage decides). HookTimeout derives from
                               BaseException so a hook's own `except Exception` cannot swallow it.
  RSTACK_UNATTENDED=1          An `ask` prompts even under --dangerously-skip-permissions, and in a headless
                               run (`claude -p`, a scheduled job) nobody is there to answer: the run stalls.
                               With this set in the environment, every ask becomes a deny that says why.
"""
import json
import os
from pathlib import Path
import signal
import sys

EVENT = 'PreToolUse'
FAIL_CLOSED_ACTS = ('send', 'merge', 'push', 'delete', 'publish')


class HookTimeout(BaseException):
    """The body ran past run()'s timeout. A BaseException so `except Exception` in a hook cannot hide it."""


class LookupFailed(Exception):
    """A lookup the guard needs (git, gh, the forge) could not be read. `what` names it."""
    def __init__(self, what):
        super().__init__(what)
        self.what = what


def lookup(what, fn, *args, **kwargs):
    """Return fn(*args, **kwargs); if it fails in any way, raise LookupFailed(what).

    `run` turns that into an `ask` naming `what`, never an allow. The original error is not kept:
    its text can carry the payload or a credential."""
    try:
        return fn(*args, **kwargs)
    except SystemExit:
        raise
    except Exception:
        raise LookupFailed(what) from None


def state_dir(*parts):
    """Where hooks keep small state files: $RSTACK_STATE_DIR, else $XDG_STATE_HOME/rstack."""
    base = os.environ.get('RSTACK_STATE_DIR')
    if not base:
        xdg = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
        base = str(Path(xdg) / 'rstack')
    return Path(base).expanduser().joinpath(*parts)


def unattended():
    return os.environ.get('RSTACK_UNATTENDED') == '1'


def decide(decision, reason):
    """Emit a PreToolUse decision. 'deny' refuses; 'ask' puts it to the owner (a deny when unattended)."""
    if decision == 'ask' and unattended():
        decision, reason = 'deny', reason + (' (Unattended run, RSTACK_UNATTENDED=1: nobody can answer a prompt '
                                             'here, so this is refused instead of asked.)')
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': EVENT,
        'permissionDecision': decision,
        'permissionDecisionReason': reason}}))


def _expired(signum, frame):
    raise HookTimeout()


def run(name, body, triage=None, guards='this action', on_error='deny', fail_closed=False, timeout=None):
    """Run `body(event)`; refuse rather than allow if it cannot be run to completion.

    A failed `lookup` asks. With fail_closed, any other error refuses whatever triage says.
    With timeout, a body still running after that many seconds is an error too.
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
        if timeout:
            signal.signal(signal.SIGALRM, _expired)
            signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            return body(event) or 0
        except SystemExit:
            raise
        except HookTimeout:
            why = 'HookTimeout'
        except LookupFailed as exc:
            decide('ask', '{} could not read {} to check this call. It guards {}; the guard works '
                          'but what it checks against is unreadable, so the owner decides.'.format(
                              name, exc.what, guards))
            return 0
        except Exception as exc:
            why = type(exc).__name__
        finally:
            if timeout:
                signal.setitimer(signal.ITIMER_REAL, 0)

    guarded = True
    if fail_closed:
        pass   # the matcher is the dangerous act itself: every failure refuses
    elif triage is not None:
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
           'rather than allowed. Repair the hook, or ask the owner to decide. Hook: {}'.format(
               name, why, guards, hook_path(name)))
    return 0


def hook_path(name):
    """The file that is running, home shown as ~, so the refusal points at the hook to repair.

    11-10: the message used to say ~/.claude/hooks/NAME, which was wrong for every project hook
    (a KB send gate lives in <project>/.claude/hooks). Falls back to the name alone."""
    try:   # the refusal must not fail because of this line
        path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] not in ('', '-c', '-') else ''
        if not path.endswith(('.py', '.sh')):
            return name
        home = os.path.expanduser('~')
        return '~' + path[len(home):] if home not in ('', '/') and path.startswith(home + os.sep) else path
    except Exception:
        return name
