# The stack as it actually runs

The rest of this repository is the part anyone can reuse. This page is the thing it was taken
from: two always-on Macs (a Mac Mini for control, a second Mini for compute) running my agents
every day since July 2026, counted by `inventory.py` and graded by `coverage.py` on 13 November 2026.

It is here because "a map plus some principles" undersells it. Most of what keeps the system
working is not the agents. It is the hooks that refuse, the scheduled jobs that notice, and the
lints that run before anything leaves.

## By the numbers

| What | Count | Notes |
|---|---:|---|
| Hooks | 25 | Run before a tool call and can refuse it. All 25 are mapped to a layer. |
| Launch agents | 80 | On both machines. 77 are mine; 3 belong to an installed vendor app and are excluded with that reason. |
| Lints | 23 | 11 are live; the other 12 are backup copies the inventory still finds, excluded by name. |
| Skills | 19 | One task each: email, X, publishing, the research harness, recovery after a reboot. |
| Memory rules | 348 | One fact per file, with the reason it exists. |
| Lane rules | 8 | Shared rules every research lane carries, synced from one source. |
| **Total** | **503** | 486 mapped to a layer, 17 excluded with a written reason, 0 unmapped. |

Of the 356 rules (memories plus lane rules), **131 have something that enforces them and 225 are
still prose.** That second number is the honest one. `coverage.py --top` ranks the prose rules by
how often they have actually been broken, from a ledger of 47 recorded corrections, and that list
is the queue for turning prose into checks. A selection from the top of it:

| Breaks | Rule, in general terms |
|---:|---|
| 7 | Check a printed prep document against the open items before it is relied on in a room. |
| 6 | Anything going to an outside expert gets an independent readability review first. |
| 6 | Writing in my name uses short plain sentences. |
| 5 | After agents finish, check for their leftover processes before calling it done. |
| 5 | Before deleting anything, check what still references it. |
| 5 | Reviews stay lean; the effort goes into ideas, not more review rounds. |

The ranking is a heuristic over free text, and it prints the matched corrections so every entry
can be checked by hand. It is a queue, not a measurement.

Two rules keep this count honest. An enforcement column is allowed to say **nothing yet**: that is
a tracked gap, written down as one, not a rule that happens to be unenforced. And anything new
that nothing maps (a hook, a scheduled job, a skill, a memory) makes `coverage.py` fail, so the
map can't quietly fall behind what's on disk. It was at 0 unmapped when these numbers were taken,
and a new item breaks that the day it's added.

## Layers

There are fourteen. Ten are about the machinery and are listed here. The other four cover my own
life and stay private, along with their playbooks.

| Layer | Items | What it owns |
|---|---:|---|
| Fleet and orchestration | 29 | One conductor session, many lane sessions; lanes reach the conductor only through a relay script. |
| Guards | 3 | The two skills for changing the machine (this map, and a re-runnable security pass) and the daily hook audit. The hooks themselves are counted under the layer each one protects. |
| Outbound communication | 72 | Email, X, the voice rules, contacts. Linted before it leaves. |
| Research harness | 106 | Lanes, frozen selection, referees, the yield check, the model leaderboard. |
| Publishing and egress | 6 | Nothing leaves unscanned; agents whose output leaves run with an empty identity. |
| Cross-machine handoff | 19 | A second machine, and a contract for what may cross in each direction. |
| Memory and the knowledge base | 35 | A worktree per session, then land; the main tree is never edited directly. |
| Background jobs | 19 | Wait on events, never poll; heavy compute goes to rented machines. |
| Family apps | 111 | Learning games I build for my two kids, and the jobs that serve and check them. |
| Session mechanics | 4 | Context limits, save-then-compact, session naming. |

The family layer is the largest, at 108 items.

## The hooks

The main ones. Each exists because something went wrong first. Generic versions of the ones marked **here**
are in [`hooks/`](hooks/), with tests.

