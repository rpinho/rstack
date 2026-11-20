# Sharing lessons between lanes and sessions

Record transferable findings in the root `LESSONS.jsonl` with evidence and an applicability condition. A promoted lesson's `promoted_to` names its enforcing file. Read that file when applying the lesson.

## Record and retrieve

All commands accept `rh --root ROOT ...`. Use real evidence for real lanes.

```sh
rh lessons add --lane sample-a --source retro --tags evaluation,baselines \
  --lesson 'A label-count control exposed a shortcut in this evaluation.' \
  --evidence lanes/sample-a/control.md \
  --applies-when 'Evaluating models on imbalanced labels'
rh lessons list --status active
rh lessons for sample-b --tags evaluation -n 12
rh lessons for sample-b --idea IDEA_ID -n 12
rh lessons supersede OLD_ID --by NEW_ID
rh lessons promote NEW_ID --to tests/test_control.py
```

- Use `add --supersedes OLD_ID ...` to supersede and replace under one local lock.
  Use `--promoted-to PATH` to import an already enforced lesson. Local evidence and
  enforcing files must exist relative to ROOT. HTTP(S) evidence is recorded without
  fetching and may carry a file fragment.
- Write a claim in at most two sentences. Use domain, method and failure-mode tags,
  comma-separated or space-separated. Retrieval uses `lesson_tags`, `tags`, `keywords`
  and `depth_tags` from `INTAKE.toml`. `--idea` accepts an unambiguous ID prefix and
  uses that idea's `data_tags`/`tags`. Relevant rows from other lanes come first.
- Sources are `retro|close|referee|correction|backfill`. Statuses are
  `active|superseded|promoted`. Revisions append under `rh.locked(ROOT)` (`ROOT/.lock`).
  See [`harness/lessons.py`](../harness/lessons.py).

## How it reaches work

- [`harness/sweep.py`](../harness/sweep.py) includes `rh lessons for LANE -n 12` in each
  stage and repair. Receipts name `lesson_ids`, `lessons_command` and `lessons_sha256`
  for material shown. [`harness/lane_setup.py`](../harness/lane_setup.py) gives a new lane
  a `LESSONS_READ.json` exposure receipt.
- At `rh idea close` (also `rh ideas close`), use `--lesson TEXT` and optional
  `--lesson-tags TAG ...`. `lessons_required = true` in `INTAKE.toml` requires `--lesson`
  or `--no-lesson REASON`. Default is false. Lint warns when an enabled lane's latest
  sweep recorded no IDs, or when an active lesson is over 90 days old with no recorded reference.

## Retros are about the field

Run `rh retro LANE [--out PATH]` at challenge end, phase change, final submission or after a
direction-changing referee FAIL. It creates `LANE/RETRO.draft.md` by default and adjacent
`.sources.json` and `.lessons.proposed.jsonl` files. It refuses existing output paths.
Review the field narrative against the evidence packet. Cover attempts, result and selection
summaries, the hard parts of the field, missing data, what would help, open questions and named
credits. Keep raw private text in the packet and agent/ops lessons in the candidate file.

Use [run-retro](../.claude/skills/run-retro/SKILL.md) and the author's voice guidance to finish the narrative. Revise candidate rows into transferable findings and land each with `rh lessons add`. Human reading and an `egress-gate scan` PASS are required before public use.

## Backfill

Use `--source backfill` with actual evidence for a small set of scientific or method claims. Use `--promoted-to PATH` only for a real test, lint or rule that enforces the claim. Historical lane names are accepted. Keep personal notes and credentials out. See the [synthetic example](../examples/lessons-backfill.md).
