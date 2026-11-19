# Prior-art receipts

Start from an existing method when one exists: identify it, reproduce it and only then try to improve it. Promotion requires a nonempty baseline and a structured receipt for GitHub, papers, leaderboards and community captures. Each source must have an honest disposition, query, search date and hits or an explanation that nothing was found. A skipped or blocked required search does not satisfy admission.

A `rh-prior-art` fenced JSON block can live inside `PRIOR_ART.md`; a plain JSON receipt is also accepted. The evidence contract checks its structure and hashes local captures. The generator queries repository metadata, paper indexes and benchmark discovery sources. Community search uses captured metadata supplied under `RH_XCAPTURE_ROOT/x_capture/`; the generator does not use a social-media API or invent a capture when one is missing. Its discovery sources are not an exhaustive survey or the official scoreboard for every competition.

```sh
python3 harness/rh.py prior-art receipt toy PRIOR_ART.md \
  --baseline 'Published method and metric, with source' \
  --query 'problem name baseline'
```

That command uses the network and GitHub CLI. Configure capture storage first. Review sources, dates, competing results and competition data rules yourself. A hash proves which local bytes were referenced; it does not prove a search was complete or a novelty claim correct. No receipt overrides a lane's data restrictions.

`rh lane new` runs the same GitHub, paper and leaderboard searches once on the lane's problem and writes `OVERLAP.json` (query, per-source hits with title, url and date, time) beside the frozen files. A failed source is recorded `unavailable` with its reason; the lane is created either way. `RH_OVERLAP=off` skips it.

Code: [idea_policy.py](../harness/idea_policy.py), [prior_art_receipt.py](../harness/tools/prior_art_receipt.py). Tests: [test_prior_art_shared.py](../harness/tests/test_prior_art_shared.py).

## A baseline you can run

Finding prior art and reading it is not the same as being able to produce its number. Three
failures here came from the gap: planets reported four candidates of which three were already in
public community tables; c5 spent about 38 rounds in a family after the KB had named a better one;
and a quoted baseline rots silently when a dependency changes under it.

`harness/tools/baseline.py` registers a published number as a command that reproduces it:

```sh
baseline.py --lane LANE add --name NAME --source DOI --published 1.8216 \
    --cmd "python3 reproduce.py" --metric bound --lower-is-better
baseline.py --lane LANE run --name NAME      # the number, reproduced today
baseline.py --lane LANE check                # every baseline; non-zero on drift
baseline.py --lane LANE list
```

The published number can come from a snapshot's own receipt instead of being typed, which is the
same rule one level up: a hand-typed figure is exactly what this replaces.

```sh
baseline.py --lane LANE add --name NAME --source "the table" \
    --published-from snapshot.json:candidates.0.period --cmd "..." --metric days
```

The file is hashed when the baseline is registered. If it later changes, `run` and `check` report
`SOURCE ... changed: published was X, now Y` and exit non-zero rather than quietly comparing
against the new number, because moving the goalposts inside a check is how a comparison stops
meaning anything. JSON and JSONL both work; in a JSONL file the last line that parses is used.

`add` refuses to record anything that does not reproduce, and that refusal is the point: a lane
cannot write down a baseline it has not run. A result that comes out better than the published
number still counts as reproducing the method, with `--higher-is-better` or `--lower-is-better`
saying which direction that is. `check` is what makes it a tested tool rather than a cached
number: when a baseline stops reproducing, the lane is told, instead of going on comparing
against a figure nothing on the machine can still produce.

Rows land in `lanes/<lane>/BASELINES.jsonl`. The number is the last one the command prints, or the
value of `--json-key` in the last JSON line, so progress output is harmless.

## Public inputs a worker may not download

A worker with network access is a worker that can exfiltrate and can be fed anything, so lanes
forbid downloads. The cost showed up on 2026-11-06: the friends kill test returned BLOCKED twice
in one day with "exact public XTW-n308 input unavailable locally; downloading is prohibited. No
solver ran." The input is public and free, and nothing in the harness was responsible for putting
it on disk.

`harness/tools/inputs.py` splits the step that reaches the network from the step that uses the
file, the same way the X policy does:

```sh
inputs.py --lane LANE add  --name XTW-n308 --url https://.../X-n308-k13.vrp \
    --sha256 <expected> --source CVRPLIB      # staged once, by someone with network
inputs.py --lane LANE path --name XTW-n308     # what a worker calls; no network, ever
inputs.py --lane LANE check                    # re-hash everything; non-zero if any changed
inputs.py --lane LANE list
```

`--sha256` is the pin. Without it the file is still staged and its hash recorded and printed, but
the row is marked unpinned, because nothing verified it is the file the source published. A
mismatch keeps nothing: the file is removed rather than left looking staged. `check` re-hashes
against what was recorded, which is what protects a comparison made weeks apart — an input that
changed under a lane invalidates every round that used it, silently.

http(s) only, no auth, a redirect off http is refused, there is a size cap, and a name is a plain
filename fragment so it cannot escape the lane's own `inputs/` directory.
