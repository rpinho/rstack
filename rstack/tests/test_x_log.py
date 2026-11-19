"""x-engage log rows keep target_url a string, and the bookmark reader survives rows that don't.

11-19: summary rows with "target_url": null crashed bookmark_queue.acted() (re.search on None) every
round from 20:56Z. Both ends are covered: the writer helper (x-log) never appends a non-string
target_url and repairs rows written around it; acted() reads null, numeric and missing values.
"""
import importlib.machinery
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / 'tools/x-log'
REVIEW = HERE.parent / 'tools/x-reply-review'
VENDORED = HERE / 'fixtures/x-engage/bookmark_queue_acted.py'
# The suite never reads the real home (conftest.py), so the host copy is opt-in: X_ENGAGE_DIR=~/.local/share/x-engage.
LIVE = Path(os.environ.get('X_ENGAGE_DIR') or '/nonexistent').expanduser() / 'bookmark_queue.py'
PID, PID2, PID3 = '2190000000000000001', '2190000000000000002', '2190000000000000003'


def load(name, path):
    spec = importlib.util.spec_from_loader(name, importlib.machinery.SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


xlog = load('x_log', TOOL)
BAD_ROWS = [
    dict(utc='2026-11-19T20:56:55Z', action='notifications_check', target_url=None, text='nothing new',
         session='x-reply-review'),
    dict(utc='2026-11-19T20:57:50Z', action='reply_early_none', target_url=None, text='none fresh'),
    dict(utc='2026-11-19T20:58:15Z', action='follow_back_check', target_url=None, text='no new follower'),
    dict(utc='2026-11-19T20:58:15Z', action='review_summary', target_url=None, text='0 replies'),
    dict(utc='2026-11-19T21:00:00Z', action='like', target_url=int(PID3)),
    dict(utc='2026-11-19T21:00:00Z', action='round_summary', text='no target_url key at all'),
    dict(utc='2026-11-19T21:00:00Z', action='follow'),
]
GOOD_ROWS = [
    dict(action='like', target_url='https://x.com/example_lab/status/' + PID),
    dict(action='reply', target_url='https://x.com/rpinho_sci/status/' + PID2,
         in_reply_to='https://x.com/example_lab/status/' + PID),
    dict(action='follow', target_url='https://x.com/Example_Builder'),
]


def write_log(where, rows):
    where.mkdir(parents=True, exist_ok=True)
    (where / 'log.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows) + 'not json\n[1, 2]\n')
    return where / 'log.jsonl'


ACTED = [pytest.param(VENDORED, id='vendored')]
if LIVE.exists():
    ACTED.append(pytest.param(LIVE, id='live-host-copy'))


@pytest.mark.parametrize('source', ACTED)
def test_acted_reads_null_numeric_and_missing_target_url(tmp_path, source):
    module = load('bookmark_queue_under_test', source)
    write_log(tmp_path, BAD_ROWS[:3] + GOOD_ROWS + BAD_ROWS[3:])
    module.HERE = str(tmp_path)
    liked, replied, followed = module.acted()
    assert PID in liked and PID3 not in liked  # a bare number has no /status/ to match
    assert PID2 in replied
    assert 'example_builder' in followed


def test_vendored_acted_matches_the_live_copy_when_present():
    if not LIVE.exists():
        pytest.skip('set X_ENGAGE_DIR to check a host copy')
    live = load('bookmark_queue_live', LIVE)
    assert inspect.getsource(live.acted) == inspect.getsource(load('bq_vendored', VENDORED).acted)


def run(log, *args):
    return subprocess.run([sys.executable, str(TOOL), '--log', str(log), *args], capture_output=True, text=True)


@pytest.mark.parametrize('row', BAD_ROWS[:4] + BAD_ROWS[5:])
def test_append_writes_empty_string_for_null_or_missing_target_url(tmp_path, row):
    log = tmp_path / 'log.jsonl'
    assert run(log, json.dumps(row)).returncode == 0
    written = json.loads(log.read_text())
    assert written['target_url'] == '' and written['action'] == row['action']


@pytest.mark.parametrize('row', [dict(action='like', target_url=int(PID)), dict(action='like', target_url=[PID]),
                                 dict(action='like', target_url=True), dict(target_url=''), dict(action=None),
                                 [1], 'just text'])
def test_append_refuses_non_string_target_url_and_bad_rows(tmp_path, row):
    log = tmp_path / 'log.jsonl'
    result = run(log, json.dumps(row))
    assert result.returncode == 2 and 'refused' in result.stderr and not log.exists()
    assert run(log, '{not json').returncode == 2 and not log.exists()


def test_append_keeps_fields_and_stamps_utc(tmp_path):
    log = tmp_path / 'log.jsonl'
    log.write_text(json.dumps(GOOD_ROWS[0]) + '\n')
    assert run(log, json.dumps(dict(action='review_summary', text='0 replies'))).returncode == 0
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[0] == GOOD_ROWS[0] and rows[1]['utc'] and rows[1]['text'] == '0 replies'


def test_repair_makes_every_present_target_url_a_string_and_touches_nothing_else(tmp_path):
    log = write_log(tmp_path, GOOD_ROWS + BAD_ROWS)
    before = log.read_text().splitlines()
    result = run(log, '--repair')
    assert result.returncode == 0 and 'repaired 5 row' in result.stdout
    after = log.read_text().splitlines()
    assert len(after) == len(before)
    for old, new in zip(before, after):
        try:
            was = json.loads(old)
        except ValueError:
            was = None
        if not isinstance(was, dict) or isinstance(was.get('target_url', ''), str):
            assert new == old
            continue
        row = json.loads(new)
        assert isinstance(row['target_url'], str)
        assert {k: v for k, v in row.items() if k != 'target_url'} == \
            {k: v for k, v in was.items() if k != 'target_url'}
    assert json.loads(after[len(GOOD_ROWS)])['target_url'] == ''
    assert json.loads(after[len(GOOD_ROWS) + 4])['target_url'] == PID3
    assert run(log, '--repair').stdout.startswith('x-log: repaired 0 row')
    assert log.read_text().splitlines() == after


def test_repaired_log_reads_cleanly_with_the_pre_fix_reader(tmp_path):
    """The 11-19 crash line, d.get('target_url', ''), works on a repaired log."""
    import re
    log = write_log(tmp_path, BAD_ROWS + GOOD_ROWS)
    run(log, '--repair')
    for line in log.read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            re.search(r'/status/(\d+)', d.get('target_url', ''))


def test_x_reply_review_rows_never_carry_a_non_string_target_url(tmp_path):
    """The rstack lane filter is the one code writer of review rows; its rows already comply."""
    from harness.lane_registry import LaneRegistry
    xrr = load('x_reply_review_rows', REVIEW)
    registry = LaneRegistry({'lanes': {'virtual-embryo': {'status': 'retired', 'x': False}}})
    text = ('### @example | https://x.com/example/status/{}\n- Status: HELD by hand\n'
            '### @example | https://x.com/example/status/{}\n- Status: ready\n- Lane: virtual-embryo\n').format(PID, PID2)
    _, rows = xrr.filter_drafts(text, {}, registry, tmp_path, 'today')
    assert {r['action'] for r in rows} == {'draft_held', 'drop_draft'}
    for row in rows:
        assert xlog.clean_row(row)['target_url'] == row.get('target_url', '')
