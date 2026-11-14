#!/usr/bin/env python3
"""PreToolUse gate for email API sends and drafts: the body must pass your voice check, and an
outreach body needs an exact-byte approval.

Why: a voice guide that a session may or may not load is prose, and the browser reply gates never
see an API send. This makes the voice check part of the send itself. It checks the words only; it
does not decide which channel a reply should go through.

  1. The body (quoted history and HTML stripped) is piped to `voice_command`. Any `FAIL:` line, or a
     nonzero exit with none, refuses the call. A checker that cannot run refuses too.
  2. The exact submitted bytes must match a draft approved with `rh outreach approve` under
     `outreach_root`/lanes/*/OUTREACH.jsonl. `outreach_gate` = warn (default) only warns; deny refuses.

Config: the `email` section of the gates config (_kbgate.py, gates.example.json). Defaults:
voice_command $RH_VOICE_COMMAND, else `voice-check` (rstack/tools/voice-lint works as one);
outreach_root $RH_OUTREACH_ROOT; outreach_gate $RH_OUTREACH_GATE, else warn. The harness keeps a
fuller version of this gate (tools/email-voice-gate.py, with the paper-cut check); this one is the
KB's own, with no dependency on a harness checkout.

Every call this hook is wired to sends or drafts mail, so it is fail_closed: input it cannot check
is refused, never let through.
"""
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kbgate  # noqa: E402

NAME = 'email-voice-gate.py'
GUARDS = 'email API sends and drafts in your name'
BODY_KEYS = ('body', 'text', 'plainText', 'plain_text', 'message', 'content', 'htmlBody', 'html_body', 'html')


def approved_body(tool_input, root):
    """Match the exact submitted UTF-8 bytes; stripping history or HTML is not approval."""
    values = [tool_input[k] for k in BODY_KEYS if isinstance(tool_input.get(k), str) and tool_input[k].strip()]
    if len(values) != 1 or not root:
        return False
    digest = hashlib.sha256(values[0].encode('utf-8')).hexdigest()
    for ledger in Path(root).glob('lanes/*/OUTREACH.jsonl'):
        try:
            latest = {}
            for line in ledger.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    latest[row['id']] = row
            for row in latest.values():
                approval = row.get('approval') or {}
                if row.get('status') == 'approved' and approval.get('sha256') == digest and approval.get('quote'):
                    if hashlib.sha256(Path(row['draft_path']).read_bytes()).hexdigest() == digest:
                        return True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return False


def body_of(tool_input):
    text = '\n'.join(v for v in (tool_input.get(k) for k in BODY_KEYS) if isinstance(v, str) and v.strip())
    if '<' in text and '>' in text:
        text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    # Quoted history ("On ... wrote:" and "> " lines) is someone else's text, not ours.
    text = re.split(r'\n\s*On .{0,200}wrote:\s*\n', text, maxsplit=1)[0]
    return '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('>')).strip()


def warn(reason):
    print(json.dumps({'systemMessage': 'WARNING: ' + reason}))


def body(event):
    tool_input = event.get('tool_input') or {}
    if not isinstance(tool_input, dict):
        raise TypeError('tool_input')
    cfg = _kbgate.config('email')
    command = cfg.get('voice_command') or os.environ.get('RH_VOICE_COMMAND') or 'voice-check'
    command = shlex.split(command) if isinstance(command, str) else [str(c) for c in command]
    text = body_of(tool_input)
    try:
        run = subprocess.run(command, input=text, capture_output=True, text=True, timeout=30)
        fails = [l[5:].strip() for l in run.stdout.splitlines() if l.startswith('FAIL:')]
        if run.returncode and not fails:
            fails = ['voice checker unavailable']
    except (OSError, subprocess.TimeoutExpired):
        fails = ['voice checker unavailable']
    if fails:
        _hookfail.decide('deny', 'Email voice gate: ' + '; '.join(fails)
                         + '. Rewrite in your own voice, run the voice check again, and retry.')
        return 0
    root = _kbgate.path_of(cfg.get('outreach_root'), os.environ.get('RH_OUTREACH_ROOT'))
    if not approved_body(tool_input, root):
        reason = ('Outreach body has no current exact-byte approval. Run: rh outreach draft LANE --to NAME '
                  '--channel email --purpose "what to learn" --file PATH; rh outreach lint LANE ID; read it; '
                  'rh outreach approve LANE ID --quote "your own words". After sending, run '
                  'rh outreach sent LANE ID --message-id M --via api|browser.')
        mode = cfg.get('outreach_gate') or os.environ.get('RH_OUTREACH_GATE') or 'warn'
        if mode == 'warn':
            warn(reason)
        else:
            _hookfail.decide('deny', reason)
    return 0


def triage(raw, event):
    """Every call this hook sees is an email send, draft, reply or forward: all of them are guarded."""
    return True


if __name__ == '__main__':
    try:
        _hookfail = _kbgate.load_wrapper()
    except Exception:
        sys.exit(_kbgate.no_wrapper(NAME, triage, 'email call'))
    sys.exit(_hookfail.run(NAME, body, triage, guards=GUARDS, fail_closed=True, timeout=45))
