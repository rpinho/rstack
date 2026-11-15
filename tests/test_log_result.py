"""`new_yes` is the number the yield test turns on, so the ledger asks for evidence.

Before 11-06 any `--new yes --referee HOLDS` was accepted with no check, and `--kind rerun`
counted as new; the friends ledger has one such row. A referee never sees this ledger, so
nothing else was checking.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

RUBRIC = ("CONTROLS: controls in runs/ctrl.json rule it out, 3 of 3 agree. "
          "CONTRADICTING: none dropped; all 12 rows in data/all.csv kept. "
          "LABELS: re-derived from raw/labels.tsv, 12 of 12 match.")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lr', ROOT / 'harness/tools/lane-yield/log_result.py')
lr = importlib.util.module_from_spec(spec); spec.loader.exec_module(lr)

NEW_CLAIM = ('NEW: yes\nPrinted: 1.0 in https://arxiv.org/abs/2601.00001\nOurs: 1.1\n'
             'Cited by: 0 papers since 2026 (OpenAlex W1, checked 2026-11-04); closest: none\n'
             'Kind: value\nStandard method: x\nDeviations: none\n')


def run(tmp_path, *args):
    ledger = tmp_path / 'RESULTS.jsonl'
    rc = lr.main(['--ledger', str(ledger), *args])
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()] \
        if ledger.exists() else []
    return rc, rows


def test_a_rerun_cannot_be_new(tmp_path):
    rc, rows = run(tmp_path, '--new', 'yes', '--kind', 'rerun', '--what', 'reproduced C44',
                   '--link', 'https://github.com/t/p/pull/9', '--referee', 'HOLDS', '--verdict', RUBRIC)
    assert rc == 2 and rows == [], 'refused, and nothing written'


def test_new_yes_needs_evidence(tmp_path):
    rc, rows = run(tmp_path, '--new', 'yes', '--kind', 'value', '--what', 'a bound',
                   '--link', 'mail-abc123', '--referee', 'HOLDS', '--verdict', RUBRIC)
    assert rc == 2 and rows == []


@pytest.mark.parametrize('link', ['https://github.com/t/p/pull/9',
                                  'https://doi.org/10.1234/abcd',
                                  'doi:10.1234/abcd'])
def test_a_pr_or_doi_link_is_evidence(tmp_path, link):
    rc, rows = run(tmp_path, '--new', 'yes', '--kind', 'value', '--what', 'a bound',
                   '--link', link, '--referee', 'HOLDS', '--verdict', RUBRIC)
    assert rc == 0 and rows[-1]['new'] is True and rows[-1]['link'] == link


def test_a_claim_dir_must_pass_result_lint(tmp_path):
    claim = tmp_path / 'claims/alpha_A1'
    claim.mkdir(parents=True)
    (claim / 'CLAIM.md').write_text(NEW_CLAIM)
    rc, rows = run(tmp_path, '--new', 'yes', '--kind', 'value', '--what', 'a bound',
                   '--link', str(claim), '--referee', 'HOLDS', '--verdict', RUBRIC)
    assert rc == 0, 'a clean claim dir is evidence'
    assert rows[-1]['new'] is True


def test_a_claim_dir_that_fails_result_lint_is_refused(tmp_path):
    bad = tmp_path / 'claims/alpha_A2'
    bad.mkdir(parents=True)
    # No "NEW: yes" first line, no Printed/Ours: exactly what result-lint exists to catch.
    (bad / 'CLAIM.md').write_text('We think this is probably better.\n')
    rc, rows = run(tmp_path, '--new', 'yes', '--kind', 'value', '--what', 'a bound',
                   '--link', str(bad), '--referee', 'HOLDS', '--verdict', RUBRIC)
    assert rc == 2 and rows == []


def test_new_no_is_unaffected(tmp_path):
    """Logging a negative result must stay frictionless; that is most of the ledger."""
    rc, rows = run(tmp_path, '--new', 'no', '--kind', 'rerun', '--what', 'did not reproduce',
                   '--link', 'notes.md', '--referee', 'NONE')
    assert rc == 0 and rows[-1]['new'] is False and rows[-1]['kind'] == 'rerun'


def test_an_unimportable_linter_refuses_rather_than_waving_it_through(tmp_path, monkeypatch):
    claim = tmp_path / 'claims/alpha_A3'
    claim.mkdir(parents=True)
    (claim / 'CLAIM.md').write_text(NEW_CLAIM)
    monkeypatch.setitem(os.environ, 'PYTHONPATH', '')
    import builtins
    real = builtins.__import__

    def no_lint(name, *a, **k):
        if name == 'result_lint':
            raise ImportError('gone')
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, '__import__', no_lint)
    assert lr.new_errors('value', str(claim)), 'fails loudly, not silently open'


def test_a_bare_lane_name_means_that_lanes_ledger_and_a_stray_name_is_refused(tmp_path, monkeypatch, capsys):
    """11-15, virtual-embryo: `--ledger virtual-embryo` wrote ./virtual-embryo, printed success and lost
    seven results for a week. A lane name now resolves; anything else that is not a ledger is refused."""
    log_result = lr
    (tmp_path / 'lanes' / 'demo').mkdir(parents=True)
    monkeypatch.setenv('RH_ROOT', str(tmp_path))
    monkeypatch.chdir(tmp_path)
    args = ['--new', 'no', '--kind', 'note', '--what', 'x', '--link', 'https://example.org/x', '--referee', 'NONE']
    assert log_result.main(['--ledger', 'demo'] + args) == 0
    assert (tmp_path / 'lanes' / 'demo' / 'RESULTS.jsonl').read_text().count('\n') == 1
    assert 'logged to ' + str((tmp_path / 'lanes' / 'demo' / 'RESULTS.jsonl').resolve()) in capsys.readouterr().err
    assert log_result.main(['--ledger', 'nosuchlane'] + args) == 2
    assert log_result.main(['--ledger', str(tmp_path / 'notes.txt')] + args) == 2
    assert not (tmp_path / 'nosuchlane').exists()
