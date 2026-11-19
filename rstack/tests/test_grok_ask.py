"""Grok Bot contract tests: fake HTTP/CDP only, isolated HOME and state."""
import base64
import contextlib
import datetime as dt
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
        self.missing_bot = False
        self.sent_prompts = []
        self.syndication = None
        self.http_requests = []
        self.events = []
        # Draft-card path (11-19 live shape): a card appears after the prompt; pressing its primary
        # button posts, and Grok's next message carries the posted URL.
        self.card = None
        self.permission_first = False
        self.permission_after_press = False
        self.after_text = 'Posted: https://x.com/fixture_account/status/9001'
        self.pressed = []

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
                if self.path.startswith('/tweet-result?'):
                    fake.http_requests.append(self.path)
                    fake.events.append('syndication')
                    data = json.dumps(fake.syndication).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
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
                            if action == 'new' and fake.missing_bot:
                                reply['result'] = dict(exceptionDetails=dict(text='bot not found in the sidebar'))
                            if action == 'snapshot':
                                value = dict(users=len(fake.sent_prompts), assistants=len(fake.sent_prompts))
                            if action == 'send':
                                data = json.loads(re.search(r'const data = (.*?);\n', expression)[1])
                                assert data['prompt'] == fake.prompt
                                fake.sent_prompts.append(fake.prompt)
                                if fake.on_send:
                                    fake.on_send(fake.prompt)
                            if action in ('card_count', 'card_n'):
                                value = 0
                            if action == 'card_read':
                                value = dict(cards=0, permission=None)
                                if fake.sent_prompts and fake.permission_first:
                                    value['permission'] = 'Allow Posts to send from X?'
                                elif fake.sent_prompts and fake.card is not None:
                                    value = dict(fake.card, cards=1, card='draft-reply',
                                                 permission='Allow Posts to send from X?' if (
                                                     fake.permission_after_press and fake.pressed) else None)
                            if action == 'card_press':
                                which = json.loads(re.search(r'const data = (.*?);\n', expression)[1])['arg']['which']
                                fake.pressed.append(which)
                                fake.events.append('press-' + which)
                                value = 'Reply' if which == 'send' else 'Discard'
                            if action == 'card_allow':
                                fake.events.append('allow')
                                value = 'allowed: Allow'
                            if action == 'card_after':
                                value = fake.after_text if 'send' in fake.pressed else ''
                            if action in ('read', 'post_read'):
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

