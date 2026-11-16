#!/usr/bin/env python3
"""Stop, conductor only: the turn does not end until every injected session report was relayed.

Why (owner, 11-14): general-inbox-relay.py only puts unrelayed reports in front of the conductor, which
could still skip them. This is the check. Reports injected so far are the inbox lines between
INBOX_DIR/relay-check.cursor and INBOX_DIR/relayed.cursor. The conductor's reply this turn (assistant text
after the owner's last prompt) must name each report's session, or one of its aliases from
INBOX_DIR/aliases.json ({"session": ["alias", ...]}). Any missing: the stop is blocked once with the list.
All covered: relay-check.cursor advances. stop_hook_active (the second stop) is always allowed, so it can
never loop, and a failure inside the hook allows the stop and says so on stderr.
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


def cursor(path, default):
    try:
        return int(open(path).read().strip())
    except (FileNotFoundError, ValueError):
        return default


def this_turn_reply(transcript):
    """Assistant text after the owner's last typed prompt."""
    reply = []
    rows = [json.loads(x) for x in open(transcript).read().splitlines() if x.strip()]
    for r in reversed(rows):
        if r.get('type') == 'user' and isinstance(r.get('message', {}).get('content'), str):
            break
        if r.get('type') == 'assistant':
            for c in r.get('message', {}).get('content', []):
                if isinstance(c, dict) and c.get('type') == 'text':
                    reply.insert(0, c['text'])
    return '\n'.join(reply)


def body(event):
    if event.get('stop_hook_active') or not _hookfail.is_conductor(event):
        return 0
    try:
        lines = open(os.path.join(INBOX_DIR, 'inbox.jsonl')).read().splitlines()
    except FileNotFoundError:
        return 0
    hi = cursor(os.path.join(INBOX_DIR, 'relayed.cursor'), len(lines))
    check = os.path.join(INBOX_DIR, 'relay-check.cursor')
    lo = cursor(check, hi)
    sessions = []
    registry = lane_registry.load()
    for line in lines[lo:hi]:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if any(n in (m.get('text') or '') for n in NOISE):
            continue
        s = str(m.get('from', m.get('lane', '?')))
        retired = registry.retired_reason(s, m.get('lane'))
        if retired:
            print('retired: [{}] {}; {}'.format(s, retired, (m.get('text') or '')[:1500]), file=sys.stderr)
            continue
        if s not in sessions:
            sessions.append(s)
    try:
        aliases = json.load(open(os.path.join(INBOX_DIR, 'aliases.json')))
    except FileNotFoundError:
        aliases = {}
    low = this_turn_reply(event['transcript_path']).lower()
    missing = [s for s in sessions
               if not any(a.lower() in low for a in [s, s.replace('-', ' ')] + list(aliases.get(s, [])))]
    if missing:
        print(json.dumps({'decision': 'block', 'reason': 'Session reports not relayed to the owner yet: '
                          + ', '.join(missing) + '. Relay the substance of each (results, decisions for him, '
                          'anything blocked), naming the session, then finish.'}))
        return 0
    with open(check, 'w') as stream:
        stream.write(str(hi))
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('general-relay-check.py', body, lambda raw, ev: False,
                           guards='nothing it may refuse on error (a broken check must not trap the conductor)'))
