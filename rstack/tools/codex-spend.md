# Codex spend at the executable boundary

The 11-17 failure was an ordinary Python loop calling `codex exec` 1,568 times, outside
`launch.sh`. `codex` now supervises the native CLI instead of replacing itself. It preserves
privacy routing, stdin, stdout/stderr and the native exit status, reserves a call under a file
lock before spawning, then appends that run's tokens and cache share from its rollout.
`CODEX_INTERNAL_ORIGINATOR_OVERRIDE` identifies concurrent new sessions; resumed sessions use
saved offsets and subtract their previous cumulative token totals. Prompt bodies are never logged.
The wrapper reuses the local allowance reader. The launcher applies only its tmux concurrency cap.

`harness-sync` ships the executable and its dependencies from committed source into
`<installed-root>/rstack/tools/`. Keep those files together. Runtime state stays in
`$RSTACK_STATE_DIR/codex-ledger/`, default `~/.local/state/rstack/codex-ledger/`.

## Policy

- Lane: `RSTACK_LANE` (aliases resolved), then the job name (`RH_JOB`, which the launcher exports,
  `LAUNCH_JOB`, `LAUNCH_JOB_NAME`, `JOB_NAME`) matched against the lane registry's lane names,
  sessions, aliases and `job_prefixes` (e.g. `"digest": {"job_prefixes": ["nightly"]}`), then cwd
  patterns `open-science/<lane>_*`, `<anchor>/<lane>` for each host `lane_anchors` entry,
  `lanes/<lane>`, finally cwd basename, each resolved through the registry the same way. A name no
  lane claims gets the default limits and one warning line naming the job (11-18: the nightly and
  bio's `hunt_*`/`ref_*` jobs were each billed as a lane of their own at 3%/day).
- Privacy routing: batch runs whose working directory is under a host `personal_roots` entry
  use `~/.codex`; all other batch runs use `~/.codex-clean`. Both lists live only in the host
  config, so private paths never enter this repo.
- Default: 60 admitted calls per rolling hour, 3 percentage points of the weekly allowance
  per rolling day, charged only from that lane's weighted ledger tokens (see below).
  `games` and `open-source` default to 200 and 10, respectively.
  Configure finite positive overrides in `~/.config/rstack/codex-budget.json` or
  `CODEX_BUDGET_CONFIG`; see `codex-budget.json.example`.
- A twentieth call sharing the first 4,096 prompt characters is refused when previous calls
  used over 20,000 input tokens and under 20% cached input. The window is ten minutes, with
  an additional sustained-hour check: the incident's calls spaced a minute apart cannot
  fit twenty calls into ten minutes. Pending long prompts reserve slots conservatively.
  `tell-general decision` runs once per lane per ten-minute alert interval.
- After fifty total calls, record a finite estimate:
  `codex-budget estimate LANE --calls 100 --tokens 27000`. Tokens are estimated input tokens
  **per call**, so this records 2,700,000 planned input tokens. The estimate has finite call
  and token totals and does not override any limit.
- Account alerts: 50%, 70%, 85%, once per reset window. The wrapper and companion launch
  legacy guard share `RSTACK_STATE_DIR/allowance/alerts.json` and its lock. The launcher does not call that guard. Above 85%, batch calls
  require nonblank `LAUNCH_URGENT`. Every admitted urgent attempt there is logged and sent
  directly to `owner_command` (default `~/.local/bin/notify-ricardo`); failed delivery refuses.
- Priority requires `LAUNCH_URGENT`, regardless of the account percentage. Without it,
  priority CLI overrides are removed and logged, config/profile priority is suppressed and
  logged, and a final effective empty `service_tier` requests the native standard tier.
  Native 0.167.0 was checked offline: this tier is omitted from requests.
- A TTY session without `exec`/`e`/`review`/`debug prompt-input` is never refused by these
  limits. Above 85% it warns. Local help, version and CLI management do not spend a call.
  Batch `--ephemeral` refuses because it disables the required rollout accounting.
- Missing/reset allowance snapshots refuse batch calls until an interactive session supplies
  a current snapshot. Successful runs with missing usage, or dead wrappers with incomplete
  accounting, stop further batch work in that lane until their accounting is repaired.

JSONL start/finish records join on `call_id`. Finishes contain input/cached tokens, cache
share, rollout paths and sizes, start/end allowance snapshots, percentage delta and native
exit status. Finishes also record output tokens (including reasoning) and model/rate-weighted
tokens. Refusals, stripped priority requests, estimates and urgent reasons are separate
append-only events. Run starts are reservations, so concurrent calls cannot race the call cap.
The wrapper forwards INT, TERM and HUP and records the resulting native exit.

## Lane percentage accounting

A lane's rolling-day charge is the sum of its completed calls' weighted tokens divided
by calibrated weighted tokens per weekly percentage point. Finishes count on their
completion date, including calls started before the window. `bio` history still counts
against `open-source`. A pending call never reserves account-wide percent movement;
call reservations and incomplete-accounting refusals still apply. A single admitted
run can exceed its budget before the next admission.

Weights reproduce the 11-17 accounting's rate card in Sol-input-equivalent units:

| Model | Uncached input | Cached input | Output | Priority multiplier |
| --- | ---: | ---: | ---: | ---: |
| GPT-6.1 Sol | 1 | 0.05 | 5 | 2.5 |
| GPT-6.2 Sol | 1 | 0.05 | 5 | 2 |
| GPT-6.2 Astra | 4 | 0.2 | 20 | 2 |
| GPT-6 Astra | 5 | 0.5 | 25 | 2.5 |
| GPT-6 Sol | 1 | 0.1 | 5 | 2.5 |
| GPT-6.1 Terra | 0.5 | 0.025 | 2.5 | 2.5 |

Input counts include cached input: subtract the cached tokens before weighting uncached
input. Reasoning tokens already belong to output. Turn contexts supply the model and,
when present, tier; resume accounting subtracts the prior cumulative counts. Unknown
GPT models use the 11-17 Sol fallback; other-provider models do not count. Legacy finishes
recover weights from their saved rollout byte boundaries and wrapper timestamps, cached
in `codex-ledger/.legacy-token-usage.json`. Missing old rollouts can only contribute their
recorded input/cache tokens, with Sol weights; output and model cannot be recovered.

On the first batch admission of each UTC day, all local lane ledgers in the past week
supply tokens and snapshots for one same-reset account window. Calibration divides total
weighted tokens in that window by its account percentage change, without summing
per-call overlapping deltas. It needs six hours, five points, ten finishes, monotone
snapshots and accounted usage. The result and source are stored in
`codex-ledger/.token-calibration.json`. If no usable window exists, retain the last fit;
otherwise use 5,000,000 weighted tokens/point: the conservative 11-17 measurement of
250 credits/point divided by 50 credits per million Sol input tokens. The measured
250–285 range corresponds to 5.0–5.7 million weighted tokens/point.

Other machines and native bypasses can move the account meter without appearing in a
host's ledger. A candidate below 4,000,000 weighted tokens/point (200 credits, 20% below
the conservative measured rate) is treated as insufficient ledger coverage and keeps
the prior fit/fallback. This does not establish full account coverage: a partially
observed window can still pass that bound. The scale is an estimate; host ledgers and
calibrations are independent. Account alerts and the urgent-only rule continue to use
the unmodified account snapshot.

