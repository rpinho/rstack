#!/usr/bin/env python3
"""Apply Claude's weekly budget to an interactive Agent spawn."""
import json
import os
from pathlib import Path
import sys

GATE = 'claude-pace-gate.py'
LIMIT = 'claude-pace-gate.limit'
CODEX = 'send it to Codex: tools/launch.sh JOB WORKDIR with AGENT_BACKEND=codex'


def check(event):
    if event.get('tool_name') != 'Agent':
        return
    import _hookfail
    import claude_cap
    import harness_blocks as blocks

    job, lane = _hookfail._who()
    session = dict(job=job, lane=lane)

    model = (event['tool_input'].get('model') or 'opus').lower()
    # Fable is priced above Opus, so it is paced the same way (harness-m5 review, 11-20).
    opus = claude_cap.is_opus(model) or 'fable' in model
    cap = claude_cap.decide(model, lane, 'agent', False, claude_cap.load_allowance(), pinned=True)
    pressure = cap['pressure']
    if pressure == 'unknown':
        blocks.warn(GATE, 'Claude usage is missing, unreadable or stale. Agent allowed.', **session)
        return
    if pressure == 'normal':
        return

    if pressure == 'ceiling':
        if _hookfail.is_conductor(event):
            return
        reason, fix = cap['leave'], CODEX
    elif pressure == 'line':
        if not opus or _hookfail.is_conductor(event):
            return
        reason = cap['line_note'] + '. Use model sonnet, or send build work to Codex.'
        fix = ''
    elif pressure == 'pace-off' and opus and not _hookfail.is_conductor(event):
        reason, fix = cap['leave'], 'Use model sonnet or ' + CODEX
    elif opus or (pressure == 'pace-off' and model in ('sonnet', 'haiku')):
        reason = ('Claude is pacing: {used:g}% now, {rate:.1f}%/h, {hours:.0f} h to reset. '
                  'Use model sonnet for mechanical work, or send build work to Codex.').format(**cap)
        fix = ''
    else:
        return

    output = {'hookEventName': 'PreToolUse'}
    if fix:
        cls = blocks.entry(LIMIT).get('class')
        if cls not in blocks.CLASSES:
            raise ValueError('invalid limit registry entry')
        receipt = blocks.record(LIMIT, cls, reason, fix=fix, **session)
        if receipt and cls == 'hard-line':
            output.update(permissionDecision='deny', permissionDecisionReason=reason + ' Fix: ' + fix)
        else:
            output['additionalContext'] = reason + ' ' + fix
    else:
        blocks.record(GATE, 'fail-open', reason, outcome='warn', **session)
        output['additionalContext'] = reason
    print(json.dumps({'hookSpecificOutput': output}))


def main():
    blocks = None
    try:
        # Same checkout, adjacent, and installed layouts as _hookfail._blocks(). Load the ledger
        # first so a broken policy module or missing hook helper can still be reported.
        here = Path(__file__).resolve().parent
        installed = Path(os.environ.get('RH_HARNESS_ROOT') or '~/.local/share/research-harness').expanduser()
        for root in (here.parent.parent / 'harness', here, installed):
            if (root / 'harness_blocks.py').is_file():
                sys.path.insert(0, str(root))
                break
        import harness_blocks as blocks
        import _hookfail
        # An old registry treats unknown hooks as refusing. Only enter the wrapper once its
        # fail-open error policy is present, including for malformed stdin.
        if blocks.entry(GATE).get('class') != 'fail-open':
            raise ValueError('missing fail-open registration')
        _hookfail.run(GATE, check)
    except Exception as exc:
        reason = 'Claude pacing check unavailable ({}). Agent allowed.'.format(type(exc).__name__)
        if blocks is None:
            print(reason, file=sys.stderr)
        else:
            blocks.warn(GATE, reason)


if __name__ == '__main__':
    main()
