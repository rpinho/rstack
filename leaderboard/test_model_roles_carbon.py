"""Gemini challengers use the ordinary candidate ranking and evidence threshold."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('model_roles', Path(__file__).with_name('model-roles.py'))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)


def test_carbon_has_a_gemini_route_and_its_own_alias():
    for suffix in ('carbon', 'hydrogen', 'argon'):
        model = 'google/gemini-4-' + suffix
        assert mr.MODELS[model] == ('gemini', model)
    assert mr.canon('google/gemini-4-carbon') == 'google/gemini-4-carbon'
    assert mr.canon('google/gemini-4-argon') == 'google/gemini-4-argon'   # the two never collide


def test_carbon_is_a_candidate_not_a_seed():
    assert all('google/gemini-4-carbon' not in seeds for seeds in mr.SEED.values())


def test_geminis_enter_six_pools_after_seeds_without_scores(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, 'LEDGER', tmp_path / 'absent.jsonl')
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    data = mr.recompute(write=False)
    for role in ('review', 'judge', 'ideation', 'design', 'mechanical', 'batch'):
        expected = [mr.MODELS[m][1] for m in mr.SEED[role]]
        assert data['roles'][role] == expected + mr.CANDIDATES[role]
        for model in mr.CANDIDATES[role]:
            assert data['routes'][model] == dict(cli='gemini', canonical=model)
            assert model not in data['evidence'][role]
            # One day never qualifies, even with perfect outcomes.
            ev = {role: {model: dict(n=20, k=20, days={'2026-01-01'})}}
            assert mr.rank(role, ev)[0][0] == mr.SEED[role][0]
            ev[role][model]['days'].add('2026-01-02')
            assert mr.rank(role, ev)[0][0] == model
    assert mr.canon('hydrogen') == 'google/gemini-4-hydrogen'
