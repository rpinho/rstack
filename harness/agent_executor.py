#!/usr/bin/env python3
"""Build explicit backend commands; inherit authentication from the caller."""
import argparse
import itertools
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

import run_records
import run_costs


def _kill_tree(proc):
    """Stop the CLI and anything it started. A surviving child keeps spending."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()


DEFAULT_TOOLS = 'Read,Write,Edit'

# 11-19 Ricardo: "No pay-as-you-go. Do NOT top up OpenRouter. Route Theorizer, referee and
# model-scoring calls to the subscriptions." claude -p, codex exec and agy need no override; a
# metered API route runs only when the caller sets its flag, which exists to let work already in
# flight finish. There is no automatic failover from one to the other.
METERED = {'openrouter': 'RH_ALLOW_OPENROUTER', 'gemini': 'RH_ALLOW_GEMINI_API'}
AGY_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
AGY_SIGN_IN = "agy needs Ricardo's one-time interactive sign-in (run `agy` with no arguments, in a terminal)"
AGY_UNAUTH = 'agy unauthenticated from lanes: direct, tmux and gui all asked to sign in'
_AGY_GUI_SEQ = itertools.count(1)


def metered_refusal(provider, env=None):
    """None when the route may run; else why not. Subscriptions are never metered here."""
    env = os.environ if env is None else env
    flag = METERED.get(provider)
    if not flag or env.get(flag) == '1':
        return None
    return ('{} is pay-as-you-go and refused (Ricardo 11-19: subscriptions only, i.e. claude, codex or agy). '
            'Set {}=1 only to finish work already in flight.'.format(provider, flag))


CODEX_UNSET = ('OPENAI_API_KEY', 'OPENAI_BASE_URL')
CODEX_SANDBOXES = ('read-only', 'workspace-write', 'danger-full-access')


def codex_sandbox(mode=None):
    """How much a codex job may touch. Default `workspace-write`, as documented.

    11-07: this is the one real behavioural difference between this executor and the launcher the
    lanes actually run, which passes --dangerously-bypass-approvals-and-sandbox. Unifying the two
    launchers without noticing would have moved every lane job into a sandbox it has never run in,
    and these jobs write their transcript to -o OUTPUT, which sits outside the work dir. So the
    mode is a setting, with the safe value as the default: a public tool should not ship with the
    sandbox off, and a host that needs it off says so once.
    """
    import os
    mode = mode or os.environ.get('LAUNCH_CODEX_SANDBOX', 'workspace-write')
    if mode not in CODEX_SANDBOXES + ('bypass',):
        raise ValueError('LAUNCH_CODEX_SANDBOX must be one of: ' +
                         ', '.join(CODEX_SANDBOXES + ('bypass',)))
    return mode


def command(backend, executable, model, effort, directory, output, budget='1.00',
            tools=DEFAULT_TOOLS, sandbox=None, prompt=None):
    if backend == 'agy':
        # Gemini on the Antigravity subscription. The prompt is an argument: `agy -p PROMPT`.
        if prompt is None:
            raise ValueError('agy needs the prompt')
        return [executable, '-p', prompt, '--output-format', 'json',
                *(['--model', model] if model and model != 'default' else []),
                # A tier name such as gemini-3.8-flash-low is its effort; agy refuses a second one.
                *(['--effort', effort] if effort in AGY_EFFORTS
                  and not str(model).endswith(tuple('-' + e for e in AGY_EFFORTS)) else []),
                '--mode', 'accept-edits', '--disable-slash-commands',
                # Headless agy auto-denies what it cannot prompt for, reading files included (11-19: a
                # referee ran 213 s and wrote nothing). Reading is always allowed, as Read is for Claude;
                # shell commands only when the job's --allowed-tools include Bash. Session-only rules.
                '--settings', json.dumps({'permissions': {'allow': ['read_file(*)'] + (
                    ['command(*)'] if 'Bash' in str(tools).split(',') else [])}})]
    if backend == 'codex':
        mode = codex_sandbox(sandbox)
        # `bypass` is the single flag that turns off approvals AND the sandbox together; the other
        # values are --sandbox levels. They are not interchangeable spellings of the same thing.
        guard = (['--dangerously-bypass-approvals-and-sandbox'] if mode == 'bypass'
                 else ['--sandbox', mode])
        # 11-16 (bio): builders on a --host stalled at git clone in workspace-write, which has no network.
        # LAUNCH_CODEX_NETWORK=1 keeps the workspace sandbox and opens its network, instead of turning the
        # sandbox off. launch.sh forwards both settings to remote runs.
        if mode == 'workspace-write' and os.environ.get('LAUNCH_CODEX_NETWORK') == '1':
            guard += ['-c', 'sandbox_workspace_write.network_access=true']
        # 11-23: the shared package caches launch.sh sets live outside the work dir; the sandbox may write them.
        caches = [os.environ[k] for k in ('UV_CACHE_DIR', 'PIP_CACHE_DIR', 'npm_config_cache') if os.environ.get(k)]
        if mode == 'workspace-write' and caches:
            guard += ['-c', 'sandbox_workspace_write.writable_roots=' + json.dumps(caches)]
        provider = os.environ.get('LAUNCH_PROVIDER', '')
        if provider not in ('', 'openrouter', 'gemini'):
            raise ValueError('unsupported LAUNCH_PROVIDER')
        why = metered_refusal(provider)
        if why:
            raise ValueError(why)
        provider_args = (['-c', 'model_provider="openrouter"',
                         '-c', 'model_providers.openrouter.name="OpenRouter"',
                         '-c', 'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"',
                         '-c', 'model_providers.openrouter.wire_api="responses"',
                         '-c', 'model_providers.openrouter.env_key="OPENROUTER_API_KEY"']
                         if provider == 'openrouter' else [])
        if provider == 'gemini':
            provider_args = ['-c', 'model_provider="gemini"',
                '-c', 'model_providers.gemini.name="Gemini"',
                '-c', 'model_providers.gemini.base_url="https://generativelanguage.googleapis.com/v1beta/openai/"',
                '-c', 'model_providers.gemini.wire_api="responses"',
                '-c', 'model_providers.gemini.env_key="GEMINI_API_KEY"',
                '-c', 'model_providers.gemini.request_max_retries=0',
                '-c', 'model_providers.gemini.stream_max_retries=0',
                '-c', 'features.apps=false', '-c', 'features.multi_agent=false',
                '-c', 'web_search="disabled"']
        return [executable, 'exec', '--ignore-user-config', '--skip-git-repo-check',
                '--cd', str(directory), '-m', model, '-c', 'model_reasoning_effort='+effort,
                *provider_args, *guard,
                '-o', str(output), '-']
    if backend == 'claude':
        # `tools` widens what a job may do. The default is read/write/edit only: a research job
        # that has to run its own code needs more, and the caller says so explicitly rather than
        # every job getting it. There is no --max-turns on this CLI, so a run is bounded by
        # --max-budget-usd here and by --timeout-seconds in main().
        return [executable, '-p', '--model', model, '--effort', effort,
                '--output-format', 'json', '--max-budget-usd', budget,
                '--permission-mode', 'acceptEdits', '--allowedTools', tools,
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--setting-sources', '', '--disable-slash-commands',
                '--no-session-persistence']
    raise ValueError('AGENT_BACKEND must be codex, claude or agy')


def shim_first(home=None, which=None):
    """None when ~/.local/bin/osascript is absent or is what `osascript` resolves to; else the reason.
    11-12: a Codex job deleted through Finder and the owner heard it; the shim makes that a silent trash,
    and it only works when it is the osascript the job finds."""
    import shutil
    shim = Path(home or Path.home()) / '.local/bin/osascript'
    if not shim.exists():
        return None
    found = (which or shutil.which)('osascript')
    if found and Path(found).resolve() == shim.resolve():
        return None
    return ('osascript resolves to {}, not the shim {}; a Finder delete in this job would play the trash '
            'sound. Put ~/.local/bin first on PATH.'.format(found, shim))


AGY_NO_KEYCHAIN = ('agy has no keychain access here: its sign-in lives in the login Keychain, which an ssh or '
                   'launchd-daemon context cannot read. Run it from the m5 tmux or GUI session '
                   '(RH_AGY_TMUX_SESSION names the tmux session the executor relays through)')


def _agy_direct(cmd, directory, timeout_seconds):
    """(stdout bytes, exit code, saw "Authentication required", hit the clock). Ends at the first auth line:
    signed out (or without the Keychain), agy prints an OAuth URL and waits 60 s for a code nobody pastes."""
    signed_out, expired, said = threading.Event(), threading.Event(), []
    proc = subprocess.Popen(cmd, cwd=directory, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True,
                            env=dict(os.environ, RSTACK_UNATTENDED='1'))

    def watch_stderr():
        for line in iter(proc.stderr.readline, b''):
            if b'authentication required' in line.lower():
                signed_out.set()
                _kill_tree(proc)
                return
            said.append(line)
            sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()

    watcher = threading.Thread(target=watch_stderr, daemon=True)
    watcher.start()
    timer = None
    if timeout_seconds > 0:
        def stop():
            expired.set()
            _kill_tree(proc)
        timer = threading.Timer(timeout_seconds, stop)
        timer.daemon = True
        timer.start()
    try:
        data = proc.stdout.read()
        code = proc.wait()
    finally:
        if timer:
            timer.cancel()
    watcher.join(timeout=5)
    return data, code, signed_out.is_set(), expired.is_set(), b''.join(said)


def _tmux():
    import shutil
    for candidate in (os.environ.get('RH_AGY_TMUX'), shutil.which('tmux'),
                      str(Path.home() / '.local/bin/tmux'), '/opt/homebrew/bin/tmux'):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _agy_tmux(cmd, directory, timeout_seconds, poll=None):
    """Run agy in a new window of the host's tmux session, which holds the Keychain the GUI login
    unlocked, and read its result from files. None when there is no such session to relay through.

    11-19: signed in on the m5, agy answered from the tmux server and from a gui/ LaunchAgent, and said
    "authentication required" over plain ssh. A --host job and this executor's own sandbox are both
    ssh-like, so the call goes where the Keychain is instead. Only this job's window is added; it closes
    when agy exits and is killed on the clock or when this executor is stopped."""
    import shlex
    import shutil
    import tempfile
    poll = float(os.environ.get('RH_AGY_POLL', '0.5')) if poll is None else poll
    tmux = _tmux()
    session = os.environ.get('RH_AGY_TMUX_SESSION', 'base')
    if not tmux or subprocess.run([tmux, 'has-session', '-t', session], capture_output=True).returncode:
        return None
    exe = shutil.which(cmd[0]) or cmd[0]
    with tempfile.TemporaryDirectory(prefix='rh-agy-') as box:
        box = Path(box)
        prompt_at = cmd.index('-p') + 1
        (box / 'prompt').write_text(cmd[prompt_at])
        tail = ' ' + ' '.join(shlex.quote(a) for a in cmd[prompt_at + 1:]) if cmd[prompt_at + 1:] else ''
        args = (' '.join(shlex.quote(a) for a in [exe, *cmd[1:prompt_at]])
                + ' "$(cat {})"'.format(shlex.quote(str(box / 'prompt'))) + tail)
        (box / 'run.sh').write_text(
            'cd {d} || {{ echo 2 > {b}/rc.tmp; mv {b}/rc.tmp {b}/rc; exit; }}\n'
            'RSTACK_UNATTENDED=1 {a} < /dev/null > {b}/out 2> {b}/err\n'
            'echo $? > {b}/rc.tmp && mv {b}/rc.tmp {b}/rc\n'.format(d=shlex.quote(str(directory)), a=args,
                                                                    b=shlex.quote(str(box))))
        made = subprocess.run([tmux, 'new-window', '-d', '-P', '-F', '#{window_id}', '-t', session + ':',
                               '-n', 'rh-agy-{}'.format(os.getpid()), '/bin/sh ' + shlex.quote(str(box / 'run.sh'))],
                              capture_output=True, text=True)
        if made.returncode:
            return None
        window = made.stdout.strip()

        def close():
            subprocess.run([tmux, 'kill-window', '-t', window], capture_output=True)

        previous = signal.signal(signal.SIGTERM, lambda *_: (close(), sys.exit(143)))
        signed_out = expired = False
        began, seen = time.monotonic(), 0
        try:
            while not (box / 'rc').exists():
                err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
                if len(err) > seen:
                    chunk, seen = err[seen:], len(err)
                    if b'authentication required' in err.lower():
                        signed_out = True
                        close()
                        break
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
                if timeout_seconds > 0 and time.monotonic() - began > timeout_seconds:
                    expired = True
                    close()
                    break
                time.sleep(poll)
            err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
            if len(err) > seen:
                chunk = err[seen:]
                if b'authentication required' in err.lower():
                    signed_out = True
                else:
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
        finally:
            signal.signal(signal.SIGTERM, previous)
        data = (box / 'out').read_bytes() if (box / 'out').exists() else b''
        try:
            code = int((box / 'rc').read_text())
        except (OSError, ValueError):
            code = 1
        err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
        return data, code, signed_out, expired, err


def _launchctl():
    import shutil
    for candidate in (os.environ.get('RH_AGY_LAUNCHCTL'), shutil.which('launchctl'), '/bin/launchctl'):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _kill_pid_tree(pid):
    """Stop a detached agent pid (and its process group when distinct from ours)."""
    try:
        pgid = os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return
    own_pgid = os.getpgrp()
    targets = []
    if pgid != own_pgid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
    else:
        try:
            out = subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True, timeout=5)
            targets = [int(p) for p in out.stdout.split() if p.isdigit()]
        except (OSError, subprocess.SubprocessError):
            targets = []
        targets.append(pid)
        for p in targets:
            try:
                os.kill(p, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            break
        time.sleep(0.05)
    if pgid != own_pgid:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    else:
        for p in targets:
            try:
                os.kill(p, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass


def _agy_gui(cmd, directory, timeout_seconds, poll=None):
    """Run agy via a one-shot LaunchAgent bootstrapped into the user's Aqua session (gui/<uid>),
    which holds the login Keychain even when an agy binary update drops tmux's Keychain trust.
    None when launchctl is absent or cannot bootstrap into gui/<uid>."""
    import plistlib
    import shlex
    import shutil
    import tempfile
    poll = float(os.environ.get('RH_AGY_POLL', '0.5')) if poll is None else poll
    launchctl = _launchctl()
    if not launchctl:
        return None
    exe = shutil.which(cmd[0]) or cmd[0]
    uid = os.getuid()
    domain = 'gui/{}'.format(uid)
    label = 'com.ricardo.agy-call.{}.{}'.format(os.getpid(), next(_AGY_GUI_SEQ))
    target = '{}/{}'.format(domain, label)
    path_parts = [p for p in os.environ.get('PATH', '').split(':') if p]
    for extra in (str(Path.home() / '.local/bin'), '/opt/homebrew/bin', '/usr/bin', '/bin'):
        if extra not in path_parts:
            path_parts.append(extra)
    run_path = ':'.join(path_parts)
    with tempfile.TemporaryDirectory(prefix='rh-agy-gui-') as tmp:
        box = Path(tmp)
        os.chmod(box, 0o700)
        prompt_at = cmd.index('-p') + 1
        prompt_file = box / 'prompt'
        prompt_file.write_text(cmd[prompt_at])
        os.chmod(prompt_file, 0o600)
        tail = ' ' + ' '.join(shlex.quote(a) for a in cmd[prompt_at + 1:]) if cmd[prompt_at + 1:] else ''
        args = (' '.join(shlex.quote(a) for a in [exe, *cmd[1:prompt_at]])
                + ' "$(cat {})"'.format(shlex.quote(str(prompt_file))) + tail)
        run_sh = box / 'run.sh'
        run_sh.write_text(
            '#!/bin/sh\n'
            'export PATH={p}\n'
            'echo $$ > {b}/sh.pid.tmp && mv {b}/sh.pid.tmp {b}/sh.pid\n'
            'cd {d} || {{ echo 2 > {b}/rc.tmp; mv {b}/rc.tmp {b}/rc; exit 2; }}\n'
            'child=\n'
            'trap \'[ -n "$child" ] && kill -TERM "$child" 2>/dev/null; exit 143\' TERM INT HUP\n'
            'RSTACK_UNATTENDED=1 {a} < /dev/null > {b}/out 2> {b}/err &\n'
            'child=$!\n'
            'echo "$child" > {b}/pid.tmp && mv {b}/pid.tmp {b}/pid\n'
            'wait "$child"\n'
            'echo $? > {b}/rc.tmp && mv {b}/rc.tmp {b}/rc\n'.format(
                p=shlex.quote(run_path), d=shlex.quote(str(directory)), a=args, b=shlex.quote(str(box))))
        os.chmod(run_sh, 0o700)
        plist_path = box / (label + '.plist')
        plist_path.write_bytes(plistlib.dumps({
            'Label': label,
            'ProgramArguments': ['/bin/sh', str(run_sh)],
            'RunAtLoad': True,
            'LimitLoadToSessionType': 'Aqua',
        }))
        os.chmod(plist_path, 0o600)

        booted_out = False

        def cleanup(kill_procs=False):
            nonlocal booted_out
            if not booted_out:
                booted_out = True
                try:
                    subprocess.run([launchctl, 'bootout', target], capture_output=True, timeout=15)
                except (OSError, subprocess.SubprocessError):
                    pass
            if kill_procs:
                for name in ('pid', 'sh.pid'):
                    try:
                        pid = int((box / name).read_text().strip())
                    except (OSError, ValueError):
                        continue
                    _kill_pid_tree(pid)

        try:
            boot = subprocess.run([launchctl, 'bootstrap', domain, str(plist_path)],
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            cleanup(kill_procs=True)
            return None
        if boot.returncode:
            cleanup(kill_procs=False)
            return None

        def on_term(signum, _frame):
            cleanup(kill_procs=True)
            raise SystemExit(128 + signum)

        previous = signal.signal(signal.SIGTERM, on_term)
        signed_out = expired = False
        began, seen = time.monotonic(), 0
        try:
            while not (box / 'rc').exists():
                err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
                if len(err) > seen:
                    chunk, seen = err[seen:], len(err)
                    if b'authentication required' in err.lower():
                        signed_out = True
                        break
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
                if timeout_seconds > 0 and time.monotonic() - began > timeout_seconds:
                    expired = True
                    break
                time.sleep(poll)
            err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
            if len(err) > seen:
                chunk = err[seen:]
                if b'authentication required' in err.lower():
                    signed_out = True
                else:
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
        finally:
            signal.signal(signal.SIGTERM, previous)
            cleanup(kill_procs=signed_out or expired or not (box / 'rc').exists())
        data = (box / 'out').read_bytes() if (box / 'out').exists() else b''
        try:
            code = int((box / 'rc').read_text())
        except (OSError, ValueError):
            code = 1
        err = (box / 'err').read_bytes() if (box / 'err').exists() else b''
        return data, code, signed_out, expired, err


# 11-19: agy has a 5-hour refresh and a weekly cap with no published numbers, so every 429 or quota error
# is kept, to learn the real limits. AI Credit Overages stays "Never": nothing here buys more.


def log_agy_quota(cmd, text):
    """Append the row (with blocked_until and its 5h/weekly window when agy names a reset), and print it as an
    AGY_QUOTA line: the job log carries it to the controller, whose picker and grader read it (11-20)."""
    import datetime as dt
    import agy_quota
    model, tier = _agy_model_effort(cmd, None)
    row = agy_quota.annotate(dict(
        utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), model=model, tier=tier,
        job=os.environ.get('RH_JOB') or os.environ.get('RSTACK_LANE') or '', error=' '.join(text.split())[:500]))
    print(agy_quota.MARK + json.dumps(row, sort_keys=True), file=sys.stderr)
    try:
        agy_quota.record(row)
    except OSError as exc:
        print('agent_executor: could not log the agy quota error: {}'.format(exc), file=sys.stderr)


def _warn_agy_auth(reason=AGY_UNAUTH):
    """RULE #1: log a fail-open warning row when no agy route authenticates."""
    try:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import harness_blocks
        harness_blocks.warn('agy.auth', reason, fix=AGY_SIGN_IN)
    except Exception:
        pass


