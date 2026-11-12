#!/usr/bin/env python3
"""SubagentStop: a subagent's final report opens with "You asked: X" and says what shipped.

The report side of the same rule tools/launch.sh lints on every job (REPORT.md opens "Shipped:"):
"You asked: X. Shipped: Y", with a count of results delivered, never activity. Reports that list
activity (runs, checks, files read) are how busy work reaches the owner looking like progress.

Blocks the stop once with the reason, so the subagent rewrites its report. stop_hook_active lets a
second stop through, and any error lets it through (with a stderr line): a report guard degrades,
it never suppresses a report.
"""
import json
from pathlib import Path
import re
import sys

ASKED = re.compile(r'you asked\b', re.I)
REASON = ('results-report-guard: rewrite your final report so it opens "You asked: X. Shipped: Y" (the '
          'goal, then the result delivered), followed by the count of results actually delivered, not '
          'activity. If nothing was delivered, say so plainly in that first line. Keep everything else.')


def last_text(path):
    p = Path(path)
    if not p.is_file():
        return ''
    with p.open('rb') as f:
        f.seek(max(0, p.stat().st_size - 400_000))
        lines = f.read().decode('utf-8', 'replace').split('\n')   # not splitlines(): U+2028 inside JSON splits a record
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get('message') or {}
        if rec.get('type') == 'assistant' and isinstance(msg, dict):
            parts = [c.get('text', '') for c in msg.get('content') or [] if isinstance(c, dict) and c.get('type') == 'text']
            if any(parts):
                return '\n'.join(parts)
    return ''


def main():
    try:
        data = json.loads(sys.stdin.read())
        if data.get('stop_hook_active'):
            return 0
        text = data.get('last_assistant_message') or last_text(
            data.get('agent_transcript_path') or data.get('transcript_path') or '')
        if text and not ASKED.search(text[:400]):
            print(json.dumps({'decision': 'block', 'reason': REASON}))
    except Exception as exc:
        print('[results-report-guard.py] internal error ({}); the report went through. The hook needs '
              'repair.'.format(type(exc).__name__), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
