"""The normal launcher path with the stub executor and a single shared wall budget."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import pytest

from test_launch_prompt import ASK, LAUNCH, harness


def run_floor(tmp_path, *, floor='50%', report='Shipped: nothing', sleep=0, timeout=14400,
              ledger=None, existing=False, on_resume=None, fails=False, watchdog=False):
    spec = ASK + '\nCheck: test -f REPORT.md\n'
    if floor is not None:
        spec += f'Effort floor: {floor}\n'
    jobs, env = harness(tmp_path, spec)
    env.update(LAUNCH_TIMEOUT_SECONDS=str(timeout), RSTACK_STATE_DIR=str(tmp_path / 'state'),
               RH_HEADROOM_ROUTING='0', RH_AGY_CLOSED='test', LAUNCH_DETACH='', RSTACK_ABLATE='0')
    if watchdog:
        env['LAUNCH_RESUME'] = '1'
    lane_ledger = Path(env['LAUNCH_LANE_ROOT']) / 'lanes/fixture/RESULTS.jsonl'
    if existing:
        lane_ledger.write_text('{"new":true,"job":"fixture-job"}\n')
    cli = Path(env['LAUNCH_CLAUDE'])
    cli.write_text(f'#!{sys.executable}\n' + f'''
import json
from pathlib import Path
import subprocess
import sys
import time

prompt = sys.stdin.read()
argv = sys.argv
with Path('calls.jsonl').open('a') as stream:
    print(json.dumps(dict(prompt=prompt, model=argv[argv.index('--model') + 1],
                          budget=argv[argv.index('--max-budget-usd') + 1])), file=stream)
resumed = 'continue: you stopped' in prompt
report = {report!r} if not resumed or {on_resume is None!r} else {on_resume!r}
if report is not None:
    Path('REPORT.md').write_text(report + '\\n')
Path('STATUS.md').write_text('You asked: find a bound. I will: try.\\n')
if not resumed and {ledger == 'own'!r}:
    subprocess.run([sys.executable, {str(LAUNCH.parents[1] / 'harness/tools/lane-yield/log_result.py')!r},
                    '--ledger', {str(lane_ledger)!r}, '--new', 'yes', '--kind', 'value',
                    '--what', 'fixture', '--link', 'https://example.test/result', '--referee', 'NONE'],
                   check=True, stdout=subprocess.DEVNULL)
elif not resumed and {ledger in ('other', 'dry', 'broken')!r}:
    with Path({str(lane_ledger)!r}).open('a') as stream:
        row = {ledger!r}
        data = dict(job='other-job' if row == 'other' else 'fixture-job', new=row == 'other')
        print('broken' if row == 'broken' else json.dumps(data), file=stream)
time.sleep({sleep!r})
print(json.dumps(dict(is_error=False, subtype='success', result='fixture', total_cost_usd=0.25)))
sys.exit({int(fails)})
''')
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == int(fails), proc.stderr
    log = (jobs / 'fixture-job.log').read_text()
    calls = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    receipt = json.loads((jobs / 'fixture-job.log.selection.json').read_text())
    return calls, log, receipt


def test_no_floor_leaves_the_job_alone(tmp_path):
    calls, log, receipt = run_floor(tmp_path, floor=None)
    assert len(calls) == 1
    assert 'effort-floor resume' not in log and 'effort_floor' not in receipt


def test_early_no_result_resumes_once_with_original_prompt_route_and_remaining_budget(tmp_path):
    calls, log, receipt = run_floor(tmp_path, sleep=1.1, on_resume='Shipped: a better bound')
    initial, resume = calls
    floor = receipt['effort_floor']
    elapsed = floor['resume_at_seconds'] / 60
    remaining = floor['remaining_seconds'] / 60
    assert 0 < elapsed < 120 and 0 < remaining < 240
    assert resume['model'] == initial['model'] == 'fixture-claude'
    assert resume['budget'] == '0.75'
    assert resume['prompt'].startswith(initial['prompt'])
    assert f'continue: you stopped at {elapsed:.2f} of 240.00 minutes with no result. ' in resume['prompt']
    assert f'You have {remaining:.2f} minutes left.' in resume['prompt']
    assert ('Do not repeat what your ledger or REPORT already tried; widen or change the search, '
            'and say in REPORT.md what is different this time.') in resume['prompt']
    assert 'RESUME (attempt 2)' in resume['prompt']
    assert log.count(f'effort-floor resume at {elapsed:.2f}/240.00 min') == 1
    assert log.count('MODEL_SELECTION ') == log.count('MODEL_OUTCOME ') == 1
    assert log.count('MODEL_ATTEMPT_OUTCOME ') == 1
    grades = [json.loads(line) for line in (tmp_path / 'jobs/everyday-grades.jsonl').read_text().splitlines()]
    assert [row['grade'] for row in grades] == ['void: attempt continued before grading', 'pass']
    assert len({row['run_id'] for row in grades}) == 2
    assert 'quit_at_seconds' not in floor


@pytest.mark.parametrize('report,ledger', [
    ('Shipped: a better bound', None),
    ('Shipped: no result\nRESULT: yes', None),
    ('Shipped: nothing\nVerdict: PASS', None),
    ('Shipped: nothing', 'own'),
])
def test_early_result_skips_the_resume(tmp_path, report, ledger):
    calls, log, receipt = run_floor(tmp_path, report=report, ledger=ledger)
    assert len(calls) == 1
    assert 'effort-floor resume' not in log and 'effort_floor' not in receipt


def test_late_exit_skips_the_resume(tmp_path):
    calls, log, receipt = run_floor(tmp_path, floor='10%', timeout=8, sleep=1.1)
    assert len(calls) == 1
    assert 'effort-floor resume' not in log and 'effort_floor' not in receipt


def test_missing_report_cannot_trigger_a_resume(tmp_path):
    calls, log, receipt = run_floor(tmp_path, report=None)
    assert len(calls) == 1
    assert 'effort-floor resume' not in log and 'effort_floor' not in receipt


def test_watchdog_resume_does_not_get_an_effort_resume(tmp_path):
    calls, log, receipt = run_floor(tmp_path, watchdog=True)
    assert len(calls) == 1 and 'RESUME (attempt 2)' in calls[0]['prompt']
    assert 'effort-floor resume' not in log and 'effort_floor' not in receipt


@pytest.mark.parametrize('ledger', ['other', 'dry'])
def test_second_early_exit_is_final_and_partial_despite_passing_checks(tmp_path, ledger):
    calls, log, receipt = run_floor(tmp_path, report='Shipped: no result. I found a special case.',
                                    ledger=ledger, existing=True)
    assert len(calls) == 2 and log.count('effort-floor resume') == 1
    grade = json.loads((tmp_path / 'jobs/everyday-grades.jsonl').read_text().splitlines()[-1])
    elapsed = receipt['effort_floor']['quit_at_seconds'] / 60
    assert grade['grade'] == 'partial'
    assert grade['note'] == f'effort floor: quit at {elapsed:.2f}/240.00 min, no result'


@pytest.mark.parametrize('floor,ledger,timeout', [('96%', None, 14400), ('50%', 'broken', 14400), ('50%', None, 0)])
def test_effort_floor_errors_warn_and_keep_the_successful_exit(tmp_path, floor, ledger, timeout):
    calls, log, receipt = run_floor(tmp_path, floor=floor, ledger=ledger, timeout=timeout)
    assert len(calls) == 1 and 'effort_floor' not in receipt
    assert '[launch.effort-floor] WARNING' in log


def test_unsuccessful_exit_preserves_the_code(tmp_path):
    calls, log, receipt = run_floor(tmp_path, fails=True)
    assert len(calls) == 1 and 'effort_floor' not in receipt
    assert re.search(r'^exit 1 ', log, re.M)


def test_codex_continuation_stops_at_its_remaining_wall_budget(tmp_path):
    jobs, env = harness(tmp_path, ASK + '\nEffort floor: 95%\n')
    Path(env['RH_ROLES_FILE']).write_text(json.dumps(dict(roles={'batch': ['gpt-6.2-sol']}, routes={
        'gpt-6.2-sol': {'canonical': 'openai/gpt-6.2-sol', 'cli': 'codex'}})))
    cli = Path(env['LAUNCH_CLAUDE'])
    cli.write_text(f'#!{sys.executable}\n'
                   'from pathlib import Path\nimport sys, time\n'
                   'if "continue: you stopped" in sys.stdin.read():\n'
                   '    time.sleep(60)\n'
                   'Path("REPORT.md").write_text("Shipped: nothing\\n")\n')
    env.update(AGENT_BACKEND='codex', LAUNCH_CODEX=str(cli), LAUNCH_TIMEOUT_SECONDS='6',
               RH_HEADROOM_ROUTING='0', RH_AGY_CLOSED='test', LAUNCH_DETACH='',
               RSTACK_STATE_DIR=str(tmp_path / 'state'))
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=20)
    assert proc.returncode == 124, proc.stderr
    receipt = json.loads((jobs / 'fixture-job.log.selection.json').read_text())['effort_floor']
    log = (jobs / 'fixture-job.log').read_text()
    assert log.count('effort-floor resume') == 1
    assert f"wall-clock cap of {receipt['remaining_seconds']}s reached" in log


def test_stopping_the_bounded_codex_executor_also_stops_its_cli(tmp_path):
    cli = tmp_path / 'codex'
    cli.write_text(f'#!{sys.executable}\n'
                   'from pathlib import Path\nimport signal, time\n'
                   'def stop(*_):\n'
                   '    Path("stopped").touch()\n'
                   '    raise SystemExit(0)\n'
                   'signal.signal(signal.SIGTERM, stop)\n'
                   'Path("ready").touch()\n'
                   'time.sleep(60)\n')
    cli.chmod(0o755)
    executor = LAUNCH.parents[1] / 'harness/agent_executor.py'
    with subprocess.Popen([sys.executable, str(executor), '--backend', 'codex', '--executable', str(cli),
                           '--directory', str(tmp_path), '--model', 'fixture', '--effort', 'low',
                           '--output', str(tmp_path / 'last'), '--timeout-seconds', '30'],
                          stdin=subprocess.DEVNULL,
                          env=dict(os.environ, RH_EFFORT_FLOOR_JOB='fixture-job')) as proc:
        try:
            deadline = time.monotonic() + 5
            while not (tmp_path / 'ready').is_file() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert (tmp_path / 'ready').is_file()
        finally:
            proc.terminate()
        assert proc.wait(timeout=15) == 143
    assert (tmp_path / 'stopped').is_file()


@pytest.mark.parametrize('shipped', ['nothing', 'NO RESULT: bar not met', 'none', 'no new bound', 'No improvement on C44'])
def test_a_shipped_line_saying_no_is_not_a_result(shipped, tmp_path):
    """11-22 review: hunts write their nothing in many ways; none of them may skip the resume."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('effort_floor', Path(__file__).resolve().parents[1] / 'harness/tools/effort_floor.py')
    ef = importlib.util.module_from_spec(spec); spec.loader.exec_module(ef)
    assert not ef.met_bar('Shipped: ' + shipped + '\n', (tmp_path / 'RESULTS.jsonl',) * 2, (0, 0), 'j')
    assert ef.met_bar('Shipped: a new bound 0.25197\n', (tmp_path / 'RESULTS.jsonl',) * 2, (0, 0), 'j')
