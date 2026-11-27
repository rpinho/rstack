"""Real pinned Git packets; optionally the installed publication hook. No network writes."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_lint as p

ROOT = Path(p.__file__).parent
# The publication hook and review-receipt CLI are installed outside this repository. Point
# RH_PUBLISH_HOOK and RH_PUBLISH_REVIEW_GATE at them to run the live-gate tests; unset, they skip.
HOOK = os.environ.get('RH_PUBLISH_HOOK', '')
REVIEW_GATE = os.environ.get('RH_PUBLISH_REVIEW_GATE', '')


@pytest.fixture(autouse=True)
def _stub_xlint(tmp_path_factory, monkeypatch):
    """A permissive voice linter; publish_lint's own banned-phrase rules still apply."""
    stub = tmp_path_factory.mktemp('xlint') / 'xlint.py'
    stub.write_text('import sys\nsys.stdin.read()\n')
    monkeypatch.setattr(p, 'XLINT', stub)
    monkeypatch.setenv('RH_XLINT', str(stub))


class Packet:
    def __init__(self, tmp):
        self.root = tmp / 'packet'
        self.root.mkdir()
        self.body = tmp / 'body.md'
        self.body.write_text('A certificate accompanies this submission.\n')
        self.meta = dict(target='teorth/optimizationproblems#42', new_bound=False,
                         producer_author='producer-a', producer_model='model-a')
        self.claims = []
        self.steps = []
        self.write('README.md', 'A mathematical packet.\n')
        self.write('PROOF.md', 'The identity follows by algebra.\n')
        self.write('exact.py', 'from fractions import Fraction\nvalue = Fraction(1, 4)\n')
        self.write('interval.py', 'from flint import arb\nvalue = arb(1) / 4\n')
        self.write('float.py', 'value = 0.25\n')
        self.write('certificate.json', '{"value":"1/4"}\n')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Publish test')
        self.git('config', 'user.email', 'publish-test@example.invalid')
        self.seal()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    def obj(self, path, data):
        self.write(path, json.dumps(data, indent=2) + '\n')

    def seal(self):
        self.obj('PUBLISH.json', self.meta)
        self.obj('CLAIMS.json', {'claims': self.claims})
        self.obj('RIGOR.json', {'steps': self.steps})
        self.git('add', '.')
        self.git('commit', '--allow-empty', '-qm', 'Test packet')

    def lint(self, comments=None):
        self.seal()
        return p.Linter(p.Snapshot(self.root), self.body, comments=comments).run()

    def bound(self, new=False, interval=False):
        script = 'interval.py' if interval else 'exact.py'
        self.claims = [dict(value='0.25', kind='rigorous', producer=script,
                            arithmetic='interval' if interval else 'exact', new_bound=new)]
        text = 'The upper bound is 0.25 (rigorous, ' + script + ').\n'
        self.write('README.md', text)
        self.body.write_text(text)
        self.meta['new_bound'] = new
        return self

    def replay(self):
        self.bound(new=True)
        self.meta['replay_inputs'] = {'PROOF.md': 'proof', 'certificate.json': 'certificate'}
        self.write('replay/check.py', 'from fractions import Fraction\nanswer = Fraction(1, 4)\n')
        self.write('replay/report.md', 'The independent exact calculation gives 0.25.\n')
        inputs = {k: p.sha((self.root / k).read_bytes()) for k in self.meta['replay_inputs']}
        self.replay_data = dict(model='model-b', author='checker-b', status='PASS', value='0.25',
                                inputs=inputs, inputs_hash=p.sha(p.canonical(inputs)),
                                read_producer_code=False, ran_producer_code=False,
                                checker='replay/check.py', arithmetic='exact',
                                checker_sha256=p.sha((self.root / 'replay/check.py').read_bytes()),
                                report='replay/report.md', report_sha256=p.sha((self.root / 'replay/report.md').read_bytes()))
        self.obj('REPLAY.json', self.replay_data)
        return self

    def receipt(self):
        result = self.lint()
        assert result['status'] == 'PASS', result['checks']
        p.save_receipt(p.receipt_path(self.root, self.body), result)
        return result


@pytest.fixture
def packet(tmp_path):
    return Packet(tmp_path)


def check(packet, name, passing):
    result = packet.lint()
    assert (result['checks'][name]['status'] == 'PASS') == passing, result['checks'][name]
    return result['checks'][name]['failures']


def advise(packet, name):
    # 11-04: paperwork/completeness findings are ADVISORY: recorded, never gating.
    result = packet.lint()
    row = result['checks'][name]
    assert row['status'] == 'PASS' and not row['failures'] and row['advisory'], row
    return row['advisory']


@pytest.mark.parametrize('interval', [False, True])
def test_claims_positive_exact_and_interval(packet, interval):
    packet.bound(interval=interval)
    assert packet.lint()['status'] == 'PASS'


@pytest.mark.parametrize('change', ['unlabeled', 'missing-label', 'missing-producer', 'float', 'mismatched-kind', 'duplicate'])
def test_claims_negative(packet, change):
    packet.bound()
    if change == 'unlabeled':
        packet.claims = []
    elif change == 'missing-label':
        packet.body.write_text('The upper bound is 0.25 from exact.py.\n')
    elif change == 'missing-producer':
        packet.body.write_text('The upper bound is 0.25 (rigorous).\n')
    elif change == 'float':
        packet.claims[0].update(producer='float.py', arithmetic='float')
    elif change == 'mismatched-kind':
        packet.claims[0]['kind'] = 'estimate'
    else:
        packet.claims.append(copy.deepcopy(packet.claims[0]))
    if change in ('missing-label', 'missing-producer', 'duplicate'):
        assert advise(packet, 'claims')
    else:
        assert check(packet, 'claims', False)


def test_estimate_separate_from_bound_positive(packet):
    packet.claims = [dict(value='0.25', kind='estimate', producer='float.py', arithmetic='float')]
    text = 'The estimate is 0.25 from float.py.\n'
    packet.write('README.md', text)
    packet.body.write_text(text)
    assert packet.lint()['status'] == 'PASS'


def test_estimate_next_to_endpoint_negative_301(packet):
    packet.bound()
    packet.claims.append(dict(value='0.24999', kind='estimate', producer='float.py', arithmetic='float'))
    packet.body.write_text('The rigorous upper bound is 0.25 from exact.py, with the review estimate 0.24999 from float.py.\n')
    failures = check(packet, 'claims', False)
    assert any('estimate in a bound sentence' in r['message'] for r in failures)


