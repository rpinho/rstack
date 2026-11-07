# Configuration

Use an isolated writable root with `python3 harness/rh.py --root PATH ...`. It contains `lanes/NAME/INTAKE.toml`, optional sweep/cadence/outreach TOML files, and runtime JSON/JSONL ledgers. Never use a real lane as a tutorial fixture. See [examples/toy-lane](../examples/toy-lane).

| Setting | Meaning |
|---|---|
| `RH_POD_LANES` | Comma-separated eligible pod lane names; empty by default. |
| `RH_SELECTION_GATE` | Optional selection package root; defaults to bundled `selection/` beside `harness/`. `~` expands. V2 requires NumPy. |
| `RH_POLICY_EXCLUDED` | Explicit legacy evidence-policy exemptions; empty by default. New deployments should keep it empty. The capacity hook also recognizes these exemptions. |
| `RH_REAP_EXCLUDED` | Comma-separated protected pod names or lane names; empty by default. |
| `RH_ROLES_FILE` | Local generated roles/routes JSON; default `.runtime/roles.json`. |
| `RH_AGENT_ALERTS` | Agent alert JSONL queue; default `.runtime/agent-alerts.jsonl`. |
| `RH_NOTIFY_COMMAND` | Optional pod/provider notification executable and quoted arguments; no service supplied. |
| `RH_CONTACTS` | Private contact file; default `.runtime/contacts.json`. Rows take a `name` and an optional `language` code such as `pt`. See [outreach](outreach.md). |
| `RH_VOICE_COMMAND`, `RH_SCIENCE_CHECK_COMMAND` | Separately supplied lint commands. Missing required commands refuse lint. |
| `RH_TRASH_COMMAND` | Reversible disposal adapter; default `/usr/bin/trash`. Linux deployments must supply a compatible Trash command. There is no destructive fallback. |
| `RH_SSH_KEY`, `RH_KNOWN_HOSTS` | SSH identity and strict known-hosts file; defaults `.runtime/ssh/id_ed25519` and `.runtime/ssh/known_hosts`; set explicitly for an existing SSH setup. |
| `RH_GH` | GitHub CLI executable used by metadata discovery; default `gh`. |
| `RH_XCAPTURE_ROOT` | Private root holding `x_capture/KEY.jsonl`; generator default is current directory. |
| `RH_EVIDENCE_ROOT` | Explicit harness root for leaderboard ingestion. No home/archive discovery. |
| `MODEL_REVIEW_ROOT`, `MODEL_DRAFTS_LOG` | Explicit private review receipt tree and draft-outcome ledger. |
| `MODEL_STATE`, `MODEL_LEDGER`, `MODEL_OVERRIDES` | Private scoring state directory (default `.runtime/leaderboard`), optional ledger path and exclusions config. |
| `LAUNCH_ARTIFACT_DIR` | Standalone job specs/logs; default `$PWD/.runtime/jobs` after entering WORKDIR. A sweep passes its own spec path. |
| `LAUNCH_STATE`, `LAUNCH_SELECTOR`, `LAUNCH_CODEX` | Job registry (default `$PWD/.runtime/job-registry`), optional selector override and Codex executable. |
| `LAUNCH_ROLE`, `LAUNCH_EFFORT` | Role and effort; fixed model overrides also require a reason. |
| `LAUNCH_IDEA`, `LAUNCH_IDEA_ROOT` | Optional promoted-idea admission check before execution. Requires an `rh` command on PATH. |
| `LAUNCH_HOST` (or `--host HOST`) | Run the executor on another machine over ssh; empty means here. `HOST` is an ssh alias, validated before it reaches an ssh argv. The work dir must exist at the **same absolute path** there, or the run refuses rather than landing in the remote `$HOME`. Admission, the word cap, the registry, model selection, the prompt and the log stay on the controller. |
| `LAUNCH_SSH`, `LAUNCH_REMOTE_EXECUTOR`, `LAUNCH_PULL_MAX_SIZE` | With `--host`: the ssh command (default `ssh`), the remote `agent_executor.py` (default `$HOME/.local/share/research-harness/agent_executor.py`, expanded on the host) and the cap on each pulled-back file (default `4m`). After every attempt the heavy outputs stay on the host and only `STATUS.md`, `REPORT.md`, `PLAN.md`, `RESULTS.jsonl`, `*.selection.json` and the job's `.last.md` come back, so status reads here as it did before. A failed pull is logged and does not fail the run. |
| `EVENT_WATCH_CONF`, `EVENT_WATCH_STATE`, `EVENT_WATCH_NOTIFY` | Watch rules (default `.runtime/event-watch/config`), cursor/event state (default `.runtime/event-watch/state`) and optional notification executable. |
| `POLL_GUARD_STATE` | Private hook fingerprint directory; default `.runtime/poll-guard`. |
| `CS_BASE`, `CS_BIN`, `CS_STATE`, `CS_AUTO_READ` | Optional local daemon URL, CLI, cookie directory (default `.runtime/cs`) and path-separated auto-readable roots. Auto-read roots default to empty. |

