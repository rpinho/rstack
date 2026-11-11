#!/usr/bin/env python3
"""PreToolUse on SendMessage: worker sessions may not message the conductor session directly.

Why: one long-lived conductor session coordinates many worker sessions. Every direct message
wakes it, and every wake replays its whole context, a few hundred thousand tokens, to deliver what
was usually an FYI. The owner's rule was that waking the conductor should be done by scripts
wherever possible, not by the model. So workers file through `relay` (rstack/tools/relay):
`relay fyi "..."` is filed without a wake, `relay decision|owner|break "..."` files and wakes.
Replies FROM the conductor to workers are untouched.

Who the conductor is: CONDUCTOR_NAME (default `conductor`), plus the socket address in
`conductor.addr` inside the inbox directory (CONDUCTOR_INBOX_DIR, default
$XDG_STATE_HOME/conductor-inbox), so a message aimed at the raw address is caught too.

It used to `json.load` unguarded, so malformed input crashed the hook and the direct message went
through, waking the conductor: exactly what the gate exists to stop. An error on a SendMessage
that names the conductor is now refused.
"""
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402


def name():
    return os.environ.get('CONDUCTOR_NAME') or 'conductor'


def inbox_dir():
    explicit = os.environ.get('CONDUCTOR_INBOX_DIR')
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'conductor-inbox'


def address():
    try:
        addr = (inbox_dir() / 'conductor.addr').read_text(encoding='utf-8').strip()
    except OSError:
        return ''
    return addr[4:] if addr.startswith('uds:') else addr


def reason():
    return ('Do not message the {0} session directly: every wake replays its whole context. '
            'Use Bash: relay fyi "..." (filed, no wake) or relay decision|owner|break "..." '
            '(files and wakes it). Keep routine status in your own handoff.'.format(name()))


def triage(raw, event):
    """Crash-proof: does this payload look like a SendMessage aimed at the conductor?"""
    return 'SendMessage' in raw and name().lower() in raw.lower()


def body(event):
    if event.get('tool_name') != 'SendMessage':
        return 0
    inp = event.get('tool_input')
    if not isinstance(inp, dict):
        raise ValueError('tool_input is not an object')
    target = str(inp.get('to', '')).strip()
    socket_path = address()
    addressed = bool(socket_path) and re.search(
        r'(?<![\w./-])' + re.escape(socket_path) + r'(?![\w./-])', target) is not None
    if target.split(' [', 1)[0] == name() or addressed:
        _hookfail.decide('deny', reason())
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('conductor-inbox-gate.py', body, triage,
                           guards='SendMessage aimed at the conductor session, which must go through relay'))
