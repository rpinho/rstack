"""A lead found during a sweep can get its X search asked for.

11-07, math's first sweep on the m5. It finished ok=false on prior-art "x: blocked" for a lead the
worker had just found (Erdos problem #531, Folkman numbers). Nothing was wrong with the worker's
behaviour: workers have no route to X, the receipt needs a real X search, and recording it blocked
is exactly what the prompt asks for. The hole was downstream. X_QUERIES.txt, the handoff the
general session answers in the browser, was built only from `x_queries` in SWEEP.toml, so there
was no way for a lead discovered DURING a sweep to have an X query asked for it. "Stays queued for
another pass" then meant every later pass failing in the same place, forever.

So the worker may ASK. Nothing about the receipt rule moves: a lead with no X search still cannot
be promoted, and these tests check that too, because the tempting fix was to let "not applicable"
satisfy the X source, which is the rubber stamp this harness exists to refuse.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rh
import sweep
import idea_policy

QUERY = 'Folkman number f(3,3;5) teorth erdosproblems'


@pytest.fixture
def lane(tmp_path):
    d = tmp_path / 'lanes' / 'math'
    d.mkdir(parents=True)
    return d


def report(lane, body):
    p = lane / 'search.report.md'
    p.write_text(body)
    return p


def test_a_worker_can_ask_and_the_ask_reaches_the_browser_handoff(lane):
    r = report(lane, 'IDEA MATH-1: a new lead\nX QUERY MATH-1: {}\nDONE\n'.format(QUERY))
    assert sweep.record_x_requests(lane, r, rh) == [('MATH-1', QUERY)]
    text = sweep.x_query_text(lane, {'x_queries': ['optimizationproblems teorth']})
    assert QUERY in text
    assert 'for idea MATH-1' in text
    # The standing queries are still there: the ask is added, not substituted.
    assert 'optimizationproblems teorth' in text


def test_running_the_search_clears_the_ask(lane):
    r = report(lane, 'IDEA MATH-1: x\nX QUERY MATH-1: {}\nDONE\n'.format(QUERY))
    sweep.record_x_requests(lane, r, rh)
    assert sweep.x_requests(lane)
    rh.append(lane / 'X_SEARCHES.jsonl',
              dict(utc=rh.now(), query=QUERY, result='none', n_hits=0, captured_by='ricardo'))
    assert sweep.x_requests(lane) == []
    assert QUERY not in sweep.x_query_text(lane, {})


def test_case_and_whitespace_do_not_make_it_a_different_ask(lane):
    rh.append(lane / 'X_SEARCHES.jsonl', dict(utc=rh.now(), query=QUERY.upper(), result='none'))
    r = report(lane, 'X QUERY MATH-1:   {}  \nDONE\n'.format(QUERY))
    assert sweep.record_x_requests(lane, r, rh) == []


def test_the_same_ask_is_not_filed_twice(lane):
    r = report(lane, 'X QUERY MATH-1: {}\nDONE\n'.format(QUERY))
    assert len(sweep.record_x_requests(lane, r, rh)) == 1
    assert sweep.record_x_requests(lane, r, rh) == []
    assert len(sweep.x_requests(lane)) == 1
    rows = [json.loads(l) for l in (lane / sweep.X_REQUESTS).read_text().splitlines() if l.strip()]
    assert len(rows) == 1 and rows[0]['idea'] == 'MATH-1'


def test_a_report_with_no_ask_files_nothing(lane):
    r = report(lane, 'IDEA MATH-1: a lead with its own X capture\nDONE\n')
    assert sweep.record_x_requests(lane, r, rh) == []
    assert not (lane / sweep.X_REQUESTS).exists()
    assert 'Asked for by a search worker' not in sweep.x_query_text(lane, {})


def test_a_malformed_ask_is_ignored_rather_than_filed_as_a_query(lane):
    r = report(lane, 'X QUERY: no id\nX QUERY not-an-id: q\nX QUERY MATH-1:\nDONE\n')
    assert sweep.record_x_requests(lane, r, rh) == []


def test_a_corrupt_request_ledger_does_not_blind_the_handoff(lane):
    (lane / sweep.X_REQUESTS).write_text('{"idea": "MATH-1", "query": "' + QUERY + '"}\nnot json\n\n')
    assert sweep.x_requests(lane) == [('MATH-1', QUERY)]


def test_the_ask_does_not_satisfy_the_receipt(lane, tmp_path):
    """The whole point. An asked-for search is not a search, and the compiler must still refuse."""
    r = report(lane, 'IDEA MATH-1: x\nX QUERY MATH-1: {}\nDONE\n'.format(QUERY))
    sweep.record_x_requests(lane, r, rh)
    receipt = lane / 'prior-art-MATH-1.json'
    receipt.write_text(json.dumps(dict(
        schema=1, baseline='best public bound 31',
        sources={s: dict(status='none', query='q', searched_at='2026-11-01T00:00:00Z', hits=[],
                         note='searched, nothing') for s in ('github', 'papers', 'leaderboards')} |
                {'x': dict(status='requested', query=QUERY, searched_at='2026-11-01T00:00:00Z',
                           hits=[], note='asked for; no intake has run it')})))
    with pytest.raises(ValueError) as e:
        idea_policy.prior_art(receipt)
    assert 'prior-art x' in str(e.value)


def attempt_with(tmp_path, search_text, kill_text, x_entry, other_status='none'):
    attempt = tmp_path / 'attempt'
    attempt.mkdir(exist_ok=True)
    paths = {'search': attempt / 'search.report.md', 'read': attempt / 'read.report.md',
             'kill': attempt / 'kill.report.md'}
    paths['search'].write_text(search_text)
    paths['read'].write_text('READ MATH-1: judged\nDONE\n')
    paths['kill'].write_text(kill_text)
    # The receipt the worker actually wrote: everything searched except X, which it cannot reach.
    (attempt / 'prior-art-MATH-1.json').write_text(json.dumps(dict(
        schema=1, baseline='best public bound 31',
        sources=dict(
            [(s, dict(status=other_status, query='q', searched_at='2026-11-01T00:00:00Z', hits=[],
                      note='searched, nothing')) for s in ('github', 'papers', 'leaderboards')] +
            ([('x', x_entry)] if x_entry else [])))))
    return paths


BLOCKED_X = dict(status='blocked', query=QUERY, searched_at='2026-11-01T00:00:00Z', hits=[],
                 note='no intake for this topic; workers may not search X')
LEAD = 'IDEA MATH-1: a new lead with a metric, a kill test and no rules risk\nX QUERY MATH-1: {}\n'.format(QUERY)


def test_a_lead_waiting_on_its_own_x_query_is_pending_not_a_failure(lane, tmp_path):
    """planets, 11-09: three sweeps in one night each found one fresh lead, asked for its X search,
    and failed on that alone, so the lane never cleared in one pass. The lead now stays queued and
    the sweep is delivered, like a per-idea BLOCKED kill row."""
    paths = attempt_with(tmp_path, LEAD + 'DONE\n', 'RESULT MATH-1: KILLED value=0; pass line > 1\nDONE\n', BLOCKED_X)
    sweep.record_x_requests(lane, paths['search'], rh)
    cfg = dict(evidence_policy=True)
    assert sweep.check(paths, [], cfg, None, lane) == []
    assert cfg['_x_pending'] == ['MATH-1']


def test_a_search_blocked_only_on_its_own_x_query_is_not_a_stage_block(lane, tmp_path):
    paths = attempt_with(tmp_path, LEAD + 'BLOCKED\n', 'RESULT MATH-1: KILLED value=0; pass line > 1\nDONE\n', BLOCKED_X)
    assert sweep.check(paths, [], dict(evidence_policy=True), None, lane) == []


def test_pending_x_does_not_excuse_another_source(lane, tmp_path):
    paths = attempt_with(tmp_path, LEAD + 'BLOCKED\n', 'RESULT MATH-1: KILLED v=0; pass > 1\nDONE\n', BLOCKED_X,
                         other_status='blocked')
    errors = sweep.check(paths, [], dict(evidence_policy=True), None, lane)
    assert 'search report BLOCKED' in errors
    assert any(e.startswith('prior-art MATH-1: prior-art github') for e in errors), errors


def test_without_an_ask_a_blocked_x_still_fails_and_says_so(lane, tmp_path):
    paths = attempt_with(tmp_path, 'IDEA MATH-1: a new lead with a metric and a kill test\nDONE\n',
                         'RESULT MATH-1: KILLED v=0; pass > 1\nDONE\n', BLOCKED_X)
    errors = sweep.check(paths, [], dict(evidence_policy=True), None, lane)
    plain = [e for e in errors if e.startswith('prior-art MATH-1')]
    assert plain and 'waiting on an X search' not in plain[0]


def test_a_wrong_x_entry_is_not_pending(lane, tmp_path):
    """Only a missing or blocked X source is pending. A claimed search with a bad capture is a wrong
    receipt, answered by the worker."""
    bad = dict(status='none', query=QUERY, searched_at='2026-11-01T00:00:00Z', hits=[], note='n',
               capture_path=str(tmp_path / 'missing.jsonl'), capture_sha256='0' * 64)
    paths = attempt_with(tmp_path, LEAD + 'DONE\n', 'RESULT MATH-1: KILLED v=0; pass > 1\nDONE\n', bad)
    errors = sweep.check(paths, [], dict(evidence_policy=True), None, lane)
    assert any('evidence file must exist' in e for e in errors), errors


def test_a_pending_receipt_still_cannot_promote(lane, tmp_path):
    paths = attempt_with(tmp_path, LEAD + 'DONE\n', 'DONE\n', BLOCKED_X)
    receipt = paths['search'].parent / 'prior-art-MATH-1.json'
    assert idea_policy.prior_art(receipt, x_pending_ok=True)['x_pending'] is True
    with pytest.raises(ValueError) as e:
        idea_policy.prior_art(receipt)
    assert 'prior-art x' in str(e.value)


def test_a_survivor_waiting_on_x_goes_back_in_the_queue(lane, tmp_path):
    paths = attempt_with(tmp_path, LEAD + 'DONE\n', 'RESULT MATH-1: SURVIVED v=9; pass > 1\nDONE\n', BLOCKED_X)
    assert sweep.carry_over(lane, paths, rh, rh.now()) == []
    assert sweep.carry_over(lane, paths, rh, rh.now(), x_pending=['MATH-1']) == ['MATH-1']
    row = [json.loads(l) for l in (lane / 'IDEAS.jsonl').read_text().splitlines()][-1]
    assert row['prior_art'].endswith('prior-art-MATH-1.json')


# --- staged public inputs: the other half of math's first m5 sweep -----------------------------

def test_the_worker_is_told_what_is_staged_and_how_to_reach_it(lane):
    """The kill test reported "BLOCKED: need locally supplied witnesses/w396.txt". inputs.py had
    existed for a day and no prompt had ever mentioned it, so the worker had no way to know a
    staged file was even possible. A tool nothing tells the worker about is a tool nobody uses."""
    rh.append(lane / sweep.INPUTS, dict(name='w396', path=str(lane / 'inputs/w396'),
                                        sha256='2a57e17ea0bea652699a3149c5ac9c0ca71bdf77029b9f52a',
                                        bytes=396, pinned=True))
    text = sweep.inputs_text(lane)
    assert 'w396' in text and 'inputs.py' in text and 'path --name' in text
    assert 'never download anything yourself' in text


def test_with_nothing_staged_the_worker_is_told_how_to_ask(lane):
    text = sweep.inputs_text(lane)
    assert 'may NOT download' in text and 'BLOCKED: need' in text
    assert 'repo@commit' in text


def test_the_newest_row_for_a_name_wins(lane):
    """inputs.py appends; re-staging a file to pin it writes a second row for the same name."""
    rh.append(lane / sweep.INPUTS, dict(name='w396', path='/old/path', sha256='a' * 64, pinned=False))
    rh.append(lane / sweep.INPUTS, dict(name='w396', path='/new/path', sha256='b' * 64, pinned=True))
    assert sweep.staged_inputs(lane) == [('w396', '/new/path', 'b' * 64)]


def test_a_row_without_a_path_is_not_offered_as_available(lane):
    rh.append(lane / sweep.INPUTS, dict(name='broken', sha256='c' * 64))
    assert sweep.staged_inputs(lane) == []


def test_the_prompt_carries_it(lane, tmp_path):
    rh.append(lane / sweep.INPUTS, dict(name='w396', path=str(lane / 'inputs/w396'),
                                        sha256='d' * 64, pinned=True))
    (lane / 'RULES.md').write_text('rules\n')
    cfg = dict(rules=[(str(lane / 'RULES.md'), 'rules')], search_targets=['t'], sources=['s'],
               banned_sources=['b'], allowed_tests=['small arithmetic only'],
               allowed_writes=['work/'], cwd=str(lane), run_path=tmp_path, _lesson_rows=[],
               search_report='x', read_report='y', kill_report='z',
               cores=1, memory_gib=1, min_free_gib=30, worker_timeout_minutes=10,
               kill_test_max_minutes=10, testing_max_age_days=3, search_max_lines=200)
    paths = {s: tmp_path / (s + '.report.md') for s in ('search', 'read', 'kill')}
    for stage in ('search', 'read', 'kill'):
        text = sweep.generate(stage, lane, cfg, paths, '2026-11-07', [])
        assert 'w396' in text, stage
