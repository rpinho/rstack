import json, subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'sbs'))
sys.path.insert(0, str(ROOT / 'harness' / 'tools'))  # result_lint and sbs both live here
from sbs import sbs  # noqa: E402
from result_lint import lint  # noqa: E402

GOOD = """NEW: yes
Printed: C = 1.2345, Table 2 of https://arxiv.org/abs/2601.00001 (their paper)
Ours: C = 1.2350
Standard method: the paper's own LP, same constraints
Deviations: none
Cited by: 7 papers since 2026 (OpenAlex W1, checked 2026-11-04); closest: none on this table
Kind: value
"""


def test_sbs_higher_and_lower_is_better():
    assert sbs(0.5, 0.84, 0.8556) == pytest.approx(0.95613, abs=1e-5)
    assert sbs(10.0, 4.0, 2.0, higher_is_better=False) == pytest.approx(0.75)
    assert sbs(0.5, 0.9, 0.8) > 1  # baseline beats the method


def test_sbs_undefined_when_method_not_better_than_trivial():
    with pytest.raises(ValueError):
        sbs(0.5, 0.6, 0.5)


def test_good_claim_passes(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD)
    assert lint(tmp_path) == []


def test_missing_new_line_fails(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD.split('\n', 1)[1])
    assert any('NEW: yes' in e for e in lint(tmp_path))


def test_new_yes_needs_a_printed_source(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('https://arxiv.org/abs/2601.00001', 'their paper'))
    assert any('Printed' in e for e in lint(tmp_path))


def test_new_no_is_well_formed_but_skipped_with_new_only(tmp_path):
    (tmp_path / 'CLAIM.md').write_text('NEW: no\nStandard method: x\nDeviations: none\n')
    assert lint(tmp_path) == []
    assert lint(tmp_path, new_only=True)


def test_deviation_must_say_where_standard_failed(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('Deviations: none', 'Deviations: skipped the symmetry step'))
    assert any('standard failed' in e for e in lint(tmp_path))
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('Deviations: none', 'Deviations: custom solver; standard failed: LP timed out at n=40 (STATUS.md)'))
    assert lint(tmp_path) == []


def test_predictive_claim_needs_matching_baselines(tmp_path):
    text = GOOD + 'AUROC 0.8556 vs printed 0.84. SBS 0.956.\n'
    (tmp_path / 'CLAIM.md').write_text(text)
    assert any('BASELINES.json' in e for e in lint(tmp_path))
    (tmp_path / 'BASELINES.json').write_text(json.dumps({'trivial': 0.5, 'simple': 0.84, 'method': 0.8556, 'sbs': 0.5}))
    assert any('does not match' in e for e in lint(tmp_path))
    (tmp_path / 'BASELINES.json').write_text(json.dumps({'trivial': 0.5, 'simple': 0.84, 'method': 0.8556, 'sbs': 0.95613}))
    assert lint(tmp_path) == []


def test_cli_exit_codes(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD)
    cli = [sys.executable, str(ROOT / 'harness' / 'tools' / 'result_lint.py'), str(tmp_path)]
    assert subprocess.run(cli, capture_output=True).returncode == 0
    (tmp_path / 'CLAIM.md').write_text('no header\n')
    assert subprocess.run(cli, capture_output=True).returncode == 1


def test_new_yes_needs_forward_citation_check(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('Cited by: 7 papers since 2026 (OpenAlex W1, checked 2026-11-04); closest: none on this table\n', ''))
    assert any('Cited by' in e for e in lint(tmp_path))
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('closest: none on this table', 'closest: <title, or none>'))
    assert any('Cited by' in e for e in lint(tmp_path))


def test_new_yes_needs_a_kind_from_the_scale(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('Kind: value', 'Kind: earth-shattering'))
    assert any('Kind' in e for e in lint(tmp_path))
    (tmp_path / 'CLAIM.md').write_text(GOOD.replace('Kind: value', 'Kind: conjecture (Conjecture 3.7)'))
    assert lint(tmp_path) == []


def test_new_no_needs_no_citation_check(tmp_path):
    (tmp_path / 'CLAIM.md').write_text('NEW: no\nStandard method: rerun\nDeviations: none\n')
    assert lint(tmp_path) == []


NOTE = """NEW: yes
Kind: note
Builds on: Irimia and Roy 2008, https://doi.org/10.1371/journal.pgen.1000148
Ours: a new estimate on 40 more genomes
Prior art: closest is X 2015, which used 12 genomes
Standard method: the paper's own parsimony count
Deviations: none
Cited by: 85 papers since 2008 (OpenAlex W1, checked 2026-11-04); closest: X 2015
"""


def test_note_needs_builds_on_note_file_and_prior_art(tmp_path):
    (tmp_path / 'CLAIM.md').write_text(NOTE)
    assert any('NOTE.md' in e for e in lint(tmp_path))
    (tmp_path / 'NOTE.md').write_text('# A note\n')
    assert lint(tmp_path) == []
    (tmp_path / 'CLAIM.md').write_text(NOTE.replace('Prior art: closest is X 2015, which used 12 genomes\n', ''))
    assert any('Prior art' in e for e in lint(tmp_path))


