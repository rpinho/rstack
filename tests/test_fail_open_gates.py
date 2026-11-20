"""RULE #1 (Ricardo, 11-20): the harness never gets in the way of the work.

Every gate has a class in rstack/gates.json. This file is the enforcement:
  * the lint passes, and it fails a gate that has no class (it can fail);
  * every fail-open hook with a probe is fed realistic work input AND its own crash path, and must exit 0
    without a deny, ask or block, leaving a warning in harness-blocks.jsonl;
  * the launcher's, the round gate's, the selector's, the Codex wrapper's and the grader's fail-open checks
    are driven with the input that used to stop a job, and the job runs.
Every CLI here is a stub: no model, no network, no spend.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'harness'))
sys.path.insert(0, str(REPO / 'rstack/tools'))
sys.path.insert(0, str(REPO / 'tests'))
import harness_blocks  # noqa: E402
import gates_lint  # noqa: E402
from test_launch_lanes import CLAUDE_ROLES, LAUNCH, claude_stub, fake_tmux, lanes_env, stub  # noqa: E402

REGISTRY = json.loads((REPO / 'rstack/gates.json').read_text())
GATES = {row['gate']: row for row in REGISTRY['gates']}
DENIED = ('"permissionDecision": "deny"', '"permissionDecision": "ask"', '"decision": "block"')


def ledger(state):
    path = Path(state) / harness_blocks.LEDGER
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_the_gates_lint_passes_on_this_repo():
    assert gates_lint.lint(REPO) == []


def test_the_lint_fails_a_gate_with_no_class(tmp_path):
    (tmp_path / 'rstack').mkdir()
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'rstack/gates.json').write_text(json.dumps({'gates': [
        {'gate': 'a', 'files': ['tools/a.py'], 'class': 'hard-line', 'hard_line': 'vibes'}], 'exempt': {}}))
    (tmp_path / 'tools/a.py').write_text('print("ok")\n')
    (tmp_path / 'tools/b.py').write_text('import sys\nprint("REFUSED: no")\nsys.exit(2)\n')
    problems = '\n'.join(gates_lint.lint(tmp_path))
    assert 'tools/b.py: refuses something but has no class' in problems
    assert "a: a hard line must be one of" in problems and 'a: a refusing gate must name its fix' in problems


def test_the_fallback_refusing_set_is_the_registrys():
    assert harness_blocks.FALLBACK_REFUSING == {n for n, r in GATES.items() if r['class'] == 'hard-line'}


def test_only_the_six_hard_lines_or_a_pending_call_may_refuse():
    for name, row in GATES.items():
        if row['class'] == 'hard-line':
            assert row['hard_line'] in harness_blocks.HARD_LINES + ('pending',), name
            assert row.get('fix'), name


def test_the_helper_refuses_only_a_hard_line_and_logs_both(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    assert harness_blocks.gate('trash-guard.py', 'rm -rf /x', job='j1') is True
    assert harness_blocks.gate('launch.spec-word-cap', 'spec is 1200 words', job='j1') is False
    err = capsys.readouterr().err
    assert 'REFUSED (hard line: permanent-delete)' in err and 'Fix: /usr/bin/trash' in err
    assert 'WARNING (fail-open, the work continues)' in err
    rows = ledger(tmp_path)
    assert [(r['gate'], r['class'], r['outcome']) for r in rows] == [
        ('trash-guard.py', 'hard-line', 'block'), ('launch.spec-word-cap', 'fail-open', 'warn')]
    assert set(rows[0]) >= {'utc', 'gate', 'class', 'job', 'lane', 'reason', 'outcome'}


def test_an_unknown_gate_keeps_refusing_and_is_named_in_the_report(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    assert harness_blocks.gate('someone-elses-gate', 'no', job='j') is True
    assert 'someone-elses-gate' in harness_blocks.line(harness_blocks.summarize(harness_blocks.read()))


def test_a_block_later_rerun_overridden_or_retracted_is_a_harness_bug(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    harness_blocks.record('launch.host-peak-cap', 'hard-line', 'peak', job='math_a')   # pending: counts
    harness_blocks.record('trash-guard.py', 'hard-line', 'rm -rf', job='math_b')       # a hard line held: does not
    harness_blocks.record('launch.load', 'fail-open', 'load', job='math_c')
    assert harness_blocks.admitted('math_a') == 1 and harness_blocks.admitted('math_a') == 0
    harness_blocks.admitted('math_b')
    harness_blocks.mark('math_c', 'retract', reason='worker_models --retract')
    s = harness_blocks.summarize(harness_blocks.read())
    assert [b['gate'] for b in s['harness_bugs']] == ['launch.host-peak-cap']
    assert s['blocks'] == 2 and s['warns'] == 1
    text = harness_blocks.line(s)
    assert 'top blockers: launch.host-peak-cap (1), launch.load (1), trash-guard.py (1)' in text


def test_the_daily_report_tells_general(tmp_path):
    told = tmp_path / 'told'
    tg = stub(tmp_path / 'tell-general', 'import sys\nopen({!r}, "a").write(" ".join(sys.argv[1:]))\n'.format(str(told)))
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path), RH_TELL_GENERAL=str(tg), RH_BLOCKS_PEERS='')
    subprocess.run([sys.executable, str(REPO / 'harness/harness_blocks.py'), 'gate', '--gate', 'launch.load',
                    '--reason', 'load 40', '--job', 'x'], env=env, check=True, capture_output=True)
    out = subprocess.run([sys.executable, str(REPO / 'harness/harness_blocks.py'), 'report', '--tell'], env=env,
                         capture_output=True, text=True, check=True)
    assert 'top blockers: launch.load (1)' in out.stdout
    assert told.read_text().startswith('--from harness-blocks fyi harness-blocks 24h:')


def test_the_daily_tick_runs_the_report():
    daily = (REPO / 'leaderboard/daily.sh').read_text()
    assert 'harness_blocks.py" report --tell' in daily


# --- every fail-open hook: realistic input, then its own crash path ---------------------------------------
HOOK_PROBES = sorted((n, r) for n, r in GATES.items() if r['class'] == 'fail-open' and 'hook' in r.get('probe', {}))


def run_hook(path, stdin, env):
    return subprocess.run([sys.executable, str(REPO / path)], input=stdin, env=env, capture_output=True,
                          text=True, timeout=60)


@pytest.mark.parametrize('name,row', HOOK_PROBES, ids=[n for n, _ in HOOK_PROBES])
def test_a_fail_open_hook_lets_real_work_through_and_survives_its_own_crash(name, row, tmp_path):
    probe = row['probe']
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path / 'state'), HOME=str(tmp_path),
               RSTACK_MAIN_TREES=str(tmp_path / 'probe-lane'), RSTACK_UNATTENDED='1')
    env.pop('RH_GATES_REGISTRY', None)
    (tmp_path / 'probe-lane').mkdir()
    event = dict(probe['event'], cwd=str(tmp_path / 'probe-lane'))
    if name == 'results-report-guard.py':
        event.pop('cwd')
    for _ in range(3):   # poll-guard refuses the third identical check; every hook gets the same three
        done = run_hook(probe['hook'], json.dumps(event), env)
        assert done.returncode == 0, done.stderr
        assert not any(d in done.stdout for d in DENIED), done.stdout
    crash = run_hook(probe['hook'], '{"tool_name": "Bash", "tool_input": ', env)
    assert crash.returncode == 0, crash.stderr
    assert not any(d in crash.stdout for d in DENIED), crash.stdout
    rows = ledger(tmp_path / 'state')
    assert all(r['class'] == 'fail-open' and r['outcome'] in ('warn', 'allowed-override') for r in rows)
    if name != 'general-inbox-relay.py':   # the one probe whose input never trips anything
        assert rows, 'the probe did not reach the check it is meant to exercise'
        assert rows[0]['gate'] == name


def test_the_hooks_that_used_to_refuse_now_warn_in_the_ledger(tmp_path):
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path), HOME=str(tmp_path), RSTACK_UNATTENDED='1')
    for name in ('gate-pipe-guard.py', 'agent-stdin-guard.py', 'results-brief-guard.py'):
        probe = GATES[name]['probe']
        done = run_hook(probe['hook'], json.dumps(probe['event']), env)
        assert done.returncode == 0 and 'fail-open' in done.stdout, (name, done.stdout, done.stderr)
    warned = {r['gate'] for r in ledger(tmp_path) if r['outcome'] == 'warn'}
    assert {'gate-pipe-guard.py', 'agent-stdin-guard.py', 'results-brief-guard.py'} <= warned


def test_a_hard_line_hook_still_refuses_with_its_fix(tmp_path):
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path), HOME=str(tmp_path), RSTACK_UNATTENDED='1')
    event = {'tool_name': 'Bash', 'tool_input': {'command': 'rm -rf /tmp/some-dir'}, 'session_id': 's', 'cwd': '/tmp'}
    done = run_hook('rstack/hooks/trash-guard.py', json.dumps(event), env)
    assert '"permissionDecision": "deny"' in done.stdout and '/usr/bin/trash' in done.stdout
    assert [r['outcome'] for r in ledger(tmp_path)] == ['block']


def test_a_sanctioned_model_override_is_allowed_and_logged(tmp_path):
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path), HOME=str(tmp_path), RSTACK_UNATTENDED='1')
    probe = GATES['model-instruction-gate']['probe']
    done = run_hook(probe['hook'], json.dumps(probe['event']), env)
    assert done.returncode == 0 and not any(d in done.stdout for d in DENIED)
    assert [r['outcome'] for r in ledger(tmp_path)] == ['allowed-override']
    bare = dict(probe['event'], tool_input={'command': 'tools/launch.sh referee-c5 lanes/c5 --role review '
                                                       '--made-by gpt-6.2-sol --model claude-sonnet-5-5'})
    done = run_hook(probe['hook'], json.dumps(bare), env)
    assert done.returncode == 0 and 'fail-open' in done.stdout
    assert ledger(tmp_path)[-1]['outcome'] == 'warn'


# --- the launcher --------------------------------------------------------------------------------------------
def launch(tmp_path, job, spec, *args, **extra):
    fake = claude_stub(tmp_path)
    jobs, env = lanes_env(tmp_path, CLAUDE_ROLES, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake), **extra)
    (jobs / (job + '.md')).write_text(spec)
    proc = subprocess.run(['zsh', str(LAUNCH), job, str(tmp_path), *args], env=env, capture_output=True, text=True,
                          timeout=120)
    return proc, jobs, env


def test_launch_gates_warn_and_run(tmp_path):
    """The spec word cap, the load ceiling and an unpromoted idea used to stop the job; now it runs, warned."""
    long_spec = ' '.join(['word'] * 1300) + '\n'
    proc, jobs, env = launch(tmp_path, 'fixture-long', long_spec, LAUNCH_MAX_LOAD='-1', FORCE_LAUNCH='',
                             LAUNCH_IDEA='nope-1', RH_ROOT=str(tmp_path / 'runtime'))
    assert proc.returncode == 0, proc.stderr
    log = (jobs / 'fixture-long.log').read_text()
    assert '=== attempt 1 model fixture-claude' in log
    warned = {r['gate'] for r in ledger(tmp_path / 'state') if r['outcome'] == 'warn'}
    assert {'launch.spec-word-cap', 'launch.load', 'launch.idea-promoted'} <= warned
    # The crash path: the helper itself missing is a warning, never a refusal.
    proc, jobs, env = launch(tmp_path, 'fixture-long2', long_spec, LAUNCH_HARNESS_BLOCKS=str(tmp_path / 'nope.py'))
    assert proc.returncode == 0 and 'harness_blocks unavailable' in proc.stderr


def test_a_lane_on_hold_still_refuses_and_names_its_fix(tmp_path):
    (tmp_path / 'runtime/lanes/fixture').mkdir(parents=True)
    (tmp_path / 'runtime/lanes/fixture/HOLD').write_text('PAUSED 11-16 by general: not doing this lane\n')
    proc, jobs, env = launch(tmp_path, 'fixture-held', 'a job\n')
    assert proc.returncode == 78 and 'pending general' in proc.stderr and 'Fix: general removes' in proc.stderr
    assert ledger(tmp_path / 'state')[-1]['pending'] is True


def test_an_unreadable_lane_registry_is_a_warning(tmp_path):
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path), RH_LANE_REGISTRY=str(tmp_path / 'missing.json'))
    done = subprocess.run([sys.executable, str(REPO / 'harness/lane_registry.py'), '--job', 'math-round-3'],
                          env=env, capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.strip() == 'math'
    assert ledger(tmp_path)[-1]['gate'] == 'launch.lane-registry'


def test_a_second_launch_waits_for_the_running_copy(tmp_path):
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
    first.wait(timeout=120)
    assert first.returncode == 3 and second.returncode == 3   # it waited and returned the job's own code
    assert 'already running' in second.stderr
    assert (state / 'job-fixture-x.cmd').read_text().count('fixture-x') >= 1


def test_a_round_gate_crash_does_not_stop_the_job(tmp_path):
    lane = tmp_path / 'runtime/lanes/fixture'
    (lane / 'ROUNDS.jsonl').mkdir(parents=True)   # a directory where the ledger should be: rounds.py crashes
    proc, jobs, env = launch(tmp_path, 'fixture-r', 'a job\n', LAUNCH_ROUND='r1', LAUNCH_GENERATOR='g',
                             RH_ROOT=str(tmp_path / 'runtime'))
    assert proc.returncode == 0, proc.stderr
    assert any(r['gate'] == 'launch.round-gate-error' for r in ledger(tmp_path / 'state'))


def test_round_gate_process_checks_warn(tmp_path):
    lane = tmp_path / 'lanes/fixture'
    lane.mkdir(parents=True)
    env = dict(os.environ, RSTACK_STATE_DIR=str(tmp_path / 'state'), RH_ROOT=str(tmp_path))
    rounds = [sys.executable, str(REPO / 'harness/tools/rounds.py'), '--lane', str(lane)]
    first = subprocess.run(rounds + ['start', '--round', 'r1', '--family', 'f', '--generator', 'g'],
                           env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr        # no KB consult, no SPEC.json: warnings
    second = subprocess.run(rounds + ['start', '--round', 'r2', '--family', 'f', '--generator', 'h'],
                            env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr      # r1 never logged: a warning
    gates = {r['gate'] for r in ledger(tmp_path / 'state')}
    assert {'rounds.kb-unread', 'rounds.spec', 'rounds.unclosed'} <= gates
    bad = subprocess.run([sys.executable, str(REPO / 'harness/tools/rounds.py'), '--lane', str(tmp_path / 'nope'),
                          'start', '--round', 'r', '--family', 'f'], env=env, capture_output=True, text=True)
    assert bad.returncode == 0
    # general, 11-20: a repeat warns too, and the round opens.
    subprocess.run(rounds + ['log', '--round', 'r2', '--family', 'f', '--outcome', 'dry', '--generator', 'h'],
                   env=env, check=True, capture_output=True)
    rep = subprocess.run(rounds + ['start', '--round', 'r3', '--family', 'f', '--generator', 'h'],
                         env=env, capture_output=True, text=True)
    assert rep.returncode == 0 and '[rounds.repeat] WARNING (fail-open' in rep.stderr


def test_a_refused_pin_reroutes_to_the_leaderboard_pick(tmp_path):
    proc, jobs, env = launch(tmp_path, 'fixture-pin', 'a job\n', '--model', 'fixture-claude')
    assert proc.returncode == 0, proc.stderr          # --model without --model-override used to be exit 2
    assert 'rerouted to the leaderboard pick' in (jobs / 'fixture-pin.log').read_text()
    assert any(r['gate'] == 'launch.model-selection' for r in ledger(tmp_path / 'state'))


def test_the_concurrency_cap_queues_then_runs(tmp_path):
    count = tmp_path / 'guard-calls'
    guard = stub(tmp_path / 'fake-guard', 'from pathlib import Path\nimport sys\np = Path({!r})\n'
                 'n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n'
                 'sys.exit(75 if n < 2 else 0)\n'.format(str(count)))
    proc, jobs, env = launch(tmp_path, 'fixture-q', 'a job\n', LAUNCH_GUARD=str(guard), LAUNCH_QUEUE_POLL='0')
    assert proc.returncode == 0, proc.stderr and count.read_text() == '3'
    assert 'queued: concurrency cap' in (jobs / 'fixture-q.log').read_text()
    always = stub(tmp_path / 'full-guard', 'import sys\nsys.exit(75)\n')
    proc, jobs, env = launch(tmp_path, 'fixture-q2', 'a job\n', LAUNCH_GUARD=str(always), LAUNCH_QUEUE_SECONDS='0')
    assert proc.returncode == 0, proc.stderr
    assert any(r['gate'] == 'launch.concurrency' for r in ledger(tmp_path / 'state'))


def test_a_wrapper_refusal_is_ungraded_not_failed(tmp_path):
    """math_huntfree_1120 (11-20): the Codex per-lane cap refused the run (exit 75) and it was graded fail."""
    import auto_grade
    work = tmp_path / 'work'
    work.mkdir()
    receipt = tmp_path / 'job.log.selection.json'
    receipt.write_text(json.dumps(dict(selection_id='sid1', job='math_huntfree_1120', lane='math', role='batch',
                                       model='gpt-6.2-sol', source='delegate')))
    log = tmp_path / 'job.log'
    log.write_text('MODEL_SELECTION ' + json.dumps(dict(selection_id='sid1')) + '\n'
                   'codex: REFUSED 3% weekly allowance/day limit for math\n'
                   'MODEL_OUTCOME ' + json.dumps(dict(selection_id='sid1', exit_code=75)) + '\n')
    (tmp_path / 'job.md').write_text('Find it.\nCheck: test -f out.txt\n')
    assert auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work),
                            '--spec', str(tmp_path / 'job.md')]) == 0
    row = json.loads((tmp_path / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['grader']) == ('ungraded', 'harness')
    assert row['note'] == 'harness: codex: REFUSED 3% weekly allowance/day limit for math'
    # Exit 75 with no refusal line in the log is still the harness's.
    log.write_text('MODEL_SELECTION ' + json.dumps(dict(selection_id='sid1')) + '\n'
                   'MODEL_OUTCOME ' + json.dumps(dict(selection_id='sid1', exit_code=75)) + '\n')
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(tmp_path / 'job.md')])
    row = json.loads((tmp_path / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert row['grade'] == 'ungraded' and row['note'].startswith('harness: exit 75')


def test_the_claude_ceiling_without_a_fallback_stays_on_claude(monkeypatch, tmp_path):
    import worker_models as wm
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    calls = []
    monkeypatch.setattr(wm.claude_cap, 'enabled', lambda: True)
    monkeypatch.setattr(wm.claude_cap, 'decide', lambda chosen, *a, **k: dict(
        model=chosen, leave='weekly 82% >= 80% ceiling', notes=[], warning='', opus_reason=''))
    monkeypatch.setattr(wm, 'claude_fallback', lambda *a, **k: calls.append(1) or None)
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(CLAUDE_ROLES))
    receipt = wm.select('batch', 'claude', '', '', roles, job='fixture', lane='lane-a')
    assert calls and receipt['model'] == 'fixture-claude' and 'no fallback route' in receipt['claude_cap']
    assert ledger(tmp_path)[-1]['gate'] == 'selector.claude-ceiling'


def test_codex_wrapper_errors_fail_open():
    src = (REPO / 'rstack/tools/_codex_budget.py').read_text()
    # After the run: an accounting error no longer replaces the run's own exit code with 75.
    assert "completion accounting failed ({}); the run\\'s own exit code stands" in src
    assert "_gate('codex-budget.unavailable'" in src and "_warn('codex-budget.limit'" in src
    assert GATES['codex-budget.unavailable']['class'] == 'fail-open'
    assert GATES['codex-budget.accounting']['class'] == 'fail-open'


# --- general's decisions on the ambiguous gates (11-20): the input that used to refuse now runs, warned ----------
CODEX_CLAUDE_ROLES = {'roles': {'batch': ['fixture-codex', 'fixture-claude']},
                      'routes': {'fixture-codex': {'canonical': 'fixture-codex', 'cli': 'codex'},
                                 'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}}}


def capped_codex(tmp_path, refusals=99):
    """A codex CLI that the spend wrapper refuses `refusals` times (its REFUSED line, exit 75), then runs."""
    count = tmp_path / 'codex-calls'
    return stub(tmp_path / 'fake-codex', 'from pathlib import Path\nimport sys\np = Path({!r})\n'
                'n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n'
                'if n < {}:\n    print("codex: REFUSED 3% weekly allowance/day limit for fixture", file=sys.stderr)\n'
                '    sys.exit(75)\nprint("codex ran")\n'.format(str(count), refusals)), count


def test_a_codex_budget_refusal_reruns_the_job_on_claude(tmp_path):
    """codex-budget.limit used to fail the job (exit 75); the cap holds on Codex and the job runs on Claude."""
    codex, count = capped_codex(tmp_path)
    fake = claude_stub(tmp_path)
    jobs, env = lanes_env(tmp_path, CODEX_CLAUDE_ROLES, AGENT_BACKEND='codex', LAUNCH_CODEX=str(codex),
                          LAUNCH_CLAUDE=str(fake), RH_CLAUDE_CAP='0', RH_HEADROOM_ROUTING='0')
    (jobs / 'fixture-cap.md').write_text('a job\n')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-cap', str(tmp_path)], env=env, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    log = (jobs / 'fixture-cap.log').read_text()
    assert '=== attempt 1 model fixture-codex' in log and 'codex budget refused fixture-cap' in log
    assert '=== attempt 1 model fixture-claude' in log and count.read_text() == '1'
    receipt = json.loads((jobs / 'fixture-cap.log.selection.json').read_text())
    assert (receipt['executor'], receipt['model']) == ('claude', 'fixture-claude')
    assert receipt['codex_refused'] == '3% weekly allowance/day limit for fixture'


def test_both_capped_queues_the_job_then_runs_it(tmp_path):
    """Codex and Claude both capped: the job queues, warned, and runs when Codex has room again; never failed."""
    codex, count = capped_codex(tmp_path, refusals=2)
    real = REPO / 'harness/worker_models.py'
    # The selector, except that Claude and agy have no room while Codex is closed (exit 5, as the 80% ceiling does).
    selector = stub(tmp_path / 'fake-selector', 'import os, sys\n'
                    'if os.environ.get("RH_CODEX_CLOSED") and any(a.endswith(".reroute.json") for a in sys.argv):\n'
                    '    sys.exit(5)\n'
                    'os.execv(sys.executable, [sys.executable, {!r}] + sys.argv[1:])\n'.format(str(real)))
    jobs, env = lanes_env(tmp_path, CODEX_CLAUDE_ROLES, AGENT_BACKEND='codex', LAUNCH_CODEX=str(codex),
                          LAUNCH_SELECTOR=str(selector), LAUNCH_BUDGET_QUEUE_POLL='0', RH_HEADROOM_ROUTING='0')
    (jobs / 'fixture-cq.md').write_text('a job\n')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-cq', str(tmp_path)], env=env, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    log = (jobs / 'fixture-cq.log').read_text()
    assert log.count('queued: codex budget') == 1 and 'codex ran' in log and count.read_text() == '3'
    rows = [r for r in ledger(tmp_path / 'state') if r['gate'] == 'codex-budget.limit']
    assert [r['outcome'] for r in rows] == ['warn']


def test_a_selector_with_codex_closed_and_claude_capped_has_no_room(monkeypatch, tmp_path):
    """The exit 5 that queues: Codex refused the job and Claude is past its ceiling with nowhere else to go."""
    import worker_models as wm
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('RH_CODEX_CLOSED', 'weekly cap')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    monkeypatch.setattr(wm.claude_cap, 'enabled', lambda: True)
    monkeypatch.setattr(wm.claude_cap, 'decide', lambda chosen, *a, **k: dict(
        model=chosen, leave='weekly 82% >= 80% ceiling', notes=[], warning='', opus_reason=''))
    monkeypatch.setattr(wm, 'claude_fallback', lambda *a, **k: None)
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(CODEX_CLAUDE_ROLES))
    with pytest.raises(wm.NoRoom):
        wm.select('batch', 'codex', '', '', roles, job='fixture', lane='lane-a')
    assert wm.main(['--role', 'batch', '--roles-file', str(roles), '--log', str(tmp_path / 'l'),
                    '--receipt', str(tmp_path / 'r.json'), '--print-route']) == 5


def rounds_cli(lane_dir, *args):
    return subprocess.run([sys.executable, str(REPO / 'harness/tools/rounds.py'), '--lane', str(lane_dir), *args],
                          capture_output=True, text=True,
                          env=dict(os.environ, RSTACK_STATE_DIR=str(lane_dir.parent / 'rounds-state')))


def test_round_process_gates_warn_into_the_prompt(tmp_path):
    """A repeat in a dry family that was closed used to refuse the round (exit 78); it runs, and the job reads why."""
    lane = tmp_path / 'runtime/lanes/fixture'
    lane.mkdir(parents=True)
    for n in (1, 2, 3):
        assert rounds_cli(lane, 'log', '--round', 'r%d' % n, '--family', 'f', '--outcome', 'dry',
                          '--generator', 'g').returncode == 0
    rounds_cli(lane, 'close-family', '--family', 'f', '--reason', 'three dry rounds')
    rounds_cli(lane, 'consult', '--source', 'index.md', '--took', 'still nothing')
    proc, jobs, env = launch(tmp_path, 'fixture-r4', 'a job\n', LAUNCH_ROUND='r4', LAUNCH_FAMILY='f',
                             LAUNCH_GENERATOR='g', RH_ROOT=str(tmp_path / 'runtime'))
    assert proc.returncode == 0, proc.stderr
    prompt = (jobs / 'fixture-r4.log.prompt').read_text()
    assert 'HARNESS WARNINGS FOR THIS JOB' in prompt
    for gate in ('rounds.repeat', 'rounds.dry-family', 'rounds.dead-end'):
        assert '[{}] WARNING'.format(gate) in prompt, gate
    assert 'round gate warnings, round r4 runs' in (jobs / 'fixture-r4.log').read_text()
    receipt = json.loads((jobs / 'fixture-r4.log.selection.json').read_text())
    assert {w.split(']')[0] for w in receipt['round_warnings']} >= {
        '[rounds.repeat', '[rounds.dry-family', '[rounds.dead-end'}
    row = json.loads((lane / 'ROUNDS.jsonl').read_text().splitlines()[-1])
    assert row['round'] == 'r4' and row['outcome'] == 'started' and len(row['warnings']) >= 3


def test_a_drifted_baseline_runs_the_round_flagged(tmp_path):
    """rounds.baseline-drift used to refuse; the round runs and the comparison is flagged in prompt and receipt."""
    lane = tmp_path / 'runtime/lanes/fixture'
    lane.mkdir(parents=True)
    rounds_cli(lane, 'consult', '--source', 'index.md', '--took', 'the family')
    (lane / 'value.txt').write_text('1.5\n')
    (lane / 'BASELINES.jsonl').write_text(json.dumps(dict(name='toy-2020', source='fixture', published=1.0,
                                                          cmd='cat value.txt', tolerance=1e-9, timeout=60)) + '\n')
    proc, jobs, env = launch(tmp_path, 'fixture-bd', 'a job\n', LAUNCH_ROUND='r1', LAUNCH_FAMILY='f',
                             LAUNCH_GENERATOR='g', RH_ROOT=str(tmp_path / 'runtime'))
    assert proc.returncode == 0, proc.stderr
    prompt = (jobs / 'fixture-bd.log.prompt').read_text()
    assert 'BASELINE DRIFT' in prompt and 'toy-2020' in prompt
    receipt = json.loads((jobs / 'fixture-bd.log.selection.json').read_text())
    assert 'toy-2020' in receipt['baseline_drift']
    assert 'toy-2020' in json.loads((lane / 'ROUNDS.jsonl').read_text().splitlines()[-1])['baseline_drift']


def test_a_coverage_repeat_is_recorded_with_a_warning(tmp_path, monkeypatch):
    """bughunt.coverage used to refuse recording the round; it is recorded and the lane's next job reads it."""
    import bug_coverage
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    lane = tmp_path / 'runtime/lanes/fixture'
    lane.mkdir(parents=True)
    r1 = dict(target='org/tool', commit='a' * 40, round='r1',
              units=[dict(unit='src/fit.py', bug_class='off-by-one', status='covered')])
    assert bug_coverage.record(lane, r1)[0]
    ok, msgs = bug_coverage.record(lane, dict(r1, round='r2'))
    assert ok and 'COVERAGE_REPEAT' in msgs[0]
    assert ledger(tmp_path / 'state')[-1]['gate'] == 'bughunt.coverage'
    proc, jobs, env = launch(tmp_path, 'fixture-bh', 'a job\n')
    assert proc.returncode == 0, proc.stderr
    assert 'Bug-hunt coverage: COVERAGE_REPEAT: round r2' in (jobs / 'fixture-bh.log.prompt').read_text()


