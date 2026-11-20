# A guard must refuse, not crash

**The rule.** Most hook systems block a tool call only on a specific exit code or an explicit deny
decision. Every other outcome lets the action through. So a guard that raises on malformed input,
a missing state file or an unreadable config is not a weaker guard. It is no guard, and it fails
silently, which is worse than failing loudly.

Twelve guards on the setup this came from were audited. Five ended in the equivalent of
`except Exception: exit(0)`. One of them was the check that a rented machine must carry its own
shutoff command: it crashed on an unexpected payload shape and the machine was created without
one, which is the single outcome it existed to prevent.

**The hard part is not catching the error.** It is deciding what to do with a call you could not
read. A guard wired to every shell command that denies on any internal error is safe and also
unusable: one bad state file and nothing runs. So each guard declares two things:

- a **triage** function answering "is this call in the set I guard?", which does substring work on
  the raw input only, with no parsing, no file I/O and no schema assumptions, so it still works
  exactly when the real check has already failed;
- what it guards, in one clause, for the refusal message.

An error on a call inside that set is refused. An error on a call outside it is allowed, with the
failure printed where someone will see it. Report the exception TYPE, never its text or the input:
payloads and environment blocks hold credentials.

Two guards are deliberately exempt and say so in their own files: a cost backstop, where denying
read-only commands would cost more than the waste it prevents, and a publication gate that already
denied on every internal error.

**Test it by feeding each guard input it cannot read**, and assert the refusal. Four of the defects
found this way were in the author's own new code, including a guard that normalised an unreadable
payload into "not the dangerous action" and allowed it.

**Since 11-20 this applies to the hard lines only.** [Rule #1](harness-never-in-the-way.md): a gate that is not a hard line fails open, so its crash is a logged warning and the call goes ahead. `_hookfail` reads the class from `rstack/gates.json`.
