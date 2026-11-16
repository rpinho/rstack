"""Stdlib CDP transport and Grok query runner. No account or credential access."""
import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import uuid

MAX_BYTES = 32 * 1024 * 1024
CACHE = 'Library/Application Support/Grok Bot/sand-client-persistence'
SUFFIX = ('Return exactly one ```json fenced block containing an array of objects. '
          'Use [] if there are no results. Do not put any other fenced blocks in the answer.')


class AskError(Exception):
    pass


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise AskError('timeout')
    return seconds


def pause(deadline, seconds):
    time.sleep(min(remaining(deadline), seconds))


def read_exact(sock, size, deadline):
    data = bytearray()
    while len(data) < size:
        sock.settimeout(remaining(deadline))
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise AskError('CDP websocket closed')
        data.extend(chunk)
    return bytes(data)


class CDP:
    """RFC 6455 client: masking, fragmented replies, ping/pong and CDP events."""
    def __init__(self, url, port, deadline):
        parsed = urlsplit(url)
        if parsed.scheme != 'ws' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise AskError('CDP advertised a non-loopback websocket')
        self.deadline = deadline
        self.ident = 0
        self.sock = socket.create_connection(('127.0.0.1', port), remaining(deadline))
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            path = parsed.path + (('?' + parsed.query) if parsed.query else '')
            request = ('GET {} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nUpgrade: websocket\r\n'
                       'Connection: Upgrade\r\nSec-WebSocket-Key: {}\r\n'
                       'Sec-WebSocket-Version: 13\r\n\r\n').format(path, port, key)
            self.sock.sendall(request.encode())
            header = bytearray()
            while not header.endswith(b'\r\n\r\n'):
                header.extend(read_exact(self.sock, 1, deadline))
                if len(header) > 16384:
                    raise AskError('oversized websocket handshake')
            lines = header.decode('latin1').split('\r\n')
            fields = {name.lower(): value for name, value in
                      (line.split(':', 1) for line in lines[1:] if ':' in line)}
            accept = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if (' 101 ' not in lines[0] or fields.get('sec-websocket-accept', '').strip() != accept
                    or fields.get('upgrade', '').strip().lower() != 'websocket'):
                raise AskError('CDP websocket handshake rejected')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.sock.close()

    def frame(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        prefix = bytes([0x80 | opcode])
        if size < 126:
            prefix += bytes([0x80 | size])
        elif size < 65536:
            prefix += bytes([0x80 | 126]) + struct.pack('!H', size)
        else:
            prefix += bytes([0x80 | 127]) + struct.pack('!Q', size)
        self.sock.settimeout(remaining(self.deadline))
        self.sock.sendall(prefix + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))

    def message(self):
        parts = bytearray()
        while True:
            first, second = read_exact(self.sock, 2, self.deadline)
            size = second & 127
            if size == 126:
                size = struct.unpack('!H', read_exact(self.sock, 2, self.deadline))[0]
            elif size == 127:
                size = struct.unpack('!Q', read_exact(self.sock, 8, self.deadline))[0]
            if size + len(parts) > MAX_BYTES:
                raise AskError('CDP response exceeds 32 MiB')
            if second & 128:
                raise AskError('unexpected masked server frame')
            payload = read_exact(self.sock, size, self.deadline)
            opcode = first & 15
            if opcode == 8:
                raise AskError('CDP websocket closed')
            if opcode == 9:
                self.frame(payload, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise AskError('unsupported CDP websocket frame')
            parts.extend(payload)
            if first & 128:
                return json.loads(parts)

    def call(self, method, **params):
        self.ident += 1
        self.frame(json.dumps(dict(id=self.ident, method=method, params=params)).encode())
        while True:
            reply = self.message()
            if reply.get('id') != self.ident:
                continue
            if 'error' in reply:
                raise AskError('CDP {}: {}'.format(method, reply['error']))
            return reply.get('result', {})

    def evaluate(self, expression):
        reply = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        if reply.get('exceptionDetails'):
            raise AskError('DOM evaluation failed: ' + str(reply['exceptionDetails']))
        return reply.get('result', {}).get('value')


def targets(port, deadline):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=min(2, remaining(deadline)))
    try:
        conn.request('GET', '/json/list')
        response = conn.getresponse()
        body = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(body) > MAX_BYTES:
            raise AskError('invalid CDP target list')
        return json.loads(body)
    finally:
        conn.close()


