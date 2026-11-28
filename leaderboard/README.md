# Model routing and scoring

The public table in [`LEADERBOARD.md`](../LEADERBOARD.md) reads the shared
`run_grades.table()` join directly, including models with runs and no grades.
Its default window is 30 days (`model-roles.py public --days N`). Run timestamps
select joined rows; dates select unmatched historical grades. Rows are grouped
by assigned role and ordered by the Wilson 95% lower bound, with `n<20, unranked`
below 20 graded outcomes. Both role and overall rates show a Wilson 95% interval;
partials retain half credit. These descriptive intervals do not correct for
selected tasks, repeated jobs, subjective grading, or different task mixes.

`Rank (Ricardo: taste + cost)` copies the owner's values from the previous
snapshot, falling back to the explicit owner map. It never uses pass rates or
routing positions. Opus 5.5 and Neon-high remain tied #1; Carbon (10-28) replaced
Argon. Unknown owner ranks show a dash. Bench results appear in a footnote.

Quota, probe, harness-failure and void grades do not enter the denominator.
Incomplete-workdir rows and old controller-side grades of remote work are
excluded with reason counts. For legacy zero-exit automatic failures recording
both missing headers, the reader checks the files in the workdir named in the
original spec or saved launch command. Reused sweep job names are matched on the
full output path. These are read-only exclusions, not historical regradings.
Driver outputs are counted separately as graded only for pass/partial/fail.

Hourly health calls set `RH_RUN_PURPOSE=probe`; the executor persists
`purpose=probe` and writes `void: probe`. Old `canary-*` jobs get the same
read-time disposition. Neither public work counts, intake nor `--owed` includes
probes. The separate routing snapshot retains candidate order and optional cost
per pass for bootstrap. Routing code, pools, inheritance and the n<5 routing rule
are unchanged. Aggregated routing evidence and feeds never fabricate raw public
grades. Only allowlisted model/role/count/rank/rate fields are exported; task text,
paths, prompts and private evidence remain local. Existing dated observation
labels remain separate from the current pass-rate table. The routing details
below describe the selector, not the owner's or the within-role public rank.

```sh
export RH_ROLES_FILE="$PWD/.runtime/roles.json"
python3 leaderboard/model-roles.py bootstrap
python3 harness/worker_models.py --role batch --executor codex \
  --log .runtime/example.log --receipt .runtime/selection.json
```

Selection refuses an incompatible executor or excluded model; it never silently skips to a lower-ranked provider. A fixed model needs `--model-override REASON`. Completion receipts retain the actual model and roles-file hash even if routes change mid-job. An exit code stays unscored.

To route an eligible OpenRouter model, register its canonical `provider/model` ID with `cli: openrouter` and include it in the role pool; selection automatically runs Codex with `LAUNCH_PROVIDER=openrouter`. For a matched candidate trial use `tools/launch.sh JOB WORKDIR --role ROLE --explore MODEL` (and `--made-by MODEL` for independent judgment): it requires a listed, eligible candidate and records `source: explore` without an override. The executing shell reads `$HOME/.config/openrouter/key` into `OPENROUTER_API_KEY`; the key never goes into logs, receipts or saved commands. The order is LEADERBOARD.md; never name a model for a judgment role in the task prompt.

As of 2026-11-18, Google models are excluded from every served role, including candidates introduced by new evidence and routes recovered by bootstrap. The owner's reason: "Spending OpenRouter money on Google is a waste". This routing preference cannot be lifted by a high score. Existing Google route metadata, observations and dated ranking rows remain available as history. The Gemini transport remains available for explicit comparisons; it does not make a Google model eligible for a served role.

Since 2026-11-19 routing uses everyday delegated work only: real lane tasks
graded pass, partial (half) or fail when they come back. The selector retains its
n<5 seed/candidate rule; the public table instead prints every observed rate and
requires n>=20 for a within-role rank. Planted-claim referee benches, known-answer
reproductions and matched mini-tasks remain correctness smoke tests. Their
explicit bench rows never change a rank, pool or setting and appear in the
public footnote. Owner, 11-19: "Those are synthetic tests. I wouldn't use synthetic
tests as the guidance... It's everyday work."

Since 2026-11-20 cost per pass shows the share of the weekly plan spent per passed
everyday task (`job_cost.py`). It now appears in the separate routing details.
The existing cost tie-break, missing-source behavior and routing calculations
are unchanged by the public table repair.

