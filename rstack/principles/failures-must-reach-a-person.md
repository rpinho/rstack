# A failure that only reaches a log has not been reported

**The rule.** Every scheduled job's failure, and every result that lands while nobody is looking,
reaches a person: the conductor's next turn, or a push. Writing it to a log file is not reporting
it. A log is read only by someone who already suspects a problem.

**Why.** Two incidents on the same day. A bookmark-builder step crashed on every round of an
engagement job for two days. The job kept running and only its log knew; each round worked from a
list three days old, and engagement fell from 77 likes a day to 5. The round agents had even
written "needs a look" into that log, which nobody reads. Hours earlier, a lane sat idle with its
result already in: the watcher it waited on watched other files, and a running shell made the
session look busy.

**Enforced by**
- `rstack/tools/job-health`: every scheduled job whose last run exited with a code it does not
  declare fine, and every required output that is missing or older than its limit, is written where
  the conductor's asks-waiting hook shows it on every turn, and each new problem is pushed once
  ([test](../tests/test_job_health.py)). The freshness check catches a job that loses its input and
  keeps running empty rounds, which an exit code never shows.
- `lane-nudge --outputs`: a finished-job file newer than the session's last real turn wakes the
  lane, even with a watcher shell running, and asks it to fix the watcher rule that missed it
  ([docs](../../docs/lane-nudge.md)).

**How to apply.** For each scheduled job, name its output and how old it may get, and register it.
When an agent finds a problem, it tells the conductor through the inbox, never only a log. A quiet
day and a broken job must not look the same.
