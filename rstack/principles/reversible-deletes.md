# Every deletion is reversible

**The rule.** Never hard-delete anything the owner might want back. Move it to the system trash,
or to a dated backup. Unconditional recursive deletion is denied outright. Before deleting data
you did not just create, verify a copy exists elsewhere first: extract, verify, then remove.

**Enforced by** a trash-only storage adapter that refuses to delete at all when no trash command
is configured, a guard that denies file-manager-driven deletes, and a permission rule that denies
recursive force-deletes.

**A restore point has a deadline in code** (the laptop, 11-15). A destructive change to live data
leaves a restore point: a clone, a snapshot, a backup table. Its removal is scheduled as a dated
job that re-checks the change held and then asks for the drop, never left to a note. A restore
point nobody schedules lives forever, and an erasure it holds a copy of has not happened. If a
downstream path must not see the old data, as with an erasure request, it gets a guard that
accounts for the restore point until the drop. Not enforced in rstack yet: prose.

It reads as paranoia until the first time a cleanup step removes the only copy of an input a week
of work depended on.
