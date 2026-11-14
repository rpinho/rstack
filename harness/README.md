# The research harness

Bounded AI agents on open research problems, with workflow checks against overfitting,
stalled work and unsupported claims. The checks are on the workflow; the science still needs
independent verification, and the record below includes four reports that needed correcting. This is one of the three parts of [rstack](../README.md); the root README says
how they fit together.

I run AI agents on open research problems and then check their work. The harness is the part that
does the checking: it runs the agents, records what they did, and checks the results.

Six bounds the agents found are merged into Terence Tao's public table of constants defined by mathematical extremal problems, six new linear codes went to the maintainer of the codetables.de tables of best known codes on 6 November, and four reports on exoplanet candidates from NASA TESS data are under review at a journal. I had to correct all four of those reports: a re-audit found errors, and some of the signals had already been reported publicly by other people. The most useful results were the negative ones. Two protein design challenges turned on the confidence scores that protein structure prediction models report, and in each the score failed differently. In one it varied between repeat predictions of the same design about as much as it varied between different designs. In the other the designs had to bind a fragment of a mutant protein presented at the cell surface, and the score could not tell that target from the equivalent unmutated one. In a cell biology challenge a local score ranked two candidates in the opposite order to the official scorer.

Nothing here has been refereed by a human expert unless it says so. The section below gives the numbers, the links and what went wrong.

## What it has produced (as of 2026-11-06)

