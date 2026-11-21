# The ablation pass

Rule #0 (11-21): rstack's goal is to delete itself. Anything that is not a hard line stays only while
it changes an outcome. The hard lines (money, sign-ins and credentials, sends in the owner's name,
permanent deletes, privacy and IP egress, unsandboxed third-party code) are exempt and are never
switched off here. This page is how the rest earns its place.

## What counts as a gate that changes an outcome

Every entry in `rstack/gates.json` has `added`, `why`, `sunset` and `last_changed_outcome`. Hard lines
are `sunset: false`; everything else is `sunset: true`. A gate changed an outcome when a warning
made the agent change course (`harness_blocks.py mark --gate NAME --outcome heeded --reason TEXT`),
or when a block it caused was rerun, overridden or retracted. `harness_blocks.py sunset --days 14`
lists every `sunset: true` gate older than 14 days with none of those rows in the last 14 days, and how
many warnings it gave. It only reads, and it exits 0.

## On each new model release

Models change what they get wrong, so a gate written for the last one may be dead weight on this one.
For one day of real work:

1. Set `RSTACK_ABLATE=1` in the environment of the sessions and jobs. `_hookfail.run` then allows every
   `sunset: true` hook without running its body, and `harness_blocks.gate` and `warn` allow every
   `sunset: true` check without printing anything. Each skipped check is a row with outcome `ablated`
   in `harness-blocks.jsonl`. Hard lines ignore the variable.
2. Switch off every skill that is not a hard line the same way: move its folder aside to the Trash
   (`/usr/bin/trash`, never rm), and note the names so the next step can put back the ones that mattered.
3. Do the normal work. Do not add anything new that day.

## The next day

Compare the ablation day with the day before, on the same measures the harness already keeps: job
grades, reruns, and harness-blocks (blocks, warnings, harness bugs). Use the `ablated` rows to see what
would have fired. For each gate or skill, ask one question: did the outcome measurably get worse
with it off? Put back only what did. Delete the rest with `git rm` (it stays in git history), remove
its registry entry and its tests, and let `rstack/tools/net-deletion` count the week as a deletion
week. A gate nobody can show an effect for is gone by default.

## Limits

One day is a small sample, so a gate that guards a rare failure can look useless. If a removed gate's
failure comes back, put the gate back with the incident named in `why`
([a guard needs a real failure](../rstack/principles/guards-need-a-real-failure.md)). The weekly
`net-deletion` line is the check that the stack is shrinking, not just being reorganised.
