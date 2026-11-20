---
name: orchestrator
description: Run one long session that talks to the owner and delegates bounded work to cheaper workers, waits on events instead of polling, and saves state before compacting. Use when planning to hand work to another model or agent CLI, when a long session nears its context limit, or when setting up watchers for background jobs.
---

# Orchestrator: running a long session that delegates

## Delegate bounded work

- Keep owner-facing decisions, writing, signed-in browser actions and final review in the
  main session. Delegate self-contained, checkable work above roughly 20 tool turns.
- Use the cheapest capable worker or a second vendor's CLI. Reserve consultation-grade
  models for second opinions, reviews and plans. Check file ownership before launch.
- Use the [job spec template](references/job-spec-template.md). Name the job, isolated
  output directory, inputs, allowed writes, budget, deadline, checkpoints and acceptance
  test. Start non-interactive workers with stdin from `/dev/null`. The runner owns retries
  and resumptions.
- Give workers zero sends or publication authority. Keep credentials at their configured
  source and minimize private extracts. Escalate money, sign-ins, sends in the owner's name,
  irreversible actions, privacy or egress, and unsandboxed third-party code. Keep decisions
  awaiting the owner in the state file.
- Use an independent referee for science claims, with final selection targets outside the
  producer's reach. Follow the [science job rules](../../../tools/RULES.md).
- The [launcher](../../../tools/launch.sh) limits the job, and records the first lines of
  `STATUS.md` and `REPORT.md`. Its [spec word counter](../../../harness/tools/spec_words.py)
  applies to the job-specific text. Check the unattended-routing override's actual expiry
  before a batch. Respect permission denials and safety stops when routing work.

## Wait on completion events

Run multi-hour builds as bounded background shell jobs. Let the agent exit and resume
from the result when ready. Use [event-watch](../../../rstack/tools/event-watch) or a
scheduled script to wake an agent on a result marker, a stale log, a matching log pattern,
a process exit or the deadline. Keep the terminal `quiet` result so silence can be checked.

Before relaunch, count jobs with `pgrep -f JOBNAME | wc -l`. Process checks must keep
other sessions' command lines out of output. On completion, verify the harvest and inspect
ownership and parentage before stopping any leftover worker.

## Save before compaction

Keep the full context window and reduce wakes. See [cost math](references/cost-math.md).

1. Set up [fleet-context-watch](../../../rstack/tools/fleet-context-watch) with the session
   threshold and skip list. The reference configuration checks every 15 minutes and requests
   a state save at 500k tokens.
2. Write enough durable state for a fresh context and reply `SAVED <path>`.
3. The watcher uses any `SAVED` reply after the request. After two quiet minutes, it types
   `/compact Full saved state is in <path>` into the terminal. It re-asks after two hours and
   resets below 300k. Inter-session messages cannot run the compaction command.

Report the shipped result, evidence and limitations from `REPORT.md`. Surface new owner
decisions once and preserve the durable queue across compaction.
