"""Speedups verified before anyone hears about them (harness/speedup.py).

Ricardo, 11-08: make their code faster, not only find bugs. A faster version that changes an
answer is a bug we introduced, a 1.1x gain is noise, and a lab that is already optimizing its own
code gets asked before we duplicate its person's work. The verifier runs here against a real git
repository with a slow and a fast version of one script; nothing touches the network.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bughunt
import outreach
import rh
import speedup
from test_bughunt import NOW, VARIED, cli, draft, lane, lint, target_verdict  # noqa: F401
from test_outreach import env  # noqa: F401  (lane's fixture needs it here too)

SLOW = 'import time\ntime.sleep({})\nprint("{}")\n'
CFG = dict(speedup_min_ratio=1.5, speedup_min_seconds=0.05)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Their repository at one commit, and a speedup directory with a patch against it."""
    trashed = []
    monkeypatch.setattr(speedup.storage, 'trash', lambda p: trashed.append(p))
    monkeypatch.delenv('RH_NO_LOCAL_COMPUTE', raising=False)
    repo = tmp_path / 'their-repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    (repo / 'work.py').write_text(SLOW.format(0.4, '1.000000 2.000000'))
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'theirs')
    base = git(repo, 'rev-parse', 'HEAD').strip()

    def make(name, sleep=0.02, output='1.000000 2.000000', tolerance=None, profile=True, base_sha=None):
        d = tmp_path / name
        d.mkdir()
        (repo / 'work.py').write_text(SLOW.format(sleep, output))
        (d / 'speedup.patch').write_text(git(repo, 'diff'))
        git(repo, 'checkout', '-q', '--', 'work.py')
        if profile:
            (d / 'profile.txt').write_text('work.py:2 sleep 96% of 0.4 s\n')
        (d / 'SPEEDUP.json').write_text(json.dumps(dict(
            target='org/tool', repo=str(repo), base=base_sha or base, patch='speedup.patch',
            command='mkdir -p out && {} work.py > out/result.txt'.format(sys.executable),
            outputs=['out/result.txt'], tolerance=tolerance, runs=3, profile='profile.txt',
            hotspot='time.sleep in work.py, 96% of 0.4 s')))
        return d
    return repo, base, make, trashed


def test_a_faster_version_with_the_same_outputs_passes(project):
    repo, base, make, trashed = project
    d = make('good')
    row = speedup.verify(d, CFG)
    assert row['verdict'] == 'PASS', row['codes']
    assert row['speedup'] > 1.5 and row['median_seconds']['before'] > row['median_seconds']['after']
    assert row['base'] == base and row['peak_bytes']['before']
    assert json.loads((d / 'VERIFY.json').read_text())['verdict'] == 'PASS'
    assert (d / 'outputs/before/out/result.txt').read_text() == (d / 'outputs/after/out/result.txt').read_text()
    assert git(repo, 'worktree', 'list').count('\n') == 1, 'the temporary checkouts are gone'
    assert len(trashed) == 1, 'scratch goes to the Trash, never a recursive delete'


def test_a_faster_version_that_changes_an_answer_is_refused(project):
    row = speedup.verify(project[2]('changed', output='1.000000 2.000001'), CFG)
    assert row['verdict'] == 'FAIL' and any(c.startswith('SPEEDUP_OUTPUT_MISMATCH') for c in row['codes'])


def test_a_stated_numerical_tolerance_is_honoured(project):
    row = speedup.verify(project[2]('close', output='1.000000 2.000001', tolerance={'rel': 1e-5}), CFG)
    assert row['verdict'] == 'PASS', row['codes']


def test_a_gain_nobody_would_notice_is_refused(project):
    row = speedup.verify(project[2]('same-speed', sleep=0.39), CFG)
    assert not any(c.startswith('SPEEDUP_PATCH_FAILS') for c in row['codes'])
    assert any(c.startswith('SPEEDUP_TOO_SMALL') for c in row['codes'])


def test_no_profile_no_speedup(project):
    row = speedup.verify(project[2]('guessed', profile=False), CFG)
    assert any(c.startswith('SPEEDUP_PROFILE_MISSING') for c in row['codes'])


def test_a_patch_that_does_not_apply_to_their_commit_is_refused(project):
    d = project[2]('broken')
    (d / 'speedup.patch').write_text('--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n')
    row = speedup.verify(d, CFG)
    assert any(c.startswith('SPEEDUP_PATCH_FAILS') for c in row['codes'])


