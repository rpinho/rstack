"""Google API scores stay in history; no served role may resolve to the Google API (11-19: agy is allowed)."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('model_roles', Path(__file__).with_name('model-roles.py'))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)


def test_google_routes_and_aliases_remain_for_history():
    for suffix in ('carbon', 'hydrogen', 'argon'):
        model = 'google/gemini-4-' + suffix
        assert mr.MODELS[model] == ('gemini', model)
        assert mr.canon(model) == model
    assert mr.canon('hydrogen') == 'google/gemini-4-hydrogen'


@pytest.mark.parametrize('role', mr.ROLES)
def test_no_served_role_resolves_to_google_even_with_winning_evidence(role, tmp_path, monkeypatch):
    # Exercise seeds, candidates, observed models, and an exclusion that would be lifted.
    google = [m for m in mr.MODELS if m.startswith('google/') and mr.MODELS[m][0] != 'agy']
    google.append(mr.canon('google/gemini-future'))
    monkeypatch.setattr(mr, 'LEDGER', tmp_path / 'absent.jsonl')
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    monkeypatch.setitem(mr.SEED, role, google + mr.SEED[role])
    monkeypatch.setitem(mr.CANDIDATES, role, google)
    monkeypatch.setitem(mr.OVERRIDES, role, dict(exclude=google, date='2026-11-18'))
    ev = {role: {m: dict(n=1000, k=1000, days={'2026-11-17', '2026-11-18'}) for m in google}}
    monkeypatch.setattr(mr, 'evidence', lambda: ev)
    data = mr.recompute(write=False)
    for order in data['roles'].values():
        assert order
        assert all(data['routes'][m]['canonical'] not in google for m in order)
    assert set(google).issubset(data['evidence'][role])
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    assert '| ' + role + ' | google/gemini-4-carbon | - | 1.0 |' in page.read_text()
    restored = mr.bootstrap(page)
    assert all(restored['routes'][m]['canonical'] not in google
               for order in restored['roles'].values() for m in order)


def test_bootstrap_old_google_routing_rows_are_history_only(tmp_path):
    page = tmp_path / 'old.md'
    historical = ('| review | google/gemini-4-carbon | 1 | 1.0 | 0.99 | 2026-11-17 |\n'
                  '| review | gpt-6.2-sol | 2 | - | - | 2026-11-17 |\n')
    page.write_text(historical)
    data = mr.bootstrap(page)
    assert data['roles']['review'] == ['gpt-6.2-sol']
    data['updated'] = '2026-11-18T00:00:00Z'
    mr.public(data, page)
    assert all(line in page.read_text() for line in historical.splitlines())


def test_exact_62_versions_have_distinct_native_routes():
    for native in ('gpt-6.2-sol', 'gpt-6.2-astra', 'gpt-6.1-sol', 'gpt-6-astra'):
        canonical = 'openai/' + native
        assert mr.canon(native) == canonical
        assert mr.MODELS[canonical] == ('codex', native)


def test_snapshot_ignores_six_column_calibration_table(tmp_path):
    page = tmp_path / 'mixed.md'
    page.write_text('| Entry | Completed /9 | Review /2 | Judge /3 | Ideation /3 | Plants /24 |\n'
                    '| openai/gpt-6.2-astra | 6 | 2 | 3 | 0 | 24 |\n'
                    '| review | gpt-6.2-sol | 1 | - | - | 2026-11-18 |\n'
                    '| review | gpt-6.2-sol | 0, 4 | 2026-11-18 |\n')
    rows = mr.snapshot_rows(page)
    assert len(rows[6]) == len(rows[4]) == 1
    assert mr.bootstrap(page)['roles'] == {'review': ['gpt-6.2-sol']}


def test_superseded_versions_are_history_and_never_routed():
    # 11-19 (general): GPT-6 Astra and 6.1 Sol were retired as routes on 11-18; their records stay visible only.
    old = {"openai/gpt-6-astra", "openai/gpt-6.1-sol"}
    for role in mr.ROLES:
        assert not old & set(mr.rank(role, {})[0])
    assert mr.rank("batch", {})[0][0] == "openai/gpt-6.2-sol"
    ev = {"batch": {"openai/gpt-6.1-sol": {"k": 170, "n": 171, "days": {str(i) for i in range(9)}}}}
    assert "openai/gpt-6.1-sol" not in mr.rank("batch", ev)[0]

def test_agy_carbon_tiers_have_subscription_routes_and_low_is_below_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, 'LEDGER', tmp_path / 'absent.jsonl')
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    monkeypatch.setattr(mr, 'evidence', lambda: {})
    data = mr.recompute(write=False)
    for tier in ('low', 'medium', 'high'):
        native = 'gemini-4-carbon-' + tier
        canonical = 'google/' + native
        assert mr.canon(native) == canonical and data['routes'][native] == {'cli': 'agy', 'canonical': canonical}
    assert 'google/gemini-4-carbon-low' in mr.GEMINI_BELOW_FLOOR
