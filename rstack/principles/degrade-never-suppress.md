# Degrade, never suppress

**The rule.** Anything that publishes, alerts or reports ships a flagged partial result rather than
nothing. Validate per item, not with one whole-run check that can fail closed and take every good
item down with the bad one.

**Why.** The failure is quiet by construction: a report that does not arrive looks the same as a
day with nothing to report. A digest that is late or partial gets noticed and fixed; a digest that
silently did not send gets noticed days later, if at all.

**Enforced by** nothing general in this repo yet. It is prose here. The pattern to copy: each
section or item is checked on its own, a failed one is replaced by a line saying what failed and
why, and the rest goes out on time.
