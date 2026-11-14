#!/usr/bin/env python3
"""PreToolUse send gate (browser computer-use): a click or key press that sends a NON-email message in
your name (a chat app, a social DM, a comment) needs a voice-cuts PASS from the last 20 minutes.

Why: email had its gate and X posts had their own loop; everything else a session typed and sent
from the browser went out with no check at all. A style rule in prose did not hold, so the send
itself carries the check.

To pass: write the text to a file, cut it from your own messages, list the cuts beside it, run
`rh voice-cuts FILE` (harness/voice_cuts.py writes pass.json with a `utc` field), then send exactly
that text. A file-only send (a photo, no caption) says "no caption" in its action_summary and is
allowed. A prompt typed into a generation tool is not a message in your name and is allowed.

Config: the `voice_send` section of the gates config (_kbgate.py, gates.example.json): the voice-cuts
state directory (default $RH_VOICE_CUTS_STATE, else .runtime/voice-cuts), the window, the phrase lists
and the command named in the refusal. Nothing about any person lives in this file.

A crash on anything that could be a sending click or key press is refused (_hookfail).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kbgate  # noqa: E402

NAME = 'voice-send-gate.py'
GUARDS = 'browser clicks and key presses that send a non-email message in your name'
SEND = re.compile(r'\bsends?\b', re.I)
EMAIL = ('email', 'e-mail', 'gmail', 'reply in thread', 'reply in the thread')
X = ('tweet', 'x post', 'on x', 'x reply')
GENERATION = ('prompt', 'generate', 'generation', 'image model', 'video model')
NO_TEXT = re.compile(r'\bno caption\b|\bwithout (a )?caption\b', re.I)


def body(event):
    cfg = _kbgate.config('voice_send')
    skip = [_kbgate.words_rx(cfg.get(key) or default) for key, default in
            (('email_words', EMAIL), ('own_loop_words', X), ('generation_words', GENERATION))]
    hit = []
    for i in _kbgate.computer_actions(event):
        summary = str(i.get('action_summary', '')) if isinstance(i, dict) else ''
        if (isinstance(i, dict) and i.get('action') in ('left_click', 'key') and SEND.search(summary)
                and not NO_TEXT.search(summary) and not any(rx.search(summary) for rx in skip)):
            hit.append(i)
    if not hit:
        return 0
    minutes = float(cfg.get('window_minutes', 20))
    state = _kbgate.path_of(cfg.get('voice_cuts_state'), os.environ.get('RH_VOICE_CUTS_STATE') or '.runtime/voice-cuts')
    if _kbgate.fresh_stamp(state / 'pass.json', minutes):
        return 0
    command = cfg.get('voice_cuts_command') or 'rh voice-cuts FILE'
    _hookfail.decide('deny', 'voice-send-gate: this sends text in your name with no voice-cuts PASS in the last '
                     '{:g} minutes. Cut the text from your own messages, list the bank lines beside it, run {}, '
                     'then send exactly that text. A file with no caption: say "no caption" in the '
                     'action_summary.'.format(minutes, command))
    return 0


triage = _kbgate.browser_triage

if __name__ == '__main__':
    try:
        _hookfail = _kbgate.load_wrapper()
    except Exception:
        sys.exit(_kbgate.no_wrapper(NAME, triage, 'possible send'))
    sys.exit(_hookfail.run(NAME, body, triage, guards=GUARDS))
