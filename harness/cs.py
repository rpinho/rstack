#!/usr/bin/env python3
"""cs: drive a Claude Science daemon from the command line (stdlib only).

Unofficial: uses the same local HTTP API the web UI uses (found 10-30 by reading the UI bundle).
The daemon is the local one by default; set CS_HOST to an ssh alias to drive the instance on that
machine instead, over a tunnel (see CLAUDE_SCIENCE.md). An instance only reads the filesystem it
runs on, so the host matters: it decides what a review can see.
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
                                      a session waiting on a prompt stays 'processing', so --approve clears them as they come;
                                      a prompt it will not answer is named at once, and after CS_WAIT_HELD_S (600) wait exits 3 'parked'

Text arguments may be '@file' to read the prompt from a file.
"""
import settings  # loads the host env file before CS_* are read
import http.cookiejar, json, os, re, shlex, socket, subprocess, sys, time, urllib.parse, urllib.request

CS_HOST = os.environ.get('CS_HOST', '').strip()
# The Claude Science CLI on the host. It is not on PATH there, so the path is a setting and the
# remote shell expands the ~.
CS_REMOTE_BIN = os.environ.get('CS_REMOTE_BIN', '~/.claude-science/bin/claude-science')
# Local end of the tunnel. Deliberately NOT 8000: that is this machine's own instance.
CS_TUNNEL_PORT = int(os.environ.get('CS_TUNNEL_PORT', '18000') or 18000)
CS_SSH = os.environ.get('LAUNCH_SSH', 'ssh')
if CS_HOST and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}', CS_HOST):
    sys.exit('CS_HOST must be an ssh alias, got ' + repr(CS_HOST))


def _remote_path(value):
    """Quote a path for a REMOTE shell while letting it expand a leading ~.

    shlex.quote('~/x') yields '~/x' with the tilde quoted, so the remote shell treats it as a
    literal filename and the command fails with "no such file or directory". This is the second
    time in one evening that quoting a path which needed remote expansion broke a remote command;
    the first was $HOME in the launcher's pid marker. So: the home prefix is handed over bare for
    the remote shell to expand, and only the rest is quoted.
    """
    text = str(value)
    if text.startswith('~/'):
        return '$HOME/' + shlex.quote(text[2:])
    return shlex.quote(text)


def _ssh(argv, timeout=30):
    return subprocess.run(shlex.split(CS_SSH) + ['-o', 'BatchMode=yes', CS_HOST] + argv,
                          capture_output=True, text=True, timeout=timeout)


