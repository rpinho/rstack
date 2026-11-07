# rstack tools

Standalone scripts (Python 3.9+ standard library, plus bash for `clean-room`). Each has its test in `../tests/test_rstack_tools.py`. None ships a term or pattern list; you supply your own and keep it private.

- `event-watch`: wakes a session only when a configured event happens (new file, stale output, dead pid, log match, deadline). One overnight watcher loop spent about 3,300 turns and 19 compactions confirming nothing had changed.
- `relay`: files a message for the conductor session, waking it only for decisions, owner requests and breakages, and quarantines messages that match your terms file, logging a count and never the terms. Relayed detail from a sensitive project stalled the conductor on a safety classifier, and naming the terms in the inbox row stalled it again.
- `egress-gate`: refuses to pass a directory, a push or a text that contains secret shapes or your own patterns and terms (exit 2). Agents build public output on a machine that holds private context, and checking by hand was prose.
- `clean-room`: runs codex or claude in an empty identity for work that will leave the machine. A fresh config dir still loaded the personal CLAUDE.md from the home directory, an ancestor of the workspace.
- `reload-lint.py`: blocks a commit that puts a configured term next to a configured working-detail marker in a file every session reloads, printing markers and counts, never the terms. An index line carrying a project's working detail stalled every general-purpose session that reloaded it.
- `_terms.py`: the shared terms-file reader, and the reason there is no built-in list.
- `terms.example.txt`: the terms-file format, with placeholder words only.