def agy_chain(cmd, directory, timeout_seconds=0):
    """Try direct, then tmux, then Aqua gui when agy asks to authenticate.

    Returns (route, data, code, signed_out, expired, err, relayed). `route` is 'direct', 'tmux',
    'gui', or None when no route authenticated."""
    data, code, signed_out, expired, err = _agy_direct(cmd, directory, timeout_seconds)
    route, relayed = 'direct', False
    if signed_out:
        again = _agy_tmux(cmd, directory, timeout_seconds)
        if again is not None:
            relayed = True
            route = 'tmux'
            data, code, signed_out, expired, err = again
    if signed_out:
        again = _agy_gui(cmd, directory, timeout_seconds)
        if again is not None:
            relayed = True
            route = 'gui'
            data, code, signed_out, expired, err = again
    if signed_out:
        route = None
    return route, data, code, signed_out, expired, err, relayed


def _agy_model_effort(cmd, fallback=''):
    model = cmd[cmd.index('--model') + 1] if '--model' in cmd else 'default'
    tier = next((t for t in AGY_EFFORTS if model.endswith('-' + t)), None)
    if not tier and '--effort' in cmd:
        tier = cmd[cmd.index('--effort') + 1]
    return model, tier or fallback


def reported_usage(output, errors=''):
    tokens, cost = None, None
    try:
        text = Path(output).read_text(errors='replace')
    except OSError:
        text = ''
    text += '\n' + errors
    for line in [text.strip(), *text.splitlines()]:
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        usage = data.get('usage') or {}
        if isinstance(usage, dict):
            values = [usage[k] for k in ('input_tokens', 'output_tokens') if type(usage.get(k)) is int]
            if values:
                tokens = sum(values)
            elif type(usage.get('total_tokens')) is int:
                tokens = usage['total_tokens']
        if type(data.get('total_cost_usd')) in (int, float):
            cost = data['total_cost_usd']
    found = re.search(r'tokens used\s*\n\s*([\d,]+)', errors)
    if tokens is None and found:
        tokens = int(found.group(1).replace(',', ''))
    return dict(tokens=tokens, cost_usd=cost)


