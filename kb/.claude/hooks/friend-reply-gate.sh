#!/usr/bin/env bash
# friend-reply-gate.sh: trampoline for friend-reply-gate.py, for settings that name a shell hook.
# The gate runs through _hookfail.py; if python3 itself cannot run it, exit 2 refuses the click
# rather than letting it through.
python3 "$(dirname "$0")/friend-reply-gate.py" && exit 0
echo "friend-reply-gate: the gate could not run (exit $?), so this browser action is refused. Repair .claude/hooks/friend-reply-gate.py." >&2
exit 2
