# Cheap local regression scorecard

Run the existing toy plus two tiny, finished Kaggle competitions to detect broken
workflows and large spend/time changes. This is a constrained end-to-end check:
one model plan, trusted CPU fits, development scoring, independent selection and a
final local hidden score. It does **not** measure an unconstrained research sweep.
All benchmark code and artifacts live under `bench/`; `harness/` and `selection/`
are imported unchanged. Data provenance, terms, limits and split hashes are in
[SOURCES.md](SOURCES.md).

```sh
# The repository environment supplies pytest/numpy; add the CPU model dependency.
.venv/bin/python -m pip install -r bench/requirements.txt
.venv/bin/python bench/setup_data.py

# Offline smoke test; no data download, CLI login, model calls or API cost.
.venv/bin/python -m pytest bench/ -q
.venv/bin/python bench/run.py --setup v1-default --backend stub --cases toy

# One authorized comparison pass: exactly one Codex invocation per setup.
.venv/bin/python bench/run.py --setup v1-default --backend codex --allow-paid
.venv/bin/python bench/run.py --setup v2-selection --backend codex --allow-paid \
  --compare-to bench/results/v1-default-<UTC timestamp>.json
```

`--setup` is required: v2 is opt-in. Codex requires an explicit `--allow-paid` and
the existing CLI login; no credentials are copied. Only `codex` and `stub` are
supported, with no backend substitution. `--model` defaults to the repository toy's
`gpt-6.2-sol` route. One call is shared across all three cases to bound spend.
There are no automatic paid retries. The durable paid-attempt ledger allows at
most two starts, one per setup, in a runtime root, including failed attempts.
Future independently authorized comparisons need an explicit fresh `--runtime`.
If a model completed but local response parsing failed before **any** case was
evaluated, `--resume-result <failed-result.json>` can recover that same response
without a model request. Use the original `--runtime`, setup and model. Recovery
checks the original freeze/log hashes, preserves backend identity, refuses any
already-scored case and writes a single-use recovery marker. It never restores
the paid-attempt allowance or retries an incomplete model turn.

`bench/data/` is created by setup (or verified/created on first real-case run).
Nothing downloaded is added to git; the largest source CSV is about 5.2 MB.
`bench/.runtime/` retains immutable freezes, plans, raw backend JSONL usage logs,
predictions, ledgers, selector evidence, receipts and process logs. Exclusive locks
refuse duplicate runs/preparation. Each run writes a new
`bench/results/<setup>-<UTC timestamp>.json`, including failure cases. There is no
cleanup command; preserve evidence and send unwanted artifacts to Trash.

## What the setups exercise

The shared prompt asks Codex for the toy sequence and exactly three bounded
recipes per real case: Ridge, ExtraTrees and histogram gradient boosting. It can
choose between two predeclared strengths per family, but cannot supply executable
code. Each recipe gets a development fit (seed 7) and two fresh bootstrap fits
(seeds 101/102) using train plus dev data. Preprocessing is fitted inside each fit;
early stopping and augmentation are disabled. Final predictions average those two
fresh fits, with no refit after selection. The mean-target floor is also available.
This deliberately small planner task does not compare autonomous coding ability.

| Setup | Selection | Extra work |
| --- | --- | --- |
| `v1-default` | Existing `selection_gate.decide`, default v1 lower-bound rule | Two fresh fit scores per candidate; one nominee or floor |
| `v2-selection` | Existing `evaluate_v2`, after `consume_scoring` reserves the hidden budget | Paired unit bootstrap, two actual expanding development backtests, fresh-rerun/trial checks, optimism ledger |

V2 explicitly waives ten measurements down to two for this cheap smoke check.
Fresh seed fits bootstrap the available training rows, so they are distinct actual
fits rather than duplicated score entries. Their variation is conditional on one
small fixed selection panel, not independent dataset replications. Expanding
backtests use disjoint, hash-ordered feature-group blocks, **not real time**.
For MAE the paired unit contribution is negative absolute error; for RMSE it is
negative squared error (the monotone underlying loss). Global gate scores remain
negative MAE/RMSE because the shared gate maximizes. The scorecard displays
positive MAE/RMSE. This two-seed, group-assumption protocol is not evidence of
generalization or proof that either gate improves research results.

The backend uses the existing `agent_executor.command` builder, with a read-only
sandbox, shell/apps/plugins/multi-agent/browser tools disabled, an empty working
directory and a strict output schema. Only case metadata enters the prompt, not
data rows, targets or earlier scores. Usage-log inspection rejects tool events.
After that process exits, trusted local workers emit target-free predictions;
the separate selector alone reads withheld targets. This is process separation
and restricted model tooling, not a separate OS account or remote evaluation
service; the local operator still controls the publicly downloadable data.

