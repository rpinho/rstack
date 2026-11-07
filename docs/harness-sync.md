# Harness sync: one source for the installed copy

An installed harness that people fix in place drifts from its repo. Each copy ages differently: a fix lands in one and not the other, and a later install silently undoes it. One source, plus a scheduled check, is the fix.

`harness/tools/harness-sync/harness_sync.py` installs the git-tracked files under `harness/` at a committed ref (default `main`) into the installed root. It never reads the working tree, so a half-finished edit cannot reach running lanes. Lanes, ledgers and other runtime state in the root are never touched.

```sh
harness-sync --check   # report drift, change nothing; exit 2 if any
harness-sync --auto    # install only a clean fast-forward; else report and exit 2
harness-sync           # install the ref; hand edits and stray modules are backed up first
```

Drift kinds: `MISSING` (in the ref, not installed), `BEHIND` (installed file matches the last install, the ref moved on), `EDITED` (changed in place since the last install), `STRAY` (an installed `.py`/`.sh` the ref doesn't have), `REMOVED` (deleted from the ref). `--auto` installs only `MISSING`/`BEHIND`/`REMOVED`, and never while a launchd job whose label contains `research-harness` has a PID. Installed files are read-only, so editing one fails instead of drifting. Every replaced or removed file is copied to `--backups/<utc>/` first, and removals go to Trash. `<root>/.harness-sync.json` records the installed commit.

Run `--auto` from the same scheduled tick as `lane-rules-sync` and `lane-yield`. To change installed behaviour: commit to the repo, then let the tick (or a manual `harness-sync`) install it.

Host-specific values (paths, lane sets, notifier commands) never go in the repo. Put them in `~/.config/research-harness/env` (or `$RH_ENV_FILE`) as `KEY=VALUE` lines. `harness/settings.py` reads it at import, so every entry point sees the same values, and the real environment always wins. See [configuration](configuration.md) for the keys.

Tests: `tests/test_harness_sync.py`, `tests/test_host_settings.py`.

## The second machine

A `--host` job runs the executor on the other machine, so it runs THAT machine's installed harness,
not its git checkout. 11-07: the host's installed copy was at 906efdc while the controller was at
ff47140, and the one commit between them touching `agent_executor.py` was the codex sandbox fix, so
`--host` jobs ran an executor the controller had already fixed. The host's own checkout was at
dee270d, older still than what it was running, so having the host follow `origin/main` and install
for itself would have installed older code than it already had.

One source, extended outward rather than duplicated:

- `harness-sync --host HOST` installs the same committed ref onto the host from here. It refuses
  unless this machine is already at that ref, because installing outward from a drifted controller
  spreads the drift. It verifies every file by hash on the host with `git hash-object` before
  writing the receipt, so a half-arrived install cannot claim a commit, and it removes nothing
  there, because a deletion over ssh is a deletion nobody watched. `--host HOST --check` reports
  and changes nothing.
- `RH_HARNESS_HOSTS` (comma or space separated) names the hosts this controller keeps current.
  After a local install, `harness-sync` installs outward to each, so the scheduled tick that
  already runs `harness-sync --auto` keeps them current with no second schedule. A host it cannot
  reach is reported, not fatal: a sleeping second machine must not break the tick.
- The launchers and the sweep refuse a `--host` run when the two machines' receipts differ, naming
  both commits and the command that fixes it. Unreadable is a refusal too: a job that cannot be
  shown to be running the right code is not run.
