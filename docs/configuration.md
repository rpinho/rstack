# Configuration

Use an isolated writable root with `python3 harness/rh.py --root PATH ...`. It contains `lanes/NAME/INTAKE.toml`, optional sweep/cadence/outreach TOML files, and runtime JSON/JSONL ledgers. Never use a real lane as a tutorial fixture. See [examples/toy-lane](../examples/toy-lane).

| Setting | Meaning |
|---|---|
| `RH_LAUNCH_RECEIPTS` | Directory of the launcher's `JOB.log.selection.json` receipts. `rh bughunt verdicts` takes a referee's model family from the receipt named after the verdict's folder, not from the referee's self-report. Unset: the self-report is used and flagged. |
| `MEM_GUARD_LIMIT_GB` | `harness/tools/mem_guard.py` (launchd, every few seconds on a compute host): kill any user process whose physical footprint passes this, default 8. The window server, agent sessions, the browser, tmux and Apple binaries are spared. |
| `MEM_GUARD_JOB_GB` | Cap on one launcher job's processes together. A job's processes are those carrying `RH_JOB=<job>` in their environment (launch.sh sets it on the executor, every worker inherits it) plus the process tree under its pid file in `MEM_GUARD_JOBS_DIR` (default `~/.local/state/research-harness/remote-jobs`). Over the cap the job is stopped whole, a `MEMKILL` line with its peak goes into its `STATUS.md`, the owner is pushed and `MEM_GUARD_TELL` (run on `MEM_GUARD_TELL_HOST` over ssh when set) tells the conductor. Unset: off. macOS ignores `ulimit -v`, so this watcher is the cap. |
| `MEM_GUARD_MIN_FREE_PCT` | While free memory (`kern.memorystatus_level`) is under this, stop the largest job, one every `MEM_GUARD_COOLDOWN_S` (default 20). Unset: off. `mem_guard.py --every 3` loops and writes `MEM_GUARD_HEARTBEAT` (default `~/.local/state/mem-guard/heartbeat`) after each pass. |
| `LAUNCH_MAX_PEAK_GB` | `launch.sh --host` refuses a job unless the host's memory-guard heartbeat (`LAUNCH_MEMGUARD_HEARTBEAT`, on the host) is under 60 s old and the spec has a line `Peak RSS: N GB` measured with `/usr/bin/time -l`. A declared peak over this (default 8) is refused and belongs on a pod. `FORCE_LAUNCH` does not skip it. |
| `MEM_GUARD_TOTAL_GB` | Cap on all unspared processes outside app bundles together; over it, the largest is killed until they fit. Unset: off. |
| `HOST_WATCH_NOTIFY` | `harness/tools/host_watch.py` (launchd, every 5 min): push critical memory pressure with the largest processes, resume apps the kernel suspended for swap exhaustion once pressure eases, and report a browser renderer above 90% CPU for an hour with the session that started it. Also `HOST_WATCH_SWAP_GB` (default 16), `HOST_WATCH_SPIN_CPU`, `HOST_WATCH_SPIN_S`. |
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
| `RH_PAPER_CACHE`, `RH_PAPER_CACHE_TTL_DAYS`, `RH_PAPER_CITING_TTL_DAYS` | Paper-lookup cache directory (default `.runtime/paper-cache`) and TTLs: 30 days for a search, 7 for a citation list, because a stale citation list can hide the paper that scooped a result last week. Point every lane at one directory to share both the cache and the quota. |
| `RH_PAPER_CONTACT` | Address sent to OpenAlex's and Crossref's polite pools, as a `mailto` parameter and in the User-Agent; empty by default, and a contact address is the operator's to supply, never this repository's. |
| `RH_OPENALEX_KEY`, `RH_SEMANTIC_SCHOLAR_KEY` | Optional API keys. The whole chain works with neither: Europe PMC, arXiv and Crossref need no key and Semantic Scholar answers keyless at a lower rate. OpenAlex takes its key as a URL parameter, Semantic Scholar as an `x-api-key` header, never in the URL. |
| `RH_PAPER_<SOURCE>_PER_DAY` | Sustained requests a day for one source (`OPENALEX`, `SEMANTICSCHOLAR`, `EUROPEPMC`, `ARXIV`, `CROSSREF`), spread over the day by a token bucket in the cache directory and shared by every lane and every parallel job. Defaults are the free limits: OpenAlex 1,000, Semantic Scholar 5,000, Europe PMC and Crossref 20,000, arXiv one request every three seconds. A source with no tokens left is skipped, not waited for. Raise one only to match a key you actually hold. |
| `RH_XCAPTURE_ROOT` | Private root holding `x_capture/KEY.jsonl`; generator default is current directory. |
| `RH_EVIDENCE_ROOT` | Explicit harness root for leaderboard ingestion. No home/archive discovery. |
| `MODEL_REVIEW_ROOT`, `MODEL_DRAFTS_LOG` | Explicit private review receipt tree and draft-outcome ledger. |
| `MODEL_STATE`, `MODEL_LEDGER`, `MODEL_OVERRIDES` | Private scoring state directory (default `.runtime/leaderboard`), optional ledger path and exclusions config. |
| `LAUNCH_ARTIFACT_DIR` | Standalone job specs/logs; default `$PWD/.runtime/jobs` after entering WORKDIR. A sweep passes its own spec path; an absolute JOB is the spec's path without `.md`, and registers under `paths/` in the registry, where job-watchdog does not look. |
| `LAUNCH_WORK_ROOT` | Base for a relative WORKDIR (default `$PWD`). |
| `LAUNCH_DETACH`, `LAUNCH_DETACH_POLL`, `LAUNCH_RESTARTS` | `LAUNCH_DETACH=tmux`: a job started outside tmux, or from a `claude-*` tmux session, runs in its own session `job-JOB` (the name job-stop and job-watchdog use) after every admission check; the caller waits (polling every `LAUNCH_DETACH_POLL` s, default 15) and exits with the job's exit line (143 for a stop, 1 for none), and a second launch while it runs exits 75. The registry entry carries `restarts=` (`LAUNCH_RESTARTS`, job-watchdog's per-job cap) and `path=`. |
| `LAUNCH_PREAMBLE` | Colon-separated files put at the top of every prompt after `tools/RULES.md` (e.g. a host's FRONT.md). Never counted against the word cap. |
| `LAUNCH_SPEC_CAP_SINCE` | Epoch seconds: a spec last modified before it is exempt from the word cap (it predates the rule). Default 0. |
| `LAUNCH_REMOTE_PATH` | With `--host`: the remote PATH (the sweep sets it from `worker_path`); default `$HOME/.local/bin:/opt/homebrew/bin:$PATH` there. The executor's last message (`JOB.last.md`) is pulled back by name when it is outside the work dir. |
| `LAUNCH_STATE`, `LAUNCH_SELECTOR`, `LAUNCH_CODEX` | Job registry (default `$PWD/.runtime/job-registry`), optional selector override and Codex executable. |
| `LAUNCH_MAX_CONCURRENT`, `LAUNCH_TMUX`, `LAUNCH_GUARD` | Default four other live Codex `job-*` tmux sessions; games/open-source/bio are exempt. The guard counts sessions, excludes dead/known non-Codex routes, and refuses an unreadable count. Allowance limits are enforced by the wrapper. |
| `RH_ALLOW_OPENROUTER`, `RH_ALLOW_GEMINI_API` | Since 11-19 the metered API routes (OpenRouter, and the Gemini API through Codex) are refused by the selector and the executor; only subscriptions run (`claude -p`, `codex exec`, `agy`). Set the flag to `1` only to let work already in flight finish. It is not a fallback: nothing swaps one route for another. Forwarded to `--host` runs. |
| `RH_CLAUDE_OVERFLOW_PERCENT` | Claude weekly usage (percent) at or above which a job routed to `claude-opus-5-5` or `claude-sonnet-5-5` runs on agy's Claude instead (`claude-opus-5-5-<tier>`, tier from `LAUNCH_EFFORT`, default high), on agy's own quota. The reading is the allowance reader's `claude` entry: `$RSTACK_STATE_DIR/usage/claude.json` (`{"weekly_percent": N, "at": unix seconds}`, at most 2 h old, `RSTACK_CLAUDE_USAGE_MAX_AGE_S`), which `rstack/tools/claude-usage` writes from launchd every 15 min. The receipt gets `overflow` and `route_model`, and the job log a line `claude overflow via agy (weekly at N%)`; the model and its evidence stay Claude's. Unset, or no fresh reading: nothing changes. |
| agy quota log | Every 429 or quota error agy returns is appended to `$RSTACK_STATE_DIR/agy-quota.jsonl` (utc, model, tier, job, error, and `blocked_until` and `window` (`5h` or `weekly`) when agy names its reset), to learn its 5-hour and weekly limits; `rstack/tools/allowance` shows the latest as `agy_quota` and what is blocked now as `agy_blocked`. Nothing buys more quota: overages stay off. Until a (model, tier)'s reset passes, the picker leaves it out of the default pick, the delegate pool and the Claude overflow, and the receipt's `quota_skipped` and the job log say `skipped MODEL: agy quota until TIME`; a named `--model` that is blocked is refused. The executor also prints the row as an `AGY_QUOTA` line, so a `--host` job's quota reaches the controller's log too. A job that hit the quota is graded `ungraded` with a note starting `quota`, never pass, partial or fail. `harness/agy_quota.py` lists the blocks; `--import FILE` adds another machine's rows. |
| `RH_DELEGATE_SHARE`, `RH_DELEGATE_ROLES` | Share (0 to 1; unset = 0) of real lane jobs in `review, judge, audit, mechanical, builder` (or the roles listed) that go to a delegate instead of the leaderboard's first pick: Gemini 4 Neon, Argon and Hydrogen at low and medium on agy, GPT-6.2 Sol and Astra, Sonnet 5.5. The delegate with the fewest graded everyday outcomes is picked, never the job's own maker for judgment roles. The receipt gets `source: delegate` and a `delegate` line, and the job log the same line. A codex job routed to claude or agy keeps a shell (`Bash` added to its tools). |
| Grading on return | Each launch log ends with a `GRADE ON RETURN` line: `worker_models.py --grade pass|partial|fail --note WHY --receipt JOB.log.selection.json --log JOB.log` writes `MODEL_GRADE` to the job's log and a row to `everyday-grades.jsonl` beside the receipt, which the daily model scorer reads as everyday work for the model the receipt ran. |
| Model pin, grading gate | A spec that needs its model (a sealed referee, a cross-family check) carries a line `Model pin: REASON` and is never delegated; the receipt records `model_pin`. A review whose verdict must count at the science-publish gate carries a line `Gate: science-publish`: the pick is then held to the gate's own `REVIEWERS` (read from the gate's source, `RH_SCIENCE_PUBLISH_GATE` or `science-publish-gate` on PATH; unreadable refuses), a model qualifies when its id names a reviewer (`claude-opus-5-5` for opus, `gpt-6.2-astra` for astra), and there is no headroom move or delegation outside that list. `RH_DELEGATE_ROLES` defaults to `review, judge, audit, mechanical, builder, batch`. Grading never blocks a launch. When a delegated job returns, `harness/auto_grade.py` grades it from its own checks (exit code for its selection, `Shipped:` in REPORT.md, `You asked:` in STATUS.md, each `Check: COMMAND` line of the spec run in the work dir, 600 s each): all pass is pass, a failed check partial, no exit 0 or no Shipped line fail. A spec without Check lines is graded by the leaderboard's review pick from another family (never delegated), which answers PASS, PARTIAL or FAIL. The row records `producer` and `grader`. If no grade can be had, it is recorded `ungraded` at once (counted, outside the rate) and writes it to `$RSTACK_STATE_DIR/asks-waiting/<host>-ungraded.tsv` for the morning report; a later `--grade` for the same selection replaces it. `leaderboard/daily.sh` also sweeps any returned delegated job still without a row at 06:30. |
| Successors | `INHERITS` in `leaderboard/model-roles.py` names successor -> predecessor pairs (same lab only): `gpt-6.2-sol` <- `gpt-6.1-sol`, `gpt-6.2-astra` <- `gpt-6-astra`. A successor ranks on its predecessor's everyday record until its own graded n reaches the predecessor's, then on its own; LEADERBOARD.md shows `inherited from X (n=N); own n=M`. The predecessor stays visible as a historical row and is not routed. |
| `RH_HEADROOM_ROUTING`, `RH_DELEGATE_CODEX_PER_DAY`, `RH_LAUNCHER_EXECUTORS` | The default executor goes to the provider with the most weekly headroom per hour left to its reset (Claude from `usage/claude.json`, which may carry `resets_at`; Codex from its rollout snapshot; read through `allowance.cached`, reused 30 min). When that is not the leaderboard pick's provider, the pick moves to that provider's default (Claude: Sonnet 5.5 for batch, mechanical and cheap, Opus 5.5 otherwise; Codex: Astra for judgment roles, Sol otherwise), never into a referee's producer family. The receipt and the log carry `executor claude: headroom X% / Yh to reset vs codex ...`. When either reading is unknown (Claude's missing, unreadable or over 2 h old) the last policy holds, the leaderboard pick on the requested executor, the line says `claude usage unknown (...); last policy kept`, and the picker leaves one row in `$RSTACK_STATE_DIR/asks-waiting/<host>-claude-usage.tsv` for the conductor. `RH_HEADROOM_ROUTING=0` turns it off; agy has no figure and is never the default. Delegate picks on Codex routes (Sol, Astra) are capped at `RH_DELEGATE_CODEX_PER_DAY` (default 6). A launcher names the executors it can run in `RH_LAUNCHER_EXECUTORS` (`tools/launch.sh` passes `codex,claude,agy` unless the host narrows it); unset, a caller that follows the printed route (`--print-route`, or `select()`) may get any of the three, and one that reads only the model name gets its own executor or claude. The 85% brake to agy applies only where agy is runnable. |
| `LAUNCH_URGENT` | Nonblank reason logged by the launcher; Codex receives `-c service_tier=priority`. Forwarded to remote executors with canonical `RSTACK_LANE`; concurrency still applies. |
| `LAUNCH_ROLE`, `LAUNCH_EFFORT` | Role and effort; fixed model overrides also require a reason. |
| `LAUNCH_YIELD_LEDGER`, `LAUNCH_NOTIFY_COMMAND` | After every job the launcher checks the two hard-rule lines (`You asked: ...` first in `STATUS.md`, `Shipped: ...` first in `REPORT.md`), writes `lint restate-ask=N shipped-line=N` to the job log, and appends one row per job to the yield ledger (default `$PWD/.runtime/job-yield.jsonl`). A job missing either line is reported through `LAUNCH_NOTIFY_COMMAND`, called with one message argument, if one is set. The lint reports and never changes the job's exit status, and a missing or broken notifier is not an error: a finished job must not be turned into a failed one by its own bookkeeping. |
| `LAUNCH_IDEA`, `LAUNCH_IDEA_ROOT` | Optional promoted-idea admission check before execution. Requires an `rh` command on PATH. |
| `LAUNCH_ROUND`, `LAUNCH_FAMILY`, `LAUNCH_GENERATOR`, `LAUNCH_PARAMS`, `LAUNCH_SCORER`, `LAUNCH_HYPOTHESIS`, `LAUNCH_NEW_EVIDENCE` | Setting `LAUNCH_ROUND` puts the job through the round gate ([`harness/tools/rounds.py`](../harness/tools/rounds.py)) before the registry write, the log or any spend: it refuses a repeated method, a reopened dead end, a dry streak and an unread KB, and otherwise opens the round in the lane's `ROUNDS.jsonl`. The repeat check is a hash of `(generator, params, scorer)`, so renaming the family does not get past it, and `LAUNCH_HYPOTHESIS` is what lets a deliberate repeat through. A round cannot start while the previous one has no logged outcome, which is what makes the ledger a precondition rather than a courtesy. A refusal exits 78 and runs nothing. Without `LAUNCH_ROUND` the job behaves exactly as before. The gate also asserts the lane's `SPEC.json` ([`harness/tools/spec.py`](../harness/tools/spec.py)): the challenge capture must match its pinned sha256, every string the lane is scored against must appear in that capture byte for byte, declared lengths must match, the size cap must be declared and present, and every ranking condition must be scored or excused with a reason. A lane with no external challenge sets `"challenge": null` with a reason and still declares its ranking. No `SPEC.json` is a refusal, for every lane. `spec.py --lane L diff` re-reads the live page and reports any scored string that has left it; that is the one step with network and is meant to be scheduled, not run by a worker. |
| `LAUNCH_HOST` (or `--host HOST`) | Run the executor on another machine over ssh; empty means here. `HOST` is an ssh alias, validated before it reaches an ssh argv. The work dir must exist at the **same absolute path** there, or the run refuses rather than landing in the remote `$HOME`. Admission, the word cap, the registry, model selection, the prompt and the log stay on the controller. |
| `LAUNCH_SSH`, `LAUNCH_REMOTE_EXECUTOR`, `LAUNCH_PULL_MAX_SIZE` | With `--host`: the ssh command (default `ssh`), the remote `agent_executor.py` (default `$HOME/.local/share/research-harness/agent_executor.py`, expanded on the host) and the cap on each pulled-back file (default `4m`). After every attempt the heavy outputs stay on the host and only `STATUS.md`, `REPORT.md`, `PLAN.md`, `RESULTS.jsonl`, `*.selection.json` and the job's `.last.md` come back, so status reads here as it did before. A failed pull is logged and does not fail the run. |
| `EVENT_WATCH_CONF`, `EVENT_WATCH_STATE`, `EVENT_WATCH_NOTIFY` | Watch rules (default `.runtime/event-watch/config`), cursor/event state (default `.runtime/event-watch/state`) and optional notification executable. |
| `POLL_GUARD_STATE` | Private hook fingerprint directory; default `.runtime/poll-guard`. |
| `CS_BASE`, `CS_BIN`, `CS_STATE`, `CS_AUTO_READ` | Optional daemon URL, CLI, cookie directory (default `.runtime/cs`) and path-separated auto-readable roots. Auto-read roots default to empty. No port is assumed when the URL is unset: the CLI is asked. |
| `CS_HOST`, `CS_REMOTE_BIN`, `CS_TUNNEL_PORT` | Drive the daemon on another machine (an ssh alias) over a tunnel, for science whose data lives there. The auto-readable roots are then checked on that machine, and a prompt for a path missing there is held. |

