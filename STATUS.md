You asked: Judgment roles resolve from the leaderboard, in code. I will: implement leaderboard-driven judgment selection and launch routing, the instruction hook and freshness lint, test them, and commit on this branch.

Checkpoint 1: RULES.md is absent at the worktree root; locating any applicable copy before implementation. No code changed yet.

Checkpoint 2: Read tools/RULES.md (no root RULES.md exists). Implemented judgment aliases, maker-family selection using bug_verdicts.maker, owner-prefixed overrides and JSONL logging, and selector-driven launch routing/spec refusal. Next: hook and freshness tool with fixture tests. No research result is claimed; this job ships a harness fix.

Checkpoint 3: Targeted fixture tests passed: 52 passed in 14.45s. The default interpreter lacks pytest; using the existing project virtualenv via PATH, with PYTHONDONTWRITEBYTECODE=1 and TMPDIR inside this worktree. No dependencies installed. Full suite is running. Added coverage for wrapped judgment instructions and a pin refusal without maker metadata after checking these edge cases in code.

Checkpoint 4: Final targeted tests passed: 53 passed in 15.42s. /usr/bin/time -l reports maximum resident set size 39,813,120 bytes for that run. Shell syntax and git diff whitespace checks pass. The original interpreter attempt failed with "No module named pytest" before collecting tests; no code rollback was applicable. The suite uses the existing interpreter/dependencies, not an installation. Full-suite completion and the branch commit remain.

Checkpoint 5: Final code passed the full suite: 2297 passed, 84 skipped in 298.98s (0:04:58). /usr/bin/time -l measured maximum RSS 330,252,288 bytes, below the 1 GB budget. All requested fixture scenarios pass. No code failures occurred. The implementation, documentation and test changes are ready to commit; the report will record that commit.
