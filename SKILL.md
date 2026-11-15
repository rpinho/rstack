---
name: rstack
description: The map of everything that runs in your agent setup, and the entry point for changing any of it. Use at the start of any task that touches guards, orchestration, outbound messages, the research harness, publishing, memory, scheduled jobs or session mechanics; and whenever you are about to add a rule, a guard, a job or a memory, to put it in the right layer with something that enforces it. Also use to answer "what enforces this?" or "where does this live?".
---

# rstack

A running agent setup is layers of machinery. The failure mode is not ignorance, it is working one
layer below or above the one that owns the problem: adding a memory when the fix is a hook, editing
an installed copy when the source is a repository, writing a rule in prose when the same sentence
could be a lint. This is how you find the right layer first.

It is three parts, and one habit:

- **`harness/`**: bounded agents on open research problems, with frozen tests, sealed selection,
  reviewers, a yield check and a baseline you can run.
- **`kb/`**: a file-based knowledge base an agent maintains: worktree per session, then land.
- **this skill**: the map, the principles, and two scripts that refuse to let the map go stale.

## Use it in four steps

1. **Restate the goal in one sentence**, in the owner's terms. "Stop outgoing mail leaking
   infrastructure details" is a goal. "Add an ops lint" is already an answer, and usually to the
   wrong layer.
2. **Find the layer.** If two fit, the owning layer is the one that can REFUSE the bad outcome, not
   the one that describes it.
3. **Run that layer's playbook.** `layers.json` carries the text. Each playbook names the mechanism
   that already exists, so you extend it instead of building a second one beside it.
4. **Report with links**: what changed, the commit, and the test that proves it. A change with no
   test is a claim.

Then, before you finish:

```sh
python3 rstack/coverage.py --config layers.json
```

It FAILS if what you just added is not in the map. That is the point. A new guard, skill, job or
rule that nothing maps is invisible by tomorrow.

## Getting your own map

The manifest shipped here is an **example, with invented data** under `rstack/example/`. The real
one is private, and so is yours: a manifest names your jobs, your notes and your rules, which is
not a list to publish. Copy it and point `sources` at your own paths:

```sh
cp rstack/layers.example.json layers.json      # then edit `sources`, `layers`, `rules`
python3 rstack/inventory.py --config layers.json           # what exists, names only
python3 rstack/coverage.py  --config layers.json           # mapped? enforced? FAILs if not
python3 rstack/coverage.py  --config layers.json --unmapped   # just what needs a rule
python3 rstack/coverage.py  --config layers.json --top 10      # the prose-to-checks queue
```

As shipped, `coverage.py` exits 1 with exactly one failure: an example guard no rule claims. That
is the tool working, and it is the first thing you will see on your own setup too.

`inventory.py` reads disk and has no opinions. `coverage.py` has all of them. Keeping those apart is
deliberate, and it is the same reason [the producer never grades itself](rstack/principles/the-producer-never-grades-itself.md):
a map written by the same pass that grades it cannot be checked.

## What coverage refuses to let you do

1. **Leave an item unmapped.** Add a rule, or an exclusion with a written reason. "Not ours" is a
   reason; "misc" is not.
2. **Write a catch-all.** A rule needs 3 literal characters in its `match` or a 4-character keyword
   in `any_of`. A rule that matches everything maps nothing.
3. **Keep a stale rule.** A rule matching no item fails. This is the check that catches drift.
4. **Point at a missing enforcer.** If the manifest says a rule is enforced by a path, the path must
   exist. Claiming a deleted script is worse than admitting the rule is prose.

Keyword rules match an item's **name and description only, never its whole body**. Matching bodies
made every keyword rule match nearly everything, which turns rule order into the entire map: a
catch-all by the back door.

## The principles

One file each in [`rstack/principles/`](rstack/principles/). Each states the rule, the evidence
behind it, and the mechanism that refuses a violation, or says plainly there isn't one.

| Principle | Short form |
|---|---|
| [Results, not activity](rstack/principles/results-not-activity.md) | every easy check measures activity instead |
| [The producer never grades itself](rstack/principles/the-producer-never-grades-itself.md) | a search that can see the scorer optimises the scorer |
| [Prior art first, and run it](rstack/principles/prior-art-first.md) | reproduce the published number, don't quote it |
| [Every deletion is reversible](rstack/principles/reversible-deletes.md) | trash, not delete; verify a copy first |
| [Architecture, not prose](rstack/principles/architecture-not-prose.md) | broken twice means build a mechanism |
| [Short asks to the human](rstack/principles/short-asks.md) | a question they can answer, where they read |
| [The goal must not become process](rstack/principles/goal-not-process.md) | gates counted as progress |
| [Close every loop](rstack/principles/close-every-loop.md) | name the consumer before the producer |
| [Reports outlive sessions](rstack/principles/reports-outlive-sessions.md) | the file is the report, the message a pointer |
| [Refresh inputs before acting](rstack/principles/refresh-inputs-before-acting.md) | re-read a snapshot older than its source |
| [Revert first, then reorder](rstack/principles/revert-first-then-reorder.md) | three forward fixes, then go back |
| [Autonomous subsystems refill themselves](rstack/principles/autonomous-subsystems-refill-themselves.md) | one alert when every source is empty |
| [Build a guard only after a real failure](rstack/principles/guards-need-a-real-failure.md) | name the incident, or don't build it |
| [A guard must refuse, not crash](rstack/principles/a-guard-must-refuse-not-crash.md) | a guard that raises is no guard |

The last two are the ones that cost the most to learn. Read them before adding anything.
