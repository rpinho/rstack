#!/usr/bin/env python3
"""PreToolUse send gate (browser computer-use): a click that sends an email reply needs proof that a
person-shaped check ran on the exact text first.

Why: replies sent from the browser had no check at all. The click is the one place every reply
passes, so the gate sits there. It allows the click when either is fresh (default 20 minutes):
  - a reply-lint PASS stamp: a JSON file with a `utc` field, written by whatever lint you run on a
    reply against the message it answers (`reply_lint_stamp`; for example the outreach lint), or
  - an `rh outreach approve` under `outreach_root`/lanes/*/OUTREACH.jsonl with the approver's own
    quote: a cold email has no incoming message to lint, and the approval is the same proof.
X posts, DMs and texts are not this gate's business (voice-send-gate covers non-email sends).

Config: the `friend_reply` section of the gates config (_kbgate.py, gates.example.json). It holds
every path, the phrase lists that recognise an email send, the lint command named in the refusal
and any line of your own to add to it. Nothing about any person lives in this file.

A crash on anything that could be a sending click is refused (_hookfail); before the wrapper, the
inline version crashed on unreadable input and the crash let the click through.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kbgate  # noqa: E402

NAME = 'friend-reply-gate.py'
GUARDS = 'browser clicks that send an email reply in your name'
SEND = re.compile(r'\bsends?\b', re.I)
EMAIL = ('email', 'e-mail', 'gmail', 'reply in thread', 'reply in the thread', 'reply to')
NOT_EMAIL = ('tweet', 'x post', 'on x', 'dm', 'text message', 'sms')


def body(event):
    cfg = _kbgate.config('friend_reply')
    email = _kbgate.words_rx(cfg.get('email_words') or EMAIL)
    not_email = _kbgate.words_rx(cfg.get('not_email_words') or NOT_EMAIL)
    hit = [i for i in _kbgate.computer_actions(event)
           if isinstance(i, dict) and i.get('action') == 'left_click'
           and SEND.search(str(i.get('action_summary', ''))) and email.search(str(i.get('action_summary', '')))
           and not not_email.search(str(i.get('action_summary', '')))]
    if not hit:
        return 0
    minutes = float(cfg.get('window_minutes', 20))
    if _kbgate.fresh_stamp(_kbgate.path_of(cfg.get('reply_lint_stamp')), minutes):
        return 0
    if _kbgate.recent_approval(_kbgate.path_of(cfg.get('outreach_root'), os.environ.get('RH_OUTREACH_ROOT')),
                               minutes):
        return 0
    lint = cfg.get('reply_lint_command') or 'rh outreach lint LANE ID'
    reason = ('friend-reply-gate: this click sends an email with no reply-lint PASS and no outreach approval in '
              'the last {:g} minutes. Run {} on the draft against their message, get PASS (or an `rh outreach '
              'approve` with your own quote), then send exactly that text.'.format(minutes, lint))
    if cfg.get('extra_reason'):
        reason += ' ' + str(cfg['extra_reason'])
    _hookfail.decide('deny', reason)
    return 0


triage = _kbgate.browser_triage

if __name__ == '__main__':
    try:
        _hookfail = _kbgate.load_wrapper()
    except Exception:
        sys.exit(_kbgate.no_wrapper(NAME, triage, 'possible send'))
    sys.exit(_hookfail.run(NAME, body, triage, guards=GUARDS))