All of it unrefereed unless stated. Reviews were by other models; the only outside checks are replays and checks by other GitHub users, linked from [math-certificates](https://github.com/rpinho/math-certificates). No human expert has refereed any of it. These are agent runs under this harness, directed by one person.

**Mathematics.** Six bounds from this work are merged into Terence Tao's [optimization-constants table](https://github.com/teorth/optimizationproblems), Our bound for the Schur–Siegel–Smyth trace constant, C86 ≤ 1.8117251 ([PR #227](https://github.com/teorth/optimizationproblems/pull/227)), improved the previous bound of 1.8216 by Orloski and Talebizadeh Sardari; Koshta's 1.8084990 has since passed ours on the table. Our bound for the Zhang–Zagier height, C82 < 0.2534449 ([PR #229](https://github.com/teorth/optimizationproblems/pull/229)), builds on Doche and on Épi/BakeLab's 0.25357. Sixteen more pull requests are open, several of them improving the merged values, and one (#300) only records other people's bounds: [the list](https://github.com/teorth/optimizationproblems/pulls?q=is%3Apr+author%3Arpinho). The newest is a candidate upper bound C82 < 0.2519923410 ([PR #330](https://github.com/teorth/optimizationproblems/pull/330)), which an AI referee judged to hold, with caveats; Arhan Canli has independently replayed all four versions of that pull request with his own code. Certificates and checkers are indexed at [math-certificates](https://github.com/rpinho/math-certificates). The search agent never grades its own certificate: a separate exact checker does, and deliberately corrupted certificates have to be rejected (4 for C86, 18 for C68). Public postings on Hexagon: C86 [2610.00425](https://hexagonmath.org/2610.00425), C82 [2610.00426](https://hexagonmath.org/2610.00426), Korenblum's c2 ≥ 0.432 [2610.00399](https://hexagonmath.org/2610.00399), and C44, C86 and C68 at [2610.00694](https://hexagonmath.org/2610.00694), [2610.00695](https://hexagonmath.org/2610.00695) and [2610.00696](https://hexagonmath.org/2610.00696).

**Coding theory.** On 6 November 2026 we sent six linear codes to Markus Grassl, who maintains the [codetables.de](https://www.codetables.de/) tables of best known codes. Each has a minimum distance one above the current lower bound for its length, dimension and field. Writing [n,k,d] for length n, dimension k and minimum distance d, they are [74,12,43], [128,14,79], [129,14,80], [130,14,81] and [130,16,77] over the five-element field GF(5), and [99,12,67] over GF(9). The [129,14,80] code is a puncturing of the [130,14,81] code. They come from Constructions X and XX applied to cyclic codes. Each code's rank and minimum distance were checked exactly by a second AI model (GPT-6 Astra) using a checker it wrote without reading the search code. It used full enumeration for the first two and a provably complete information-set search for the other four. The codes are submitted but not yet accepted, and the tables do not list them. No earlier report was found, but that search cannot prove absence.

**Exoplanets.** Four reports based on NASA TESS data are under review at Research Notes of the American Astronomical Society (RNAAS). Three concern a single candidate each: TOI-6000 c (1.15 R⊕, 4.21 d), a third candidate at TOI-4342 (18.9 d, first publicly reported by Eumemic), and TIC 144439305 (1.2 R⊕, 0.94 d). The fourth covers four signals: one at TOI-4405, one at TIC 101653309 and two at TIC 262843927. TOI-6000 c was also in Eumemic's public table first, and Kunimoto et al. (2025) had already published the 14.52-day TIC 262843927 signal; the corrections credit both. Pipeline: [planet-hunt](https://github.com/rpinho/planet-hunt). All four were corrected after the numbers were re-audited, and the corrected versions are published on Zenodo: TOI-6000 c ([10.5281/zenodo.23895484](https://doi.org/10.5281/zenodo.23895484)), the TOI-4342 candidate ([10.5281/zenodo.23824790](https://doi.org/10.5281/zenodo.23824790)), TIC 144439305 ([10.5281/zenodo.23836131](https://doi.org/10.5281/zenodo.23836131)) and the three-target note ([10.5281/zenodo.23895440](https://doi.org/10.5281/zenodo.23895440)). RNAAS has made no editorial decision on any of the four reports, so all four remain unrefereed and under review. The pipeline's own [retro](https://github.com/rpinho/planet-hunt/blob/main/RETRO.md) says what changed and why. The lesson from this work: cross-match the ExoFOP TOI and CTOI tables and the public community lists before calling anything new, and test the pipeline by injecting simulated transits and measuring how often it recovers them.

**Arc Virtual Cell Challenge 2026.** [virtual-cell-challenge](https://github.com/rpinho/virtual-cell-challenge): best official validation score 0.1644, rank about 463 of about 1,580 (2026-10-21). The final entry went in on 2026-10-23 and stood as the final when submissions closed on 2026-11-05; its score is pending. The useful result is a negative one. A local proxy score ranked two candidates in the opposite order to the official scorer, so the official metric is the only judge. A split-half noise ceiling (method credited to @zymobyte012) puts two halves of the real data at cosine 0.65 while the predictions reach 0.08, about 12% of that half-split agreement and about 10% of the estimated full-data ceiling.

**Virtual Embryo.** [virtual-embryo-community](https://github.com/rpinho/virtual-embryo-community): the reusable parts of the Virtual Embryo work, released publicly on synthetic data with 102 tests. It has a checker that flags public mouse-atlas samples whose embryo ages fall outside the stage windows the challenge allows for outside data, and a tutorial on picking which of many candidate models to submit without fooling yourself with a lucky validation score. Challenge results stay unpublished under the competition's terms, so no score is claimed here.

**Adaptyv protein design.** [adaptyv-challenges](https://github.com/rpinho/adaptyv-challenges): in challenge 4 (TfR1 binder), 342 designs were scored with AlphaFold2-multimer, five models each, against the TfR1 homodimer construct. The predicted confidence in the protein interface (the iPTM score) varied across the five predictions of one design about as much as it varied between different designs, so designs were filtered for agreement across all five rather than ranked by peak iPTM. In challenge 5 the designs had to bind a fragment of the mutant KRAS G12D protein presented by an MHC molecule at the cell surface, and neither AlphaFold2-multimer nor Boltz-2 confidence could separate that target from the unmutated one.

## What this is

A **lane** is one research problem with its own queue, rules, schedule and results. Lane state stays local. This repository contains code, synthetic examples and a dated snapshot of model rankings and routing choices.

Tools for running AI agents on open research problems and competitions with checks against overfitting, stalled work and unapproved outreach. The research harness records ideas and evidence, checks lane rules, watches delivery cadence, and manages bounded workers. The [model leaderboard](../LEADERBOARD.md) is one input to model routing.

Agents: start with [AGENTS.md](../AGENTS.md), the single source of agent instructions. Agents run the field's standard method before their own, and every claim starts with NEW: yes or NEW: no. See [normal first](../docs/normal-first.md).

## Quickstart

Start in a clone or extracted copy of this repository. Python 3.9 or later runs
the harness using the standard library; the selection gate also needs NumPy.
Run the idempotent bootstrap to create a virtual environment and install dependencies.
The paid worker example needs zsh and an authenticated executor CLI on PATH.
The toy preview uses neither an executor nor the network.

```sh
scripts/bootstrap.sh
. .venv/bin/activate
python3 examples/toy_demo.py --root .runtime/toy
python3 harness/rh.py --root .runtime/toy ideas list toy
python3 harness/rh.py --root .runtime/toy sweep toy --dry-run
python3 -m pytest -q
```

For a user-owned problem, follow [new-lane](../.claude/skills/new-lane/SKILL.md). `rh --root .runtime lane new NAME --help` lists the facts you have to supply, and the same command without `--help` creates the frozen v2 declarations; then lint and preview using the commands in [AGENTS.md](../AGENTS.md). New lanes keep real workers disabled and have at most 24 hours of setup lint grace; no external reading or results are claimed.

The demo creates an invented integer-sequence lane and previews search, read and kill-test instructions. Choose a fresh root on subsequent runs. A real sweep without `--dry-run` starts configured workers and can use remote sources. Do not enable workers until you have supplied your own access controls and lane policy.

To recover the dated model routes into a local file:

```sh
export RH_ROLES_FILE="$PWD/.runtime/roles.json"
python3 leaderboard/model-roles.py bootstrap --output "$RH_ROLES_FILE"
```

See [configuration](../docs/configuration.md) before connecting an executor, remote pod, contact file or notification command.

## Run one real toy worker

Install [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) or
[Claude Code](https://code.claude.com/docs/en/setup) separately. Each provider
requires an account with model access. Authenticate **in the same HOME and
environment that will run the worker**: `codex login` for Codex, or `claude auth login`
for Claude Code. Check with `codex login status` or `claude auth status`.
[Codex authentication](https://learn.chatgpt.com/docs/auth) also supports an API key
piped to `codex login --with-api-key`; keep credentials outside this repository.
For automated Claude authentication, supply your own `CLAUDE_CODE_OAUTH_TOKEN`
(from `claude setup-token`) or `ANTHROPIC_API_KEY` through your secret manager.
Do not copy credentials from another HOME as an installation shortcut.

After the quickstart, choose either command, or run both with separate roots:

```sh
AGENT_BACKEND=codex python3 examples/toy_worker.py --root .runtime/toy-codex
AGENT_BACKEND=claude python3 examples/toy_worker.py --root .runtime/toy-claude
```

Each command starts exactly one worker through `tools/launch.sh`, asks it to write
an integer sequence and search/read/kill reports, and verifies the exact result.
It writes `receipts/toy.json`, a hash-bound `receipts/selection.json`, model selection
and outcome events in `jobs/toy-worker.log`, the provider output in
`jobs/toy-worker.last.md`, and a finished registry record under the chosen root.
A fresh root is mandatory. The toy uses `gpt-6.1-sol` or `claude-haiku-5-5`, low
effort and a three-minute timeout. Claude has a $1 per-run CLI budget and no
launcher retries; actual pricing and account access depend on the provider.
Codex has no dollar cap in this launcher. The toy claims no statistical holdout.

For general jobs set `AGENT_BACKEND=codex|claude` (default `codex`) and supply
compatible routes through `RH_ROLES_FILE`. There is no automatic backend/model
substitution. Claude uses `acceptEdits`, preapproved file tools and an empty MCP
configuration; it has no OS sandbox supplied by this runner. Codex uses
`workspace-write`. Both inherit caller authentication. A clean HOME excludes
personal context but requires its own login. If that login is unavailable, a
fresh clone outside personal directories with an existing login is a useful
integration test, but does not prove authentication in an empty HOME.

## Enforced contracts

- [Sealed selection](../docs/sealed-selection.md): a [selection package](../selection/README.md) computes conservative decisions and hashes artifacts; promotion freezes a test/pass line. The opt-in [v2 harness policy](docs/selection.md) adds frozen declarations, trial accounting and replayed scoring evidence. The [overfitting map](../docs/overfitting.md) distinguishes defaults, optional checks and missing controls.
- [Idea intake, sweeps and kill-tests](../docs/idea-intake.md): append-only idea events, source screening, required rule files, bounded workers and result receipts.
- [Lane cadence, lint and alerts](../docs/lane-cadence.md): delivery checks remain active when workers are disabled; lane-health alerts enter an agent queue.
- [Pods and harvesting](../docs/pods.md): ownership, capacity receipts, atomic claims, deadlines and verified copies before supported shutdown paths.
- [Prior-art receipts](../docs/prior-art.md): promotion requires structured source dispositions, a baseline and captured evidence.
- [Verification levels L0–L3](../docs/verification.md): scoped whole-result and finite-component claims, hashed checker or Lean receipts, and opt-in close/lint checks.
- [Outreach](../docs/outreach.md): draft, lint, approve exact bytes, then record a separate send. The harness has no send function. Lint gates a result email on an independent re-check of every claim it reports (`RECHECK_MISSING`, `RECHECK_FAILED`, `RECHECK_DROPPED`), on pod-touched evidence having been re-run after a configured host incident (`POD_EVIDENCE_STALE`), and on the two-language rule when the recipient's contact language is not English.
- [Lane yield](../docs/lane-yield.md): each lane logs every run to its own `RESULTS.jsonl` through `log-result`. `BURNING` fails a lane that spends job-hours with nothing new, `DRY_ROUNDS` a lane that logs run after run with nothing new, `RUBBER_STAMP` a referee that passes almost everything, and `UNSURFACED` a `HOLDS` claim that reached neither an audit ledger nor a message that went out. `DRY_STREAK` fails three rounds in a row that produced nothing selective, read from a per-round ledger every paid round writes; it sends the lane to a different method family rather than stopping it, and refuses to reopen a family it has closed without new evidence.
- [One source for the installed copy](../docs/harness-sync.md): `harness-sync` installs only committed `main`, reports drift as MISSING, BEHIND, EDITED, STRAY or REMOVED, and refuses to install while a harness job runs. The installed copy is never edited in place, and the rules every lane carries come from [LANE_RULES_COMMON.md](LANE_RULES_COMMON.md) through `lane-rules-sync`.
- [Repo freshness](../docs/repo-freshness.md): README numbers are rendered from their sources (`readme-blocks`), `log-result` refuses a public result until the lane's README shows it (or `--private`), and a nightly `repo-freshness` lists every public repo as pushed or published, failing on any that is neither and on each kind's drift.

Three scheduled scripts enforce these rules: a lane that goes quiet gets a [resume prompt](../docs/lane-nudge.md), a lane going in circles fails [lane yield](../docs/lane-yield.md), and agents wake the conductor only through the [conductor inbox](../docs/conductor-inbox.md).

The [science rules](../tools/RULES.md) are a job-spec template. They distinguish requirements enforced by code from responsibilities of the experiment owner. The [commands and modules](#commands-and-modules) lists commands and the [migration notes](MIGRATION.md) explain changes from a machine-local installation.

## Limits

This is a Unix-oriented local harness, using file locks and processes. Reversible disposal defaults to macOS Trash; other systems need a compatible configured command. It is not an access-control sandbox, a competition platform or an independent judge of scientific truth. Holdout declarations, reviewer identities, human approval quotes and reported results are assertions with receipts; the harness cannot prove the person, model or experiment was honest. An exact verifier and a separate selection environment remain necessary.

The model snapshot reflects selected tasks and small samples. The initial ordering of models for selection reflects judgment, not measured superiority. An executor exit code is not a quality score. Model availability can change; a route entry does not prove access to a provider. See the [ranking method](../leaderboard/README.md).

Optional hooks must be installed in the tool environment that performs the action. The capacity hook starts in audit mode. The deadline hook only recognizes command text; it cannot prove that a remote termination command will succeed. A stopped controller, missing scheduler, unavailable provider or missing credentials can still stall work. There is no installed watchdog, cloud account configuration or notification service in this repository.

## Credit and license

The separation of adaptive work from final evaluation is informed by [Dwork and coauthors on holdout reuse](https://arxiv.org/abs/1506.02629) and [Blum and Hardt on reliable competition leaderboards](https://arxiv.org/abs/1502.04585). The search/evaluate/retain pattern has related work in [AlphaEvolve](https://arxiv.org/abs/2506.13131). This code implements local workflow checks, not those papers' algorithms or guarantees. [Sources and attribution](../docs/credits.md) describe the relationship.

[MIT license](../LICENSE).

## Shared lessons and field retros

See [sharing lessons](../docs/lessons.md) for `rh lessons`, automatic sweep/new-lane
reads, opt-in close requirements, and the local-only `rh retro` workflow.

## Commands and modules

Run `python3 harness/rh.py --help` from the repository root. The runtime uses Python 3.9+ and standard-library modules. State is local, append-only where possible, and excluded from Git.

```sh
python3 harness/rh.py --root ROOT ideas add LANE --source-type internal --claim 'testable mechanism'
python3 harness/rh.py --root ROOT ideas list LANE
python3 harness/rh.py --root ROOT sweep LANE --dry-run
python3 harness/rh.py --root ROOT lint --all --json
python3 harness/rh.py --root ROOT lanes cadence --json
python3 harness/rh.py --root ROOT lanes check
```

The last command writes monitor state and alerts. A real sweep launches workers; intake defaults to dry-run but `intake LANE --live` fetches configured sources and writes receipts. Consult command help before using mutation commands.

| Module | Responsibility |
|---|---|
| `rh.py` | Idea CLI, metadata intake, source screening, append-only revisions and lint. |
| `idea_policy.py` | Frozen bars, config/result hashes, source receipts and explicit close contracts. |
| `verification.py` | [Verification levels L0–L3](../docs/verification.md), whole/finite evidence validation and optional publication checks. |
| `sweep.py` | Policy compiler, search/read/kill stages, resource guards and carry-over. |
| `cadence.py`, `lane_alerts.py` | Delivery evidence and durable alerts to agents. |
| `pods.py`, `pod/runner.py` | Registry, monitoring, ownership, capacity, claims, reaping and local pod runner. |
| `harvest.py`, `harvest_reader.py` | Verified incremental snapshots and bounded remote reads. |
| `outreach.py` | Private draft ledger, lint, exact-byte approval and follow-up tracking. |
| `settings.py`, `storage.py` | Explicit configuration and reversible Trash disposal. |
| `worker_models.py` | Role route selection and outcome receipts; no inference calls. |
| `intake_all.py` | Discover configured lane directories and continue after an intake failure. |
| `cs.py` | Optional unofficial local daemon client. See [CLAUDE_SCIENCE.md](CLAUDE_SCIENCE.md). |
| `tools/prior_art_receipt.py` | Generate source receipts using explicit capture storage. |

The [idea intake](../docs/idea-intake.md), [pod](../docs/pods.md) and [outreach](../docs/outreach.md) pages describe enforcement boundaries. Use the [toy example](../examples/toy_demo.py) for a safe local preview.