def test_claims_negative_301_unlabeled_adjacent_review_value(packet):
    packet.claims = [dict(value='0.25309183355151', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False)]
    packet.body.write_text('The rigorous upper endpoint is 0.25309183355151 from exact.py. The separate integrator float.py gives 0.25309183355146.\n')
    errors = advise(packet, 'claims')
    assert '0.25309183355146' in str(errors)


def test_claims_positive_301_adjacent_estimate_explicitly_labeled(packet):
    packet.claims = [dict(value='0.25309183355151', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False),
                     dict(value='0.25309183355146', kind='estimate', producer='float.py', arithmetic='float')]
    packet.body.write_text('The rigorous upper endpoint is 0.25309183355151 from exact.py. The separate estimate is 0.25309183355146 from float.py.\n')
    assert packet.lint()['status'] == 'PASS'


def credited(packet, pr_name='Ada Lovelace', packet_name='Ada Lovelace', source_name='Ada Lovelace'):
    packet.body.write_text('I credit ' + pr_name + '.\n')
    packet.write('CREDIT.md', 'Author: ' + packet_name + '\n')
    packet.obj('sources/pr17.json', {'number': 17, 'author': {'login': 'ada', 'name': source_name}, 'body': ''})
    packet.obj('CREDITS.json', {'credits': [dict(pr_name=pr_name, packet_name=packet_name, source_name=source_name,
                                                packet_file='CREDIT.md', source_pr='sources/pr17.json')]})


def test_credit_positive(packet):
    credited(packet)
    assert packet.lint()['status'] == 'PASS'


def test_credit_negative_verbatim_299(packet):
    credited(packet, 'V. Patankar', 'David Niedbala Giraudin', 'vidigoat')
    failures = check(packet, 'credit', False)
    assert all(name in str(failures) for name in ('V. Patankar', 'David Niedbala Giraudin', 'vidigoat'))


def test_credit_negative_missing_or_fabricated_evidence(packet):
    packet.body.write_text('I credit Ada Lovelace.\n')
    advise(packet, 'credit')
    credited(packet)
    packet.obj('sources/pr17.json', {'author': {'login': 'someone-else'}})
    check(packet, 'credit', False)


def test_credit_positive_source_byline(packet):
    credited(packet)
    data = json.loads((packet.root / 'CREDITS.json').read_text())
    data['credits'][0]['byline'] = 'Ada Lovelace'
    packet.obj('CREDITS.json', data)
    packet.obj('sources/pr17.json', {'number': 17, 'author': {'login': 'ada'}, 'body': 'By Ada Lovelace'})
    check(packet, 'credit', True)


def test_paths_positive(packet):
    packet.write('PRIOR_ART.md', 'Prior work.\n')
    packet.write('PROOF.md', 'See [prior art](PRIOR_ART.md) and `certificate.json`.\n')
    assert packet.lint()['status'] == 'PASS'


def test_paths_negative_missing_299_and_untracked_at_pin(packet):
    packet.write('PROOF.md', 'See PRIOR_ART.md.\n')
    failures = check(packet, 'paths', False)
    assert 'PRIOR_ART.md' in str(failures)
    packet.write('PRIOR_ART.md', 'Present locally, absent from pinned commit.\n')
    result = p.Linter(p.Snapshot(packet.root), packet.body).run()
    assert result['checks']['paths']['status'] == 'FAIL'


def test_paths_negative_escape_and_symlink(packet):
    packet.write('PROOF.md', 'See ../../outside.md.\n')
    check(packet, 'paths', False)
    packet.write('PROOF.md', 'See linked.md.\n')
    (packet.root / 'linked.md').symlink_to('PROOF.md')
    check(packet, 'paths', False)


def test_paths_positive_sibling_at_pin(packet):
    # Packet prefix is a subdirectory; a legitimate ../ link stays in the repository.
    packet.write('sub/README.md', 'See ../PROOF.md.\n')
    packet.seal()
    snapshot = p.Snapshot(packet.root / 'sub')
    result = p.Linter(snapshot, metadata=dict(packet.meta)).run()
    assert result['checks']['paths']['status'] == 'PASS'


@pytest.mark.parametrize('text,passing', [('Builds on #41.', True), ("Replaces round 3 in #42.", False),
                                       ('This PR (#42) has a certificate.', True),
                                       ('Builds on https://github.com/teorth/optimizationproblems/pull/42.', False)])
def test_selfref_positive_and_negative_307(packet, text, passing):
    packet.body.write_text(text)
    check(packet, 'selfref', passing)


@pytest.mark.parametrize('place', ['body', 'comment', 'readme'])
@pytest.mark.parametrize('phrase', ['load-bearing', 'good one to have on the record'])
def test_voice_negative_all_requested_surfaces(packet, place, phrase, tmp_path):
    text = 'I think this is a ' + phrase + ' result.\n'
    comments = []
    if place == 'body':
        packet.body.write_text(text)
    elif place == 'readme':
        packet.write('README.md', text)
    else:
        comment = tmp_path / 'comment.md'
        comment.write_text(text)
        comments = [comment]
    packet.seal()
    assert p.Linter(p.Snapshot(packet.root), packet.body, comments=comments).run()['checks']['voice']['status'] == 'FAIL'


def test_voice_positive_real_pr_refs_and_code(packet, tmp_path):
    packet.body.write_text('I checked the certificate in #41.\n\n```python\nload_bearing = True\n```\n')
    comment = tmp_path / 'comment.md'
    comment.write_text('I checked the fraction.\n')
    packet.seal()
    assert p.Linter(p.Snapshot(packet.root), packet.body, comments=[comment]).run()['checks']['voice']['status'] == 'PASS'


def test_rigor_positive_exact_and_mapped_interval(packet):
    packet.write('PROOF.md', 'The finite identity is verified by exact.py.\nThe integral is verified.\n')
    packet.steps = [dict(document='PROOF.md', statement='The integral is verified.', producer='interval.py', arithmetic='interval')]
    assert packet.lint()['status'] == 'PASS'


@pytest.mark.parametrize('script', ['float.py', 'missing.py'])
def test_rigor_negative_verified_float_or_missing(packet, script):
    packet.write('PROOF.md', 'The cover is verified by ' + script + '.\n')
    check(packet, 'rigor', False)


@pytest.mark.parametrize('arith', ['exact', 'interval'])
def test_rigor_negative_false_manifest_arithmetic(packet, arith):
    packet.write('PROOF.md', 'The leaves are verified.\n')
    packet.steps = [dict(document='PROOF.md', statement='The leaves are verified.', producer='float.py', arithmetic=arith)]
    advise(packet, 'rigor')


