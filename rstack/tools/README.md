# rstack tools

Standalone scripts (Python 3.9+ standard library, plus bash for `clean-room`; `ui-golden` uses Playwright and Pillow). Tests live under `../tests/`. Private-content filters take your own term files; the model instruction guard uses public model spellings.

- [`ui-golden`](ui-golden.md): render a viewport with Playwright, compare exact pixels with an optional rectangular mask, and explicitly approve a new golden. Comparison never approves; missing goldens and differences refuse. Profiles and screenshots belong outside public source trees.

- `event-watch`: wakes a session only when a configured event happens (new file, stale output, dead pid, log match, deadline). One overnight watcher loop spent about 3,300 turns and 19 compactions confirming nothing had changed.
- `fleet-context-watch`: on a schedule, asks each tmux-hosted Claude Code session over a context threshold to save its state and reply `SAVED <path>`, then types `/compact` once that reply is in and the session is quiet. Its first version read only the latest reply, so a SAVED buried under a later reply left two sessions at 530k and 680k for hours; the test pins that.
- `voice-lint`: `--measure` profiles your own writing (sentence length, contractions, hedges, exclamations, em dashes) so a voice guide can state numbers; check mode refuses a draft with a phrase from your private slop list, an em dash or too many exclamation marks, and works as the harness's `RH_VOICE_COMMAND`. `slop.example.txt` has generic entries only.
- `relay`: files a message for the conductor session, waking it only for decisions, owner requests and breakages, and quarantines messages that match your terms file, logging a count and never the terms. Relayed detail from a sensitive project stalled the conductor on a safety classifier, and naming the terms in the inbox row stalled it again.
- `egress-gate`: refuses to pass a directory, a push or a text that contains secret shapes or your own patterns and terms (exit 2). Agents build public output on a machine that holds private context, and checking by hand was prose.
- `clean-room`: runs codex or claude in an empty identity for work that will leave the machine. A fresh config dir still loaded the personal CLAUDE.md from the home directory, an ancestor of the workspace.
- `reload-lint.py`: blocks a commit that puts a configured term next to a configured working-detail marker in a file every session reloads, printing markers and counts, never the terms. An index line carrying a project's working detail stalled every general-purpose session that reloaded it.
- `hook-audit`: feeds every registered PreToolUse guard malformed events (unparseable text, a string or list instead of an object, fields of the wrong type) shaped like the action it guards, and lists the ones that crash. Claude Code treats a crash as allow, so a guard that raises on input it cannot read is no guard. Its first run found three send gates on one machine that did exactly that.
- `hook-wrap-check`: the rule itself as a check. Every registered PreToolUse guard (user settings, and each project in the host's policy file) must be a Python hook that calls `_hookfail.run(`, or be on the allowlist (`~/.config/rstack/hook-allowlist.json`) with a reason and, for a temporary exception, an `until` date. A shell guard counts only through a Python shim that uses the wrapper, and a registered file that is missing fails. `tests/test_hook_policy.py` runs it, and hook-audit, against the live settings on any host with a policy file, so the suite (and the install script, which runs the suite) fails on a new unwrapped guard.
- `instruction-refs`: fails when an instruction file (CLAUDE.md, AGENTS.md, a skill, a memory note) names a link, a repo path, an `rh` subcommand or action, an `rh` option or, with `--local`, a `~/` path that no longer exists. Agents follow a stale instruction over the code about 90% of the time (SmartScope); one of our guards protected a path deleted months earlier. Its test is `../../tests/test_instruction_refs.py`.
- `_terms.py`: the shared terms-file reader, and the reason there is no built-in list.
- `terms.example.txt`: the terms-file format, with placeholder words only.
- `asks-waiting`: lists lane sessions resting on a question or on a permission prompt, and our PRs idle 6 h+, one line per repo; `--hook` prints the list in the conductor session on every turn. Run it from a scheduler on each machine (`--push HOST` copies a machine's list to the conductor's). Three lanes once sat stopped for three days unnoticed.
- `osascript`: a shim installed first on PATH (`~/.local/bin`). A Finder delete becomes `/usr/bin/trash` (same Trash and Put Back, no sound); anything else goes to the real osascript unchanged. Agents kept deleting through Finder despite a written rule, and the owner heard every item. `tools/launch.sh` and the harness's `agent_executor` refuse a job where it would not be the osascript found.
- `job-health`: every scheduled job's failure reaches a person, not just its log. It lists launchd jobs whose last run exited with a code they don't declare as fine, and required outputs (a registry with max ages) that are missing or stale, into the conductor's asks-waiting list while they last, and alerts once per new problem. Twice in one day a failure only reached a log: a crashed step left X rounds working from a 72-hour-old list for two days, and a lane sat idle with its result in.
- `readme-blocks`: renders and checks the marked blocks in a README (`<!-- auto:NAME -->...<!-- /auto -->`) from a PR count, a JSONL ledger or a command, so no number in a README is typed by hand. An audit on 11-13 found 8 public READMEs out of date. `log-result` uses it to refuse a public result until the README shows it. Its test is `../tests/test_readme_blocks.py`.
- `repo-freshness`: the nightly check that every public repo is pushed (a clone) or published (a PUBLISH whitelist) and has not drifted: dirty or unpushed clones, private commits on a branch tracking public main, an export that differs from the public repo, stale README blocks, live code that differs from the repo, stale retros and unscheduled backups. Reports like `job-health`, one row per repo and kind. Its test is `../tests/test_repo_freshness.py`; see [repo freshness](../../docs/repo-freshness.md).
- `model-instruction-gate`: refuses model names in the same sentence as a judgment instruction in SendMessage text, `tell-general` arguments, or Write/Edit content under `lane-briefs`. Also refuses Sonnet/Haiku Agent calls when their description or prompt contains a judgment word in any sentence, and Bash commands with judgment text that run `claude --model/-m` on Sonnet/Haiku or `codex exec --model/-m` on an explicit model. Refusals direct callers to `launch.sh --role review --made-by MODEL`. Tests: `../tests/test_model_instruction_gate.py`. It uses `../hooks/_hookfail.py` to refuse guarded malformed events and report unrelated errors.
- `leaderboard-freshness LEADERBOARD.md`: checks the newest table Date (default `--max-age-days 2`) and whether models in `--used FILE` have a routing role row. Canonical/native version spellings are normalised. `--used-from-receipts DIR` reads `*.selection.json` recursively and uses selection `utc` timestamps from the last seven days, not file modification times. `--alert` calls `tell-general fyi "..."` once per failing UTC day, recording it under `RSTACK_STATE_DIR` (default `$XDG_STATE_HOME/rstack`), then runs `--refresh-command 'executable args'` if supplied; that command uses shell quoting but no shell expansion. Refresh does not change the current failure exit status. Tests: `../tests/test_leaderboard_freshness.py`.

Register the instruction gate in the desired Claude Code `settings.json` with this PreToolUse matcher. Set `RSTACK_ROOT` to the directory containing this `tools/` and its sibling `hooks/`; keep the two together. Registration is an operator step; the tool does not edit settings.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "SendMessage|Agent|Bash|Write|Edit",
        "hooks": [{"type": "command", "command": "python3 \"$RSTACK_ROOT/tools/model-instruction-gate\"", "timeout": 10}]
      }
    ]
  }
}
```

## xurl

The gated wrapper is the only supported path to the X API. Put it first on every agent and scheduled job's PATH, with `xurl-policy` beside it; keep the original executable at a separate configured path. This is an operator installation step. The wrapper evaluates and logs the policy before executing the original binary, preserves its arguments, output and exit code, and returns **86** on refusal. An unreadable decision ledger also refuses execution.

Configuration: `~/.config/rstack/xurl-policy.json`, or `XURL_POLICY_CONFIG`. Start from [`xurl-policy.json.example`](xurl-policy.json.example). Keys and environment overrides:

| Key | Environment | Meaning |
|---|---|---|
| `owner_id` | `XURL_OWNER_ID` | Numeric owner ID for the bookmark endpoint; required. |
| `ledger_path` | `XURL_LEDGER` | Append-only local JSONL ledger; default state directory's `xurl-ledger.jsonl`. |
| `real_binary` | `XURL_REAL_BINARY` | Original executable, never this wrapper; required. |
| `sync_command` | `XURL_SYNC_COMMAND` | Optional argv list or shell-quoted command, called with `pull`, then `push` if auth files changed. No shell evaluation. |
| `auth_file` | `XURL_AUTH_FILE` | File or directory to hash around a call; default `~/.xurl`. Auth contents are never logged. |
| `sync_lock` | `XURL_SYNC_LOCK` | Cross-process auth-sync lock; default state directory's `xurl-sync.lock`. |

State directory: `RSTACK_STATE_DIR`, else `$XDG_STATE_HOME/rstack`, else `~/.local/state/rstack`. With missing or malformed configuration every non-local call refuses, including overrides. A fallback ledger records attempts before configuration exists. Auth sync is optional; its failures preserve the original API exit code, like the original wrapper.

Each call keeps its policy decision row (`utc`, `host`, `decision`, `method`, `path`, `why`, `caller`, `cwd`) and adds `call_id`. Executed calls add a separate `type: "outcome"` row linked by `call_id`, containing `items_returned`, `exit_code`, `http_outcome` and `http_status`. Arrays count their elements, single objects count as one, and unknown output records null. Output capture uses disk-backed temporary files, with JSON parsing capped at 16 MiB. The numeric HTTP status is null when xurl does not emit it; success/error also reflects its exit code. The wrapper does not enable verbose output, which can expose authorization headers in [upstream xurl](https://github.com/xdevplatform/xurl/blob/main/api/client.go). Bodies and headers never enter the ledger. Local auth/help commands inherit the terminal and record `http_outcome: "local"`, preserving interactive authentication.

## xurl-policy

The standard-library policy can be called alone: `xurl-policy /2/usage/tweets` prints `ALLOW` or `BLOCK`, logs the decision, and exits 0 or 86. It never executes an API request itself. Configuration is shared with `xurl` above.

Allowed classes match the original gate: owner bookmarks GET; POST `/2/tweets` (the posting gate still applies); DELETE `/2/tweets/<numeric-id>`; approved POSTs under `/2/dm_conversations/`; `media`; GET `/2/usage` and its children; and local `auth`, `version` and help commands. Everything else, including tweet/user lookups, search, mentions, likes and follows, refuses. Grok Bot finds posts; the browser reads exact text and handles likes and follows, checking its logged-in handle before each action. Approved posts, replies and DMs default to `grok-post`. A nonempty `XURL_ALLOW_REASON` permits a one-off exception and records the reason in `why`. Configuration errors cannot be overridden. Body/file arguments require an explicit non-GET method, preventing an implicit POST from being admitted as a bookmark GET. These checks do not independently verify post ownership or DM approval; existing posting/approval boundaries and the API remain responsible for those.

## x-api-bypass-guard

The [`hook`](../hooks/x-api-bypass-guard) denies direct `xurl-bin` calls and direct X API URLs, including curl, wget and Python calls, with `_hookfail` handling guarded malformed inputs. Read-only mentions such as `grep api.x.com file` pass; appending an executable command does not inherit that exemption. Keep `_hookfail.py` beside the hook. Register explicitly in the desired Claude Code settings (no settings are edited by these tools):

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "python3 \"$RSTACK_ROOT/hooks/x-api-bypass-guard\"", "timeout": 10}]
    }]
  }
}
```

