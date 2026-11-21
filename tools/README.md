# Optional tools

These scripts are not installed or scheduled by cloning the repo.

- `launch.sh`: synchronous zsh executor adapter. Resolves a model role, registers a job, writes selection/outcome receipts and retries capacity errors. It does not send messages or publish. Outcome exit status is operational evidence only.
- `event-watch`: standard-library watcher. Put rules in `$HOME/.config/event-watch/JOB.conf` or `EVENT_WATCH_CONF`. Rules: `new GLOB`, `stale GLOB MINUTES`, `pid PID_OR_FILE`, `match FILE REGEX`, `deadline LOCAL_ISO_TIME`, `push on|off`. Run `tools/event-watch wait JOB --max-hours 6 --every 60` as a background task. A first scan establishes the baseline. `scan JOB` makes one pass; `list` shows configured rules. State paths can be overridden. Optional notification payloads contain event kinds and basenames, never matched log text.
- `pod-create-gate.py`: JSON-in capacity receipt hook. Defaults to audit mode. Configure eligible lanes and install the hook where pod creation occurs.
- `pod-deadline-gate.py`: command-text check for a bounded self-termination marker. It cannot validate a real provider deadline.
- `email-voice-gate.py`: JSON-in draft/send hook for configurable voice checks and exact approved body bytes. Configure enforce mode in the sender separately.

Hook payloads follow the `tool_name`/`tool_input` convention used by their hosting tool. Hook installation and scheduler activation depend on that tool and are deliberately manual. These files contain no notification service, contact records, provider credentials or loaded jobs.
