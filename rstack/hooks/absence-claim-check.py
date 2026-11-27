#!/usr/bin/env python3
"""Warn on unsourced absence claims in final messages to the owner."""
import re
import sys

import _hookfail

ABSENCE = re.compile(r"\b(?:never|no record|we didn['’]t|we have not|there is no(?! need\b))\b", re.I)
SOURCE = re.compile(r'\b(?:searched|grep|gmail|kb|index\.md|state\.md|not found in)\b', re.I)


def body(event):
    if event.get('stop_hook_active') or not _hookfail.attended(event):
        return
    message = event.get('last_assistant_message') or ''
    if ABSENCE.search(message) and not SOURCE.search(message):
        _hookfail.warn('Name the sources you searched for this absence claim, or say "not found in X".')


if __name__ == '__main__':
    _hookfail.EVENT = 'Stop'
    sys.exit(_hookfail.run('absence-claim-check.py', body, on_error='warn'))
