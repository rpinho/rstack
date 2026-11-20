# Rule #1: the harness never gets in the way of the work

**The rule.** rstack and the research harness exist to make the work go faster and better. A gate,
hook, lint or launcher that stops real work for its own reasons is a harness bug, not a safety win.
Every check **fails open**: it warns, logs and lets the work continue. Only the hard lines may
refuse: money, sign-ins and credentials, sends or posts in Ricardo's name, permanent deletes,
privacy/IP egress, and running third-party code unsandboxed. Even those refuse with the fix in the
message, never a dead end. Harness errors are never charged to a model, a lane or Ricardo.

**Ricardo, 11-20:** "Make sure the harness is not getting in our way. That should be rule number
one of the harness or rstack." Same day: "wut?" when the grading gate blocked new lane work.

**Evidence (one day, 11-19/20):** the grading gate blocked lanes from starting work (fixed 9193dce);
agy jobs launched without Bash (launcher, not model); auto_grade read the controller copy of a
--host job and failed good work; the nested sandbox (exit 71) blocked three CellularAI referee
verdicts; math jobs fell through an untracked launcher. Each one cost hours of lane time and was
first reported as the model's or the lane's failure.

**Enforced by** (harness-m5, 11-20):
- every gate declares a class, `hard-line` or `fail-open`, in [rstack/gates.json](../gates.json); a hard line
  names its reason and its fix, and a call general has not made yet is `pending` with a recommendation.
  [gates_lint.py](../tools/gates_lint.py) fails any gate in the code with no class;
- the class lives in the registry, not in the gate: hooks decide through [_hookfail](../hooks/_hookfail.py) and
  everything else through [harness_blocks.gate()](../../harness/harness_blocks.py), so a fail-open gate's deny
  becomes a warning and its crash an allow;
- every refusal and warning is one line in `~/.local/state/rstack/harness-blocks.jsonl` (utc, host, gate,
  class, job, lane, outcome, reason, fix);
- the daily tick (leaderboard/daily.sh) counts blocks later rerun, overridden or retracted as harness bugs
  and sends general the top three blockers (`tell-general fyi`);
- [tests/test_fail_open_gates.py](../../tests/test_fail_open_gates.py) feeds each fail-open gate real work
  input and its crash path;
- harness-caused failures are retracted, never graded against the model: `worker_models.py --retract`, a
  quota hit is ungraded, and a run the wrapper or launcher refused is ungraded with "harness: <reason>".
