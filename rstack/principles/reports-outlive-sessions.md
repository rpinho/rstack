# Reports outlive sessions

**The rule.** A worker writes its result to a file that the fleet's sweep reads, before it sends any
message about it. A waiter, watcher or background task inside a session dies with that session on
compaction or restart, and so does the report it was going to send.

**Why.** The laptop's lesson from a day of running a session fleet: a report held only by a live
session is lost when the session compacts. On the Mini, the fix for a related failure only worked because the reports were already
files: lanes write to the conductor's inbox, so when the conductor dropped them, the inbox still
had every one, and a hook could put them back in front of it.

**Enforced by**
- [relay](../tools/relay) writes every lane report to the conductor inbox file, and
  [general-inbox-relay](../hooks/general-inbox-relay.py) reads that file with a cursor on every
  prompt. A report survives the sender's session and the conductor's compaction alike.
- `lane-nudge --outputs`: a finished-job file newer than a session's last real turn wakes that
  session, whether or not its own watcher is still alive ([docs](../../docs/lane-nudge.md)).

**How to apply.** The file is the report; the message is a pointer to it. If a job's only record of
success is a line a live session was going to print, it has no record.
