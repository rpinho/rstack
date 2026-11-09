# Lane nudge: lanes that go quiet

A lane can stop without failing. Its last job ends, the agent reports once and waits at the prompt, and nothing is set to wake it. `rh lanes cadence` notices, but only on the lane's delivery window (often a day), and only if something runs it. A check that nobody delivers is just prose.

`harness/tools/lane-nudge/lane-nudge` delivers it. Run it every 30 minutes. For each tmux session named `PREFIX + owner_session`, it types one resume prompt into the pane when all of these hold:
- the session's Claude Code transcript hasn't moved for `--idle-min` minutes (default 60);
- the pane shows no running shell or agent;
- `rh lanes cadence` reports WARN, STALLED or BROKEN for the lane, or the session has simply been idle that long;
- the lane wasn't nudged in the last `--reask` seconds (default 2 hours).

Lanes marked EXEMPT or UNCONFIGURED by cadence are never nudged, and neither are sessions in `--skip` (finished challenges, on-demand sessions, the conductor). `--dry` prints the decisions without typing.

```sh
harness/tools/lane-nudge/lane-nudge --skip conductor,on-demand-lane --dry
# cron: */30 * * * * /path/to/lane-nudge --skip conductor
```

Where it sits in the enforcement ladder (architecture > compiler > CI/lint > bot rules > prose): the "lanes never stop" rule used to be prose in each lane's instructions, plus a lint the operator had to remember to run. This moves it into a scheduled script that acts. The prompt is plain text in the pane, so the agent still decides what to do next; the script never chooses work for it.

Limits: it only sees tmux-hosted Claude Code sessions, and it detects "running" from the pane's status line, which can change between Claude Code versions. Tests: `tests/test_lane_nudge.py`.

A cadence read that fails is never read as all clear. If `rh lanes cadence` cannot run or prints no JSON, lane-nudge prints `CADENCE READ FAILED`, runs `--alert COMMAND` (or `LANE_NUDGE_ALERT`) with the message once per failure streak and again on recovery, and still nudges quiet lanes, as "cadence unknown". One installation called a bare `rh` from launchd, whose PATH did not include it; every read failed for eight hours and every lane read as fine. Pass `--rh` (or `RH_BIN`) as a full path when a scheduler runs it.
