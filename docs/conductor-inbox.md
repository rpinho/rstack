# The conductor is woken by scripts, never by peers

Every wake replays the conductor's context. In one measured day, peer messages
accounted for about a third of model usage. That observation motivates batching;
it is not a prediction of savings for every deployment.

A request to “message less” is easy to forget. Prefer the enforcement hierarchy:
architecture, compiler checks, CI/lint, bot rules, then prose. This inbox moves
the wake decision into scripts: peers file messages, a tool-boundary hook denies
direct conductor messages, and a background watcher wakes the conductor only
when an escalation marker appears. Routine status stays in each peer's handoff.

## Install for the current conductor

Requires Python 3.9+, a POSIX shell, `ps`, and a local CLI exposing Unix sockets
named `<pid>.sock` (by default under `/tmp/cc-socks`). Run from the repository:

```sh
export PATH="$PWD/tools:$HOME/.local/bin:$PATH"
harness/tools/conductor-inbox/install-conductor-inbox.sh
```

The installer walks its ancestors and selects the nearest process with a socket.
It checks that the path is a Unix socket; it does not verify the process's identity.
Alternatively pass the conductor's PID as the single argument. Set
`CONDUCTOR_SOCKET_DIR` if the CLI uses another directory. A CLI with a different
transport needs an adapter; this is not a universal agent messaging interface.

Installation creates the inbox, links `tell-conductor` and the compatibility alias
`tell-general` into `$HOME/.local/bin`, links the gate into `$HOME/.claude/hooks`,
and merges a `SendMessage` PreToolUse hook into `$HOME/.claude/settings.json`.
Unrelated settings/hooks are retained. Existing unrelated files at link destinations
are refused. Nothing is installed or started merely by cloning the repository.

It records the socket in `conductor.addr`, writes the `conductor-inbox` watcher
rule, establishes the watcher's baseline, and pipe-tests denial by name and address.
The printed exports must be set in both conductor and peer shells. Installed hook
configuration embeds the selected state directory and conductor name, so the hook
does not depend on the peer's environment. Restart peer CLI sessions if their host
only loads hook settings at startup. The repository must remain at its installed
location because the installed commands are symlinks.

**Re-run the installer from the new conductor session after every restart**, or
pass its new PID. The socket changes on restart. Reinstallation updates the
address and existing inbox hook without duplicating it or clearing the inbox.
Restart/re-arm the background watcher with the printed exports as well.

## Configure

| Variable | Default / meaning |
|---|---|
| `CONDUCTOR_INBOX_DIR` | `$XDG_STATE_HOME/conductor-inbox`, or `$HOME/.local/state/conductor-inbox`; use an absolute path shared by peers and conductor. |
| `CONDUCTOR_NAME` | `conductor`; exact name denied by the hook, also when followed by a display annotation. |
| `CONDUCTOR_HUMAN_KIND` | `human`; optional additional escalation keyword for compatibility with a local caller's terminology. The public `human` spelling always works. |
| `CONDUCTOR_SOCKET_DIR` | `/tmp/cc-socks`; installer socket discovery only. |
| `CONDUCTOR_QUARANTINE_TERMS` | Unset: nothing is quarantined. A file of terms, one per line (`#` comments). A message matching one is kept out of the conductor's context: the full text goes to `quarantine/` under the inbox (mode 600) and the row carries the sender's `--summary`, the path and a count of matched terms, never the terms. The kind is kept, so a wake still happens. A configured file that cannot be read quarantines every message. |
| `CONDUCTOR_HOST`, `CONDUCTOR_REMOTE_COMMAND`, `CONDUCTOR_SSH` | Unset: file here. An ssh alias: hand each message to `tell-conductor` on that machine (default command `~/.local/bin/tell-conductor`) with the same kind, sender and summary, for peers on a machine whose inbox the conductor does not read. An unreachable host is an error, never a silent local filing. |
| `EVENT_WATCH_CONF` | Installer defaults to `$HOME/.config/event-watch`. Export the printed value: the repository watcher itself otherwise defaults to `.runtime/event-watch/config`. |
| `EVENT_WATCH_STATE` | Installer defaults to `$XDG_STATE_HOME/event-watch` or `$HOME/.local/state/event-watch`. Export it to share the installer's baseline; the watcher itself otherwise uses `.runtime/event-watch/state`. |
| `CLAUDE_SESSION_NAME` | Default sender; falls back to the current directory basename. Override with `--from NAME`. |

Choose a unique state directory for each conductor. All participants must use the
same settings; a single installation protects one conductor at a time.

## Peers file; the conductor batches

```sh
tell-conductor fyi "A result is ready; details are in my handoff."
tell-conductor decision "Two approaches remain; choose which to fund next."
tell-conductor human "An operator approval is needed."
tell-conductor break "A dependency is blocking all workers."
```

Every command appends one UTF-8 JSON row (`utc`, `from`, `kind`, `text`, plus
`quarantined` and `quarantine_match_count` for a quarantined message) to
`inbox.jsonl`. Pass `--summary "what is needed, from whom, where the detail lives"`
with anything that might be quarantined, so the conductor can act on the pointer. `fyi` creates no wake file. `decision`, `human`, the configured
human alias, and `break` also create a unique file under `wake/`. The first 200
characters are copied into the marker. Scripts never send a peer message or
connect to the socket. The gate denies the configured conductor name and recorded
address, with or without `uds:` and with display annotations; other targets and
other tool types pass through. Messages from the conductor to peers pass through.

The conductor first reads its backlog, then runs this as a **background shell
task** whose completion notification wakes the session:

```sh
event-watch wait conductor-inbox --max-hours 12
```

On completion, read all rows since the last processed row, handle the batch,
persist that row offset in conductor-owned state, and re-arm the wait. The watcher
tracks wake files, not the inbox read offset. On startup/restart, always drain the
backlog before waiting, including existing wake files and FYIs. The installer
baselines existing markers, and never treats them as new work. A `quiet` timeout
also completes the wait: inspect the batch and re-arm. Do not delete wake markers
while a watcher is active; archive processed state to Trash during coordinated
maintenance and re-baseline before resuming.

## Limits

The PreToolUse boundary enforces this policy only in a host that honors these
hooks. A different messaging tool, an unconfigured peer or direct socket access
can bypass it. Peers can also misclassify routine updates as escalations. Keep the
inbox local and access-controlled; it contains message text. This port does not
add a service, automatic inbox acknowledgement, retention policy, user approvals
or a background process. The CLI writes a durable inbox row before its marker;
if marker creation fails, the row remains for the next backlog read.