def record_run(backend, model, effort, directory, output, rc, quota='', errors=''):
    launch_id = os.environ.get('RH_LAUNCH_RUN_ID')
    run_id = launch_id or uuid.uuid4().hex
    lane = os.environ.get('RSTACK_LANE', '')
    row = dict(
        run_id=run_id, utc=run_records.utc_now(),
        job=os.environ.get('RH_JOB') or os.environ.get('AGENT_JOB') or lane or Path(directory).name,
        backend=backend, model=model, effort=effort or 'default', rc=int(rc), transcript=str(output),
        lane=lane, workdir=str(Path(directory).resolve()), role=os.environ.get('RSTACK_CALL_ROLE') or 'batch')
    for key, env in [('grade_ledger', 'RH_LAUNCH_GRADE_LEDGER'), ('driver', 'RH_LAUNCH_DRIVER'),
                     ('launch_group', 'RH_LAUNCH_GROUP')]:
        if launch_id and os.environ.get(env):
            row[key] = os.environ[env]
    if quota:
        row['reason'] = 'quota'
        # The launcher sees this marker even when the executor ran via its existing SSH route.
        print('EXECUTOR_QUOTA ' + run_id, file=sys.stderr)
    try:
        existing = next((r for r in run_records.read_jsonl(run_records.runs_path()) if r.get('run_id') == run_id), None)
        if existing is None:
            existing = run_records.open_run(row)
        usage = reported_usage(output, errors)
        closed_at = run_records.utc_now()
        # Save the breakdown while the output still belongs to this attempt.
        # For a remote run, forward the counters with the existing outcome summary.
        candidate = dict(existing, **usage)
        candidate.update(transcript=str(Path(output).absolute()), closed_at=closed_at)
        if not run_records.is_probe(existing):
            measured = run_costs.tokens_for(candidate)
            if measured is not None:
                usage['token_usage'] = measured
        usage['transcript'] = candidate['transcript']
        usage['closed_at'] = closed_at
        closed = run_records.close_run(run_id, rc=int(rc), reason='quota' if quota else '', **usage)
        if closed:
            summary = {key: closed.get(key) for key in
                       ('run_id', 'closed_at', 'wall_seconds', 'tokens', 'cost_usd', 'token_usage', 'rc')}
            print('EXECUTOR_RUN ' + json.dumps(summary), file=sys.stderr)
        if quota:
            run_records.record_quota(dict(row, utc=existing['utc'] if existing else row['utc']), quota)
        if not launch_id or os.environ.get('RH_EXECUTOR_STANDALONE') == '1':
            probe = run_records.is_probe(closed or existing or row)
            reason = 'probe' if probe else 'quota' if quota else 'no launcher acceptance checks'
            grade = run_records.grade_fields(run_id, row['job'], model, row['role'], 'void: ' + reason, reason,
                                             cost_usd=run_records.grade_cost(run_id, closed))
            run_records.append(run_records.grades_path(), grade)
    except OSError as exc:
        run_records.warn(exc)


