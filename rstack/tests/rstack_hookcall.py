"""Run an rstack hook the way Claude Code does and classify the outcome.

The contract every guard is held to (rstack/principles/a-guard-must-refuse-not-crash.md):

  1. GUARDED AND BROKEN -> refused. Input the hook cannot parse, that still looks like the action
     it guards, comes back deny or ask. Never allow.
  2. UNRELATED AND BROKEN -> allowed, but loudly: printed to stderr, never silent.
  3. THE REAL THING -> refused.
  4. THE INNOCENT THING -> allowed. A guard that denies everything bricks the session.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

RSTACK = Path(__file__).resolve().parents[1]
HOOKS = RSTACK / 'hooks'
TOOLS = RSTACK / 'tools'
BLOCKING = ('deny', 'ask')


def call(script, payload, cwd=None, env=None):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([sys.executable, str(script)], input=raw, capture_output=True, text=True,
                       cwd=str(cwd or Path.cwd()), env=e, timeout=60)
    decision, context = None, None
    for line in p.stdout.splitlines():
        try:
            out = json.loads(line)
        except ValueError:
            continue
        if isinstance(out, dict):
            spec = out.get('hookSpecificOutput') or {}
            decision = spec.get('permissionDecision') or decision
            context = spec.get('additionalContext') or context
    return dict(blocked=p.returncode == 2 or decision in BLOCKING, decision=decision,
                context=context, code=p.returncode, stdout=p.stdout, stderr=p.stderr)


def blocked(script, payload, **kw):
    r = call(script, payload, **kw)
    assert r['blocked'], 'ALLOWED a call it should have refused: {} -> {}'.format(Path(script).name, r)
    return r


def allowed(script, payload, **kw):
    r = call(script, payload, **kw)
    assert not r['blocked'], 'REFUSED a call it should have allowed: {} -> {}'.format(Path(script).name, r)
    assert r['code'] == 0, 'non-zero exit (Claude Code would treat it as an error): {}'.format(r)
    return r


def loud(script, payload, **kw):
    r = allowed(script, payload, **kw)
    assert r['stderr'].strip(), 'allowed silently; a broken guard must say so: {}'.format(Path(script).name)
    return r


def bash(command, **extra):
    d = {'tool_name': 'Bash', 'tool_input': {'command': command}}
    d.update(extra)
    return d
