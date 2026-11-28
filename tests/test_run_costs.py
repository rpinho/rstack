"""Synthetic executor usage, attribution and dollar arithmetic."""
import datetime as dt
import json
import os
import re
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
import run_costs

START = dt.datetime(2026, 11, 27, 13, tzinfo=dt.timezone.utc)
END = START + dt.timedelta(minutes=5)


def stamp(seconds=0):
    return (START + dt.timedelta(seconds=seconds)).isoformat()


def run(tmp_path, backend, **kwargs):
    return dict(backend=backend, workdir=str(tmp_path), started_at=stamp(), closed_at=END.isoformat(), **kwargs)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_claude_result_cache_and_reasoning(tmp_path):
    path = tmp_path / 'result.json'
    path.write_text(json.dumps(dict(type='result', usage=dict(
        input_tokens=100, cache_read_input_tokens=400, cache_creation_input_tokens=50, output_tokens=40,
        output_tokens_details=dict(thinking_tokens=10)), modelUsage={'claude-opus-5-5': {}},
        total_cost_usd=123456)))
    os.utime(path, (END.timestamp(), END.timestamp()))
    job = run(tmp_path, 'claude', transcript=str(path), model='claude-opus-5-5')
    used = run_costs.tokens_for(job)
    assert used == dict(input=550, cached_input=400, cache_write=50, output=40, reasoning=10,
                        source='claude result', served_models=['claude-opus-5-5'])
    rate = dict(input=5, cached_input=.5, cache_write=10, output=20)
    plan = dict(usd_per_month=100, tokens_per_weekly_percent=1000, calibration_as_of='2026-11-27')
    result = run_costs.cost_for(job, prices={'anthropic/claude-opus-5.5': rate}, plans={'anthropic': plan})
    assert result['api'] == pytest.approx(.002)
    assert result['plan'] == pytest.approx(590 / 1000 / 100 * (100 * 12 / 52))
    assert result['plan_as_of'] == '2026-11-27'
    del rate['cache_write']
    assert run_costs.cost_for(job, prices={'anthropic/claude-opus-5.5': rate})['api'] == 'unknown'


def test_claude_session_counts_assistant_messages_once_and_refuses_reused_result(tmp_path):
    project = tmp_path / 'projects' / re.sub(r'[^a-zA-Z0-9-]', '-', str(tmp_path))
    rows = [
        dict(type='user', cwd=str(tmp_path), timestamp=stamp(2)),
        dict(type='assistant', timestamp=stamp(3), message=dict(id='a', model='claude-sonnet-5-5',
             usage=dict(input_tokens=7, cache_read_input_tokens=30, output_tokens=2))),
        dict(type='assistant', timestamp=stamp(4), message=dict(id='a', model='claude-sonnet-5-5',
             usage=dict(input_tokens=7, cache_read_input_tokens=30, output_tokens=3))),
        dict(type='assistant', timestamp=stamp(5), message=dict(id='b', model='claude-sonnet-5-5',
             usage=dict(input_tokens=13, output_tokens=1))),
    ]
    write_jsonl(project / 'session.jsonl', rows)
    path = tmp_path / 'overwritten.json'
    path.write_text(json.dumps(dict(type='result', usage=dict(input_tokens=100, output_tokens=50))))
    os.utime(path, (END.timestamp() + 60, END.timestamp() + 60))
    reader = run_costs.TokenReader(claude_projects=project.parent)
    job = run(tmp_path, 'claude', transcript=str(path))
    used, reason = reader.measure(job)
    assert reason is None and used['source'] == 'claude session'
    assert (used['input'], used['cached_input'], used['output']) == (50, 30, 4)
    rows[-1]['timestamp'] = stamp(600)
    write_jsonl(project / 'session.jsonl', rows)
    assert reader.measure(job) == (None, 'Claude session usage exceeds the attempt bounds')


def make_rollout(directory, work, name='first', source='exec'):
    path = directory.joinpath(*START.strftime('%Y/%m/%d').split('/'), 'rollout-' + name + '.jsonl')
    rows = [
        dict(type='session_meta', timestamp=stamp(2), payload=dict(cwd=str(work), source=source)),
        dict(type='turn_context', timestamp=stamp(4), payload=dict(model='gpt-6.2-sol')),
    ]
    for sec, i, c, o, r in [(5, 100, 20, 10, 6), (6, 200, 100, 30, 10), (7, 200, 100, 30, 10)]:
        counts = dict(input_tokens=i, cached_input_tokens=c, output_tokens=o, reasoning_output_tokens=r, total_tokens=i + o)
        rows.append(dict(type='event_msg', timestamp=stamp(sec), payload=dict(type='token_count', info=dict(total_token_usage=counts))))
    write_jsonl(path, rows)
    return path


def test_codex_cumulative_usage_and_scalar_counter(tmp_path):
    sessions = tmp_path / 'sessions'
    make_rollout(sessions, tmp_path)
    make_rollout(sessions, tmp_path, 'subagent', source={'subagent': {}})
    make_rollout(sessions, tmp_path / 'another-dir', 'elsewhere')
    reader = run_costs.TokenReader(codex_sessions=sessions)
    job = run(tmp_path, 'codex', tokens=130, model='gpt-6.2-sol')
    counts, reason = reader.measure(job)
    assert reason is None
    assert counts == dict(input=200, cached_input=100, cache_write=0, output=30, reasoning=10,
                          source='codex rollout', served_models=['gpt-6.2-sol'])
    assert run_costs.cost_for(job, reader)['api'] == pytest.approx(.00051)
    assert reader.measure(dict(job, tokens=999)) == (None, 'Codex rollout totals disagree with executor counters')
    make_rollout(sessions, tmp_path, 'both')
    fresh_reader = run_costs.TokenReader(codex_sessions=sessions)
    assert fresh_reader.measure(job) == (None, 'ambiguous Codex rollouts')