def test_baselines_per_metric_with_saved_stdout(tmp_path):
    # 11-05: a note with one sbs.py record per metric (command + stdout saved) failed with KeyError 'trivial'
    (tmp_path / 'CLAIM.md').write_text(GOOD + 'MAE 0.1087 vs simple 0.1392. SBS 0.782.\n')
    good = {'metric': 'MAE', 'higher_is_better': False, 'trivial': 0.2487, 'simple': 0.1392,
            'method': 0.1087, 'sbs': sbs(0.2487, 0.1392, 0.1087, False)}
    (tmp_path / 'BASELINES.json').write_text(json.dumps({'SSI': {'command': ['sbs.py'], 'stdout': json.dumps(good)},
                                                         'MiBa': dict(good)}))
    assert lint(tmp_path) == []
    bad = dict(good, sbs=0.1)
    (tmp_path / 'BASELINES.json').write_text(json.dumps({'SSI': {'stdout': json.dumps(bad)}}))
    assert any('does not match' in e for e in lint(tmp_path))
    (tmp_path / 'BASELINES.json').write_text(json.dumps({'SSI': {'command': ['x']}}))
    assert any('unreadable or incomplete' in e for e in lint(tmp_path))


def _row(metric, trivial, simple, method, higher=True, **extra):
    return dict(metric=metric, higher_is_better=higher, trivial=trivial, simple=simple, method=method,
                sbs=sbs(trivial, simple, method, higher), **extra)


def test_each_reported_metric_needs_its_own_baseline_row(tmp_path):
    # 11-19, Arc VCC 2026: most entries beat the context mean on PDS but lost to it on MSE and Jaccard.
    claim = GOOD.replace('Ours: C = 1.2350', 'Ours: Pearson 0.41 and MSE 0.020 on the held-out line') + 'SBS 0.5.\n'
    (tmp_path / 'CLAIM.md').write_text(claim)
    (tmp_path / 'BASELINES.json').write_text(json.dumps([_row('Pearson', 0.0, 0.2, 0.41)]))
    assert any('Ours reports mse' in e for e in lint(tmp_path))
    rows = [_row('Pearson', 0.0, 0.2, 0.41), dict(_row('MSE', 0.030, 0.025, 0.020, higher=False), trivial=0.018)]
    (tmp_path / 'BASELINES.json').write_text(json.dumps(rows))
    assert any('does not beat the trivial' in e for e in lint(tmp_path))  # loses to the mean on MSE
    (tmp_path / 'BASELINES.json').write_text(json.dumps([_row('Pearson', 0.0, 0.2, 0.41),
                                                         _row('MSE', 0.030, 0.025, 0.020, higher=False)]))
    assert lint(tmp_path) == []


def test_noise_is_a_note_not_a_fail(tmp_path):
    from result_lint import noise_notes
    (tmp_path / 'CLAIM.md').write_text(GOOD + 'AUROC 0.8556 vs simple 0.84. SBS 0.956.\n')
    (tmp_path / 'BASELINES.json').write_text(json.dumps(_row('AUROC', 0.5, 0.84, 0.8556, noise=0.02)))
    assert lint(tmp_path) == []
    assert any('within the run-to-run spread' in n for n in noise_notes(tmp_path))
    (tmp_path / 'BASELINES.json').write_text(json.dumps(_row('AUROC', 0.5, 0.84, 0.8556, noise=0.004)))
    assert noise_notes(tmp_path) == []
    (tmp_path / 'BASELINES.json').write_text(json.dumps(_row('AUROC', 0.5, 0.84, 0.8556, noise=-1)))
    assert any('noise must be' in e for e in lint(tmp_path))


def test_gain_on_one_harness_only_is_a_note_not_a_fail(tmp_path):
    # 11-20, Illumina CellularAI: an idea was kept only if it gained on all three of their harnesses.
    from result_lint import harness_notes
    (tmp_path / 'CLAIM.md').write_text(GOOD + 'AUROC 0.86 on VCC2025 and 0.80 on Replogle. SBS 0.9.\n')
    rows = [_row('AUROC', 0.5, 0.80, 0.86, harness='VCC2025'), _row('AUROC', 0.5, 0.80, 0.80, harness='Replogle')]
    (tmp_path / 'BASELINES.json').write_text(json.dumps(rows))
    assert lint(tmp_path) == []
    notes = harness_notes(tmp_path)
    assert len(notes) == 1 and 'on Replogle' in notes[0]
    rows[1] = _row('AUROC', 0.5, 0.80, 0.84, harness='Replogle')
    (tmp_path / 'BASELINES.json').write_text(json.dumps(rows))
    assert harness_notes(tmp_path) == []


def test_pooling_baselines_mean_inverse_variance_stouffer():
    from pool import mean, inverse_variance, stouffer
    effects, ses = [1.0, 1.0, -2.0], [0.5, 0.5, 4.0]
    assert mean(effects) == pytest.approx(0.0)
    assert inverse_variance([1.0, 3.0], [1.0, 1.0]) == pytest.approx(2.0)
    assert inverse_variance(effects, ses) > 0.9  # the noisy outlier barely counts
    assert stouffer(effects, ses) == pytest.approx((2 + 2 - 0.5) / 3 ** 0.5)
    assert stouffer([1.0, 1.0], [1.0, 1.0], weights=[1.0, 0.0]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        stouffer([1.0], [0.0])
    out = subprocess.run([sys.executable, str(ROOT / 'harness' / 'tools' / 'pool.py'), '--effect', '1',
                          '--se', '0.5', '--effect', '1', '--se', '0.5'], capture_output=True, text=True)
    assert out.returncode == 0 and json.loads(out.stdout)['stouffer_z'] == pytest.approx(2 * 2 / 2 ** 0.5)
