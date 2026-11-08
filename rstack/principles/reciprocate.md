# Reciprocate

**The rule.** A reply mirrors the message it answers: its length, its greeting and sign-off, its
warmth, its questions, whether it mentions family, its language. The owner's words: "we're like a
mirror."

**Why.** Agents answering a friend tend to write the reply they would want to send: longer, more
formal, with a result or an ask bolted on. Reminders in the writing guide did not hold. A friend
who wrote four warm lines and asked how things are does not want twelve lines about a paper.

**Enforced by** the outreach lint ([reciprocate.py](../../harness/reciprocate.py)). A reply is drafted
with the message it answers (`--incoming`), and lint fails it with a `RECIPROCATE_*` code for each
mismatch, quoting their line and ours. When it is our move to answer, or the send was requested,
the draft fails without the incoming message, so the check cannot be skipped by leaving it out.

**Limits.** The matching is lexical and covers English and Portuguese. It catches a missing
greeting, an unanswered question or a reply three times too long. It does not judge tone; a person
still reads the two side by side before approving.