def run_agy(cmd, directory, output, timeout_seconds=0, effort=''):
    """Run agy print mode; its JSON result goes to `output`.

    Direct first; if agy asks to authenticate, relay through tmux, then a one-shot Aqua LaunchAgent
    (gui/<uid>) that can read the login Keychain. That relay is the same call in another place, never
    another model. When no route authenticates, log a harness_blocks warn row and fail with a clear
    sign-in message."""
    route, data, code, signed_out, expired, err, relayed = agy_chain(cmd, directory, timeout_seconds)
    Path(output).write_bytes(data)
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    try:
        result = json.loads(data.decode() or 'null')
    except ValueError:
        result = None
    error = str(result.get('error') or '') if isinstance(result, dict) else ''
    rc = code
    if signed_out or 'authentication' in error.lower():
        _warn_agy_auth()
        if relayed or not signed_out:
            print('agent_executor: {}; {}'.format(AGY_UNAUTH, AGY_SIGN_IN), file=sys.stderr)
            rc = 77
        else:
            print('agent_executor: {} ({})'.format(AGY_UNAUTH, AGY_NO_KEYCHAIN), file=sys.stderr)
            rc = 76
    elif expired:
        print('wall-clock cap of {:g}s reached; stopped'.format(timeout_seconds), file=sys.stderr)
        rc = 124
    else:
        if route:
            print('agent_executor: agy route=' + route, file=sys.stderr)
        if code == 0 and (not isinstance(result, dict) or result.get('status') == 'ERROR' or error):
            print('agy returned an error result' + (': ' + error if error else ''), file=sys.stderr)
            rc = 1
        elif code == 0 and not str(result.get('response') or '').strip() and result.get('denied_actions'):
            print('agy produced nothing; it was denied: ' + ', '.join(
                str(d.get('action')) for d in result['denied_actions'] if isinstance(d, dict)), file=sys.stderr)
            rc = 1
    quota = run_records.quota_message('agy', err.decode(errors='replace') + '\n' + error) if rc else ''
    if quota:
        log_agy_quota(cmd, quota)
    model, tier = _agy_model_effort(cmd, effort)
    record_run('agy', model, tier, directory, output, rc, quota)
    return rc


