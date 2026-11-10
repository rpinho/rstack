import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rh
import verification as v
from verification_fixtures import synthetic_lean, l1, reseal_lean, save_json
import test_rh


def assert_failure(row, root, message):
    errors = v.validate_row(row, root)
    assert errors and message in errors[0], errors


def add_axiom(root, row, listed=True):
    with (root / 'ToyProof.lean').open('a') as f:
        f.write('\naxiom Test.inherited : True\n')
    p = root / 'receipts/axioms.txt'
    p.write_text(p.read_text().replace('[propext, Quot.sound]', '[propext, Quot.sound, Test.inherited]', 1))
    p = root / 'receipts/clean-build.log'
    p.write_text(p.read_text().replace('[propext, Quot.sound]', '[propext, Quot.sound, Test.inherited]', 1))
    if listed:
        (root / 'AXIOMS.md').write_text('# Axioms\n\n| Axiom | Citation |\n| --- | --- |\n| `Test.inherited` | https://example.org/paper-v1, Theorem 3.2 |\n')
    return reseal_lean(root, row)


def test_synthetic_lean_l2_replay(tmp_path):
    row = synthetic_lean(tmp_path)
    before = {p.relative_to(tmp_path): v.sha256(p) for p in tmp_path.rglob('*') if p.is_file()}
    assert v.validate_row(row, tmp_path) == []
    assert len(list(tmp_path.glob('ToyProof/*.lean'))) == 4
    assert len(row['main_theorems']) == 4
    row['verification'] = 'L3'
    # Synthetic receipts test the validator, not a real proof or whole bound.
    assert v.validate_row(row, tmp_path) == []
    assert before == {p.relative_to(tmp_path): v.sha256(p) for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('word', ['sorry', 'admit', 'sorryAx'])
def test_forbidden_source_even_with_matching_hash(tmp_path, word):
    row = synthetic_lean(tmp_path)
    with (tmp_path / 'ToyProof.lean').open('a') as f:
        f.write('\nexample : True := ' + word + '\n')
    reseal_lean(tmp_path, row)
    assert_failure(row, tmp_path, 'forbidden ' + word)


@pytest.mark.parametrize('name', ['receipts/axioms.txt', 'receipts/clean-build.log'])
def test_forbidden_receipt(tmp_path, name):
    row = synthetic_lean(tmp_path)
    with (tmp_path / name).open('a') as f:
        f.write('\nsorryAx\n')
    reseal_lean(tmp_path, row)
    assert_failure(row, tmp_path, 'forbidden sorryAx')


def test_unlisted_axiom(tmp_path):
    row = add_axiom(tmp_path, synthetic_lean(tmp_path), listed=False)
    assert_failure(row, tmp_path, 'unlisted')


def test_listed_axiom_l2_and_l3(tmp_path):
    row = add_axiom(tmp_path, synthetic_lean(tmp_path))
    assert v.validate_row(row, tmp_path) == []
    row['verification'] = 'L3'
    assert_failure(row, tmp_path, 'L3 requires an empty')


def test_l3_refuses_even_unused_listed_axiom(tmp_path):
    row = synthetic_lean(tmp_path)
    (tmp_path / 'AXIOMS.md').write_text('| Axiom | Citation |\n| --- | --- |\n| `Unused.inherited` | https://example.org/paper, Lemma 1 |\n')
    reseal_lean(tmp_path, row)
    row['verification'] = 'L3'
    assert_failure(row, tmp_path, 'L3 requires an empty')


def test_axiom_requires_citation_and_locator(tmp_path):
    row = add_axiom(tmp_path, synthetic_lean(tmp_path))
    p = tmp_path / 'AXIOMS.md'
    p.write_text(p.read_text().replace('https://example.org/paper-v1, Theorem 3.2', 'trust me'))
    reseal_lean(tmp_path, row)
    assert_failure(row, tmp_path, 'needs an exact citation')


def test_trimmed_axiom_receipt_cannot_contradict_build(tmp_path):
    row = add_axiom(tmp_path, synthetic_lean(tmp_path))
    p = tmp_path / 'receipts/axioms.txt'
    p.write_text(p.read_text().replace(', Test.inherited', ''))
    reseal_lean(tmp_path, row)
    assert_failure(row, tmp_path, 'conflicting axiom receipts')


def test_unexplained_native_decide(tmp_path):
    row = synthetic_lean(tmp_path)
    with (tmp_path / 'ToyProof.lean').open('a') as f:
        f.write('\nexample : True := by native_decide\n')
    reseal_lean(tmp_path, row)
    # A denial of native evaluation is not an explanation of its trust boundary.
    assert_failure(row, tmp_path, 'native_decide requires')
    with (tmp_path / 'AXIOMS.md').open('a') as f:
        f.write('\nnative_decide trusts compiled evaluation beyond the kernel; this extra trust is disclosed.\n')
    reseal_lean(tmp_path, row)
    assert v.validate_row(row, tmp_path) == []


@pytest.mark.parametrize('change,message', [
    ('missing', 'missing'), ('exit', 'exit_code 0'), ('source', 'source hash mismatch'),
    ('log', 'hash mismatch'), ('axioms', 'hash mismatch'), ('doc', 'hash mismatch'),
    ('pin', 'pin a Lean'), ('manifest', 'pinned git'), ('main', 'each main_theorems'),
])
def test_lean_receipt_failures(tmp_path, change, message):
    row = synthetic_lean(tmp_path)
    if change == 'missing':
        row.pop('build_receipt')
    elif change == 'exit':
        p = tmp_path / 'receipts/build.json'
        data = json.loads(p.read_text())
        data['exit_code'] = 1
        row['build_receipt_sha256'] = save_json(p, data)
    elif change == 'source':
        with (tmp_path / 'ToyProof.lean').open('a') as f:
            f.write('\n-- changed\n')
    elif change in ('log', 'axioms', 'doc'):
        p = tmp_path / {'log': 'receipts/clean-build.log', 'axioms': 'receipts/axioms.txt', 'doc': 'AXIOMS.md'}[change]
        p.write_text(p.read_text() + '\nchanged\n')
    elif change == 'pin':
        (tmp_path / 'lean-toolchain').write_text('leanprover/lean4:stable\n')
    elif change == 'manifest':
        p = tmp_path / 'lake-manifest.json'
        data = json.loads(p.read_text())
        data['packages'][0]['rev'] = 'main'
        save_json(p, data)
    else:
        row['main_theorems'] = ['Missing.theorem']
    assert_failure(row, tmp_path, message)


def test_l1_replays_at_120_and_uses_receipt_above(tmp_path):
    row = l1(tmp_path, seconds=120)
    with patch.object(v, '_run_checker', return_value=row['expected_output_sha256']) as replay:
        assert v.validate_row(row, tmp_path) == []
        replay.assert_called_once()
        row['checker_max_seconds'] = 121
        assert v.validate_row(row, tmp_path) == []
        assert replay.call_count == 1


def test_l1_real_read_only_replay(tmp_path):
    row = l1(tmp_path)
    before = {p.name: v.sha256(p) for p in tmp_path.iterdir()}
    assert v.validate_row(row, tmp_path) == []
    assert before == {p.name: v.sha256(p) for p in tmp_path.iterdir()}


def test_l1_same_author(tmp_path):
    row = l1(tmp_path)
    row['checker_author'] = '  MODEL-PRODUCER  '
    assert_failure(row, tmp_path, 'must differ')


@pytest.mark.parametrize('change,message', [
    ('certificate', 'hash mismatch'), ('output', 'hash mismatch'), ('checker', 'hash mismatch'),
    ('receipt', 'hash mismatch'), ('expected', 'hash mismatch'), ('missing', 'producer_author'),
])
def test_l1_hashes_and_provenance(tmp_path, change, message):
    row = l1(tmp_path, seconds=121)
    if change in ('certificate', 'output', 'checker'):
        (tmp_path / {'certificate': 'certificate.txt', 'output': 'output.txt', 'checker': 'checker.py'}[change]).write_text('changed\n')
    elif change == 'receipt':
        row['run_receipt_sha256'] = '0' * 64
    elif change == 'expected':
        row['expected_output_sha256'] = '0' * 64
    else:
        row.pop('producer_author')
    assert_failure(row, tmp_path, message)


def test_l1_replay_failure_and_timeout(tmp_path):
    row = l1(tmp_path)
    with patch.object(v, '_run_checker', return_value='0' * 64):
        assert_failure(row, tmp_path, 'replay output hash mismatch')
    with pytest.raises(ValueError, match='timed out'):
        v._run_checker([row['checker'][0], '-c', 'import time; time.sleep(2)'], tmp_path, 0.05)


def test_l1_long_receipt_cannot_change_checker_command(tmp_path):
    row = l1(tmp_path, seconds=121)
    row['checker'] = ['different-checker']
    assert_failure(row, tmp_path, 'matching command')


@pytest.mark.skipif(v.sys.platform != 'darwin', reason='macOS read-only sandbox')
def test_l1_checker_cannot_write_lane_data(tmp_path):
    (tmp_path / 'protected.txt').write_text('original')
    with pytest.raises(ValueError, match='exited'):
        v._run_checker([v.sys.executable, '-c', "from pathlib import Path; Path('protected.txt').write_text('changed')"], tmp_path, 5)
    assert (tmp_path / 'protected.txt').read_text() == 'original'


def test_finite_component_evidence_separate_from_whole(tmp_path):
    evidence = l1(tmp_path)
    row = dict(verification='L0', finite_component='L1', finite_evidence=evidence)
    assert v.validate_row(row, tmp_path) == []
    row['finite_evidence']['checker_author'] = evidence['producer_author']
    assert_failure(row, tmp_path, 'must differ')


@pytest.mark.parametrize('row,required,valid', [
    ({}, False, True), ({}, True, False),
    ({'verification': 'L0'}, False, False),
    ({'verification': 'L0', 'finite_component': 'none'}, True, True),
    ({'verification': 'L4', 'finite_component': 'none'}, False, False),
])
def test_legacy_and_level_schema(tmp_path, row, required, valid):
    assert (v.validate_row(row, tmp_path, required=required) == []) == valid


def test_verification_line():
    assert rh.verification_line is v.verification_line
    assert v.verification_line({'verification': 'L0', 'finite_component': 'L1'}).startswith('Verification level: L0 ')
    assert 'finite component: L1.' in v.verification_line({'verification': 'L0', 'finite_component': 'L1'})
    assert '\n' not in v.verification_line({'verification': 'L2', 'verification_scope': 'the finite step'})


@pytest.fixture
def harness():
    h = test_rh.HarnessTests(methodName='runTest')
    h.setUp()
    try:
        yield h
    finally:
        h.doCleanups()


def test_cli_required_close_legacy_optional_and_lint(harness):
    h = harness
    first = h.add()
    assert h.cli('ideas', 'close', 'test', first, '--closed-reason', 'known', '--no-test-reason', 'known')[0] == 0
    old = h.history()[-1]
    assert 'verification' not in old
    # A genuinely historical row stays optional after opt-in.
    assert v.validate_row(old, h.lane) == []
    (h.lane / 'INTAKE.toml').write_text('keywords = []\nverification_required = true\n')
    second = h.add()
    code, _, err = h.cli('ideas', 'close', 'test', second, '--closed-reason', 'known', '--no-test-reason', 'known')
    assert code == 2 and 'verification must' in err
    assert h.history()[-1]['status'] == 'new'
    code, _, err = h.cli('ideas', 'close', 'test', second, '--closed-reason', 'known', '--no-test-reason', 'known', '--verification', 'L0', '--finite-component', 'none')
    assert code == 0, err
    row = copy.deepcopy(h.history()[-1])
    assert row['verification'] == 'L0' and row['verification_policy_version'] == 1
    failures = rh.checked_lint(h.lane)['failures']
    assert not any(f['check'] == 'verification' for f in failures), failures
    row.pop('verification')
    rh.append(h.lane / 'IDEAS.jsonl', row)
    failures = rh.checked_lint(h.lane)['failures']
    assert any(f['check'] == 'verification' for f in failures)


def test_cli_result_evidence_and_new_attempt_does_not_inherit(harness):
    h = harness
    idea = h.add()
    assert h.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')[0] == 0
    row = l1(h.lane)
    evidence = h.root / 'verification.json'
    save_json(evidence, row)
    result = h.root / 'result.md'
    result.write_text('finite witness')
    config = h.root / 'config.json'
    config.write_text('{"parameter": 1}')
    args = ['ideas', 'result', 'test', idea, '--result-path', str(result), '--config-path', str(config)]
    code, _, err = h.cli(*(args + ['--verification-evidence', str(evidence)]))
    assert code == 0, err
    assert h.history()[-1]['verification'] == 'L1'
    # Repeat result without metadata cannot retain a previous claim.
    second_result = h.root / 'result-2.md'
    second_result.write_text('another finite witness')
    config.write_text('{"parameter": 2}')
    args[args.index(str(result))] = str(second_result)
    code, _, err = h.cli(*args)
    assert code == 0, err
    assert 'verification' not in h.history()[-1]


def test_cli_flags_override_json_and_unknown_fields_refuse_append(harness):
    h = harness
    idea = h.add()
    evidence = h.root / 'verification.json'
    packet = l1(h.lane)
    packet['closed_reason'] = 'must not override the event'
    save_json(evidence, packet)
    args = ['ideas', 'close', 'test', idea, '--closed-reason', 'known',
            '--no-test-reason', 'known', '--verification-evidence', str(evidence),
            '--verification', 'L0', '--finite-component', 'none']
    before = h.history()
    code, _, err = h.cli(*args)
    assert code == 2 and 'unknown verification evidence fields' in err
    assert h.history() == before
    packet.pop('closed_reason')
    save_json(evidence, packet)
    with patch.object(v, '_run_checker', side_effect=AssertionError('L0 must not replay')):
        code, _, err = h.cli(*args)
    assert code == 0, err
    assert h.history()[-1]['verification'] == 'L0'
    assert h.history()[-1]['finite_component'] == 'none'
    assert h.history()[-1]['closed_reason'] == 'known'


def test_config_boolean_and_new_close_cutoff():
    with pytest.raises(ValueError, match='verification_required'):
        rh.validate_config({'verification_required': 'true'})
    assert not v.new_close({'event': 'close', 'revised': '2026-11-01T00:00:00+00:00'})
    assert v.new_close({'event': 'close', 'revised': '2026-11-04T00:00:00+00:00'})
    assert v.new_close({'event': 'close', 'revised': '2026-11-03T14:10:00-04:00'})
    assert not v.new_close({'event': 'close', 'verification_policy_version': 1, 'verification_required_at_close': False})
    assert v.new_close({'event': 'close', 'revised': 'broken'})
    assert v.new_close({'status': 'closed', 'created': '2026-11-04T00:00:00Z'})


def test_intake_automatic_close_has_l0_in_opted_in_lane(harness):
    h = harness
    cfg = dict(verification_required=True, banned_patterns=[dict(pattern='out of scope', reason='source exclusion')])
    assert h.ingest([dict(title='out of scope', source_url='https://example.org/paper')], cfg=cfg) == 1
    row = h.history()[-1]
    assert row['status'] == 'closed'
    assert row['verification'] == 'L0' and row['finite_component'] == 'none'
    assert v.validate_row(row, h.lane, required=True) == []


def test_lint_validates_historical_tagged_evidence(harness):
    h = harness
    row = l1(h.lane, seconds=121)
    row.update(id=h.add(), event='result', status='testing', revised='2026-11-01T00:00:00Z')
    row['checker_author'] = row['producer_author']
    rh.append(h.lane / 'IDEAS.jsonl', row)
    errors = rh.checked_lint(h.lane)['failures']
    assert any(e['check'] == 'verification' and 'must differ' in e['message'] for e in errors)


def public_packet(root, row, text):
    path = root / 'body.md'
    path.write_text(text)
    save_json(Path(str(path) + '.verification.json'), dict(sha256=v.sha256(path), row=row))
    return path


def test_public_overclaim_and_body_hash(tmp_path):
    row = l1(tmp_path)
    path = public_packet(tmp_path, row, v.verification_line(row))
    assert v.publication_errors(path) == []
    path = public_packet(tmp_path, row, 'Verification level: L3 (full bound).')
    assert 'exceeds supported L1' in v.publication_errors(path)[0]
    path.write_text('Verification level: L2 changed after review')
    assert 'body hash mismatch' in v.publication_errors(path)[0]


def test_public_whole_cannot_borrow_finite_level(tmp_path):
    row = dict(verification='L0', finite_component='L1', finite_evidence=l1(tmp_path))
    path = public_packet(tmp_path, row, v.verification_line(row))
    assert v.publication_errors(path) == []
    path = public_packet(tmp_path, row, 'The whole bound has verification level L1.')
    assert 'exceeds supported L0' in v.publication_errors(path)[0]


def test_optional_publication_helper_never_runs_checker_and_rechecks_receipts(tmp_path):
    row = l1(tmp_path)
    path = public_packet(tmp_path, row, v.verification_line(row))
    with patch.object(v, '_run_checker', side_effect=AssertionError('publication must not execute evidence')):
        assert v.publication_errors(path) == []
        (tmp_path / 'checker.py').write_text('changed after review\n')
        assert 'hash mismatch' in v.publication_errors(path)[0]


def test_public_missing_evidence_and_untagged_legacy(tmp_path):
    path = tmp_path / 'body.md'
    path.write_text('Verification level: L2')
    assert v.publication_errors(path)
    path.write_text('Legacy text without a verification claim.')
    assert v.publication_errors(path) == []


@pytest.mark.parametrize('level', ['L2-same-agent', 'L3-partial', 'L3-independence-unestablished'])
def test_public_strict_lean_claims_cannot_hide_behind_l1_annotations(tmp_path, level):
    path = tmp_path / 'body.md'
    path.write_text('Verification level: ' + level)
    assert v.publication_errors(path)


def test_public_same_agent_l1_annotation_does_not_assert_strict_l1(tmp_path):
    path = tmp_path / 'body.md'
    path.write_text('Whole-bound level: L0; finite parts L1-same-agent.')
    assert v.publication_errors(path) == []


def test_a_read_mark_on_an_old_close_is_not_a_new_close():
    """11-10, math rows 511/512/517/518: closed 10-31 and 11-01, then a sweep read mark on 11-03 copied
    each closed row with a later `revised`, and lint judged the copy as a close made under the rule."""
    old_close = {'event': 'close', 'status': 'closed', 'revised': '2026-11-01T17:45:06+00:00'}
    read_mark = dict(old_close, event='read', revised='2026-11-03T21:27:34+00:00')
    assert not v.new_close(old_close)
    assert not v.new_close(read_mark)
    # A close made under the rule is still judged on its own row, whatever read marks follow it.
    assert v.new_close({'event': 'close', 'status': 'closed', 'revised': '2026-11-04T00:00:00+00:00'})
