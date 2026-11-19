"""11-19 Ricardo: "No pay-as-you-go. Do NOT top up OpenRouter." Every served role is a subscription route."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('model_roles', Path(__file__).with_name('model-roles.py'))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)
METERED = [m for m, (cli, _) in mr.MODELS.items() if cli == 'openrouter']


def test_every_seed_is_a_subscription_route():
    for role, seeds in mr.SEED.items():
        assert seeds, role
        assert all(mr.MODELS[mr.canon(m)][0] in ('claude', 'codex', 'agy') for m in seeds), role


@pytest.mark.parametrize('role', mr.ROLES)
def test_no_role_routes_to_openrouter_even_with_winning_evidence(role, tmp_path, monkeypatch):
    assert METERED  # the history stays readable: DeepSeek, GLM, Kimi, Grok
    monkeypatch.setattr(mr, 'LEDGER', tmp_path / 'absent.jsonl')
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    monkeypatch.setitem(mr.CANDIDATES, role, METERED)
    ev = {role: {m: dict(n=1000, k=1000, days={'2026-11-17', '2026-11-18'}) for m in METERED}}
    monkeypatch.setattr(mr, 'evidence', lambda: ev)
    data = mr.recompute(write=False)
    for name, order in data['roles'].items():
        assert order, name
        assert {data['routes'][m]['cli'] for m in order} <= {'claude', 'codex', 'agy'}, (name, order)
    assert set(mr.MODELS[m][1] for m in METERED) <= set(data['evidence'][role])


def test_the_public_roles_contract_names_no_openrouter_model():
    doc = json.loads((Path(__file__).resolve().parents[1] / 'kb/docs/model-roles.json').read_text())
    for role, models in doc['roles'].items():
        assert models, role
        assert all(m.split('/')[0] in ('anthropic', 'openai', 'google') for m in models), (role, models)
