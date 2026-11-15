"""A lane whose results are PRs ships only what upstream merged.

11-10: in the maintainer's repo nothing had merged since 10-26, 18 of the 86 open PRs were ours,
and the math lane reported "two PR updates are live on Tao's table". These tests use a cached PR
list written by hand, so no test touches GitHub.
"""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
import upstream  # noqa: E402
import publish_lint  # noqa: E402

spec = importlib.util.spec_from_file_location('lane_yield', ROOT / 'harness/tools/lane-yield/lane_yield.py')
ly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ly)

REPO = 'teorth/optimizationproblems'
NOW = dt.datetime(2026, 11, 10, 14, 0, tzinfo=dt.timezone.utc)


def pr(n, state='open', merged=None, created='2026-10-30T19:48:29Z', author='rpinho'):
    return dict(number=n, state=state, merged_at=merged, created_at=created, author=author,
                url='https://github.com/{}/pull/{}'.format(REPO, n), base='main')


def lane(tmp_path, prs, fetched=None):
    d = tmp_path / 'lanes' / 'math'
    d.mkdir(parents=True)
    (d / 'UPSTREAM.json').write_text(json.dumps(dict(repo=REPO, author='rpinho')))
    upstream.refresh(d, fetch=lambda repo: prs, now=fetched or dt.datetime.now(dt.timezone.utc))
    return d


def ours_open(n):
    return [pr(300 + i, created='2026-10-{:02d}T00:00:00Z'.format(30 - i % 3)) for i in range(n)]


def test_the_summary_counts_our_open_unmerged_prs_and_the_oldest(tmp_path):
    d = lane(tmp_path, ours_open(3) + [pr(200, 'closed', '2026-10-26T04:07:00Z'),
                                       pr(201, author='someone-else')], fetched=NOW)
    s = upstream.summary(d, NOW)
    assert s['open_unmerged'] == 3 and s['merged'] == 1 and s['last_merge_ours'].startswith('2026-10-26')
    assert s['oldest_open_days'] == pytest.approx(13.6, abs=0.1)
    assert 'open-unmerged 3, oldest 13.6 d; merged 1' in upstream.line(s)


def test_yield_counts_a_result_only_once_merged(tmp_path):
    d = lane(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z')])
    log = tmp_path / 'math_a.log'
    log.write_text('=== run 1 model m Tue Nov 10 00:00:00 EST 2026\nwork\nexit 0 Tue Nov 10 23:00:00 EST 2026\n')
    now = ly.parse_stamp('exit 0 Tue Nov 10 23:30:00 EST 2026')
    ledger = tmp_path / 'RESULTS.jsonl'
    utc = ly.datetime.fromtimestamp(now - 3600).astimezone().isoformat()
    row = dict(utc=utc, new=True, kind='value', referee='HOLDS',
               link='https://github.com/{}/pull/298'.format(REPO))
    ledger.write_text(json.dumps(row) + '\n')
    cfg = {'logs': [str(log)], 'results': [str(ledger)], 'upstream': str(d)}
    r = ly.check_lane('math', cfg, now)
    assert r['new_yes'] == 0 and r['status'] == 'FAIL', 'an open PR is activity'
    assert 'nothing merged upstream: 1 of our PRs open and unmerged' in r['fails'][0]
    assert r['upstream_open'] == 1
    ledger.write_text(json.dumps(dict(row, link='https://github.com/{}/pull/250'.format(REPO))) + '\n')
    assert ly.check_lane('math', cfg, now)['new_yes'] == 1, 'a merged PR is a result'
    # Without the upstream setting the old counting is unchanged.
    cfg.pop('upstream')
    ledger.write_text(json.dumps(row) + '\n')
    assert ly.check_lane('math', cfg, now)['new_yes'] == 1


@pytest.mark.parametrize('text', [
    "Both pushed and live: two PR updates are live on Tao's table.",
    'PR #298 updated to C86 <= 1.8055; live now.',
    'https://github.com/teorth/optimizationproblems/pull/298 is live',
    "C47 is on Tao's table via #298.",
])
def test_calling_an_unmerged_pr_live_fails(tmp_path, text):
    lane(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z')])
    errors = upstream.report_lint(text, tmp_path)
    assert errors and 'PR updated, not merged' in errors[0]


@pytest.mark.parametrize('text', [
    'PR #298 updated, not merged.',
    "#250 merged on 10-26 and is on Tao's table.",
    'The memory guard is live on the m5.',
    'kb backup: no OK line; the live log is fine.',
    'Both options are still on the table.',
    "Tao's table lists C22b at 0.9 since 2024.",
])
def test_true_reports_pass(tmp_path, text):
    lane(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z')])
    assert upstream.report_lint(text, tmp_path) == []


def test_without_any_upstream_lane_the_lint_is_silent(tmp_path):
    assert upstream.report_lint("two PR updates are live on Tao's table", tmp_path) == []


def yield_row(tmp_path, prs, hold=None):
    d = lane(tmp_path, prs)
    log = tmp_path / 'math_a.log'
    log.write_text('=== run 1 model m Tue Nov 10 00:00:00 EST 2026\nwork\nexit 0 Tue Nov 10 23:00:00 EST 2026\n')
    now = ly.parse_stamp('exit 0 Tue Nov 10 23:30:00 EST 2026')
    cfg = {'logs': [str(log)], 'results': [], 'upstream': str(d), 'report_only': True,
           'hold': str(hold or tmp_path / 'lanes/math/HOLD')}
    return ly.check_lane('math', cfg, now), cfg


def test_a_frozen_queue_keeps_the_lane_report_only(tmp_path, monkeypatch):
    """general 11-10: nobody merged since 10-26, so a hold would punish the lane for that."""
    monkeypatch.setattr(ly.subprocess, 'run', lambda *a, **k: None)
    row, cfg = yield_row(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z'),
                                    pr(260, 'closed', '2026-10-26T03:00:00Z', author='someone-else')])
    assert row['status'] == 'FAIL' and row['upstream_binding'] is False
    ly.act(row, cfg)
    assert not Path(cfg['hold']).exists()


def test_others_merged_a_week_after_us_makes_it_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(ly.subprocess, 'run', lambda *a, **k: None)
    row, cfg = yield_row(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z'),
                                    pr(360, 'closed', '2026-11-03T05:00:00Z', author='someone-else')])
    assert row['upstream_binding'] is True and row['upstream_merge_gap_days'] == 8
    assert 'binding: upstream merged others 8 d after our last merge' in row['fails'][0]
    ly.act(row, cfg)
    assert Path(cfg['hold']).read_text().startswith('HOLD by lane-yield')


def test_six_days_is_not_yet_binding(tmp_path):
    row, _ = yield_row(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z'),
                                  pr(360, 'closed', '2026-11-01T05:00:00Z', author='someone-else')])
    assert row['upstream_binding'] is False and row['upstream_merge_gap_days'] == 6


