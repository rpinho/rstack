# Agent entry point

> **HARD RULE (11-04): the goal must not turn into process, and success is never activity.** A lane exists to find something new. Our failure mode is the ask being reframed into gates, receipts, audits and validation layers, then tests, checks, ideas and verdicts being counted as progress. Enforced in code, not prose: `launch.sh` refuses new specs over 1,000 words without `SPEC_OVER_CAP=<reason>` and lints every job for `You asked: ... I will: ...` (STATUS.md) and `Shipped: ...` (REPORT.md) into a job-yield ledger; `lane-yield` fails any lane that spends 20+ job-hours with no refereed new result (`lanes/<lane>/RESULTS.jsonl`, written by `log-result`) or whose referee passes 90%+.


**Please let's do normal things unless they don't work.** Standard method first; deviate only after it fails, and say where. Trivial predictor and simple baseline before any predictive claim. Every result answers one question: did you find something new, yes or no? [Normal first](docs/normal-first.md).

Run bounded agents on open research problems and competitions.
Keep ideas, frozen tests, evidence and delivery cadence in a local **lane**.
Use independent sealed selection; this repo ships code and synthetic examples.
Wake the conductor through scripts, never peer messages: [conductor inbox](docs/conductor-inbox.md).
Lanes that go quiet get a scheduled resume prompt, not a reminder in prose: [lane nudge](docs/lane-nudge.md).
Lanes that spend without finding anything new, or whose referee passes everything, fail a scheduled test and stop: [lane yield](docs/lane-yield.md).
The installed copy comes only from committed repo code; never edit it in place. Host paths go in a local env file: [harness sync](docs/harness-sync.md).

## Set up and run

- Install with one command: `scripts/bootstrap.sh` (macOS/Linux, Python 3.9+).
- Activate: `. .venv/bin/activate`. Run all tests: `python3 -m pytest -q`.
- For installation requests, use [.claude/skills/install-harness/SKILL.md](.claude/skills/install-harness/SKILL.md); its script installs, tests and runs the offline toy demo.
- Before creating the user's lane, read [.claude/skills/new-lane/SKILL.md](.claude/skills/new-lane/SKILL.md). Use facts already supplied; ask only for missing facts. For an unattended toy, record conservative provisional split assumptions; do not invent evidence or contact the user when the prompt already supplies the problem and rules.
- Create with `rh --root .runtime lane new NAME --help`; provide problem, metric, dev set, hidden test, split/reason, sealed set ID, deadline and submission rules. Use `--deadline-days 7` for seven days from creation. Then `rh --root .runtime lint NAME`.
- New lanes freeze `LANE.json` and `SELECTION.json` before any result. If a provisional assumption or identifier changes, create a new lane; never edit frozen fields or recommend doing so. Leave `n_trials_total=0`, no measurements, no invented prior-art receipts. A setup-only 24h lint grace ends when work begins. A clean setup lint is not evidence of research progress.
- Before previewing, load [.claude/skills/run-sweep/SKILL.md](.claude/skills/run-sweep/SKILL.md) (or invoke the `run-sweep` skill). Preview: `scripts/run-sweep.sh --root .runtime NAME`. It prints search/read/kill plans with no workers or network.
- For a real sweep, configure actual data/sources, compatible model routes and worker limits; review the preview, then set `workers_enabled = true` in the lane's `SWEEP.toml`. Run `AGENT_BACKEND=codex scripts/run-sweep.sh --root .runtime NAME --execute` (or `claude`). This may spend money. Dry-run requests authorize only a preview.
- Config lives at `ROOT/lanes/NAME/{INTAKE,SWEEP,CADENCE,OUTREACH}.toml`; new lanes also have frozen declarations and `RULES.md`. Runtime default: `.runtime/`. See [configuration](docs/configuration.md) for executor auth, routes and explicit paths. Provider CLIs require their own account; never copy credential files into a clone.
- Record actual browser outcomes: `rh intake x-search LANE --query Q [--subject S] --result none|hits --n N` (requires `x_local_file`; records locally without searching).
- Use `AGENT_BACKEND=codex|claude`; there is no model/backend substitution. The offline demo requires neither CLI nor login.
- Heavy jobs run where there is memory and disk, not on the controller: `tools/launch.sh JOB WORKDIR --host HOST` runs the executor on another machine over ssh, with the work dir at the same absolute path there. Status and receipts still read on the controller. One flag, no per-lane variants: see [configuration](docs/configuration.md).

- For retros and cross-lane learning, use [run-retro](.claude/skills/run-retro/SKILL.md) and [lessons](docs/lessons.md).

## Hard rules

| Never break this rule | Code enforcing the instrumented boundary |
|---|---|
| Never score candidates yourself on sealed data; never select on a board you can see. Use dev folds; only an independent selector sees sealed targets. | [Lane audit](harness/lane_setup.py), [worker prohibitions](harness/sweep.py), [sealed disposition](harness/idea_policy.py), [pre-scoring budget](selection/selection_gate/v2.py). Operator must isolate hidden data; declarations cannot create filesystem isolation. |
| Freeze the test and bar before the first result. Never edit a freeze to fit results. | [Lane hashes](harness/lane_setup.py), [idea freeze and result admission](harness/idea_policy.py), [v2 replay](harness/selection_policy.py). |
| Claim only the scoped verification level supported by the evidence; label whole results and finite components separately. | [Verification levels L0–L3](docs/verification.md), [row and receipt validation](harness/verification.py). |
| No outreach without `rh outreach` approval. | [Draft/lint/approve/send ledger](harness/outreach.py), [email approval hook](tools/email-voice-gate.py). Install hooks at your send boundary; the harness cannot intercept arbitrary send tools. |
| Bound every worker; let pods end themselves. | [Sweep time/process-tree limits](harness/sweep.py), [launcher retry limits](tools/launch.sh), [pod TTL/idle runner](harness/pod/runner.py), [pod reap](harness/pods.py). |
| Send deletions to Trash; never use destructive cleanup. | [Trash-only storage adapter](harness/storage.py). On Linux configure `RH_TRASH_COMMAND`; missing Trash refuses deletion. |

## Route requests

| When the user asks… | Do… |
|---|---|
| “Install”, “set this up” | Read and use `install-harness`; run its script, report tests and toy preview. |
| “Use this for my problem”, “new competition” | Read and use `new-lane`; create frozen v2 declarations with `rh lane new`, then lint. |
| “Sweep”, “dry run” | Read and use `run-sweep`; preview and show the plan; execute only when requested. |
| “Check overfitting”, “audit selection” | Read and use `check-overfitting`; report all ten declared/undeclared practices with limits. |
| “Send/contact someone” | Use `rh outreach --help`; draft, lint, obtain recorded approval, then send through the gate. |
| “Clean up” | Move artifacts to Trash; keep frozen evidence and ledgers. |
