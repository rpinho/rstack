"""Local sockets only; no DNS, interface aliases, firewall or Serve changes."""
import asyncio
import importlib.machinery
import importlib.util
import logging
from pathlib import Path
import socket
import subprocess

import pytest

from rstack_hookcall import TOOLS


_CONNECT, _CONNECT_EX = socket.socket.connect, socket.socket.connect_ex


@pytest.fixture(autouse=True)
def local_sockets_only(no_internet, monkeypatch):
    # This spec explicitly requires local TCP integration. Keep the suite's ban
    # for every destination except the two literal loopbacks used below.
    def local_connect(self, address):
        assert address[0] in ('127.0.0.1', '::1'), 'external network remains disabled'
        return _CONNECT(self, address)

    def local_connect_ex(self, address):
        assert address[0] in ('127.0.0.1', '::1'), 'external network remains disabled'
        return _CONNECT_EX(self, address)

    monkeypatch.setattr(socket.socket, 'connect', local_connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', local_connect_ex)


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(TOOLS / filename))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


proxy = load('lan_proxy_test', 'lan-proxy')


async def stop(relay, server):
    server.close()
    await server.wait_closed()
    tasks = list(relay.active)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def test_new_connections_follow_address_change_preserving_http_and_tcp():
    async def scenario():
        requests = []

        def handler(identity):
            async def respond(reader, writer):
                try:
                    data = await reader.read(65536)
                    requests.append(data)
                    if data.startswith(b'GET '):
                        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\n' + identity)
                    else:
                        # Respond only after receiving EOF: prove TCP half-close works.
                        rest = await reader.read()
                        writer.write(identity + data + rest)
                    await writer.drain()
                finally:
                    await proxy.close_writer(writer)
            return respond

        first = await asyncio.start_server(handler(b'one'), '127.0.0.1', 0)
        port = first.sockets[0].getsockname()[1]
        second = await asyncio.start_server(handler(b'two'), '::1', port, family=socket.AF_INET6)
        resolved = [('127.0.0.1', socket.AF_INET)]
        calls = []

        async def resolver(host, requested_port, **kwargs):
            calls.append((host, requested_port))
            address, family = resolved[0]
            answers = [(family, socket.SOCK_STREAM, 6, '', (address, requested_port))]
            # Real mDNS may put AAAA first; use the hub's IPv4 A when available.
            if family == socket.AF_INET:
                answers.insert(0, (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', requested_port)))
            return answers

        relay = proxy.Proxy(port=port, resolver=resolver)
        server = await asyncio.start_server(relay.handle, '127.0.0.1', 0)
        relay_port = server.sockets[0].getsockname()[1]
        request = (b'GET /api/config HTTP/1.1\r\nHost: hub.example.ts.net\r\n'
                   b'Origin: https://hub.example.ts.net\r\nConnection: close\r\n\r\n')

        async def ask(data, half_close=False):
            reader, writer = await asyncio.open_connection('127.0.0.1', relay_port)
            writer.write(data)
            await writer.drain()
            if half_close:
                writer.write_eof()
            answer = await asyncio.wait_for(reader.read(), 2)
            await proxy.close_writer(writer)
            return answer

        try:
            assert (await ask(request)).endswith(b'one')
            resolved[0] = ('::1', socket.AF_INET6)
            assert (await ask(request)).endswith(b'two')
            binary = b'\x00\xff\x10raw TCP'
            assert await ask(binary, half_close=True) == b'two' + binary
            assert calls == [('m5.local', port)] * 3
            assert requests == [request, request, binary]
            health = load('lan_health_integration', 'job-health')
            assert await asyncio.to_thread(health.lan_proxy_problems,
                {'proxy_port': relay_port}, lambda host: ['192.168.86.135']) == []
            # The same real listener remains up; upstream failure must still alert.
            second.close()
            await second.wait_closed()
            rows = await asyncio.to_thread(health.lan_proxy_problems,
                {'proxy_port': relay_port}, lambda host: ['192.168.86.135'])
            assert rows[0][0] == 'lan-proxy-hub'
        finally:
            await stop(relay, server)
            first.close()
            second.close()
            await first.wait_closed()
            await second.wait_closed()

    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['connect-timeout', 'dns-timeout', 'refused'])
def test_failed_dial_is_bounded_and_http_gets_a_clean_error(failure, caplog):
    async def scenario():
        async def resolver(*args, **kwargs):
            if failure == 'dns-timeout':
                await asyncio.sleep(10)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 9))]

        async def connector(*args, **kwargs):
            if failure == 'refused':
                raise ConnectionRefusedError('test refusal')
            await asyncio.sleep(10)

        relay = proxy.Proxy(connect_timeout=.03, resolver=resolver, connector=connector)
        server = await asyncio.start_server(relay.handle, '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            writer.write(b'GET / HTTP/1.1\r\nHost: m5.local\r\n\r\n')
            await writer.drain()
            answer = await asyncio.wait_for(reader.read(), 1)
            assert answer.startswith(b'HTTP/1.1 502' if failure == 'refused' else b'HTTP/1.1 504')
            assert b'Connection: close' in answer
            await proxy.close_writer(writer)
        finally:
            await stop(relay, server)

    with caplog.at_level(logging.WARNING, logger='lan-proxy'):
        asyncio.run(scenario())
    assert 'failed:' in caplog.text
    assert 'Traceback' not in caplog.text


def test_server_first_tcp_and_idle_connection_are_supported():
    async def scenario():
        async def greet(reader, writer):
            writer.write(b'hello without client bytes')
            await writer.drain()
            await reader.read()
            await proxy.close_writer(writer)

        origin = await asyncio.start_server(greet, '127.0.0.1', 0)
        relay = proxy.Proxy('127.0.0.1', origin.sockets[0].getsockname()[1], idle_timeout=.1)
        server = await asyncio.start_server(relay.handle, '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            assert await asyncio.wait_for(reader.readexactly(26), 1) == b'hello without client bytes'
            assert await asyncio.wait_for(reader.read(), 1) == b''
            await proxy.close_writer(writer)
        finally:
            await stop(relay, server)
            origin.close()
            await origin.wait_closed()

    asyncio.run(scenario())


def test_pf_refresh_replaces_table_and_keeps_it_on_dns_failure():
    import sys
    sys.path.insert(0, str(TOOLS))
    pf = load('lan_pf_test', 'lan-proxy-pf-refresh')
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, '', '')

    def healthy(host):
        assert host == 'Ricardos-Mac-mini.local'
        return ['127.0.0.1', '192.168.1.20', '192.168.86.247']

    assert pf.refresh('Ricardos-Mac-mini.local', resolver=healthy, runner=runner) == 0
    assert calls[-1][1]['input'] == '192.168.86.247\n'
    assert '-T' in calls[-1][0] and 'replace' in calls[-1][0]
    assert pf.refresh('m4', resolver=lambda host: ['192.168.86.248'], runner=runner) == 0
    assert calls[-1][1]['input'] == '192.168.86.248\n'

    def unavailable(host):
        raise OSError('test mDNS failure')

    before = len(calls)
    assert pf.refresh('m4', resolver=unavailable, runner=runner) == 1
    assert pf.refresh('m4', resolver=lambda host: ['192.168.1.20'], runner=runner) == 1
    assert len(calls) == before
    assert pf.refresh('Ricardos-Mac-mini.local', dry=True, resolver=healthy, runner=runner) == 0
    assert len(calls) == before


def test_launchd_proposals_have_expected_shape():
    import plistlib
    proposals = TOOLS.parent / 'config/lan-proxy'
    agent = plistlib.loads((proposals / 'com.ricardo.lan-proxy.plist').read_bytes())
    assert agent['ProgramArguments'][0] == '/usr/bin/python3'
    assert agent['KeepAlive'] is True
    assert agent['StandardErrorPath'].endswith('/lan-proxy.log')
    daemon = plistlib.loads((proposals / 'com.ricardo.family-games-pf-refresh.plist').read_bytes())
    assert daemon['StartInterval'] == 60
    assert daemon['UserName'] == 'root'
