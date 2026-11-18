# LAN proxy

`lan-proxy` lets a machine's `tailscale serve` front a service that runs on another
machine on the same LAN, when that machine has no fixed address. Serve points at a
loopback port; the proxy resolves the target name (an mDNS `.local` name, say) on
every accepted connection and relays the bytes.

Why not point Serve at the name directly: Serve's HTTP handler pools upstream
connections, so a name is resolved when a connection opens, not per request, and the
macOS app warns that it cannot reach remote destinations on a non-default route.

## Relay

- Python 3.9+ standard library (asyncio streams). Listens on `127.0.0.1` unless `--listen-host` and `--allow` say otherwise.
- Calls `getaddrinfo` for every accepted connection and dials the numeric result,
  IPv4 first. No upstream pool, no address cache.
- Copies bytes unchanged: Host and Origin headers, uploads, streaming, WebSockets,
  half-closes. HTTPS terminates at Serve.
- One deadline (default 3 s) covers resolution and every connect attempt. On failure,
  an HTTP request gets 502 (refused) or 504 (deadline); other traffic gets EOF.
- An open connection stays with the peer it reached; the next one resolves again. It
  never replays writes.
- Defaults: 128 connections, 64 KiB chunks, four resolver threads, 120 s idle timeout.

## Two relays, one per machine

The service stays bound to loopback on its own machine, exactly as before the move.
A second `lan-proxy` there listens on the LAN and admits only the front machine:

```sh
# front machine (runs tailscale serve); serve points at 127.0.0.1:14325
lan-proxy --listen-port 14325 --target m5.local --target-port 14325
# service machine; the service itself stays on 127.0.0.1:4325
lan-proxy --listen-host 0.0.0.0 --listen-port 14325 --target 127.0.0.1 --target-port 4325 \
  --allow FRONT-MACHINE.local
```

Why the second hop: the service then sees a loopback peer, so whatever it already
trusts from a local TLS front (for example `X-Forwarded-Proto` from loopback only)
keeps working, and nothing that regenerates its launchd plist can undo a LAN bind.

`--allow NAME` (repeatable) admits loopback and whatever NAME resolves to. Answers are
cached for `--allow-ttl` seconds (default 30) and refreshed in the background; a failed
lookup keeps the last good set; a refused peer forces one fresh lookup, so a front
machine that just changed address gets in. A refused connection is closed before
anything is dialed. Listening beyond loopback without `--allow` is refused at startup.

The front machine's launchd agent is
[com.ricardo.lan-proxy.plist](../config/lan-proxy/com.ricardo.lan-proxy.plist)
(not loaded by anything here; installing it is an operator step).

## Optional: pf instead of --allow

[family-games.pf](../config/lan-proxy/family-games.pf) admits loopback and the table
`family_games_clients` to port 4325 and drops everything else, for a service bound to
all interfaces. `lan-proxy-pf-refresh --host NAME` (as root, from
[its LaunchDaemon](../config/lan-proxy/com.ricardo.family-games-pf-refresh.plist))
fills the table by name every 60 s, keeps the last good table when a lookup fails, and
never enables pf or loads rules. It needs root and a pf load after every reboot, which
is why `--allow` is the default.

## Health

`job-health` has an opt-in `lan_proxy` registry entry: the target must resolve inside
the home LAN, and `GET /api/config` through the relay must return 200 with a body.
Keys: `target`, `proxy_port`, `http_host` (a Host the service accepts), `timeout`, `label`.

Tests: `../tests/test_lan_proxy.py`, `../tests/test_job_health.py`.
