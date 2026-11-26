"""End-to-end scoring regressions using only local synthetic evidence."""
import datetime as dt
import os
from pathlib import Path
import plistlib
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'leaderboard'))
import driver_grades
import run_grades
import score_canary
from run_grades import run_records


@pytest.fixture
def logs(tmp_path, monkeypatch):
    runs = tmp_path / 'model-runs.jsonl'
    monkeypatch.setenv('RH_MODEL_RUNS_LOG', str(runs))
    return runs


def write_run(path, ident, hours, model='gemini-4-neon-high', **extra):
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    row = dict(run_id=ident, job=ident, model=model, utc=when.isoformat(), **extra)
    run_records.append(path, row)
    return row


def test_old_run_without_grade_fails_the_canary(logs, capsys):
    old = write_run(logs, 'old', 3)
    write_run(logs, 'recent', .1)
    row = run_records.grade_fields('recent', 'recent', old['model'], 'batch', 'pass', 'checked')
    run_records.append(run_records.grades_path(), row)
    assert score_canary.main([]) == 1
    output = capsys.readouterr().out
    assert 'missing grade: run_id=old job=old' in output
    assert 'runs=2 graded=1 pass=1 partial=0 fail=0 harness_fail=0 void=0' in output
    assert not logs.with_name('score-canary-alerts.jsonl').exists()


def test_model_with_recent_runs_and_zero_grades_fails_before_two_hours(logs, capsys):
    write_run(logs, 'new', .1)
    assert score_canary.main([]) == 1
    output = capsys.readouterr().out
    assert 'model has zero grades in 24h: run_id=new' in output
    assert 'missing grade:' not in output


def test_canary_reports_incomplete_grade_even_when_recent(logs, capsys):
    row = write_run(logs, 'bad', .1)
    grade = run_records.grade_fields('bad', 'bad', row['model'], 'batch', 'harness_fail',
                                     'workdir incomplete: REPORT.md', missing_files=['REPORT.md'])
    run_records.append(run_records.grades_path(), grade)
    assert score_canary.main([]) == 1
    output = capsys.readouterr().out
    assert 'workdir incomplete: REPORT.md: run_id=bad' in output
    assert 'runs=1 graded=1 pass=0 partial=0 fail=0 harness_fail=1 void=0' in output


def test_join_uses_one_legacy_grade_and_prefers_explicit_run_keys(logs):
    for days in (2, 3):
        run_records.append(logs, dict(job='repeat', model='gpt-6.2-sol', utc=f'2026-11-0{days}T10:00:00Z'))
    run = write_run(logs, 'current', 1)
    grades = run_records.grades_path()
    run_records.append(grades, dict(id='old', job='repeat', model='gpt-6.2-sol', grade='fail', source_kind='everyday'))
    run_records.append(grades, run_records.grade_fields('current', 'another-name', run['model'], 'batch', 'pass', 'checked'))
    pairs, historical = run_grades.table()
    assert [record[0]['grade'] if record else None for _, record in pairs] == ['pass', 'fail', None]
    assert pairs[-1][0]['run_id'] == 'repeat@2026-11-02T10:00:00Z'
    assert not historical


def test_driver_result_and_empty_round_get_one_grade_each(tmp_path, logs, monkeypatch):
    root = tmp_path / 'root'
    lane = root / 'lanes/example'
    lane.mkdir(parents=True)
    monkeypatch.setenv('RH_EVIDENCE_ROOT', str(root))
    monkeypatch.setattr(driver_grades, 'command', lambda *_: '')
    file = lane / 'DRIVER_STATUS.md'
    run_records.append(lane / 'RESULTS.jsonl', dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                                                  referee='HOLDS', link='proof.txt'))
    file.write_text('Driver: agy-example (Gemini Neon)\nDone: proof.txt\n')
    assert driver_grades.main() == driver_grades.main() == 0
    file.write_text('Driver: agy-example (Gemini Neon)\nWaiting on data\n')
    assert driver_grades.main() == driver_grades.main() == 0
    pairs, _ = run_grades.table()
    assert {(run['backend'], grade[0]['grade']) for run, grade in pairs} == {
        ('agy-driver', 'pass'), ('agy-driver', 'partial')}
    assert len(list(run_records.read_jsonl(logs))) == 2
    assert len(list(run_records.read_jsonl(run_records.grades_path()))) == 2
    assert pairs[0][1][0]['reason'] == 'no output'


