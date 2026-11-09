# Change direction after a dry streak

**The rule.** Three tries of one approach with nothing usable: stop, write the dead end down where
the next session will read it, look for prior art, and change the method. Running it again with a
new name is the same method.

**Why.** One lane ran about eighty rounds of a single method against a target while the answer, a
better family of methods, was already written down in its own notes. Every round was a reasonable
next step on its own; together they were the same experiment repeated.

**Enforced by**
- [lane-yield](../../harness/tools/lane-yield/lane_yield.py) `DRY_STREAK`: three rounds in a row
  with nothing selective fails the lane.
- [the round gate](../../harness/tools/rounds.py): `REPEAT` refuses an identical (generator,
  params, scorer) within five rounds, whatever the family is called; a round cannot start while the
  previous one has no logged outcome; `KB_UNREAD` refuses round 1, and any round after a dry
  stretch, without a consult receipt from the notes; `close-family` records a dead end.
