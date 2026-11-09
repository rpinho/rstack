"""Referee verdicts (11-08): refuted vs blocked, refuted claims remembered, planted claims, coverage."""
import json
from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bug_coverage
import bug_verdicts
from test_bughunt import draft, lane, lint, rh_cli, target_verdict  # noqa: F401
from test_outreach import env  # noqa: F401

COMMIT = 'a' * 40
CLAIMS = dict(target='org/tool', commit=COMMIT, hunter=dict(model='h-1', family='hunterfam'), claims=[
    dict(id='B1', file='src/fit.py', function='fit', root_cause='the last bin is dropped when n is odd',
         observed='9 bins', expected='10 bins'),
    dict(id='B2', file='src/io.py', function='read_table', root_cause='a header with spaces shifts every column',
         observed='column 2 holds names', expected='column 1 holds names'),
])


def write_verdict(lane_dir, workdir, judge, model='m', family='f'):
    batch = bug_verdicts.ledger(lane_dir, 'PLANTS.jsonl')[-1]['batch']
    claims = json.loads((Path(workdir) / 'claims.json').read_text())['claims']
    out = []
    for c in claims:
        v = dict(id=c['id'], file=c['file'], function=c['function'], root_cause=c['root_cause'], effect='x')
        v.update(judge(c))
        out.append(v)
    doc = dict(schema=bug_verdicts.SCHEMA, batch=batch, target='org/tool', commit=COMMIT,
               referee=dict(model=model, family=family), claims=out)
    path = Path(workdir) / 'verdict.json'
    path.write_text(json.dumps(doc))
    return path


def honest(c):
    """Runs the code: the real claims hold; a planted one does not match what the code does."""
    real = any(c['file'] == r['file'] and c['function'] == r['function'] and c['observed'] == r['observed']
               and c['root_cause'] == r['root_cause'] for r in CLAIMS['claims'])
    if real:
        return dict(verdict='CONFIRMED', repro='repro/{}/run.py'.format(c['id']))
    return dict(verdict='REFUTED', reason='the code does not behave as claimed here')


@pytest.fixture
def ln(tmp_path):
    d = tmp_path / 'lane'
    d.mkdir()
    return d


def test_the_verdict_schema_is_strict():
    good = dict(schema=bug_verdicts.SCHEMA, batch='b', target='org/tool', commit=COMMIT,
                referee=dict(model='m', family='f'),
                claims=[dict(id='C01', verdict='REFUTED', file='a.py', function='f', root_cause='x y z',
                             effect='none', reason='it returns the right thing')])
    assert bug_verdicts.validate(good) == []
    for change, expect in (
            (dict(verdict='NOT REPRODUCED'), 'split'),
            (dict(verdict='BLOCKED'), 'needs the one fact'),
            (dict(verdict='CONFIRMED', reason=None), 'repro'),
            (dict(reason='no'), 'needs the reason'),
            (dict(surprise=1), 'unknown fields')):
        claim = dict(good['claims'][0], **change)
        claim = {k: v for k, v in claim.items() if v is not None}
        assert any(expect in e for e in bug_verdicts.validate(dict(good, claims=[claim]))), change
    assert bug_verdicts.validate(dict(good, extra=1))


def test_a_honest_referee_is_recorded_and_its_refutations_remembered(ln, tmp_path):
    work = tmp_path / 'ref1'
    batch, real, planted = bug_verdicts.referee_prompt(ln, CLAIMS, work, n_plants=2, rng=random.Random(1))
    assert real == 2 and planted == 2
    prompt = (work / 'PROMPT.md').read_text()
    assert batch in prompt and 'REFUTED' in prompt and 'planted' not in json.dumps(json.loads((work / 'claims.json').read_text()))
    path = write_verdict(ln, work, honest)
    ok, msgs = bug_verdicts.record(ln, path)
    assert ok and '2 of 2 planted caught' in msgs[-1], msgs
    assert bug_verdicts.accepted(path, ln) and len(bug_verdicts.confirmed(path)) == 4 - 2


def test_a_referee_that_confirms_everything_is_rejected_whole(ln, tmp_path):
    work = tmp_path / 'ref'
    bug_verdicts.referee_prompt(ln, CLAIMS, work, n_plants=1, rng=random.Random(2))
    path = write_verdict(ln, work, lambda c: dict(verdict='CONFIRMED', repro='r'), model='yes-man')
    ok, msgs = bug_verdicts.record(ln, path)
    assert not ok and 'REFEREE_FOOLED' in msgs[0]
    assert not bug_verdicts.accepted(path, ln)
    assert 'WARN: fooled' in bug_verdicts.referees(ln)[0]