@contextlib.contextmanager
def endpoint(host, port, deadline):
    if host == 'local':
        yield port
        return
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        local_port = probe.getsockname()[1]
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(['ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                                 '-o', 'ConnectTimeout=5', '-L',
                                 '127.0.0.1:{}:127.0.0.1:{}'.format(local_port, port), host],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            while True:
                if proc.poll() is not None:
                    errors.seek(0)
                    raise AskError('ssh tunnel failed: ' + errors.read(4096).decode(errors='replace'))
                try:
                    with socket.create_connection(('127.0.0.1', local_port), timeout=0.1):
                        break
                except OSError:
                    pause(deadline, 0.1)
            yield local_port
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def app_command(host, argv, deadline):
    command = argv if host == 'local' else ['ssh', '-T', '-o', 'BatchMode=yes', host, shlex.join(argv)]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=remaining(deadline))
    if result.returncode:
        raise AskError('app command failed: ' + result.stderr.decode(errors='replace'))


def quit_app(host, deadline):
    app_command(host, ['osascript', '-e', 'tell application "Grok Bot" to quit'], deadline)


@contextlib.contextmanager
def app_lifecycle(host, port, relaunch, deadline):
    if not relaunch:
        yield
        return
    try:
        quit_app(host, deadline)
        pause(deadline, 1)
        app_command(host, ['open', '-a', 'Grok Bot', '--args',
                          '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + str(port)], deadline)
        yield
    finally:
        # Restoration gets its own bounded window even after a query timeout.
        restore_deadline = time.monotonic() + 15
        quit_app(host, restore_deadline)
        pause(restore_deadline, 1)
        app_command(host, ['open', '-a', 'Grok Bot'], restore_deadline)


def entries(cache):
    """Decoder reused from grok_fresh.py: base32 name, transcript replicas, JSON value.

    Decode one copied blob at a time; callers retain the filename to correlate a prompt.
    """
    for p in Path(cache).rglob('*.blob'):
        n = p.name[:-5].upper()
        n += '=' * ((8 - len(n) % 8) % 8)
        try:
            name = base64.b32decode(n).decode()
        except Exception:
            continue
        if '.transcript.replicas.' not in name:
            continue
        try:
            v = json.loads(p.read_text()).get('value')
            v = json.loads(v) if isinstance(v, str) else v
            messages = (v or {}).get('entries', [])
        except (OSError, ValueError, AttributeError):
            continue
        for e in messages:
            msg = e.get('message') or {}
            if isinstance(msg.get('content'), str) and e.get('timestampMs'):
                yield p.name, e['timestampMs'], msg['content']


def copy_cache(dst, host, deadline):
    """Copy only blobs, at most 32 MiB. Never extract remote paths or read credentials."""
    total = 0
    if host == 'local':
        for path in (Path.home() / CACHE).rglob('*.blob'):
            remaining(deadline)
            size = path.stat().st_size
            total += size
            if total > MAX_BYTES:
                raise AskError('cache exceeds 32 MiB copy limit')
            shutil.copyfile(path, Path(dst) / path.name)
        return
    command = ('cd "$HOME/' + CACHE + '" && '
               "find . -type f -name '*.blob' -print0 | COPYFILE_DISABLE=1 tar --null -T - -cf -")
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(['ssh', '-T', '-o', 'BatchMode=yes', host, command],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors)
        # Stream through a socket deadline, avoiding an unbounded pipe read from ssh.
        try:
            with tempfile.TemporaryFile() as archive:
                while True:
                    if not select.select([proc.stdout], [], [], remaining(deadline))[0]:
                        raise AskError('timeout copying cache')
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise AskError('cache exceeds 32 MiB copy limit')
                    archive.write(chunk)
                if proc.wait(timeout=remaining(deadline)):
                    raise AskError('could not copy remote Grok Bot cache')
                archive.seek(0)
                with tarfile.open(fileobj=archive, mode='r|') as tar:
                    for item in tar:
                        if item.isfile() and item.name.endswith('.blob'):
                            with tar.extractfile(item) as src, (Path(dst) / Path(item.name).name).open('wb') as out:
                                shutil.copyfileobj(src, out)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()


def cache_answer(host, prompt, deadline):
    with tempfile.TemporaryDirectory(prefix='grok-ask-cache-') as tmp:
        copy_cache(tmp, host, deadline)
        transcripts = {}
        for name, ts, text in entries(tmp):
            transcripts.setdefault(name, []).append((ts, text))
        candidates = []
        for messages in transcripts.values():
            messages.sort(key=lambda row: row[0])
            # The unique request ID correlates across hosts without assuming clock sync.
            matching = [ts for ts, text in messages if text == prompt]
            if matching:
                candidates.extend((ts, text) for ts, text in messages
                                  if ts > max(matching) and text != prompt)
        return max(candidates, default=(0, ''))[1]


def js(config, action, prompt=''):
    # Pass configuration as JSON data, never interpolate selectors or queries as code.
    data = json.dumps(dict(config=config, action=action, prompt=prompt))
    return '/* grok-ask:{} */\n'.format(action) + '(() => { const data = ' + data + ''';
      const c = data.config, prompt = data.prompt;
      const one = key => document.querySelector(c[key]);
      const all = key => [...document.querySelectorAll(c[key])];
      const text = el => el.innerText || el.textContent || '';
      const visible = el => !!(el.getClientRects().length);
      if (data.action === 'new' && c.bot_name) {
        // 11-15 live: Grok Bot has no "new chat"; each bot is one conversation. grok-ask uses its own bot
        // so its answers never mix with a routine's output in another bot's conversation.
        const bot = [...document.querySelectorAll('button,a')].find(b =>
          (b.getAttribute('aria-label') || '').split(',')[0].trim() === c.bot_name);
        if (!bot) throw Error('bot ' + c.bot_name + ' not found in the sidebar');
        bot.click(); return true;
      }
      if (data.action === 'new') {
        const button = one('new_chat');
        if (!button || !visible(button)) throw Error('new_chat selector not found');
        button.click(); return true;
      }
      if (data.action === 'ready') {
        const box = one('composer');
        const title = document.querySelector('button[aria-label="View conversation details"]');
        const onBot = !c.bot_name || (!!title && text(title).trim() === c.bot_name);
        const fresh = c.bot_name || (!all('assistant_message').length && !all('user_message').length);
        return !!box && visible(box) && !box.disabled && onBot && fresh &&
          (!!c.bot_name || !(box.value || box.textContent || '').trim());
      }
      if (data.action === 'focus') {
        const box = one('composer'); box.focus();
        document.execCommand('selectAll'); document.execCommand('delete');   // a failed send leaves text
        return true;
      }
      if (data.action === 'send') {
        const box = one('composer'), button = one('send');
        const norm = t => (t || '').replace(/\s+/g, ' ').trim();   // a rich editor drops line breaks
        if (norm(box.value || box.innerText || box.textContent) !== norm(prompt)) throw Error('composer text mismatch');
        if (!button || button.disabled || !visible(button)) throw Error('send selector not ready');
        button.click(); return true;
      }
      const marker = prompt.slice(prompt.lastIndexOf('Request ID:'));
      const mine = all('user_message').filter(el => text(el).includes(marker));
      const sent = mine.length > 0;
      // Only an answer AFTER our own message counts (a bot's conversation keeps earlier answers).
      const after = sent ? all('assistant_message').filter(el =>
        mine[mine.length - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) : [];
      const answer = after[after.length - 1];
      if (!answer) return {text:'', busy:all('busy').some(visible), sent};
      let raw = text(answer);
      if (!raw.includes('```')) {
        const blocks = [...answer.querySelectorAll(c.json_code)];
        raw += blocks.map(el => '\\n```json\\n' + text(el) + '\\n```').join('');
      }
      return {text:raw, busy:all('busy').some(visible), sent};
    })()'''


def query(cdp, config, host, prompt, deadline, state):
    cdp.call('Page.enable')
    cdp.evaluate(js(config, 'new'))
    while not cdp.evaluate(js(config, 'ready')):
        pause(deadline, config['poll_seconds'])
    cdp.evaluate(js(config, 'focus'))
    cdp.call('Input.insertText', text=prompt)
    cdp.evaluate(js(config, 'send', prompt))
    previous, changed = None, time.monotonic()
    fallback = False
    while True:
        remaining(deadline)
        if not fallback:
            try:
                sample = cdp.evaluate(js(config, 'read', prompt))
                if not isinstance(sample, dict) or not isinstance(sample.get('text'), str):
                    raise AskError('DOM answer read failed')
                state['raw'] = sample['text']
            except (AskError, OSError, ValueError):
                fallback = True
                previous = None
        if fallback:
            try:
                raw = cache_answer(host, prompt, deadline)
            except (OSError, ValueError, AskError) as exc:
                state['cache_error'] = str(exc)
                raw = ''
            if raw:
                state['raw'] = raw
            sample = dict(text=raw, busy=False, sent=bool(raw))
        # 11-15 digest: an answer captured while the app showed "Queries is typing / Typing…" failed with no
        # JSON. Progress text is busy, however long it stays the same.
        if re.search(config.get('busy_text', r'is typing|Typing…|Typing\.\.\.|Searching X posts|Searching the web'),
                     sample['text'] or ''):
            sample = dict(sample, busy=True)
        signature = (sample['text'], sample.get('busy'), sample.get('sent'))
        if signature != previous:
            changed = time.monotonic()
            previous = signature
        quiet = config['cache_settle_seconds'] if fallback else config['settle_seconds']
        if (sample.get('sent') and sample['text'] and not sample.get('busy')
                and time.monotonic() - changed >= quiet):
            # 11-15 live: the app shows "Searching X posts" with no busy control, so a quiet page is not a
            # finished answer. Done = the answer parses, or nothing has changed for answer_quiet_seconds.
            try:
                parse_answer(sample['text'], [])
                return sample['text']
            except AskError:
                if time.monotonic() - changed >= config.get('answer_quiet_seconds', 90):
                    return sample['text']
        pause(deadline, config['poll_seconds'])


def parse_answer(raw, required):
    blocks = re.findall(r'^[ \t]*```json[ \t]*\r?\n(.*?)^[ \t]*```[ \t]*\r?$',
                        raw, flags=re.S | re.M | re.I)
    if len(blocks) > 1:
        raise AskError('expected exactly one json fenced block')
    if not blocks:
        # 11-15 live: the app renders the code block, so the page text has the JSON and no fences.
        # Take the one top-level JSON array that the text holds; anything else is still refused.
        found, last = [], -1
        for start in [m.start() for m in re.finditer(r'\[', raw)]:
            if start < last:
                continue            # inside an array already taken: nested arrays are part of it
            try:
                value, end = json.JSONDecoder().raw_decode(raw[start:])
            except ValueError:
                continue
            if isinstance(value, list):
                found.append(raw[start:start + end])
                last = start + end
        if len(found) != 1:
            raise AskError('expected exactly one JSON array in the answer (found {})'.format(len(found)))
        blocks = found
    try:
        rows = json.loads(blocks[0], parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except ValueError as exc:
        raise AskError('bad JSON: ' + str(exc))
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise AskError('JSON must be an array of objects')
    for index, row in enumerate(rows):
        missing = set(required) - row.keys()
        if missing:
            raise AskError('schema miss in row {}: {}'.format(index, ', '.join(sorted(missing))))
    return rows


def schema_keys(path):
    if not path:
        return []
    value = json.loads(Path(path).read_text())
    if isinstance(value, list):
        required = value
    elif isinstance(value, dict):
        item = value.get('items', value)
        if not isinstance(item, dict) or not isinstance(item.get('properties', {}), dict):
            raise AskError('schema items/properties must be objects')
        required = item.get('required', list(item.get('properties', {})))
    else:
        raise AskError('schema must be a key list or an object/array JSON Schema')
    if not isinstance(required, list) or not all(isinstance(key, str) and key for key in required):
        raise AskError('schema required keys must be nonempty strings')
    return required


@contextlib.contextmanager
def host_lock(path, deadline):
    with path.open('a') as stream:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AskError('timeout waiting for host lock')
                pause(deadline, 0.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def load_config():
    path = Path(os.environ.get('GROK_ASK_CONFIG', '~/.config/rstack/grok-ask.json')).expanduser()
    defaults = json.loads(Path(__file__).with_name('grok-ask.json.example').read_text())
    if path.exists():
        defaults.update(json.loads(path.read_text()))
    for key in ('new_chat', 'composer', 'send', 'user_message', 'assistant_message', 'busy', 'json_code'):
        if not isinstance(defaults[key], str) or not defaults[key]:
            raise AskError('config requires selector: ' + key)
    for key in ('target_title', 'target_url'):
        if not isinstance(defaults[key], str):
            raise AskError('config requires a string for ' + key)
    for key in ('poll_seconds', 'settle_seconds', 'cache_settle_seconds'):
        if not isinstance(defaults[key], (int, float)) or not math.isfinite(defaults[key]) or defaults[key] <= 0:
            raise AskError('config requires positive finite ' + key)
    if type(defaults['port']) is not int or not 1 <= defaults['port'] <= 65535:
        raise AskError('config port must be 1..65535')
    return defaults


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='local', help='SSH host alias, or local (default)')
    parser.add_argument('--timeout', type=float, default=120, help='seconds including lock wait (default 120)')
    parser.add_argument('--schema', help='JSON key list or JSON Schema required/properties keys')
    parser.add_argument('--relaunch', action='store_true', help='explicitly quit/restart app; restore normal startup afterwards')
    parser.add_argument('query')
    args = parser.parse_args(argv)
    if args.host in ('localhost', '127.0.0.1', '::1'):
        args.host = 'local'
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', args.host):
        parser.error('host must be local or a plain SSH host alias')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout must be positive and finite')
    start = time.monotonic()
    deadline = start + args.timeout
    state = dict(raw='')
    rows, error, code = None, None, 3
    root = Path(os.environ.get('RSTACK_STATE_DIR',
                str(Path(os.environ.get('XDG_STATE_HOME', '~/.local/state')).expanduser() / 'rstack'))).expanduser()
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        required = schema_keys(args.schema)
        config = load_config()
        prompt = args.query + '\n\n' + SUFFIX
        if required:
            prompt += '\nEvery object must include these keys: ' + json.dumps(required) + '.'
        prompt += '\nRequest ID: ' + uuid.uuid4().hex
        lock_name = hashlib.sha256(args.host.encode()).hexdigest()[:24]
        with host_lock(root / ('grok-ask-' + lock_name + '.lock'), deadline):
            with app_lifecycle(args.host, config['port'], args.relaunch, deadline):
                with endpoint(args.host, config['port'], deadline) as port:
                    while True:
                        try:
                            pages = targets(port, deadline)
                            break
                        except (OSError, ValueError, AskError) as exc:
                            if args.relaunch and time.monotonic() < deadline:
                                pause(deadline, 0.2)
                                continue
                            raise AskError('CDP endpoint unavailable on {} localhost:{}. Start Grok Bot on that host with: '
                                           'open -a "Grok Bot" --args --remote-debugging-address=127.0.0.1 '
                                           '--remote-debugging-port={} (quit it manually first if already running). {}'.format(
                                               args.host, config['port'], config['port'], exc))
                    pages = [p for p in pages if p.get('type') == 'page'
                             and config['target_title'].lower() in p.get('title', '').lower()
                             and config['target_url'] in p.get('url', '')]
                    if len(pages) != 1:
                        raise AskError('expected one Grok page, found {}; configure target_title/target_url'.format(len(pages)))
                    with contextlib.closing(CDP(pages[0]['webSocketDebuggerUrl'], port, deadline)) as cdp:
                        raw = query(cdp, config, args.host, prompt, deadline, state)
                        rows = parse_answer(raw, required)
                        code = 0
    except (AskError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        code = 3
        error = str(exc) or type(exc).__name__
        print('grok-ask: ' + error, file=sys.stderr)
        print('Raw answer:\n' + state['raw'], file=sys.stderr)
        if state.get('cache_error'):
            print('Cache fallback: ' + state['cache_error'], file=sys.stderr)
    finally:
        record = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), host=args.host,
                      caller=os.environ.get('RSTACK_CALLER', 'grok-ask'),
                      query_hash=hashlib.sha256(args.query.encode()).hexdigest(),
                      rows_returned=len(rows) if code == 0 else 0,
                      seconds=round(time.monotonic() - start, 3), exit_code=code)
        if error:
            # Keep raw answers, account details and connection diagnostics out of the ledger.
            record['failed'] = True
        try:
            with (root / 'grok-ask.jsonl').open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.write(json.dumps(record) + '\n')
        except OSError as exc:
            print('grok-ask: could not write ledger: ' + str(exc), file=sys.stderr)
            code = 3
    if code == 0:
        print(json.dumps(rows, ensure_ascii=False, allow_nan=False))
    return code
