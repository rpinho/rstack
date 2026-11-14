# Repo freshness: every clone and backup on every host

On 11-13 an audit found 8 stale public repos, 7 stale or missing retros, and live code that differed from the repo it came from. Nothing had failed; each had aged. Three tools turn that audit into code, highest layer first.

**Numbers are rendered, not typed.** `rstack/tools/readme-blocks` fills marked blocks in a README, `<!-- auto:NAME -->...<!-- /auto -->`, from their source: a GitHub pull request count, a count or the latest value in a JSONL ledger such as `lanes/<lane>/RESULTS.jsonl`, or a command's output. The mapping is `readme-blocks.json` next to the README. `readme-blocks render README.md` rewrites the blocks; `readme-blocks check README.md` exits 1 and names each stale block. A source it cannot read is an error (exit 2), never a pass. For a published repo the blocks live in the private source, and the publish carries them out.

**A public result is not logged until the README shows it.** A lane that publishes declares `lanes/<lane>/PUBLIC.json`:

```json
{"repo": "~/dev/demo", "readme": "README.md", "config": "readme-blocks.json"}
```

`log-result --new yes` then renders the README's blocks against the ledger plus the new row and refuses unless the README committed at the repo's HEAD already equals that render. The refusal prints the render command and the `--utc` to log the row again with. A lane with no public repo passes `--private`, and the row records `private: true`.

**A nightly check fails on drift.** `rstack/tools/repo-freshness` lists every public repo of the configured owners and its kind:

- **pushed**: the public repo is the working clone. In addition to the clone checks below, it checks local branches that track the public default branch while carrying commits not on it (a plain push would publish them).
- **published**: the public repo is a release of a private repo through a `PUBLISH` whitelist (`publish-public`). Drift is a difference between what a publish would export now (whitelisted files committed at the source's HEAD, agent working files dropped) and the public default branch. The private repo being ahead of or behind the public one is not drift.
- **archived** repos are listed, not checked; **declared** ones have no clone on purpose and a reason in the config.
- **unknown**: a public repo with no clone, no `PUBLISH` source and no declaration. This is a failure: every public repo needs exactly one way in.

**Every clone is checked, including private repos and repos with no remote.** Each root can name an ssh `host`, so a single run covers multiple machines. Overlapping roots are deduplicated. Git worktrees with a `.git` file are included. The checks run independently of GitHub's public inventory, even if that inventory fails:

- **behind**: the current branch is behind its upstream; reports `behind N`.
- **no-upstream**: the current branch has no resolvable upstream, including a detached HEAD. An exact `detached` entry suppresses this finding only while that checkout is detached.
- **dirty**: tracked or untracked changes, respecting `.gitignore`, whose oldest file mtime exceeds `dirty_max_hours` (default 24). Reports the file count and oldest age. Renames count once; for a deleted file, the nearest surviving parent directory's mtime is used because the file no longer has one. This measures file age, not the time the edit was made.
- **unpushed**: commits on the current branch absent from its upstream, with at least one committer timestamp older than `unpushed_max_hours` (default 24). Reports the total ahead count and oldest age. A copy on another remote does not count as pushed to this upstream. Without an upstream, the separate no-upstream finding applies.
- **fetch**: when `fetch: true`, one `git fetch --all --no-recurse-submodules` per clone per run, with a 30-second timeout. A failure is a finding; other checks still run against the available refs. Fetch defaults to false, using cached tracking refs. Fetch never pulls or merges.

Each discovered path must be its own checkout root; an invalid `.git` directory that makes Git fall back to a parent checkout is reported as a read error. Status has a 120-second limit. If it fails, the error is reported alongside any upstream findings already available for that clone.

It also checks README auto-blocks against a fresh render, installed files against the repo copy as committed, each retro against its lane's results (a result left out of the retro for more than 7 days fails), and backups. The original `match` backup form checks that a scheduled launchd job or crontab line runs the command. A `repo` backup entry checks the newest commit reachable from HEAD or any local/fetched ref against `max_hours` (default 48). This includes fetched remote commits even when the checked-out branch is behind. Empty or unreadable backup clones produce findings. A backup may have both `repo` and `match`; both checks run. Backup clones outside the roots are also read and fetched if enabled, sharing the same per-run cache.

For example:

```json
{
  "owners": ["example-owner"],
  "roots": [
    {"path": "~/dev", "depth": 3},
    {"path": "~/dev", "depth": 3, "host": "other-mac"}
  ],
  "exclude": ["~/dev/scratch/*"],
  "fetch": true,
  "dirty_max_hours": 24,
  "unpushed_max_hours": 24,
  "detached": [{"path": "~/dev/pinned", "host": "other-mac"}],
  "alert_hours": 24,
  "backups": [
    {"name": "notes", "match": "backup-notes"},
    {"name": "results", "repo": "~/dev/results-backup", "host": "other-mac", "max_hours": 48}
  ]
}
```

`owners` may be empty or omitted for a clone/backup-only scan. Paths beginning with `~` and exclusions expand against each entry's host home. Clone findings name the host (`local` on the scanning machine), path and counts/ages. Problems go to `$RSTACK_STATE_DIR/asks-waiting/<host>-repos.tsv`, one row per clone and kind (public branch safety findings remain aggregated per public repo), which the conductor sees on every turn.

`--alert CMD` receives one line as its last argument: total findings, counts by kind, and the first five findings with details. It sends at most once per `alert_hours` (default 24; 0 sends every run with findings). Persistent problems are paged again after that interval; new findings within it wait for the next eligible run. A successful send is recorded in `$RSTACK_STATE_DIR/repo-freshness/last-alert.json`; a failed send is printed to stderr and can be retried next run. `job-health` retains its own alert behavior.

`--dry` prints the inventory and problems, writes no report state, sends no alerts, and exits 1 if it finds a problem. For a strictly read-only scan, also set `fetch: false`: an enabled fetch updates Git refs even with `--dry`. Normal runs exit 0 after reporting findings.

The config shape is in the tool's docstring (`repo-freshness --help`); the default path is `~/.config/rstack/repo-freshness.json`. Tests: `rstack/tests/test_readme_blocks.py`, `rstack/tests/test_repo_freshness.py`.
