# Intermediate: make it remember, and make it check

You use an agent on real work. Now make it keep what it learns about your project, check its own
work, and stop the one mistake that keeps happening. Each section is a how-to; do the ones you need.

## Give your project a CLAUDE.md

Run `/init` in your project. It writes a `CLAUDE.md` the agent reads at the start of every session.
Then cut it down: keep the commands to build and test, where things live, and the rules people get
wrong. If a line wouldn't change what the agent does, delete it. Codex reads `AGENTS.md`; one can
import the other.

## Write a skill for something you repeat

If you've explained the same procedure to the agent twice, it should be a skill. Put it in
`.claude/skills/NAME/SKILL.md` inside the project (shared with everyone who clones it) or in
`~/.claude/skills/` (just for you). The `description` line decides when it gets used, so write it
as "Use when ...".

## Work in a worktree

When you want the agent working on two things at once, or you don't want it touching your current
branch, give it its own checkout:

```sh
git worktree add ../my-project-fix -b fix/the-bug
cd ../my-project-fix && claude
```

Merge the branch when it's done, and remove the worktree with `git worktree remove`.

## One verification skill

Many of the failures written up in this repo weren't wrong code. They were claims nobody checked
("done, tests pass" when nobody ran them). Write a skill that says what "done" means in your project: which command to run,
what output counts as passing, and that it shows you that output before it says it's finished.

## One hook

A hook is a script Claude Code runs before or after a tool call. Unlike a line in CLAUDE.md, it
can't be skipped. Pick the one mistake that keeps happening and refuse it. A PreToolUse hook that
exits with code 2 blocks the call and shows its message to the agent. [trash-guard.py](../../rstack/hooks/trash-guard.py)
is a small real one: it refuses deletes that bypass the Trash. Later, the
[hooks README](../../rstack/hooks/README.md) has the rest of ours and why each exists.

## Ready for the next one?

Move on to [advanced](advanced.md) when you can say yes to all three:

- My project has a CLAUDE.md I've cut down, and a skill I wrote that gets used.
- I've had an agent work in a worktree or in the background while I did something else.
- I've turned a rule that kept being broken into a hook or a test.
