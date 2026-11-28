"""Offline backfill, calibration, and public aggregation with synthetic records."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backfill_costs as backfill
import calibrate_costs as calibrate
import run_grades as rg

spec = importlib.util.spec_from_file_location('cost_test_roles', HERE / 'model-roles.py')
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)
NOW = dt.datetime(2026, 11, 27, 13, tzinfo=dt.timezone.utc)
SOL = 'openai/gpt-6.2-sol'
TOKENS = dict(input=200, cached_input=100, cache_write=0, output=30, reasoning=10, source='synthetic')


def dump(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def before(hours=0):
    return (NOW - dt.timedelta(hours=hours)).isoformat()


def test_backfill_is_append_only_windowed_and_retryable(tmp_path, monkeypatch):
    run_file = tmp_path / 'model-runs.jsonl'
    grade_file = tmp_path / 'everyday-grades.jsonl'
    monkeypatch.setenv('RH_MODEL_RUNS_LOG', str(run_file))
    monkeypatch.setenv('RH_EVERYDAY_GRADES', str(grade_file))
    evaluations = tmp_path / 'state/evaluations.jsonl'
    dump(evaluations, [{'sentinel': 'old ledger'}])
    runs = [dict(run_id=key, job='reused', utc=before(age), model=SOL, backend='codex')
            for key, age in [('known', 1), ('missing', 2), ('ungraded', 3), ('old', 1000)]]
    runs[0]['token_usage'] = TOKENS
    grades = [dict(id=f'grade-{key}', run_id=key, job='reused', source_kind='everyday', model=SOL,
                   grade=verdict) for key, verdict in [('known', 'pass'), ('missing', 'fail'), ('old', 'pass')]]
    dump(run_file, runs)
    dump(grade_file, grades)
    originals = [p.read_bytes() for p in (evaluations, run_file, grade_file)]
    path, considered, written = backfill.backfill(evaluations, NOW)
    assert path == evaluations.with_name('costs.jsonl') and (considered, written) == (2, 2)
    assert [p.read_bytes() for p in (evaluations, run_file, grade_file)] == originals
    costed = rg.sidecar(path)
    assert costed[('known', 'grade-known', SOL)]['api'] == pytest.approx(.00051)
    assert costed[('missing', 'grade-missing', SOL)]['api'] == 'unknown'
    assert backfill.backfill(evaluations, NOW)[2] == 0
    with path.open('ab') as output:
        output.write(b'{"stopped":')
    earlier = path.read_bytes()
    with run_file.open('a') as stream:
        stream.write(json.dumps(dict(runs[1], token_usage=TOKENS)) + '\n')
    assert backfill.backfill(evaluations, NOW)[2] == 1
    assert path.read_bytes().startswith(earlier)
    assert rg.sidecar(path)[('missing', 'grade-missing', SOL)]['tokens'] == TOKENS


def test_backfill_rejects_an_evaluations_path_that_aliases_the_sidecar(tmp_path):
    evaluations = tmp_path / 'evaluations.jsonl'
    evaluations.write_bytes(b'unchanged')
    (tmp_path / 'costs.jsonl').symlink_to(evaluations)
    with pytest.raises(ValueError, match='separate sidecar'):
        backfill.backfill(evaluations, NOW)
    assert evaluations.read_bytes() == b'unchanged'


def test_public_cost_stats_only_use_eligible_passes(tmp_path, monkeypatch):
    run_file = tmp_path / 'model-runs.jsonl'
    grade_file = tmp_path / 'everyday-grades.jsonl'
    evaluations = tmp_path / 'evaluations.jsonl'
    monkeypatch.setenv('RH_MODEL_RUNS_LOG', str(run_file))
    monkeypatch.setenv('RH_EVERYDAY_GRADES', str(grade_file))
    monkeypatch.setattr(mr, 'LEDGER', evaluations)
    monkeypatch.setattr(mr, 'now', lambda: NOW)
    jobs = [('a', 'pass'), ('b', 'pass'), ('c', 'pass'), ('unknown', 'pass'),
            ('d', 'partial'), ('e', 'fail')]
    runs, grades = [], []
    for key, verdict in jobs:
        runs.append(dict(run_id=key, job=key, model=SOL, utc=before(1)))
        grades.append(dict(id=f'grade-{key}', run_id=key, job=key, role='batch', model=SOL,
                           source_kind='everyday', grade=verdict, cost_usd=dict(
                               api='unknown', plan='unknown', tokens={'reason': 'missing'})))
    grades.append(dict(id='historical', job='pre-ledger', date='2026-11-26', role='batch', model=SOL,
                       source_kind='everyday', grade='pass'))
    grades[0]['cost_usd'] = dict(api=0, plan=.01, tokens=TOKENS, plan_as_of='2026-11-25')
    dump(run_file, runs)
    dump(grade_file, grades)
    dump(rg.costs_path(evaluations), [
        dict(run_id=key, grade_id=grade_id, model=SOL, cost_usd=dict(
             api=value, plan='unknown', tokens=TOKENS))
        for key, grade_id, value in [
            ('b', 'grade-b', 1), ('c', 'grade-c', 5), ('d', 'grade-d', 600),
            ('e', 'grade-e', 700), ('unknown', 'wrong-grade', 1000)]
    ])
    path = tmp_path / 'leaderboard.md'
    mr.public(dict(updated=NOW.isoformat(), roles={'batch': ['gpt-6.2-sol']}), path)
    text = path.read_text()
    assert '| $1 / $2 (3/5) | $0.01 / $0.01 (1/5) |' in text
    assert 'Plan calibration date(s) 2026-11-25' in text
    assert '700' not in text and '1000' not in text
    assert mr.bootstrap(path)['roles']['batch'] == ['gpt-6.2-sol']
    assert mr.snapshot_rows(path)[5]


def test_claude_calibration_brackets_complete_runs(tmp_path):
    day = NOW - dt.timedelta(hours=2)
    reset = (NOW + dt.timedelta(days=3)).isoformat()
    samples, runs = [], []
    for i in range(4):
        at = day + dt.timedelta(minutes=30 * i)
        samples.append(dict(at=at.isoformat(), resets_at=reset, weekly_percent=10 + 2 * i))
        if i < 3:
            runs.append(dict(backend='claude', started_at=(at + dt.timedelta(minutes=5)).isoformat(),
                             closed_at=(at + dt.timedelta(minutes=25)).isoformat(), token_usage=TOKENS))
    dump(tmp_path / 'claude-history.jsonl', samples)
    until = NOW.timestamp()
    reader = rg.run_costs.TokenReader()
    result = calibrate.claude(tmp_path, runs, reader, day.timestamp(), until)
    assert result['tokens_per_weekly_percent'] == 115
    assert result['positive_intervals'] == 3
    del runs[1]['token_usage']
    result = calibrate.claude(tmp_path, runs, reader, day.timestamp(), until)
    assert result['tokens_per_weekly_percent'] is None and result['omitted_weekly_points'] == 2


def test_codex_calibration_prices_only_same_window_deltas(tmp_path):
    path = tmp_path / NOW.strftime('%Y/%m/%d') / 'rollout-fixture.jsonl'
    day = NOW - dt.timedelta(hours=1)
    reset = (NOW + dt.timedelta(days=3)).timestamp()
    rows = [dict(type='session_meta', timestamp=day.isoformat(), payload=dict(creator_account_id='fixture', id='one'))]
    for i in range(5):
        at = day + dt.timedelta(minutes=5 * i)
        total = 100 + 100 * i
        limits = dict(limit_id='codex', plan_type='pro', secondary=dict(window_minutes=10080,
                      resets_at=reset if i < 4 else reset + 604800, used_percent=2 * i if i < 4 else 95))
        rows.append(dict(type='event_msg', timestamp=at.isoformat(), payload=dict(type='token_count',
                         info=dict(total_token_usage=dict(input_tokens=total - 20, output_tokens=20, total_tokens=total)),
                         rate_limits=limits)))
    dump(path, rows)
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    result = calibrate.codex(rg.run_costs.TokenReader(codex_sessions=tmp_path), day.timestamp(), NOW.timestamp())
    assert result['tokens_per_weekly_percent'] == 50
    assert result['weekly_points'] == 6
    assert result['omitted_intervals'] == {'reset, tier change or falling reading': 1}
