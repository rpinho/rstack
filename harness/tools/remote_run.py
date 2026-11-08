#!/usr/bin/env python3
"""Run a --host job's executor detached on the host, so it outlives this machine's ssh session.

Why (2026-11-08). launch.sh ran the remote executor as the foreground command of one ssh session,
so the job lived exactly as long as that connection. On 11-07 a Tailscale blip ended math's
codetables job after five hours ("Timeout, server not responding", exit 255). The same night this
controller ran out of memory and reset at 22:16, and every job on the compute host died with its
driver here: the host was idle all night with nothing wrong with it. A job that needs a network link
to stay up for five hours is a job that will be lost.

So the executor is started on the host under nohup, with its stdin, stdout and stderr in files
there, and a watcher shell that writes its exit code when it ends. This side only polls: it streams
the host's output into the local log as it arrives and returns the executor's exit code. A dropped
connection is retried, not fatal. And because the attempt is recorded in a state file next to the
log, a launcher that is restarted (the job watchdog resumes jobs after a reset) reattaches to an
attempt that is still running, or collects one that finished while nobody was watching, instead of
starting a second copy of the same job beside the first.

    remote_run.py --host H --job JOB --log LOG --prompt PROMPT --command CMDFILE --state STATE

CMDFILE is the remote shell program the launcher built (cd to the work dir, the pid marker, then
`exec` the executor). It reaches the host over stdin, so it is never re-quoted. The executor reads
PROMPT on its stdin, as before. Exit status: the executor's, or 255 when the attempt was lost on
the host or the host stayed unreachable for LAUNCH_REMOTE_UNREACHABLE_S (default 12 h).

Settings: LAUNCH_SSH (default ssh), LAUNCH_REMOTE_ATTEMPTS (where attempts live on the host, relative
to the host's $HOME unless absolute; default .local/state/research-harness/remote-attempts),
LAUNCH_REMOTE_POLL_S (default 15).
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

DEFAULT_ROOT = '.local/state/research-harness/remote-attempts'


def root_expr(root):
    """The attempts root as a remote shell expression: $HOME must expand THERE, not here."""
    if root.startswith('/'):
        return shlex.quote(root)
    return '"$HOME"/' + shlex.quote(root)


class Host:
    def __init__(self, host, ssh, root):
        self.host, self.ssh, self.root = host, shlex.split(ssh), root_expr(root)

    def run(self, program, stdin=b'', timeout=120):
        """(returncode, stdout bytes), or None when ssh itself failed."""
        argv = self.ssh + ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20',
                           '-o', 'ServerAliveInterval=30', self.host, program]
        try:
            out = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode == 255:
            return None
        return out.returncode, out.stdout

    def dir(self, job, attempt):
        return 'd={}/{}/{}'.format(self.root, shlex.quote(job), shlex.quote(attempt))

    def start(self, job, attempt, prompt, command):
        """Stage the prompt and the program, then start the watcher detached. True when started."""
        d = self.dir(job, attempt)
        steps = [
            (d + '; mkdir -p "$d" && cat > "$d/prompt" && echo OK', prompt),
            (d + '; cat > "$d/run.sh" && echo OK', command),
            # The watcher runs the program, then records its exit code atomically. Everything it
            # holds is a file or /dev/null, so nothing ties it to this ssh session, and the session
            # can close as soon as it is started.
            (d + '; cd / && nohup /bin/sh -c \'/bin/sh "$1/run.sh" < "$1/prompt" > "$1/out.log" '
                 '2>&1; echo $? > "$1/rc.tmp"; mv "$1/rc.tmp" "$1/rc"\' sh "$d" '
                 '> /dev/null 2>&1 < /dev/null & echo $! > "$d/watcher.pid"; echo OK', b''),
        ]
        for program, data in steps:
            got = self.run(program, stdin=data)
            if got is None or got[0] != 0 or b'OK' not in got[1]:
                return False
        return True

    def status(self, job, attempt):
        """'rc=N', 'running', 'lost' (dir there, watcher gone, no rc), 'none', or None (unreachable)."""
        program = (self.dir(job, attempt) + '; if [ -f "$d/rc" ]; then echo "rc=$(cat "$d/rc")"; '
                   'elif [ -f "$d/watcher.pid" ] && kill -0 "$(cat "$d/watcher.pid")" 2>/dev/null; '
                   'then echo running; elif [ -d "$d" ]; then echo lost; else echo none; fi')
        got = self.run(program)
        if got is None or got[0] != 0:
            return None
        words = got[1].decode(errors='replace').split()
        return words[-1] if words else None

    def output(self, job, attempt, offset):
        """New bytes of the host's out.log after `offset`, or None when unreachable."""
        got = self.run(self.dir(job, attempt) + '; tail -c +{} "$d/out.log" 2>/dev/null; true'
                       .format(int(offset) + 1), timeout=300)
        return None if got is None else got[1]


