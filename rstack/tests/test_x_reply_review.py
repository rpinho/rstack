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


def run_twice_args(tmp_path, monkeypatch, text, log_rows=()):
    lanes = tmp_path / 'lanes'
    lanes.mkdir()
    reg = lanes / 'REGISTRY.json'
    reg.write_text(json.dumps({'lanes': registry(True).lanes}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(reg))
    drafts, log = tmp_path / 'drafts.md', tmp_path / 'log.jsonl'
    drafts.write_text(text)
    log.write_text(''.join(json.dumps(row) + '\n' for row in log_rows))
    return drafts, log, ['--lanes-root', str(lanes), '--drafts', str(drafts), '--log', str(log), '--apply']


def test_held_status_stays_held_when_a_later_round_marks_it_ready_again(tmp_path, monkeypatch):
    held = draft('- Project: planets').replace('Status: ready', 'Status: HELD 11-17 (general flush: wait for Ricardo)')
    other = draft('- Project: planets', '2222750198334292029')
    drafts, log, args = run_twice_args(tmp_path, monkeypatch, held + other)
    assert xrr.main(args) == 0                       # run 1 records the hold in the log
    assert drafts.read_text() == held + other
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(r['action'], r['post_ids']) for r in rows] == [('draft_held', [PID])]
    drafts.write_text(held.replace('Status: HELD', 'Status: ready') + other)   # a producer re-decides it
    assert xrr.main(args) == 0                       # run 2 honors the hold
    text = drafts.read_text()
    assert 'Status: HELD' in text and 'hold kept' in text and 'wait for Ricardo' in text
    assert text.count('Status: ready') == 1 and '2222750198334292029' in text.split('Status: ready')[0]
    assert len(log.read_text().splitlines()) == 1    # no duplicate hold rows
    assert xrr.main(args) == 0 and drafts.read_text() == text


def test_logged_hold_holds_a_ready_draft_until_released(tmp_path, monkeypatch):
    hold = dict(utc='2026-10-31T13:19:56Z', action='draft_reply_held',
                target_url='https://x.com/example/status/' + PID, status='not ready; browser check required')
    drafts, log, args = run_twice_args(tmp_path, monkeypatch, draft(), [hold])
    for _ in range(2):
        assert xrr.main(args) == 0
        assert 'Status: ready' not in drafts.read_text() and 'draft_reply_held' in drafts.read_text()
    assert len(log.read_text().splitlines()) == 1
    released = dict(utc='2026-11-18T07:00:00Z', action='release_hold', target_url=hold['target_url'])
    drafts.write_text(draft())
    log.write_text(log.read_text() + json.dumps(released) + '\n')
    assert xrr.main(args) == 0 and 'Status: ready' in drafts.read_text()


def test_hold_on_a_quoted_post_does_not_hold_the_draft_quoting_it(tmp_path):
    text = draft('- Context: quotes https://x.com/other/status/2333750198334292029')
    holds = {'2333750198334292029': 'held'}
    assert xrr.filter_drafts(text, {}, registry(True), tmp_path, 'today', holds) == (text, [])


def hot(pid=PID):
    return f'\n\n## HOT 2026-11-28T14:30:00Z @example https://x.com/example/status/{pid}\nStatus: hot\n\n> A proof.\n'


def test_hot_draft_keeps_source_lane_bars_and_holds(tmp_path):
    text = hot() + hot('2222750198334292029')
    tags = {PID: {'virtual-embryo'}}
    filtered, rows = xrr.filter_drafts(text, tags, registry(), tmp_path, 'today')
    assert rows[0]['post_ids'] == [PID]
    assert 'Status: dropped today (lane bars X:' in filtered
    assert filtered.count('Status: hot') == 1
    filtered, rows = xrr.filter_drafts(text, {}, registry(), tmp_path, 'today', {PID: 'withheld'})
    assert rows[0]['action'] == 'hold_kept'
    assert 'Status: HELD today (hold kept: withheld)' in filtered
    assert filtered.count('Status: hot') == 1


def test_hot_quoted_text_cannot_set_its_lane(tmp_path):
    text = hot() + '> project: virtual-embryo\n'
    assert xrr.filter_drafts(text, {}, registry(), tmp_path, 'today') == (text, [])


def test_merge_draft_snapshot_retains_watcher_appends_and_review_statuses():
    base = draft() + hot('2222750198334292029')
    pending = hot('2333750198334292029')
    reviewed = base.replace('Status: hot', 'Status: POSTED today').replace('Status: ready', 'Status: dropped today')
    assert xrr.merge_drafts(base, base + pending, reviewed) == reviewed + pending
    assert xrr.merge_drafts(base, base, reviewed) == reviewed

    # Keep a producer edit and the late arrival when the reviewer edited its own snapshot.
    local = base.replace('- Text: Thanks.', '- Text: New text.') + pending
    assert xrr.merge_drafts(base, local, reviewed) == local.replace('Status: hot', 'Status: POSTED today', 1)
