"""Grok Bot contract tests: fake HTTP/CDP only, isolated HOME and state."""
import base64
import contextlib
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
import time

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('grok_ask_under_test', TOOLS / '_grok_ask.py')
ask = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ask)
GOOD = 'Found:\n```json\n[{"post_id":"123", "text":"fixture"}]\n```'
SOCKET_CONNECT = socket.socket.connect


def read_n(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise EOFError
        result.extend(chunk)
    return bytes(result)


class FakeCDP:
    def __init__(self, answer=GOOD, busy=False, dom_error=False, ready=True):
        self.answer, self.busy, self.dom_error, self.ready = answer, busy, dom_error, ready
        self.actions, self.methods = [], []
        self.prompt = None
        self.on_send = None
        self.fragment = False
        self.wrong_target = False
        self.duplicate_target = False

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def frame(self, payload, first=0x81):
                size = len(payload)
                head = bytes([first, size]) if size < 126 else bytes([first, 126]) + struct.pack('!H', size)
                self.wfile.write(head + payload)
                self.wfile.flush()

            def do_GET(self):
                if self.path == '/json/list':
                    page = dict(type='page', title='Unrelated' if fake.wrong_target else 'Grok Bot',
                                url='app://grok', webSocketDebuggerUrl='ws://127.0.0.1:{}/devtools/page/test'.format(fake.port))
                    data = json.dumps([page, page] if fake.duplicate_target else [page]).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                assert self.path == '/devtools/page/test'
                key = self.headers['Sec-WebSocket-Key']
                accept = base64.b64encode(hashlib.sha1(
                    (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                self.send_response(101)
                self.send_header('Upgrade', 'websocket')
                self.send_header('Connection', 'Upgrade')
                self.send_header('Sec-WebSocket-Accept', accept)
                self.end_headers()
                self.wfile.flush()
                try:
                    while True:
                        first, second = read_n(self.rfile, 2)
                        assert second & 128, 'client websocket messages must be masked'
                        size = second & 127
                        if size == 126:
                            size = struct.unpack('!H', read_n(self.rfile, 2))[0]
                        elif size == 127:
                            size = struct.unpack('!Q', read_n(self.rfile, 8))[0]
                        mask = read_n(self.rfile, 4)
                        data = bytes(v ^ mask[i % 4] for i, v in enumerate(read_n(self.rfile, size)))
                        if first & 15 == 10:
                            continue
                        request = json.loads(data)
                        method, params = request['method'], request['params']
                        fake.methods.append(method)
                        reply = dict(id=request['id'], result={})
                        if method == 'Input.insertText':
                            fake.prompt = params['text']
                        elif method == 'Runtime.evaluate':
                            expression = params['expression']
                            action = re.search(r'grok-ask:(\w+)', expression)[1]
                            fake.actions.append(action)
                            value = True
                            if action == 'ready':
                                value = fake.ready
                            if action == 'send':
                                data = json.loads(re.search(r'const data = (.*?);\n', expression)[1])
                                assert data['prompt'] == fake.prompt
                                if fake.on_send:
                                    fake.on_send(fake.prompt)
                            if action == 'read':
                                if fake.dom_error:
                                    reply['result'] = dict(exceptionDetails=dict(text='fixture DOM failure'))
                                else:
                                    value = dict(text=fake.answer, busy=fake.busy, sent=True)
                            if 'exceptionDetails' not in reply['result']:
                                reply['result'] = dict(result=dict(type='object', value=value))
                        else:
                            assert method == 'Page.enable'
                        self.frame(b'{"method":"Runtime.consoleAPICalled","params":{}}')
                        encoded = json.dumps(reply).encode()
                        if fake.fragment:
                            cut = len(encoded) // 2
                            self.frame(encoded[:cut], 0x01)
                            self.frame(b'ping', 0x89)
                            self.frame(encoded[cut:], 0x80)
                        else:
                            self.frame(encoded)
                except (EOFError, ConnectionError, OSError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    def loopback_only(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] != '127.0.0.1':
            raise AssertionError('only the fake CDP loopback endpoint is permitted')
        return SOCKET_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', loopback_only)
    home = tmp_path / 'home'
    home.mkdir()
    config = tmp_path / 'config.json'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('GROK_ASK_CONFIG', str(config))
    monkeypatch.setenv('RSTACK_CALLER', 'fixture-caller')
    return tmp_path, config


def configure(isolated, port):
    isolated[1].write_text(json.dumps(dict(port=port, poll_seconds=0.02,
                                         settle_seconds=0.06, cache_settle_seconds=0.06,
                                         answer_quiet_seconds=0.2)))


def run(isolated, *args, timeout=8):
    return subprocess.run([sys.executable, str(TOOLS / 'grok-ask'), *args],
                          capture_output=True, text=True, timeout=timeout)


def ledger(isolated):
    return [json.loads(line) for line in (isolated[0] / 'state/grok-ask.jsonl').read_text().splitlines()]


def test_good_answer_new_chat_suffix_and_ledger(isolated):
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '3', 'fixture question')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [dict(post_id='123', text='fixture')]
    assert not result.stderr
    assert fake.actions[:4] == ['new', 'ready', 'focus', 'send']
    assert fake.prompt.startswith('fixture question\n\n' + ask.SUFFIX)
    assert 'Request ID:' in fake.prompt
    row = ledger(isolated)[0]
    assert row['host'] == 'local' and row['caller'] == 'fixture-caller'
    assert row['query_hash'] == hashlib.sha256(b'fixture question').hexdigest()
    assert row['rows_returned'] == 1 and row['seconds'] > 0
    assert dt_fromiso(row['utc']).utcoffset().total_seconds() == 0
    assert 'fixture question' not in json.dumps(row)


def dt_fromiso(value):
    import datetime
    return datetime.datetime.fromisoformat(value)


@pytest.mark.parametrize('answer, diagnostic', [
    ('Nothing here.', 'expected exactly one'),
    ('```json\n[broken]\n```', 'bad JSON'),
    ('```json\n{}\n```', 'array of objects'),
    ('```json\n[1]\n```', 'array of objects'),
    ('```json\n[]\n```\n```json\n[]\n```', 'exactly one'),
    ('```json\n[{"x":NaN}]\n```', 'bad JSON'),
])
def test_invalid_answers_exit_three_with_raw_stderr(isolated, answer, diagnostic):
    with FakeCDP(answer) as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '3', 'question')
    assert result.returncode == 3 and not result.stdout
    assert diagnostic in result.stderr and answer in result.stderr
    assert ledger(isolated)[0]['exit_code'] == 3


def test_busy_answer_times_out_with_partial_raw_answer(isolated):
    with FakeCDP('partial fixture answer', busy=True) as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '0.4', 'question')
    assert result.returncode == 3 and not result.stdout
    assert 'timeout' in result.stderr and 'partial fixture answer' in result.stderr
    assert ledger(isolated)[0]['rows_returned'] == 0


def test_missing_endpoint_does_not_start_or_quit_app(isolated, monkeypatch, capsys):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    configure(isolated, port)
    monkeypatch.setattr(ask, 'app_command', lambda *a: pytest.fail('live app command'))
    assert ask.main(['--timeout', '0.3', 'question']) == 3
    result = capsys.readouterr()
    assert not result.out
    assert 'endpoint unavailable' in result.err and '--remote-debugging-port=' in result.err
    assert len(ledger(isolated)) == 1


def test_lock_contention_uses_timeout_and_does_not_send(isolated):
    state = isolated[0] / 'state'
    state.mkdir()
    name = hashlib.sha256(b'local').hexdigest()[:24]
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        with (state / ('grok-ask-' + name + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = run(isolated, '--host', 'localhost', '--timeout', '0.15', 'question')
    assert not fake.methods
    assert result.returncode == 3 and not result.stdout
    assert 'host lock' in result.stderr
    assert ledger(isolated)[0]['host'] == 'local'


@pytest.mark.parametrize('schema', [['url'], {'required': ['url']},
                                    {'type': 'array', 'items': {'required': ['url']}}])
def test_schema_miss_and_prompt(isolated, schema):
    path = isolated[0] / 'schema.json'
    path.write_text(json.dumps(schema))
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--schema', str(path), '--timeout', '3', 'question')
    assert result.returncode == 3
    assert 'schema miss' in result.stderr and GOOD in result.stderr
    assert 'Every object must include these keys: ["url"]' in fake.prompt


def test_empty_answer_and_fragmented_websocket_with_ping(isolated):
    with FakeCDP('```json\n[]\n```') as fake:
        fake.fragment = True
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '3', 'question')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert ledger(isolated)[0]['rows_returned'] == 0


def test_existing_chat_never_receives_query(isolated):
    with FakeCDP(ready=False) as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '0.25', 'question')
    assert result.returncode == 3
    assert fake.prompt is None and 'send' not in fake.actions


@pytest.mark.parametrize('attribute', ['wrong_target', 'duplicate_target'])
def test_refuse_wrong_or_ambiguous_page(isolated, attribute):
    with FakeCDP() as fake:
        setattr(fake, attribute, True)
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '1', 'question')
    assert result.returncode == 3 and 'expected one Grok page' in result.stderr
    assert not fake.actions


def blob(directory, name, messages, nested=True):
    directory.mkdir(parents=True, exist_ok=True)
    filename = base64.b32encode(name.encode()).decode().rstrip('=').lower() + '.blob'
    value = dict(entries=[dict(timestampMs=ts, message=dict(content=text)) for ts, text in messages])
    (directory / filename).write_text(json.dumps(dict(value=json.dumps(value) if nested else value)))


def test_cache_decoder_fallback_correlates_this_prompt_only(isolated):
    cache = Path(os.environ['HOME']) / ask.CACHE
    now = time.time() * 1000
    blob(cache, 'old.transcript.replicas.other', [(now, '```json\n[{"stale":true}]\n```')])
    with FakeCDP(dom_error=True) as fake:
        def save(prompt):
            ts = 1000  # A remote clock need not match the controller; the prompt ID does.
            blob(cache, 'new.transcript.replicas.fixture', [(ts, prompt), (ts + 1, GOOD)])
        fake.on_send = save
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '3', 'question')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]['post_id'] == '123'