def test_malformed_and_unplanted_verdicts_are_refused(ln, tmp_path):
    bad = tmp_path / 'verdict.json'
    bad.write_text('{"schema": "x"')
    assert 'VERDICT_MALFORMED' in bug_verdicts.record(ln, bad)[1][0]
    work = tmp_path / 'w'
    work.mkdir()
    (work / 'claims.json').write_text(json.dumps(CLAIMS))
    (ln / 'PLANTS.jsonl').write_text(json.dumps(dict(batch='other', key=[])) + '\n')
    path = write_verdict(ln, work, honest)
    doc = json.loads(path.read_text())
    path.write_text(json.dumps(dict(doc, batch='never-planted')))
    assert 'VERDICT_UNPLANTED' in bug_verdicts.record(ln, path)[1][0]


def test_a_refuted_claim_cannot_be_claimed_again(ln, tmp_path):
    work = tmp_path / 'ref'
    bug_verdicts.referee_prompt(ln, CLAIMS, work, rng=random.Random(3))
    refute_b1 = lambda c: (dict(verdict='REFUTED', reason='odd n keeps every bin', file_sha256='1' * 64)
                           if c['function'] == 'fit' or not honest(c)['verdict'].startswith('CONFIRMED')
                           else dict(verdict='CONFIRMED', repro='r'))
    assert bug_verdicts.record(ln, write_verdict(ln, work, refute_b1))[0]
    again = bug_verdicts.claims_check(ln, CLAIMS)
    assert len(again) == 1 and again[0].startswith('REFUTED_BEFORE: B1')
    with pytest.raises(ValueError, match='REFUTED_BEFORE'):
        bug_verdicts.referee_prompt(ln, CLAIMS, tmp_path / 'ref2')
    changed = dict(CLAIMS, claims=[dict(CLAIMS['claims'][0], file_sha256='2' * 64)])
    assert bug_verdicts.claims_check(ln, changed) == [], 'the source changed'
    fp = bug_verdicts.fingerprint('org/tool', 'src/fit.py', 'fit')
    differs = dict(CLAIMS, claims=[dict(CLAIMS['claims'][0], differs_from=dict(fingerprint=fp,
                   why='a different input path: weights, not the bin count'))])
    assert bug_verdicts.claims_check(ln, differs) == []


def test_blocked_claims_are_kept_as_questions(ln, tmp_path):
    work = tmp_path / 'ref'
    bug_verdicts.referee_prompt(ln, CLAIMS, work, rng=random.Random(4))
    judge = lambda c: (dict(verdict='BLOCKED', needs='which units the published runs used',
                            check='ask the author which config file the paper used') if c['function'] == 'read_table'
                       else honest(c))
    assert bug_verdicts.record(ln, write_verdict(ln, work, judge))[0]
    assert bug_verdicts.ledger(ln, 'BLOCKED.jsonl')[0]['needs'] == 'which units the published runs used'


def test_a_referee_from_the_hunters_family_does_not_count(ln, tmp_path):
    """11-09: a GPT-6 Codex hunter was refereed by GPT-6 and the verdicts were accepted."""
    gpt = dict(CLAIMS, hunter=dict(model='gpt-6.1-codex', family='GPT-6 Codex'))
    bug_verdicts.referee_prompt(ln, gpt, tmp_path / 'a', rng=random.Random(6))
    ok, msgs = bug_verdicts.record(ln, write_verdict(ln, tmp_path / 'a', honest, model='gpt-6.1-sol', family='GPT-6'))
    assert not ok and msgs[0].startswith('REFEREE_SAME_FAMILY')
    assert bug_verdicts.ledger(ln, 'REFEREE.jsonl')[-1]['same_family'] is True
    assert not bug_verdicts.ledger(ln, 'REFUTED.jsonl'), 'a refused file leaves no refutations behind'
    bug_verdicts.referee_prompt(ln, gpt, tmp_path / 'b', rng=random.Random(7))
    ok, _ = bug_verdicts.record(ln, write_verdict(ln, tmp_path / 'b', honest, model='claude-opus-5-5', family='Claude'))
    assert ok


def test_the_hunter_family_is_required_and_compared_by_maker(ln, tmp_path):
    bare = {k: v for k, v in CLAIMS.items() if k != 'hunter'}
    with pytest.raises(ValueError, match='HUNTER_UNDECLARED'):
        bug_verdicts.referee_prompt(ln, bare, tmp_path / 'w')
    bug_verdicts.referee_prompt(ln, bare, tmp_path / 'w', hunter_family='Claude Opus', rng=random.Random(8))
    assert bug_verdicts.ledger(ln, 'PLANTS.jsonl')[-1]['hunter_maker'] == 'anthropic'
    assert 'hunter' not in json.loads((tmp_path / 'w/claims.json').read_text()), 'the referee is not told'
    m = bug_verdicts.maker
    assert m('GPT-5') == m('GPT-6 Codex') == m('o3') == 'openai'
    assert m('Opus') == m('Sonnet 5.5') == m('Fable') == 'anthropic'
    assert m('Gemini') != m('GPT-6') and m('DeepSeek V4') == 'deepseek' and m('Some Lab X') == 'somelabx'