def relay_errors(proc, tail):
    def copy():
        with proc.stderr as stream:
            for block in iter(lambda: stream.read1(65536), b''):
                tail.extend(block)
                del tail[:-16384]
                sys.stderr.buffer.write(block)
                sys.stderr.buffer.flush()
    thread = threading.Thread(target=copy, daemon=True)
    thread.start()
    return thread


def run_codex(cmd, args, env, errors):
    # Existing callers leave Codex's clock alone. An effort-floor job shares one wall budget
    # across calls, including the first call when it uses all of that budget itself.
    if not env.get('RH_EFFORT_FLOOR_JOB') or args.timeout_seconds <= 0:
        with subprocess.Popen(cmd, cwd=args.directory, env=env, stderr=subprocess.PIPE) as proc:
            relay = relay_errors(proc, errors)
            rc = proc.wait()
            relay.join(timeout=1)
            return rc
    def stopped(signum, _frame):
        # 11-23 (math_leanshadow_1123): a job exited 143 and nothing recorded which process got the signal.
        # This line says it was the executor, not Codex, and when, so the sender can be matched in the logs.
        print('agent_executor: received {} at {} (pid {}, parent {}); stopping Codex'.format(
            signal.Signals(signum).name, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            os.getpid(), os.getppid()), file=sys.stderr, flush=True)
        raise SystemExit(128 + signum)

    stop_signals = (signal.SIGTERM, signal.SIGHUP)
    handlers = {sig: signal.signal(sig, stopped) for sig in stop_signals}
    try:
        with subprocess.Popen(cmd, cwd=args.directory, env=env, start_new_session=True,
                              stderr=subprocess.PIPE) as proc:
            relay = relay_errors(proc, errors)
            try:
                return proc.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                print('wall-clock cap of {:g}s reached; stopped'.format(args.timeout_seconds), file=sys.stderr)
                return 124
            finally:
                if proc.poll() is None:
                    _kill_tree(proc)
                relay.join(timeout=1)
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('codex', 'claude', 'agy'), required=True)
    p.add_argument('--executable', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--effort', required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--budget', default='1.00')
    p.add_argument('--allowed-tools', default=DEFAULT_TOOLS,
                   help='claude only: --allowedTools value. The default is read/write/edit; a '
                        'job that must run its own code needs more, and says so here.')
    p.add_argument('--timeout-seconds', type=float, default=0,
                   help='wall-clock cap; 0 means none. This CLI has no --max-turns, so a run '
                        'is bounded by spend and by the clock.')
    a = p.parse_args(argv)
    # Persist before provider validation, stdin reads, or process creation.
    launch_id = os.environ.get('RH_LAUNCH_RUN_ID')
    ident = launch_id or uuid.uuid4().hex
    os.environ['RH_LAUNCH_RUN_ID'] = ident
    a.standalone = not launch_id
    try:
        run_records.open_run(dict(run_id=ident, utc=run_records.utc_now(),
            job=os.environ.get('RH_JOB') or os.environ.get('AGENT_JOB') or os.environ.get('RSTACK_LANE') or Path(a.directory).name,
            lane=os.environ.get('RSTACK_LANE', ''),
            model=a.model, effort=a.effort, backend=a.backend, workdir=str(a.directory.resolve()),
            transcript=str(a.output), role=os.environ.get('RSTACK_CALL_ROLE') or 'batch',
            **{key: os.environ[env] for key, env in [('grade_ledger', 'RH_LAUNCH_GRADE_LEDGER'),
                ('driver', 'RH_LAUNCH_DRIVER'), ('launch_group', 'RH_LAUNCH_GROUP')]
               if os.environ.get(env)}))
    except OSError as exc:
        run_records.warn(exc)
    if a.standalone:
        os.environ['RH_EXECUTOR_STANDALONE'] = '1'
    why = shim_first()
    if why:
        print('agent_executor refused: ' + why, file=sys.stderr)
        run_records.close_run(ident, rc=78)
        return 78
    try:
        cmd = command(a.backend, a.executable, a.model, a.effort, a.directory, a.output, a.budget,
                      a.allowed_tools, prompt=sys.stdin.read() if a.backend == 'agy' else None)
    except ValueError as exc:
        print('agent_executor refused: ' + str(exc), file=sys.stderr)
        run_records.close_run(ident, rc=78)
        return 78
    if a.backend == 'agy':
        try:
            return run_agy(cmd, a.directory, a.output, a.timeout_seconds, a.effort)
        except OSError:
            model, tier = _agy_model_effort(cmd, a.effort)
            record_run('agy', model, tier, a.directory, a.output, 1)
            raise
    errors = bytearray()
    rc, quota = 1, ''
    try:
        rc = run_backend(cmd, a, errors)
    except SystemExit as exc:
        rc = exc.code
        raise
    finally:
        if rc:
            quota = run_records.quota_message(a.backend, errors.decode(errors='replace'))
        if rc and a.backend == 'claude' and not quota:
            quota = claude_quota(a.output)
        record_run(a.backend, a.model, a.effort, a.directory, a.output, rc, quota, errors.decode(errors='replace'))
    return rc