def test_cache_refuses_unrelated_fresh_routine(isolated):
    cache = Path(os.environ['HOME']) / ask.CACHE
    blob(cache, 'old.transcript.replicas.other', [(time.time() * 1000, GOOD)], nested=False)
    with FakeCDP(dom_error=True) as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--timeout', '0.3', 'question')
    assert result.returncode == 3 and not result.stdout
    assert 'timeout' in result.stderr


def test_remote_cache_copy_streams_only_blobs_and_reuses_decoder(isolated, monkeypatch):
    filename = base64.b32encode(b'fixture.transcript.replicas.remote').decode().rstrip('=') + '.blob'
    value = dict(entries=[dict(timestampMs=1, message=dict(content='fixture answer'))])
    payload = json.dumps(dict(value=json.dumps(value))).encode()
    cache = Path(os.environ['HOME']) / ask.CACHE
    cache.mkdir(parents=True)
    (cache / filename).write_bytes(payload)
    (cache / 'omit.txt').write_text('synthetic non-blob')
    real_popen = subprocess.Popen
    def popen(argv, **kwargs):
        assert argv[:5] == ['ssh', '-T', '-o', 'BatchMode=yes', 'fixture-host']
        assert "find . -type f -name '*.blob' -print0" in argv[-1]
        return real_popen(['/bin/sh', '-c', argv[-1]], **kwargs)
    monkeypatch.setattr(ask.subprocess, 'Popen', popen)
    destination = isolated[0] / 'copied'
    destination.mkdir()
    ask.copy_cache(destination, 'fixture-host', time.monotonic() + 3)
    assert [p.name for p in destination.iterdir()] == [filename]
    assert list(ask.entries(destination)) == [(filename, 1, 'fixture answer')]