# grok-post uses the same fake CDP transport, with an additional HTTP syndication stub.
@pytest.fixture
def posting(isolated, monkeypatch):
    folder, config = isolated
    root = folder / 'rh-root'
    lane = root / 'lanes/fixture'
    lane.mkdir(parents=True)
    monkeypatch.setenv('RH_ENV_FILE', str(folder / 'no-env-file'))
    monkeypatch.setenv('RH_DRAFT_ARCHIVE', str(folder / 'draft-archive'))
    monkeypatch.setenv('RH_X_REPLIED', str(folder / 'replied.json'))
    (folder / 'replied.json').write_text('[]')
    text = 'A fixed sample has three distinct periods.\nThe approved text stays exact.\n'
    draft = folder / 'draft.txt'
    draft.write_bytes(text.encode())
    digest = hashlib.sha256(draft.read_bytes()).hexdigest()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    row = dict(id='o1', lane='fixture', status='approved', channel='x_post',
               to_key='@fixture_account', purpose='Share measured periods',
               draft_path=str(draft), draft_sha256=digest,
               approval=dict(utc=now, by='owner', quote='Send these exact words', sha256=digest),
               lint=dict(ok=True, sha256=digest))
    ledger_path = lane / 'OUTREACH.jsonl'
    sent_log, page_log = folder / 'rh-calls.json', folder / 'pages.json'
    rh_stub, notify_stub = folder / 'rh-stub.py', folder / 'notify-stub.py'
    rh_stub.write_text('''import json,sys
from pathlib import Path
root = Path(sys.argv[sys.argv.index('--root')+1])
assert sys.argv[sys.argv.index('outreach')+1] == 'sent'
lane, ident = sys.argv[sys.argv.index('sent')+1:sys.argv.index('sent')+3]
p = root/'lanes'/lane/'OUTREACH.jsonl'
row = [json.loads(s) for s in p.read_text().splitlines()][-1]
assert row['id'] == ident and row['status'] == 'approved' and row['gate_attempt']['path'] == 'grok-post'
row.update(status='sent',sent={'message_id':sys.argv[sys.argv.index('--message-id')+1],'via':'grok'})
with p.open('a') as f: f.write(json.dumps(row)+'\\n')
Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))
''')
    notify_stub.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
    post_config = folder / 'grok-post.json'
    monkeypatch.setenv('GROK_POST_CONFIG', str(post_config))
    options = dict(post_account='fixture_account', post_host='local', rh_root=str(root),
                   rh_command=[sys.executable, str(rh_stub), str(sent_log)],
                   notify_command=[sys.executable, str(notify_stub), str(page_log)],
                   ledger_path=str(folder / 'post-ledger.jsonl'))

    class Posting:
        def setup(self, fake):
            configure(isolated, fake.port)
            options['syndication_url'] = 'http://127.0.0.1:{}/tweet-result'.format(fake.port)
            self.save()
            fake.syndication = dict(id_str='9001', text=text,
                                    user=dict(screen_name='fixture_account'))
            def answer(prompt):
                fake.events.append(prompt if prompt in ('send', 'cancel, do not send') else 'draft')
                if prompt == 'send':
                    fake.answer = json.dumps([dict(status='sent', id='9001',
                        posted_url='https://x.com/fixture_account/status/9001',
                        account='fixture_account', recipient=row['to_key'])])
                elif prompt == 'cancel, do not send':
                    fake.answer = '[{"status":"cancelled"}]'
                else:
                    fake.answer = json.dumps([dict(draft=self.returned_draft)])
            fake.on_send = answer
        def save(self):
            post_config.write_text(json.dumps(options))
            ledger_path.write_text(json.dumps(row) + '\n')
        def run(self, *args):
            return subprocess.run([sys.executable, str(TOOLS / 'grok-post'), '--rh', 'fixture/o1',
                '--text-file', str(draft), '--timeout', '3', *args], capture_output=True, text=True, timeout=8)
        def records(self):
            return [json.loads(s) for s in (folder / 'post-ledger.jsonl').read_text().splitlines()]
    p = Posting()
    p.row, p.text, p.draft, p.options = row, text, draft, options
    p.sent_log, p.page_log, p.ledger_path = sent_log, page_log, ledger_path
    p.returned_draft = text
    return p


def test_post_exact_draft_send_verify_and_rh_receipt(posting, isolated):
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--post')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'send', 'syndication']
    assert fake.http_requests == ['/tweet-result?id=9001&token=x']
    assert 'Do not compose' in fake.sent_prompts[0] and posting.text in fake.sent_prompts[0]
    assert fake.sent_prompts[1] == 'send'
    args = json.loads(posting.sent_log.read_text())
    assert args[-8:] == ['outreach', 'sent', 'fixture', 'o1', '--message-id', '9001', '--via', 'grok']
    record = posting.records()[-1]
    assert record['rh_id'] == 'fixture/o1' and record['posted_id'] == '9001'
    assert record['verified_fields']['author_screen_name'] == 'fixture_account'
    assert 'Verified:' in result.stdout and not posting.page_log.exists()


@pytest.mark.parametrize('draft', ['changed character', 'trailing space', 'unicode', 'invalid json'])
def test_post_changed_draft_cancels_exit_four(posting, draft):
    posting.returned_draft = {'changed character': posting.text.replace('fixed', 'mixed'),
                             'trailing space': posting.text + ' ',
                             'unicode': posting.text.replace('periods', 'périods')}.get(draft)
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--post')
    assert result.returncode == 4, result.stderr
    assert fake.events == ['draft', 'cancel, do not send']
    assert not posting.sent_log.exists() and not fake.http_requests
    record = posting.records()[-1]
    assert record['cancelled'] and record['diff'] and record['draft_response']


