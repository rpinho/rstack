"""The round gate: a paid round is admitted by the ledger, not by the lane's own judgement.

Ricardo, 11-07, after c5 repeated the 11-06 failure in its own words: "66 identical BoltzGen
rounds. Same generator, same params, same scorer. Mechanical repetition, no variation." Nothing
had beaten v25 since 11-05 and it had untried generators the whole time.

The rule was not missing. `harness/tools/rounds.py` has refused a repeated dry family, a reopened
dead end and an unread KB since the first c5 postmortem, `lane_yield`'s DRY_STREAK binds on every
lane including report_only ones, and ~/.config/lane-yield.json already pointed every lane at a
`rounds` glob. What was missing was any row: no lane had a ROUNDS.jsonl, nothing called `check`
before a round and nothing called `log` after one, so every check read an empty ledger and found
nothing to object to.

So these tests are about the two things that close that: the launcher calls the gate, which makes
the write unavoidable, and the fingerprint is mechanical, so a lane cannot relabel its way past it.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / 'tools/launch.sh'
ROUNDS = REPO / 'harness/tools/rounds.py'
PARAMS = '{"length": [60, 80], "n": 100}'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rounds = load('rounds_tool', ROUNDS)
lane_yield = load('lane_yield_tool', REPO / 'harness/tools/lane-yield/lane_yield.py')


def cli(lane, *args):
    return subprocess.run([sys.executable, str(ROUNDS), '--lane', str(lane), *args],
                          capture_output=True, text=True, timeout=60)


def opened(lane, number, generator='BoltzGen', params=PARAMS, scorer='ipae', family='boltzgen'):
    """Open and close one dry round, the way a lane that is doing the bookkeeping would."""
    assert cli(lane, 'start', '--round', number, '--family', family, '--generator', generator,
               '--params', params, '--scorer', scorer).returncode == 0
    assert cli(lane, 'log', '--round', number, '--family', family, '--outcome', 'dry',
               '--generator', generator, '--params', params, '--scorer', scorer).returncode == 0


# Every round is now also asserted against the lane's SPEC.json (11-07, postmortem 3: 115 rounds
# against the wrong allele). These tests are about the dry streak and the fingerprint, so they
# declare the minimum honest spec: this fixture lane has no challenge page to pin.
SPEC = json.dumps(dict(schema=1, challenge=None,
                       no_challenge_reason='fixture lane; there is no challenge page to capture',
                       ranking=[{'condition': 'selective hits', 'scored': True}]))


@pytest.fixture
def lane(tmp_path):
    d = tmp_path / 'lanes' / 'c5'
    d.mkdir(parents=True)
    (d / 'SPEC.json').write_text(SPEC)
    # Round 1 needs a KB consult receipt; that rule predates this change and is not what is
    # under test here, so satisfy it once.
    assert cli(d, 'consult', '--source', 'index.md', '--took', 'the BoltzGen baseline').returncode == 0
    return d


def test_the_same_knobs_under_a_new_family_name_are_still_refused(lane):
    """c5's hole. `family` is a label the lane picks, and a lane sure it is varying enough will
    keep picking a new one. The fingerprint is computed from what the round does."""
    opened(lane, 'R1')
    again = cli(lane, 'start', '--round', 'R2', '--family', 'boltzgen_v2_retuned',
                '--generator', 'BoltzGen', '--params', '{"n": 100, "length": [60, 80]}',
                '--scorer', 'ipae')
    assert again.returncode == 2
    assert 'REPEAT' in again.stderr and 'R1' in again.stderr
    # Refused means not recorded: a refused round must not pad the ledger it was judged against.
    assert [r['round'] for r in rounds.read(lane / 'ROUNDS.jsonl')] == ['R1', 'R1']


def test_param_order_is_not_a_variation_but_a_changed_value_is(lane):
    opened(lane, 'R1')
    assert cli(lane, 'start', '--round', 'R2', '--family', 'boltzgen', '--generator', 'BoltzGen',
               '--params', '{"length": [60, 80], "n": 150}', '--scorer', 'ipae').returncode == 0


def test_a_stated_hypothesis_lets_a_repeat_through(lane):
    """The gate redirects, it does not halt. Repeating a method on purpose is allowed when the
    lane says what is different and what it would show, which is the thing that was missing."""
    opened(lane, 'R1')
    assert cli(lane, 'start', '--round', 'R2', '--family', 'boltzgen', '--generator', 'BoltzGen',
               '--params', PARAMS, '--scorer', 'ipae',
               '--hypothesis', 'same knobs, new target set, to separate target from method').returncode == 0


def test_a_round_cannot_start_while_the_last_one_has_no_outcome(lane):
    """What turns logging from a courtesy into a precondition: skipping it blocks the next round
    instead of quietly blinding every check that reads the ledger."""
    assert cli(lane, 'start', '--round', 'R1', '--family', 'boltzgen', '--generator', 'BoltzGen',
               '--params', PARAMS, '--scorer', 'ipae').returncode == 0
    blocked = cli(lane, 'start', '--round', 'R2', '--family', 'proteina',
                  '--generator', 'RFD4-Proteina', '--params', PARAMS, '--scorer', 'ipae')
    assert blocked.returncode == 2
    assert 'UNCLOSED' in blocked.stderr and 'R1' in blocked.stderr


def test_a_different_generator_proceeds(lane):
    opened(lane, 'R1')
    assert cli(lane, 'start', '--round', 'R2', '--family', 'proteina',
               '--generator', 'RFD4-Proteina', '--params', PARAMS, '--scorer', 'ipae').returncode == 0


def test_a_lane_that_cannot_name_its_knobs_is_not_told_its_rounds_look_alike(lane):
    """An empty fingerprint is never compared. Otherwise every round of a lane that does not pass
    generator/params/scorer would collide with every other and the gate would refuse everything,
    which is how a guard gets switched off."""
    assert rounds.fingerprint() == ''
    assert cli(lane, 'start', '--round', 'R1', '--family', 'a').returncode == 0
    assert cli(lane, 'log', '--round', 'R1', '--family', 'a', '--outcome', 'dry').returncode == 0
    assert cli(lane, 'start', '--round', 'R2', '--family', 'a').returncode == 0


def test_an_open_round_counts_as_not_selective_but_only_once(lane):
    """`start` writes a row and the lane logs the outcome later, so a single round appears twice
    in the file. Counted naively, a streak reads as double its length and DRY_STREAK fires early."""
    opened(lane, 'R1')
    opened(lane, 'R2', generator='RFD4-Proteina', family='proteina')
    rows = rounds.read(lane / 'ROUNDS.jsonl')
    assert len(rows) == 4                       # two rows per round, on disk
    assert rounds.dry_streak(rows) == 2         # but two rounds in the streak
    assert lane_yield.dry_tail(rows)[0] == 2    # and the yield test agrees


def test_a_selective_round_clears_the_streak(lane):
    opened(lane, 'R1')
    assert cli(lane, 'start', '--round', 'R2', '--family', 'proteina', '--generator',
               'RFD4-Proteina', '--params', PARAMS, '--scorer', 'ipae').returncode == 0
    assert cli(lane, 'log', '--round', 'R2', '--family', 'proteina', '--outcome', 'selective',
               '--generator', 'RFD4-Proteina', '--params', PARAMS, '--scorer', 'ipae').returncode == 0
    assert rounds.dry_streak(rounds.read(lane / 'ROUNDS.jsonl')) == 0


# --- the launcher is what makes the write unavoidable ------------------------------------------

def launcher(tmp_path, lane_name='c5', env_extra=None):
    jobs = tmp_path / 'jobs'
    jobs.mkdir(exist_ok=True)
    (jobs / (lane_name + '-job.md')).write_text('Find a design that beats v25, or say plainly that you did not.')
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    ran = tmp_path / 'executor-ran'
    fake = tmp_path / 'fake-cli'
    fake.write_text('#!' + sys.executable + '\nimport os, sys\n'
                    'open(os.environ["EXECUTOR_RAN"], "a").write("ran\\n")\n'
                    'print(\'{"is_error":false,"subtype":"success","result":"fixture"}\')\n')
    fake.chmod(0o755)
    root = tmp_path / 'runtime'
    (root / 'lanes' / lane_name).mkdir(parents=True, exist_ok=True)
    (root / 'lanes' / lane_name / 'SPEC.json').write_text(SPEC)
    # Round 1 needs a KB consult receipt. That rule predates this change and the launcher tests
    # are about the gate being called at all, so satisfy it once here.
    cli(root / 'lanes' / lane_name, 'consult', '--source', 'index.md', '--took', 'the baseline')
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(root),
               EXECUTOR_RAN=str(ran))
    for key in ('LAUNCH_RESUME', 'SPEC_OVER_CAP', 'LAUNCH_HOST', 'LAUNCH_ROUND'):
        env.pop(key, None)
    env.update(env_extra or {})
    proc = subprocess.run(['zsh', str(LAUNCH), lane_name + '-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=120)
    return proc, root / 'lanes' / lane_name / 'ROUNDS.jsonl', ran


def test_a_job_without_a_round_is_unchanged(tmp_path):
    """The gate is opt-in per job. If it had become unconditional, every existing job in every
    lane would start refusing at once."""
    proc, ledger, ran = launcher(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert not ledger.exists()
    assert ran.exists()


def test_the_launcher_opens_the_round_in_the_lane_ledger(tmp_path):
    proc, ledger, ran = launcher(tmp_path, env_extra=dict(
        LAUNCH_ROUND='R1', LAUNCH_FAMILY='boltzgen', LAUNCH_GENERATOR='BoltzGen',
        LAUNCH_PARAMS=PARAMS, LAUNCH_SCORER='ipae'))
    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    assert [r['round'] for r in rows] == ['R1']
    assert rows[0]['fingerprint'] == rounds.fingerprint('BoltzGen', PARAMS, 'ipae')
    assert ran.exists()


def test_the_launcher_refuses_a_repeat_before_spending_anything(tmp_path):
    """The refusal has to come before the executor runs, or the guard only reports a round that
    has already been paid for."""
    first = dict(LAUNCH_ROUND='R1', LAUNCH_FAMILY='boltzgen', LAUNCH_GENERATOR='BoltzGen',
                 LAUNCH_PARAMS=PARAMS, LAUNCH_SCORER='ipae')
    proc, ledger, ran = launcher(tmp_path, env_extra=first)
    assert proc.returncode == 0, proc.stderr
    lane_dir = ledger.parent
    assert cli(lane_dir, 'log', '--round', 'R1', '--family', 'boltzgen', '--outcome', 'dry',
               '--generator', 'BoltzGen', '--params', PARAMS, '--scorer', 'ipae').returncode == 0
    ran.unlink()
    again = dict(first, LAUNCH_ROUND='R2', LAUNCH_FAMILY='boltzgen_but_surely_different')
    proc2, _, ran2 = launcher(tmp_path, env_extra=again)
    assert proc2.returncode == 78, proc2.stdout + proc2.stderr
    assert 'REPEAT' in proc2.stderr
    assert not ran2.exists()           # nothing was spent
    assert [json.loads(l)['round'] for l in ledger.read_text().splitlines() if l.strip()] \
        == ['R1', 'R1']                # and the refused round was not recorded
