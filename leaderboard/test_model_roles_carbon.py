"""Gemini 4 Carbon (11-10): routable on OpenRouter as a candidate, ranked in no role until our own
plant-check and yield numbers put it there. Vendor benchmarks count for nothing."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('model_roles', Path(__file__).with_name('model-roles.py'))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)


def test_carbon_has_an_openrouter_route_and_its_own_alias():
    assert mr.MODELS['google/gemini-4-carbon'] == ('openrouter', 'google/gemini-4-carbon')
    assert mr.canon('google/gemini-4-carbon') == 'google/gemini-4-carbon'
    assert mr.canon('google/gemini-4-argon') == 'google/gemini-4-argon'   # the two never collide


def test_carbon_is_a_candidate_not_a_seed():
    assert all('google/gemini-4-carbon' not in seeds for seeds in mr.SEED.values())
