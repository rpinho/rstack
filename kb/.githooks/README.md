# `.githooks/`: enforced KB rules

A rule written only in prose is the weakest kind, because nothing enforces it. The hierarchy this
repo follows is **architecture > compiler > CI/lint > prose**: when a rule matters, find the
highest tier that can enforce it, and keep the prose only as the explanation.

Every rule in `pre-commit` was first a sentence in `AGENTS.md`, and every one was broken anyway.

## Install (once per clone; hook config is not version-controlled)

```bash
git config core.hooksPath .githooks
git config core.hooksPath   # verify: prints .githooks
```

The path is **relative**, so each worktree runs its own tracked copy of the hook, and the setting
lives in the shared `.git/config`, so one command covers the main tree and every worktree.

## What `pre-commit` enforces

| # | Rule | Override |
|---|---|---|
| 1 | **Commit only from a worktree**, never the main tree | `KB_ALLOW_MAIN_COMMIT=1` |
| 2 | **`raw/` is immutable**: additions fine, modify/delete blocked (`raw/_index/` exempt) | `KB_ALLOW_RAW_EDIT=1` |
| 3 | **Never-commit paths**: `.env`, keys, `.pem`, `private/`, `records/`, `credentials` | none: unstage them |
| 4 | **Ingest leaves a day-ledger line**: new `raw/` files need `raw/_index/day-ledger.jsonl` staged too | `KB_NO_LEDGER=1` (backfill), `KB_NIGHTLY=1` (the consumer) |
| 5 | **Hand-over docs don't contradict `state.md`** (`scripts/prep-lint.py`) | `KB_PREP_LINT_SKIP=1` |
| 6 | **Blast radius**: more than 40 staged files is what `git add -A` looks like | `KB_BULK_OK=1` |
| 7 | **A touched `state.md` item opens with its current status**: an opening its own later text (or another item with the same PR/id) overturns is stale (`scripts/state-lint.py --staged`) | `KB_STATE_LINT_SKIP=1` |
| 8 | **No working detail in always-reloaded files** (`state.md`, `index.md`, `goals.md`): a term next to a marker, from your own terms file (`scripts/context-hygiene-lint.py`, `KB_CONTEXT_TERMS`) | `KB_CONTEXT_LINT_SKIP=1` |

Edit `NEVER_COMMIT` at the top of the hook for your own private folders.

## Two bugs that testing caught (kept as a reminder to test, not trust)

1. **The worktree check cannot be a path match.** A worktree can legitimately live *inside* the
   main tree's path. The reliable test: a linked worktree's `git rev-parse --absolute-git-dir`
   contains `/worktrees/`.
2. **`(^|/)(...|\.pem$)` silently allowed `certs/server.pem`.** An extension pattern inside that
   group requires a path *segment* starting with `.pem`. Extension patterns sit outside it.

## Re-running the tests

```bash
scripts/test-hooks.sh
```

It builds a throwaway repo + worktree, exercises every branch of the hook, and checks both the
blocked (exit 1) and override (exit 0) paths. **A hook you have not watched fire is just prose in
a different file.**
