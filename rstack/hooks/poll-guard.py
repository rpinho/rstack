#!/usr/bin/env python3
"""PreToolUse(Bash) guard: stop a session burning turns on repeated status polling.

Why: three long-running orchestrator sessions were told, in prose, to wait on `event-watch` in a
BACKGROUND task instead of polling. They kept polling. Every foreground check is a whole turn that
re-reads a context of a few hundred thousand tokens. One day's count was 103 foreground status
checks against 3 background waits.

Honest measurement after it shipped: zero denials in its first 26 hours. The 103 came from a loose
regex (any `status` or `tail`); only 9 of the 103 match the patterns below. It stays as a backstop.

What it does: fingerprints foreground Bash commands that only LOOK at state (ssh ... cat/tail/ls/ps,
tail/cat of a log, a provider's get-pod/list-pods, a status flag file). The first two identical
checks in a 30-minute window pass. The third is DENIED with instructions to wait on
`event-watch wait <job>` as a background task.

Deliberately narrow and escapable:
  - only foreground Bash (`run_in_background: true` is always allowed),
  - only read-only-looking commands; anything that writes, builds, submits or edits is never matched,
  - a command containing `# poll-ok` is always allowed, so a session with a real reason to look
    again pays one comment, not a wall.

The one guard here that stays fail-OPEN, on purpose: it prevents a wasted turn, not a loss.
Denying every read-only Bash command because its state file went bad would cost far more than the
polling it stops. What it must not be is silent: an internal error prints to stderr.

State: $RSTACK_STATE_DIR/poll-guard/<session>.json (fingerprints and timestamps, never commands).
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

WINDOW_S = 30 * 60      # how long a fingerprint is remembered
FREE_CHECKS = 2         # identical checks allowed inside the window

# A command must look like one of these to be a "status check" at all.
STATUS = re.compile(
    r"(^|[;&|]\s*)(tail|cat|head|ls|stat|wc)\b[^|;&]*\.(log|out|err|json|flag|txt)"
    r"|\bssh\b[^|;&]*\b(cat|tail|ls|ps|nvidia-smi|squeue|qstat|du|df|wc|grep -c)\b"
    r"|\bget-pod\b|\bget-job-status\b|\blist-pods\b|\bendpoint-health\b"
    r"|\bevent-watch\s+(list|scan)\b"
    r"|\bps\b[^|;&]*\b(aux|-o)\b",
    re.I,
)
# Anything that changes state is never a poll, whatever else it matches.
MUTATES = re.compile(
    r"\b(rm|mv|cp|mkdir|touch|tee|chmod|chown|kill|pkill|scp|rsync|git|pip|npm|make|"
    r"python3?\s+\S+\.py|nohup|codex|claude|curl\s+-X|create-|delete-|update-|"
    r"run-endpoint|pod-action|submit)\b|>\s*\S|>>\s*\S",
    re.I,
)
NOISE = re.compile(r"\d+|'[^']*'|\"[^\"]*\"|/[A-Za-z0-9_.\-/]+")

REASON = (
    "[poll-guard] This is check #{n} of the same thing in {mins} min, and each one costs a full "
    "turn that re-reads your whole context. Don't look again; be told.\n"
    "Add what you are waiting for to an event-watch job (new <glob> for a result, match <log> "
    "<regex> for errors or exit lines, stale <glob> <min> for a hang, pid <pid> for a crash, "
    "deadline <ISO>), then run `event-watch wait <job>` as a BACKGROUND Bash task "
    "(run_in_background: true). It blocks until something happens and the completion notification "
    "wakes you; re-run it after each exit.\n"
    "If you genuinely need this one look now, re-send the same command with `# poll-ok` appended.")


def fingerprint(cmd):
    """Collapse literals so `tail -5 a.log` and `tail -20 a.log` are the same check."""
    return NOISE.sub("#", " ".join(cmd.split()))[:160]


def is_poll(cmd):
    return bool(STATUS.search(cmd)) and not MUTATES.search(cmd)


def body(ev):
    if ev.get("tool_name") != "Bash":
        return 0
    inp = ev.get("tool_input") or {}
    cmd = str(inp.get("command") or "")
    if inp.get("run_in_background") or "# poll-ok" in cmd or not is_poll(cmd):
        return 0

    sid = re.sub(r"[^A-Za-z0-9_\-]", "", str(ev.get("session_id", "x")))[:64] or "x"
    directory = _hookfail.state_dir("poll-guard")
    path = directory / (sid + ".json")
    now = time.time()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        seen = json.loads(path.read_text())
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    seen = {k: v for k, v in seen.items() if isinstance(v, list) and v and now - v[-1] < WINDOW_S}
    hits = seen.setdefault(fingerprint(cmd), [])
    hits.append(now)
    path.write_text(json.dumps(seen))

    if len(hits) > FREE_CHECKS:
        _hookfail.decide("deny", REASON.format(n=len(hits), mins=int((now - hits[0]) / 60)))
    return 0


if __name__ == "__main__":
    # triage always False: an error never denies here, it allows and reports. See the docstring.
    sys.exit(_hookfail.run("poll-guard.py", body, triage=lambda raw, event: False,
                           guards="repeated foreground status polling (cost only)"))