def load_state(path, host):
    try:
        state = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return state if state.get('host') == host and state.get('attempt') else None


def save_state(path, state):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(state))
    tmp.replace(path)


def note(log, text):
    with open(log, 'a') as fh:
        fh.write('remote-run: {} {}\n'.format(text, time.strftime('%a %b %e %H:%M:%S %Z %Y')))


def pull(host, state, log, path):
    chunk = host.output(state['job'], state['attempt'], state['offset'])
    if chunk:
        with open(log, 'ab') as fh:
            fh.write(chunk)
        state['offset'] += len(chunk)
        save_state(path, state)
    return chunk is not None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    for name in ('--host', '--job', '--log', '--prompt', '--command', '--state'):
        ap.add_argument(name, required=True)
    a = ap.parse_args(argv)
    host = Host(a.host, os.environ.get('LAUNCH_SSH', 'ssh'),
                os.environ.get('LAUNCH_REMOTE_ATTEMPTS', DEFAULT_ROOT))
    poll = float(os.environ.get('LAUNCH_REMOTE_POLL_S', '') or 15)
    give_up = float(os.environ.get('LAUNCH_REMOTE_UNREACHABLE_S', '') or 12 * 3600)

    state = load_state(a.state, a.host)
    if state:
        st = host.status(state['job'], state['attempt'])
        if st == 'running' or st is None or (st or '').startswith('rc='):
            # Running, finished while nobody was watching, or not answering yet: in every case the
            # attempt that exists is the one to follow. Starting another beside it is the failure.
            note(a.log, 'reattached to attempt {} on {} ({})'.format(
                state['attempt'], a.host, st or 'host not answering yet'))
        else:
            note(a.log, 'previous attempt {} on {} is {}; starting a new one'.format(
                state['attempt'], a.host, st))
            state = None
    if not state:
        state = dict(host=a.host, job=a.job, attempt=time.strftime('%Y%m%dT%H%M%S-') +
                     uuid.uuid4().hex[:6], offset=0)
        save_state(a.state, state)
        if not host.start(a.job, state['attempt'], Path(a.prompt).read_bytes(),
                          Path(a.command).read_bytes()):
            note(a.log, 'could not start the executor on {}'.format(a.host))
            Path(a.state).unlink(missing_ok=True)
            return 255
        note(a.log, 'executor started detached on {} as attempt {}'.format(a.host,
                                                                            state['attempt']))

    unreachable_since = None
    lost_once = False
    while True:
        st = host.status(state['job'], state['attempt'])
        if st is None:
            unreachable_since = unreachable_since or time.time()
            if time.time() - unreachable_since > give_up:
                note(a.log, '{} unreachable for {:.0f} s; the executor may still be running there '
                     '(attempt {})'.format(a.host, time.time() - unreachable_since, state['attempt']))
                return 255
            time.sleep(poll)
            continue
        if unreachable_since:
            note(a.log, '{} reachable again after {:.0f} s; the job kept running'.format(
                a.host, time.time() - unreachable_since))
            unreachable_since = None
        pull(host, state, a.log, a.state)
        if st.startswith('rc='):
            pull(host, state, a.log, a.state)
            Path(a.state).unlink()
            try:
                return int(st[3:])
            except ValueError:
                return 255
        if st in ('lost', 'none'):
            if not lost_once:          # the watcher writes rc a moment after the executor exits
                lost_once = True
                time.sleep(min(3.0, poll))
                continue
            pull(host, state, a.log, a.state)
            note(a.log, 'attempt {} is gone on {} with no exit code (host restarted, or the '
                 'watcher was killed)'.format(state['attempt'], a.host))
            Path(a.state).unlink()
            return 255
        lost_once = False
        time.sleep(poll)


if __name__ == '__main__':
    sys.exit(main())
