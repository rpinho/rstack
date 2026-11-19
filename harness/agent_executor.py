#!/usr/bin/env python3
"""Build explicit backend commands; inherit authentication from the caller."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading


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


def metered_refusal(provider, env=None):
    """None when the route may run; else why not. Subscriptions are never metered here."""
    env = os.environ if env is None else env
    flag = METERED.get(provider)
    if not flag or env.get(flag) == '1':
        return None
    return ('{} is pay-as-you-go and refused (Ricardo 11-19: subscriptions only, i.e. claude, codex or agy). '
            'Set {}=1 only to finish work already in flight.'.format(provider, flag))


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
                *(['--effort', effort] if effort in AGY_EFFORTS else []),
                '--mode', 'accept-edits', '--disable-slash-commands']
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
                *(['-c', 'service_tier=priority'] if os.environ.get('LAUNCH_URGENT', '').strip() else []),
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


def run_agy(cmd, directory, output, timeout_seconds=0):
    """Run agy print mode; its JSON result goes to `output`.

    Signed out, agy prints an OAuth URL and waits 60 s for a pasted code. Nobody answers a headless
    job, and signing in is Ricardo's, so the first "Authentication required" line ends the run.
    """
    signed_out, expired = threading.Event(), threading.Event()
    proc = subprocess.Popen(cmd, cwd=directory, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True,
                            env=dict(os.environ, RSTACK_UNATTENDED='1'))

    def watch_stderr():
        for line in iter(proc.stderr.readline, b''):
            if b'authentication required' in line.lower():
                signed_out.set()
                _kill_tree(proc)
                return
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
    Path(output).write_bytes(data)
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    try:
        result = json.loads(data.decode() or 'null')
    except ValueError:
        result = None
    error = str(result.get('error') or '') if isinstance(result, dict) else ''
    if signed_out.is_set() or 'authentication' in error.lower():
        print('agent_executor: ' + AGY_SIGN_IN, file=sys.stderr)
        return 77
    if expired.is_set():
        print('wall-clock cap of {:g}s reached; stopped'.format(timeout_seconds), file=sys.stderr)
        return 124
    if code == 0 and (not isinstance(result, dict) or result.get('status') == 'ERROR' or error):
        print('agy returned an error result' + (': ' + error if error else ''), file=sys.stderr)
        return 1
    return code


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
    why = shim_first()
    if why:
        print('agent_executor refused: ' + why, file=sys.stderr)
        return 78
    try:
        cmd = command(a.backend, a.executable, a.model, a.effort, a.directory, a.output, a.budget,
                      a.allowed_tools, prompt=sys.stdin.read() if a.backend == 'agy' else None)
    except ValueError as exc:
        print('agent_executor refused: ' + str(exc), file=sys.stderr)
        return 78
    if a.backend == 'agy':
        return run_agy(cmd, a.directory, a.output, a.timeout_seconds)
    if a.backend == 'codex':
        if os.environ.get('LAUNCH_PROVIDER') == 'gemini':
            from gemini_transport import bridge
            if not os.environ.get('GEMINI_API_KEY'):
                print('agent_executor: missing GEMINI_API_KEY', file=sys.stderr)
                return 2
            # Current Codex supports only Responses; Google exposes Chat Completions.
            with bridge() as base_url:
                cmd[-1:-1] = ['-c', 'model_providers.gemini.base_url=' + json.dumps(base_url)]
                return subprocess.call(cmd, cwd=a.directory)
        return subprocess.call(cmd, cwd=a.directory)
    # Preserve the provider's JSON result, including usage and budget errors.
    expired = threading.Event()
    with a.output.open('wb') as out:
        # Its own session, so the wall-clock kill signals the CLI's process group and not ours.
        # Without this, getpgid(child) is our own group and the cap would kill the launcher
        # instead of the job.
        # 11-11: a hook's `ask` prompts even with permissions bypassed, and nobody answers a headless
        # job, so it would stall. RSTACK_UNATTENDED turns every rstack hook's ask into a deny with a reason.
        proc = subprocess.Popen(cmd, cwd=a.directory, stdout=subprocess.PIPE,
                                start_new_session=True, env=dict(os.environ, RSTACK_UNATTENDED='1'))
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
        finally:
            if timer:
                timer.cancel()
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
