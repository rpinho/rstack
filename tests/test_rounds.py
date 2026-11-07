"""A dry streak changes direction, and the lane reads what we already knew first.

The c5 postmortem (11-06): about 80 rounds, almost all in one method family, "0 selective"
round after round, ~$340 through an external API with ~$80 on seventeen dry rounds in one day.
It changed method only when Ricardo stepped in, and the KB bookmarks had already identified the
better family for that target 38 rounds earlier.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rounds', ROOT / 'harness/tools/rounds.py')
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)


# Every round is now also asserted against the lane's SPEC.json (11-07, postmortem 3: 115 rounds
# against the wrong allele). These tests are about the dry streak and the fingerprint, so they
# declare the minimum honest spec: this fixture lane has no challenge page to pin.
SPEC = json.dumps(dict(schema=1, challenge=None,
                       no_challenge_reason='fixture lane; there is no challenge page to capture',
                       ranking=[{'condition': 'selective hits', 'scored': True}]))


def lane(tmp_path):
    d = tmp_path / 'lanes/c5'
    d.mkdir(parents=True)
    (d / 'SPEC.json').write_text(SPEC)
    return d


def consult(d, utc='2026-11-09T00:00:00Z'):
    """Fresh by default, i.e. newer than the rounds below, so a test that is not about the
    receipt is not also tripping KB_UNREAD. The staleness test sets its own timestamps."""
    rd.append(d / rd.RECEIPTS, dict(utc=utc, sources=['index.md'], took='the better family'))


def rounds(d, n, family='boltzgen', outcome='dry', start=16, utc='2026-11-02T00:00:00Z'):
    for i in range(n):
        rd.append(d / rd.ROUNDS, dict(utc=utc, round='R%d' % (start + i), family=family,
                                      outcome=outcome, spend_usd=5.0, provider='JapanFold'))


def errors(d, family, **kw):
    return [e.split(':')[0] for e in rd.gate(d, family, **kw)[0]]


def test_three_dry_rounds_in_one_family_refuse_a_fourth(tmp_path):
    d = lane(tmp_path)
    consult(d)
    rounds(d, 2)
    assert errors(d, 'boltzgen') == [], 'two dry rounds is not yet a verdict'
    assert 'more closes this family' in rd.gate(d, 'boltzgen')[1][0]
    rounds(d, 1, start=18)
    assert errors(d, 'boltzgen') == ['DRY_FAMILY']
    # The point is to redirect, not to stop: a different family may start at once.
    assert errors(d, 'rfdiffusion') == []


def test_the_refusal_names_the_spend_so_far(tmp_path):
    d = lane(tmp_path)
    consult(d)
    rounds(d, 4)
    message = next(e for e in rd.gate(d, 'boltzgen')[0] if 'DRY_FAMILY' in e)
    assert '$20 spent' in message and 'run a different one' in message


def test_a_closed_family_cannot_be_reopened_without_new_evidence(tmp_path):
    d = lane(tmp_path)
    consult(d)
    rounds(d, 1, family='boltzgen', outcome='selective')
    rd.append(d / rd.DEAD_ENDS, dict(utc='2026-11-03T00:00:00Z', family='boltzgen',
                                     status='closed', reason='17 dry rounds'))
    assert errors(d, 'boltzgen') == ['DEAD_END']
    assert errors(d, 'boltzgen', new_evidence='JapanFold shipped a new sampler') == []


def test_round_one_needs_a_kb_consult_receipt(tmp_path):
    """c5's own account: the KB had the better family 38 rounds before anyone looked."""
    d = lane(tmp_path)
    assert errors(d, 'boltzgen') == ['KB_UNREAD']
    consult(d)
    assert errors(d, 'boltzgen') == []


def test_a_dry_streak_needs_a_fresh_consult_not_an_old_one(tmp_path):
    d = lane(tmp_path)
    consult(d, utc='2026-11-01T00:00:00Z')
    rounds(d, 3, utc='2026-11-02T00:00:00Z')
    # The old receipt predates the streak: that is the reading that did not help.
    assert 'KB_UNREAD' in errors(d, 'rfdiffusion')
    consult(d, utc='2026-11-03T00:00:00Z')
    assert errors(d, 'rfdiffusion') == []


def test_a_crashed_round_does_not_reset_the_streak(tmp_path):
    """A round that failed produced nothing selective either; treating it as a fresh start is
    how seventeen dry rounds look like scattered bad luck."""
    d = lane(tmp_path)
    consult(d)
    rounds(d, 2)
    rounds(d, 1, outcome='failed', start=30)
    assert rd.dry_streak(rd.read(d / rd.ROUNDS)) == 3
    assert errors(d, 'boltzgen') == ['DRY_FAMILY']


def test_a_selective_round_clears_everything(tmp_path):
    d = lane(tmp_path)
    consult(d)
    rounds(d, 5)
    rounds(d, 1, outcome='selective', start=99)
    assert errors(d, 'boltzgen') == [] and rd.dry_streak(rd.read(d / rd.ROUNDS)) == 0


def test_the_cli_logs_a_round_and_the_gate_reads_it(tmp_path):
    d = lane(tmp_path)
    assert rd.main(['--lane', str(d), 'consult', '--source', 'index.md',
                    '--took', 'the PXDesign family']) == 0
    for i in range(3):
        assert rd.main(['--lane', str(d), 'log', '--round', 'R%d' % (41 + i),
                        '--family', 'boltzgen', '--outcome', 'dry', '--spend-usd', '5',
                        '--provider', 'JapanFold']) == 0
    assert rd.main(['--lane', str(d), 'check', '--family', 'boltzgen']) == 2
    assert rd.main(['--lane', str(d), 'check', '--family', 'pxdesign']) == 0
    assert rd.main(['--lane', str(d), 'close-family', '--family', 'boltzgen',
                    '--reason', 'three dry rounds']) == 0
    assert rd.main(['--lane', str(d), 'check', '--family', 'boltzgen']) == 2
    rows = rd.read(d / rd.ROUNDS)
    assert len(rows) == 3 and rd.spend(rows) == 15.0


def test_a_corrupt_ledger_line_does_not_blind_the_gate(tmp_path):
    d = lane(tmp_path)
    consult(d)
    (d / rd.ROUNDS).write_text('{"not json\n' + '\n'.join(
        json.dumps(dict(utc='2026-11-02T00:00:00Z', round='R%d' % i, family='boltzgen',
                        outcome='dry', spend_usd=1.0)) for i in range(3)) + '\n')
    assert errors(d, 'boltzgen') == ['DRY_FAMILY']
