---
name: orchestrator
description: Run one long session that talks to the owner and delegates bounded work to cheaper workers, waits on events instead of polling, and saves state before compacting. Use when planning to hand work to another model or agent CLI, when a long session nears its context limit, or when setting up watchers for background jobs.
---

# Orchestrator: running a long session that delegates

Principles, not a procedure. I prefer the model deciding over a rigid harness: the model is
usually smarter than the harness. The numbers below are from one fleet of research sessions;
[references/cost-math.md](references/cost-math.md) has the arithmetic, and
[references/job-spec-template.md](references/job-spec-template.md) a worker spec to start from.

## Delegate cheaply

- The main session talks to the owner, decides, and reads short results. Bounded, checkable, big
  work (more than ~20 tool turns) goes to a worker. Anything needing the main conversation's
  context stays in it.
- Workers run on the cheapest model that can do the job. **A consultation-grade model is for
  second opinions, reviews and plans only. Never a builder, never a long-running worker.** One
  such builder spent ~9 hours mostly waiting on builds and burned most of a weekly limit.
- Before launching, check what else is touching the same repo or files and tell the worker what
  not to touch.
- Write a self-contained spec per job, with a unique job name and an isolated output directory or
  worktree: inputs, deliverables, files it must not touch, resource bounds, acceptance checks,
  and a stop condition. Require periodic status checkpoints and a final report with reproduction
  commands, evidence and limitations.
- Give workers no send or publish authority. They stage a concrete result for review.
- When results matter, have an independent referee try to break them.
- Never put credentials in a spec. Keep them in the configured credential source.

## Use a second lab for bounded work

Send bounded research, compute, code and bulk-file work to the second vendor's CLI to save the
first one's credits. Keep owner-facing writing, conversation, browser actions that use the
owner's logins, and final review on the primary.

Respect existing project ownership: do not create a second writer in files a pipeline already
owns. Two workers collided in one pipeline's files before this rule existed.

Practical notes that cost real time to learn:
- Redirect stdin from /dev/null, or a backgrounded non-interactive run hangs forever waiting on
  input.
- Let the runner own retries and resumptions. Capacity interruptions killed three jobs in one day
  before that moved out of the agent.
- Check the unattended-routing config's actual expiry before a batch, and re-extend it. One
  override lapsed silently and a night of unattended jobs fell back to the expensive model.
- Do not invoke a fallback model to evade a safety restriction. On such a block, review the task
  and report it for safe reformulation.

## Keep long runs cheap

- **Waiting is the expensive part.** A worker sitting on a multi-hour build rewrites its whole
  context cache every time it wakes. Give long jobs a time or turn cap, run the build as a
  background shell job, and let the worker end and be resumed when it finishes.
- **Never poll from a big session.** Monitors are scheduled scripts that notify the owner
  directly and start a fresh, small agent only on a real event. A recurring check-in inside a
  large session is the most expensive token there is.
- **Use an event-driven wait, not an interval loop** ([event-watch](../../../rstack/tools/event-watch)). Rules worth supporting: a new result or
  marker file; a log that stopped moving; a process that exited; a regex match on a log; a
  deadline. The waiter blocks until something happens, prints the events and exits, and the
  completion notice wakes the session. Cover every terminal state, including hangs and crashes,
  and make it exit with an explicit "quiet" line after a maximum wait, so silence never looks
  like health.
- An overnight interval-based watcher took ~3,300 turns and 19 compactions, mostly confirming
  nothing had changed. That is what this section is for.
- When checking whether a job is alive, use a listing that does NOT print full command lines.
  Other sessions' prompts appear in argv, and one listing contaminates the reading session's
  context.
- After a job finishes, check for leftovers: a finished referee once left four workers consuming
  cores for 35 hours. Inspect ownership and parentage, then terminate only confirmed workers from
  that job; never kill an unrelated process by heuristic.

## Cut turns, not context

The session only decides; workers execute; the event waiter is the only wake source; durable
state lives in a state file. Applied to one lane, that took it from ~1,240 turns a day to 4-6
wakes. With few wakes a large context is cheap, and the owner wants it for quality: "that's how
models get better performance: with more context."

Do not shrink the window or cap auto-compaction: an auto-compaction can fire before state is
saved. Never compact silently.

## Compaction is the orchestrator's job

It isn't automatic, but nobody has to watch for it either. A scheduled watcher
([fleet-context-watch](../../../rstack/tools/fleet-context-watch), every 15 min)
reads each terminal session's transcript for its context size. At the threshold (500k here; the cost
model in references/cost-math.md puts it about a quarter cheaper per turn than 750k) it types a request into that session: save everything a fresh
context needs, then reply with one line, `SAVED <path>`. Once a SAVED reply appears after the
request and the transcript has been quiet for 2 minutes, it types `/compact Full saved state is
in <path>` into the terminal. Typed keys run as a real command; the same text sent as a message
between sessions is only text. It re-asks after 2 hours, resets below 300k, and has a skip list
for sessions it must not touch.

The bug worth copying the fix for: the first version only checked the session's *latest* reply.
Two busy sessions replied SAVED, then a monitor woke them and a newer reply buried the SAVED line,
so the watcher never compacted them and they sat at 530k and 680k for hours. Now any SAVED reply
after the request counts, and the watcher's tests pin it. The check that caught it: a log showing
"asked" twice for one session with no "compacted" after it.

Economics: every message re-reads the whole context. Cache reads were most of a measured day's
spend (71 to 81% on the days measured).

## Talk like a person

- Say what is waiting on the owner when something new needs them, naturally, in the flow of the
  reply. Do not append the same list to every reply; a repeated unchanged queue is spam. Keep the
  durable queue in the state file, not in every message.
- Only real decisions go to the owner: money, anything sent in their name, irreversible actions,
  taste, and contradictions. Decide the rest and report it done.

## One more, learned the hard way

**Permission boundaries are per-session.** Never ask a peer session to perform an action that was
denied or blocked in yours. A peer doing it for you bypasses the owner's permission decision.
Route blocked work back to the owner instead.