@pytest.mark.parametrize('post', [
    "Candidate bound on Tao's table for C22b.",
    'Candidate bound on Tao’s table for C22b.',
    'New C22b bound, PR https://github.com/teorth/optimizationproblems/pull/347 is live.',
])
def test_an_x_post_that_calls_an_open_pr_shipped_fails_with_the_x_wording(tmp_path, post):
    """11-10: the C22b post said "Candidate bound on Tao's table" while #347 was unmerged."""
    lane(tmp_path, [pr(347)])
    errors = upstream.report_lint(post, tmp_path, fix=upstream.X_FIX)
    assert errors and "(Tao's optimization table), PR open" in errors[0]


def test_the_x_fix_wording_itself_passes(tmp_path):
    lane(tmp_path, [pr(347)])
    assert upstream.report_lint("Candidate bound for C22b (Tao's optimization table), PR open: "
                                'https://github.com/teorth/optimizationproblems/pull/347', tmp_path) == []


def test_a_new_pr_is_not_capped_by_how_many_are_open(tmp_path, monkeypatch):
    """11-14: the open-PR cap is removed (Ricardo: "Why do we have that rule? Just remove it.")."""
    lane(tmp_path, ours_open(25), fetched=NOW)
    monkeypatch.setenv('RH_ROOT', str(tmp_path))
    errors = publish_lint.publication_errors('/no/body.md', REPO, now=NOW)
    assert not any('open-PR cap' in e for e in errors)          # it goes on to the receipt check


def test_a_refereed_result_published_outside_the_upstream_repo_counts(tmp_path):
    """11-15: math's Erdos #1183 values (HOLDS, linked to the problem site) never counted, because the
    merged-upstream rule was applied to every row, not only to results sent to the upstream repo."""
    d = lane(tmp_path, [pr(298)])
    log = tmp_path / 'math_a.log'
    log.write_text('=== run 1 model m Tue Nov 10 00:00:00 EST 2026\nwork\nexit 0 Tue Nov 10 23:00:00 EST 2026\n')
    now = ly.parse_stamp('exit 0 Tue Nov 10 23:30:00 EST 2026')
    ledger = tmp_path / 'RESULTS.jsonl'
    utc = ly.datetime.fromtimestamp(now - 3600).astimezone().isoformat()
    ledger.write_text(json.dumps(dict(utc=utc, new=True, kind='value', referee='HOLDS',
                                      link='https://www.erdosproblems.com/1183')) + '\n')
    cfg = {'logs': [str(log)], 'results': [str(ledger)], 'upstream': str(d)}
    assert ly.check_lane('math', cfg, now)['new_yes'] == 1
    ledger.write_text(json.dumps(dict(utc=utc, new=True, kind='value', referee='FAILS',
                                      link='https://www.erdosproblems.com/1183')) + '\n')
    assert ly.check_lane('math', cfg, now)['new_yes'] == 0, 'still needs a HOLDS verdict'