## Operator installation (not performed by this change)

First land the reviewed commit into the controller's normal sync ref. Otherwise a later
scheduled sync against an older ref would disagree with the deployment. No credential file
needs copying. The controller's updated `harness-sync` must be used for the first install;
an older copy does not know about these rstack files.

1. Run that `harness-sync --repo REPO --ref COMMIT` on the controller and then
   `harness-sync --repo REPO --ref COMMIT --host HOST`. The normal root is
   `~/.local/share/research-harness`. Existing running-job refusals still apply.
2. On **each** Mac, create the host config. Use absolute notifier argv paths so a minimal
   environment can still deliver alerts. For example:

   ```sh
   /usr/bin/python3 - <<'PY'
   import json
   from pathlib import Path
   home = Path.home()
   path = home / '.config/rstack/codex-budget.json'
   path.parent.mkdir(parents=True, exist_ok=True)
   if path.exists():
       raise SystemExit('Merge these settings into the existing config; preserve its limits.')
   cfg = {'defaults': {'calls_hour': 60, 'weekly_percent_day': 3},
          'lanes': {name: {'calls_hour': 200, 'weekly_percent_day': 10}
                    for name in ('games', 'open-source')},
          'notify_command': [str(home / '.local/bin/tell-general')],
          'owner_command': [str(home / '.local/bin/notify-ricardo')]}
   path.write_text(json.dumps(cfg, indent=2) + '\n')
   PY
   /usr/bin/python3 "$HOME/.local/share/research-harness/rstack/tools/codex-budget" activate \
     --entrypoint "$HOME/.local/bin/codex" --entrypoint /opt/homebrew/bin/codex
   ```

   Add `--npx "$HOME/.local/bin/npx"` to replace npx with the shim that refuses
   `npx codex` / `npx @openai/codex` (the real npx moves behind `~/.local/libexec/npx-real`).
   Activation preserves every replaced file/symlink in `codex-ledger/entrypoint-backups/`;
   it never follows the brew symlink to overwrite the native binary. Both PATH entrypoints
   now point to the installed wrapper. The wrapper reaches the native only through
   `~/.local/libexec/codex-real`, a symlink activation points at the newest
   `/opt/homebrew/Caskroom/codex/*/bin/codex`; no version is pinned in code.
