# Autonomous subsystems refill themselves

**The rule.** A subsystem that is meant to run on its own funds, updates, resets and refills itself
from its own automatic sources. It never routes a routine ask to the person. The person gets one
alert, only when every automatic source is empty.

**Why.** A lesson from the laptop's session fleet, about a self-sustaining test subsystem. An ask
the system could have answered itself costs the owner a context switch, and teaches them that its
asks are noise.

**Enforced on the laptop** by a check on outgoing asks: its ask-format check refuses any ask line
that names that subsystem.

**Not enforced in rstack yet.** The nearest mechanism is
[lane-no-questions](../hooks/lane-no-questions.py), which denies question cards to every session
but the conductor, so lanes decide or route to the conductor instead of waiting on the owner. It
does not yet know which subsystems are meant to be autonomous. The candidate is a list of them in
the asks check, refusing any owner-bound ask that names one unless it says every automatic source
is empty.

Related: [short asks to the human](short-asks.md).
