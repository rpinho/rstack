# rstack tools

Standalone scripts (Python 3.9+ standard library, plus bash for `clean-room`). Tests live under `../tests/`. Private-content filters take your own term files; the model instruction guard uses public model spellings.

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

Allowed classes match the original gate: owner bookmarks GET; POST `/2/tweets` (the posting gate still applies); DELETE `/2/tweets/<numeric-id>`; approved POSTs under `/2/dm_conversations/`; `media`; GET `/2/usage` and its children; and local `auth`, `version` and help commands. Everything else, including tweet/user lookups, search, mentions, likes and follows, refuses. Grok Bot finds posts; the browser reads exact text and handles likes, follows and replies. A nonempty `XURL_ALLOW_REASON` permits a one-off exception and records the reason in `why`. Configuration errors cannot be overridden. Body/file arguments require an explicit non-GET method, preventing an implicit POST from being admitted as a bookmark GET. These checks do not independently verify post ownership or DM approval; existing posting/approval boundaries and the API remain responsible for those.

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
| `repo` | Host checkout used for `origin/main` and source file comparisons; required. No fetch is performed. |
| `wrapper` | Expected gated xurl path; default `~/.local/bin/xurl`. |
| `harness_stamp` | Installed harness's `.harness-sync.json`; its `commit` must equal that host repo's `origin/main`. |
| `install_map` | Nonempty mapping from repo-relative tool/hook paths to installed paths. Map every installed rstack tool, including the wrapper, policy and hook support file. Missing/different files fail. |
| `launchers` | Executable/script names or exact paths accepted in an agent's parent chain. Defaults: `launch.sh`, `lane-session`, `~/.local/bin/claude`, `~/.local/bin/codex`. Arguments and prompt mentions do not count. |
| `lane_registry` | Optional JSON file: `["session"]` or `{"sessions": ["session", {"tmux_session": "other"}]}`. A lane root with `lanes/*/SESSION.json` files containing `tmux_session` also works. A listed tmux session satisfies the launcher check. |
| `label_prefix` | Required launchd label prefix, e.g. `com.example.`. |
| `ssh_host` | SSH alias for the default second host. Per-host `ssh` overrides this. |

Collection runs `ps -axo pid,ppid,command`, `ps eww -p PID` (retaining only PATH resolution), tmux listing commands, `launchctl list`, local file reads/hashes and `git rev-parse origin/main^{commit}`. It resolves xurl on each agent's own PATH, follows symlinks and requires the configured wrapper. The wrapper and its adjacent policy are always compared with repo code, even if omitted from `install_map`. Missing PATH or relative PATH entries are reported as unresolvable. Use absolute PATH entries in launchers. Remote collection sends the same Python collector through SSH with batch mode, strict host-key checking and bytecode writes disabled; no remote install or configuration change occurs. Collection races or inaccessible hosts are findings, not an all-clear. Empty sessions remain in the inventory. launchd inventory covers loaded agents; process ancestry proves only what remains observable after exec/reparenting, so the lane registry supplies the alternative evidence.

Tests for these tools and the hook: `../tests/test_x_api_gate.py` and `../tests/test_fleet_lint.py`. They use a stub executable and synthetic usage/ps/tmux/launchctl fixtures; no X request, real SSH connection or real notification runs.