def test_a_lane_yield_hold_warns_and_files_a_decision_card(tmp_path, monkeypatch):
    """lane-yield's hold used to stop the lane (a HOLD file, exit 78). It is YIELD_HOLD now: a decision card to
    general, and a warning the job runs past. general's own HOLD still refuses (the test above)."""
    sys.path.insert(0, str(REPO / 'harness/tools/lane-yield'))
    import lane_yield
    home = tmp_path / 'home'
    told = tmp_path / 'told'
    (home / '.claude/skills/orchestrator/scripts').mkdir(parents=True)
    stub(home / '.claude/skills/orchestrator/scripts/tell-general',
         'import sys\nopen({!r}, "a").write(" ".join(sys.argv[1:]))\n'.format(str(told)))
    monkeypatch.setattr(lane_yield.Path, 'home', lambda: home)
    lane = tmp_path / 'runtime/lanes/fixture'
    lane_yield.act({'lane': 'fixture', 'as_of': '2026-11-20', 'fails': ['BURNING: 25 job-h, 0 new']},
                   {'hold': str(lane / 'HOLD')})
    assert (lane / 'YIELD_HOLD').exists() and not (lane / 'HOLD').exists()
    card = told.read_text()
    assert card.startswith('--from lane-yield decision lane-yield FAIL fixture: BURNING') and 'mv ' in card
    proc, jobs, env = launch(tmp_path, 'fixture-yh', 'a job\n')
    assert proc.returncode == 0, proc.stderr
    assert 'Lane yield: YIELD_HOLD by lane-yield' in (jobs / 'fixture-yh.log.prompt').read_text()
    assert [r['outcome'] for r in ledger(tmp_path / 'state') if r['gate'] == 'lane-yield.hold'] == ['warn']


