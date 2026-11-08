#!/usr/bin/env python3
"""cs: drive the local Claude Science daemon from the command line (stdlib only).

Unofficial: uses the same local HTTP API the web UI uses (found 10-30 by reading the UI bundle).
Login = the single-use link from `claude-science url`, posted to /api/auth/nonce; the session cookie
is kept in the configured CS_STATE/cookies.txt (0600). Writes need Origin + x-operon-csrf (double-submit).

  cs.py login                         mint a link and log in (cookie saved)
  cs.py projects                      list projects (id, name)
  cs.py newproject "Name" [--desc D] [--instructions @file]   create a project; prints id + URL
  cs.py instructions PROJECT @file    replace a project's standing instructions
  cs.py archive PROJECT               archive a project
  cs.py ask PROJECT "text" [--model M] [--effort E]   start a new session; prints the session id + URL
                                      model = the calling session's, else the lane's claude_science_model, else Opus 5.5; Opus 5 is refused
  cs.py reply SESSION "text"          send a follow-up in an existing session
  cs.py status SESSION                processing / waiting / done, plus any prompt waiting for a click
  cs.py approve SESSION [--scope S]   allow its pending local prompts (scope conversation by default)
  cs.py cancel SESSION                stop a session
  cs.py resume SESSION                restart a cancelled session where it stopped
  cs.py read SESSION [--all]          print the assistant's final text (or every assistant text block)
  cs.py wait SESSION [--timeout S] [--approve]   block until the session stops processing, then print the final text;
                                      a session waiting on a prompt stays 'processing', so --approve clears them as they come

Text arguments may be '@file' to read the prompt from a file.
"""
import settings  # loads the host env file before CS_* are read
import http.cookiejar, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

def _discover_base():
    """The daemon does NOT always come back on 8765: a restart can land it on any free
    port (seen 10-30: 8765 -> 8000), and cs.py then fails with 'Connection refused'.
    Ask the CLI for the live port; fall back to 8765 only if that fails."""
    if os.environ.get('CS_BASE'):
        return os.environ['CS_BASE']
    try:
        out = subprocess.run([CS_BIN, 'status'], capture_output=True, text=True, timeout=20).stdout
        d = json.loads(out)
        if d.get('running') and d.get('port'):
            return f"http://localhost:{d['port']}"
    except Exception:
        pass
    return 'http://localhost:8765'
STATE = os.path.expanduser(os.environ.get('CS_STATE', '.runtime/cs')); os.makedirs(STATE, mode=0o700, exist_ok=True)
JAR = os.path.join(STATE, 'cookies.txt')
AUTO_APPROVE = {'local_exec'}
# Kinds whose approval the API only honours with the 'always' scope. 11-07, math: a network
# approval sent with scope 'conversation' returns 200 "accepted" and changes nothing, so the
# session parks forever (C47 session 6660b62e sat on annals.math.princeton.edu until it was
# resolved by hand). A 200 that does nothing is the worst kind of answer, so the scope the API
# requires is sent regardless of what the caller asked for, rather than relaying a request that
# will be silently dropped.
SCOPE_ALWAYS = {'network'}
AUTO_READ = tuple(os.path.abspath(os.path.expanduser(p)) + os.sep for p in os.environ.get('CS_AUTO_READ', '').split(os.pathsep) if p)
CS_BIN = os.environ.get('CS_BIN', 'claude-science')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rh


def model_for(project, opts):
    """--model if given, else the calling session's model, else the lane's claude_science_model, else Opus 5.5.

    A session that a safeguard moved to Opus 5 falls through to the lane's model."""
    model = opts.get('model')
    if not model:
        model = rh.session_model()
    if not model or (model in rh.CS_BANNED_MODELS and not opts.get('model')):
        model = rh.CS_DEFAULT_MODEL
        for path in sorted((rh.ROOT / 'lanes').glob('*/INTAKE.toml')):
            cfg = rh.config(path)
            if project and cfg.get('claude_science_project', '').rstrip('/').endswith(project):
                model = cfg.get('claude_science_model', rh.CS_DEFAULT_MODEL)
    if model in rh.CS_BANNED_MODELS:
        sys.exit('{} is banned (configured model policy): use {} (alternate {})'.format(model, rh.CS_DEFAULT_MODEL, rh.CS_ALTERNATE_MODEL))
    return model
