---
name: paper-innovate
description: Find a new, refereed result on someone's published research (beat or extend their numbers, settle an open question they posed), then report through the outreach rules. Use for a lane that works on other people's papers (friends, collaborators, a lab).
---

Treat their papers like a table of open constants: every number is a candidate to move. Reproducing
their table is homework, not a gift. The point is a result they would want to know.

1. **Board.** One job per person lists every candidate across their recent papers: the number, the
   paper, the data and metric, and why it might move. Rank by the chance it moves and by whether they
   would care.
2. **Raise the bar.** A target counts only if it is an open problem or "future work" item from their
   papers, an unsolved instance on a tracked public benchmark, an invariant nobody has computed, or
   a held-out prediction that beats their method and a trivial control. Reproductions, sensitivity
   checks and optimizer restarts that nudge their own number do not count. Keep several live targets
   per person, each with a written kill line checked early.
3. **Reproduce, then beat.** Same data and metric. Freeze any held-out set before modelling. Run the
   trivial predictor and a simple baseline beside any predictive claim. Exact claims get a verifier
   written apart from the search. A big jump is a warning until a control explains it.
4. **Referee.** A separate job rebuilds each claim from the paper with its own code, tries to break
   it, and ends HOLDS, HOLDS WITH CAVEATS or FAILS, naming the author's strongest objection. Judging
   novelty is a separate, stronger model's call, not the checker's. The objection becomes the next
   round's bar.
5. **Report.** Only refereed results, reviewed once adversarially on the exact final text, read by
   the owner, and sent through `rh outreach` with `--kind paper`: one email per person per day, the
   lane's required questions, the contact's scrutiny level. The author is the judge of whether it is
   useful; record their answer and let it steer their next targets.

Heavy work runs on the compute host, never the controller. Lessons from a round go in the lane's
LESSONS.jsonl through `rh lessons add`.