@pytest.mark.parametrize('change', ['unapproved', 'sent', 'hash', 'text', 'expired', 'future',
                                    'recipient', 'channel', 'attempt', 'target'])
def test_post_refuses_bad_rh_before_cdp(posting, change):
    with FakeCDP() as fake:
        posting.setup(fake)
        args = ['--post']
        if change == 'unapproved': posting.row['status'] = 'linted'
        if change == 'sent': posting.row['sent'] = dict(message_id='old')
        if change == 'hash': posting.row['approval']['sha256'] = '0' * 64
        if change == 'text': posting.row['text'] = 'different row text'
        if change in ('expired', 'future'):
            delta = dt.timedelta(hours=-49 if change == 'expired' else 1)
            posting.row['approval']['utc'] = (dt.datetime.now(
                dt.timezone.utc) + delta).isoformat()
        if change == 'recipient':
            posting.row.update(channel='x_dm', to_key='@different')
            args = ['--dm', 'fixture_recipient']
        if change == 'channel': posting.row['channel'] = 'email'
        if change == 'attempt': posting.row['gate_attempt'] = dict(path='previous')
        if change == 'target':
            posting.row.update(channel='x_reply', in_reply_to='https://x.com/fixture_target/status/12')
            args = ['--reply-to', 'https://x.com/fixture_target/status/13']
        posting.save()
        result = posting.run(*args)
    assert result.returncode == 2, result.stderr
    assert not fake.methods and not posting.sent_log.exists()


@pytest.mark.parametrize('change', ['author', 'reply', 'text', 'id', 'endpoint', 'malformed'])
def test_post_bad_public_verification_exit_five_and_pages(posting, change):
    posting.row.update(channel='x_reply', in_reply_to='https://x.com/fixture_target/status/12')
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.syndication['in_reply_to_status_id_str'] = '12'
        if change == 'author': fake.syndication['user']['screen_name'] = 'wrong_account'
        if change == 'reply': fake.syndication['in_reply_to_status_id_str'] = '13'
        if change == 'text': fake.syndication['text'] += 'changed'
        if change == 'id': fake.syndication['id_str'] = '9002'
        if change == 'endpoint': fake.syndication = {}
        if change == 'malformed': fake.syndication = None
        result = posting.run('--reply-to', posting.row['in_reply_to'])
    assert result.returncode == 5, result.stderr
    assert fake.events == ['draft', 'send', 'syndication']
    assert not posting.sent_log.exists()
    assert 'verification failed' in posting.page_log.read_text()
    assert posting.records()[-1]['exit_code'] == 5
    row = json.loads(posting.ledger_path.read_text().splitlines()[-1])
    assert row['status'] == 'approved' and row['gate_attempt']['path'] == 'grok-post'
    # An ambiguous outcome remains single use.
    with FakeCDP() as retry:
        configure((None, Path(os.environ['GROK_ASK_CONFIG'])), retry.port)
        again = posting.run('--reply-to', posting.row['in_reply_to'])
    assert again.returncode == 2 and not retry.sent_prompts


def test_post_reply_verified(posting):
    posting.row.update(channel='x_reply', in_reply_to='https://x.com/fixture_target/status/12')
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.syndication['in_reply_to_status_id_str'] = '12'
        result = posting.run('--reply-to', posting.row['in_reply_to'])
    assert result.returncode == 0, result.stderr
    assert posting.records()[-1]['verified_fields']['in_reply_to_status_id_str'] == '12'