| Hook | Refuses | Because |
|---|---|---|
| fail-safe wrapper (**here**) | nothing itself; makes every other hook refuse on its own internal error | A hook blocks only on one exit code or an explicit decision. Five of the hooks on this machine ended `except Exception: exit(0)`, so a crash let the call through, silently. |
| poll guard (**here**) | a third identical foreground status check within 30 minutes of the last | Sessions agreed in prose to stop polling and kept doing it. Fail-open on purpose: it saves turns, not losses. |
| trash guard (**here**) | a delete scripted through Finder; deletes go through `/usr/bin/trash` | Every deletion has to be recoverable, and Finder played the trash sound once per item. |
| main-tree guard (**here**) | a commit straight onto the knowledge base's main tree (it denies; on its own internal error it asks) | A session read files from the main tree, then edited and committed there. The first version guarded a path that no longer existed and was dead for four months. |
| pod gates (**here**) | creating a rented GPU machine without a self-termination deadline | A pod's only shutoff was a session remembering to stop it, and sessions die; now the start command carries its own kill. The first version of the gate crashed on unexpected input and let a pod through without one. |
| conductor-inbox gate (**here**) | a lane messaging the conductor session directly | Every wake replays the conductor's whole context. Lanes file through the relay, which wakes it only for decisions. |
| read the thread first (**here**) | sending an email reply unless the page text was read in the last 30 minutes | A screenshot is not reading. |
| publish gate | a publication click or `gh` call that skips the publish checklist | Denies on every internal error. |
| friend-reply gate, voice gate | sending to a friend without a passing lint in the last 20 minutes | Replies that ignored what the friend had just said. |
| review-not-open | opening a long document on the owner's screen | Long documents go to a review page on the phone instead. |
| title index | (injects) the knowledge base's page titles at session start | Sessions said "we never documented that" about pages that existed. |
| context watch | (reports) context size at 500k, 750k and 900k tokens | So compaction is chosen at a good moment instead of happening mid-task. |

Three more hooks still fail open, besides the poll guard. Patches exist and were not applied, because nothing has
gone wrong through those holes, and I decided on 6 November not to build guards for failures that
have not happened. That rule is [its own principle](principles/guards-need-a-real-failure.md).

## The scheduled jobs

74 launch agents. The main ones, grouped by what they protect, with the reason each exists.

**Keeping the fleet alive.** A check of every session every 30 minutes that pushes to my phone
only on a problem: a session gone, context over 600k, or a session waiting on a question for two
hours. A context watcher every 15 minutes that asks a large session to save its state, then
compacts it once it replies; it exists because one session reached 862k tokens before anyone
noticed. A nudge every 30 minutes for lanes that go quiet with nothing running: one sat idle from
10:47 one morning and nobody noticed. Session recovery at login, and an updater that restarts a
session only after its window has been idle for 30 minutes.

**Keeping jobs honest.** A watchdog every 5 minutes that resumes a registered job whose process
died without writing an exit line, at most three times per job and never under memory pressure, so
a crash cannot feed itself. A yield check every 6 hours that fails lanes spending without
producing, after one ran 38 workers for two days with every check green and nothing worth sending.
A generic event watcher (**here**, in [`tools/`](tools/)) that blocks until a file appears, a log
goes stale or a process exits, which replaced an overnight watcher that took about 3,300 turns and
19 compactions mostly confirming nothing had changed.

**Keeping rented compute bounded.** Pod checks every 15 minutes, utilisation sampling every 5, and
result harvesting every minute before a deadline, so results reach the Mini before a pod ends
itself. A renewal job that extends a busy pod's self-termination timer and never renews an idle
one. A low-balance alert on the model API account.

**Keeping the knowledge base whole.** A nightly ingest that processes the day's bookmarks
and writes the morning digest. A nightly encrypted backup and a mirror push to a second machine.
A weekly coherence report. Two scheduled jobs used to commit in the main tree, were blocked by the
repository's pre-commit hook, and left staged files that stopped the next night's run from landing; they now
work in their own worktree and land like any session.

**Keeping the research going.** A daily sweep and a six-hourly intake for the research harness. A daily
model-role table built from the harness's own outcomes, so no script hard-codes a model name. A
twice-daily push of the open-science repository, gated by the same egress scan as every push.
A guard that a frozen challenge entry has not changed.

**Keeping the family apps up.** Seven game servers, a promoter that ships a reviewed build, an
audit twice a day, a check every morning that the day's quest is ready, and a guard that pauses
science compute while the games are in use.

**Housekeeping.** Six engagement rounds a day for the science account on X. Each round drafts replies and posts
one queued original if one is ready; a separate reviewer posts only the drafts that pass the voice
rules. A resource log every 5 minutes,
kept to size the next machine from real use. Dated reminders for expiring credits. An hourly disk
cleanup that moves old build scratch to the Trash and never empties it; it was weekly until
scratch reached 37 GB between runs, and it skips any build a running process is still using,
after one run removed a release a draft was running from.

## What is not here, and why

- **The memory files.** They are mine and name people. The principles in
  [`principles/`](principles/) are the parts that generalise.
- **The four private layers and every playbook.** Same reason.
- **The real term lists** behind the egress scan and the relay's quarantine. The tools ship with no
  terms at all; you supply your own.
- **Anything with a host name, an account, or a dollar figure.**

The scripts that produced the counts above are [`inventory.py`](inventory.py) and
[`coverage.py`](coverage.py). Point them at your own setup and you get the same tables for yours.
