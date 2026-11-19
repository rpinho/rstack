"""11-19 Ricardo: rank by everyday delegated work first; the bench is a second check and never ranks."""
import importlib.util
import json

import pytest
from pathlib import Path

spec = importlib.util.spec_from_file_location('model_roles', Path(__file__).with_name('model-roles.py'))
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)


def ev(**models):
    return {'batch': {m: dict(n=n, k=k, days={'2026-11-18', '2026-11-19'}) for m, (n, k) in models.items()}}


def test_models_with_everyday_data_rank_above_every_n_under_5_model_by_their_rate():
    sol, opus, terra = 'openai/gpt-6.2-sol', 'anthropic/claude-opus-5.5', 'openai/gpt-6.1-terra'
    order, _ = mr.rank('batch', ev(**{sol: (4, 4), opus: (100, 91), terra: (20, 12)}))
    # Opus and Terra have data (n>=5) and lead, best rate first; Sol, the first seed, has n<5 and follows.
    assert order[:3] == [opus, terra, sol]


def test_a_perfect_n_under_5_record_does_not_outrank_a_weaker_record_with_data():
    sol, sonnet = 'openai/gpt-6.2-sol', 'anthropic/claude-sonnet-5.5'
    order, _ = mr.rank('batch', ev(**{sol: (4, 4), sonnet: (5, 2)}))
    assert order.index(sonnet) < order.index(sol)


def test_without_everyday_data_the_seed_order_stands():
    order, _ = mr.rank('batch', {})
    assert order[:len(mr.SEED['batch'])] == mr.SEED['batch']


def test_bench_rows_never_rank_and_show_in_their_own_column(tmp_path, monkeypatch):
    ledger = tmp_path / 'ledger.jsonl'
    flash = mr.canon('gemini-3.8-flash-low')
    rows = [mr.obs('receipt-review', 'plant-%d' % i, flash, 'batch', 'held', '2026-11-19', ['fixture'], 'plants')
            for i in range(8)]
    rows = [dict(r, source='receipt-review') for r in rows]
    rows += [mr.obs('receipt-result', 'job-%d' % i, 'anthropic/claude-opus-5.5', 'batch',
                    'held' if i < 5 else 'partial', '2026-11-19', ['fixture'], 'everyday') for i in range(6)]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(mr, 'LEDGER', ledger)
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    assert flash not in mr.evidence()['batch'] and mr.bench_evidence()['batch'][flash]['n'] == 8
    data = mr.recompute(write=False)
    assert data['roles']['batch'][0] == 'claude-opus-5-5'
    assert data['evidence']['batch']['claude-opus-5-5']['rate'] == round(5.5 / 6, 3)  # a partial counts half
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    text = page.read_text()
    assert '| Role | Model | Routing order | Everyday passed | Everyday n | Bench passed | Date |' in text
    assert '| batch | claude-opus-5-5 | 1 | 0.917 | 6 |' in text
    assert '| batch | gemini-3.8-flash-low | ' in text and '| n<5 | 0 | 1.0 |' in text


def test_gemini_4_low_and_medium_are_both_candidates_until_real_work_decides():
    for name in ('neon', 'argon', 'hydrogen'):
        for tier in ('low', 'medium'):
            assert mr.served_model('google/gemini-4-%s-%s' % (name, tier))
            assert 'google/gemini-4-%s-%s' % (name, tier) in mr.CANDIDATES['review']


def test_a_bench_row_cannot_move_a_rank(tmp_path, monkeypatch):
    # Plants, known-answer reproductions and matched mini-tasks are smoke tests that a route works.
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    ledger = tmp_path / 'ledger.jsonl'
    everyday = [mr.obs('receipt-result', 'job-%d' % i, 'anthropic/claude-opus-5.5', 'batch', 'held', '2026-11-19',
                       ['fixture'], 'everyday') for i in range(6)]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in everyday))
    monkeypatch.setattr(mr, 'LEDGER', ledger)
    before = mr.recompute(write=False)
    hydrogen = mr.canon('gemini-4-hydrogen-low')
    bench = [dict(mr.obs('receipt-review', 'plant-%d' % i, hydrogen, role, 'held', '2026-11-19', ['fixture'], 'plants'),
                  source='receipt-review') for i in range(50) for role in mr.ROLES]
    bench += [dict(mr.obs('known-answer', 'repro-%d' % i, 'anthropic/claude-opus-5.5', 'batch', 'overturned',
                          '2026-11-19', ['fixture'], 'bench'), bench=True) for i in range(50)]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in everyday + bench))
    after = mr.recompute(write=False)
    assert after['roles'] == before['roles'] and after['evidence'] == before['evidence']
    assert after['bench']['batch']['gemini-4-hydrogen-low']['n'] == 50


