"""What the lanes' launcher did that tools/launch.sh now does (11-20: _codex/launch.sh became a thin exec into it).

Every CLI here is a stub (agy, claude, tmux, ssh): no model, no network, no spend.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / 'tools/launch.sh'
DONE = ('from pathlib import Path\n'
        'Path("STATUS.md").write_text("You asked: a file. I will: write it.\\n")\n'
        'Path("REPORT.md").write_text("Shipped: out.txt\\n")\nPath("out.txt").write_text("ok")\n')


def stub(path, body):
    path.write_text('#!' + sys.executable + '\n' + body)
    path.chmod(0o755)
    return path


def fake_tmux(tmp_path):
    """has-session / new-session -d -s NAME -c DIR CMD / display-message, with the session as a background sh."""
    state = tmp_path / 'tmux'
    state.mkdir()
    tm = tmp_path / 'fake-tmux'
    tm.write_text('#!/bin/sh\nS=' + str(state) + '\n'
                  'case "$1" in\n'
                  '  has-session) n=${3#=}; [ -f "$S/$n.pid" ] && kill -0 "$(cat "$S/$n.pid")" 2>/dev/null;;\n'
                  '  new-session) shift; while [ $# -gt 1 ]; do case "$1" in -d) shift;; -s) n=$2; shift 2;;\n'
                  '      -c) d=$2; shift 2;; *) break;; esac; done\n'
                  '    echo "$1" > "$S/$n.cmd"; (cd "$d" && env -u TMUX sh -c "$1" > "$S/$n.out" 2>&1) &\n'
                  '    echo $! > "$S/$n.pid";;\n'
                  '  display-message) echo "${FAKE_TMUX_SESSION:-other}";;\n'
                  'esac\n')
    tm.chmod(0o755)
    return tm, state


def lanes_env(tmp_path, roles, **extra):
    jobs = tmp_path / 'jobs'
    jobs.mkdir(exist_ok=True)
    root = tmp_path / 'runtime'
    (root / 'lanes/fixture').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'roles.json').write_text(json.dumps(roles))
    env = dict(os.environ, LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               RH_ROLES_FILE=str(tmp_path / 'roles.json'), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(root),
               RSTACK_STATE_DIR=str(tmp_path / 'state'), LAUNCH_YIELD_LEDGER=str(tmp_path / 'yield.jsonl'))
    for k in ('LAUNCH_RESUME', 'SPEC_OVER_CAP', 'LAUNCH_HOST', 'TMUX', 'LAUNCH_DETACHED', 'AGENT_BACKEND',
              'LAUNCH_BACKEND', 'RH_LAUNCHER_EXECUTORS', 'LAUNCH_ROLE', 'RH_DELEGATE_SHARE'):
        env.pop(k, None)
    env.update(extra)
    return jobs, env


AGY_ROLES = {'roles': {'batch': ['gemini-4-hydrogen-low']},
             'routes': {'gemini-4-hydrogen-low': {'cli': 'agy', 'canonical': 'google/gemini-4-hydrogen-low'}}}


def test_an_agy_route_runs_detached_through_the_launcher_and_comes_back_graded(tmp_path):
    """The whole lane path: detached into tmux, agy executor, receipt, exit line, auto-grade row, registry."""
    agy = stub(tmp_path / 'fake-agy', 'import json, sys\n' + DONE +
               'assert "--model" in sys.argv and "gemini-4-hydrogen-low" in sys.argv\n'
               'print(json.dumps({"response": "done", "status": "OK"}))\n')
    tm, state = fake_tmux(tmp_path)
    jobs, env = lanes_env(tmp_path, AGY_ROLES, AGENT_BACKEND='agy', LAUNCH_AGY=str(agy), LAUNCH_DETACH='tmux',
                          LAUNCH_TMUX=str(tm), LAUNCH_DETACH_POLL='0.2', LAUNCH_RESTARTS='2')
    (jobs / 'fixture-agy.md').write_text('Write out.txt.\nCheck: test -f out.txt\n')
    work = tmp_path / 'work'
    work.mkdir()
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-agy', str(work), '--role', 'batch'], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr + (state / 'job-fixture-agy.out').read_text()
    assert (state / 'job-fixture-agy.cmd').exists()   # it ran in its own session, not under the caller
    log = (jobs / 'fixture-agy.log').read_text()
    assert '=== attempt 1 model gemini-4-hydrogen-low' in log and '"response": "done"' in log
    assert any(line.startswith('exit 0 ') for line in log.splitlines())
    receipt = json.loads((jobs / 'fixture-agy.log.selection.json').read_text())
    assert (receipt['executor'], receipt['model'], receipt['role']) == ('agy', 'gemini-4-hydrogen-low', 'batch')
    assert 'GRADE ON RETURN' in log
    entry = dict(line.split('=', 1) for line in (tmp_path / 'registry/fixture-agy.finished').read_text().splitlines())
    assert entry['restarts'] == '2' and entry['path'] and entry['dir'] == str(work)


def test_a_delegated_agy_job_is_auto_graded_at_return(tmp_path):
    agy = stub(tmp_path / 'fake-agy', 'import json\n' + DONE + 'print(json.dumps({"response": "done"}))\n')
    roles = {'roles': {'batch': ['gpt-6.2-sol']}, 'routes': {
        'gpt-6.2-sol': {'cli': 'codex', 'canonical': 'openai/gpt-6.2-sol'},
        'gemini-4-hydrogen-low': {'cli': 'agy', 'canonical': 'google/gemini-4-hydrogen-low'}}}
    jobs, env = lanes_env(tmp_path, roles, LAUNCH_AGY=str(agy), RH_DELEGATE_SHARE='1',
                          RH_LAUNCHER_EXECUTORS='agy', RH_HEADROOM_ROUTING='0')
    (jobs / 'fixture-d.md').write_text('Write out.txt.\nCheck: test -f out.txt\n')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-d', str(tmp_path)], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((jobs / 'fixture-d.log.selection.json').read_text())
    assert (receipt['source'], receipt['executor']) == ('delegate', 'agy')
    row = json.loads((jobs / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['grader'], row['producer']) == ('pass', 'checks', 'gemini-4-hydrogen-low')


CLAUDE_ROLES = {'roles': {'batch': ['fixture-claude']},
                'routes': {'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}}}


def claude_stub(tmp_path, body=''):
    return stub(tmp_path / 'fake-claude', 'import sys\n' + body +
                'print(\'{"is_error":false,"subtype":"success","result":"fixture"}\')\n')


def test_a_detached_job_returns_its_code_and_a_second_copy_is_refused(tmp_path):
    fake = claude_stub(tmp_path, 'import time; time.sleep(3); sys.exit(3)\n')
    tm, state = fake_tmux(tmp_path)
    jobs, env = lanes_env(tmp_path, CLAUDE_ROLES, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
                          LAUNCH_DETACH='tmux', LAUNCH_TMUX=str(tm), LAUNCH_DETACH_POLL='0.2')
    (jobs / 'fixture-x.md').write_text('a job\n')
    first = subprocess.Popen(['zsh', str(LAUNCH), 'fixture-x', str(tmp_path)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if (state / 'job-fixture-x.pid').exists():
            break
        time.sleep(0.1)
    second = subprocess.run(['zsh', str(LAUNCH), 'fixture-x', str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=60)
    assert second.returncode == 75 and 'already running' in second.stderr
    first.wait(timeout=120)
    assert first.returncode == 3   # the job's own exit code, read from its exit line
    # Inside a tmux session that is not a Claude session, the job runs in place.
    jobs, env = lanes_env(tmp_path, CLAUDE_ROLES, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(claude_stub(tmp_path)),
                          LAUNCH_DETACH='tmux', LAUNCH_TMUX=str(tm), TMUX='/tmp/x,1,0', FAKE_TMUX_SESSION='job-other')
    (jobs / 'fixture-y.md').write_text('a job\n')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-y', str(tmp_path)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0 and not (state / 'job-fixture-y.cmd').exists()


def test_an_absolute_job_path_is_its_spec_and_does_not_register_for_the_watchdog(tmp_path):
    """The sweep hands the lanes' launcher a path relative to it; the wrapper makes it absolute."""
    jobs, env = lanes_env(tmp_path, CLAUDE_ROLES, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(claude_stub(tmp_path)))
    run = tmp_path / 'lane/runs/r1'
    run.mkdir(parents=True)
    (run / 'search.md').write_text('search\n')
    proc = subprocess.run(['zsh', str(LAUNCH), str(run / 'search'), str(tmp_path)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert (run / 'search.log').exists() and (run / 'search.last.md').exists()
    assert not list((tmp_path / 'registry').glob('*.job')) and not list((tmp_path / 'registry').glob('*.finished'))
    assert list((tmp_path / 'registry/paths').glob('*.finished'))


def test_the_preamble_follows_the_rules_and_old_specs_keep_their_exemption(tmp_path):
    front = tmp_path / 'FRONT.md'
    front.write_text('# Normal first.\n\nEverything below is the job\'s own spec.\n\n---\n')
    goal = tmp_path / 'GOAL.md'
    goal.write_text('friends goal\n')
    sent = tmp_path / 'notified.txt'
    note = stub(tmp_path / 'note', 'import sys\nopen(' + repr(str(sent)) + ', "a").write(" ".join(sys.argv[1:]) + "\\n")\n')
    jobs, env = lanes_env(tmp_path, CLAUDE_ROLES, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(claude_stub(tmp_path)),
                          LAUNCH_PREAMBLE='{}:{}:{}'.format(front, tmp_path / 'absent.md', goal),
                          LAUNCH_NOTIFY_COMMAND=str(note) + ' fyi')
    (jobs / 'fixture-p.md').write_text('the ask\n')
    assert subprocess.run(['zsh', str(LAUNCH), 'fixture-p', str(tmp_path)], env=env, capture_output=True).returncode == 0
    prompt = (jobs / 'fixture-p.log.prompt').read_text()
    assert prompt.index('Science job rules') < prompt.index('# Normal first.') < prompt.index('friends goal') \
        < prompt.index('the ask')
    long = jobs / 'fixture-long.md'
    long.write_text(' '.join(['ceremony'] * 1200))
    os.utime(long, (1_700_000_000, 1_700_000_000))
    env['LAUNCH_SPEC_CAP_SINCE'] = '1793842533'
    assert subprocess.run(['zsh', str(LAUNCH), 'fixture-long', str(tmp_path)], env=env, capture_output=True).returncode == 0
    long.write_text(' '.join(['ceremony'] * 1200))   # touched now: the cap applies, and says so
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-long', str(tmp_path)], env=env, capture_output=True, text=True)
    assert proc.returncode == 2 and 'over the 1000 cap' in proc.stderr
    assert 'fyi launch refused fixture-long: spec over 1000 words' in sent.read_text()


def test_a_host_job_honours_the_remote_path_and_brings_back_its_last_message(tmp_path):
    from test_launch_host import harness
    jobs, env = harness(tmp_path)
    env['LAUNCH_REMOTE_PATH'] = '/lane/tools:/usr/bin:/bin'
    work = tmp_path / 'work'
    work.mkdir()
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(work), '--host', 'm5'], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert 'export PATH=/lane/tools:/usr/bin:/bin\n' in (jobs / 'fixture-job.log.rcmd').read_text()
    out = str(jobs / 'fixture-job.last.md')
    # The last message sits beside the spec, outside the work dir, so it is pulled by name.
    assert any(out in line for line in Path(env['SSH_LOG']).read_text().splitlines() if 'rsync' in line)
    assert 'fixture' in (jobs / 'fixture-job.log').read_text()   # the host's output is in the job log
