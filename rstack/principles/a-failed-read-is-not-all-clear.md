# A failed read is never all clear

**The rule.** A watchdog, sweep or report that cannot read one of its sources says so, loudly, in
its output and to whoever acts on it. It never returns the empty answer that means "nothing wrong".

**Why.** A scheduled watchdog called the harness by a bare command name. The scheduler's PATH did
not include it, so every read failed for eight hours. The script caught the error and returned an
empty table, and an empty table meant "no lane is behind". Four lanes were stalled for two to four
days and none was flagged. Nothing was broken except the one thing that was supposed to notice.

**Enforced by**
- lane-nudge: a cadence read that fails or returns no lanes prints `CADENCE READ FAILED ... every
  lane is UNKNOWN this run, not fine`, pushes once per failure streak (`--alert`), and nudges quiet
  lanes as "cadence unknown" instead of skipping them ([test](../../tests/test_lane_nudge.py)).
- `rstack/tools/hook-audit`: a guard that crashes on input it cannot read is reported, because a
  crash is not a decision and the action goes through.

**How to apply.** Call tools by full path from anything a scheduler runs. Distinguish "the source
says nothing is wrong" from "I could not ask". When in doubt, emit a row that says which source
could not be read, and keep going with the rest.