def test_no_role_serves_grok_4_7_over_4_6(monkeypatch):
    newer = mr.canon('x-ai/grok-4.7')
    monkeypatch.setattr(mr, 'evidence', lambda: {r: {newer: dict(n=50, k=50, days={'a', 'b'})} for r in mr.ROLES})
    monkeypatch.setattr(mr, 'bench_evidence', lambda: {})
    data = mr.recompute(write=False)
    assert all('grok' not in m for order in data['roles'].values() for m in order)


def sol_ledger(tmp_path, monkeypatch, old_n, new_n, new_held=None):
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    ledger = tmp_path / 'ledger.jsonl'
    rows = [mr.obs('receipt-result', 'old-%d' % i, 'openai/gpt-6.1-sol', 'batch', 'held', '2026-11-1%d' % (i % 9),
                   ['fixture'], 'everyday') for i in range(old_n)]
    held = new_n if new_held is None else new_held
    rows += [mr.obs('receipt-result', 'new-%d' % i, 'openai/gpt-6.2-sol', 'batch', 'held' if i < held else 'overturned',
                    '2026-11-19', ['fixture'], 'everyday') for i in range(new_n)]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(mr, 'LEDGER', ledger)
    return mr.recompute(write=False)


def test_a_successor_ranks_on_its_predecessors_record_while_its_own_n_is_smaller(tmp_path, monkeypatch):
    # Ricardo 11-19: "6.2 should inherit the scores of 6.1 in the rank until we get a larger sample size."
    data = sol_ledger(tmp_path, monkeypatch, 25, 3, new_held=0)
    assert 'gpt-6.1-sol' not in data['roles']['batch'] and data['roles']['batch'][0] == 'gpt-6.2-sol'
    row = data['evidence']['batch']['gpt-6.2-sol']
    assert row['n'] == 3 and row['inherited'] == {'from': 'gpt-6.1-sol', 'n': 25, 'rate': 1.0}
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    text = page.read_text()
    assert '| batch | gpt-6.2-sol | 1 | 1.0 | inherited from gpt-6.1-sol (n=25); own n=3 |' in text
    assert '| batch | gpt-6.1-sol | - | 1.0 | 25 |' in text   # historical: visible, not routed
    assert mr.bootstrap(page)['roles']['batch'][0] == 'gpt-6.2-sol'


def test_the_inheritance_drops_when_its_own_n_reaches_the_predecessors(tmp_path, monkeypatch):
    data = sol_ledger(tmp_path, monkeypatch, 6, 6, new_held=3)
    row = data['evidence']['batch']['gpt-6.2-sol']
    assert 'inherited' not in row and (row['n'], row['rate']) == (6, 0.5)
    # ranked on its own record now: a seed with no data does not pass it, and its 0.5 is what is shown
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    assert '| batch | gpt-6.2-sol | 1 | 0.5 | 6 |' in page.read_text()


def test_there_is_no_inheritance_across_families():
    with pytest.raises(ValueError, match='across families'):
        mr.check_inherits({'anthropic/claude-sonnet-5.5': 'openai/gpt-6.1-sol'})
    e = {'openai/gpt-6.1-sol': {'n': 25, 'k': 25}}
    assert mr.effective('anthropic/claude-sonnet-5.5', e) == (0, 0, None)
    assert mr.effective('openai/gpt-6.2-sol', e) == (25, 25, 'openai/gpt-6.1-sol')
