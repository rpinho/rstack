<!-- lane-rules-common: generated from harness/LANE_RULES_COMMON.md by `lane-rules-sync`. Edit there, not here. -->
## Rules every lane gets

**HARD RULE (Ricardo, 11-04): the goal must not turn into process, and success is never activity.**
Rounds launched, jobs run, designs scored, tests passed, checks added, ideas logged and dollars
spent are not results. The only result is the thing that was asked for, shipped. A lane that
measures itself by how much it ran has already lost the ask.

**Restate the ask.** The first line of each round, job or campaign note is
`You asked: <the ask, in the spec's or Ricardo's words>. I will: <what this run does differently from the last one>.`
A run whose difference from the previous one cannot be named is a repeat and must not start.

**Stop rule.** Three runs that fail the same way end that approach; there is no fourth. Record in
STATUS.md or STATE.md what failed, by number, and what changes. "Same way" means the same thing
stopping the work, whatever the parameters were. On the first real failure after one of your own
changes, revert it before investigating.

Before relaunching, count this job's processes with `pgrep -f JOBNAME | wc -l` only; never print process command lines (other sessions' commands would land in this log).

**Log every run, win or not.** One line per run to this lane's `RESULTS.jsonl`:
`log-result --ledger <lane>/RESULTS.jsonl --new yes|no --kind <kind> --what "<what changed and what came of it>" --link <path> --referee HOLDS|NONE`
A passing verdict (HOLDS, ACCEPT, PASS) on a `--new yes` row also needs
`--verdict "<text or file>"` answering three questions, each with the file, command, count or line
you checked: `CONTROLS:` did an assumption override what the controls show? `CONTRADICTING:` was
data that contradicts the conclusion dropped or ignored? `LABELS:` was a label or annotation
trusted without checking it against the raw data? An unsupported "no" is refused, because it is
the cheapest way to satisfy a rubric. Rows with `--referee NONE` or a failing verdict are
unaffected. (BioBasicsBench failure modes, 11-06: these are what goes wrong, not arithmetic, and
our own referee passed 98% of 528 claims.)
`--new yes` only when something actually moved: a printed number beaten under the same definition
and data, a stated open problem settled, a prediction tested on new data, or a shipped artefact
that is better than the one before it. Reproductions, restricted variants you defined yourself and
sensitivity checks are not new. Say "no" plainly when it is no.

**Email in two languages (Ricardo, 11-05).** When a recipient's contact record carries a
language other than English, that language is the **default** for the whole email, and it
**opens** and **closes** in it. **English is required only where the content is technical** —
numbers, variables, equations, methods, measurements — because English is the science
language. Attachments are always English. The rule holds even when the recipient writes their
own science in English. `rh outreach lint` fails a technical paragraph in their language, an
opening or closing that is not in it, and an attachment that is not English; ordinary prose
in English anywhere in the email is a warning, because it belongs in their language too.

**No ops in friend emails (Ricardo, 11-06).** An email to a friend carries only what the
friend needs. Never our infrastructure or operations: providers (RunPod, OpenRouter), pods,
security incidents, key rotations, harness or watchdog details, or why something was re-run.
Say "re-checked on my own machine; the numbers match." If the friend asks about one of these,
answer in one plain line. The rule came from one sentence in an email of 11-05 — "The first
two ran on a RunPod server that has since had a security incident" — which cost a round trip
and told a friend about a host compromise he had no way to act on. `rh outreach lint` fails
any non-public message carrying those terms (`OPS_DETAIL`); when the friend raised the subject
themselves, name the term with `rh outreach draft --asked-about TERM` and it drops to a
warning, so a reply can answer them. It takes a term from the check's own list, never the
friend's words.

**A result is not sendable until someone else rebuilt it (Ricardo, 11-05).** A referee pass
is not evidence: 528 claims went through a referee that passed 98% of them. A result may go
out when a **separate model rebuilt it from the public inputs with its own code and got the
same answer**, and that re-check is recorded. Two of thirteen claims did not survive that on
11-05. Evidence **produced or modified on a pod** stops being evidence when the host is
compromised, and becomes evidence again only once it has been **re-run after the incident**
somewhere trusted, with the re-run recorded. `rh outreach lint` fails an email whose claim
has no recorded independent re-check, whose re-run did not reproduce it, whose re-check
dropped it, or whose pod-touched evidence was last re-checked before the configured incident:
`RECHECK_MISSING`, `RECHECK_FAILED`, `RECHECK_DROPPED`, `POD_EVIDENCE_STALE`. Name the claims a
draft reports with `rh outreach draft --claim DIR`.

**How this is enforced.** `lane-yield` reads that ledger on a schedule. BURNING fails a lane that
spends job-hours with nothing new; DRY_ROUNDS fails a lane that logs run after run with nothing
new; RUBBER_STAMP fails a referee that passes everything. A lane that stops logging reads as a lane
that stopped reporting, and is treated as such. Process is not the task: do not add gates,
receipts, audits or review stages unless the spec asks for them; write the suggestion in STATUS.md
and keep doing the task.

**Returned jobs are graded at return, by the harness.** A delegated job is graded pass, partial or fail
from its own checks: exit code, the `Shipped:` and `You asked:` lines, and every `Check: COMMAND` line in
its spec. Without Check lines the lane's reviewing model grades it. Put a `Check:` line in a spec whenever
the result can be checked by a command. To correct a grade, run the `GRADE ON RETURN` line at the end of
its launch log. Grading never holds up a lane: a job that could not be graded is recorded "ungraded" and
listed in the morning report. This is how other models earn a rank (Ricardo, 11-19: "it's very, very
important that we delegate to other models").

**Driver sessions log what they ship.** Work you do yourself in this session (not a launched job) has no
grader unless you log it. Each time you ship a unit (a result, a PR, a report), run once:
`delegate-log --model <your model> --source session --session <your tmux session> --task <id> --run-id <id> --verdict pass|partial|fail --asked "<what was asked>" --did "<what you did>" --shipped "<path, PR or link>"`
Use one stable id per unit for both `--task` and `--run-id`, so a retry does not count twice.
<!-- /lane-rules-common -->
