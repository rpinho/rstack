# Optional local science daemon client

`cs.py` is an unofficial HTTP client for a separately installed local daemon. The core harness and tests do not require that service. API changes may break it.

`CS_BASE` selects a URL; otherwise the client asks `CS_BIN status` for the live port. There is no default port: the daemon does not keep one across restarts, so a client that assumed one reported a refused connection instead of a stopped daemon. When no port can be read the client exits and says so.

`CS_STATE` stores its private cookie jar with restricted permissions. `CS_AUTO_READ` is a path-separated list of explicitly approved roots; it defaults to empty. The client can automatically approve local execution prompts; other prompt types require review. Check its approval logic before using it with an untrusted project.

## Driving an instance on another machine

The daemon reads the filesystem of the machine it runs on, so when the data and compute live on another host, the instance that reviews them has to be the one there. Set `CS_HOST` to an ssh alias for that host. The client then asks that machine's CLI for its live port, forwards it over ssh, and talks to the local end of that tunnel; `CS_REMOTE_BIN` is the CLI's path on the host (the remote shell expands a leading `~`), and `CS_TUNNEL_PORT` is the local port to forward to, which must not be the port of an instance on this machine.

Three consequences, each from a failure rather than from caution:

- The tunnel is bound to `127.0.0.1`, not `localhost`, and the cookie jar is named per host. Cookies ignore the port, so a session minted against `localhost:<tunnel>` otherwise overwrites the session of a local instance on `localhost:<its port>`, and the client silently drives the wrong account.
- `CS_AUTO_READ` is configured on the controller but names paths on the host. Before granting a read-only host prompt the client checks that the target exists there, and holds the prompt when it is missing or cannot be checked. A review that read nothing otherwise looks like a review that found nothing.
- `CS_HOST` must be a plain ssh alias. A value carrying ssh options or shell metacharacters is refused.

Models follow an explicit option, the calling session's model when supplied, or the lane's `claude_science_model`. A legacy banned-model set remains in `rh.py`; edit that policy for your deployment. No project IDs, session IDs, cookies or model account data are included.

A lane may enable `claude_science_required` to require a review URL before promotion. Promoting an idea sourced from this service requires an independent-check description. Those strings are receipts, not proof of an independent replication. Reopen primary sources and verify numbers outside the producing session.

```sh
python3 harness/cs.py projects
python3 harness/cs.py status SESSION
python3 harness/cs.py read SESSION
```

Other commands can create, edit, approve or cancel remote sessions; only run them under explicit authorization. These examples are documentation, not configured sessions.