def test_link_self_reply_row_posts_with_reply_to_its_own_post(posting):
    posting.row.update(channel='x_post', self_reply_to='12')
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.syndication['in_reply_to_status_id_str'] = '12'
        result = posting.run('--reply-to', 'https://x.com/fixture_account/status/12')
    assert result.returncode == 0, result.stderr
    assert posting.records()[-1]['verified_fields']['in_reply_to_status_id_str'] == '12'


def test_link_self_reply_row_refuses_another_target(posting):
    posting.row.update(channel='x_post', self_reply_to='12')
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--reply-to', 'https://x.com/fixture_account/status/13')
    assert result.returncode == 2 and not fake.sent_prompts


def test_post_dry_run_cancels_without_send_or_receipt(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--post', '--dry-run')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'cancel, do not send']
    assert not posting.sent_log.exists() and not fake.http_requests
    assert not json.loads(posting.ledger_path.read_text().splitlines()[-1]).get('gate_attempt')
    assert 'Nothing posted' in result.stdout


def test_post_missing_bot_never_types(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.missing_bot = True
        result = posting.run('--post')
    assert result.returncode == 2, result.stderr
    assert 'create the configured post_bot_name' in result.stderr
    assert not fake.sent_prompts and 'Input.insertText' not in fake.methods


def test_post_line_endings_only_normalized(posting):
    posting.returned_draft = posting.text.replace('\n', '\r\n')
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.syndication['text'] = posting.returned_draft
        result = posting.run('--post')
    assert result.returncode == 0, result.stderr


def test_dm_confirmation_and_rh_only(posting):
    posting.row.update(channel='x_dm', to_key='@fixture_person')
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--dm', 'fixture_person')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'send'] and not fake.http_requests
    assert 'no public endpoint' in result.stdout and posting.sent_log.exists()
    assert posting.records()[-1]['verified_fields']['confirmation'] == 'Grok only; no public endpoint'


def test_post_host_cannot_switch_fixed_account(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        result = posting.run('--host', 'other_host', '--post')
    assert result.returncode == 2 and not fake.methods


def test_post_rh_failure_after_verified_send_pages_and_retains_attempt(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        posting.options['rh_command'] = [sys.executable, '-c', 'raise SystemExit(2)']
        posting.save()
        result = posting.run('--post')
    assert result.returncode == 5 and 'rh outreach sent failed' in result.stderr
    assert fake.events == ['draft', 'send', 'syndication']
    assert posting.page_log.exists() and not posting.sent_log.exists()
    assert posting.records()[-1]['verified_fields']['id'] == '9001'


@pytest.mark.parametrize('change', ['status', 'recipient', 'account', 'id'])
def test_dm_requires_explicit_matching_confirmation(posting, change):
    posting.row.update(channel='x_dm', to_key='@fixture_person')
    with FakeCDP() as fake:
        posting.setup(fake)
        original = fake.on_send
        def answer(prompt):
            original(prompt)
            if prompt == 'send':
                response = json.loads(fake.answer)[0]
                response[change] = 'wrong'
                fake.answer = json.dumps([response])
        fake.on_send = answer
        result = posting.run('--dm', 'fixture_person')
    assert result.returncode == 5 and posting.page_log.exists()
    assert not posting.sent_log.exists() and not fake.http_requests


def test_approval_changed_while_drafting_cancels_before_send(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        original = fake.on_send
        def answer(prompt):
            original(prompt)
            if prompt not in ('send', 'cancel, do not send'):
                posting.row['status'] = 'dropped'
                posting.save()
        fake.on_send = answer
        result = posting.run('--post')
    assert result.returncode == 2, result.stderr
    assert fake.events == ['draft', 'cancel, do not send']
    assert not posting.sent_log.exists() and not fake.http_requests


def test_post_draft_transport_timeout_cancels_without_send(posting):
    with FakeCDP(busy=True) as fake:
        posting.setup(fake)
        result = posting.run('--post', '--timeout', '0.4')
    assert result.returncode == 3 and 'timeout' in result.stderr
    assert fake.events == ['draft', 'cancel, do not send']
    assert posting.records()[-1]['cancelled'] and not posting.sent_log.exists()


def test_post_send_timeout_is_uncertain_and_pages(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        original = fake.on_send
        def answer(prompt):
            original(prompt)
            if prompt == 'send':
                fake.busy = True
        fake.on_send = answer
        result = posting.run('--post', '--timeout', '0.6')
    assert result.returncode == 5 and 'timeout' in result.stderr
    assert fake.events == ['draft', 'send']
    assert posting.page_log.exists() and not posting.sent_log.exists()


def test_post_uses_real_rh_sent_implementation(posting):
    with FakeCDP() as fake:
        posting.setup(fake)
        posting.options['rh_command'] = [sys.executable, str(TOOLS.parents[1] / 'harness/rh.py')]
        posting.save()
        result = posting.run('--post')
    assert result.returncode == 0, result.stderr
    row = json.loads(posting.ledger_path.read_text().splitlines()[-1])
    assert row['sent']['via'] == 'grok' and row['sent']['message_id'] == '9001'
    assert row['status'] == 'sent'


def card(posting, **change):
    fields = dict(type='reply' if posting.row.get('in_reply_to') or posting.row.get('self_reply_to') else 'post',
                  text=posting.text, author='fixture_account', reply_to='', media=[], quote=False, sent=False)
    fields.update(change)
    return fields


def test_card_path_checks_structured_draft_presses_and_verifies(posting):
    posting.options['draft_card'] = True
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.card = card(posting)
        result = posting.run('--post')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'press-send', 'syndication']
    assert 'Call create_posts once now' in fake.sent_prompts[0] and posting.text in fake.sent_prompts[0]
    args = json.loads(posting.sent_log.read_text())
    assert args[-8:] == ['outreach', 'sent', 'fixture', 'o1', '--message-id', '9001', '--via', 'grok']
    assert 'Verified: https://x.com/fixture_account/status/9001' in result.stdout


@pytest.mark.parametrize('change', [dict(text='A fixed sample has three distinct periods.'),
                                    dict(author='someone_else'), dict(reply_to='12'), dict(media=['media']),
                                    dict(quote=True), dict(sent=True)])
def test_card_path_discards_any_difference_exit_four(posting, change):
    posting.options['draft_card'] = True
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.card = card(posting, **change)
        result = posting.run('--post')
    assert result.returncode == 4, result.stderr
    assert fake.events == ['draft', 'press-discard'] and not posting.sent_log.exists()
    assert not json.loads(posting.ledger_path.read_text().splitlines()[-1]).get('gate_attempt')


def test_card_path_dry_run_discards(posting):
    posting.options['draft_card'] = True
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.card = card(posting)
        result = posting.run('--post', '--dry-run')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'press-discard'] and not fake.http_requests


def test_card_path_permission_before_card_sends_nothing(posting):
    posting.options['draft_card'] = True
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.permission_first = True
        result = posting.run('--post')
    assert result.returncode == 3, result.stderr
    assert fake.events == ['draft'] and not fake.pressed


def test_card_path_allows_permission_after_press(posting):
    posting.options['draft_card'] = True
    posting.row.update(channel='x_post', self_reply_to='12')
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.card = card(posting, reply_to='12')
        fake.permission_after_press = True
        fake.syndication['in_reply_to_status_id_str'] = '12'
        result = posting.run('--reply-to', 'https://x.com/fixture_account/status/12')
    assert result.returncode == 0, result.stderr
    assert fake.events == ['draft', 'press-send', 'allow', 'syndication']


def test_card_path_no_posted_url_is_uncertain_and_pages(posting):
    posting.options['draft_card'] = True
    with FakeCDP() as fake:
        posting.setup(fake)
        fake.card = card(posting)
        fake.after_text = 'Working on it'
        result = posting.run('--post')
    assert result.returncode == 5, result.stderr
    assert posting.page_log.exists()
    assert json.loads(posting.ledger_path.read_text().splitlines()[-1])['gate_attempt']['path'] == 'grok-post'