`RSTACK_ROOT` names the directory containing `hooks/` and `tools/`. The hook is a shell-call guard, not OS/network isolation; Codex sessions do not run Claude hooks. PATH enforcement, usage reconciliation and fleet inventory cover those sessions without claiming interception of arbitrary network clients.

## x-usage-reconcile

`x-usage-reconcile --days 7` calls the adjacent gated `xurl` with `/2/usage/tweets?days=7&usage.fields=daily_project_usage`, then compares each UTC day with the ledger. `--usage-json FILE` reads a captured response offline. The parser accepts both shapes in X's [API reference](https://docs.x.com/x-api/usage/get-usage) and [usage overview](https://docs.x.com/x-api/usage/introduction); absent daily data, invalid counts, missing ledgers and malformed rows fail instead of producing an all-clear.

Configuration: optional `~/.config/rstack/x-usage-reconcile.json`, `X_USAGE_RECONCILE_CONFIG`, or `--config FILE`. Example: [`x-usage-reconcile.json.example`](x-usage-reconcile.json.example). Keys: `days` (7), `absolute_margin` (25), `percent_margin` (20), and `ledger_paths` (defaults to the gate's ledger). CLI `--days`, `--absolute-margin`, `--percent-margin`, and repeatable `--ledger FILE` override them. Include every host/app ledger for the project whose usage X returns; the tool does not transfer ledgers. An explicit missing config file fails; the default file is optional.

ALLOW decisions contribute `items_returned`, or one call if absent; linked outcomes replace that fallback rather than adding a second call. An unsuccessful call with no returned items contributes zero. Local and free usage requests are excluded. A day fails (exit 1) only when the excess exceeds **both** margins: `X - ledger > absolute_margin` and `X - ledger > ledger * percent_margin / 100`. The failure prints its date and both counts. This is a conservative bypass detector for Post consumption, not dollar spend or proof that no user lookup/like/follow bypass occurred; repeated or non-Post allowed calls can over-explain consumption.

`--alert` runs `tell-general fyi "<one line with day and counts>"` once per failing usage day, persisting successful notifications in `$RSTACK_STATE_DIR/x-usage-reconcile-alerts.jsonl` under a file lock. Notification failure exits 1 and remains retryable. Schedule daily through your existing scheduler, for example `x-usage-reconcile --days 7 --alert`; installation and scheduling are operator steps.

## fleet-lint

`fleet-lint [--json] [--alert]` inventories every tmux session, Claude/Codex processes (including those outside tmux), and loaded launchd jobs under the configured prefix. It prints one finding per offender and check, and exits 1 on findings or unreadable inputs. JSON includes inventories and findings. It changes no process, installation, registry or settings. `--alert` sends one `tell-general fyi` line with counts for that invocation. Schedule it daily through your existing scheduler.

Configuration: `~/.config/rstack/fleet-lint.json`, `FLEET_LINT_CONFIG`, or `--config FILE`; see [`fleet-lint.json.example`](fleet-lint.json.example). Default inventory is local plus `ssh_host` (or `FLEET_LINT_SSH_HOST`); a missing SSH host is a finding. An explicit `hosts` list replaces the default: each entry has `name`, optional `ssh`, and any per-host overrides of the common keys below.

| Key | Meaning |
|---|---|
| `repo` | Controller checkout used for every host's source file and harness tree comparisons; required. Host overrides do not change this source. No fetch is performed. |
| `wrapper` | Expected gated xurl path; default `~/.local/bin/xurl`. |
| `harness_stamp` | Installed harness's `.harness-sync.json`; its commit's `harness/` tree must equal `origin/main:harness` in the controller repo. Unavailable commits fail; commits that change only other directories pass. |
| `install_map` | Nonempty mapping from repo-relative tool/hook paths to installed paths. Map every installed rstack tool, including the wrapper, policy and hook support file. Missing/different files fail. |
| `launchers` | Executable/script names or exact paths accepted in an agent's parent chain. Defaults: `launch.sh`, `lane-session`, `run.sh`, `agent_executor.py`, `~/.local/bin/claude`, `~/.local/bin/codex`. The remote runner's `sh -c` script position counts; arguments and prompt mentions do not. App-server chains and `codex resume --remote` attachments also count when tmux's pane start command is a configured launcher. A bare Codex command in tmux does not. |
| `lane_registry` | Optional JSON file: `["session"]` or `{"sessions": ["session", {"tmux_session": "other"}]}`. A lane root with `lanes/*/SESSION.json` files containing `tmux_session` also works. A listed tmux session satisfies the launcher check. |
| `label_prefix` | Required launchd label prefix, e.g. `com.example.`. |
| `ssh_host` | SSH alias for the default second host. Per-host `ssh` overrides this. |
| `skills.denied` | Skill names prohibited on this host, matched against directory names and SKILL.md frontmatter names. Defaults to an empty list. Use the complete excluded list in the relevant vendor manifest for a lane's policy. |
| `skills.allowed_dirs` | Absolute or home-relative directories under which vendored packs may live, including their descendants. Defaults to none. Configure lane directories explicitly. |

Collection runs `ps -axo pid,ppid,command`, `ps eww -p PID` (reading only PATH), tmux listing commands, `launchctl list`, and file reads/hashes. On each host, `zsh -lc 'whence -p xurl'` and `zsh -ic 'whence -p xurl'` must resolve to the wrapper. Both shells' PATHs and all agent process PATHs are scanned for every executable named xurl, including shadowed copies; any extra path is a finding. A bare process PATH with no xurl passes. Relative PATH entries cannot be inspected and are findings; use absolute PATH entries in launchers.

Each host returns SHA-256 hashes for installed targets; the controller compares them with its own repo files, once per target. The wrapper and its adjacent policy are always included, even if omitted from `install_map`. Harness stamps are compared using `git rev-parse --verify COMMIT:harness` and `origin/main:harness` on the controller. Remote checkouts are never consulted. Remote collection sends the same Python collector through SSH with batch mode, strict host-key checking and bytecode writes disabled; no remote install or configuration change occurs. Collection races or inaccessible hosts are findings, not an all-clear. Empty sessions remain in the inventory. launchd inventory covers loaded agents; process ancestry proves only what remains observable after exec/reparenting, so the lane registry supplies the alternative evidence.

Tests for these tools and the hook: `../tests/test_x_api_gate.py` and `../tests/test_fleet_lint.py`. They use a stub executable and synthetic usage/ps/tmux/launchctl fixtures; no X request, real SSH connection or real notification runs.

The `skills` check inventories `~/.claude/skills`, `~/.codex/skills`, `~/.agents/skills`,
every tmux pane's `cwd/.claude/skills`, and every running Claude/Codex process's
`cwd/.claude/skills`, including agents outside tmux. It reads process working directories
through `/proc/PID/cwd` on Linux or `lsof -a -p PID -d cwd -Fn` on macOS. Inaccessible
working directories are collection findings. Skill links are followed with cycle detection;
denied directory aliases still count. Each `.skills-vendor.json` marker identifies a pack:
a location outside `allowed_dirs` and an unsuccessful integrity check are separate findings.
Unmarked skills are inventoried and checked against denied names; they have no vendor
manifest to check. Both local and SSH hosts use the controller's shared integrity checker,
sent with the read-only collector. Keep `skills_vendor_integrity.py` beside both installed
tools; remote hosts need no installed copy of it.

## skills-vendor

`skills-vendor` uses Python's standard library and Git. It treats an upstream pack as
untrusted text: it never imports, runs, installs dependencies from, or follows instructions
in that pack. This repository contains only the reviewed manifest and review, not upstream
skill code. The manifest records the repository, full commit and tree, MIT license hash,
included file lists and SHA-256 hashes, and every excluded skill with reasons.

The initial K-Dense pin is `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`, tree
`390fe361644ba6ef88019af55a45a28ace2014ba`. The default cache is
`$XDG_DATA_HOME/rstack-vendor/scientific-agent-skills`, falling back to
`~/.local/share/rstack-vendor/scientific-agent-skills`. Populate it without running upstream
code, for example:

```sh
CACHE="${XDG_DATA_HOME:-$HOME/.local/share}/rstack-vendor/scientific-agent-skills"
git clone --no-checkout https://github.com/K-Dense-AI/scientific-agent-skills.git "$CACHE"
git -c core.hooksPath=/dev/null -C "$CACHE" checkout --detach 2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5
python3 rstack/tools/skills-vendor review --cache "$CACHE"
```

`review [--cache DIR] [--manifest M] [--review FILE]` verifies source bytes against the Git
tree, scans every file of all skills for fail rules, and writes the manifest and Markdown
review. The review contains candidate PASS/FAIL rows, hosts, environment names, per-file
line evidence, and the complete excluded list. No candidate name mapping is needed at this
pin. The scoped candidate list is explicit in the tool; `--candidate NAME` can override it
for custom reviews. Review cannot replace an existing pin with another commit, and a fresh
manifest is restricted to the initial approved pin. Further commits use update and accept.

The scanner discloses environment access, URLs/hosts, shell/process use, dependency
install instructions, dynamic/deserialization operations, home and clipboard access, and
potential writes outside the working directory. It rejects provider-key references/read
instructions (including EXA and Parallel), pipe-to-shell installers, sensitive browser,
cookie, keychain, SSH or screen access, agent settings/hook instructions, and recognizable
obfuscated or downloaded code execution. Ordinary science service keys are listed rather
than rejected. Explicit exclusions remain excluded even if the lexical scan has no match;
in particular citation-management has no provider-key match at this pin. Lexical findings
can be conservative, and computed names, indirect paths and arbitrary obfuscation can evade
static analysis. PASS is scoped to these rules, not a guarantee of safety. Potential home
writes are marked as such when the exact destination depends on runtime arguments.

For an authorized lane installation, use an absent or empty pack directory:

```sh
python3 rstack/tools/skills-vendor install --manifest rstack/vendor/kdense/manifest.json --dest /path/to/lane/.claude/skills
python3 rstack/tools/skills-vendor check --dest /path/to/lane/.claude/skills --manifest rstack/vendor/kdense/manifest.json
```

`install` verifies the cache's commit/tree, every source SHA-256 and the exact included
skill file sets before copying only manifest files, plus the MIT license. It refuses
modified/missing/extra files, links, unsafe paths and nonempty destinations. It writes
`.skills-vendor.json` with the accepted manifest and its digest. `check --dest DIR` checks
the installed file set and every hash against that record; `--manifest M` also compares
the record with a separately trusted manifest. The marker is local inventory, not a
signature. None of these commands executes skill code, changes agent settings, or enables
global discovery. The tool performs no destructive cleanup; keep or Trash an old pack
before choosing a fresh destination.

```sh
python3 rstack/tools/skills-vendor update --to FULL_COMMIT --proposal /path/to/proposal
# Person or conductor reviews manifest.json, REVIEW.md and review.diff, then explicitly:
python3 rstack/tools/skills-vendor accept /path/to/proposal
```

`update` fetches origin, creates a detached snapshot at `rstack-vendor/review-FULL_COMMIT`,
re-scans the entire pack, and diffs both previously and newly included skills. It writes a
**proposed** manifest, complete review and review diff without changing the accepted pin,
the original cache checkout, any installation, or settings. A proposed manifest refuses
installation. `accept PROPOSAL [--manifest M]` checks the proposal's base pin, repository
and scope and replaces only the accepted manifest and adjacent review. It never installs.
Acceptance is an explicit operator/conductor decision; the CLI does not authenticate the
person invoking it. After acceptance, install with `--cache` pointing to that reviewed
snapshot, because the original cache stays pinned. Retained snapshots are cache data and
are never run automatically.

Tests: `python3 -m pytest -q rstack/tests/test_skills_vendor.py rstack/tests/test_fleet_lint.py`.
They use synthetic packs, local Git fixture origins and simulated SSH; no downloaded skill
is installed or executed, and no external network or notification is needed.

## grok-ask

`grok-ask [--host HOST] [--timeout S] [--schema FILE] [--relaunch] "<query>"`
asks Grok Bot in a **new chat** and writes only a parsed JSON array of objects to stdout.
It uses Python 3.9+ standard library and the app's CDP endpoint. Local calls use
localhost:9333; `--host` uses a temporary SSH tunnel bound to 127.0.0.1, with the
remote destination also 127.0.0.1:9333. SSH uses your existing host configuration;
no credentials are copied or shared between hosts. Pick the host with the intended
app account. The tool never visits sign-in, account, settings or subscription screens.

The endpoint must already be enabled. On the intended host, an operator can quit the
app and start it with:

```sh
open -a "Grok Bot" --args --remote-debugging-address=127.0.0.1 --remote-debugging-port=9333
```

An unavailable endpoint fails with this instruction. The tool never restarts the
app by default. `--relaunch` explicitly permits quitting, starting with CDP, then
quitting and starting normally again, including after query failures. Restoration
has a separate 15-second limit. Do not use that option during fake-only testing.

Copy `grok-ask.json.example` to `~/.config/rstack/grok-ask.json` and adjust selectors
for the installed UI. `GROK_ASK_CONFIG` can select another file. Missing configuration
uses the shipped example; **its selectors are assumptions, not live-verified**.
`target_title` and `target_url` are substring filters; exactly one page must match.
The tool clicks `new_chat` and waits for an empty composer and zero user/assistant
messages before inserting text. It clicks `send`, waits for the current prompt to
appear, the `busy` indicator to disappear, and the answer to stop changing for
`settle_seconds`. Rendered code selected by `json_code` is reconstructed as a JSON
fence when the DOM has stripped markdown fences. A UI change is a config edit.
An incorrect completion selector can misidentify a pause as completion; check it live.

The fixed suffix requests exactly one JSON fence, containing an array of objects
(or `[]`). `--schema FILE` adds and checks required keys in every row. FILE can be
a JSON key list (`["post_id", "url"]`), an object JSON Schema with `required`
(or `properties` when `required` is absent), or an array schema with that under
`items`. This checks keys only, not JSON Schema types or other constraints.
Missing/bad JSON, missing keys, connection failures and timeouts exit 3, with the
raw answer on stderr and no stdout JSON. CLI usage errors exit 2.

When DOM reading raises an error, the fallback copies app-cache `.blob` files to
scratch and reuses the `grok_fresh.py` decoder: base32 filenames containing
`.transcript.replicas.`, JSON `value` (possibly JSON-encoded again), then
`entries[].message.content` and `timestampMs`. It accepts only a transcript containing
this exact prompt and unique request ID, followed by a newer message. Copies are
limited to 32 MiB. Cache completion uses `cache_settle_seconds` of unchanged text
(default 5), a heuristic because the reused format has no completion flag. A cache
that exceeds the limit, lacks this prompt, or cannot be decoded cannot supply an answer.

A file lock serializes calls to each host alias on this controller; use one alias
per remote host and one shared state directory. Local, localhost and loopback IP
spellings share a lock. Different controllers require external serialization.
`--timeout` (default 120 seconds) includes lock and tunnel wait. Every attempted
query appends UTC, host, caller, SHA-256 query hash, row count, elapsed seconds and
exit code to `$RSTACK_STATE_DIR/grok-ask.jsonl` (default
`$XDG_STATE_HOME/rstack`, otherwise `~/.local/state/rstack`). Raw queries and answers
are not logged. `RSTACK_CALLER` labels the caller; its default is `grok-ask`.

## grok-x-search

```sh
grok-x-search LANE --query 'example topic' --since 2026-11-01
```

This calls the sibling `grok-ask`, requests X post leads, saves its JSON array as
`lanes/LANE/intake/x-search/<utc>-<query-hash>.json`, and runs:

```sh
rh --root ROOT intake x-search LANE --query Q --result hits --n N \
  --hits-file SAVED_JSON --captured-by grok-x-search
```

Empty arrays use `--result none --n 0`. `--since` adds X's `since:YYYY-MM-DD` to Q.
`--root` defaults to `$RH_ROOT`, otherwise `.runtime`; `--host` and `--timeout` pass
through to `grok-ask`. The lane must already exist with `x_local_file` configured in
`INTAKE.toml`; the adapter does not change its configuration or declarations.
`rh` records the saved file as `evidence_file` in `X_SEARCHES.jsonl`. Saved evidence
is local data, and never counts as an external browser read. If `rh` fails, the
saved leads remain and the adapter reports the failure. `GROK_ASK` and `RH` may name
alternate executables (used for stub tests).

**Grok rows are leads: exact text must be read in the browser before anything is
scored.** A zero-row Grok result is not proof that no prior art exists. Grok finds,
the browser reads exact text, and approved posts, replies and DMs default to `grok-post`.

Fake-only coverage: `python3 -m pytest -q rstack/tests/test_grok_ask.py
rstack/tests/test_grok_x_search.py harness/tests/test_x_searches.py`. No app or
account is needed; CDP, SSH forwarding and intake commands use local fakes/stubs.

## Standalone tool migration settings

Private configuration stays outside the repository. Environment values override file defaults for
`event-watch` and `fleet-context-watch`:

| Tool | Default private configuration | Contents |
|---|---|---|
| `egress-gate` | `~/.config/rstack/egress/` or `RSTACK_EGRESS_DIR` | Patterns, exceptions, samples and the settings below. |
| `clean-room` | `~/.config/rstack/clean-room.env` or `CLEAN_ROOM_CONFIG` | Trusted shell defaults, for example `: "${CLEAN_ROOM_CODEX_BIN:=/path/to/codex}"`. Use this assignment form to retain explicit environment overrides. `CLEAN_ROOM_PATH` sets the room's PATH unless `--keep-path` is given. |
| `event-watch` | `~/.config/rstack/event-watch.json` or `EVENT_WATCH_CONFIG` | JSON object with `EVENT_WATCH_CONF`, `EVENT_WATCH_STATE`, `EVENT_WATCH_NOTIFY`. Keep the previous state path to retain cursors and avoid replaying events. Its config directory follows `XDG_CONFIG_HOME` when set. |
| `fleet-context-watch` | `~/.config/rstack/fleet-context-watch.json` or `FLEET_CONFIG` | JSON object with the documented `FLEET_*` values, including `FLEET_SKIP`, the existing state/log paths and optional `FLEET_SAVE_MSG` (a template using `{k}` for thousands of tokens). |

Egress defaults still include the public secret shapes. An existing installation with its own complete
pattern policy can set `builtin_shapes = false` in `settings.ini`, section `[egress]`, to use precisely
its `patterns.txt` and optional `terms.txt`. `skip_dirs` and `skip_suffixes` are whitespace-separated
replacement lists; omit them to retain the port defaults. For a deployment that requires private
files, `require_patterns`, `require_agent_files` and `require_self_test` can be set to `true` (default
`false`). Missing required files exit 1, like malformed regex configuration. The agent-file requirement
applies to pre-push and self-test. `agent-test.txt` optionally adds `true|false<TAB>path` self-test rows;
`self-test.txt` retains its `label<TAB>text` format. Built-in self-test rows run only when built-in
shapes are enabled.

Pre-push also respects a worktree's `PUBLISH` manifest: when its first `remote` line identifies the
push destination, it blocks direct pushing and directs the operator to `publish-public`. SSH and
HTTPS spellings of the same destination match. Missing scan inputs fail with exit 1.

Fleet help (`-h` or `--help`) prints documentation without inspecting sessions. Dry mode retains the
save/compact decision output and changes no session state. A completed reset writes an empty state
object rather than deleting the previous state file.

## grok-post

Posts go through the fixed Grok account; the browser is only for likes and follows,
with its logged-in handle checked before each action. Grok transports the approved
words and must never compose them.

```sh
grok-post --rh LANE/ID --reply-to https://x.com/example/status/123 --text-file DRAFT --dry-run
grok-post --rh LANE/ID --post --text-file DRAFT
grok-post --rh LANE/ID --dm RECIPIENT --text-file DRAFT
```

Use exactly one of `--reply-to`, `--post`, or `--dm`. The row must already be linted,
approved, unsent, and approved within the last 48 hours (the outreach health window).
The file, ledger draft, lint hash and approval hash must match byte for byte,
including trailing newlines. Replies must match the approved target; DMs must match
the approved recipient. Existing public outreach reach checks still apply.
Media-bearing rows are refused by this text-only tool.

Copy [`grok-post.json.example`](grok-post.json.example) to
`~/.config/rstack/grok-post.json`, or select it with `GROK_POST_CONFIG`. Set the fixed
host and account explicitly; `--host` may only repeat that configured host. Configure
the project host independently of any other account's app. The named posting bot
must already exist in the sidebar; create it manually if missing. No bot creation,
account switching, app launch, restart, installation or API posting is performed.

| Config key | Default and meaning |
| --- | --- |
| `post_bot_name` | `Posts`; dedicated existing bot, distinct from the query `bot_name`. |
| `post_host` | `m5`; fixed SSH alias, or `local` for a local endpoint. |
| `post_account` | Empty, refuses until configured; exact expected X screen_name without `@`. |
| `rh_root` | `RH_OUTREACH_ROOT`, then `RH_ROOT`, then `~/.local/share/research-harness`; contains `lanes/`. |
| `rh_command` | `["rh"]`, or `["$RH"]` when that environment variable is set; argv prefix for sent bookkeeping. |
| `ledger_path` | `$RSTACK_STATE_DIR/grok-post.jsonl`, otherwise `$XDG_STATE_HOME/rstack/grok-post.jsonl`, otherwise `~/.local/state/rstack/grok-post.jsonl`. |
| `notify_command` | `["tell-general"]`; argv prefix, called with a single failure message argument. |
| `syndication_url` | `https://cdn.syndication.twimg.com/tweet-result`; HTTP loopback override is for fake tests only. |

CDP settings come from `GROK_ASK_CONFIG` / `~/.config/rstack/grok-ask.json` and may
also be overridden in the posting config: `port`, `target_title`, `target_url`,
`composer`, `send`, `user_message`, `assistant_message`, `busy`, `busy_text`,
`poll_seconds`, `settle_seconds`, and `answer_quiet_seconds`. The sidebar button or
link must have an aria-label whose first comma-separated part equals `post_bot_name`;
`button[aria-label="View conversation details"]` must show that bot's name.
Posting uses DOM answers following the current user message, with a snapshot of
message counts before each turn. It never falls back to cached transcripts.

The draft instruction contains unique delimiters and an authoritative JSON string
of the exact approved text. Grok must return one JSON array with one object whose
`draft` field contains the prepared text. Only CRLF/CR versus LF is normalized for
the draft and public verification comparisons; spaces, punctuation, Unicode and
trailing newlines remain exact. A mismatch sends `cancel, do not send`, exits **4**,
and logs the diff and draft response. Keep this ledger private: a mismatch may
contain approved text or DM content. `--dry-run` also cancels after a matching draft,
without sending `send`, claiming the row or recording it sent.

After a match, approval and reach are rechecked, the existing outreach posting
attempt is recorded, and the next command is exactly `send`. The bot is asked for
`[{"status":"sent","id":"...","posted_url":"...","account":"...","recipient":"..."}]`.
For public posts, a unique posted URL or numeric ID is also accepted. The tool reads
`tweet-result?id=ID&token=x` and requires the same ID, exact text, exact account and
reply target (and no reply target for originals). After verification it runs
`rh --root ROOT outreach sent LANE ID --message-id ID --via grok` and appends UTC,
rh ID, target, posted URL/ID and verified fields to the JSONL ledger.

DMs require Grok's explicit `status: sent`, numeric message ID, matching account and
recipient, plus successful `rh outreach sent`. Their output and ledger explicitly
say **Grok confirmation plus rh row only; no public endpoint**. They do not receive
independent public verification.

Usage/approval refusals exit **2**; transport/configuration failures before sending
exit **3**; draft differences exit **4**. Any uncertain send, failed verification or
failed sent bookkeeping exits **5** and invokes `notify_command`. A posting attempt
remains reserved after an uncertain send: reconcile its actual outcome before any
manual retry. Notification failure is reported on stderr. `--timeout` defaults to
180 seconds, including host lock and tunnel wait; cancellation after a failed draft
has a separate bounded five-second window. The host lock is shared with `grok-ask`.

Fake-only tests (CDP, syndication and rh stubs; no live app or X actions):

```sh
python3 -m pytest -q rstack/tests/test_grok_ask.py harness/tests/test_outreach.py
```