def test_rigor_positive_float_downgrades_claim_text(packet):
    packet.claims = [dict(value='0.25', kind='estimate', producer='float.py', arithmetic='float')]
    packet.body.write_text('Numerical evidence gives the estimate 0.25 from float.py.\n')
    packet.write('README.md', packet.body.read_text())
    statement = 'The sampling is numerical evidence from float.py.'
    packet.write('PROOF.md', statement + '\n')
    packet.steps = [dict(document='PROOF.md', statement=statement, producer='float.py', arithmetic='float')]
    assert packet.lint()['status'] == 'PASS'


def test_rigor_negative_float_step_requires_packet_downgrade(packet):
    packet.bound()
    statement = 'The sampling is numerical evidence from float.py.'
    packet.write('PROOF.md', statement + '\n')
    packet.steps = [dict(document='PROOF.md', statement=statement, producer='float.py', arithmetic='float')]
    assert any('downgrades the packet' in e['message'] for e in check(packet, 'rigor', False))


def test_rigor_negative_float_import_hidden_in_local_helper(packet):
    packet.write('helper.py', 'import math\nvalue = math.sqrt(2)\n')
    packet.write('exact.py', 'from helper import value\nfrom fractions import Fraction\nresult = Fraction(value)\n')
    packet.bound()
    advise(packet, 'claims')  # heuristic source audit: ADVISORY


def test_replay_positive_different_author_and_model(packet):
    packet.replay()
    assert packet.lint()['status'] == 'PASS'


def test_replay_positive_comment_mention_does_not_access_producer(packet):
    packet.replay()
    packet.write('replay/check.py', '# I did not read exact.py.\nfrom fractions import Fraction\nanswer = Fraction(1, 4)\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    check(packet, 'replay', True)


def test_replay_positive_no_new_bounds_needs_no_lean_or_l1(packet):
    packet.bound(new=False)
    assert packet.lint()['status'] == 'PASS'


def test_replay_negative_missing_for_new_bound(packet):
    packet.bound(new=True)
    check(packet, 'replay', False)


@pytest.mark.parametrize('change', ['same-model', 'same-author', 'inputs-hash', 'proof-change', 'value',
                                  'read-code', 'ran-code', 'FAIL', 'missing-report', 'checker-change',
                                  'extra-code-input', 'float-checker', 'missing-input-role'])
def test_replay_negative_provenance_and_freshness(packet, change):
    packet.replay()
    row = packet.replay_data
    if change == 'same-model': row['model'] = ' MODEL-A '
    elif change == 'same-author': row['author'] = 'Producer A'
    elif change == 'inputs-hash': row['inputs_hash'] = '0' * 64
    elif change == 'proof-change': packet.write('PROOF.md', 'The algebra is revised.\n')
    elif change == 'value': row['value'] = '0.25001'
    elif change == 'read-code': row['read_producer_code'] = True
    elif change == 'ran-code': row['ran_producer_code'] = True
    elif change == 'FAIL': row['status'] = 'FAIL'
    elif change == 'missing-report': row['report'] = 'absent.md'
    elif change == 'checker-change': packet.write('replay/check.py', 'answer = 1\n')
    elif change == 'extra-code-input': packet.meta['replay_inputs']['exact.py'] = 'certificate'
    elif change == 'float-checker': row['arithmetic'] = 'float'
    elif change == 'missing-input-role': packet.meta['replay_inputs'] = {'PROOF.md': 'proof'}
    packet.obj('REPLAY.json', row)
    check(packet, 'replay', False)


def test_replay_negative_cannot_turn_off_for_new_claim(packet):
    packet.bound(new=True)
    packet.meta['new_bound'] = False
    check(packet, 'replay', False)


def test_receipt_positive_and_expiry(packet):
    packet.bound().receipt()
    assert p.publication_errors(packet.body, packet.meta['target']) == []
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    assert 'expired' in str(p.publication_errors(packet.body, packet.meta['target'], future))


@pytest.mark.parametrize('change', ['body', 'target', 'source', 'HEAD', 'untracked', 'checks', 'future-date'])
def test_receipt_negative_stale_or_misbound(packet, change):
    packet.bound().receipt()
    target = packet.meta['target']
    if change == 'body': packet.body.write_text('Changed submission.\n')
    elif change == 'target': target = 'teorth/optimizationproblems#43'
    elif change == 'source': packet.write('exact.py', 'value = 0.25\n')
    elif change == 'HEAD': packet.seal()
    elif change == 'untracked': packet.write('new-proof.md', 'Another proof.\n')
    else:
        path = p.receipt_path(packet.root, packet.body)
        row = json.loads(path.read_text())
        if change == 'checks': row['checks']['replay']['status'] = 'FAIL'
        else: row['utc'] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)).isoformat()
        path.write_text(json.dumps(row))
    assert p.publication_errors(packet.body, target)


def test_receipt_comment_changes_invalidate(packet, tmp_path):
    comment = tmp_path / 'comment.md'
    comment.write_text('I checked it.\n')
    result = packet.lint(comments=[comment])
    p.save_receipt(p.receipt_path(packet.root, packet.body), result)
    assert p.publication_errors(packet.body, packet.meta['target']) == []
    comment.write_text('I changed my comment.\n')
    assert p.publication_errors(packet.body, packet.meta['target'])


def hook_home(tmp_path):
    if not (HOOK and Path(HOOK).is_file() and REVIEW_GATE and Path(REVIEW_GATE).is_file()):
        pytest.skip('RH_PUBLISH_HOOK / RH_PUBLISH_REVIEW_GATE not set to installed gates')
    home = tmp_path / 'home'
    harness = home / '.local/share/research-harness'
    harness.mkdir(parents=True)
    shutil.copy2(ROOT / 'verification.py', harness / 'verification.py')
    cli = home / '.local/bin/science-publish-gate'
    cli.parent.mkdir(parents=True)
    shutil.copy2(REVIEW_GATE, cli)
    return home


def hook(home, packet, command):
    event = dict(tool_name='Bash', cwd=str(packet.root), tool_input={'command': command})
    # Pre-import this repository's modules so the hook's own imports reuse them.
    shim = ('import sys, runpy; sys.path.insert(0, ' + repr(str(ROOT)) + '); import x_gate, publish_lint; '
            'sys.argv = [' + repr(HOOK) + ']; runpy.run_path(' + repr(HOOK) + ", run_name='__main__')")
    result = subprocess.run([sys.executable, '-c', shim], input=json.dumps(event), capture_output=True,
                            text=True, env=dict(os.environ, HOME=str(home)))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def review(home, packet):
    report = packet.body.parent / 'review.md'
    report.write_text('The supplied bytes were reviewed.\n')
    digest = p.sha(packet.body.read_bytes())
    data = {'reviews': [dict(reviewer=r, verdict='accept', sha256=digest, report=str(report)) for r in ('fable', 'astra')]}
    Path(str(packet.body) + '.reviews.json').write_text(json.dumps(data))
    result = subprocess.run([sys.executable, str(REVIEW_GATE), str(packet.body), '--action', 'teorth-pr',
                             '--target', packet.meta['target']], capture_output=True, text=True,
                            env=dict(os.environ, HOME=str(home)))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('verb', ['create', 'edit', 'ready'])