def test_a_dead_host_memory_guard_is_kickstarted_then_the_job_runs(tmp_path):
    """launch.host-memguard used to refuse (exit 75). The guard is kickstarted over ssh; if it still is not
    beating, the job runs with a warning."""
    from test_launch_host import harness as host_harness
    jobs, env = host_harness(tmp_path)
    Path(env['LAUNCH_MEMGUARD_HEARTBEAT']).unlink()
    env.update(LAUNCH_MEMGUARD_KICK='true', RSTACK_STATE_DIR=str(tmp_path / 'state'))   # the kickstart does not help
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path), '--host', 'm5'], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert '[launch.host-memguard] WARNING (fail-open' in proc.stderr and 'after a kickstart' in proc.stderr
    assert 'cmd=true' in Path(env['SSH_LOG']).read_text()
    assert [r['outcome'] for r in ledger(tmp_path / 'state') if r['gate'] == 'launch.host-memguard'] == ['warn']


def test_sweep_headroom_runs_after_the_wait(tmp_path, monkeypatch):
    """sweep.host-headroom used to refuse at the end of its wait; the sweep runs, warned."""
    import sweep
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(sweep, 'disk_guard', lambda cfg: None)
    monkeypatch.setattr(sweep, 'execution_host', lambda cfg: '')
    monkeypatch.setattr(sweep, 'free_memory_gib', lambda: 0.5)
    monkeypatch.setattr(sweep, 'cpu_busy', lambda: 0.1)
    sweep.guard({'load_wait_minutes': 0, 'min_free_memory_gib': 6, 'cores': 1, 'max_load': 8})
    rows = ledger(tmp_path)
    assert [(r['gate'], r['outcome']) for r in rows] == [('sweep.host-headroom', 'warn')]
    assert 'insufficient free memory' in rows[0]['reason'] and 'nice 10' in rows[0]['reason']

    def full(cfg):   # the disk floor beside it is kept: still a refusal
        raise ValueError('sweep refused: disk below the floor')
    monkeypatch.setattr(sweep, 'disk_guard', full)
    with pytest.raises(ValueError, match='disk'):
        sweep.guard({'load_wait_minutes': 0})


