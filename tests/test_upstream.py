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


def lane(tmp_path, prs, fetched=None, max_open=10):
    d = tmp_path / 'lanes' / 'math'
    d.mkdir(parents=True)
    (d / 'UPSTREAM.json').write_text(json.dumps(dict(repo=REPO, author='rpinho', max_open=max_open)))
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


def test_a_new_pr_waits_at_the_cap_and_an_update_does_not(tmp_path, monkeypatch):
    lane(tmp_path, ours_open(10), fetched=NOW)
    monkeypatch.setenv('RH_ROOT', str(tmp_path))
    errors = publish_lint.publication_errors('/no/body.md', REPO, now=NOW)
    assert len(errors) == 1 and errors[0].startswith('open-PR cap: 10 of our PRs are open and unmerged')
    assert 'Update an existing PR' in errors[0]
    # An edit of an existing PR is not a new PR: it reaches the ordinary receipt check instead.
    edit = publish_lint.publication_errors('/no/body.md', REPO + '#298', now=NOW)
    assert not any(e.startswith('open-PR cap') for e in edit)


def test_under_the_cap_a_new_pr_goes_on_to_the_receipt_check(tmp_path, monkeypatch):
    lane(tmp_path, ours_open(9), fetched=NOW)
    monkeypatch.setenv('RH_ROOT', str(tmp_path))
    errors = publish_lint.publication_errors('/no/body.md', REPO, now=NOW)
    assert errors and not errors[0].startswith('open-PR cap')


def test_a_stale_pr_list_refuses_rather_than_guesses(tmp_path):
    lane(tmp_path, ours_open(1), fetched=NOW - dt.timedelta(hours=7))
    errors = upstream.new_pr_errors(tmp_path, REPO, NOW)
    assert errors and 'over 6 h old' in errors[0] and '--refresh' in errors[0]


def test_another_repo_is_not_capped(tmp_path):
    lane(tmp_path, ours_open(12), fetched=NOW)
    assert upstream.new_pr_errors(tmp_path, 'someone/else', NOW) == []


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
])
def test_true_reports_pass(tmp_path, text):
    lane(tmp_path, [pr(298), pr(250, 'closed', '2026-10-26T04:07:00Z')])
    assert upstream.report_lint(text, tmp_path) == []


def test_without_any_upstream_lane_the_lint_is_silent(tmp_path):
    assert upstream.report_lint("two PR updates are live on Tao's table", tmp_path) == []