Each local worker has one thread, a 180-second CPU limit and a 240-second wall
limit. The selector has 30 CPU seconds/60 wall seconds; the shared model call has
180 wall seconds. Timeout handling ends owned process groups. Even the bounded
failure path stays below the 15-minute CPU limit per case. No GPU is used.

## Scorecard fields and alerts

Every case records status, wall time, number of final local submissions, selected
recipe, development score and final hidden score. `n_submissions` counts one local
frozen prediction file, including a floor fallback; `official_uploads` is zero.
Development scores describe the initial train-only fit, not the final two-fit
ensemble. The toy records exact-match validation and a null hidden score/reason.

The run records raw Codex input/cached-input/output token counts from its
`turn.completed` event and the raw log SHA-256. Cached tokens are a subset of
input tokens, not added a second time. Billed dollars are null with a reason when
the CLI does not provide them; no API-price or subscription-cost estimate is
invented. Per-case tokens/dollars are null with an explicit shared-call allocation
reason. Per-case wall time covers local fitting/selection; total wall time also
includes preparation, verification and shared model latency. Warm data caches and
other Mini jobs affect timing.

`--compare-to` adds flags for breakage and **strictly greater than 2x** token/time
growth. Score differences are displayed without winner or improvement claims.
One run per setup can show that a path executed, failed or became much more
expensive in this observation. It cannot estimate a variance, establish a small
score improvement, rank backends reliably or demonstrate statistical superiority.
Run-to-run noise is real, and a different planner response also confounds a pure
gate comparison. Repeated comparisons require new spend approval and a protocol
that accounts for repeated use of the final holdout.

## Recorded comparison

Observed on 2026-11-04 on the Mini (Apple M4, Python 3.9.6, NumPy 2.0.2,
scikit-learn 1.6.1, Codex CLI 0.164.0), using `gpt-6.1-sol`, low effort. Both
model requests returned the same recipes: small Ridge, medium ExtraTrees and
medium histogram boosting. Two model requests total; **23,961 input+output
tokens**, with no billed-dollar figure returned. Per-case usage cannot be
separated from the shared call.

| Setup | Cases OK | Active wall seconds | Input tokens | Cached input | Output tokens | Billed $ | Breakage / >2x token or time alert |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `v1-default` | 3/3 | 10.414* | 11,851 | 0 | 147 | null (CLI does not report) | None after local recovery* |
| `v2-selection` | 3/3 | 8.894 | 11,857 | 0 | 106 | null (CLI does not report) | None |

| Case (metric) | v1 dev | v1 hidden | v1 local seconds | v2 dev | v2 hidden | v2 local seconds | Local submissions v1/v2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Toy (exact match) | 1.0000 | n/a | 0.242 | 1.0000 | n/a | 0.219 | 1 / 1 |
| Concrete (RMSE) | 13.2005 | 11.6939 | 2.224 | 13.1232 | 11.6901 | 1.571 | 1 / 1 |
| Crab (MAE) | 1.5881 | 1.5534 | 1.192 | 1.5881 | 1.5534 | 1.208 | 1 / 1 |

Every case used under 1.3 CPU seconds in this observation. V1 selected histogram
boosting for Concrete; v2 selected ExtraTrees using its conservative ranking.
Both selected Ridge for Crab. These score deltas are diagnostic observations,
with **no improvement claim**. Timing is noisy and the v1 recovery prevents a
clean latency comparison.

*V1 had two integration failures, both retained: a local CLI configuration rejection
before any model request, then a completed model response whose CLI diagnostic
messages were misclassified as tool calls by the log parser. The invalid config
override and parser were fixed. The exact completed response was recovered with
**zero additional model requests**, before any case had been scored. V1's 10.414s
sums the original 6.747s execution and 3.666s local recovery; intervening developer
time and the 0.063s configuration preflight are excluded. Original model-only
latency was not separately captured and is null with a reason. Local NumPy/Ridge
floating-point warnings are retained in worker logs; all saved predictions and
scores passed finite-value checks. These incidents limit this first observation
and should remain visible to reviewers.

Successful scorecards:

- [v1-default JSON](results/v1-default-2026-11-04T20-52-44.997118Z.json)
- [v2-selection JSON](results/v2-selection-2026-11-04T20-53-09.946162Z.json)

Retained integration failures:

- [Local configuration rejection, no model request](results/v1-default-2026-11-04T20-48-30.699962Z.json)
- [Parser rejection, response subsequently recovered](results/v1-default-2026-11-04T20-50-02.996297Z.json)