def test_scorer_plist_uses_hourly_interval():
    with (REPO / 'leaderboard/com.example.model-scorer.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    assert plist['StartInterval'] == 3600
    assert 'StartCalendarInterval' not in plist


@pytest.mark.parametrize('backend, code', [
    ('agy', 'print(\'{"status":"ERROR","error":"RESOURCE_EXHAUSTED: Resets in 4h"}\')'),
    ('codex', 'sys.stderr.write("usage_limit_reached. Try again at 4 PM.\\n"); sys.exit(1)'),
    ('claude', 'print(\'{"is_error":true,"subtype":"error","result":"You\' + chr(39) + \'ve hit your limit · resets 6pm"}\')'),
])
def test_executor_quota_records_run_grade_and_reset(backend, code, tmp_path, logs, monkeypatch):
    fake = tmp_path / 'executor'
    fake.write_text(f'#!{sys.executable}\nimport sys\n{code}\n')
    fake.chmod(0o755)
    monkeypatch.setenv('RSTACK_LANE', 'fixture-lane')
    env = dict(os.environ, RH_JOB='fixture')
    done = subprocess.run([sys.executable, str(REPO / 'harness/agent_executor.py'), '--backend', backend,
                           '--executable', str(fake), '--directory', str(tmp_path), '--model', 'fixture',
                           '--effort', 'low', '--output', str(tmp_path / 'last')], input='', env=env,
                          capture_output=True, text=True, timeout=10)
    assert done.returncode == 1, done.stderr
    run, record = run_grades.table()[0][0]
    quota, = run_records.read_jsonl(logs.with_name('quota-hits.jsonl'))
    assert quota['run_id'] == run['run_id'] and quota['model'] == 'fixture'
    assert quota['lane'] == 'fixture-lane' and quota['utc'] == run['utc'] and quota['reset_time']
    assert (record[0]['grade'], record[0]['reason']) == ('void: quota', 'quota')


def test_driver_launch_follows_last_attempt_instead_of_grading_two_jobs(tmp_path, logs, monkeypatch):
    root = tmp_path / 'root'
    lane = root / 'lanes/example'
    lane.mkdir(parents=True)
    monkeypatch.setenv('RH_EVIDENCE_ROOT', str(root))
    monkeypatch.setattr(driver_grades, 'command', lambda *_: '')
    (lane / 'DRIVER_STATUS.md').write_text('Driver: agy-example\nDone: watched the launch\n')
    first = write_run(logs, 'first', 1, driver='agy-example', backend='codex', launch_group='same')
    last = write_run(logs, 'last', .5, driver='agy-example', backend='codex', launch_group='same')
    for row, verdict in [(first, 'void: continued'), (last, 'fail')]:
        run_records.append(run_records.grades_path(), run_records.grade_fields(
            row['run_id'], row['job'], row['model'], 'batch', verdict, 'synthetic'))
    assert driver_grades.main() == 0
    pairs, _ = run_grades.table()
    (driver, record), = [(r, g) for r, g in pairs if r['backend'] == 'agy-driver']
    assert driver['downstream_launch'] == 'same'
    assert record[0]['grade'] == 'fail'


def test_driver_commit_grade_changes_when_a_remote_ref_contains_it(tmp_path, logs, monkeypatch):
    root = tmp_path / 'root'
    lane = root / 'lanes/example'
    lane.mkdir(parents=True)
    monkeypatch.setenv('RH_EVIDENCE_ROOT', str(root))
    monkeypatch.setattr(driver_grades, 'pane_paths', lambda: {'agy-example': {lane}})

    def git(*argv):
        return subprocess.check_output(['git', '-C', str(lane), *argv], text=True).strip()

    git('init', '-q')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-q', '--allow-empty', '-m', 'Fixture result')
    commit = git('rev-parse', 'HEAD')
    (lane / 'DRIVER_STATUS.md').write_text(f'Driver: agy-example\nDone: committed {commit}\n')
    assert driver_grades.main() == 0
    assert run_grades.table()[0][0][1][0]['grade'] == 'void: local commit awaiting push or merge'
    git('update-ref', 'refs/remotes/origin/main', commit)
    assert driver_grades.main() == 0
    (run, record), = run_grades.table()[0]
    assert run['commit'] == commit
    assert record[0]['grade'] == 'pass'


def test_scorer_and_canary_read_the_same_run_grade_without_a_legacy_receipt(tmp_path, logs, monkeypatch):
    receipts = tmp_path / 'receipts'
    receipts.mkdir()
    ledger = tmp_path / 'evaluations.jsonl'
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('MODEL_LEDGER', str(ledger))
    (tmp_path / 'lanes').mkdir()
    monkeypatch.setenv('RH_EVIDENCE_ROOT', str(tmp_path))
    run = write_run(logs, 'current', 3)
    run_records.append(run_records.grades_path(), run_records.grade_fields(
        run['run_id'], run['job'], run['model'], 'batch', 'pass', 'checked'))
    assert score_canary.main([]) == 0
    done = subprocess.run([sys.executable, str(REPO / 'leaderboard/model-roles.py'), 'ingest'],
                          capture_output=True, text=True, timeout=10)
    assert done.returncode == 0, done.stderr
    grade, = run_records.read_jsonl(ledger)
    assert grade['case'] == 'receipt-everyday:grade-current'
    assert grade['model'] == 'google/gemini-4-neon-high' and grade['outcome'] == 'pass'