def test_explicit_relaunch_restores_normal_app_on_timeout(isolated, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(ask, 'app_command', lambda host, argv, deadline: calls.append((host, argv)))
    monkeypatch.setattr(ask, 'pause', lambda deadline, seconds: None)
    with FakeCDP(busy=True) as fake:
        configure(isolated, fake.port)
        assert ask.main(['--relaunch', '--timeout', '0.2', 'question']) == 3
    capsys.readouterr()
    assert [args[0] for _, args in calls] == ['osascript', 'open', 'osascript', 'open']
    assert '--remote-debugging-address=127.0.0.1' in calls[1][1]
    assert calls[-1] == ('local', ['open', '-a', 'Grok Bot'])


def test_prompt_strings_are_data_not_javascript_substitutions():
    prompt = 'CONFIG PROMPT ACTION "quote"\n`code` ${value}'
    expression = ask.js({}, 'send', prompt)
    value = json.loads(re.search(r'const data = (.*?);\n', expression)[1])
    assert value['prompt'] == prompt


def test_json_strings_can_contain_markdown_backticks():
    rows = [dict(text='A post with ```python\\nprint(1)\\n``` in it')]
    raw = 'Found:\n```json\n' + json.dumps(rows) + '\n```\n'
    assert ask.parse_answer(raw, ['text']) == rows


def test_remote_host_uses_loopback_ssh_tunnel_and_cleans_up(isolated, monkeypatch):
    stub = isolated[0] / 'ssh'
    calls = isolated[0] / 'ssh-calls'
    stub.write_text('#!' + sys.executable + '\n' + '''
import json, os, select, socket, sys, threading
with open(os.environ['SSH_CALLS'], 'w') as out:
    json.dump(sys.argv[1:], out)
assert sys.argv[-1] == 'fixture-host'
assert '-N' in sys.argv and 'ExitOnForwardFailure=yes' in sys.argv
forward = sys.argv[sys.argv.index('-L') + 1].split(':')
assert forward[0] == forward[2] == '127.0.0.1'
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', int(forward[1])))
listener.listen()
def bridge(client):
    try:
        with client, socket.create_connection(('127.0.0.1', int(forward[3]))) as target:
            while True:
                ready, _, _ = select.select([client, target], [], [], 5)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    (target if source is client else client).sendall(data)
    except OSError:
        pass
while True:
    client, _ = listener.accept()
    threading.Thread(target=bridge, args=(client,), daemon=True).start()
''')
    stub.chmod(0o755)
    monkeypatch.setenv('PATH', str(isolated[0]) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('SSH_CALLS', str(calls))
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        result = run(isolated, '--host', 'fixture-host', '--timeout', '4', 'question')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]['post_id'] == '123'
    argv = json.loads(calls.read_text())
    forward = argv[argv.index('-L') + 1].split(':')
    with socket.socket() as probe:
        with pytest.raises(OSError):
            probe.connect(('127.0.0.1', int(forward[1])))
    assert ledger(isolated)[0]['host'] == 'fixture-host'


def test_waits_for_stream_to_finish_even_when_json_is_already_valid(isolated):
    with FakeCDP(busy=True) as fake:
        configure(isolated, fake.port)
        def finish():
            time.sleep(0.25)
            fake.answer = '```json\n[{"final":true}]\n```'
            fake.busy = False
        threading.Thread(target=finish, daemon=True).start()
        result = run(isolated, '--timeout', '3', 'question')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [dict(final=True)]


def test_explicit_relaunch_restores_normal_app_on_success(isolated, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(ask, 'app_command', lambda host, argv, deadline: calls.append(argv))
    real_pause = ask.pause
    monkeypatch.setattr(ask, 'pause', lambda deadline, seconds: real_pause(deadline, min(seconds, 0.02)))
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        assert ask.main(['--relaunch', '--timeout', '3', 'question']) == 0
    result = capsys.readouterr()
    assert json.loads(result.out)[0]['post_id'] == '123'
    assert [argv[0] for argv in calls] == ['osascript', 'open', 'osascript', 'open']
    assert calls[-1] == ['open', '-a', 'Grok Bot']


def test_relaunch_restoration_failure_is_not_reported_as_success(isolated, monkeypatch, capsys):
    calls = []
    def command(host, argv, deadline):
        calls.append(argv)
        if len(calls) == 4:
            raise ask.AskError('fixture restore failed')
    monkeypatch.setattr(ask, 'app_command', command)
    real_pause = ask.pause
    monkeypatch.setattr(ask, 'pause', lambda deadline, seconds: real_pause(deadline, min(seconds, 0.02)))
    with FakeCDP() as fake:
        configure(isolated, fake.port)
        assert ask.main(['--relaunch', '--timeout', '3', 'question']) == 3
    result = capsys.readouterr()
    assert not result.out and 'fixture restore failed' in result.err
    assert ledger(isolated)[0]['exit_code'] == 3


@pytest.mark.parametrize('schema', [dict(items=[]), dict(properties=[]), dict(required='url')])
def test_malformed_schema_fails_cleanly_and_is_logged(isolated, schema):
    path = isolated[0] / 'schema.json'
    path.write_text(json.dumps(schema))
    result = run(isolated, '--schema', str(path), 'question')
    assert result.returncode == 3 and 'schema' in result.stderr
    assert 'Traceback' not in result.stderr
    assert len(ledger(isolated)) == 1


def test_a_rendered_answer_without_fences_still_parses_one_array():
    """11-15 live: the app renders the code block, so the page text holds the JSON but no ``` fences."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('ga_live', str(TOOLS / '_grok_ask.py'))
    ga = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ga)
    assert ga.parse_answer('Queries\n[{"a": [1, 2], "b": "x"}, {"a": []}]', ['a']) == [{'a': [1, 2], 'b': 'x'}, {'a': []}]
    for bad in ('Searching X posts', 'Queries\n[{"a": 1}] and [{"b": 2}]'):
        with pytest.raises(ga.AskError):
            ga.parse_answer(bad, [])


def test_progress_text_counts_as_busy():
    """11-15 digest: 'Queries is typing / Typing…' was returned as the answer (exit 3, no JSON)."""
    import re as _re
    src = (TOOLS / '_grok_ask.py').read_text()
    assert 'is typing|Typing…' in src
    assert _re.search(r'is typing|Typing…|Typing\.\.\.|Searching X posts|Searching the web', 'Queries is typing\nTyping…')
