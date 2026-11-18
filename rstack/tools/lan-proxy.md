# LAN proxy

`lan-proxy` lets a machine's `tailscale serve` front a service that runs on another
machine on the same LAN, when that machine has no fixed address. Serve points at a
loopback port; the proxy resolves the target name (an mDNS `.local` name, say) on
every accepted connection and relays the bytes.

Why not point Serve at the name directly: Serve's HTTP handler pools upstream
connections, so a name is resolved when a connection opens, not per request, and the
macOS app warns that it cannot reach remote destinations on a non-default route.

## Relay

- Python 3.9+ standard library (asyncio streams). Listens only on `127.0.0.1`.
- Calls `getaddrinfo` for every accepted connection and dials the numeric result,
  IPv4 first. No upstream pool, no address cache.
- Copies bytes unchanged: Host and Origin headers, uploads, streaming, WebSockets,
  half-closes. HTTPS terminates at Serve.
- One deadline (default 3 s) covers resolution and every connect attempt. On failure,
  an HTTP request gets 502 (refused) or 504 (deadline); other traffic gets EOF.
- An open connection stays with the peer it reached; the next one resolves again. It
  never replays writes.
- Defaults: 128 connections, 64 KiB chunks, four resolver threads, 120 s idle timeout.

```sh
lan-proxy --listen-port 14325 --target m5.local --target-port 4325 --log ~/Library/Logs/lan-proxy.log
```

The launchd agent is [com.ricardo.lan-proxy.plist](../config/lan-proxy/com.ricardo.lan-proxy.plist)
(not loaded by anything here; installing it is an operator step).

## Inbound limit on the target

The target service binds all interfaces, so the limit is a pf anchor,
[family-games.pf](../config/lan-proxy/family-games.pf): loopback and the addresses in
the table `family_games_clients` may reach the port; everything else is dropped. The
table starts empty.

`lan-proxy-pf-refresh --host NAME` resolves the proxy machine by name every 60 s (as
root, from [its LaunchDaemon](../config/lan-proxy/com.ricardo.family-games-pf-refresh.plist)),
keeps the usable IPv4s in the home LAN (`_lan.LAN`) and replaces the table. A failed
lookup leaves the last good table in place and exits 1, so an mDNS blip does not cut
clients off; the next good lookup replaces it. `--dry` resolves and prints only.

It never enables pf or loads rules. The anchor load is runtime-only: after a reboot,
load it again before relying on the limit.

## Health

`job-health` has an opt-in `lan_proxy` registry entry: the target must resolve inside
the home LAN, and `GET /api/config` through the relay must return 200 with a body.
Keys: `target`, `proxy_port`, `http_host` (a Host the service accepts), `timeout`, `label`.

Tests: `../tests/test_lan_proxy.py`, `../tests/test_job_health.py`.
