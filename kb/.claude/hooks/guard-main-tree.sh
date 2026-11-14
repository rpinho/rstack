#!/usr/bin/env bash
# guard-main-tree.sh: PreToolUse hook (Edit|Write|NotebookEdit). Works for Claude Code and Codex.
# The logic lives in guard-main-tree.py, which runs through _hookfail.py and refuses rather than
# allows when it cannot check a main-tree edit. This file stays so settings and every reference keep
# working. If python3 itself cannot run the guard, exit 2 refuses the edit rather than letting it through.
python3 "$(dirname "$0")/guard-main-tree.py" && exit 0
echo "guard-main-tree: the guard refused this edit, or could not run (exit $?). If it could not run, repair .claude/hooks/guard-main-tree.py." >&2
exit 2