def test_the_controller_does_not_run_it(project, monkeypatch):
    monkeypatch.setenv('RH_NO_LOCAL_COMPUTE', '1')
    with pytest.raises(ValueError, match='compute host'):
        speedup.verify(project[2]('anywhere'), CFG)


# ---- the email ------------------------------------------------------------------------------

def verified(tmp_path, name, base='a' * 40, verdict='PASS', patch='diff\n'):
    d = tmp_path / name
    d.mkdir()
    (d / 'speedup.patch').write_text(patch)
    (d / 'SPEEDUP.json').write_text(json.dumps(dict(
        target='org/tool', repo='/x', base=base, patch='speedup.patch', command='true', outputs=['o'],
        runs=3, profile='p', hotspot='f 90% of 10 s')))
    sha = lambda p: hashlib.sha256((d / p).read_bytes()).hexdigest()
    (d / 'VERIFY.json').write_text(json.dumps(dict(
        verdict=verdict, codes=[] if verdict == 'PASS' else ['SPEEDUP_TOO_SMALL: 1.1x'], target='org/tool',
        base=base, manifest_sha256=sha('SPEEDUP.json'), patch_sha256=sha('speedup.patch'))))
    return d


def checked(lane, sha='a' * 40, optimizing=()):
    rh.append(lane[1] / 'TARGETS.jsonl', dict(target='org/tool', verdict='PASS', reasons=[], utc=NOW.isoformat(),
                                              numbers=dict(last_commit_sha=sha, optimizing=list(optimizing))))


def test_a_speedup_email_names_a_verified_current_speedup(lane, tmp_path):
    checked(lane)
    ident, _ = draft(lane, kind='code-speedup', target='org/tool')
    assert 'SPEEDUP_UNVERIFIED' in lint(lane, ident)[1]
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=verified(tmp_path, 'failed', verdict='FAIL'))
    assert 'SPEEDUP_UNVERIFIED' in lint(lane, ident)[1]
    good = verified(tmp_path, 'good')
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=good)
    rc, out = lint(lane, ident)
    assert rc == 0, out
    (good / 'speedup.patch').write_text('diff, edited after verification\n')
    assert 'SPEEDUP_STALE:' in lint(lane, ident)[1]


def test_a_speedup_on_code_they_have_since_changed_is_refused(lane, tmp_path):
    checked(lane, sha='b' * 40)
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=verified(tmp_path, 'old-base'))
    assert 'SPEEDUP_STALE_BASE' in lint(lane, ident)[1]


def test_a_lab_already_working_on_speed_is_asked_first(lane, tmp_path):
    checked(lane, optimizing=['PR #12: Speed up the splicing scan'])
    d = verified(tmp_path, 'dup')
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=d)
    out = lint(lane, ident)[1]
    assert 'SPEEDUP_OVERLAP' in out and 'PR #12' in out
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=d,
                     overlap_checked='asked their developer on 11-09; different module')
    rc, out = lint(lane, ident)
    assert rc == 0 and 'their own speed work' in out


def test_an_extra_scrutiny_reader_gets_a_second_independent_run(lane, tmp_path):
    checked(lane)
    one, two = verified(tmp_path, 'run1'), verified(tmp_path, 'run2')
    other = verified(tmp_path, 'other-patch', patch='a different diff\n')
    ident, _ = draft(lane, to='Contact Gamma', kind='code-speedup', target='org/tool', speedup=[one, other])
    assert 'SECOND_RECHECK_MISSING' in lint(lane, ident)[1], 'two runs of two different patches are not a re-run'
    ident, _ = draft(lane, to='Contact Gamma', kind='code-speedup', target='org/tool', speedup=[one, two])
    out = lint(lane, ident)[1]
    assert 'SECOND_RECHECK_MISSING' not in out and 'TEXT_REVIEW_MISSING' in out


