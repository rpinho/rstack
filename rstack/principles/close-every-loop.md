# Close every loop

**The rule.** Every output has a named consumer in code: a job that acts on the queue, a ticket
queue with an owner, or a report read on a schedule. Name the consumer before you build the
producer. Measure a loop by what reached its end, not by what it produced.

**Why.** Both machines learned it the same week. The laptop wrote it down after a day of running a
session fleet. On the Mini, lanes reported their results into the conductor's inbox faithfully, and the conductor stopped
passing them on to the owner. Every producer was green. The owner noticed only because the answers
he had asked for never arrived.

**Enforced by**
- [general-inbox-relay](../hooks/general-inbox-relay.py) and
  [general-relay-check](../hooks/general-relay-check.py): each session report is put in front of the
  conductor on every prompt, and its turn cannot end until the reply names every report's session.
  The report loop ends at the owner, in code.
- [job-health](../tools/job-health): a required output that is missing or older than its limit
  reaches the conductor, so a producer that stops is visible.

**Not enforced yet.** The laptop's version goes further: every loop emits a daily
produced-versus-consumed count with a floor rule, in the same alerting pipeline as everything else,
so a stall alerts instead of waiting for the owner. rstack has no such count. Until it does, a loop
whose consumer quietly stops is caught only by the two mechanisms above.

Related: [results, not activity](results-not-activity.md).
