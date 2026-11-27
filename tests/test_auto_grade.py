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
    assert (row['grade'], row['producer'], row['grader'], row['auto']) == ('pass', 'google/gemini-4-argon-low', 'checks', True)
    assert 'MODEL_GRADE' in log.read_text()


def test_a_failed_check_is_partial_and_no_exit_0_or_no_shipped_line_is_fail(tmp_path):
    receipt, log, work, spec = returned(tmp_path, spec='Check: grep -qx different out.txt\n')
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
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec),
                     '--roles-file', str(roles)])
    row = graded(tmp_path)
    assert (row['grade'], row['grader'], row['producer']) == ('partial', 'claude-opus-5-5', 'google/gemini-4-argon-low')


def test_a_grader_that_cannot_answer_leaves_the_job_ungraded(tmp_path, monkeypatch):
    receipt, log, work, spec = returned(tmp_path, spec='Write a short review.\n')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps({'roles': {'review': ['claude-opus-5-5']},
                                 'routes': {'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'}}}))
    monkeypatch.setenv('LAUNCH_CLAUDE', str(tmp_path / 'absent-claude'))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec),
                     '--roles-file', str(roles)])
    assert graded(tmp_path)['grade'] == 'void: grader gave no verdict (exit 1)'


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
               RSTACK_STATE_DIR=str(tmp_path / 'state'), RH_CLAUDE_DELEGATE_DEFAULT='1', RH_AGY_CLOSED='test')
    proc = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), 'fixture', str(work)], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads((jobs / 'fixture.log.selection.json').read_text())
    assert receipt['source'] == 'delegate' and receipt['model'] == 'gpt-6.2-sol'
    row = json.loads((jobs / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['grader'], row['producer']) == ('pass', 'checks', 'openai/gpt-6.2-sol')


def test_a_host_jobs_checks_run_on_the_host_where_its_outputs_are(tmp_path, monkeypatch):
    # 11-20: jobs run on the m5 from the M4 wrote out.txt there; the M4 has only STATUS.md and REPORT.md back, and
    # a reviewer reading the M4's copy graded all three fail.
    receipt, log, work, spec = returned(tmp_path)
    (work / 'out.txt').unlink()   # the controller's copy has no outputs
    host_side = tmp_path / 'host'
    (host_side / work.relative_to('/')).mkdir(parents=True)
    (host_side / work.relative_to('/') / 'out.txt').write_text('ok')
    (host_side / work.relative_to('/') / 'STATUS.md').write_text('You asked: a table. I will: build it.\n')
    (host_side / work.relative_to('/') / 'REPORT.md').write_text('Shipped: the table\n')
    ssh = tmp_path / 'fake-ssh'
    ssh.write_text('#!/bin/sh\nwhile [ "$1" = "-o" ]; do shift 2; done\necho "$1" >> ' + str(tmp_path / 'hosts') +
                   '\nshift\ncd ' + str(host_side) + ' && exec sh -c "$(echo "$*" | sed "s|cd |cd ' + str(host_side) + '|")"\n')
    ssh.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(ssh))
    auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec), '--host', 'm5'])
    row = graded(tmp_path)
    assert (row['grade'], row['grader']) == ('pass', 'checks') and (tmp_path / 'hosts').read_text().splitlines() == ['m5', 'm5']
    assert row['grade_host'] == 'm5' and row['grade_dir'] == str(work)
    assert 'cd ' in (REPO / 'tools/launch.sh').read_text() and '--host} ${LAUNCH_HOST:+$LAUNCH_HOST}' in \
        (REPO / 'tools/launch.sh').read_text()


def test_an_executor_that_is_not_installed_is_a_harness_error_not_a_fail(tmp_path):
    # 11-22 (general): ddbench_scan_1122 was routed to agy on the M4, which has no agy, and graded FAIL for Hydrogen.
    receipt, log, work, spec = returned(tmp_path, rc=1, report='nothing', status='nothing', model='gemini-4-hydrogen-medium')
    log.write_text('MODEL_SELECTION ' + json.dumps(dict(selection_id='sid1')) + '\n'
                   "FileNotFoundError: [Errno 2] No such file or directory: 'agy'\n"
                   'MODEL_OUTCOME ' + json.dumps(dict(selection_id='sid1', exit_code=1)) + '\n')
    assert auto_grade.main(['--receipt', str(receipt), '--log', str(log), '--dir', str(work), '--spec', str(spec)]) == 0
    row = graded(tmp_path)
    assert (row['grade'], row['grader']) == ('harness_fail', 'harness') and 'agy' in row['note']


def test_files_missing_from_the_jobs_own_dir_are_the_models_result(tmp_path):
    """11-27: cyvcf2/cperm/cskew exited 1 or 124 with no REPORT.md in their own dir. That is a fail, not a gap."""
    receipt, log, work, spec = returned(tmp_path, rc=124, spec='Check: grep -q ok "nested/out file.txt"\n')
    (work / 'REPORT.md').unlink()
    row = auto_grade.grade(receipt, log, work, spec)
    assert row['grade'] == 'fail' and 'not shipped: REPORT.md, nested/out file.txt' in row['reason']
    assert not row.get('missing_files')
    receipt, log, work, spec = returned(tmp_path, spec='Check: test -f missing.txt\n')
    row = auto_grade.grade(receipt, log, work, spec)
    assert row['grade'] == 'partial' and 'missing: missing.txt' in row['reason']


def test_an_unreachable_workdir_stays_ungraded_without_running_the_checks(tmp_path):
    receipt, log, work, spec = returned(tmp_path, rc=1, spec='Check: grep -q ok "nested/out file.txt"\n')
    gone = tmp_path / 'not-here'
    row = auto_grade.grade(receipt, log, gone, spec)
    assert row['grade'] == 'harness_fail'
    assert row['reason'].startswith('workdir incomplete: STATUS.md, REPORT.md')
    assert row['missing_files'][:2] == ['STATUS.md', 'REPORT.md']
    assert row['grade_dir'] == str(gone) and row['grade_host']


def test_a_sweep_stage_without_status_or_report_is_void(tmp_path):
    stage = tmp_path / 'lanes/planets/sweep-work/runs/r1'
    stage.mkdir(parents=True)
    receipt, log, work, spec = returned(stage)
    (work / 'REPORT.md').unlink(); (work / 'STATUS.md').unlink()
    row = auto_grade.grade(receipt, log, work, spec)
    assert row['grade'] == 'void: sweep stage' and not row.get('missing_files')