def test_live_gate_positive_needs_both_receipts(packet, tmp_path, verb):
    packet.meta['target'] = 'teorth/optimizationproblems' if verb == 'create' else 'teorth/optimizationproblems#42'
    packet.bound().receipt()
    home = hook_home(tmp_path)
    pr = '' if verb == 'create' else '42'
    command = f'gh pr {verb} {pr} -R teorth/optimizationproblems --body-file {packet.body}'
    assert hook(home, packet, command) is not None
    review(home, packet)
    assert hook(home, packet, command) is None
    packet.body.write_text('Changed after lint and review.\n')
    review(home, packet)
    assert 'publish-lint' in str(hook(home, packet, command))


def test_live_gate_negative_reviews_alone_insufficient(packet, tmp_path):
    home = hook_home(tmp_path)
    review(home, packet)
    decision = hook(home, packet, f'gh pr edit 42 -R teorth/optimizationproblems --body-file {packet.body}')
    assert 'publish-lint' in str(decision)


def test_cli_positive_read_only_and_negative_exit(packet, tmp_path):
    packet.bound().seal()
    command = [sys.executable, str(ROOT / 'rh.py'), 'publish-lint', str(packet.root), '--pr-body', str(packet.body), '--json', '--no-receipt']
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'PASS'
    assert not p.receipt_path(packet.root, packet.body).exists()
    packet.body.write_text('The upper bound is 0.24.\n')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1 and json.loads(result.stdout)['status'] == 'FAIL'


def test_cli_audit_metadata_cannot_issue_publish_receipt(packet, tmp_path):
    config = tmp_path / 'audit.json'
    config.write_text(json.dumps(packet.meta))
    result = subprocess.run([sys.executable, str(ROOT / 'rh.py'), 'publish-lint', str(packet.root),
                             '--metadata', str(config)], capture_output=True, text=True)
    assert result.returncode == 1 and 'audit-only' in result.stderr


def test_receipt_replacement_preserves_backup(packet):
    packet.receipt()
    path = p.receipt_path(packet.root, packet.body)
    original = path.read_bytes()
    p.save_receipt(path, json.loads(original))
    assert Path(str(path) + '.bak-1104x').read_bytes() == original


@pytest.mark.parametrize('text', ['`C<0.24`', '```math\nC <= 0.24\n```', '    C <= 0.24', 'C\\leq 0.24', 'C≤.24'])
def test_claims_negative_bound_display_forms(packet, text):
    packet.body.write_text(text + '\n')
    check(packet, 'claims', False)


def test_claims_positive_wrapped_label_and_latex_fraction(packet):
    packet.claims = [dict(value='1/4', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False)]
    text = 'The upper bound is \\frac{1}{4}\n(rigorous, exact.py).\n'
    packet.body.write_text(text)
    packet.write('README.md', text)
    check(packet, 'claims', True)


def test_claims_positive_complete_bound_expression(packet):
    packet.claims = [dict(value='1/2 + 2^-4096', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False)]
    packet.body.write_text('The lower bound is 1/2 + 2^{-4096} (rigorous, exact.py).\n')
    check(packet, 'claims', True)


@pytest.mark.parametrize('source', ['# Arb interval arithmetic\nvalue = 0.25\n',
                                    'from flint import arb\nvalue = 0.25\n'])
def test_claims_negative_fake_interval_annotation_or_unused_import(packet, source):
    packet.bound(interval=True)
    packet.write('interval.py', source)
    advise(packet, 'claims')  # heuristic source audit: ADVISORY


def test_claims_negative_cpp_float_literal_even_with_gmp_name(packet):
    packet.write('counter.cpp', 'int main() { mpq_class unused; auto value = 0.25; }\n')
    packet.bound()
    packet.claims[0]['producer'] = 'counter.cpp'
    advise(packet, 'claims')  # heuristic source audit: ADVISORY


@pytest.mark.parametrize('expression', ['1 / 4', '2 ** -2'])
def test_claims_negative_implicit_python_floats_with_unused_fraction_import(packet, expression):
    packet.bound()
    packet.write('exact.py', 'from fractions import Fraction\nvalue = ' + expression + '\n')
    advise(packet, 'claims')  # heuristic source audit: ADVISORY


def test_claims_positive_rational_division_and_constructor_alias(packet):
    packet.bound()
    packet.write('exact.py', 'from fractions import Fraction as Q\nq = Q(1, 1)\nvalue = q / 4\n')
    check(packet, 'claims', True)


def test_credit_negative_extra_unmapped_name_or_pr(packet):
    credited(packet)
    packet.body.write_text('I credit Ada Lovelace in #17 and Bob in #18.\n')
    packet.write('OTHER_CREDIT.md', 'Author: Bob\n')
    errors = check(packet, 'credit', False)
    assert '#18' in str(errors)
    assert "'Bob'" in str(packet.lint()['checks']['credit']['advisory'])


def test_credit_negative_mentions_are_not_author_bylines(packet):
    credited(packet)
    data = json.loads((packet.root / 'CREDITS.json').read_text())
    data['credits'][0]['byline'] = 'Ada Lovelace'
    packet.obj('CREDITS.json', data)
    packet.obj('sources/pr17.json', dict(number=17, author={'login': 'someone-else'}, body='I used Ada Lovelace\'s result.'))
    check(packet, 'credit', False)


@pytest.mark.parametrize('change', ['path', 'pin', 'truncated'])
def test_paths_negative_external_pinned_link_evidence(packet, change):
    commit = 'a' * 40
    tree = dict(commit=commit, truncated=False, tree=[{'path': 'PROOF.md', 'type': 'blob', 'mode': '100644'}])
    packet.body.write_text('See [proof](https://github.com/example/result/blob/' + commit + '/PROOF.md).\n')
    packet.meta['linked_trees'] = {'example/result@' + commit: tree}
    check(packet, 'paths', True)
    if change == 'path': tree['tree'][0]['path'] = 'OTHER.md'
    elif change == 'pin': tree['commit'] = 'b' * 40
    else: tree['truncated'] = True
    check(packet, 'paths', False)


def test_paths_positive_math_quotients_are_not_paths(packet):
    packet.write('PROOF.md', 'Use `1396/125`, `T/m` and `mu/m` in the identity.\n')
    check(packet, 'paths', True)


