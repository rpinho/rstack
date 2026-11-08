"""coverage.py fails the day something new appears that nothing maps (rstack/STACK.md).

A map that silently falls behind what is on disk stops being a map. The example configuration
ships with one deliberate failure, an example guard no rule claims; these tests copy the example,
add a new item, and check that the failure names it and goes away once a rule maps it.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def example(tmp_path):
    shutil.copytree(ROOT / 'rstack/example', tmp_path / 'rstack/example')
    shutil.copy(ROOT / 'rstack/layers.example.json', tmp_path / 'rstack/layers.example.json')
    return tmp_path


def coverage(where, *args):
    return subprocess.run([sys.executable, str(ROOT / 'rstack/coverage.py'), '--config',
                           'rstack/layers.example.json', *args], cwd=where, capture_output=True, text=True)


def test_the_example_fails_on_exactly_its_one_unmapped_guard(tmp_path):
    run = coverage(example(tmp_path))
    assert run.returncode == 1 and 'FAIL (1)' in run.stdout and 'unmapped hook: stale-guard' in run.stdout


def test_a_new_item_nothing_maps_fails_the_day_it_appears(tmp_path):
    where = example(tmp_path)
    (where / 'rstack/example/hooks/brand-new-guard.py').write_text('"""A guard added today."""\n')
    run = coverage(where)
    assert 'unmapped hook: brand-new-guard' in run.stdout and 'FAIL (2)' in run.stdout
    assert 'brand-new-guard' in coverage(where, '--unmapped').stdout


def test_mapping_it_clears_that_failure(tmp_path):
    where = example(tmp_path)
    (where / 'rstack/example/hooks/brand-new-guard.py').write_text('"""A guard added today."""\n')
    cfg = where / 'rstack/layers.example.json'
    data = json.loads(cfg.read_text())
    data['rules'].append(dict(type='hook', match='brand-new-guard', layer='02-guards',
                              enforcer='rstack/example/hooks/brand-new-guard.py'))
    cfg.write_text(json.dumps(data))
    run = coverage(where)
    assert 'brand-new-guard' not in run.stdout and 'FAIL (1)' in run.stdout