def test_an_explore_outside_the_pool_runs_the_explored_model(tmp_path):
    """math 11-20: `--explore claude-sonnet-5-5` outside the builder pool was rerouted to the leaderboard pick."""
    roles = {'roles': {'batch': ['fixture-claude']},
             'routes': {'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'},
                        'fixture-other': {'canonical': 'fixture-other', 'cli': 'claude'}}}
    fake = claude_stub(tmp_path)
    jobs, env = lanes_env(tmp_path, roles, AGENT_BACKEND='codex', LAUNCH_CLAUDE=str(fake), RH_CLAUDE_CAP='0',
                          RH_HEADROOM_ROUTING='0')
    (jobs / 'fixture-ex.md').write_text('a job\n')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-ex', str(tmp_path), '--explore', 'fixture-other'], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    log = (jobs / 'fixture-ex.log').read_text()
    assert '=== attempt 1 model fixture-other' in log and 'rerouted to the leaderboard pick' not in log
    receipt = json.loads((jobs / 'fixture-ex.log.selection.json').read_text())
    assert (receipt['source'], receipt['executor']) == ('explore', 'claude') and receipt['explore_outside_pool']
    assert [r['outcome'] for r in ledger(tmp_path / 'state') if r['gate'] == 'selector.explore-pool'] == ['warn']
