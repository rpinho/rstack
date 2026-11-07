#!/usr/bin/env python3
"""PreToolUse on a pod-creation tool: the capacity-receipt gate, run fail-safe.

Why: the capacity check itself lives in this repository's `tools/pod-create-gate.py` (audit by
default, enforcement opt-in per lane; it reads the harness work queue and asks for a fresh
`rh pods plan` receipt before a pod of that shape is rented). That file already survives malformed
JSON, but an unexpected failure above it, a bad import or an unreadable harness, exited 1, and
Claude Code treats exit 1 as "allow": the pod was created unchecked.

This hook adds no policy. It loads that implementation and runs it inside the fail-safe wrapper.
Everything that reaches this hook is a create-pod call (that is what the matcher is for), so any
internal error, including the implementation being missing, refuses.

RSTACK_POD_GATE_IMPL overrides where the implementation is loaded from.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _hookfail  # noqa: E402

REPO = HERE.parents[1]


def implementation():
    path = Path(os.environ.get('RSTACK_POD_GATE_IMPL') or REPO / 'tools/pod-create-gate.py')
    harness = REPO / 'harness'
    if harness.is_dir() and str(harness) not in sys.path:
        sys.path.append(str(harness))
    spec = importlib.util.spec_from_file_location('rstack_pod_create_gate_impl', str(path))
    if spec is None or spec.loader is None:
        raise ImportError('pod gate implementation not loadable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body(event):
    code, message = implementation().gate(event)
    if message:
        if code:
            print(message, file=sys.stderr)
        else:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                                    'additionalContext': message}}))
    return code


if __name__ == '__main__':
    sys.exit(_hookfail.run('pod-create-gate.py', body, triage=lambda raw, event: True,
                           guards='every pod creation and its capacity receipt'))
