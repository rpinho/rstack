#!/usr/bin/env python3
"""Deny AskUserQuestion in every session except the conductor.

Why: lane sessions sat for days on a question card while the owner was away. The rule "lanes decide,
or send the decision to the conductor" was prose and did not hold. A lane picks the recommended
option when the answer follows from its rules, and otherwise sends the question to the conductor
(relay / tell-general) and keeps working.

Who the conductor is, without a pinned session id (the id changes every time it restarts): its
working directory ends with CONDUCTOR_CWD_SUFFIX, or its tmux session is CONDUCTOR_TMUX (default
`claude-` + CONDUCTOR_NAME). If neither is configured, nobody is exempt.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

REASON = ('lane-no-questions: only the conductor shows question cards. If you would pick the recommended '
          'option, or the answer follows from your rules or memory, do it now and report the decision. If '
          'it really is the owner\'s call, send it to the conductor and keep working on everything else.')


def body(event):
    if not str(event.get('tool_name', '')).endswith('AskUserQuestion'):
        return 0
    if not _hookfail.is_conductor(event):   # one definition, shared with the ask default
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('lane-no-questions.py', body, lambda raw, ev: 'AskUserQuestion' in raw,
                           guards='question cards outside the conductor'))
