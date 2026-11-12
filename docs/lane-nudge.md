# Lane nudge: lanes that go quiet

A lane can stop without failing. Its last job ends, the agent reports once and waits at the prompt, and nothing is set to wake it. `rh lanes cadence` notices, but only on the lane's delivery window (often a day), and only if something runs it. A check that nobody delivers is just prose.

`harness/tools/lane-nudge/lane-nudge` delivers it. Run it every 30 minutes. For each tmux session named `PREFIX + owner_session`, it types one resume prompt into the pane when all of these hold:
- the session's last real turn (a user or assistant message in its Claude Code transcript) is at least `--idle-min` minutes old (default 60);
- the pane shows no running shell or agent;
- `rh lanes cadence` reports WARN, STALLED or BROKEN for the lane, or the session has simply been idle that long;
- the lane wasn't nudged in the last `--reask` seconds (default 2 hours).

Lanes marked EXEMPT or UNCONFIGURED by cadence are never nudged, and neither are sessions in `--skip` (finished challenges, on-demand sessions, the conductor). `--dry` prints the decisions without typing.

```sh
harness/tools/lane-nudge/lane-nudge --skip conductor,on-demand-lane --dry
# cron: */30 * * * * /path/to/lane-nudge --skip conductor
```

Where it sits in the enforcement ladder (architecture > compiler > CI/lint > bot rules > prose): the "lanes never stop" rule used to be prose in each lane's instructions, plus a lint the operator had to remember to run. This moves it into a scheduled script that acts. The prompt is plain text in the pane, so the agent still decides what to do next; the script never chooses work for it.

Idle is never the transcript's mtime. From 11-08 to 11-11 every lane slept: Claude Code's idle compaction and the session metadata it rewrites while idle touched each transcript about hourly, so no pane ever looked idle and nothing was nudged for three days. Compaction boundary and summary rows, meta rows and untimestamped metadata rows are skipped; a peer message or a task notification is a real turn.

Each Mac that hosts lane sessions runs its own copy against its own tmux. Under launchd pass `--tmux` (or `TMUX_BIN`) and `--rh` as full paths; `--log` (or `LANE_NUDGE_LOG`) appends each nudge to a file.

Limits: it only sees tmux-hosted Claude Code sessions, and it detects "running" from the pane's status line, which can change between Claude Code versions. Tests: `tests/test_lane_nudge.py`.

A cadence read that fails is never read as all clear. If `rh lanes cadence` cannot run or prints no JSON, lane-nudge prints `CADENCE READ FAILED`, runs `--alert COMMAND` (or `LANE_NUDGE_ALERT`) with the message once per failure streak and again on recovery, and still nudges quiet lanes, as "cadence unknown". One installation called a bare `rh` from launchd, whose PATH did not include it; every read failed for eight hours and every lane read as fine. Pass `--rh` (or `RH_BIN`) as a full path when a scheduler runs it.

A paused lane has one place for its pause: `lanes/<lane>/HOLD`, whose first line says who paused it and why. `tools/launch.sh` refuses the lane's jobs, `rh sweep --all` skips it, `rh lanes cadence` reports it HELD rather than STALLED, and lane-nudge leaves it alone. Only the conductor removes it. friends, 11-11: paused by its owner, and still nudged twice to start the next round.

A result that lands while a lane waits is a nudge of its own. With `--outputs` (globs of finished-job files such as `_codex/{lane}_*.last.md`, `{lane}` filled in), a file newer than the session's last real turn and at least 15 minutes old wakes the lane even though a watcher shell is running, once per file, with a message that names the file and asks it to fix the watcher rule that missed it. math, 11-12: its review finished at 16:18Z and it sat until 21:05Z, because the watcher it waited on watched other files and a running shell made the pane look busy.
