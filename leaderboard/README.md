# Model routing and scoring

[`LEADERBOARD.md`](../LEADERBOARD.md) is the sole committed leaderboard data artifact. It retains dated routing snapshots using an explicit export allowlist. Export merges the existing public tables with new dated rows; it never replaces historical scored rows. Bootstrap uses the newest routing snapshot for each role. It contains models, roles, routing order, held-outcome scores, Wilson lower scores and the source snapshot date. A second table retains active 0–4 observation scores grouped only by recognized role, model and date. It includes operational/proxy labels and preserves repeated scores; observations without a recognized public model or role are omitted. Unranked observations have a dash in routing order; unscored models have dashes in score columns. No task text, case identifiers, prompts, costs or personal overrides are exported. `public` includes active scores from the configured local model ledger when that file exists; it validates the ledger before exporting.

The snapshot describes one selected set of local outcomes. Its seeded order is a routing preference and may differ from sorting by measured score. Individual source evidence, task distribution and the original outcome judgments are not shipped, so the scores cannot be independently verified from this snapshot. The 0–4 lists expose only selected recorded labels, not their context. Bootstrap recovers routes, not the private evidence ledger. A new deployment starts its own evidence history.

```sh
export RH_ROLES_FILE="$PWD/.runtime/roles.json"
python3 leaderboard/model-roles.py bootstrap
python3 harness/worker_models.py --role batch --executor codex \
  --log .runtime/example.log --receipt .runtime/selection.json
```

Selection refuses an incompatible executor or excluded model; it never silently skips to a lower-ranked provider. A fixed model needs `--model-override REASON`. Completion receipts retain the actual model and roles-file hash even if routes change mid-job. An exit code stays unscored.

To route an eligible OpenRouter model, register its canonical `provider/model` ID with `cli: openrouter` and include it in the role pool; selection automatically runs Codex with `LAUNCH_PROVIDER=openrouter`. For a matched candidate trial use `tools/launch.sh JOB WORKDIR --role ROLE --explore MODEL` (and `--made-by MODEL` for independent judgment): it requires a listed, eligible candidate and records `source: explore` without an override. The executing shell reads `$HOME/.config/openrouter/key` into `OPENROUTER_API_KEY`; the key never goes into logs, receipts or saved commands. The order is LEADERBOARD.md; never name a model for a judgment role in the task prompt.

As of 2026-11-18, Google models are excluded from every served role, including candidates introduced by new evidence and routes recovered by bootstrap. The owner's reason: "Spending OpenRouter money on Google is a waste". This routing preference cannot be lifted by a high score. Existing Google route metadata, observations and dated ranking rows remain available as history. The Gemini transport remains available for explicit comparisons; it does not make a Google model eligible for a served role.

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

Dry run copies an existing ledger into the scratch directory and writes the new
ledger, roles and page only there. It makes no Git changes and does not fetch or
push. The scratch directory must not already contain scoring outputs. Omit
`--dry-run` for publication. `PYTHON` can select an existing interpreter;
`MODEL_SCORER_REMOTE` and `MODEL_SCORER_BRANCH` default to `origin` and `main`.
The inactive `com.example.model-scorer.plist` template runs at 06:30 local time.
Replace its placeholders, remove unused optional source variables, and configure
Git authentication and executable paths before installing it yourself.

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
