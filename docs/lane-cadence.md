# Lane cadence, lint and agent alerts

Disabling sweep workers must not hide a missed deliverable. `CADENCE.toml` describes the output, interval, warning threshold, owner and evidence locations. Cadence evaluates delivery independently of worker enablement. It uses configured file mtimes or timestamps in a receipt log; a configured receipt log is authoritative, and failed attempts can be excluded through a success field. Future timestamps never count as delivery.

Declare the lane's output, not a worker's artifact. A lane whose `CADENCE.toml` names a successful sweep report as its deliverable reads as STALLED whenever the sweep stage cannot run, however much that lane shipped; the alert then repeats indefinitely and carries no information, which buries the real ones. When a lane delivers emails, submissions or logged results, point `evidence_jsonl` at the ledger that records them, and leave the success field out when the lane is required to log every run, win or not.

A fixed release epoch bounds initial grace. Restarting a monitor does not reset it. The monitor reports healthy, warning, stalled or configuration states and records transitions, recovery and retry state. Missing evidence and malformed configuration remain visible. Lint also checks queue depth, source freshness, unread ideas, overdue tests, receipt integrity and outreach follow-ups.

Lane-health notifications append to `RH_AGENT_ALERTS`, an on-disk agent queue. Payloads carry lane/check summaries, not log or dataset contents. A consuming agent must be scheduled separately; writing the queue does not itself wake a model. Pod/provider alerts use a separately configured notification adapter.

`tools/event-watch` can wait for new paths, stale files, process exit, matching log lines and deadlines. It establishes an initial baseline and tracks offsets, so old lines do not repeatedly trigger. Optional notifications are off unless configured.

Code: [cadence.py](../harness/cadence.py), [lane_alerts.py](../harness/lane_alerts.py). Tests: [test_lane_health.py](../harness/tests/test_lane_health.py).
