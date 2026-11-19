"""A returned delegated job is graded at return by its own checks, else by the lane's reviewing model."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
import auto_grade  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def returned(tmp_path, rc=0, report='Shipped: the table', status='You asked: a table. I will: build it.',
             spec='Build the table.\nCheck: test -f out.txt\n', model='gemini-4-argon-low'):
    work = tmp_path / 'work'; work.mkdir(exist_ok=True)
    (work / 'REPORT.md').write_text(report + '\n')
    (work / 'STATUS.md').write_text(status + '\n')
    (work / 'out.txt').write_text('ok')
    receipt = tmp_path / 'job.log.selection.json'
    receipt.write_text(json.dumps(dict(selection_id='sid1', job='job', lane='lane-a', role='batch', model=model,
                                       source='delegate')))
    log = tmp_path / 'job.log'
    log.write_text('MODEL_OUTCOME ' + json.dumps(dict(selection_id='sid1', exit_code=rc)) + '\n')
    (tmp_path / 'job.md').write_text(spec)
    return receipt, log, work, tmp_path / 'job.md'


def graded(tmp_path):
    return json.loads((tmp_path / 'everyday-grades.jsonl').read_text().splitlines()[-1])


def test_a_returned_job_with_passing_checks_is_graded_pass_with_no_session_step(tmp_path):
    receipt, log, work, spec = returned(tmp_path)
    assert auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec)]) == 0
    row = graded(tmp_path)
    assert (row['grade'], row['producer'], row['grader'], row['auto']) == ('pass', 'gemini-4-argon-low', 'checks', True)
    assert 'MODEL_GRADE' in log.read_text()


def test_a_failed_check_is_partial_and_no_exit_0_or_no_shipped_line_is_fail(tmp_path):
    receipt, log, work, spec = returned(tmp_path, spec='Check: test -f missing.txt\n')
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec)])
    assert graded(tmp_path)['grade'] == 'partial'
    receipt, log, work, spec = returned(tmp_path, rc=1)
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec)])
    assert graded(tmp_path)['grade'] == 'fail'
    receipt, log, work, spec = returned(tmp_path, report='Working on it.')
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec)])
    assert graded(tmp_path)['grade'] == 'fail'


def test_without_checks_the_lanes_reviewing_model_grades_and_is_recorded(tmp_path, monkeypatch):
    receipt, log, work, spec = returned(tmp_path, spec='Write a short review of the paper.\n')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps({'roles': {'review': ['claude-opus-5-5']},
                                 'routes': {'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'}}}))
    fake = tmp_path / 'fake-claude'
    fake.write_text('#!' + sys.executable + '\nimport json\n'
                    'print(json.dumps({"is_error": False, "subtype": "success", "result": "PARTIAL\\nhalf of it"}))\n')
    fake.chmod(0o755)
    monkeypatch.setenv('LAUNCH_CLAUDE', str(fake))
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')   # the grader itself is never delegated
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec),
                     '--roles-file', str(roles)])
    row = graded(tmp_path)
    assert (row['grade'], row['grader'], row['producer']) == ('partial', 'claude-opus-5-5', 'gemini-4-argon-low')


def test_a_grader_that_cannot_answer_leaves_the_job_ungraded(tmp_path, monkeypatch):
    receipt, log, work, spec = returned(tmp_path, spec='Write a short review.\n')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps({'roles': {'review': ['claude-opus-5-5']},
                                 'routes': {'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'}}}))
    monkeypatch.setenv('LAUNCH_CLAUDE', str(tmp_path / 'absent-claude'))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec),
                     '--roles-file', str(roles)])
    assert graded(tmp_path)['grade'] == 'ungraded'


def test_the_launcher_grades_a_returned_delegated_job_by_itself(tmp_path):
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    (jobs / 'fixture.md').write_text('Write out.txt and the report.\nCheck: test -f out.txt\n')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps({'roles': {'batch': ['claude-opus-5-5']}, 'routes': {
        'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'},
        'gpt-6.2-sol': {'cli': 'codex', 'canonical': 'openai/gpt-6.2-sol'}}}))
    fake = tmp_path / 'fake-codex'
    fake.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport sys\n'
                    'Path("out.txt").write_text("ok")\nPath("REPORT.md").write_text("Shipped: out.txt\\n")\n'
                    'Path("STATUS.md").write_text("You asked: out.txt. I will: write it.\\n")\n'
                    'Path(sys.argv[sys.argv.index("-o") + 1]).write_text("done")\n')
    fake.chmod(0o755)
    work = tmp_path / 'work'; work.mkdir()
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CODEX=str(fake), LAUNCH_ARTIFACT_DIR=str(jobs),
               LAUNCH_STATE=str(tmp_path / 'registry'), RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1',
               RH_DELEGATE_SHARE='1', RSTACK_STATE_DIR=str(tmp_path / 'state'))
    proc = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), 'fixture', str(work)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((jobs / 'fixture.log.selection.json').read_text())
    assert receipt['source'] == 'delegate' and receipt['model'] == 'gpt-6.2-sol'
    row = json.loads((jobs / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['grader'], row['producer']) == ('pass', 'checks', 'gpt-6.2-sol')
