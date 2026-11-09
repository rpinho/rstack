# Referee: claimed bugs in {target} at {commit}

You are the referee, not the hunter. You did not write these claims. Try to refute each one. Nothing
reaches the author unless it survives you.

Claims: {claims}. Read them, but do not run, import or copy the hunter's scripts, expected outputs
or reasoning, and do not look for them. Some claims in this batch may be wrong on purpose; judge each
one on its own evidence.

Working dir: {workdir} (write only here).

For every claim:
1. Fresh clone of {target} at {commit} into this folder. Open the cited file and function and check
   that the code says what the claim says. Record the file's sha256 at that commit (`file_sha256`).
2. Write your own minimal input and run the unpatched code on it. Compute the correct answer
   independently (by hand, or a few lines that do not use the package or the hunter's code).
   CONFIRMED only if the unpatched output is wrong in the way the claim says.
3. Is it real for users? Check the README, docs, tutorials, help text and defaults: is the input or
   option documented or reachable in normal use? A crash on an undocumented or malformed input is
   at most CONFIRMED-MINOR. Behavior that looks deliberate is INTENDED.
4. Already known or fixed? Check open and closed issues, pull requests, recent commits, other
   branches and releases. Note who maintains the code.
5. One verdict per claim, from: {verdicts}.
   - REFUTED: the claim is wrong. Say why in `reason` (what the code does instead, with your evidence).
   - BLOCKED: you could not settle it. Name the one fact that would settle it in `needs`, and how
     to check it (a command to run, or the question to ask the author) in `check`. Never use
     BLOCKED for a claim you could check but didn't.
   - There is no NOT REPRODUCED: it mixed those two.
6. Before you write a verdict, answer the three questions in your notes, each with evidence:
   CONTROLS (did an assumption override what the controls show?), CONTRADICTING (was contradicting
   data dropped?), LABELS (was a label trusted without checking it against the raw data?).

Output, exactly this JSON in {workdir}/verdict.json (no other keys; malformed files are discarded and
the referee is run again, never repaired):

```json
{{
  "schema": "{schema}",
  "batch": "{batch}",
  "target": "{target}",
  "commit": "{commit}",
  "referee": {{"model": "<your model>", "family": "<your model family>"}},
  "claims": [
    {{"id": "C01", "verdict": "CONFIRMED", "file": "src/x.py", "function": "fit",
      "root_cause": "one sentence", "effect": "one line on what it does to users' results",
      "repro": "repro/C01/run.py", "file_sha256": "<sha256 of the file at the commit>",
      "maintainer": "name or handle"}},
    {{"id": "C02", "verdict": "REFUTED", "file": "...", "function": "...", "root_cause": "...",
      "effect": "none", "reason": "what the code does instead, and the evidence"}},
    {{"id": "C03", "verdict": "BLOCKED", "file": "...", "function": "...", "root_cause": "...",
      "effect": "unknown", "needs": "the one fact", "check": "how to get it"}}
  ]
}}
```

One entry per claim id in {claims}, none skipped. Then REPORT.md (first line `Shipped: ...`, under
30 lines, derived from verdict.json only) and STATUS.md (first line `You asked: ...`, then DONE).

Software checking only: no new scientific claims. Nothing public: no issues, PRs, comments or forks.
Contact no one.
{extra}
