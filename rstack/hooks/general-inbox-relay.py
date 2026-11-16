#!/usr/bin/env python3
"""UserPromptSubmit, conductor only: put every session report it has not relayed yet in front of it.

Why (owner, 11-14): "you stopped relaying the responses from the other sessions to me here. You tell the
other sessions to do something but then you don't bring them back to me." Reports land in the conductor
inbox (INBOX_DIR/inbox.jsonl, written by tell-general); the conductor read it only when it remembered to.
This hook injects the unrelayed lines on every prompt and advances a cursor (INBOX_DIR/relayed.cursor),
so relaying no longer depends on memory. Launcher noise ("ended without the hard-rule lines") is dropped
from the injection and stays in the file.

Who the conductor is: _hookfail.is_conductor (CONDUCTOR_CWD_SUFFIX or its tmux session), the same rule
the ask default and lane-no-questions use. Everyone else: no-op.

It informs and never blocks: a failure inside it is reported on stderr and the prompt goes through
(triage says no prompt is in the set it guards), because refusing the owner's own prompt to the
conductor would be worse than one missed relay.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'harness'))
sys.path.append(str(Path(os.environ.get('RH_ROOT') or '~/.local/share/research-harness').expanduser()))
import lane_registry

INBOX_DIR = os.path.expanduser(os.environ.get('RSTACK_CONDUCTOR_INBOX', '~/.local/state/general-inbox'))
NOISE = ('ended without the hard-rule lines',)


def body(event):
    if not _hookfail.is_conductor(event):
        return 0
    inbox, cursor = os.path.join(INBOX_DIR, 'inbox.jsonl'), os.path.join(INBOX_DIR, 'relayed.cursor')
    try:
        lines = open(inbox).read().splitlines()
    except FileNotFoundError:
        return 0
    try:
        start = int(open(cursor).read().strip())
    except (FileNotFoundError, ValueError):
        start = len(lines)       # first run: start from now, not from the whole history
    registry = lane_registry.load()
    new, retired = [], []
    for line in lines[start:]:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        text = m.get('text') or m.get('msg') or m.get('message') or ''
        if any(n in text for n in NOISE):
            continue
        session = str(m.get('from', m.get('lane', '?')))
        reason = registry.retired_reason(session, m.get('lane'))
        line = '- {}Z [{}] {}'.format(str(m.get('utc', ''))[:16], session, text[:1500])
        if reason:
            retired.append(line + ' (' + reason + ')')
        else:
            new.append(line)
    with open(cursor, 'w') as stream:
        stream.write(str(len(lines)))
    if new or retired:
        ctx = ('SESSION REPORTS NOT YET RELAYED TO THE OWNER ({}). Relay the substance of each in this reply: '
               'results, decisions he must make, anything blocked. Plain words, grouped by session, no jargon.\n'
               .format(len(new)) + '\n'.join(new)) if new else ''
        if retired:
            ctx += '\nretired (visible history; no relay required):\n' + '\n'.join(retired)
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': ctx}}))
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('general-inbox-relay.py', body, lambda raw, ev: False,
                           guards='nothing (it relays reports to the conductor; it never blocks a prompt)'))
