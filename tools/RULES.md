# Science job rules template

Set the work directory, time limit, compute allowance, permitted sources, allowed writes, required artifacts and exact acceptance checks in each job spec.

Begin with prior art: inspect the official scoreboard, public code and open changes, current papers and relevant community evidence. Write `PRIOR_ART.md` with links, dates, the best known baseline and an honest reproduction result. Recheck novelty before making a public claim. Credit methods you build on.

Freeze the experiment configuration, comparison and pass line before examining results. Keep final selection targets inaccessible to producing agents. An exact certificate task should use a separately written verifier and explain why no statistical holdout applies. Report failed experiments and uncertainty.

Run only within the permitted root and compute budget. Use bounded workers, checkpoints in `STATUS.md`, a deadline, process cleanup and a verified result harvest. No worker should survive the authorized job interval. Alerts should go to the owning agent; escalate to a person only when their action is required.

Before relaunching, count this job's processes with `pgrep -f JOBNAME | wc -l` only; never print process command lines (other sessions' commands would land in this log).

Do not publish, push, post, upload or contact anyone without task authorization. Outreach requires draft review, lint and exact-byte approval. Data-use restrictions and source licenses apply even to public downloads. Never include secrets, personal state or private challenge data in publishable artifacts.

Whenever you referee or review a result, yours or anyone's, answer these three in the verdict, each with the file, command, count or line you checked. An unsupported "no" fails the check.

- `CONTROLS:` did an assumption override what the controls show?
- `CONTRADICTING:` was data that contradicts the conclusion dropped or ignored?
- `LABELS:` was a label or annotation trusted without checking it against the raw data?

Deliver `REPORT.md` with the result and verification status, reproduction commands, sources, limitations and next steps. Keep results small enough to review. Move superseded user files to reversible storage rather than destroying them.

These rules are job instructions. The harness enforces selected receipt, resource and workflow contracts; it does not provide OS isolation, authenticate scientific claims or authorize publication. See the docs for the boundary of each check.