def claude_quota(output):
    try:
        text = output.read_text(errors='replace')
    except OSError:
        return ''
    try:
        result = json.loads(text)
    except ValueError:
        return run_records.quota_message('claude', text)
    if isinstance(result, dict) and (result.get('is_error') or result.get('subtype') != 'success'):
        message = '\n'.join(str(result.get(k) or '') for k in ('subtype', 'result', 'error', 'errors'))
        return run_records.quota_message('claude', message)
    return ''


def run_backend(cmd, a, errors):
    if a.backend == 'codex':
        # No OpenAI API key or base URL reaches codex: with one in the environment it can bill the API instead of
        # the subscription (11-19: no pay-as-you-go). The lanes' launcher has run codex this way since 10-18.
        env = {k: v for k, v in os.environ.items() if k not in CODEX_UNSET}
        if os.environ.get('LAUNCH_PROVIDER') == 'gemini':
            from gemini_transport import bridge
            if not os.environ.get('GEMINI_API_KEY'):
                print('agent_executor: missing GEMINI_API_KEY', file=sys.stderr)
                return 2
            # Current Codex supports only Responses; Google exposes Chat Completions.
            with bridge() as base_url:
                cmd[-1:-1] = ['-c', 'model_providers.gemini.base_url=' + json.dumps(base_url)]
                return run_codex(cmd, a, env, errors)
        return run_codex(cmd, a, env, errors)
    # Preserve the provider's JSON result, including usage and budget errors.
    expired = threading.Event()
    # 11-27 (math): the result streams to a side file and lands at --output only when the CLI exits, so a
    # watcher on JOB.last.md never fires on an empty file at the job's start (Codex writes it only at the end).
    partial = a.output.with_name(a.output.name + '.partial')
    with partial.open('wb') as out:
        # Its own session, so the wall-clock kill signals the CLI's process group and not ours.
        # Without this, getpgid(child) is our own group and the cap would kill the launcher
        # instead of the job.
        # 11-11: a hook's `ask` prompts even with permissions bypassed, and nobody answers a headless
        # job, so it would stall. RSTACK_UNATTENDED turns every rstack hook's ask into a deny with a reason.
        proc = subprocess.Popen(cmd, cwd=a.directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True, env=dict(os.environ, RSTACK_UNATTENDED='1'))
        relay = relay_errors(proc, errors)
        # A watchdog rather than a check inside the read loop: stdout.read(65536) blocks until
        # the buffer fills or the process exits, so a job that goes quiet and hangs never
        # reaches a check placed in that loop. This fires on the clock either way.
        timer = None
        if a.timeout_seconds > 0:
            def stop():
                expired.set()
                _kill_tree(proc)
            timer = threading.Timer(a.timeout_seconds, stop)
            timer.daemon = True
            timer.start()
        try:
            for block in iter(lambda: proc.stdout.read(65536), b''):
                out.write(block)
                sys.stdout.buffer.write(block)
                sys.stdout.buffer.flush()
            code = proc.wait()
            relay.join(timeout=1)
        finally:
            if timer:
                timer.cancel()
            os.replace(partial, a.output)
    if expired.is_set():
        print('wall-clock cap of {:g}s reached; stopped'.format(a.timeout_seconds),
              file=sys.stderr)
        return 124
    if code == 0:
        try:
            result = json.loads(a.output.read_text())
        except ValueError:
            print('Claude returned invalid result JSON', file=sys.stderr)
            return 1
        if result.get('is_error') or result.get('subtype') != 'success':
            return 1
    return code


if __name__ == '__main__':
    raise SystemExit(main())