def test_paths_positive_cited_target_repository_file(packet):
    commit = 'c' * 40
    packet.meta.update(publication_commit=commit, publication_tree=dict(commit=commit, truncated=False,
        tree=[{'path': 'constants/42a.md', 'type': 'blob', 'mode': '100644'}]))
    packet.body.write_text('This updates `constants/42a.md`.\n')
    check(packet, 'paths', True)


@pytest.mark.parametrize('text', ['This updates our existing open PR #42.',
                                'See [my comment](https://github.com/teorth/optimizationproblems/pull/42#issuecomment-123).',
                                'Only #41 and #42 change this page.'])
def test_selfref_positive_legitimate_self_context(packet, text):
    packet.body.write_text(text)
    check(packet, 'selfref', True)


def test_replay_negative_cannot_import_producer(packet):
    packet.replay()
    packet.write('replay/check.py', 'from ..exact import value\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    # Relative imports are resolved and cannot replace an independently written check.
    check(packet, 'replay', False)


@pytest.mark.parametrize('wrapper', ["bash -lc {command}", '/usr/bin/env -- {raw}',
                                     'env -u UNUSED {raw}', 'command -- {raw}',
                                     'export GH_REPO=teorth/optimizationproblems; {bare}',
                                     "GH_REPO=teorth/optimizationproblems sh -c {bare_quoted}"])
def test_live_gate_negative_wrappers_cannot_bypass(packet, tmp_path, wrapper):
    import shlex
    home = hook_home(tmp_path)
    raw = f'gh pr edit 42 -R teorth/optimizationproblems --body-file {packet.body}'
    bare = f'gh pr edit 42 --body-file {packet.body}'
    command = wrapper.format(command=shlex.quote(raw), raw=raw, bare=bare, bare_quoted=shlex.quote(bare))
    assert hook(home, packet, command) is not None


def test_live_gate_negative_edit_requires_explicit_pr(packet, tmp_path):
    packet.meta['target'] = 'teorth/optimizationproblems'
    packet.receipt()
    home = hook_home(tmp_path)
    review(home, packet)
    decision = hook(home, packet, f'gh pr edit -R teorth/optimizationproblems --body-file {packet.body}')
    assert 'numeric PR' in str(decision)


def test_live_gate_positive_pr_number_after_options(packet, tmp_path):
    packet.receipt()
    home = hook_home(tmp_path)
    review(home, packet)
    command = f'gh pr edit -R teorth/optimizationproblems --title "Revised title" --body-file {packet.body} 42'
    assert hook(home, packet, command) is None


@pytest.mark.parametrize('prefix', ['env -u GH_REPO ', 'env --unset=GH_REPO ', 'unset GH_REPO; '])
def test_live_gate_negative_unset_unrelated_environment_cannot_hide_teorth_repo(packet, tmp_path, monkeypatch, prefix):
    packet.git('remote', 'add', 'origin', 'https://github.com/teorth/optimizationproblems.git')
    home = hook_home(tmp_path)
    monkeypatch.setenv('GH_REPO', 'unrelated/repository')
    command = prefix + f'gh pr edit 42 --body-file {packet.body}'
    assert hook(home, packet, command) is not None


@pytest.mark.parametrize('raw', ['{"claims": [], "claims": []}', '{"claims": NaN}', '{"claims": [1]}'])
def test_claims_negative_malformed_manifests_fail_closed(packet, raw):
    packet.seal()
    packet.write('CLAIMS.json', raw)
    packet.git('add', '.')
    packet.git('commit', '-qm', 'Malformed manifest')
    result = p.Linter(p.Snapshot(packet.root), packet.body).run()
    # 11-04: malformed manifests are recorded (ADVISORY), never silently accepted.
    row = result['checks']['claims']
    assert row['advisory'] and 'CLAIMS.json' in str(row['advisory'])


@pytest.mark.parametrize('text,passing', [('The identity is verified by exact.py.', True),
                                       ('The integral is verified by float.py.', False), ('', False)])
def test_rigor_pdf_proof_cannot_be_skipped(packet, monkeypatch, text, passing):
    packet.write('PROOF.pdf', '%PDF-fixture\n')
    original = p.subprocess.run
    def run(command, *args, **kwargs):
        if command[0] == 'pdftotext':
            assert kwargs['input'] == b'%PDF-fixture\n'
            return subprocess.CompletedProcess(command, 0, stdout=text.encode(), stderr=b'')
        return original(command, *args, **kwargs)
    monkeypatch.setattr(p.subprocess, 'run', run)
    if not text:
        advise(packet, 'rigor')
    else:
        check(packet, 'rigor', passing)


def test_advisory_context_integers_do_not_gate(packet):
    # 11-04: years, spans and counts in a bound paragraph are recorded, never gating.
    packet.bound()
    packet.body.write_text(packet.body.read_text().rstrip('\n') + ' It extends span 18 from the 2004 paper.\n')
    result = packet.lint()
    assert result['status'] == 'PASS' and any('2004' in a['message'] for a in result['checks']['claims']['advisory'])


def test_wrong_bound_value_still_blocks(packet):
    packet.bound()
    packet.body.write_text('The upper bound is 0.24 (rigorous, exact.py).\n')
    assert any("'0.24'" in f['message'] for f in check(packet, 'claims', False))


def test_cited_public_value_positive_and_never_new(packet):
    packet.bound()
    packet.claims.append(dict(value='0.26', kind='cited', source='https://github.com/teorth/optimizationproblems/pull/1'))
    packet.body.write_text(packet.body.read_text() + 'The previous upper bound was 0.26.\n')
    assert packet.lint()['status'] == 'PASS'
    packet.claims[-1]['new_bound'] = True
    check(packet, 'claims', False)
    # Astra 11-04 #1: an invalid cited row is not registered, so its value blocks.
    packet.claims[-1] = dict(value='0.24', kind='cited', source='unspecified paper')
    packet.body.write_text('The new rigorous upper bound is 0.24.\n')
    check(packet, 'claims', False)


def test_paths_identical_copies_resolve_and_archived_refs_advisory(packet):
    packet.bound()
    packet.write('frozen/a/SHARED.md', 'same\n')
    packet.write('frozen/b/SHARED.md', 'same\n')
    packet.write('PROOF.md', 'See SHARED.md.\n')
    assert packet.lint()['checks']['paths']['status'] == 'PASS'
    packet.write('frozen/a/PROOF_OLD.md', 'Run gone_helper.cpp first.\n')
    check(packet, 'paths', False)  # unsealed archive copy: BLOCKING (Astra 11-04 #4)
    packet.write('frozen/SHA256SUMS', '0' * 64 + '  a/PROOF_OLD.md\n')
    check(packet, 'paths', False)  # a fabricated seal does not count (Astra r2 #8)
    packet.write('frozen/SHA256SUMS', p.sha(b'Run gone_helper.cpp first.\n') + '  a/PROOF_OLD.md\n')
    assert any('gone_helper.cpp' in a['message'] for a in advise(packet, 'paths'))
    packet.write('frozen/a/PROOF_OLD.md', 'See [helper](gone_helper.cpp).\n')
    check(packet, 'paths', False)  # an explicit link stays BLOCKING even when sealed
    packet.write('PROOF.md', 'Run gone_helper.cpp first.\n')
    check(packet, 'paths', False)


def test_marked_estimate_near_bound_word_is_advisory(packet):
    packet.bound()
    packet.claims.append(dict(value='1.00001', kind='estimate', producer='float.py', arithmetic='float'))
    packet.body.write_text(packet.body.read_text() + 'The value at the reciprocal of this bound is approximately 1.00001.\n')
    assert packet.lint()['checks']['claims']['status'] == 'PASS'
    packet.body.write_text(packet.body.read_text() + 'The upper bound is 1.00001.\n')
    check(packet, 'claims', False)


def test_registered_expression_at_sentence_end(packet):
    packet.bound()
    packet.claims.append(dict(value='51/2^7', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False))
    packet.body.write_text(packet.body.read_text() + 'The bound holds at c=51/2^7. It is rigorous (exact.py).\n')
    assert packet.lint()['checks']['claims']['status'] == 'PASS'


def test_version_and_ellipsis_artifacts_are_context(packet):
    packet.bound()
    packet.body.write_text(packet.body.read_text() + 'The bound checker needs Python 3.10 and checks k=1,...,5999.\n')
    assert packet.lint()['checks']['claims']['status'] == 'PASS'


def test_mixed_exact_float_named_verifier_is_advisory(packet):
    packet.bound()
    packet.write('mixed.py', 'from fractions import Fraction\nx = Fraction(1, 4)\nprint(float(x))\n')
    packet.write('PROOF.md', 'The cover is verified by mixed.py.\n')
    assert advise(packet, 'rigor')


# Astra 11-04 review repros: each must BLOCK.
def test_astra_repro_integer_false_bound_blocks(packet):
    packet.bound()
    packet.body.write_text('The upper bound is 0.\n')
    check(packet, 'claims', False)


def test_astra_repro_numerical_word_cannot_excuse_rigor(packet):
    packet.bound()
    packet.claims.append(dict(value='0.24', kind='estimate', producer='float.py', arithmetic='float'))
    packet.body.write_text('The numerical estimate 0.24 is a rigorous upper bound.\n')
    check(packet, 'claims', False)


def test_astra_repro_archive_folder_cannot_hide_false_bound(packet):
    packet.bound()
    packet.write('frozen/current/README.md', 'The upper bound is 0.24. See [certificate](gone.json).\n')
    result = packet.lint()
    assert result['checks']['claims']['status'] == 'FAIL' and result['checks']['paths']['status'] == 'FAIL'


def test_astra_repro_malformed_credits_keep_pr_attribution_check(packet):
    credited(packet)
    packet.obj('CREDITS.json', {'credits': {}})
    packet.body.write_text('I credit Mallory in #17.\n')
    check(packet, 'credit', False)


def test_astra_repro_identical_copy_cannot_repair_link(packet):
    packet.bound()
    packet.write('a/SHARED.md', 'same\n')
    packet.write('b/SHARED.md', 'same\n')
    packet.write('README.md', packet.body.read_text() + 'See [evidence](SHARED.md).\n')
    check(packet, 'paths', False)


def test_astra_repro_float_only_replay_checker_blocks(packet):
    packet.replay()
    packet.write('replay/check.py', 'answer = 0.1 + 0.15\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    check(packet, 'replay', False)


def unchanged_update(packet, live_text):
    packet.bound(new=True)
    packet.meta['target'] = 'teorth/optimizationproblems#42'
    packet.meta['live_body'] = 'sources/live_pr42.json'
    packet.obj('sources/live_pr42.json', live_snapshot(42, live_text))


def live_snapshot(n, body, repo='teorth/optimizationproblems', state='OPEN', fetched=None):
    import datetime as dt
    fetched = fetched or dt.datetime.now(dt.timezone.utc).isoformat()
    return {'number': n, 'body': body, 'url': 'https://github.com/' + repo + '/pull/' + str(n), 'state': state, 'fetched_utc': fetched}


def test_open_pr_update_with_unchanged_bound_needs_no_replay(packet):
    # general 11-04: bound unchanged vs the PR's current live body => replay ADVISORY.
    unchanged_update(packet, 'Old wording. The upper bound is 0.25 (rigorous, exact.py).')
    row = packet.lint()['checks']['replay']
    assert row['status'] == 'PASS' and row['advisory']


def test_open_pr_update_with_changed_bound_still_needs_replay(packet):
    unchanged_update(packet, 'The upper bound is 0.26 (rigorous, exact.py).')
    check(packet, 'replay', False)
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py).')
    packet.obj('sources/live_pr42.json', {'number': 43, 'body': 'The upper bound is 0.25.'})
    check(packet, 'replay', False)  # snapshot of a different PR does not count


def test_new_pr_with_new_bound_still_needs_replay(packet):
    packet.bound(new=True)
    packet.meta['target'] = 'teorth/optimizationproblems'
    check(packet, 'replay', False)


def test_open_pr_update_new_value_relabelled_old_still_needs_replay(packet):
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py).')
    packet.claims.append(dict(value='0.24', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=False))
    packet.body.write_text('The upper bound is 0.25 (rigorous, exact.py). The improved upper bound is 0.24 (rigorous, exact.py).\n')
    check(packet, 'replay', False)


