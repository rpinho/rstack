"""11-27 fast lane: a venue with an automatic checker submits without a frozen selection or referee."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
import idea_policy
import lane_setup
import rh
from test_lane_setup import create, lane

spec = importlib.util.spec_from_file_location('lane_yield', ROOT / 'harness/tools/lane-yield/lane_yield.py')
ly = importlib.util.module_from_spec(spec); spec.loader.exec_module(ly)


def setup(tmp_path, checker=None, status='testing'):
    assert create(tmp_path) == 0
    target = lane(tmp_path)
    (target / 'SWEEP.toml').write_text('enabled = false\n' + ('checker = "{}"\n'.format(checker) if checker else ''))
    (target / 'IDEAS.jsonl').write_text(json.dumps(dict(id='a', status=status)) + '\n')
    return target


def test_checker_venue_submits_without_frozen_selection_or_referee(tmp_path):
    target = setup(tmp_path, 'lake build', 'shipped')
    assert idea_policy.checker(target) == 'lake build' and not idea_policy.enabled(target)
    assert lane_setup.audit(target, rh) == []


def test_venue_without_checker_still_requires_it(tmp_path):
    target = setup(tmp_path)
    assert idea_policy.enabled(target)
    assert 'new lanes require v2' in lane_setup.audit(target, rh)[0]


def test_leaderboard_submits_but_final_pick_needs_the_selection(tmp_path):
    assert lane_setup.audit(setup(tmp_path, 'leaderboard'), rh) == []
    shipped = setup(tmp_path / 'b', 'leaderboard', 'shipped')
    assert 'new lanes require v2' in lane_setup.audit(shipped, rh)[0]


def test_leaderboard_still_refuses_selecting_on_the_public_board(tmp_path):
    target = setup(tmp_path, 'leaderboard')
    path = target / 'LANE.json'
    data = json.loads(path.read_text())
    data['frozen']['public_board_selection'] = True
    path.write_text(json.dumps(data))
    assert lane_setup.audit(target, rh)


def test_accepted_submission_waits_for_its_post_merge_referee(tmp_path):
    ledger = tmp_path / 'RESULTS.jsonl'
    now = ly.parse_stamp('exit 0 Tue Nov  3 23:30:00 EST 2026')
    utc = ly.datetime.fromtimestamp(now - 3600).astimezone().isoformat()
    row = dict(utc=utc, new=True, kind='value', link='pr/1', referee='NONE')
    ledger.write_text(json.dumps(row) + '\n')
    cfg = {'logs': [], 'results': [str(ledger)]}
    assert ly.check_lane('m', cfg, now)['awaiting_referee'] == ['pr/1']
    ledger.write_text(json.dumps(row) + '\n' + json.dumps(dict(row, referee='HOLDS')) + '\n')
    assert 'awaiting_referee' not in ly.check_lane('m', cfg, now)