The public work table also shows model-wide median and mean dollar estimates for
eligible passes in its displayed window. Each cell shows the number of available
estimates over all passes. API-equivalent estimates use the dated rates in
`prices.json`. Subscription estimates allocate the weekly equivalent of the
monthly fee using measured tokens and the calibration in `plans.json`. These
figures describe the passes with cost evidence. Sparse coverage limits comparisons.

The executor captures token breakdowns at close and grades carry the breakdown
and estimates. Use `python3 leaderboard/backfill_costs.py` to append recent
graded-run costs beside `MODEL_LEDGER` (by default, `MODEL_STATE/evaluations.jsonl`).
Use a scratch state directory with a ledger copy for an offline trial. The
backfill uses the normal run-to-grade join and reads execution telemetry locally.
`RH_CODEX_SESSIONS` selects a colon-separated list of rollout directories,
`RH_CLAUDE_PROJECTS` selects the Claude project log root, and
`RH_AGY_USAGE_DECODER` and `RH_AGY_CONVERSATIONS` select the agy decoder and
conversation directories. `python3 leaderboard/calibrate_costs.py` prints
calibration evidence for review before changing the plan card.

Since 2026-11-19 only subscription routes are served (`claude`, `codex`, `agy`); OpenRouter and Gemini API models are history only. The exclusion above applies to the Google API routes. Gemini 3.8 Flash on the Antigravity subscription (`agy`, tiers high, medium and low) and Gemini 4 Neon, Argon and Hydrogen (medium tier) enter every role except writing as candidates after the seeds, and move only by the Wilson rule like any other model.

The Astra seed slot for review, judge and ideation is `gpt-6.2-astra`. This is the requested routing preference, not a claim of general superiority: the 11-17 v3.1 calibration has five overall winners, and GPT-6.2 Astra completed none of three ideation calls within 480 seconds. Existing Anthropic first picks remain in place.

## Local scoring

`model-eval.py` validates private observation ledgers: anchored scores 0..4, evidence references, finite optional costs and append-only supersession. It can print a local diagnostic including task and cost fields. That diagnostic is private; it is never used as the public Markdown export.

`model-roles.py ingest` requires at least one explicit evidence path. `RH_EVIDENCE_ROOT` selects a harness root and reads idea histories only there. A taste promotion is held when it ships, overturned when a later structured close identifies prior art, duplication or a rule violation. A failed kill-test does not by itself mean the proposal was a mistake. An unreversed judgment close settles after 14 days. The generic proposer adapter separately credits `proposed_by` for reaching testing, even if a candidate later fails its own bar. Optional review receipts under `MODEL_REVIEW_ROOT` score flags against revised document bytes; `MODEL_DRAFTS_LOG` scores explicit sent-as-drafted/rewritten/dropped outcomes without reading recipients. All inputs require explicit paths. Other sources can supply validated local observations directly; no personal archive, transcript, contact or account discovery adapters are included.

Only one process should write the model observation ledger at a time. It is validated before recomputing; malformed observations refuse ranking instead of disappearing.

`recompute` requires at least 5 resolved observations on 2 distinct days before a challenger can move on evidence. It passes an adjacent model only when its 95% Wilson lower bound exceeds that model's held rate. A model without sufficient evidence has seed rate 0.75. Ideation prioritizes distinct labs in its first two picks where possible. Configured exclusions are explicit; evidence can lift one only at 20 observations under the ranker's rule. Overrides are written to local routes and omitted from public exports.

```sh
export RH_EVIDENCE_ROOT=/path/to/private/runtime
python3 leaderboard/model-roles.py daily
python3 leaderboard/model-roles.py public --output /path/to/review/LEADERBOARD.md
```

`model-roles.sh` wraps the local daily command. The compatibility filename `model-roles-publish.sh` only generates a local export; it has no Git, upload or network-publication step. Review and scan exports before publishing them yourself.

`model-mine.py --archive ROOT --out DIR` deterministically scans supplied bookmark JSON under `ROOT/raw/bookmarks/`. It prints file/item denominators and writes local text dumps; those dumps can contain personal material and must remain outside public content. Mining output never flows into the public exporter automatically.

