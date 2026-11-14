# Repo freshness: public repos cannot drift silently

On 11-13 an audit found 8 stale public repos, 7 stale or missing retros, and live code that differed from the repo it came from. Nothing had failed; each had aged. Three tools turn that audit into code, highest layer first.

**Numbers are rendered, not typed.** `rstack/tools/readme-blocks` fills marked blocks in a README, `<!-- auto:NAME -->...<!-- /auto -->`, from their source: a GitHub pull request count, a count or the latest value in a JSONL ledger such as `lanes/<lane>/RESULTS.jsonl`, or a command's output. The mapping is `readme-blocks.json` next to the README. `readme-blocks render README.md` rewrites the blocks; `readme-blocks check README.md` exits 1 and names each stale block. A source it cannot read is an error (exit 2), never a pass. For a published repo the blocks live in the private source, and the publish carries them out.

**A public result is not logged until the README shows it.** A lane that publishes declares `lanes/<lane>/PUBLIC.json`:

```json
{"repo": "~/dev/demo", "readme": "README.md", "config": "readme-blocks.json"}
```

`log-result --new yes` then renders the README's blocks against the ledger plus the new row and refuses unless the README committed at the repo's HEAD already equals that render. The refusal prints the render command and the `--utc` to log the row again with. A lane with no public repo passes `--private`, and the row records `private: true`.

**A nightly check fails on drift.** `rstack/tools/repo-freshness` lists every public repo of the configured owners and its kind:

- **pushed**: the public repo is the working clone. Drift is a clone with uncommitted changes, a checked-out branch with commits on no remote, or a local branch that tracks the public default branch while carrying commits not on it (a plain push would publish them).
- **published**: the public repo is a release of a private repo through a `PUBLISH` whitelist (`publish-public`). Drift is a difference between what a publish would export now (whitelisted files committed at the source's HEAD, agent working files dropped) and the public default branch. The private repo being ahead of or behind the public one is not drift.
- **archived** repos are listed, not checked; **declared** ones have no clone on purpose and a reason in the config.
- **unknown**: a public repo with no clone, no `PUBLISH` source and no declaration. This is a failure: every public repo needs exactly one way in.

It also checks README auto-blocks against a fresh render, installed files against the repo copy as committed, each retro against its lane's results (a result left out of the retro for more than 7 days fails), and that each backup command is run by a scheduled launchd job or crontab line. Each config entry can name an ssh host, so one run on one machine covers both. Problems go to `$RSTACK_STATE_DIR/asks-waiting/<host>-repos.tsv`, one row per repo and kind, which the conductor sees on every turn. `--alert CMD` runs once for each new problem, the same way `job-health` reports. `--dry` prints the inventory and problems, writes nothing, and exits 1 if it finds a problem.

The config shape is in the tool's docstring (`repo-freshness --help`); the default path is `~/.config/rstack/repo-freshness.json`. Tests: `rstack/tests/test_readme_blocks.py`, `rstack/tests/test_repo_freshness.py`, `tests/test_public_readme.py`.