BASE = _discover_base()

jar = http.cookiejar.MozillaCookieJar(JAR)
if os.path.exists(JAR):
    jar.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def save():
    jar.save(ignore_discard=True, ignore_expires=True); os.chmod(JAR, 0o600)


def csrf():
    for c in jar:
        if c.name == 'operon_csrf':
            return c.value
    return ''


def call(path, data=None, form=False):
    headers = {}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        headers['Origin'] = BASE
        headers['x-operon-csrf'] = csrf()
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method='POST' if body else 'GET')
    try:
        with opener.open(req) as r:
            out = r.read().decode(); save()
            return r.status, out
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def patch(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, method='PATCH', headers={
        'Content-Type': 'application/json', 'Origin': BASE, 'x-operon-csrf': csrf()})
    try:
        with opener.open(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login():
    url = re.search(r'http\S+', subprocess.run([CS_BIN, 'url'], capture_output=True, text=True).stdout + '').group(0)
    nonce = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['nonce'][0]
    call(urllib.parse.urlparse(url).path + '?' + urllib.parse.urlparse(url).query)  # sets operon_csrf
    code, _ = call('/api/auth/nonce', {'nonce': nonce, 'dest': '/'}, form=True)
    me = call('/api/me')
    if me[0] != 200:
        sys.exit(f'login failed ({code}/{me[0]})')
    print('logged in')


def ensure():
    if call('/api/me')[0] != 200:
        login()
    call('/csrf')  # refresh the CSRF cookie


def post(data):
    code, out = call('/api/request', data)
    if code == 403 and 'csrf' in out:
        call('/csrf'); code, out = call('/api/request', data)
    if code != 200:
        sys.exit(f'HTTP {code}: {out[:300]}')
    return json.loads(out)


def text_arg(s):
    return open(s[1:]).read() if s.startswith('@') else s


def frame(fid):
    code, out = call(f'/api/frames/{fid}?shallow=1')
    if code != 200:
        sys.exit(f'HTTP {code}: {out[:200]}')
    return json.loads(out)


def messages(fid):
    out, start = [], 0
    while True:
        code, body = call(f'/api/frames/{fid}/messages?from={start}&limit=200')
        d = json.loads(body); m = d.get('messages', [])
        out += m; start += len(m)
        if not m or start >= d.get('total', start):
            return out


def pending(fid):
    return (json.loads(call(f'/api/frames/{fid}')[1]).get('output_data') or {}).get('pending_input_requests') or []


def approve(fid, scope='conversation'):
    # Approve Claude Science yourself. Only local compute is automatic; anything that spends,
    # reads credentials or deletes keeps waiting for a human click (Spend rule, README).
    def auto(r):
        # A usage_checkpoint with no boundary is only "approaching your limit" and cannot bill;
        # boundary 'overage' (limit reached, continuing draws credits) still waits for a human.
        if r.get('kind') == 'usage_checkpoint':
            return not r.get('boundary')
        return r.get('kind') in AUTO_APPROVE or (r.get('kind') == 'host' and r.get('requested_mode') == 'ro'
                                                 and (r.get('target', '') + '/').startswith(AUTO_READ))
    ok = [r for r in pending(fid) if auto(r)]
    if ok:
        code, out = call(f'/api/frames/{fid}/resolve-input', {'responses': [
            dict(requestId=r['requestId'], approved=True) if r.get('kind') == 'usage_checkpoint' else
            dict(requestId=r['requestId'], tool_id=r.get('tool_id'), approved=True, action='allow',
                 scope='always' if r.get('kind') in SCOPE_ALWAYS else scope,
                 **({'mode': 'ro'} if r.get('kind') == 'host' else {})) for r in ok]})
        if code != 200:
            sys.exit(f'HTTP {code}: {out[:300]}')
    return ok, pending(fid)


def assistant_texts(fid):
    texts = []
    for m in messages(fid):
        if m.get('role') != 'assistant':
            continue
        c = m.get('content')
        for b in (c if isinstance(c, list) else [{'type': 'text', 'text': c}]):
            if isinstance(b, dict) and b.get('type') == 'text' and b.get('text', '').strip():
                texts.append(b['text'])
    return texts


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return
    cmd, rest = a[0], a[1:]
    opts = {k.lstrip('-'): v for k, v in zip(rest[::2], rest[1::2]) if k.startswith('--')}
    pos = [x for i, x in enumerate(rest) if not x.startswith('--') and (i == 0 or not rest[i - 1].startswith('--') or rest[i - 1] == '--all')]
    if cmd == 'login':
        login(); return
    ensure()
    if cmd == 'projects':
        for p in json.loads(call('/api/projects')[1])['projects']:
            print(p['project_id'], p['name'])
    elif cmd == 'newproject':
        body = {'name': pos[0], 'description': opts.get('desc', '')}
        if opts.get('instructions'):
            body['instructions'] = text_arg(opts['instructions'])
        code, out = call('/api/projects', body)
        if code not in (200, 201):
            sys.exit(f'HTTP {code}: {out[:300]}')
        pid = json.loads(out).get('project_id') or json.loads(out)['project']['project_id']
        print(pid, f'{BASE}/projects/{pid}')
    elif cmd == 'instructions':
        code, out = patch(f'/api/projects/{pos[0]}', {'context': text_arg(pos[1])})  # the daemon's field is context; an 'instructions' key is silently ignored
        print(code, out[:200])
    elif cmd == 'archive':
        print(call(f'/api/projects/{pos[0]}/archive', {})[0])
    elif cmd == 'ask':
        pid, text = pos[0], text_arg(pos[1])
        r = post({'target_agent': 'OPERON', 'project_id': pid, 'input_data': {'request': text},
                  'model': model_for(pid, opts), 'effort': opts.get('effort', 'high'), 'thinking': True})
        print(r['root_frame_id'], f"{BASE}/projects/{pid}/frames/{r['root_frame_id']}")
    elif cmd == 'reply':
        f = frame(pos[0])
        r = post({'target_agent': 'OPERON', 'root_frame_id': f['root_frame_id'], 'project_id': f.get('project_id') or opts.get('project'),
                  'input_data': {'request': text_arg(pos[1])}, 'model': model_for(f.get('project_id') or opts.get('project'), opts),
                  'effort': opts.get('effort', 'high'), 'thinking': True})
        print(r.get('status'), r.get('frame_id'))
    elif cmd == 'status':
        print(frame(pos[0]).get('status'))
        for r in pending(pos[0]):
            print('prompt:', r.get('kind'), r.get('tool'), str(r.get('code') or r.get('target', ''))[:200].replace('\n', ' '))
    elif cmd == 'approve':
        ok, held = approve(pos[0], opts.get('scope', 'conversation'))
        print(f'allowed {len(ok)}, held {len(held)}')
        for r in held:
            print('held:', r.get('kind'), r.get('tool'), str(r.get('code') or r.get('target', ''))[:200].replace('\n', ' '))
            if r.get('kind') in SCOPE_ALWAYS:
                # Say what clears it. math lost a session to this being silent: the request sat
                # pending with nothing explaining that only a person can let it through, and that
                # the API wants the Always scope when they do.
                print('      network access waits for a person by design (Spend rule). When they '
                      'allow it, the scope must be "always"; "conversation" returns 200 and '
                      'changes nothing.')
    elif cmd == 'resume':
        print(call(f'/api/frames/{pos[0]}/resume', {})[0])
    elif cmd == 'cancel':
        print(call(f'/api/frames/{pos[0]}/cancel', {})[0])
    elif cmd == 'read':
        t = assistant_texts(pos[0])
        print('\n\n'.join(t) if '--all' in rest else (t[-1] if t else ''))
    elif cmd == 'wait':
        end = time.time() + float(opts.get('timeout', 7200))
        while time.time() < end:
            cleared = approve(pos[0])[0] if '--approve' in rest else []
            if not cleared and frame(pos[0]).get('status') != 'processing':
                break
            time.sleep(30)  # local daemon status check; no remote polling
        print(frame(pos[0]).get('status'))
        t = assistant_texts(pos[0]); print(t[-1] if t else '')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
