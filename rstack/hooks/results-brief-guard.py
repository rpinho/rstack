#!/usr/bin/env python3
"""Deny a subagent brief that doesn't restate the ask and say when it is done.

The rule (one rule, the same one tools/launch.sh lints on every job's STATUS.md): a brief opens with
"You asked: X. I will: Y." and carries a "Done when: <what is visible when it is finished>" line.
X is the owner's goal in their words; Y is the result to deliver, not the process. Drift starts in
the brief, when the goal turns into process, so the goal is restated at the tool boundary.

Checked: Agent (prompt). Not checked: SendMessage (a reply or a relay to a running session, not a
new brief), or any text whose first line carries [followup] or [relay].
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

ASKED = re.compile(r"you asked\b.{0,600}?\bI(?:'ll| will)\b", re.I | re.S)
DONE_WHEN = re.compile(r'\bdone when\b', re.I)
REASON = ('results-brief-guard: open the brief with "You asked: X. I will: Y." and include a "Done when: '
          '<what is visible when it is finished>" line. X = the owner\'s goal in their words; Y = the result '
          'to deliver, not the process. Ask the worker to report results delivered (count them), not activity. '
          'A short follow-up or relay: put [followup] or [relay] on the first line.')


def body(event):
    if event.get('tool_name') != 'Agent':
        return 0
    text = (event.get('tool_input') or {}).get('prompt') or ''
    if not isinstance(text, str):
        raise ValueError('prompt is not a string')
    first = text.strip().splitlines()[0].lower() if text.strip() else ''
    if not text.strip() or '[followup]' in first or '[relay]' in first:
        return 0
    if not (ASKED.search(text[:1500]) and DONE_WHEN.search(text[:3000])):
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    # Only Agent briefs are guarded; on its own failure it asks (a lost brief costs more than a prompt).
    sys.exit(_hookfail.run('results-brief-guard.py', body, lambda raw, ev: '"Agent"' in raw,
                           guards='subagent briefs', on_error='ask'))
