# A session's context is a resource

**The rule.** Whatever a session reloads on every wake, something has to keep clean. If content
that breaks a session can get written into the files it rereads, the session breaks again every
time it starts, and the obvious remedies do not touch it.

**The failure it came from.** One general-purpose session kept being stopped by a safety
classifier. The suspicion was that another session was leaking into it, which is not how
sessions work. The real causes were duller:

1. Worker sessions reported results into a shared inbox, and the general-purpose session read those
   reports verbatim on its next wake.
2. The index entry for one of those workers' write-ups carried the whole technical detail in a
   single table cell, and the index is reread at session start.

The second one is the interesting half. That file is also reread **after compaction**, so
compacting never cleared it: the summary gets rebuilt from the files that put the content
straight back. Three stalls in one evening, all of them looking like a fresh problem.

**Enforced by** two mechanisms, one per channel. Inbound messages from other sessions are
filtered at the relay: a matching message is written to a file and the inbox row carries a short
summary plus that path, keeping its wake priority, so nothing is lost and nothing is blocked. The
always-reloaded files are checked by a lint wired into the repository's pre-commit hook, with a
named escape that shows up in the log.

**Co-occurrence, not a word list.** The same vocabulary is legitimate elsewhere in the same
files: an index legitimately indexes published papers on the subject, and unrelated pages use
some of the same words for something else entirely. So both mechanisms fire only on a term
appearing **next to** working detail — an internal identifier, a score, a configuration value, a
raw sequence — plus one standalone rule for data that is never prose in any context. Encoding
that distinction is the design, not a refinement of it.

**Calibrate it, or it gets switched off.** The first version of the lint flagged 449 lines in one
file. The alphabet it searched for is a subset of English letters, so ordinary capitalised words
matched it. It now checks candidates against the system wordlist with light stemming, and applies
two density thresholds by length. A lint that cries wolf gets disabled, which is worse than
having none.

**A filter must not log what it filters.** The first version of the relay named the matched terms in
the inbox row it wrote: the row is the part the session reads on every wake, so the mechanism built to
keep that vocabulary out of the session's context was writing a tidy list of it into the file the
session rereads. The next wake was stopped again, by the fix. The row now carries a count. The terms
stay in the quarantine file, which that session never opens, and in the sending worker's own output,
which is its own context. Generalise it past this one script: a guard's log line, error message and
metric label are all on the clean side of the boundary it enforces. Log what it did, not what it saw.

**Two things the mechanisms caught that the hand fix did not.** A line the manual pass missed,
and then the fact that the lint had been installed where nothing ran it: the repository sets
`core.hooksPath`, so `.git/hooks/pre-commit` is dead code. A test commit that should have been
refused went straight through. A guard nobody runs is prose with a shebang.

Related: [architecture, not prose](architecture-not-prose.md) — the first fix here was a manual
scrub, which held until the next write-up was indexed.