The ranker uses the [Wilson score interval](https://doi.org/10.1080/01621459.1927.10502953). Small samples, selected tasks, correlated runs, subjective outcomes and seed choices limit interpretation. This code does not run matched benchmark trials or establish causal comparisons between models.

## Receipt-linked daily scoring

`daily.sh` reads outcome evidence, recomputes routes, exports the page, and scans
it with `rstack/tools/egress-gate`. A changed page is committed in a separate,
reusable worktree based on the fetched remote main branch, then pushed to main.
The main checkout is never edited or committed. A failed command exits nonzero;
a rejected push leaves its commit in the landing worktree for inspection. There
is no force push. Run only one writer against a ledger at a time.

Configure paths explicitly (none are discovered from a personal home directory):

```sh
export RH_EVIDENCE_ROOT=/path/to/runtime
export RH_LAUNCH_RECEIPTS=/path/to/launch-receipts
export MODEL_OUTCOMES_ROOT=/path/to/outcomes
export MODEL_STATE=/path/to/scorer-state
export MODEL_LEDGER="$MODEL_STATE/evaluations.jsonl"
export RH_ROLES_FILE=/path/to/roles.json
leaderboard/daily.sh --dry-run --scratch-dir /path/to/new-scratch-directory
```

Dry run copies an existing ledger into scratch and writes the new ledger,
roles and page there. Give it a scratch directory without scoring outputs.
The regular hourly tick refreshes the local page and roles, imports driver
outputs, and runs the scoring canary. Run `leaderboard/score_canary.py` for a
read-only check. Its `graded` count includes all four grade categories.

Use `--publish` on an authorized tick to publish the page. `PYTHON` can
select an existing interpreter. `MODEL_SCORER_REMOTE` and `MODEL_SCORER_BRANCH`
default to `origin` and `main`. The inactive
`com.example.model-scorer.plist` template uses a one-hour interval.
Replace its placeholders before installing it.

With `RH_LAUNCH_RECEIPTS` set, receipt-linked adapters replace the legacy
self-attributed readers. The older review/draft readers remain available through
local ingestion without this variable; the daily runner uses receipt-linked sources only. Old receipts use their
`JOB.log.selection.json` filename; newer receipts can declare `job`, `job_id` or
round aliases. Specs can survive as `JOB.log.prompt` after `JOB.md` is removed.
Directory names, explicit output artifacts and `_codex/JOB.*` stems join native
outcomes to those jobs. The launcher's injected shared context is excluded from
artifact links.

Provenance is ranked: a selection `receipt` first, a saved `launch-command`
second, and a launching session's `transcript-call` third. Every new observation
records its link kind and evidence paths. Configure `MODEL_LAUNCH_ROOT` for the
launcher's `JOB/ATTEMPT/run.sh` records, and `MODEL_TRANSCRIPTS_ROOT` for supplied
Claude or Codex transcript JSONL. Commands must explicitly set a versioned model;
Agent calls must set `model` and name their work directory. No home-directory or
account discovery occurs. Conflicts at the best available rank remain unlinked.
A model named only in REPORT/STATUS prose, or an executor exit code, never links. A new
versioned native model ID or canonical `provider/model` ID registers its route
automatically. Bare family names do not identify a model version. New models appear
in their observed roles immediately, including roles entered through explicit
launch specs and their output artifacts. Their cells remain unscored until they have
five resolved observations on two days. Promotion still uses the existing Wilson
rule. `design` starts with taste's order, and `judge` with review's order.

`outcome_adapters.py` reads `lanes/*/IDEAS.jsonl`, `RESULTS.jsonl`,
`REFEREE.jsonl` and `.upstream-prs.json`. It streams JSONL and rejects malformed
rows with their source line. Idea histories credit `proposer_job` (or `job`) for
reaching testing or a result; prior-art and duplicate closures count against it.
A fair failure at the frozen bar or an engineering stop is neutral. Taste calls
use `decider_job`/`decision_job`; promotion is settled by the later disposition,
and an unreversed close settles after 14 days. Plant records score one batch:
all plants caught is held, any plant confirmed is overturned, and an incomplete
batch stays pending. The verdict artifact's path identifies its producing job;
the referee's self-reported model is ignored.

For additional structured sources, `MODEL_OUTCOMES_ROOT` reads direct `*.jsonl`
and `*.outcomes.json` files, plus one-level `*.outcomes.json[l]`, `referee*.md`
and `ledger_verdict.md` files. Direct `*.verdict.md` files are also supported.
Each resolved record has `id`, `date` (or `utc`), `source_kind` and a producing
job. The supported fields are:

| Kind | Job link | Outcome |
|---|---|---|
| design | `design_job` or `job` | `referee`/`verdict`: HOLDS, HOLDS WITH CAVEATS, FAILS |
| judge | `judge_job` or `job` | `judge_outcome`/`ruling_outcome`: confirmed, overturned |
| review | `review_job`/`referee_job` or `job` | `plant_caught`: true, false |
| ideation | `proposer_job` or `job` | `status` history and `close_kind` |
| pull-request | `opened_by_job` or `job` | `merged_at`, or `state: closed` without a merge |

Markdown verdicts use the same labelled fields, for example `Design job:`,
`Judge job:`, `Judge outcome:` and `Date:`. A general HOLDS on a result does not
confirm every earlier judge ruling. A native audit explicitly naming the judge
it independently recomputes can confirm or overturn that ruling. A later explicit
correction overturns it even when the narrower scientific result still holds.
Rulings without a later disposition stay pending; interim full-panel verdicts
also stay pending. Unlabelled verdicts count as unlinked.
Result artifact paths can identify a design directly, or through a producing
run's `JOB.md` reference to `DESIGN.md`; a labelled `Working dir:` associates a
receipt with a work directory. Ambiguous artifact links are skipped.

`MODEL_UPSTREAM_ROOT` optionally reads supplied PR JSON/JSONL caches. Native
upstream caches without opening-job metadata remain unlinked; mentioning a PR
in a job spec does not establish who opened it. When a cached closed PR lacks a
closure timestamp, its observation day is the cache's `fetched` date.

Nested `*/claims/*/VERDICT.md` files can resolve a production job when its saved
spec explicitly writes that claim and a separate referee job owns the verdict.
The producing job keeps its selected role (for example batch); it is not recast
as a designer. A separate launched execution of an explicitly referenced frozen
design credits admission to testing for the originating ideation job. Repeated
native referee reads of one design or ruling retain one active disposition.
These admission, technical correctness, plant and taste outcomes have different
meanings and are not matched model trials. When a verdict has no date, its
issuing launch date is used; no model identity comes from the verdict's prose.


### Scoring records and driver sessions

`harness/model_slugs.py:canon` is the shared resolver for model runs, grades and scorer observations. Explicit effort tiers and API routes retain their own keys; bare subscription Hydrogen resolves to high. New score writes accept only `pass`, `partial`, `fail`, `harness_fail` or `void: <reason>`. Quota exits use `void: quota`; harness refusals and incomplete work directories use `harness_fail`. Historical rows remain readable, including retractions.

The executor opens a run before execution and appends its first close under the same run ID. Readers collapse these lifecycle rows to one run. Metrics are reported values or null. `auto_grade` can close an interrupted run and harvest remote executor metrics from the existing job log; a second close is a no-op.

Drivers record each shipped unit explicitly:

```sh
tools/delegate-log --model gemini-4-neon-high --source session --session agy-example \
  --task 'example result' --verdict pass --asked 'the requested result' \
  --did 'the completed work' --shipped 'REPORT.md' --run-id example-result-1
```

Use one stable `--run-id` per unit to retry a wrap-up safely. A lane driver session (agy-<lane>, claude-<lane>) calls `delegate-log` itself when it ships a unit; it is a plain command on PATH, not a Claude Code hook, so agy drivers can call it too.

`python3 leaderboard/score_canary.py --owed` is read-only. It includes every ungraded run older than 24 hours and retains the hourly canary's existing FAIL rules. `daily.sh` calls this same command with `--alert`; direct inspection never alerts unless explicitly requested.

`python3 harness/tools/score_migrate.py --dry-run` prints translations and per-model raw row counts for configured ledgers, run-linked ledgers and the installed scorer's evaluations. `--write` creates sibling `.migrated.jsonl` files exclusively. It preserves row IDs, supersessions and old verdicts in `legacy_grade`/`legacy_outcome`; it never overwrites the inputs. Model run lifecycle rows and mirrored grades may repeat, so raw migration counts are not ranking totals.

Ricardo's own 2026-11-26 rank is explicit `OWNER_RANK` metadata: Neon and Opus 5.5 tied #1. It appears in generated roles and snapshot prose separately from the measured everyday routing order.
