"""11-20: cost per PASSED everyday task is display and tie-break only; missing sources give '-' and never raise."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jc, mr = load('job_cost', 'job_cost.py'), load('model_roles', 'model-roles.py')
T0 = dt.datetime(2026, 11, 20, 10, 0, tzinfo=dt.timezone.utc).timestamp()
RESET = '2026-11-23T02:59:59+00:00'
SONNET = 'claude-sonnet-5-5'


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()


def world(tmp_path, jobs, usage):
    """jobs: [(name, executor, start, end, grade)]; usage: [(time, percent)] for claude."""
    receipts, state = tmp_path / 'receipts', tmp_path / 'state'
    (state / 'usage').mkdir(parents=True)
    receipts.mkdir()
    (state / 'usage' / 'claude-history.jsonl').write_text(
        ''.join(json.dumps(dict(at=t, resets_at=RESET, weekly_percent=p)) + '\n' for t, p in usage))
    grades = []
    for name, executor, start, end, grade in jobs:
        (receipts / (name + '.log.selection.json')).write_text(
            json.dumps(dict(job=name, executor=executor, utc=iso(start))))
        log = receipts / (name + '.log')
        log.write_text('x')
        os.utime(log, (end, end))
        grades.append(dict(id='grade-' + name, job=name, model=SONNET, role='batch', grade=grade,
                           source_kind='everyday'))
    (receipts / 'everyday-grades.jsonl').write_text(''.join(json.dumps(g) + '\n' for g in grades))
    return receipts, state


def five_jobs(tmp_path, grades, extra=()):
    # Job i runs [T0+i*3600, +600]; usage rises 1 point across each job.
    jobs = [('j%d' % i, 'claude', T0 + i * 3600, T0 + i * 3600 + 600, g) for i, g in enumerate(grades)]
    usage = [(t, 10 + i + d) for i in range(len(grades)) for t, d in ((T0 + i * 3600 - 60, 0), (T0 + i * 3600 + 660, 1))]
    return world(tmp_path, jobs + list(extra), usage)


def test_cost_per_pass_is_total_cost_over_passes_once_five_tasks_have_a_cost(tmp_path):
    receipts, state = five_jobs(tmp_path, ['pass', 'pass', 'fail', 'partial', 'pass'])
    got = jc.per_pass(receipts, mr.canon, state)[('batch', mr.canon(SONNET))]
    # a failed or partial task still cost something: 5 points over 3 passes
    assert (got['n'], got['passes'], got['pct'], got['per_pass']) == (5, 3, 5.0, round(5 / 3, 3))


def test_under_five_costed_tasks_shows_nothing(tmp_path):
    receipts, state = five_jobs(tmp_path, ['pass'] * 4)
    assert jc.per_pass(receipts, mr.canon, state)[('batch', mr.canon(SONNET))]['per_pass'] is None


def test_overlapping_jobs_on_one_executor_are_shared_and_left_out(tmp_path):
    extra = [('over', 'claude', T0 + 100, T0 + 300, 'pass')]            # overlaps j0
    receipts, state = five_jobs(tmp_path, ['pass'] * 6, extra)
    costs = jc.job_costs(receipts, state)
    assert costs['j0'] == 'shared' and costs['over'] == 'shared' and costs['j1'] == 1.0
    assert jc.per_pass(receipts, mr.canon, state)[('batch', mr.canon(SONNET))]['n'] == 5


def test_stale_missing_or_agy_sources_give_no_cost_and_never_raise(tmp_path):
    receipts, state = five_jobs(tmp_path, ['pass'] * 5)
    (state / 'usage' / 'claude-history.jsonl').write_text('not json\n')
    assert jc.per_pass(receipts, mr.canon, state) == {}
    assert jc.per_pass(tmp_path / 'nowhere', mr.canon, tmp_path / 'nostate') == {}
    assert jc.per_pass(None, mr.canon) == {}
    receipts, state = world(tmp_path / 'agy', [('a', 'agy', T0, T0 + 60, 'pass')], [(T0 - 1, 1), (T0 + 61, 2)])
    assert jc.job_costs(receipts, state) == {'a': None}


def test_retracted_grades_and_other_weekly_windows_do_not_count(tmp_path):
    receipts, state = five_jobs(tmp_path, ['pass'] * 5)
    with open(receipts / 'everyday-grades.jsonl', 'a') as f:
        f.write(json.dumps(dict(id='grade-j0', source_kind='everyday', grade='retracted')) + '\n')
    assert jc.per_pass(receipts, mr.canon, state)[('batch', mr.canon(SONNET))]['n'] == 4
    path = state / 'usage' / 'claude-history.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]['resets_at'] = '2026-11-30T00:00:00+00:00'        # the last reading is from a new week: no delta
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    assert jc.job_costs(receipts, state)['j4'] is None


def test_cost_only_breaks_ties_and_never_outranks_a_better_record():
    opus, sonnet, terra = 'anthropic/claude-opus-5.5', 'anthropic/claude-sonnet-5.5', 'openai/gpt-6.1-terra'
    ev = {'batch': {m: dict(n=10, k=k, days={'a', 'b'}) for m, k in ((opus, 8), (sonnet, 8), (terra, 9))}}
    assert mr.rank('batch', ev, {opus: 0.5, sonnet: 2.0})[0][:3] == [terra, opus, sonnet]   # tie: cheaper first
    assert mr.rank('batch', ev, {sonnet: 0.5, opus: 2.0})[0][:3] == [terra, sonnet, opus]
    assert mr.rank('batch', ev, {sonnet: 0.5})[0][:3] == [terra, sonnet, opus]               # no figure sorts last
    assert mr.rank('batch', ev, {opus: 9.0, sonnet: 0.1, terra: 99.0})[0][0] == terra         # never the rank


def test_the_leaderboard_shows_the_cost_column_and_a_dash_without_it(tmp_path):
    data = dict(updated='2026-11-20T00:00:00+00:00', roles={'batch': [SONNET, 'claude-opus-5-5']},
                evidence={'batch': {SONNET: dict(n=6, rate=0.9), 'claude-opus-5-5': dict(n=6, rate=0.9)}},
                bench={}, cost={'batch': {SONNET: dict(n=6, passes=5, pct_per_pass=1.234)}})
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    text = page.read_text()
    assert '| Cost per pass | Date |' in text
    assert '| batch | claude-sonnet-5-5 | 1 | 0.9 | 6 | - | 1.23% wk | 2026-11-20 |' in text
    assert '| batch | claude-opus-5-5 | 2 | 0.9 | 6 | - | - | 2026-11-20 |' in text
    page.write_text(text.replace('2026-11-20', '2026-11-19'))
    mr.public(dict(data, cost={}), page)                       # a rerun keeps the older day's rows
    assert '| 1.23% wk | 2026-11-19 |' in page.read_text()
