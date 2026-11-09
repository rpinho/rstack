"""Offline coverage for the dated X search journal and CLI."""
import contextlib
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import idea_policy
import rh
import sweep
import x_searches
from policy_fixtures import prior_art


@pytest.fixture
def lane(tmp_path, monkeypatch):
    lane = tmp_path / 'lanes/test'
    lane.mkdir(parents=True)
    (lane / 'INTAKE.toml').write_text('keywords = []\nx_local_file = "X_HITS.jsonl"\n')
    monkeypatch.setenv('RH_CAPTURED_BY', 'general:test-session')
    def forbidden(*args, **kwargs):
        raise AssertionError('network, workers and notifications forbidden')
    monkeypatch.setattr(rh, 'get_url', forbidden)
    monkeypatch.setattr(sweep, 'run_worker', forbidden)
    monkeypatch.setattr(sweep, 'notify', forbidden)
    return lane


def cli(lane, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = rh.main(['--root', str(lane.parents[1]), 'intake'] + list(args))
    return rc, out.getvalue(), err.getvalue()


def outcome(**changes):
    row = dict(utc=rh.now(), query='"fixture method" code', result='none', n_hits=0,
               captured_by='general:test-session')
    row.update(changes)
    return row


def prompt(lane, configured=True, stage='search', failures=()):
    cfg = dict(cwd=lane, cores=1, memory_gib=1, min_free_gib=1, kill_test_max_minutes=1,
               search_targets=['fixture'], sources=['fixture'], banned_sources=['sealed'],
               allowed_tests=['arithmetic'], allowed_writes=['work/'], rules=[],
               evidence_policy=True, x_capture_path=lane / 'X_HITS.jsonl' if configured else None)
    paths = {s: lane / 'work' / (s + '.md') for s in ('search', 'read', 'kill')}
    return sweep.generate(stage, lane, cfg, paths, '2026-11-03', [], failures)


def test_cli_records_negative_and_hits_without_url_or_queue_mutations(lane):
    for result, count in (('none', 0), ('hits', 3)):
        rc, out, err = cli(lane, 'x-search', 'test', '--query', '"fixture method" code',
                           '--subject', 'fixture author', '--result', result, '--n', str(count))
        assert rc == 0, out + err
    rows = rh.rows(lane / 'X_SEARCHES.jsonl')
    assert [(r['result'], r['n_hits']) for r in rows] == [('none', 0), ('hits', 3)]
    assert all(r['subject'] == 'fixture author' and r['captured_by'] == 'general:test-session' for r in rows)
    assert all(x_searches.validate(r).utcoffset() == dt.timedelta(0) for r in rows)
    assert not (lane / 'IDEAS.jsonl').exists()
    assert not (lane / 'INTAKE_RUNS.jsonl').exists()
    assert not (lane / 'X_HITS.jsonl').exists()


def test_the_capturing_session_can_name_itself(lane):
    """planets, 11-08: it ran the search itself and the row named someone else."""
    rc, out, err = cli(lane, 'x-search', 'test', '--query', 'fixture', '--result', 'none', '--n', '0',
                       '--captured-by', 'planets')
    assert rc == 0, out + err
    assert rh.rows(lane / 'X_SEARCHES.jsonl')[-1]['captured_by'] == 'planets'


def test_cli_subject_is_optional(lane):
    rc, out, err = cli(lane, 'x-search', 'test', '--query', 'fixture', '--result', 'none', '--n', '0')
    assert rc == 0, out + err
    assert 'subject' not in rh.rows(lane / 'X_SEARCHES.jsonl')[0]


@pytest.mark.parametrize('changes', [
    {'utc': 'not a date'}, {'utc': '2026-01-01T00:00:00'}, {'utc': '2999-01-01T00:00:00Z'},
    {'utc': 12}, {'utc': None}, {'query': ''}, {'query': '  '}, {'query': ['fixture']},
    {'query': 'injected\nline'}, {'captured_by': ''}, {'captured_by': None},
    {'subject': ''}, {'subject': 12}, {'subject': 'a\0b'},
    {'result': 'skipped'}, {'result': ['none']}, {'result': 'hits', 'n_hits': 0},
    {'result': 'none', 'n_hits': 1}, {'n_hits': -1}, {'n_hits': 0.0}, {'n_hits': True},
    {'n_hits': '0'}, {'extra': 'unrecognized'},
])
def test_malformed_rows_are_rejected(lane, changes):
    row = outcome(**changes)
    with pytest.raises(ValueError, match='X search'):
        x_searches.validate(row)
    (lane / 'X_SEARCHES.jsonl').write_text(json.dumps(row) + '\n')
    with pytest.raises(ValueError, match=r'X_SEARCHES.jsonl:1:'):
        prompt(lane)


@pytest.mark.parametrize('key', ['utc', 'query', 'result', 'n_hits', 'captured_by'])
def test_required_fields_cannot_be_omitted(key):
    row = outcome()
    del row[key]
    with pytest.raises(ValueError, match='requires'):
        x_searches.validate(row)


@pytest.mark.parametrize('raw', ['not-json\n', '[]\n', 'null\n', '"string"\n'])
def test_bad_journal_json_is_rejected(lane, raw):
    (lane / 'X_SEARCHES.jsonl').write_text(raw)
    with pytest.raises(ValueError, match=r'X_SEARCHES.jsonl:1:'):
        prompt(lane)


@pytest.mark.parametrize('args', [
    ['--query', '', '--result', 'none', '--n', '0'],
    ['--query', 'fixture', '--result', 'none', '--n', '1'],
    ['--query', 'fixture', '--result', 'hits', '--n', '0'],
    ['--query', 'fixture', '--result', 'hits', '--n', '-1'],
    ['--query', 'fixture', '--result', 'none'],
    ['--query', 'fixture', '--subject', '', '--result', 'none', '--n', '0'],
    ['--query', 'fixture', '--result', 'none', '--n', '0', '--live'],
    ['--query', 'fixture', '--result', 'none', '--n', '0', '--dry-run'],
])
def test_cli_rejects_bad_outcomes_before_writing(lane, args):
    rc, out, err = cli(lane, 'x-search', 'test', *args)
    assert rc == 2, out + err
    assert not (lane / 'X_SEARCHES.jsonl').exists()
    assert not (lane / 'IDEAS.jsonl').exists()


def test_writer_refuses_existing_malformed_journal(lane):
    path = lane / 'X_SEARCHES.jsonl'
    path.write_text('{"result":"none"}\n')
    before = path.read_bytes()
    rc, _, err = cli(lane, 'x-search', 'test', '--query', 'fixture', '--result', 'none', '--n', '0')
    assert rc == 2 and 'X_SEARCHES.jsonl:1:' in err
    assert path.read_bytes() == before


def test_prompt_includes_recent_outcomes_on_first_and_repair_pass(lane):
    now = dt.datetime.now(dt.timezone.utc)
    rows = [outcome(utc=(now - dt.timedelta(days=days)).isoformat(), query=query, **extra)
            for days, query, extra in (
                (0, 'current negative', {'subject': 'fixture author'}),
                (13, 'recent hits', {'result': 'hits', 'n_hits': 2}),
                (15, 'expired query', {}))]
    journal = lane / 'X_SEARCHES.jsonl'
    journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    before = journal.read_bytes()
    for failures in ((), ('repair fixture',)):
        text = prompt(lane, failures=failures)
        for row in rows[:2]:
            assert json.dumps(row) in text
        assert 'expired query' not in text
        assert 'X searched on <utc date>, none on topic' in text
        assert 'applicable negative receipts establish coverage' in text
        assert 'capture_path/capture_sha256' in text
        assert 'missing, stale or unrelated' in text
    assert journal.read_bytes() == before
    assert 'current negative' not in prompt(lane, stage='read')
    assert 'current negative' not in prompt(lane, stage='kill')


def test_fourteen_day_boundary_is_inclusive(lane):
    now = dt.datetime(2026, 11, 3, 17, tzinfo=dt.timezone.utc)
    boundary = now - dt.timedelta(days=14)
    rows = [outcome(utc=when.isoformat(), query=query) for when, query in (
        (boundary, 'boundary'), (boundary - dt.timedelta(microseconds=1), 'too old'), (now, 'now'))]
    path = lane / 'X_SEARCHES.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert [r['query'] for r in x_searches.recent(path, clock=now)] == ['boundary', 'now']


def test_unconfigured_lane_ignores_journal_and_existing_intake_is_unchanged(lane):
    (lane / 'X_SEARCHES.jsonl').write_text('malformed but irrelevant to this lane\n')
    text = prompt(lane, configured=False)
    assert 'X_SEARCHES.jsonl' not in text
    (lane / 'INTAKE.toml').write_text('keywords = []\n')
    rc, _, _ = cli(lane, 'x-search', 'test', '--query', 'fixture', '--result', 'none', '--n', '0')
    assert rc == 2
    rc, out, err = cli(lane, 'test', '--dry-run')
    assert rc == 0, out + err
    assert 'DRY RUN' in out


def test_recorded_negative_can_back_existing_prior_art_contract(lane):
    rc, out, err = cli(lane, 'x-search', 'test', '--query', 'fixture method', '--result', 'none', '--n', '0')
    assert rc == 0, out + err
    row = rh.rows(lane / 'X_SEARCHES.jsonl')[0]
    work = lane / 'work'
    work.mkdir()
    stable = work / 'X_SEARCHES.capture.jsonl'
    stable.write_bytes((lane / 'X_SEARCHES.jsonl').read_bytes())
    receipt = prior_art(work / 'prior-art-B-1.json')
    data = json.loads(receipt.read_text())
    data['sources']['x'] = dict(status='none', hits=[], query=row['query'], searched_at=row['utc'],
                                note='X searched on {}, none on topic'.format(row['utc'][:10]),
                                capture_path=str(stable), capture_sha256=hashlib.sha256(stable.read_bytes()).hexdigest())
    receipt.write_text(json.dumps(data))
    assert idea_policy.prior_art(receipt)['baseline']
    paths = {s: work / (s + '.md') for s in ('search', 'read', 'kill')}
    paths['search'].write_text('IDEA B-1: https://example.org method; metric; kill; risk\nDONE\n')
    paths['read'].write_text('DONE\n')
    paths['kill'].write_text('RESULT B-1: KILLED value=0; pass > 1\nDONE\n')
    assert sweep.check(paths, [], cfg={'evidence_policy': True}) == []
    stable.write_text('tampered\n')
    assert any('capture hash mismatch' in e for e in sweep.check(paths, [], cfg={'evidence_policy': True}))
