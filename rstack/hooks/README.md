# rstack hooks

Claude Code PreToolUse guards. Each runs inside `_hookfail.run`, so an internal error on a call it guards refuses instead of allowing ([a guard must refuse, not crash](../principles/a-guard-must-refuse-not-crash.md)), and each has its test in `../tests/test_rstack_hooks.py`. Wiring: `settings.example.json`. State goes to `$RSTACK_STATE_DIR` (default `~/.local/state/rstack`).

- `_hookfail.py`: the fail-safe wrapper. Five of the guards it was written for ended `except Exception: exit(0)`, and one of them let a machine be created with no shutoff.
- `poll-guard.py`: denies the third identical foreground status check in 30 minutes and points at `event-watch wait` in the background. Sessions told in prose to stop polling kept polling; it denies a repeat within 30 minutes of the last one. The one guard that stays fail-open, because it saves turns, not losses.
- `trash-guard.py`: denies Finder-scripted deletes; use `/usr/bin/trash`. Finder plays a sound per item and the owner had to ask twice for it to stop.
- `block-main-tree-commit.py`: denies a `git commit` in a protected main checkout (and asks, rather than allows, on its own internal error) (`RSTACK_MAIN_TREES`). A session committed straight onto main while its worktree had the same files; the first version then guarded a moved path for four months, so it now reports a dead path.
- `pod-deadline-gate.py`: refuses a pod whose start command does not end the pod itself within a day. "Remember to stop it" dies with the session; a pod that never shut off is the failure.
- `pod-create-gate.py`: runs the repo's capacity-receipt gate (`tools/pod-create-gate.py`) fail-safe. An import error used to exit 1, which Claude Code treats as allow.
- `conductor-inbox-gate.py`: denies direct SendMessage to the conductor session; workers use `relay`. Every wake replays the conductor's whole context to deliver what was usually an FYI.
- `read-the-thread-first.py`: denies a browser click that sends an email unless the session pulled the page text in the last 30 minutes. Wrong replies were wrong about the question, not the voice; a screenshot does not count as a read.
- `settings.example.json`: the matchers each hook is meant for.