All data paths default to the current workspace/runtime, not a personal HOME.
Absolute data paths are accepted when a caller supplies a documented setting,
CLI path or lane configuration. Standard system executable paths such as
`/usr/bin/ssh` and `/usr/bin/trash` are executable dependencies, not data discovery.
Provider CLIs manage their own login/config outside the harness; choose HOME and
provider-specific config directories before invocation.

Judgment roles are `review`, `judge`, `audit`, `taste`, `design`, and `ideation`; `judge`/`audit` use `review` and `design` uses `taste` unless an explicit row exists.
Pass `--role ROLE --made-by MODEL` (or `LAUNCH_MADE_BY`); the maker is required for review/judge/audit, and the first eligible model from another family is selected.
Judgment jobs follow the selected model's CLI route automatically; their specs name the role and must contain no model names.
A judgment `--model` pin requires `--model-override 'Ricardo: REASON'` (or `MODEL_OVERRIDE_REASON`), while family independence and exclusions still apply.
Accepted overrides append role/model/reason/job/utc to `RH_MODEL_OVERRIDE_LOG` (default `model-overrides.jsonl` beside `RH_ROLES_FILE`); other roles retain their explicit-executor behavior.

| Additional setting | Meaning |
|---|---|
| `AGENT_BACKEND` (or `LAUNCH_BACKEND`) | `codex` (default), `claude` or `agy` (Gemini on the Antigravity subscription, `agy -p PROMPT --output-format json`; its sign-in is in the login Keychain, so when a direct call is asked to authenticate the executor relays the same call through a new window of the tmux session `RH_AGY_TMUX_SESSION` (default `base`), which can read it; no such session means exit 76, no keychain access here, and asked again there means exit 77, the owner's one-time sign-in; a job whose `--allowed-tools` include `Bash` may run shell commands); invalid values refuse. `tools/launch.sh` reads either name; both set to different values refuse. The role comes from `LAUNCH_ROLE` (default `batch`). Judgment roles use the selected model's CLI; other roles refuse when their top model has no compatible route for the chosen CLI. |
| `LAUNCH_CLAUDE`, `LAUNCH_CLAUDE_BUDGET` | Claude executable and per-run dollar cap (default `1.00`); no automatic Claude retries. |
| `LAUNCH_CLAUDE_TOOLS`, `LAUNCH_TIMEOUT_SECONDS` | Claude jobs from `tools/launch.sh`: the `--allowedTools` list (default `Read,Write,Edit`; a job that runs its own code adds `Bash` and says so) and the wall-clock cap in whole seconds (default `5400`; `0` means none). The CLI has no turn limit, so spend and the clock are the two bounds. |
| `LAUNCH_CODEX_SANDBOX` | How much a codex job may touch: `read-only`, `workspace-write` (the default), `danger-full-access`, or `bypass`. The first three become `--sandbox MODE`; `bypass` is the single `--dangerously-bypass-approvals-and-sandbox` flag, which turns off approvals and the sandbox together and is not a sandbox level. An unknown value refuses rather than being passed through. The default is deliberate: a job whose transcript is written outside its work dir needs a wider mode, and the host says so once rather than the tool shipping with the sandbox off. |
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

A sweep worker cannot reach X and cannot download. Two asks exist so that is not a dead end.
A search worker may write one `X QUERY <ID>: <query>` line in its report; the sweep files it in the
lane's `X_REQUESTS.jsonl`, adds it to `X_QUERIES.txt` for the general session's browser step, and
one `rh intake x-search` with that query clears it. The receipt rule does not move: a lead with no
X search is still incomplete and still unpromotable, so the ask is a way to get the search run, not
a substitute for it. While the ask is open, that lead's receipt is pending rather than failed: if
its X source is `blocked` and every other source is complete, the sweep is delivered and the lead
stays queued (a SURVIVED one goes back in the queue), so one fresh lead does not fail every pass
until someone runs its query. A wrong X entry, or any other incomplete source, still fails. For data, [`inputs.py`](../harness/tools/inputs.py) stages a public file once,
by hash, and the worker prompt now lists what is staged and how to get a path offline; a worker that
needs an unstaged file says `BLOCKED: need <name> from <url or repo@commit and path>` and a person
stages it. Before 11-07 neither was reachable from a sweep: a lead found during a run could never
have its X query asked, and no prompt mentioned staged inputs at all.

`SWEEP.toml`'s `host` (default empty, meaning here) is the machine a lane's workers run on, an
ssh alias validated in the same shape `launch.sh` validates. It reaches the launcher as
`LAUNCH_HOST`, so the work dir must exist at the same absolute path there. An explicit
`LAUNCH_HOST` in the environment wins over it, which is how one run moves without editing the
lane. Before 11-07 the only way to say where a lane's work ran was a flag on each launch.

`SWEEP.toml`'s `min_free_gib` (default 30) is the floor on **the machine that runs the workers**:
the lane's `host` when it has one, otherwise the controller. `controller_min_free_gib` (default 2)
is the controller's own floor, because specs, logs, receipts and pulled-back status files land
there even when the work does not. If the host's disk cannot be read, the sweep refuses rather than
assuming it has room. Before 11-07 the floor always measured the controller, so moving the workers
to a second machine refused every sweep on a disk that was not doing the work. On a host where the
work dir does not exist yet, the floor is measured at its nearest existing parent, because the
sweep's mirror creates it right after this check (11-10).

`SWEEP.toml`'s `worker_path` (default empty) lists absolute directories put first on the worker's
`PATH`, both here and on the host (as `LAUNCH_REMOTE_PATH`). A lane whose checkers need a venv names
its `bin` directory there, so a bare `python3` in any stage is that interpreter. 11-10: a math kill
test was blocked on a missing `flint` module because the m5 worker ran the system `python3`.

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


Lane registry entries (`RH_LANE_REGISTRY` or `lanes/REGISTRY.json`) may declare
`"x": false` to bar that lane's drafts from X review. The optional field must be a
boolean and is independent of lifecycle status. Aliases resolve to the same policy;
`x:true` cannot override an explicit no-X rule in the canonical or alias RULES.md.
Encode prose restrictions with `x:false` so consumers need no natural-language inference.

## Claude ceiling, pacing, Sonnet default, lane shares (11-20)

Ricardo: Claude must never reach 100% (general runs on it), Sonnet is the default, MecCog sits at the bottom.
`harness/claude_cap.py`, applied by `worker_models.select()` to every Claude pick:

- Ceiling: weekly at or above `RH_CLAUDE_CEILING_PERCENT` (80) refuses Claude; the job takes Codex's default for
  its role, else agy's Claude, else the launch is refused. A pinned or explicit model is refused, not swapped.
  `claude_warning` in the receipt from `RH_CLAUDE_WARN_PERCENT` (70).
- Pacing: weekly + burn %/h x hours to reset above 80 moves Opus to Sonnet; at `RH_CLAUDE_PACE_OFF_PERCENT` (100)
  the job leaves Claude. Burn is the slope of `usage/claude-history.jsonl` (claude-usage appends a row every
  reading, 14 days kept) over 6 h, else the week's average. The receipt's `claude_cap` says why.
- Default model: Sonnet 5.5. Opus needs a spec line `Model: opus, REASON` (no reason refuses the launch); the
  reason is in the receipt (`opus_reason`) and the log.
- Lane shares: `~/.config/rstack/claude-shares.json` (`rstack/tools/claude-shares.json.example`), per lane
  `max_week_percent` and `models`, with a `default`. Measured from Claude Code transcripts (token-weighted, Opus x5,
  fraction of all transcripts since the week began x the weekly percent). Limits: a session in a directory not
  named for the lane is unattributed; chat and desktop use leaves no transcript. The weekly figure stays the hard bound.
- `RH_CLAUDE_CAP=0` turns all of it off.
