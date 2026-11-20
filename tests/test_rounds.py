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


def test_the_cli_logs_a_round_and_the_gate_reads_it(tmp_path, capsys):
    d = lane(tmp_path)
    assert rd.main(['--lane', str(d), 'consult', '--source', 'index.md',
                    '--took', 'the PXDesign family']) == 0
    for i in range(3):
        assert rd.main(['--lane', str(d), 'log', '--round', 'R%d' % (41 + i),
                        '--family', 'boltzgen', '--outcome', 'dry', '--spend-usd', '5',
                        '--provider', 'JapanFold']) == 0
    # general, 11-20 (RULE #1): a dry family and a dead end warn; the round may run.
    capsys.readouterr()
    assert rd.main(['--lane', str(d), 'check', '--family', 'boltzgen']) == 0
    assert '[rounds.dry-family] WARNING' in capsys.readouterr().err
    assert rd.main(['--lane', str(d), 'check', '--family', 'pxdesign']) == 0
    assert rd.main(['--lane', str(d), 'close-family', '--family', 'boltzgen',
                    '--reason', 'three dry rounds']) == 0
    capsys.readouterr()
    assert rd.main(['--lane', str(d), 'check', '--family', 'boltzgen']) == 0
    assert '[rounds.dead-end] WARNING' in capsys.readouterr().err
    rows = rd.read(d / rd.ROUNDS)
    assert len(rows) == 3 and rd.spend(rows) == 15.0


def test_a_corrupt_ledger_line_does_not_blind_the_gate(tmp_path):
    d = lane(tmp_path)
    consult(d)
    (d / rd.ROUNDS).write_text('{"not json\n' + '\n'.join(
        json.dumps(dict(utc='2026-11-02T00:00:00Z', round='R%d' % i, family='boltzgen',
                        outcome='dry', spend_usd=1.0)) for i in range(3)) + '\n')
    assert errors(d, 'boltzgen') == ['DRY_FAMILY']


# 11-19: a round must not build on a baseline that no longer reproduces. baseline.py `check` existed
# and nothing called it (planets and c5, see its docstring); the gate now runs it when stale.
DAY = 86400.0


@pytest.fixture(autouse=True)
def _no_launch_host(monkeypatch):
    monkeypatch.delenv('LAUNCH_HOST', raising=False)


def baselines(d, published=1.0, value='1.0', cmd='cat value.txt'):
    """A one-baseline synthetic lane: the baseline reproduces while value.txt holds `published`."""
    (d / 'value.txt').write_text(value + '\n')
    rd.append(d / rd.BASELINES, dict(name='toy-2020', source='fixture', published=published,
                                     cmd=cmd, tolerance=1e-9, timeout=60))


def cached(d, age_days):
    import time as _t
    (d / rd.BASELINE_CACHE).write_text(json.dumps(dict(last_ok_epoch=_t.time() - age_days * DAY)))


def no_subprocess(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('the baseline check must not run')
    monkeypatch.setattr(rd.subprocess, 'Popen', boom)


def test_a_lane_without_baselines_runs_no_check(tmp_path, monkeypatch):
    d = lane(tmp_path)
    consult(d)
    no_subprocess(monkeypatch)
    assert errors(d, 'boltzgen') == []
    assert not (d / rd.BASELINE_CACHE).exists()


def test_a_fresh_baseline_check_is_not_rerun(tmp_path, monkeypatch):
    d = lane(tmp_path)
    consult(d)
    baselines(d, value='9.9')   # would drift, so passing proves the check did not run
    cached(d, 6)
    no_subprocess(monkeypatch)
    assert errors(d, 'boltzgen') == []


def test_a_stale_check_that_passes_allows_the_round_and_refreshes_the_cache(tmp_path):
    d = lane(tmp_path)
    consult(d)
    baselines(d)
    cached(d, 8)
    before = json.loads((d / rd.BASELINE_CACHE).read_text())['last_ok_epoch']
    assert errors(d, 'boltzgen') == []
    after = json.loads((d / rd.BASELINE_CACHE).read_text())
    assert after['last_ok_epoch'] > before + 7 * DAY and after['last_ok_utc']


def test_a_stale_check_that_drifts_refuses_the_round_and_names_the_baseline(tmp_path):
    d = lane(tmp_path)
    consult(d)
    baselines(d, value='1.5')   # the published number no longer comes out
    assert not (d / rd.BASELINE_CACHE).exists(), 'missing counts as stale'
    errs = rd.gate(d, 'boltzgen')[0]
    assert [e.split(':')[0] for e in errs] == ['BASELINE_DRIFT']
    assert 'toy-2020' in errs[0]
    assert not (d / rd.BASELINE_CACHE).exists(), 'a failed check is never cached as a pass'


def test_a_check_that_cannot_finish_refuses_rather_than_passes(tmp_path):
    d = lane(tmp_path)
    baselines(d, cmd='sleep 30; echo 1.0')
    errs = rd.baseline_errors(d, timeout=1)
    assert len(errs) == 1 and 'baseline check could not run' in errs[0]
    assert not (d / rd.BASELINE_CACHE).exists()


def test_the_cli_start_runs_flagged_on_drift(tmp_path):
    """general, 11-20: a drifted baseline no longer refuses the round; the round's row flags it."""
    import subprocess, sys
    d = lane(tmp_path)
    consult(d)
    baselines(d, value='3.0')
    r = subprocess.run([sys.executable, str(ROOT / 'harness/tools/rounds.py'), '--lane', str(d),
                        'start', '--round', 'R1', '--family', 'boltzgen'],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and 'BASELINE_DRIFT' in r.stderr and 'toy-2020' in r.stderr
    row = rd.read(d / rd.ROUNDS)[-1]
    assert row['outcome'] == rd.STARTED and 'toy-2020' in row['baseline_drift']
    assert any(w.startswith('rounds.baseline-drift: ') for w in row['warnings'])


def test_a_lane_with_a_host_runs_its_baseline_check_there(tmp_path, monkeypatch):
    """math declares host = "m5" and its checkers take minutes; the controller is the 16 GB M4."""
    d = lane(tmp_path)
    consult(d)
    baselines(d)
    (d / 'SWEEP.toml').write_text('host = "m5"\n')
    log = tmp_path / 'ssh.log'
    ssh = tmp_path / 'fake-ssh'
    ssh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "{}"\nfor last; do :; done\nexec sh -c "$last"\n'
                   .format(log))
    ssh.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(ssh))
    assert errors(d, 'boltzgen') == []
    argv = log.read_text().splitlines()
    assert 'm5' in argv and 'baseline.py' in argv[-1] and str(d) in argv[-1]
    assert (d / rd.BASELINE_CACHE).exists(), 'the cache stays with the lane on the controller'
