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
    # Import inside the fail-safe body: a missing install must refuse, not crash
    # before _hookfail can emit a deny. The same hook runs from repo or ~/.claude.
    from pathlib import Path
    source_tools = Path(__file__).resolve().parents[1] / 'tools'
    if 'RSTACK_TOOLS' in os.environ:
        tools = Path(os.environ['RSTACK_TOOLS']).expanduser()
    elif (source_tools / 'ask_lint.py').is_file():
        tools = source_tools
    else:
        tools = Path.home() / '.local/share/research-harness/rstack/tools'
    sys.path.insert(0, str(tools))
    from ask_lint import lint
    for question in event.get('tool_input', {}).get('questions', []):
        # Descriptions explain the option's work, often the agent's own plan.
        # Only the question and option labels ask the owner to do something.
        texts = [question.get('question', '')]
        for option in question.get('options', []):
            texts.append(option.get('label', ''))
        messages = lint('\n'.join(texts))
        if messages:
            _hookfail.decide('deny', '\n'.join(messages))
            return 0
    if not _hookfail.is_conductor(event):   # one definition, shared with the ask default
        _hookfail.decide('deny', REASON)
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('lane-no-questions.py', body, lambda raw, ev: 'AskUserQuestion' in raw,
                           guards='mechanical owner asks and question cards outside the conductor'))