def _listening(port):
    with socket.socket() as s:
        s.settimeout(1.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def host_has(target):
    """Does `target` exist on the machine running the instance? None when it cannot be checked.

    general, 11-08: "refuse when a lane points Claude Science at a path that doesn't exist on the
    m5, rather than letting the review read nothing." With CS_HOST the instance reads the HOST's
    filesystem, so CS_AUTO_READ names host paths even though it is configured here. An allowlist
    entry that exists only on this machine would be granted and then read nothing, and a review
    that read nothing looks like a review that found nothing.
    """
    out = _ssh(['test -e ' + shlex.quote(str(target)) + ' && echo yes || echo no'])
    if out.returncode != 0:
        return None
    answer = out.stdout.strip().splitlines()[-1:] or ['']
    return True if answer[0] == 'yes' else False if answer[0] == 'no' else None


def _remote_status():
    """The host daemon's status JSON, or exit with why it could not be read."""
    out = _ssh([_remote_path(CS_REMOTE_BIN) + ' status'])
    if out.returncode != 0:
        sys.exit('cannot reach Claude Science on {}: {}'.format(CS_HOST, out.stderr.strip()[:200]))
    try:
        d = json.loads(out.stdout)
    except ValueError:
        sys.exit('Claude Science on {} did not answer with JSON: {}'
                 .format(CS_HOST, out.stdout.strip()[:200]))
    if not d.get('running') or not d.get('port'):
        sys.exit('Claude Science is not running on {} (status: {})'
                 .format(CS_HOST, json.dumps(d)[:200]))
    return d


def _tunnel(remote_port):
    """Make sure 127.0.0.1:CS_TUNNEL_PORT reaches remote_port on the host. Returns the local port.

    127.0.0.1 rather than localhost, deliberately. Cookies ignore the port, so a session minted
    against localhost:18000 collides with this machine's own instance on localhost:8000, and
    general lost a login to exactly that on 11-08. 127.0.0.1 is a different cookie domain, and the
    jar is per host as well, below.

    The sandbox content port is the app port plus one on both ends; the login link needs it.
    """
    local = CS_TUNNEL_PORT
    if _listening(local):
        return local            # already up, from this process or an earlier one
    forwards = []
    for offset in (0, 1):
        forwards += ['-L', '127.0.0.1:{}:localhost:{}'.format(local + offset, remote_port + offset)]
    argv = (shlex.split(CS_SSH) + ['-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                                   '-f', '-N'] + forwards + [CS_HOST])
    out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        sys.exit('could not open the tunnel to {} ({} -> {}): {}'
                 .format(CS_HOST, local, remote_port, out.stderr.strip()[:200]))
    for _ in range(20):
        if _listening(local):
            return local
        time.sleep(0.25)
    sys.exit('the tunnel to {} opened but 127.0.0.1:{} is not answering'.format(CS_HOST, local))


def _discover_base():
    """The URL of the instance to drive, asked for rather than assumed.

    The daemon does not keep a port: a restart lands it on any free one (seen 10-30, 8765 -> 8000,
    and again on 11-08). So the CLI is asked for the live port, on whichever machine owns the
    instance, and there is NO fallback. The old fallback to 8765 turned a stopped daemon into a
    'Connection refused', which reads as a network problem and sends you to the wrong place; an
    exit saying the daemon is not running sends you to the right one.
    """
    if os.environ.get('CS_BASE'):
        return os.environ['CS_BASE']
    if CS_HOST:
        # Ricardo, 11-08: "Make sure that the research harness knows to use Claude Science in the
        # m5." The science compute lives there, so the instance that reads the science filesystem
        # has to be the one on that machine. The CLI there is asked for its live port and a tunnel
        # is kept to it; nothing here assumes a port.
        global _ORIGIN
        port = _remote_status()['port']
        # The daemon checks Origin against its OWN address and answers a write from any other with
        # 403 "forbidden origin" (11-08: every write through the tunnel failed that way while reads
        # worked). Requests go to the tunnel; the Origin names the daemon as it sees itself.
        _ORIGIN = 'http://localhost:{}'.format(port)
        return 'http://127.0.0.1:{}'.format(_tunnel(port))
    try:
        out = subprocess.run([CS_BIN, 'status'], capture_output=True, text=True, timeout=20).stdout
        d = json.loads(out)
        if d.get('running') and d.get('port'):
            return f"http://localhost:{d['port']}"
    except Exception as exc:
        sys.exit('cannot ask {} for the daemon port ({}). The daemon does not keep one: a restart '
                 'can land it anywhere, so there is no port to fall back to. Start it, or set '
                 'CS_BASE, or set CS_HOST to use another machine\'s instance.'
                 .format(CS_BIN, str(exc)[:120]))
    sys.exit('Claude Science is not running here (status: {}). Start it, or set CS_HOST to use '
             'another machine\'s instance.'.format(out.strip()[:200] or 'no output'))
STATE = os.path.expanduser(os.environ.get('CS_STATE', '.runtime/cs')); os.makedirs(STATE, mode=0o700, exist_ok=True)
JAR = os.path.join(STATE, 'cookies-{}.txt'.format(CS_HOST) if CS_HOST else 'cookies.txt')
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
_BASE = None
_ORIGIN = None


def origin():
    """The Origin header a write must carry: the daemon's own address, which under CS_HOST is not
    the address the request goes to."""
    url = base()
    return _ORIGIN or url


def base():
    """The instance's URL, resolved on first use and then kept.

    Lazily, deliberately. Resolving it asks a daemon for its live port, and with CS_HOST that is
    an ssh round trip plus a tunnel. 11-08: resolving it at import, now that a missing daemon
    exits instead of guessing 8765, made `import cs` kill its own importer, and 12 of 14 tests in
    test_cs_host.py died before their first assertion. Importing this module must not need a
    daemon, a host, or a network.
    """
    global _BASE
    if _BASE is None:
        _BASE = _discover_base()
    return _BASE

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
        headers['Origin'] = origin()
        headers['x-operon-csrf'] = csrf()
    req = urllib.request.Request(base() + path, data=body, headers=headers, method='POST' if body else 'GET')
    try:
        with opener.open(req) as r:
            out = r.read().decode(); save()
            return r.status, out
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def patch(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(base() + path, data=body, method='PATCH', headers={
        'Content-Type': 'application/json', 'Origin': origin(), 'x-operon-csrf': csrf()})
    try:
        with opener.open(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def remote_login_url():
    """A single-use login link from the host, rewritten to the local end of the tunnel.

    The host prints a link to its own localhost:<port>. Posting that here would hit THIS machine's
    instance, which is a different account session and silently the wrong one, so the netloc is
    replaced with the tunnel's 127.0.0.1:<local port>. The link is valid for about three minutes.
    """
    out = _ssh([_remote_path(CS_REMOTE_BIN) + ' url'], timeout=60)
    if out.returncode != 0:
        sys.exit('could not mint a login link on {}: {}'.format(CS_HOST, out.stderr.strip()[:200]))
    found = re.search(r'http\S+', out.stdout or '')
    if not found:
        sys.exit('{} printed no login link: {}'.format(CS_HOST, (out.stdout or '').strip()[:200]))
    parts = urllib.parse.urlparse(found.group(0))
    return urllib.parse.urlunparse(parts._replace(netloc=urllib.parse.urlparse(base()).netloc))


def login():
    if CS_HOST:
        url = remote_login_url()
    else:
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
    if CS_HOST:
        # The grant is for a path on the host, so it is checked there. Unreadable counts as absent:
        # granting a read we cannot show exists is how a review comes back empty and convincing.
        kept = []
        for r in ok:
            if r.get('kind') != 'host':
                kept.append(r)
                continue
            there = host_has(r.get('target', ''))
            if there:
                kept.append(r)
            else:
                print('held: host {} is {} on {}; not granting a read of nothing. A review that '
                      'reads nothing looks like a review that found nothing.'
                      .format(r.get('target'), 'missing' if there is False else 'unverifiable',
                              CS_HOST))
        ok = kept
    if ok:
        code, out = call(f'/api/frames/{fid}/resolve-input', {'responses': [
            dict(requestId=r['requestId'], approved=True) if r.get('kind') == 'usage_checkpoint' else
            dict(requestId=r['requestId'], tool_id=r.get('tool_id'), approved=True, action='allow',
                 scope='always' if r.get('kind') in SCOPE_ALWAYS else scope,
                 **({'mode': 'ro'} if r.get('kind') == 'host' else {})) for r in ok]})
        if code != 200:
            sys.exit(f'HTTP {code}: {out[:300]}')
        # A 200 is not evidence the grant landed. 11-07: math's network approval and planets' host
        # prompts both came back "accepted" and changed nothing, and the session then sat pending
        # with nothing saying why. Whatever the cause, the check is the same: read the requests
        # back, and if one this call claimed to approve is still pending, say so loudly instead of
        # returning as though it worked. The one failure direction that wastes a whole session is
        # a tool reporting success for a request nobody granted.
        left = {r.get('requestId') for r in pending(fid)}
        ignored = [r for r in ok if r.get('requestId') in left]
        if ignored:
            kinds = ', '.join(sorted({str(r.get('kind')) for r in ignored}))
            sys.exit('resolve-input returned 200 and changed nothing: {} request(s) ({}) are still '
                     'pending. Claude Science accepted the call and ignored it, which usually means '
                     'the scope was wrong for the kind: it was sent as {!r}, and some kinds are only '
                     'granted with "always". Nothing was approved; re-run with --scope always, or '
                     'resolve it in the app.'.format(len(ignored), kinds, scope))
    return ok, pending(fid)


# Kinds this tool never answers, with what clears them. A held prompt is named the first time
# wait sees it, because 11-08 planets' review sat an hour on a contact_email prompt while
# `wait --approve` printed nothing: the session stays 'processing' while it waits for a click, so
# from outside a parked session and a working one looked the same.
HELD_HINT = {
    'network': 'network access waits for a person by design (Spend rule); allowed with scope '
               '"always".',
    'contact_email': "a contact address for NCBI/EBI/OurResearch is the owner's personal data, not a "
                     'lane call: answer it in the app, or ask general.',
}
WAIT_HELD_S = float(os.environ.get('CS_WAIT_HELD_S', '') or 600)


def describe(r):
    return '{} {} {}'.format(r.get('kind'), r.get('tool'),
                             str(r.get('code') or r.get('target', ''))[:200].replace('\n', ' '))


def wait(fid, timeout, auto, held_limit=None, sleep=time.sleep, now=time.time):
    """The session's final status, or 'parked' when a prompt this call will not answer has been
    pending for held_limit seconds (CS_WAIT_HELD_S, default 600). Waiting the full timeout on a
    prompt nobody is going to click is the failure; the caller decides what to do about it."""
    held_limit = WAIT_HELD_S if held_limit is None else held_limit
    end, seen = now() + timeout, {}
    while now() < end:
        cleared, left = approve(fid) if auto else ([], pending(fid))
        for r in left:
            if r.get('requestId') not in seen:
                seen[r.get('requestId')] = now()
                print('waiting on a person:', describe(r), file=sys.stderr)
                if r.get('kind') in HELD_HINT:
                    print('      ' + HELD_HINT[r.get('kind')], file=sys.stderr)
        ids = {r.get('requestId') for r in left}
        stuck = [r for r in left if now() - seen[r.get('requestId')] >= held_limit]
        if stuck:
            print('parked {:.0f} s on: {}'.format(held_limit, '; '.join(describe(r) for r in stuck)),
                  file=sys.stderr)
            return 'parked'
        for k in [k for k in seen if k not in ids]:
            del seen[k]
        if not cleared and frame(fid).get('status') != 'processing':
            break
        sleep(30)  # local daemon status check; no remote polling
    return frame(fid).get('status')


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
        print(pid, f'{base()}/projects/{pid}')
    elif cmd == 'instructions':
        code, out = patch(f'/api/projects/{pos[0]}', {'context': text_arg(pos[1])})  # the daemon's field is context; an 'instructions' key is silently ignored
        print(code, out[:200])
    elif cmd == 'archive':
        print(call(f'/api/projects/{pos[0]}/archive', {})[0])
    elif cmd == 'ask':
        pid, text = pos[0], text_arg(pos[1])
        r = post({'target_agent': 'OPERON', 'project_id': pid, 'input_data': {'request': text},
                  'model': model_for(pid, opts), 'effort': opts.get('effort', 'high'), 'thinking': True})
        print(r['root_frame_id'], f"{base()}/projects/{pid}/frames/{r['root_frame_id']}")
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
        status = wait(pos[0], float(opts.get('timeout', 7200)), '--approve' in rest)
        print(status)
        if status == 'parked':
            sys.exit(3)
        t = assistant_texts(pos[0]); print(t[-1] if t else '')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
