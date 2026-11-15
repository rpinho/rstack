# Revert first, then reorder

**The rule.** After three forward fixes on one target, stop fixing forward. Revert to the last
state that worked, then run the path already proven to work first. Take on the unproven variant
only once that baseline holds again.

**Why.** A lesson from the laptop's session fleet. Each forward fix is a reasonable next step, and
each leaves the system in a state nobody has seen work. By the third, the failure being chased may
be one the fixes made.

This is the debugging form of [change direction after a dry streak](change-direction-after-a-dry-streak.md).
That one is about a research method that keeps producing nothing; this one is about a fix that
keeps not holding. Both count to three.

**Not enforced yet.** Prose. A candidate mechanism is a count of commits touching one file or
config key within a day, with a nudge at the third.