def test_a_batch_from_before_the_family_record_is_flagged_not_refused(ln, tmp_path):
    bug_verdicts.referee_prompt(ln, CLAIMS, tmp_path / 'w', rng=random.Random(9))
    rows = bug_verdicts.ledger(ln, 'PLANTS.jsonl')
    for r in rows:
        for k in ('hunter_family', 'hunter_model', 'hunter_maker'):
            r.pop(k)
    (ln / 'PLANTS.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    ok, msgs = bug_verdicts.record(ln, write_verdict(ln, tmp_path / 'w', honest))
    assert ok and any(x.startswith('REFEREE_FAMILY_UNCHECKED') for x in msgs)


def test_no_plant_possible_is_refused(ln, tmp_path):
    one = dict(CLAIMS, claims=[dict(CLAIMS['claims'][0], observed='same', expected='same')])
    with pytest.raises(ValueError, match='PLANT_IMPOSSIBLE'):
        bug_verdicts.referee_prompt(ln, one, tmp_path / 'w')
    plant = [dict(id='P', file='src/x.py', function='g', root_cause='g divides by the wrong count')]
    assert bug_verdicts.referee_prompt(ln, one, tmp_path / 'w', plants=plant)[2] == 1


def test_coverage_refuses_a_round_with_nothing_new(ln):
    r1 = dict(target='org/tool', commit=COMMIT, round='r1', units=[
        dict(unit='src/fit.py', bug_class='off-by-one', status='candidate'),
        dict(unit='src/io.py', bug_class='parsing', status='deferred')])
    assert bug_coverage.record(ln, r1)[0]
    assert not bug_coverage.status(ln, 'org/tool')['done']
    repeat = dict(r1, round='r2', units=[dict(unit='src/fit.py', bug_class='off-by-one', status='covered')])
    ok, msgs = bug_coverage.record(ln, repeat)
    assert not ok and 'COVERAGE_REPEAT' in msgs[0]
    gapfill = dict(r1, round='r2', units=[dict(unit='src/io.py', bug_class='parsing', status='covered')])
    assert bug_coverage.record(ln, gapfill)[0]
    st = bug_coverage.status(ln, 'org/tool')
    assert st['rounds'] == 2 and st['done'] and not st['deferred']


def test_lint_needs_a_recorded_verdict_and_warns_on_one_pass(lane, tmp_path):
    lane_dir = lane[1]
    target_verdict(lane, 'org/tool')
    work = tmp_path / 'ref'
    bug_verdicts.referee_prompt(lane_dir, CLAIMS, work, rng=random.Random(5))
    path = write_verdict(lane_dir, work, honest)
    ident, _ = draft(lane, target='org/tool', recheck=str(work))
    out = lint(lane, ident)[1]
    assert 'VERDICT_UNRECORDED' in out and 'COVERAGE_UNRECORDED' in out
    assert bug_verdicts.record(lane_dir, path)[0]
    assert 'VERDICT_UNRECORDED' not in lint(lane, ident)[1]


def test_the_cli(lane, tmp_path):
    root = lane[0]
    claims = tmp_path / 'claims.json'
    claims.write_text(json.dumps(CLAIMS))
    rc, out, _ = rh_cli(lane, 'bughunt', 'claims-check', 'test', str(claims))
    assert rc == 0 and out.startswith('PASS')
    rc, out, _ = rh_cli(lane, 'bughunt', 'referee-prompt', 'test', str(claims), str(tmp_path / 'ref'))
    assert rc == 0 and (tmp_path / 'ref/PROMPT.md').is_file()
    rc, out, _ = rh_cli(lane, 'bughunt', 'referees', 'test')
    assert rc == 0
    cov = tmp_path / 'cov.json'
    cov.write_text(json.dumps(dict(target='org/tool', commit=COMMIT, round='r1',
                                   units=[dict(unit='a.py', bug_class='x', status='covered')])))
    assert rh_cli(lane, 'bughunt', 'coverage', 'test', 'record', str(cov))[0] == 0
    rc, out, _ = rh_cli(lane, 'bughunt', 'coverage', 'test', 'show', 'org/tool')
    assert rc == 0 and '1 rounds' in out
