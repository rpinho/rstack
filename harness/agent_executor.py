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
            tools=DEFAULT_TOOLS, sandbox=None):
    if backend == 'codex':
        mode = codex_sandbox(sandbox)
        # `bypass` is the single flag that turns off approvals AND the sandbox together; the other
        # values are --sandbox levels. They are not interchangeable spellings of the same thing.
        guard = (['--dangerously-bypass-approvals-and-sandbox'] if mode == 'bypass'
                 else ['--sandbox', mode])
        return [executable, 'exec', '--ignore-user-config', '--skip-git-repo-check',
                '--cd', str(directory), '-m', model, '-c', 'model_reasoning_effort='+effort,
                *guard, '-o', str(output), '-']
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
    raise ValueError('AGENT_BACKEND must be codex or claude')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('codex', 'claude'), required=True)
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
    cmd = command(a.backend, a.executable, a.model, a.effort, a.directory, a.output, a.budget,
                  a.allowed_tools)
    if a.backend == 'codex':
        return subprocess.call(cmd, cwd=a.directory)
    # Preserve the provider's JSON result, including usage and budget errors.
    expired = threading.Event()
    with a.output.open('wb') as out:
        # Its own session, so the wall-clock kill signals the CLI's process group and not ours.
        # Without this, getpgid(child) is our own group and the cap would kill the launcher
        # instead of the job.
        proc = subprocess.Popen(cmd, cwd=a.directory, stdout=subprocess.PIPE,
                                start_new_session=True)
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
