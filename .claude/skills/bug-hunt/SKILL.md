---
name: bug-hunt
description: Find confirmed bugs in someone's recent research code and make it faster with identical outputs, then report through the outreach rules. Use for a lane that works on other people's code (friends, collaborators, a lab).
---

The goal is something the author would want to fix or merge today: a confirmed bug with a repro and
a patch, or a speedup that gives the same answers. Not a code review, and not a list of style notes.

1. **Target.** Only recent, active code: `rh bughunt target-check LANE OWNER/REPO` must PASS (a
   commit or release within the lane's limit, not archived, not marked unmaintained). A paper alone
   does not make code a target. Someone outside the project must use it too: outside issue,
   PR or fork accounts, stars, or downloads (`--package pypi:NAME`), or it fails as `TARGET_UNUSED`.
   Hunt their latest commit.
2. **Bugs.** Each bug gets a minimal repro that fails on their latest commit, a patch that makes it
   pass, and the effect on a result they published or would publish. Write the claims as
   `claims.json` (file, function, root cause, observed, expected) and run
   `rh bughunt claims-check LANE claims.json`: a claim a referee refuted before is refused unless the
   source changed or it says how it differs. Record what the round covered with
   `rh bughunt coverage LANE record FILE`; one pass finds about half, so a target is not done until a
   gap-fill round finds nothing new. The referee gets the standard prompt from
   `rh bughunt referee-prompt LANE claims.json WORKDIR`, which mixes in planted false claims, and
   writes `verdict.json` (CONFIRMED, CONFIRMED-MINOR, KNOWN, INTENDED, REFUTED, BLOCKED). Run
   `rh bughunt verdicts LANE WORKDIR/verdict.json`: malformed output is run again, never repaired, and
   a referee that confirms a planted claim is rejected whole. The claims file names the hunter
   (`"hunter": {"model", "family"}`, or `--hunter-family`), and a referee from the same maker's
   family is rejected whole too (`REFEREE_SAME_FAMILY`). Report only what it confirmed. A BLOCKED claim is never a bug in an
   email; its one missing fact can be the question the email opens with.
3. **Speedups.** Before starting, read their open pull requests and branches (the target check
   lists any about speed) and, if someone there is already optimizing, ask them first. Profile on a
   representative input (theirs where public) and name the hot spot with numbers. Write the change
   as a patch against their latest commit, describe it in `SPEEDUP.json`, and run
   `rh bughunt speedup-verify LANE DIR` on the compute host. It checks equal outputs (byte-identical
   or within a stated tolerance) and a real margin, and records the benchmark.
4. **Report.** One email per person per day, batched with `rh outreach batch`: draft with
   `--kind code-bug` or `--kind code-speedup`, `--target`, and `--recheck DIR` or `--speedup DIR`;
   lint; read; approve; send; then `sent`. Lint enforces the target check, the verified speedup,
   their own speed work, the contact's address and scrutiny, and the lane's required questions.

The rules and their codes are in docs/outreach.md, "Bug-hunt lane". A finding lint refuses is fixed
or dropped, never argued around.
