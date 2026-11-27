"""One lifecycle decision for lane names, session aliases and inclusive end dates."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from harness import lane_registry as lr


def test_load_default_override_and_fresh_reads(tmp_path, monkeypatch):
    monkeypatch.setenv('RH_ROOT', str(tmp_path))
    assert lr.status('unknown', date(2026, 1, 2)) == 'active'
    lanes = tmp_path / 'lanes'
    lanes.mkdir()
    path = lanes / 'REGISTRY.json'
    data = {'lanes': {'closed': {'status': 'retired', 'since': '2026-01-01',
                                'sessions': ['closedb'], 'why': 'owner ended the work'}}}
    path.write_text(json.dumps(data))
    assert lr.load(lanes).status('closedb') == 'retired'
    assert lr.lane_of_session('claude-closedb') == 'closed'
    override = tmp_path / 'other.json'
    override.write_text('{"lanes": {}}')
    monkeypatch.setenv('RH_LANE_REGISTRY', str(override))
    assert lr.status('closed') == 'active'
    override.write_text(json.dumps(data))
    assert lr.status('closedb') == 'retired'
    monkeypatch.setenv('RH_LANE_REGISTRY', str(tmp_path / 'missing'))
    with pytest.raises(FileNotFoundError):
        lr.load()


def test_status_dates_precedence_and_job_prefixes():
    registry = lr.LaneRegistry({'lanes': {
        'closed': {'status': 'retired', 'end': '2026-01-01', 'sessions': ['closedb']},
        'long-lane': {'status': 'active', 'end': '2026-01-01'},
        'long': {'status': 'active'},
        'paused': {'status': 'held', 'end': '2026-01-01'},
    }})
    assert registry.status('closed', '2026-01-02') == 'ended'
    assert registry.status('closed', '2026-01-01') == 'retired'
    for lane in ('long-lane', 'paused'):
        assert registry.status(lane, '2026-01-02') == 'ended'
    assert registry.status('long-lane', '2026-01-01') == 'active'
    assert registry.status('paused', '2026-01-01') == 'held'
    assert registry.status('long-lane', '2025-12-31') == 'active'
    assert registry.lane_of_session('codex-closedb') == 'closed'
    assert registry.lane_of_session('unknown') == 'unknown'
    assert registry.lane_of_job('long-lane_round1') == 'long-lane'
    assert registry.lane_of_job('closedb-recheck') == 'closed'
    assert registry.lane_of_job('closedbook-job') == 'closedbook'
    assert registry.lane_of_job('unknown_job') == 'unknown'
    assert registry.retired_reason('closedb').startswith('closed: ended')


def test_renamed_lane_alias_resolves_sessions_jobs_and_retired_reason():
    registry = lr.LaneRegistry({'lanes': {
        'open-source': {'status': 'retired', 'aliases': ['bio'], 'sessions': ['bio-nightly'],
                        'why': 'fixture retirement'},
    }})
    for name in ('bio', 'open-source', 'codex-bio', 'claude-bio', 'bio-nightly'):
        assert registry.lane_of_session(name) == 'open-source'
        assert registry.status(name) == 'retired'
        assert registry.retired_reason(name) == 'open-source: retired: fixture retirement'
    assert registry.lane_of_job('bio_round1') == 'open-source'
    assert registry.lane_of_job('open-source_round1') == 'open-source'


def test_declared_job_prefixes_resolve_jobs_and_conflicts_are_errors():
    registry = lr.LaneRegistry({'lanes': {
        'digest': {'status': 'active', 'job_prefixes': ['nightly']},
        'open-source': {'status': 'active', 'aliases': ['bio'], 'job_prefixes': ['hunt', 'ref', 'bio']},
    }})
    assert registry.lane_of_job('nightly-20261118') == 'digest'
    assert registry.lane_of_job('hunt_scrna') == registry.lane_of_job('ref_1118') == 'open-source'
    assert registry.registered_lane_of_job('refurbish_1') is None
    assert registry.lane_of_job('refurbish_1') == 'refurbish'
    assert registry.lane_of_session('nightly') == 'nightly'
    for bad in ({'a': {'status': 'active', 'job_prefixes': ['x']}, 'b': {'status': 'active', 'job_prefixes': ['x']}},
                {'a': {'status': 'active', 'job_prefixes': ['b']}, 'b': {'status': 'active'}},
                {'a': {'status': 'active', 'job_prefixes': 'x'}}):
        with pytest.raises(ValueError):
            lr.LaneRegistry({'lanes': bad})


def test_open_source_job_fallback_retains_the_lane_hyphen():
    registry = lr.LaneRegistry({'lanes': {}})
    assert registry.lane_of_job('open-source_fix') == 'open-source'
    assert registry.lane_of_job('open-source-fix') == 'open-source'
    assert registry.lane_of_job('open-source') == 'open-source'
    assert registry.lane_of_job('open-sourcebook_fix') == 'open'


@pytest.mark.parametrize('data', [
    [], {}, {'lanes': []}, {'lanes': {'x': {'status': 'ended'}}},
    {'lanes': {'x': {'status': 'active', 'end': '2026-02-30'}}},
    {'lanes': {'x': {'status': 'active', 'end': '20260101'}}},
    {'lanes': {'x': {'status': 'active', 'sessions': 'xb'}}},
    {'lanes': {'x': {'status': 'active', 'sessions': ['y']}, 'y': {'status': 'active'}}},
    {'lanes': {'x': {'status': 'active', 'aliases': 'old'}}},
    {'lanes': {'x': {'status': 'active', 'aliases': ['']}}},
    {'lanes': {'x': {'status': 'active', 'aliases': [1]}}},
    {'lanes': {'x': {'status': 'active', 'aliases': ['y']}, 'y': {'status': 'active'}}},
    {'lanes': {'x': {'status': 'active', 'aliases': ['old']},
               'y': {'status': 'active', 'sessions': ['old']}}},
])
def test_invalid_registry_never_becomes_an_active_lane(tmp_path, monkeypatch, data):
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps(data))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(path))
    with pytest.raises(ValueError):
        lr.load()


@pytest.mark.parametrize('deadline', [
    {'kind': 'other'},
    {'what': ''},
    {'ends': '2026-11-30T17:00'},
    {'ends': '2026-11-30T17:00+01:00'},
    {'starts': '2026-12-01T17:00Z'},
])
def test_malformed_deadline_names_the_lane(deadline):
    entry = dict(kind='event', what='Fixture', ends='2026-11-30T17:00Z') | deadline
    with pytest.raises(ValueError, match='deadline.*fixture-lane'):
        lr.LaneRegistry({'lanes': {'fixture-lane': {'status': 'active', 'deadlines': [entry]}}})


def test_live_deadline_window_and_soonest_end(monkeypatch):
    monkeypatch.delenv('RH_DEADLINE_LEAD_HOURS', raising=False)
    event = dict(kind='event', what='Fixture event', starts='2026-11-29T17:00Z', ends='2026-11-29T19:00Z')
    bounty = dict(kind='bounty', what='Open bounty', ends='2026-11-30T17:00Z')
    registry = lr.LaneRegistry({'lanes': {
        'math': {'status': 'active', 'aliases': ['theory'], 'deadlines': [bounty, event]},
    }})

    def check(when):
        return registry.live_deadline('theory', datetime.fromisoformat(when + '+00:00'))

    assert check('2026-11-27T16:59:59') == bounty
    assert check('2026-11-27T17:00:00') == event
    assert check('2026-11-29T19:00:00') == bounty
    assert check('2026-11-30T17:00:00') is None
    monkeypatch.setenv('RH_DEADLINE_LEAD_HOURS', '1')
    assert check('2026-11-29T15:59:59') == bounty
    assert check('2026-11-29T16:00:00') == event


@pytest.mark.parametrize('status', ['retired', 'held'])
def test_inactive_lane_has_no_live_deadline(status):
    entry = dict(kind='event', what='Fixture', ends='2026-11-30T17:00Z')
    registry = lr.LaneRegistry({'lanes': {'math': {'status': status, 'deadlines': [entry]}}})
    assert registry.live_deadline('math', datetime(2026, 11, 27, tzinfo=timezone.utc)) is None


def test_ticker_lists_live_and_upcoming_in_end_order(tmp_path, monkeypatch):
    def when(days):
        return datetime.fromtimestamp(now + days * 86400, timezone.utc).isoformat()

    now = datetime.now(timezone.utc).timestamp()
    upcoming = dict(kind='leaderboard', what='Upcoming fixture', starts=when(4), ends=when(5))
    early = dict(kind='bounty', what='Early fixture', ends=when(1))
    late = dict(kind='competition', what='Later fixture', starts=when(1), ends=when(6))
    (tmp_path / 'REGISTRY.json').write_text(json.dumps({'lanes': {
        'first': {'status': 'active', 'deadlines': [late, early]},
        'second': {'status': 'active', 'deadlines': [upcoming, dict(early, ends=when(-1))]},
        'retired': {'status': 'retired', 'deadlines': [early]},
    }}))
    monkeypatch.delenv('RH_LANE_REGISTRY', raising=False)
    monkeypatch.setenv('RH_DEADLINE_LEAD_HOURS', '48')
    cmd = [sys.executable, str(Path(lr.__file__)), 'ticker', '--lanes-root', str(tmp_path)]
    lines = subprocess.check_output(cmd, text=True).splitlines()
    assert len(lines) == 3
    for line, fields in zip(lines, [
        ('first', 'bounty', 'Early fixture', 'left'),
        ('second', 'leaderboard', 'Upcoming fixture', 'starts in'),
        ('first', 'competition', 'Later fixture', 'left'),
    ]):
        assert all(field in line for field in fields)
    rows = json.loads(subprocess.check_output(cmd + ['--json'], text=True))
    assert [(r['lane'], r['what'], r['status']) for r in rows] == [
        ('first', 'Early fixture', 'live'),
        ('second', 'Upcoming fixture', 'upcoming'),
        ('first', 'Later fixture', 'live'),
    ]
