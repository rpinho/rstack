# Rule #0: rstack's goal is to delete itself

**The rule.** Everything in rstack that is not a hard line stays only while it changes an outcome. The
hard lines (money, sign-ins and credentials, sends in the owner's name, permanent deletes, privacy and
IP egress, unsandboxed third-party code) are exempt. Rule #1 ([the harness never gets in the way](harness-never-in-the-way.md))
says what a check may do; this rule says whether it should exist at all.

**The evidence (11-19 to 11-21).** Seven fail-open hooks were deleted in one pass. In two days the
results-report guard warned 83 times and the results-brief guard 9 times (once on a one-line brief), and
nothing changed; the other five fired 0 times and still started a python process on every tool call. A
warning nobody heeds is cost with no result. The gate-pipe guard stayed: it answers a real incident (a
failing check piped into tail looked green), and its warnings that day were heeded. That is the test.

**Enforced by.** Every entry in `rstack/gates.json` carries `added`, `why` and `sunset`;
`harness_blocks.py sunset` lists the ones that changed no outcome in 14 days; `rstack/tools/net-deletion`
sends a weekly line saying whether the stack shrank; and [the ablation pass](../../docs/ablation.md) switches
every sunset gate off for a day on each new model release.