3. Point the existing scheduled `~/.local/bin/job-health` at the installed
   `rstack/tools/job-health` (preserve the old copy with a move before making the symlink).
   Its companion `_codex_budget.py` must be beside the resolved target. The existing
   `--prefix ... --alert '/absolute/tell-general decision'` schedule is sufficient;
   no launchd plist change or new schedule is needed. `codex-budget activate` records
   activation time and entrypoints in `RSTACK_STATE_DIR/codex-deployment.json`.
4. `job-health` checks those entrypoints on every scheduled run. If `brew upgrade --cask codex`
   replaced the brew symlink, it preserves that new symlink, restores the wrapper and alerts
   general. It also re-points `codex-real` at the newest Caskroom version and restores the npx
   shim. A wrapper that finds `codex-real` dangling (the old version removed) re-points it before
   running. Run job-health immediately after every upgrade as well, before starting new jobs;
   the interval between replacement and repair is a real exposure window.
5. Inventory executable files and symlinks named `codex` under `/opt`, `/usr/local`, `~/.npm`,
   `~/.nvm`, `~/node_modules`, and any additional local Node prefix. Activate each extra
   executable entrypoint with `--entrypoint PATH` **alongside both existing entrypoints**.
   Do not activate the Caskroom native path itself. Preserve copies rather than deleting them.
   Existing npm/npx Codex copies are thereby redirected to the same wrapper.
6. Verify with `command -v codex`, `ls -l ~/.local/bin/codex /opt/homebrew/bin/codex`,
   `codex --version`, and `codex-budget check`. These do not make a model request.
   Configure `codex_homes` or path-separated `CODEX_HOMES` for homes outside normal discovery.

## What the backstop detects

The deployed job-health discovers Codex homes under the login home using the allowance reader,
plus explicit homes and homes remembered by the wrapper. It reads rollout metadata and compares
all files modified since activation with ledger coverage. A new unledgered session reports its
cwd. Appending to an already-accounted session through an absolute native path is also a finding.
Live reservations count as coverage; completed runs cover only their recorded byte sizes.
Findings use the existing persistent asks-waiting report and once-per-new-finding general alert.
Failed alert delivery is retried. `--dry` and `codex-budget check` do not repair or notify.

These are admission controls and a scheduled detector, **not OS isolation**. An absolute native
path, a freshly downloaded `npx @openai/codex`, an independently supplied client, or a remote app
server can run outside this wrapper. Local persisted rollouts are detected on the next health
run; ephemeral/deleted rollouts and remote-only sessions are not observable. There is no honest
same-user filesystem installation that prohibits every arbitrary executable while retaining the
native binary. Existing in-flight runs are not stopped, and a single admitted long run can pass
a percentage boundary before the next admission. Weekly percentages have the provider's meter
granularity. Lane charges are estimates from their own tokens, not per-lane provider billing.
Local ledgers do not aggregate live calls
across Macs. Threshold delivery state is once per host unless a shared state directory is used.

Tests use synthetic rollouts, fake native processes and temporary PATH entrypoints, never an
authenticated provider or real notifier:

```sh
python3 -m pytest -q rstack/tests
python3 -m pytest -q tests/test_harness_sync.py
```


`bio` is a compatibility alias for `open-source`, sharing its ledger and finite higher
limits. A lane may additionally configure `calls_run` (positive and finite). Unattended
calls in that lane require `RSTACK_RUN_ID`; admission counts all start reservations for
that ID, including unfinished calls and calls older than one hour. Set one run ID in
the parent scheduler before probes, phases, repairs and child calls. It caps wrapper
invocations, not the model's internal turns or the tokens of a single admitted run.

The health backstop caches whole-home discovery in
`RSTACK_STATE_DIR/codex-home-discovery.json` for six hours. Cold/expired caches still run
full discovery. Every pass scans all rollouts in all known homes, with no newest-N
truncation: configured, environment, conventional and wrapper-registered homes are read
immediately. Unknown native-only project homes may take up to six hours to discover.
`--dry` reads but never populates the cache or repairs entrypoints.
