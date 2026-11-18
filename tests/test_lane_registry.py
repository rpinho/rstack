"""One lifecycle decision for lane names, session aliases and inclusive end dates."""
from datetime import date
import json

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
