#!/usr/bin/env python3
"""PreToolUse on a pod-creation tool: refuse a rented machine that cannot end itself.

Why: rented GPU/CPU pods bill until someone stops them, and "remember to stop it" is prose that
dies with the session holding it. A rented machine that never shut off is the failure this answers.
The fix is architecture: a pod must carry its own kill in its start command, so it cannot outlive
its deadline even if every session watching it is gone.

The check: the start command (entrypoint + cmd + args) must contain a `sleep N` with
N <= RSTACK_POD_MAX_SECONDS (default 86400, one day) and the provider's self-termination call,
RSTACK_POD_KILL_MARKER (default `podTerminate`, the name of RunPod's terminate mutation). The
shape, with the provider call left schematic:

    entrypoint ["/bin/bash", "-c"]
    cmd        "(sleep 21600; <call podTerminate for $RUNPOD_POD_ID>) & exec /start.sh"

It used to read the payload unguarded, so malformed input or a non-dict body crashed the hook and
the pod was created with no self-kill: the one outcome it exists to prevent. Everything that
reaches this hook is a create-pod call, so every internal error refuses.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402


def limits():
    return (int(os.environ.get('RSTACK_POD_MAX_SECONDS') or 24 * 3600),
            os.environ.get('RSTACK_POD_KILL_MARKER') or 'podTerminate')


def self_terminating(start):
    max_seconds, marker = limits()
    m = re.search(r'\bsleep\s+(\d+)\b', start)
    return marker in start and m is not None and int(m.group(1)) <= max_seconds


def start_command(event):
    inp = event.get('tool_input')
    if not isinstance(inp, dict):
        raise ValueError('tool_input is not an object')
    b = inp.get('body', inp)
    if not isinstance(b, dict):
        raise ValueError('body is not an object')
    parts = [b.get('args') or '']
    for key in ('entrypoint', 'cmd', 'dockerStartCmd', 'dockerArgs'):
        value = b.get(key) or []
        parts += list(value) if isinstance(value, (list, tuple)) else [value]
    return ' '.join(map(str, parts))


def body(event):
    if self_terminating(start_command(event)):
        return 0
    max_seconds, marker = limits()
    print('Pod refused: its start command must end the pod itself: a `sleep N` (N <= {}) followed '
          'by the provider kill call ({}), backgrounded before the real entrypoint. See the recipe '
          'in rstack/hooks/pod-deadline-gate.py.'.format(max_seconds, marker), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(_hookfail.run('pod-deadline-gate.py', body, triage=lambda raw, event: True,
                           guards='every pod creation, which must carry its own kill'))