@pytest.fixture
def agy_reader(tmp_path):
    # This replacement has the separate decoder's interface. The SQLite rows
    # are entirely synthetic, with JSON standing in for protobuf wire parsing.
    decoder = tmp_path / 'decoder.py'
    decoder.write_text('''
import json
import sqlite3
from dataclasses import dataclass
from types import SimpleNamespace

@dataclass
class Fixture:
    data: bytes | None

def connect(path):
    return sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)

def fields(blob):
    return {int(k): v for k, v in json.loads(blob).items()} if blob else {}

def text(value):
    return value or ""

def timestamp(value):
    return value or None

def workspace_path(value):
    return value

def model_family(value):
    return value.removesuffix("-high").split("/")[-1]

def generation(index, blob):
    raw = fields(blob)
    uncached, cached, output, reasoning = raw[2], raw[5], raw[3], raw[9]
    model, at = raw[19], raw[1]
    return SimpleNamespace(measured=True, request=index, tokens={9:reasoning, 10:output-reasoning},
                           counts=(uncached + cached, output, cached), when=at,
                           model=model, api_model=model, label="", repeated_usage=b"")

def generation_time(gen, steps, requests, created):
    return gen.when, "request+usage", None
''')
    folders = [tmp_path / 'conversations', tmp_path / 'backup']
    for folder in folders:
        folder.mkdir()
    return run_costs.TokenReader(agy_decoder=decoder, agy_dirs=folders), folders


def agy_db(path, work, output=70, model='gemini-4-neon'):
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE trajectory_metadata_blob(id TEXT, data BLOB);
            CREATE TABLE steps(idx INTEGER, step_type INTEGER, metadata BLOB);
            CREATE TABLE gen_metadata(idx INTEGER, data BLOB);''')
        db.execute('INSERT INTO trajectory_metadata_blob VALUES (?, ?)',
                   ('main', json.dumps({7: str(work), 2: START.timestamp() + 3})))
        db.executemany('INSERT INTO gen_metadata VALUES (?, ?)', [
            (1, json.dumps({1: START.timestamp() + 15, 2: 100, 3: output, 5: 40, 9: 20, 19: model})),
            (2, json.dumps({1: START.timestamp() + 16, 2: 40, 3: 10, 5: 20, 9: 0, 19: model})),
        ])


def test_agy_sqlite_matches_time_directory_and_model(agy_reader, tmp_path):
    reader, folders = agy_reader
    agy_db(folders[0] / 'work.db', tmp_path)
    agy_db(folders[0] / 'another.db', tmp_path / 'other')
    job = run(tmp_path, 'agy', model='gemini-4-neon-high', tokens=220)
    counts, reason = reader.measure(job)
    assert reason is None
    assert counts == dict(input=200, cached_input=60, cache_write=0, output=80, reasoning=20,
                          source='agy conversation', served_models=['gemini-4-neon'])
    assert reader.measure(dict(job, tokens=300)) == (None, 'agy generation totals disagree with executor counters')
    assert reader.measure(dict(job, model='gemini-4-carbon-high')) == (None, 'no matching measured agy conversation')


def test_agy_conflicting_snapshot_remains_unpriced(agy_reader, tmp_path):
    reader, folders = agy_reader
    agy_db(folders[0] / 'work.db', tmp_path)
    agy_db(folders[1] / 'work.db', tmp_path, output=25)
    job = run(tmp_path, 'agy', model='gemini-4-neon-high')
    assert reader.measure(job) == (None, 'agy snapshots disagree')


def test_no_token_data_and_invalid_config_fail_open(tmp_path):
    job = run(tmp_path, 'no-provider')
    assert run_costs.tokens_for(job) is None
    assert run_costs.cost_for(job) == dict(api='unknown', plan='unknown',
                                         tokens={'reason': 'unsupported or missing run backend'})
    tokens = dict(input=50, cached_input=10, output=5, cache_write=0, reasoning=1, source='synthetic')
    job = run(tmp_path, 'codex', token_usage=tokens, model='gpt-6.2-sol')
    cost = run_costs.cost_for(job, prices={'openai/gpt-6.2-sol': {'input': True}}, plans={'openai': []})
    assert (cost['api'], cost['plan']) == ('unknown', 'unknown')
    assert run_costs.tokens_for(job) == tokens


def test_shipped_prices_cover_gpt_cache_writes():
    """11-28 (laptop handoff 0130): GPT-6.x cache_write was null, so any Codex run with cache writes priced UNKNOWN."""
    used = dict(input=1_000_000, cached_input=600_000, cache_write=100_000, output=10_000, reasoning=0,
                served_models=['gpt-6.2-astra'])
    reader = type('Reader', (), {'measure': lambda self, job: (used, None)})()
    cost = run_costs.cost_for({'model': 'gpt-6.2-astra', 'backend': 'codex'}, reader=reader)
    # 300k uncached x $8 + 600k cached x $0.40 + 100k written x $10 + 10k out x $40, per 1M
    assert cost['api'] == pytest.approx(2.4 + 0.24 + 1.0 + 0.4)
    shipped = run_costs.config('prices')
    for model in ('openai/gpt-6.2-astra', 'openai/gpt-6.2-sol', 'openai/gpt-6.1-sol', 'openai/gpt-6-astra'):
        assert shipped[model]['cache_write'] == pytest.approx(1.25 * shipped[model]['input'])