All data paths default to the current workspace/runtime, not a personal HOME.
Absolute data paths are accepted when a caller supplies a documented setting,
CLI path or lane configuration. Standard system executable paths such as
`/usr/bin/ssh` and `/usr/bin/trash` are executable dependencies, not data discovery.
Provider CLIs manage their own login/config outside the harness; choose HOME and
provider-specific config directories before invocation.

| Additional setting | Meaning |
|---|---|
| `AGENT_BACKEND` | `codex` (default) or `claude`; invalid values refuse. |
| `LAUNCH_CLAUDE`, `LAUNCH_CLAUDE_BUDGET` | Claude executable and per-run dollar cap (default `1.00`); no automatic Claude retries. |
| `RH_POD_GATE_CONFIG`, `RH_POD_GATE_AUDIT` | Capacity policy (default `$RH_ROOT/pod-gate.json`) and audit log (default `$RH_ROOT/.runtime/pod-gate-audit.jsonl`). |
| `RH_HARVEST_STATE` | Snapshot state override; default `<root>/.harvest-state`. |
| `RH_ENV_FILE` | Host env file of `KEY=VALUE` lines read once at import; default `$XDG_CONFIG_HOME/research-harness/env` (else `~/.config/...`). The real environment wins. Keep host paths here, never in the repo. See [harness sync](harness-sync.md). |
| `RH_DISK_FLOOR_BYTES` | Free bytes required before a full harvest snapshot; default 12 GB. |
| `RH_OWNER_ALIASES` | Comma-separated older names for the operator, accepted as an idea `source_type` and as a lint-exception `decided_by`; empty by default. |
| `RH_INTAKE_LANES` | Comma-separated lanes the scheduled intake runs, in order; default every lane with an `INTAKE.toml`, alphabetically. |
| `RH_OUTREACH_ROOT` | Approval hook's ledger root; default repo `.runtime`. |
| `RH_ANSWERS_FILE` | Optional local answers file; default `.runtime/ANSWERS.md`; CLI `--answers-file` overrides it. |
| `RH_TRANSCRIPTS_ROOT` | Explicit Claude project-transcript tree for session-model detection; disabled when unset. |
| `RH_CS_DB_ROOT` | Explicit daemon data root containing `orgs/*/operon-cli.db`; disabled when unset. |
| `RH_REMOTE_RUNNER` | Deployed runner path on a pod; default relative `research-harness/pod/runner.py`; quote-safe in the SSH shell command. |
| `RH_RUNNER_SOCKET` | Local pod-runner socket; default `.runtime/rh-pod-runner.sock`; CLI `--socket` overrides it. |

Capacity policy uses `mode = audit|enforce` and `enforce_lanes` drawn from
`RH_POD_LANES`. Hooks are not installed automatically. Set `RH_ROOT` explicitly
when using them in a deployment.

The launcher stays synchronous so a sweep can bound its process group. Codex
capacity retries are limited to five attempts. Claude has one attempt so a retry
cannot reset its dollar cap. Codex uses workspace-write; Claude uses acceptEdits
and preapproved file tools, without an OS sandbox from this runner. External
access and credentials belong to the caller. No watchdog is installed.

Launchd templates under [harness/templates](../harness/templates) contain `@...@` placeholders. Render them into your own scheduler directory, choose Python and root paths, and inspect before loading. Template files are not active jobs. Linux users can schedule the same commands with their existing scheduler.

Linux/container system files are the only absolute data defaults. They are named
configuration settings, rather than private-machine locations:
`RH_MEMINFO` defaults to `/proc/meminfo`; `RH_CGROUP_ROOT` defaults to
`/sys/fs/cgroup`; remote probes use `RH_REMOTE_CGROUP_ROOT` (default
`/sys/fs/cgroup`) and `RH_REMOTE_UPTIME` (default `/proc/uptime`).
`RH_POD_WORKSPACE` defaults to the container contract `/workspace` and can also
be overridden with `--workspace`. Harvest's `/workspace/` check is a remote-path
allowlist, not discovery of local files. `MODEL_MINE_OUT` defaults to
`.runtime/model-mine` and `--out` overrides it. Missing evidence fails directly,
without probing a made-up absolute sentinel file.

New lanes created with `rh lane new` also contain `LANE.json` (frozen problem, metric, deadline, test/bar, submission rules and access declarations) and `SELECTION.json` (v2 policy). Lint checks their hashes and lane limits. A 24-hour setup grace applies only while workers are disabled and no idea, intake, sweep or sealed-scoring history exists. Afterwards the ordinary reading, queue and delivery checks apply. `workers_enabled=false` refuses real sweeps while preserving previews. These local hashes detect accidental edits; they are not an authenticated audit service.
