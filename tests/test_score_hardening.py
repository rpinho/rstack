"""Structural scoring regressions; all writes are synthetic and no alert is sent."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'harness'), str(REPO / 'harness/tools'), str(REPO / 'leaderboard')]
from model_slugs import canon, MODELS
import delegate_log
import run_records
import score_migrate
import score_canary
import worker_models


@pytest.mark.parametrize('aliases, expected', [
    (['google/gemini-4-neon-high', 'gemini-4-neon-high', 'gemini-4-neon'], 'google/gemini-4-neon-high'),
    (['anthropic/claude-sonnet-5.5', 'claude-sonnet-5-5[1m]', 'claude-sonnet-5-5-high'], 'anthropic/claude-sonnet-5.5'),
    (['gemini-4-hydrogen', 'gemini-4-hydrogen-high'], 'google/gemini-4-hydrogen-high'),
])
def test_all_aliases_share_one_registered_key(aliases, expected):
    assert {canon(alias) for alias in aliases} == {expected}
    assert expected in MODELS and canon(expected) == expected


def test_unknown_verdict_refused_by_each_writer(tmp_path):
    row = dict(model='gemini-4-neon-high', grade='almost passed')
    for writer in (run_records.append, lambda p, r: worker_models.log_record(p, '', r)):
        target = tmp_path / 'grades.jsonl'
        with pytest.raises(ValueError, match=r'pass \| partial \| fail \| harness_fail \| void: <reason>'):
            writer(target, row)
        assert not target.exists()
    assert delegate_log.main(['--model', row['model'], '--source', 'session', '--task', 'x',
                              '--verdict', row['grade'], '--asked', 'x', '--did', 'x', '--shipped', 'x']) == 0
    assert not run_records.runs_path().exists()


def test_migration_preserves_rows_and_live_input(tmp_path, capsys):
    path = tmp_path / 'grades.jsonl'
    rows = [dict(id=str(i), model='claude-sonnet-5-5[1m]', grade=g, reason=r) for i, (g, r) in enumerate([
        ('held', ''), ('overturned', ''), ('ungraded', 'quota'), ('ungraded', 'workdir incomplete: x'),
        ('retracted', 'bad harness'), ('unexpected', '')])]
    original = '\n'.join(json.dumps(r) for r in rows) + '\n'
    path.write_text(original)
    assert score_migrate.main([str(path), '--dry-run']) == 0
    target = path.with_name('grades.migrated.jsonl')
    assert not target.exists() and path.read_text() == original
    assert score_migrate.main([str(path), '--write']) == 0
    migrated = list(run_records.read_jsonl(target))
    assert [r['grade'] for r in migrated] == ['pass', 'fail', 'void: quota', 'harness_fail',
                                              'void: retracted', 'void: legacy unexpected']
    assert len(migrated) == len(rows) and path.read_text() == original
    assert {r['model'] for r in migrated} == {'anthropic/claude-sonnet-5.5'}
    with pytest.raises(FileExistsError):
        score_migrate.main([str(path), '--write'])


def test_run_exists_while_executor_is_alive_then_survives_its_death(tmp_path):
    fake = tmp_path / 'fake-codex'
    fake.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(2)\n')
    fake.chmod(0o755)
    process = subprocess.Popen([sys.executable, str(REPO / 'harness/agent_executor.py'),
        '--backend', 'codex', '--executable', str(fake), '--model', 'gpt-6.2-sol', '--effort', 'medium',
        '--directory', str(tmp_path), '--output', str(tmp_path / 'out'), '--timeout-seconds', '2'],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    process.stdin.close()
    try:
        until = time.monotonic() + 5
        while not run_records.runs_path().exists() and time.monotonic() < until:
            time.sleep(.02)
        row, = run_records.read_jsonl(run_records.runs_path())
        assert process.poll() is None
        assert row['model'] == 'openai/gpt-6.2-sol' and row['effort'] == 'medium'
        assert row['closed_at'] is None
        assert row['tokens'] is row['cost_usd'] is row['wall_seconds'] is None
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        assert list(run_records.read_jsonl(run_records.runs_path())) == [row]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        # The synthetic child shares the executor's test-owned process group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_close_twice_changes_nothing_and_preserves_reported_usage():
    run_records.open_run(dict(run_id='once', job='once', utc=run_records.utc_now(), model='gemini-4-neon-high'))
    run_records.close_run('once', tokens=42, cost_usd=.03)
    before = run_records.runs_path().read_bytes()
    run_records.close_run('once', tokens=999, cost_usd=99)
    assert run_records.runs_path().read_bytes() == before
    row = list(run_records.read_jsonl(run_records.runs_path()))[-1]
    assert row['tokens'] == 42 and row['cost_usd'] == .03 and row['closed_at']


def test_delegate_row_is_counted_by_leaderboard(tmp_path, monkeypatch):
    receipts = tmp_path / 'receipts'
    receipts.mkdir()
    (tmp_path / 'lanes').mkdir()
    ledger = tmp_path / 'evaluations.jsonl'
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('RH_EVIDENCE_ROOT', str(tmp_path))
    monkeypatch.setenv('MODEL_LEDGER', str(ledger))
    args = ['--model', 'gemini-4-neon-high', '--source', 'session', '--session', 'agy-example',
            '--task', 'shipped unit', '--verdict', 'pass', '--asked', 'a report', '--did', 'verified result',
            '--shipped', 'REPORT.md', '--run-id', 'unit-1']
    assert delegate_log.main(args) == delegate_log.main(args) == 0
    assert len(list(run_records.read_jsonl(run_records.grades_path()))) == 1
    assert len(list(run_records.read_jsonl(run_records.runs_path()))) == 1
    done = subprocess.run([sys.executable, str(REPO / 'leaderboard/model-roles.py'), 'ingest'],
                           capture_output=True, text=True, timeout=15)
    assert done.returncode == 0, done.stderr
    row, = run_records.read_jsonl(ledger)
    assert row['model'] == 'google/gemini-4-neon-high' and row['outcome'] == 'pass'
    spec = importlib.util.spec_from_file_location('hardening_roles', REPO / 'leaderboard/model-roles.py')
    roles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roles)
    assert roles.evidence()['builder'][row['model']]['n'] == 1
    assert roles.OWNER_RANK['google/gemini-4-neon-high'] == roles.OWNER_RANK['anthropic/claude-opus-5.5'] == 1
    # 11-27 (Ricardo via general 1127j): Astra #2, Fable 5.2 #3, and the page header says so.
    assert (roles.OWNER_RANK['openai/gpt-6.2-astra'], roles.OWNER_RANK['anthropic/claude-fable-5.2']) == (2, 3)
    assert 'Astra #2, Fable #3' in roles.OWNER_RANK_LINE
    # A historical native slug in evaluations must not duplicate the canonical observation.
    ledger.write_text(json.dumps(dict(row, model='gemini-4-neon-high', outcome='held')) + '\n')
    again = subprocess.run([sys.executable, str(REPO / 'leaderboard/model-roles.py'), 'ingest'],
                           capture_output=True, text=True, timeout=15)
    assert again.returncode == 0, again.stderr
    assert len(list(run_records.read_jsonl(ledger))) == 1


def test_owed_lists_25h_run_and_passes_once_graded(capsys):
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
    run_records.append(run_records.runs_path(), dict(run_id='owed', job='owed', model='gemini-4-neon-high', utc=when.isoformat()))
    assert score_canary.main(['--owed']) == 1
    assert 'missing grade: run_id=owed' in capsys.readouterr().out
    run_records.append(run_records.grades_path(), run_records.grade_fields('owed', 'owed', 'google/gemini-4-neon-high',
                                                                        'builder', 'pass', 'checked'))
    assert score_canary.main(['--owed']) == 0
    assert 'missing grade:' not in capsys.readouterr().out


def test_auto_grade_closes_run_idempotently(tmp_path):
    import auto_grade
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'STATUS.md').write_text('You asked: x. I will: x.\n')
    (work / 'REPORT.md').write_text('Shipped: x\n')
    spec = tmp_path / 'job.md'
    spec.write_text('Check: test -f REPORT.md\n')
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps(dict(selection_id='s', run_id='autoclose', job='x',
                                       model='gemini-4-neon-high', role='builder')))
    log = tmp_path / 'job.log'
    log.write_text('MODEL_OUTCOME ' + json.dumps(dict(selection_id='s', run_id='autoclose', exit_code=0)) + '\n')
    run_records.open_run(dict(run_id='autoclose', job='x', utc=run_records.utc_now(), model='gemini-4-neon-high'))
    assert auto_grade.grade(receipt, log, work, spec)['grade'] == 'pass'
    closed = run_records.runs_path().read_bytes()
    assert auto_grade.grade(receipt, log, work, spec)['grade'] == 'pass'
    assert run_records.runs_path().read_bytes() == closed


def test_new_scorer_outcomes_survive_feed_export(tmp_path):
    import grades_feed
    ledger = tmp_path / 'evaluations.jsonl'
    rows = [dict(id=str(i), model='google/gemini-4-neon-high', pick_role='builder',
                 outcome=value, date='2026-11-26') for i, value in enumerate(
                     ['pass', 'partial', 'fail', 'harness_fail', 'void: quota'])]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    feed = grades_feed.ledger_rows(ledger)
    assert [r['verdict'] for r in feed] == ['pass', 'partial', 'fail', 'void', 'void']
    assert [r['harness_fail'] for r in feed] == ['0', '0', '0', '1', '0']


def test_reported_usage_is_preserved_without_estimates(tmp_path):
    import agent_executor
    output = tmp_path / 'provider.json'
    output.write_text(json.dumps(dict(usage=dict(input_tokens=40, output_tokens=2), total_cost_usd=.125), indent=2))
    assert agent_executor.reported_usage(output) == dict(tokens=42, cost_usd=.125)
    output.write_text('plain output')
    assert agent_executor.reported_usage(output, 'tokens used\n1,234\n') == dict(tokens=1234, cost_usd=None)
    assert agent_executor.reported_usage(output) == dict(tokens=None, cost_usd=None)


def test_owed_retains_existing_two_hour_failure_rule(capsys):
    now = dt.datetime.now(dt.timezone.utc)
    for ident, hours in [('three-hours', 3), ('graded', 1)]:
        run_records.append(run_records.runs_path(), dict(run_id=ident, job=ident, model='gemini-4-neon-high',
                                                        utc=(now - dt.timedelta(hours=hours)).isoformat(),
                                                        closed_at=(now - dt.timedelta(hours=hours - .5)).isoformat()))
    run_records.append(run_records.grades_path(), run_records.grade_fields('graded', 'graded', 'gemini-4-neon-high',
                                                                          'builder', 'pass', 'checked'))
    assert score_canary.main(['--owed']) == 1
    assert 'missing grade: run_id=three-hours' in capsys.readouterr().out


def test_auto_grade_harvests_remote_executor_metrics(tmp_path):
    import auto_grade
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'STATUS.md').write_text('You asked: x. I will: x.\n')
    (work / 'REPORT.md').write_text('Shipped: x\n')
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps(dict(selection_id='s', run_id='remote', job='x', model='gemini-4-neon-high', role='builder')))
    log = tmp_path / 'job.log'
    summary = dict(run_id='remote', closed_at=run_records.utc_now(), wall_seconds=12, tokens=77, cost_usd=.125, rc=0)
    log.write_text('EXECUTOR_RUN ' + json.dumps(summary) + '\nMODEL_OUTCOME ' +
                   json.dumps(dict(selection_id='s', run_id='remote', exit_code=0)) + '\n')
    run_records.open_run(dict(run_id='remote', job='x', utc=run_records.utc_now(), model='gemini-4-neon-high'))
    auto_grade.grade(receipt, log, work, None)
    row = list(run_records.read_jsonl(run_records.runs_path()))[-1]
    assert {key: row[key] for key in summary} == summary


def test_a_run_still_open_is_not_owed_a_grade_until_it_is_stuck(capsys):
    # 11-28 (general): planets_tnodes_1127 was flagged "missing grade 2.3 h" while it waited, by design, for a data window.
    now = dt.datetime.now(dt.timezone.utc)
    for ident, hours in [('open-3h', 3), ('open-30h', 30)]:
        run_records.append(run_records.runs_path(), dict(run_id=ident, job=ident, model='gemini-4-neon-high',
                                                        utc=(now - dt.timedelta(hours=hours)).isoformat()))
    score_canary.main([])
    out = capsys.readouterr().out
    assert 'missing grade: run_id=open-3h' not in out and 'missing grade: run_id=open-30h' in out
