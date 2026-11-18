"""Lane bars apply to source project tags, even when the publisher uses general."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

from harness.lane_registry import LaneRegistry

TOOL = Path(__file__).resolve().parents[1] / 'tools/x-reply-review'
spec = importlib.util.spec_from_loader('x_reply_review', importlib.machinery.SourceFileLoader('x_reply_review', str(TOOL)))
xrr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xrr)
PID = '2122750198334292029'


def draft(tags='', pid=PID):
    return '### @example | https://x.com/example/status/{}\n- Status: ready\n{}\n- Text: Thanks.\n'.format(pid, tags)


def registry(x=False):
    return LaneRegistry({'lanes': {'virtual-embryo': {'status': 'retired', 'x': x, 'aliases': ['ve']}}})


@pytest.mark.parametrize('tags', ['- Owner: general | Project: virtual-embryo | Move: thanks',
                                  '- Lane: virtual-embryo', '- Project: ve'])
def test_ready_tagged_drafts_are_refused_without_affecting_other_drafts(tmp_path, tags):
    text = draft(tags) + draft('- Project: planets', '2222750198334292029')
    filtered, rows = xrr.filter_drafts(text, {}, registry(), tmp_path, 'today')
    assert len(rows) == 1 and rows[0]['post_ids'] == [PID]
    assert 'registry x=false' in filtered
    assert filtered.count('Status: ready') == 1


def test_real_log_project_shape_blocks_draft_with_missing_row_tag(tmp_path):
    log = tmp_path / 'log.jsonl'
    log.write_text(json.dumps(dict(action='draft_reply', target_url='https://x.com/example/status/' + PID,
                                   project='virtual-embryo', status='ready')) + '\n'
                   + json.dumps(dict(action='reply', in_reply_to='https://x.com/example/status/' + PID,
                                     lane='general')) + '\n')
    filtered, rows = xrr.filter_drafts(draft('- Owner: general'), xrr.log_tags(log), registry(), tmp_path, 'today')
    assert rows and 'Status: ready' not in filtered


@pytest.mark.parametrize('rule', ['Results stay off X.', 'Do not post results to X.',
                                 'Never publish this lane on Twitter.', 'No X posting.', 'x: false',
                                 'Results stay off\nX.'])
def test_rules_bar_wins_over_registry_permission_and_aliases(tmp_path, rule):
    path = tmp_path / 'virtual-embryo/RULES.md'
    path.parent.mkdir()
    path.write_text(rule)
    filtered, rows = xrr.filter_drafts(draft('- Project: ve'), {}, registry(True), tmp_path, 'today')
    assert rows and str(path) in rows[0]['reason']


def test_round_heading_lane_tag_is_inherited_only_by_its_drafts(tmp_path):
    text = '## Round | Lane: virtual-embryo\n' + draft() + '## General round\n' + draft(pid='2222750198334292029')
    filtered, rows = xrr.filter_drafts(text, {}, registry(), tmp_path, 'today')
    assert len(rows) == 1 and filtered.count('Status: ready') == 1


def test_ordinary_x_rules_and_already_posted_drafts_are_unchanged(tmp_path):
    path = tmp_path / 'virtual-embryo/RULES.md'
    path.parent.mkdir()
    path.write_text('Post results to X only after approval. Never post unverified claims. Read X for prior art.')
    text = draft('- Lane: virtual-embryo')
    assert xrr.filter_drafts(text, {}, registry(True), tmp_path, 'today') == (text, [])
    posted = text.replace('Status: ready', 'Status: POSTED yesterday')
    assert xrr.filter_drafts(posted, {}, registry(), tmp_path, 'today') == (posted, [])


def test_apply_drops_and_logs_once_and_invalid_registry_stops_review(tmp_path, monkeypatch):
    lanes = tmp_path / 'lanes'
    lanes.mkdir()
    reg = lanes / 'REGISTRY.json'
    reg.write_text(json.dumps({'lanes': registry().lanes}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(reg))
    drafts, log = tmp_path / 'drafts.md', tmp_path / 'log.jsonl'
    drafts.write_text(draft('- Project: virtual-embryo'))
    args = ['--lanes-root', str(lanes), '--drafts', str(drafts), '--log', str(log)]
    assert xrr.main(args) == 1 and 'Status: ready' in drafts.read_text() and not log.exists()
    assert xrr.main(args + ['--apply']) == 0
    assert xrr.main(args + ['--apply']) == 0
    assert len(log.read_text().splitlines()) == 1
    reg.write_text('{broken')
    assert xrr.main(args + ['--apply']) == 78


@pytest.mark.parametrize('value', ['false', 0, None, []])
def test_registry_x_field_is_boolean(value):
    with pytest.raises(ValueError, match='x must be boolean'):
        registry(value)