def test_target_check_records_the_commit_and_their_own_speed_work():
    def get(path):
        if path.count('/') == 2 and '?' not in path:
            return dict(archived=False, default_branch='main')
        if '/commits?' in path and 'since=' not in path:
            return [dict(sha='c' * 40, commit=dict(committer=dict(date='2026-10-01T00:00:00Z')))]
        if '/pulls?' in path:
            return [dict(number=7, title='Vectorize the inner loop'), dict(number=8, title='Fix typo')]
        if '/branches?' in path:
            return [dict(name='main'), dict(name='faster-io'), dict(name='docs')]
        return []
    row = bughunt.target_check('org/tool', get=get, clock=dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc))
    assert row['numbers']['last_commit_sha'] == 'c' * 40
    assert row['numbers']['optimizing'] == ['PR #7: Vectorize the inner loop', 'branch faster-io']


def test_old_rows_tagged_code_count_as_bug_reports(lane):
    rows = [dict(channel='email', to_key='A', kind='code', sent=dict(utc='2026-11-07T00:00:00+00:00')),
            dict(channel='email', to_key='A', kind='code-speedup', sent=dict(utc='2026-11-08T00:00:00+00:00'))]
    assert sorted(outreach.stats(rows)['total']['by_kind']) == ['code-bug', 'code-speedup']
    assert bughunt.kind_in('code-speedup', ['code']) and not bughunt.kind_in('paper', ['code'])


def test_one_email_with_bugs_and_a_speedup_carries_both_kinds_and_both_rules(lane, tmp_path):
    """11-08: a batched email to one person held two refereed bugs and a verified speedup."""
    checked(lane)
    ref1, ref2 = (tmp_path / 'ref1', tmp_path / 'ref2')
    for d in (ref1, ref2):
        d.mkdir()
        (d / 'VERDICTS.md').write_text('| B1 | CONFIRMED |')
    ident, _ = draft(lane, kind=['code-bug', 'code-speedup'], target='org/tool')
    assert 'SPEEDUP_UNVERIFIED' in lint(lane, ident)[1], 'the speedup rules apply to a mixed email'
    one = verified(tmp_path, 'run1')
    ident, _ = draft(lane, to='Contact Gamma', kind=['code-bug', 'code-speedup'], target='org/tool',
                     speedup=one, recheck=[ref1, ref2])
    out = lint(lane, ident)[1]
    assert 'verified runs of the same patch' in out and 're-checks with a confirmed verdict' not in out
    row = outreach.current(lane[1], rh)[ident]
    assert row['kinds'] == ['code-bug', 'code-speedup']
    sent = dict(row, status='sent', sent=dict(utc=NOW.isoformat(), message_id='x', via='api'))
    stats = outreach.stats([sent])['total']
    assert stats['sent'] == 1, 'one email, counted once'
    assert stats['by_kind']['code-bug']['sent'] == stats['by_kind']['code-speedup']['sent'] == 1


def bundle(tmp_path, name, patch):
    import tarfile
    src = tmp_path / (name + '-src')
    src.mkdir()
    (src / 'patch.diff').write_text(patch)
    (src / 'README.md').write_text('How to apply it and the benchmark.\n')
    out = tmp_path / (name + '.tar.gz')
    with tarfile.open(str(out), 'w:gz') as tar:
        tar.add(str(src / 'patch.diff'), arcname='bundle/patch.diff')
        tar.add(str(src / 'README.md'), arcname='bundle/README.md')
    return out


def test_the_verified_patch_bundle_is_not_held_to_the_paper_result_checks(lane, tmp_path):
    """11-08: the patch bundle a recipient asked for failed the adversarial-review and slop-question
    checks meant for result claims. The fixture science checker fails any attachment without that
    question, so a PASS here means the bundle was not sent to it."""
    checked(lane)
    config_text = (lane[1] / 'OUTREACH.toml').read_text()
    (lane[1] / 'OUTREACH.toml').write_text(config_text + 'science_checks = true\n')
    d = verified(tmp_path, 'v')
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=d,
                     attach=bundle(tmp_path, 'same', 'diff\n'))
    rc, out = lint(lane, ident)
    assert rc == 0, out
    assert 'is the verified speedup patch' in out
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=d,
                     attach=bundle(tmp_path, 'edited', 'diff, edited after verification\n'))
    assert 'fixture attachment needs useful or slop question' in lint(lane, ident)[1]
    extra = tmp_path / 'results.txt'
    extra.write_text('A table of timings.\n')
    ident, _ = draft(lane, kind='code-speedup', target='org/tool', speedup=d,
                     attach=[bundle(tmp_path, 'again', 'diff\n'), extra])
    assert 'fixture attachment needs useful or slop question' in lint(lane, ident)[1], \
        'anything else attached is still checked'
