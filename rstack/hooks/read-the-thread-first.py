#!/usr/bin/env python3
"""Read the thread before you answer it. PreToolUse on the browser tools.

Why: the agent-drafted email replies that came back wrong were not wrong about the voice, they
were wrong about the question. A session that drafts from the notification line and clicks Send
has never seen the thread. A lint on the draft checks its words; nothing checked that anyone had
read what they were replying to. The owner's correction, more than once: lead with what they
actually asked.

So: a browser click that sends an email is refused unless this session has pulled the page text
at least once in the last 30 minutes. The read is the evidence; `get_page_text` and `read_page`
count, because they return the thread rather than a picture of it.

Deliberately narrow:
  - only an email send. Posts, DMs and texts are not gated.
  - a screenshot is not a read. It is how a session convinces itself it looked.
  - `# thread-read-ok` in the action summary passes, for a thread read in another session or a
    reply the owner dictated.

It records on PreToolUse, so it credits a read that was requested rather than one that returned
text. That is the loose end, and it is the safe direction: it can only be fooled by a session
that genuinely asked for the thread.

State: $RSTACK_STATE_DIR/read-the-thread/<session>.json (one timestamp).
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

WINDOW_S = 30 * 60
READ_TOOLS = ('get_page_text', 'read_page')

SEND = re.compile(r'\bsends?\b', re.I)
EMAIL = re.compile(r'\b(e-?mail|gmail|reply in (the )?thread|reply to)\b', re.I)
NOT_EMAIL = re.compile(r'\b(tweet|x post|on x|dm|text message|sms)\b', re.I)
ESCAPE = '# thread-read-ok'

REASON = ('Read the thread before answering it: this session has not pulled the page text in the '
          'last 30 minutes, so the draft cannot be answering what they actually asked. Call '
          'get_page_text or read_page on the open thread, read the last message, then send. A '
          'screenshot does not count. If the thread was read in another session or the owner '
          'dictated the reply, put "' + ESCAPE + '" in the action summary.')


def session_file(event):
    sid = re.sub(r'[^A-Za-z0-9_-]', '', str(event.get('session_id', 'x')))[:64] or 'x'
    return _hookfail.state_dir('read-the-thread', sid + '.json')


def note_read(event):
    try:
        path = session_file(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'last_read': time.time()}))
    except OSError:
        pass          # a lost note means the next send asks for another read: the safe way


def read_recently(event):
    try:
        last = json.loads(session_file(event).read_text())['last_read']
        return (time.time() - float(last)) <= WINDOW_S
    except (OSError, ValueError, KeyError, TypeError):
        return False


def actions(event):
    """Both shapes: a single computer call, and the actions inside a browser_batch.

    A tool_input that is not an object RAISES rather than being read as "no actions". Caught by
    this hook's own test: normalising it to {} made an unreadable send look like "not a send",
    which is the silent allow the wrapper exists to prevent.
    """
    name = str(event.get('tool_name', ''))
    inp = event.get('tool_input')
    if not isinstance(inp, dict):
        raise ValueError('tool_input is not an object')
    if name.endswith('__computer'):
        return [inp]
    found = inp.get('actions')
    if found is not None and not isinstance(found, list):
        raise ValueError('actions is not a list')
    return [a.get('input', {}) for a in (found or [])
            if isinstance(a, dict) and isinstance(a.get('input'), dict)]


def sends_email(event):
    for a in actions(event):
        summary = str(a.get('action_summary', ''))
        if ESCAPE in summary:
            continue
        if (a.get('action') == 'left_click' and SEND.search(summary)
                and EMAIL.search(summary) and not NOT_EMAIL.search(summary)):
            return True
    return False


def triage(raw, event):
    return 'left_click' in raw and re.search(r'\bsends?\b', raw, re.I) is not None


def body(event):
    name = str(event.get('tool_name', ''))
    if any(name.endswith('__' + t) or name == t for t in READ_TOOLS):
        note_read(event)
        return 0
    if 'get_page_text' in str(event.get('tool_input', '')):
        note_read(event)
    if sends_email(event) and not read_recently(event):
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('read-the-thread-first.py', body, triage,
                           guards='a browser click that sends an email'))
