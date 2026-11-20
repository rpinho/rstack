---
name: run-retro
description: Draft a field retrospective from a research lane and land transferable lessons at a challenge end, phase change, final submission, or direction-changing referee failure.
---

Run a retro at a challenge's end, a phase change or final submission, and after
any referee FAIL that changed direction. Work locally; do not publish or send.

Run `rh retro LANE` (or `rh --root ROOT retro LANE --out FRESH_PATH`). The default
is `LANE/RETRO.draft.md`. Read its local `.sources.json` packet and review the
`.lessons.proposed.jsonl` candidates. Existing output files are preserved; use a
fresh path for a new draft.

Fill the draft from the challenge repo docs, lane files, measured results,
selection outcomes, verification scopes, prior-art receipts, and substantive
outreach replies. Read only challenge-related X threads under
the configured local X-thread archive; do not import unrelated conversations or private
personal material. Check credit against sources; give real names and links.
Apply the author's configured voice skill before writing in their name; if
one is unavailable, use plain claims, uncertainty, numbers and source links.

Keep these eight field sections:
- what we tried;
- what the results taught us about the problem and the field;
- what's easy and what's hard;
- what data is missing;
- what would make it easier;
- what's still open;
- credits and thanks, by name with links;
- how hard open science with AI is in that field.

Optional, when a complex method held: distill it into its few main steps and add
an ablation table, the baseline, then each step added in turn with its score on
the same split, so the retro says which step carries the gain (CellularAI's
VCC 2026 retro: five steps, Stouffer-z the biggest share). Skip it
when there is no such method.

The public retro is about the field. Explain scientific methods, limits,
negative results, data gaps and unanswered questions. Agent work, leaks and ops
belong in `LESSONS.jsonl`, never in the public narrative. The local source
packet may contain those notes; do not copy it into public output. Separate a
whole-result claim from its finite component and label unsupported claims.

Drafts stay local until the research owner has read the exact text. Before anything
public, `egress-gate scan PATH...` must PASS on the exact proposed artifacts.
The scaffold command does not supply publication approval or publish anything.

Review proposed lessons as candidates, rewrite them into one supported claim
(at most two sentences), and land accepted rows with `rh lessons add --lane
LANE --source retro --tags TAG ... --lesson TEXT --evidence PATH --applies-when
CONDITION`. Never bulk-import the private source packet. Use `rh lessons
supersede OLD --by NEW` for corrections and `rh lessons promote ID --to PATH`
when a test, lint or rule enforces the claim. Read `docs/lessons.md` in the
repository for ranking, receipt and enforcement limits.
