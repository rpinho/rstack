# Verify before a destructive or load-bearing claim

**The rule.** "Unused", "redundant", "safe to delete" or "nobody depends on this" either cites the
check that showed it or is labelled as an unverified assumption. The same goes for a claim that
something is inaccessible or read-only.

**Why.** These words are where cleanups break things. A repository was archived as unused while a
weekly job still pushed to it; the job failed the next week. The claim was believed because it was
plausible, not because anyone looked for what still referenced it.

**Includes:** never "test" a credential you cannot explain by calling the service it belongs to.
An identification call can trip the owner's security alarm, and finding out whose key it is does
not need the call.

**Enforced by**, partly: deletions go to the Trash, never a permanent delete
([reversible deletes](reversible-deletes.md)), so a wrong "unused" is recoverable. The claim itself
is prose: nothing yet checks that an "unused" cites its search.
