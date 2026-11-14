# CLAUDE.md: Claude Code overlay

**Read [`AGENTS.md`](./AGENTS.md) first.** It is the canonical operating manual for this KB. This file only adds Claude-Code-specific notes; everything substantive lives in `AGENTS.md` so the KB stays portable across runtimes.

## Where you are, and where to edit

- This session should be running in a **session worktree** (cwd like `~/.worktrees/<kb>/<adjective-noun>/`), created by `kb-claude` from `shell/kb-launcher.zsh`. All tracked edits and all commits happen here; then you land.
- **Before every `git commit`:** `git rev-parse --show-toplevel` should print a worktree path. If it prints the main tree, stop. (The pre-commit hook and the `guard-main-tree` hook will stop you anyway; don't make them.)
- The main tree may be exposed to you read-only (e.g. via `--add-dir`) for gitignored private files that exist only there. Read from it; never edit tracked files in it.

## Hooks wired in `.claude/settings.json`

- **PreToolUse `guard-main-tree.sh`** (Edit/Write/NotebookEdit): blocks edits to tracked files in the main tree and new files in its tracked areas. Worktrees, gitignored paths and scratch areas pass.
- **PreToolUse send gates** (browser computer-use and Gmail tools): `friend-reply-gate.py`, `voice-send-gate.py`, `email-voice-gate.py`. A send with no fresh check is refused; so is one the gate cannot read. Config: `~/.config/kb/gates.json` (see `.claude/hooks/gates.example.json`).
- **SessionStart `inject-title-index.sh`**: injects every wiki page title (via `scripts/kb-title-index.sh`) so "do we have a page on X?" is answerable before any search. Use it before claiming something was never documented.
- **Permissions deny** `rm -rf`, force-push, `reset --hard`, `branch -D`, `git add -A`.

## Claude-specific notes

- Skills live in `.claude/skills/` as a byte-identical mirror of `.agents/skills/`.
- When the human says **"land"** / **"merge"** / **"push to main"**, follow the [`land`](.claude/skills/land/SKILL.md) skill exactly; never a plain `git merge`/`git push`.
- Commit with explicit pathspecs; never `git add -A`.
- Every ingest ends with `python3 scripts/day-ledger.py add ...` staged in the same commit (AGENTS.md -> Ingest, step 6).
- For a cross-lab second opinion, the other lab's CLI can be run headless (e.g. `codex exec --skip-git-repo-check "<prompt>" </dev/null`; the `</dev/null` matters, or a backgrounded run waits forever on stdin). Check which account and gateway it is configured for before sending it personal content.
