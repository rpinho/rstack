"""Friends counts only new science from 2025+ papers (Ricardo, 11-11): log-result, outreach and lane-yield
all read lanes/<lane>/RESULT_GATES.json, so a repro, a bug or a tighter number never counts as yield."""
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
import result_gates  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lr = load('lr_gates', 'harness/tools/lane-yield/log_result.py')
ly = load('ly_gates', 'harness/tools/lane-yield/lane_yield.py')
GATES = {'paper_since': '2025-01-01', 'novelty': ['new-science']}
RUBRIC = ("CONTROLS: controls in runs/ctrl.json rule it out, 3 of 3 agree. "
          "CONTRADICTING: none dropped; all 12 rows in data/all.csv kept. "
          "LABELS: re-derived from raw/labels.tsv, 12 of 12 match.")


def lane(tmp_path, gates=GATES):
    d = tmp_path / 'lanes/friends'
    d.mkdir(parents=True)
    if gates is not None:
        (d / 'RESULT_GATES.json').write_text(json.dumps(gates))
    return d


def test_errors_name_what_is_wrong():
    assert result_gates.errors(GATES, 'new-science', '2025-06-01') == []
    assert result_gates.errors(None, None, None) == []
    errs = result_gates.errors(GATES, 'tightening', '2019-03-01')
    assert len(errs) == 2 and 'tightening' in errs[0] and '2019-03-01' in errs[1]
    assert len(result_gates.errors(GATES, None, None)) == 2


def test_a_malformed_gate_file_raises(tmp_path):
    d = lane(tmp_path, {'paper_since': '2025', 'novelty': ['new-science']})
    with pytest.raises(ValueError):
        result_gates.load(d)
    (d / 'RESULT_GATES.json').write_text(json.dumps({'novelty': ['novel']}))
    with pytest.raises(ValueError):
        result_gates.load(d)


def test_log_result_refuses_old_papers_and_non_new_science(tmp_path, capsys):
    ledger = lane(tmp_path) / 'RESULTS.jsonl'
    base = ['--ledger', str(ledger), '--new', 'yes', '--kind', 'question', '--what', 'w',
            '--link', 'https://doi.org/10.1/x', '--referee', 'HOLDS', '--verdict', RUBRIC]
    assert lr.main(base + ['--novelty', 'bug', '--paper-date', '2025-03-01']) == 2
    assert lr.main(base + ['--novelty', 'new-science', '--paper-date', '2023-03-01']) == 2
    assert 'from 2025-01-01 on' in capsys.readouterr().err
    assert not ledger.exists()
    assert lr.main(base + ['--novelty', 'new-science', '--paper-date', '2025-03-01']) == 0
    row = json.loads(ledger.read_text())
    assert (row['novelty'], row['paper_date']) == ('new-science', '2025-03-01')


def test_lane_yield_counts_only_gated_holds_and_reports_the_week(tmp_path):
    ledger = lane(tmp_path) / 'RESULTS.jsonl'
    now = time.time()
    utc = ly.datetime.fromtimestamp(now - 3600).astimezone().isoformat()
    tight = dict(utc=utc, new=True, kind='value', referee='HOLDS', novelty='tightening', paper_date='2025-05-01')
    ledger.write_text(json.dumps(tight) + '\n')
    cfg = {'logs': [], 'results': [str(ledger)]}
    r = ly.check_lane('friends', cfg, now)
    assert r['new_yes'] == 0 and r['gated_holds_7d'] == 0
    ledger.write_text(json.dumps(tight) + '\n' + json.dumps(dict(tight, novelty='new-science')) + '\n')
    r = ly.check_lane('friends', cfg, now)
    assert r['new_yes'] == 1 and r['gated_holds_7d'] == 1


def test_a_lane_without_gates_is_unchanged(tmp_path):
    ledger = lane(tmp_path, None) / 'RESULTS.jsonl'
    now = time.time()
    utc = ly.datetime.fromtimestamp(now - 3600).astimezone().isoformat()
    ledger.write_text(json.dumps(dict(utc=utc, new=True, kind='value', referee='HOLDS')) + '\n')
    r = ly.check_lane('math', {'logs': [], 'results': [str(ledger)]}, now)
    assert r['new_yes'] == 1 and 'gated_holds_7d' not in r


def test_outreach_refuses_a_paper_email_without_new_science_claims(tmp_path):
    import outreach
    d = lane(tmp_path)
    claim = tmp_path / 'claim1'
    claim.mkdir()
    (claim / 'CLAIM.md').write_text('NEW: yes\nNovelty: tightening\nPaper date: 2024-02-01\n')
    row = dict(kind='paper', claims=[str(claim)])
    errs = outreach.novelty_findings(d, row)
    assert len(errs) == 2 and all(e.startswith('NOVELTY: claim1') for e in errs)
    assert outreach.novelty_findings(d, dict(kind='paper', claims=[]))[0].startswith('NOVELTY: a paper email')
    (claim / 'CLAIM.md').write_text('NEW: yes\nNovelty: new-science\nPaper date: 2025-09-12\n')
    assert outreach.novelty_findings(d, row) == []
    assert outreach.novelty_findings(d, dict(kind='code-bug', claims=[])) == []
    assert outreach.novelty_findings(lane(tmp_path / 'other', None), dict(kind='paper')) == []