# Astra 11-04 round-2 repros: each must BLOCK.
def test_r2_unchanged_rule_compares_asserted_bounds_not_presence(packet):
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py). The numerical estimate is 0.24.')
    packet.claims.append(dict(value='0.24', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=True))
    packet.body.write_text('The upper bound is 0.25 (rigorous, exact.py). The improved rigorous upper bound is 0.24 from exact.py.\n')
    check(packet, 'replay', False)


@pytest.mark.parametrize('kw', [dict(repo='teorth/another-repository'), dict(state='CLOSED'), dict(fetched='2020-01-01T00:00:00+00:00')])
def test_r2_snapshot_bound_to_repo_open_state_and_freshness(packet, kw):
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py).')
    packet.obj('sources/live_pr42.json', live_snapshot(42, 'The upper bound is 0.25 (rigorous, exact.py).', **kw))
    check(packet, 'replay', False)


@pytest.mark.parametrize('source', ['certificate.json', 'https://example.org/nonexistent'])
def test_r2_cited_row_cannot_carry_new_result(packet, source):
    packet.bound()
    packet.claims.append(dict(value='0.24', kind='cited', source=source, new_bound=False))
    packet.body.write_text('The new rigorous upper bound is 0.24.\n')
    check(packet, 'claims', False)


def test_r2_unused_fraction_import_cannot_launder_float_replay(packet):
    packet.replay()
    packet.write('replay/check.py', 'from fractions import Fraction\nanswer = 0.1 + 0.15\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    check(packet, 'replay', False)


@pytest.mark.parametrize('text', ['The upper bound equals 0.', 'The rigorous upper bound: 0.', 'Using Python 3.10, the rigorous upper bound is 3.10.'])
def test_r2_integer_and_version_phrasings_block(packet, text):
    packet.bound()
    packet.body.write_text(text + '\n')
    check(packet, 'claims', False)


def test_r2_malformed_author_evidence_keeps_credit_blocking(packet):
    credited(packet, 'Mallory', 'Mallory', 'Mallory')
    packet.obj('sources/pr17.json', {'number': 17, 'author': {'name': 'Ada', 'login': []}, 'body': ''})
    packet.body.write_text('I credit Mallory in #17.\n')
    check(packet, 'credit', False)


def test_r2_explicit_link_resolves_from_its_document(packet):
    packet.bound()
    packet.write('SHARED.md', 'x\n')
    packet.write('sub/README.md', 'See [evidence](SHARED.md).\n')
    check(packet, 'paths', False)


def test_r2_stdlib_import_in_exact_replay_is_fine(packet):
    packet.replay()
    packet.write('replay/check.py', 'import secrets\nfrom fractions import Fraction\nanswer = Fraction(1, 4)\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    assert packet.lint()['checks']['replay']['status'] == 'PASS'


# Astra 11-04 round-3 repros: each must BLOCK unless noted.
@pytest.mark.parametrize('live', ['The cited upper bound of Smith is 0.25.', 'The lower bound is 0.25 (rigorous, exact.py).',
                                  'The upper bound is not 0.25.', 'The estimated upper bound is 0.25.'])
def test_r3_unchanged_rule_needs_same_asserted_bound(packet, live):
    unchanged_update(packet, live)
    check(packet, 'replay', False)


@pytest.mark.parametrize('text', ['This submission improves the result. The rigorous upper bound is 0.24.',
                                  'I prove the rigorous upper bound 0.24.'])
def test_r3_cited_guard_spans_paragraph_and_I(packet, text):
    packet.bound()
    packet.claims.append(dict(value='0.24', kind='cited', source='https://example.org/x', new_bound=False))
    packet.body.write_text(text + '\n')
    check(packet, 'claims', False)


def test_r3_cited_previous_bound_with_we_is_fine(packet):
    packet.bound()
    packet.claims.append(dict(value='0.24', kind='cited', source='https://example.org/x', new_bound=False))
    packet.body.write_text('The upper bound is 0.25 (rigorous, exact.py). The previous upper bound was 0.24; we cite it for comparison.\n')
    assert packet.lint()['checks']['claims']['status'] == 'PASS'


def test_r3_interval_replay_with_float_blocks(packet):
    packet.replay()
    packet.replay_data['arithmetic'] = 'interval'
    packet.write('replay/check.py', 'from flint import arb\nunused = arb(1)\nanswer = 0.1 + 0.15\n')
    packet.replay_data['checker_sha256'] = p.sha((packet.root / 'replay/check.py').read_bytes())
    packet.obj('REPLAY.json', packet.replay_data)
    check(packet, 'replay', False)


@pytest.mark.parametrize('text', ['For k=1,...,24, the rigorous upper bound is .24.', '0 is a rigorous upper bound.',
                                  'The rigorous upper bound is now 0.', 'The rigorous upper bound is **0**.'])
def test_r3_numeric_phrasings_block(packet, text):
    packet.bound()
    packet.body.write_text(text + '\n')
    check(packet, 'claims', False)


def test_r3_credit_name_bound_to_its_pr(packet):
    credited(packet)
    packet.body.write_text('Ada Lovelace is acknowledged. I credit Mallory in #17.\n')
    check(packet, 'credit', False)


@pytest.mark.parametrize('link', ['[evidence](SHARED.md "evidence")', '[evidence][e]\n\n[e]: SHARED.md'])
def test_r3_titled_and_reference_links_resolve_from_document(packet, link):
    packet.bound()
    packet.write('SHARED.md', 'x\n')
    packet.write('sub/README.md', link + '\n')
    check(packet, 'paths', False)


# Astra 11-04 round-4 repros: each must BLOCK.
def test_r4_changed_bound_in_packet_doc_needs_replay(packet):
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py).')
    packet.write('PROOF.md', 'The new rigorous lower bound is 0.25 from exact.py.\n')
    check(packet, 'replay', False)


def test_r4_null_new_bound_counts_as_new(packet):
    packet.replay()
    packet.claims.append(dict(value='0.24', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=None))
    packet.body.write_text(packet.body.read_text() + 'The new rigorous upper bound is 0.24 from exact.py.\n')
    check(packet, 'replay', False)


def test_r4_wrong_credit_in_packet_doc_blocks(packet):
    credited(packet)
    packet.write('README.md', 'I credit Mallory in #17.\n')
    check(packet, 'credit', False)


def test_r4_credit_snapshot_from_other_repo_blocks(packet):
    credited(packet)
    packet.obj('sources/pr17.json', {'number': 17, 'author': {'login': 'ada', 'name': 'Ada Lovelace'}, 'body': '',
                                     'url': 'https://github.com/elsewhere/unrelated/pull/17'})
    packet.body.write_text('I credit Ada Lovelace in #17.\n')
    check(packet, 'credit', False)


def test_own_pr_credit_may_live_in_packet_text_only(packet):
    credited(packet)
    packet.meta['submitter'] = 'ada'
    packet.body.write_text('A certificate accompanies this submission.\n')
    packet.write('README.md', 'This builds on Ada Lovelace (#17).\n')
    assert packet.lint()['checks']['credit']['status'] == 'PASS'
    packet.meta['submitter'] = 'someone-else'
    check(packet, 'credit', False)


def test_prose_citation_relative_to_ancestor_or_own_subtree(packet):
    packet.bound()
    packet.write('round11/frozen_parity/check_b.py', 'from fractions import Fraction\n')
    packet.write('round11/review/README.md', 'It subclasses checker B (`frozen_parity/check_b.py`).\n')
    packet.write('round8/inputs/round7/LEMMA_PROOF.md', 'a\n')
    packet.write('round9/inputs/LEMMA_PROOF.md', 'b\n')
    packet.write('round8/PROOF.md', 'This uses LEMMA_PROOF.md.\n')
    assert packet.lint()['checks']['paths']['status'] == 'PASS'
    packet.write('round11/review/README.md', 'See [checker](frozen_parity/check_b.py).\n')
    check(packet, 'paths', False)  # explicit links still resolve from their own folder


# Astra 11-04 round-5 repros: each must BLOCK.
def test_r5_version_cue_does_not_exempt_separate_bound(packet):
    packet.bound()
    packet.claims.append(dict(value='3.10', kind='cited', source='https://www.python.org/', new_bound=False))
    packet.body.write_text('Using Python 3.10, we establish the rigorous upper bound C <= 3.10.\n')
    check(packet, 'claims', False)


def test_r5_lowercase_i_still_counts(packet):
    packet.bound()
    packet.claims.append(dict(value='0.24', kind='cited', source='https://example.org/x', new_bound=False))
    packet.body.write_text('After simplification, i establish the rigorous upper bound 0.24.\n')
    check(packet, 'claims', False)


@pytest.mark.parametrize('doc', ['We establish C >= 0.25 (rigorous, exact.py).', 'The upper bound and lower bound are both 0.25 (rigorous, exact.py).'])
def test_r5_direction_change_in_doc_needs_replay(packet, doc):
    unchanged_update(packet, 'The upper bound is 0.25 (rigorous, exact.py).')
    packet.write('PROOF.md', doc + '\n')
    check(packet, 'replay', False)


def test_r5_sealed_copy_cannot_hide_wrong_credit(packet):
    credited(packet)
    packet.write('inputs/README.md', 'I credit Mallory in #17.\n')
    packet.write('SHA256SUMS', p.sha(b'I credit Mallory in #17.\n') + '  inputs/README.md\n')
    check(packet, 'credit', False)


def test_r5_html_link_resolves_from_its_document(packet):
    packet.bound()
    packet.write('round/certs/result.txt', 'x\n')
    packet.write('round/review/README.md', '<a href="certs/result.txt">Read the certificate</a>\n')
    check(packet, 'paths', False)


# 11-05 (C44 #294 re-lint): a chained inequality and a directionless live value.
def test_chained_inequality_gives_only_the_bound_direction(packet):
    unchanged_update(packet, 'The upper bound is C <= 0.25 (rigorous, exact.py).')
    packet.write('PROOF.md', '0 <= C <= 0.25 < 0.3 (rigorous, exact.py).\n')
    row = packet.lint()['checks']['replay']
    assert row['status'] == 'PASS' and row['advisory']


def directionless_live(packet, doc):
    live = 'Records the rigorous claim C < 0.3 (exact.py).\n\n    0.25 = 0.25000 < 0.3.\n'
    unchanged_update(packet, live)
    packet.claims.append(dict(value='0.3', kind='rigorous', producer='exact.py', arithmetic='exact', new_bound=True))
    packet.body.write_text(live)
    packet.write('PROOF.md', doc + '\n')


def test_directionless_live_value_takes_the_live_direction(packet):
    directionless_live(packet, 'The rigorous upper bound is C <= 0.25 < 0.3 (exact.py).')
    row = packet.lint()['checks']['replay']
    assert row['status'] == 'PASS' and row['advisory']


def test_directionless_live_value_cannot_flip_direction(packet):
    directionless_live(packet, 'We establish C >= 0.25 (rigorous, exact.py).')
    check(packet, 'replay', False)


# 11-05 (#299, CS FLAG): a PR's own diff credits its author by name when the profile name is empty.
def own_diff_credit(packet, diff):
    credited(packet, 'V. Patankar', 'V. Patankar', 'V. Patankar')
    packet.obj('sources/pr17.json', {'number': 17, 'author': {'login': 'vidigoat', 'name': ''}, 'body': '', 'diff': diff})


def test_own_diff_by_name_is_credit_evidence(packet):
    own_diff_credit(packet, '--- a/README.md\n+++ b/README.md\n+- [68] lower bound 0.446* by [V. Patankar](https://github.com/vidigoat/optimization-records), 26 Oct 2026\n')
    check(packet, 'credit', True)


@pytest.mark.parametrize('diff', [
    '--- a/README.md\n+++ b/README.md\n-- [68] lower bound 0.446* by [V. Patankar](https://example.org/x)\n',  # removed line
    '--- a/README.md\n+++ b/README.md\n+- reviewed with V. Patankar\n',  # mention, not a by-credit
    '--- a/README.md\n+++ b/README.md\n+- by [V. Patankarov](https://example.org/x)\n',  # different name
])
def test_own_diff_without_added_by_credit_is_not_evidence(packet, diff):
    own_diff_credit(packet, diff)
    check(packet, 'credit', False)


def test_initial_does_not_split_a_credit_sentence(packet):
    credited(packet, 'V. Patankar', 'V. Patankar', 'V. Patankar')
    packet.body.write_text('I credit V. Patankar. Older files name the #17 author wrongly; this packet credits V. Patankar.\n')
    check(packet, 'credit', True)


@pytest.mark.parametrize('body, exact', [('import math\nprint(math.isqrt(10), math.gcd(4, 6), math.comb(5, 2))\n', True),
                                         ('from math import isqrt\nprint(isqrt(10))\n', True),
                                         ('import math\nprint(math.isqrt(10), math.sqrt(2))\n', False)])
def test_rigor_exact_integer_math_functions_are_not_floating_point(packet, body, exact):
    # 11-27 (math, A270594 packet): a referee checker using math.isqrt was audited as floating point.
    packet.write('isqrt.py', body)
    packet.write('PROOF.md', 'The leaves are verified.\n')
    packet.steps = [dict(document='PROOF.md', statement='The leaves are verified.', producer='isqrt.py', arithmetic='exact')]
    if exact:
        assert packet.lint()['checks']['rigor']['advisory'] == []
    else:
        advise(packet, 'rigor')


@pytest.mark.parametrize('target, passing', [('rpinho/math-certificates', True), ('rpinho/math-certificates#7', True),
                                             ('rpinho/other-repo', False)])
def test_paths_target_may_be_our_certificates_repo(packet, target, passing):
    # 11-27 (math): an OEIS counterexample's home is rpinho/math-certificates, not a teorth repo.
    packet.meta['target'] = target
    failures = packet.lint()['checks']['paths']['failures']
    assert (not any('target must be' in str(f) for f in failures)) == passing, failures
