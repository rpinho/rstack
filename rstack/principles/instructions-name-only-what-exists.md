# Instructions name only what exists

**The rule.** An instruction file (CLAUDE.md, AGENTS.md, a skill, a memory note) names only paths,
links, commands and options that exist now. Anything it names that can be checked is checked
mechanically, and a stale one fails the build rather than waiting for an agent to trip on it.
Limits and numbers live in the code; the instruction points at the code instead of restating them.

**Why.** Agents follow the instruction file over the code. A published study of 40 projects found a
stale CLAUDE.md or AGENTS.md instruction followed about 90% of the time, against about 4% for what
the code actually did ([SmartScope](https://smartscope.blog/en/blog/claude-md-agents-md-stale-instructions-override-code-2026)).
Ours drifted the same way: a guard kept protecting a path deleted four months earlier, and a posting
skill kept a daily limit after the code that enforced it changed.

**Enforced by**
- `rstack/tools/instruction-refs`: resolves every markdown link, every repo path in backticks, every
  `rh` subcommand and action and every `rh` option named in the given files, and with `--local` every
  `~/` path on this machine. A skill's own files resolve against its folder first.
- [test](../../tests/test_instruction_refs.py): the repo's own AGENTS.md, CLAUDE.md, README, docs,
  skills and rstack pages pass it on every run of the suite.

**How to apply.** Run it with `--local` over the instruction files and memory folders that live
outside a repo, as part of whatever pass already reorganizes them. A finding is either a stale line
to fix, or a sentence that names a path on purpose because it is gone; reword that one so it says so.
Addy Osmani's agent-skills enforces the same thing in CI (`validate-reference-links`,
`validate-commands`, `validate-artifact-paths`).
