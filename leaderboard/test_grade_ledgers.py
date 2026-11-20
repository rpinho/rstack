"""11-20: the scorer reads every Mac's everyday grade ledgers (RH_EVERYDAY_GRADES), one record across files.

Before, it read only the ledger beside its own receipts, so the M4's grades (most of the record) never reached
the ranking or the cost column. Other Macs' ledgers arrive as read-only mirrors (harness/tools/grades-mirror).
"""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

HERE = Path(__file__).resolve().parent
MIRROR = HERE.parent / 'harness/tools/grades-mirror/grades-mirror'


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gl, jc, mr, oa = (load('t_grade_ledgers', 'grade_ledgers.py'), load('t_job_cost', 'job_cost.py'),
                  load('t_model_roles', 'model-roles.py'), load('t_outcome_adapters', 'outcome_adapters.py'))
SONNET = 'claude-sonnet-5-5'
T0 = dt.datetime(2026, 11, 20, 10, 0, tzinfo=dt.timezone.utc).timestamp()
RESET = '2026-11-23T02:59:59+00:00'


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def grade(gid, job, value, **extra):
    return dict(id=gid, job=job, grade=value, model=SONNET, role='batch', source_kind='everyday',
                date='2026-11-20', **extra)


def receipt(directory, job, start=None):
    directory.mkdir(parents=True, exist_ok=True)
    row = dict(job=job, model=SONNET, role='batch', executor='claude', utc='2026-11-20')
    if start is not None:
        row['utc'] = dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat()
    (directory / (job + '.log.selection.json')).write_text(json.dumps(row))


def everyday(receipts, grades):
    observations, _ = oa.collect(None, receipts, mr.canon, mr.obs, grades=grades)
    return sorted((o['case'].split(':', 1)[1], o['outcome']) for o in observations if o['source_kind'] == 'everyday')


@pytest.fixture
def two_macs(tmp_path):
    """The local ledger beside its receipts, and another Mac's ledger mirrored as <slug>.jsonl + <slug>.receipts."""
    local = tmp_path / 'receipts'
    mirror = tmp_path / 'grades-mirror' / 'm4'
    for job in ('a', 'b'):
        receipt(local, job)
    for job in ('c', 'd', 'e'):
        receipt(mirror / 'codex.receipts', job)
    write(local / gl.NAME, [grade('g-a', 'a', 'pass'), grade('g-b', 'b', 'fail')])
    write(mirror / 'codex.jsonl', [
        grade('g-c', 'c', 'pass'),
        grade('g-a', 'a', 'pass'),                                   # the same grade id in both files
        grade('g-d', 'd', 'fail'),
        grade('g-b', 'b', 'retracted', retracted='fail', note='launcher error'),   # retracts the local g-b
        grade('g-e', 'e', 'ungraded'), grade('g-e', 'e', 'partial')])
    return local, mirror


def test_the_union_dedupes_by_id_and_a_retraction_in_one_file_applies_in_every_file(two_macs):
    local, mirror = two_macs
    ledgers = [local / gl.NAME, mirror / 'codex.jsonl']
    rows = gl.rows(ledgers)
    assert sorted(r['id'] for r, _, _ in rows) == ['g-a', 'g-c', 'g-d', 'g-e']
    assert {r['id']: r['grade'] for r, _, _ in rows}['g-e'] == 'partial'
    # The ranking: one observation per grade id, the M4's grades linked to the M4's own receipts.
    assert everyday(local, ledgers) == [('g-a', 'held'), ('g-c', 'held'), ('g-d', 'overturned'), ('g-e', 'partial')]
    # The cost column reads the same record.
    assert sorted(jc.grades(local, ledgers)) == ['a', 'c', 'd', 'e']
    # An "ungraded" row never replaces a grade, whichever file it comes from.
    write(mirror / 'late.jsonl', [grade('g-c', 'c', 'ungraded')])
    assert {r['id']: r['grade'] for r, _, _ in gl.rows(ledgers + [mirror / 'late.jsonl'])}['g-c'] == 'pass'


def test_rh_everyday_grades_takes_paths_and_globs_and_reads_one_file_reached_twice_once(two_macs, monkeypatch):
    local, mirror = two_macs
    (mirror.parent / 'alias').symlink_to(mirror)
    spec = ':'.join([str(local / gl.NAME), str(mirror / '*.jsonl'), str(mirror.parent / 'alias' / 'codex.jsonl')])
    monkeypatch.setenv('RH_EVERYDAY_GRADES', spec)
    assert gl.ledgers(local) == [local / gl.NAME, mirror / 'codex.jsonl']
    observations, _ = oa.collect(None, local, mr.canon, mr.obs)
    assert sum(o['source_kind'] == 'everyday' for o in observations) == 4


def test_a_missing_mirror_never_raises_and_warns_once_per_tick(two_macs, tmp_path, monkeypatch, capsys):
    local, mirror = two_macs
    gone = tmp_path / 'gone' / 'm4' / '*.jsonl'
    ledgers = gl.ledgers(local, spec=f'{local / gl.NAME}:{gone}:{tmp_path / "nope.jsonl"}')
    assert everyday(local, ledgers) == [('g-a', 'held'), ('g-b', 'overturned')]
    assert sorted(jc.grades(local, ledgers)) == ['a', 'b']
    assert jc.per_pass(local, mr.canon, tmp_path / 'nostate', ledgers) == {}
    # The mirror's receipts gone too: its grades stay unlinked, never an error.
    shutil.move(str(mirror / 'codex.receipts'), str(tmp_path / 'moved'))
    assert ('g-c', 'held') not in everyday(local, [local / gl.NAME, mirror / 'codex.jsonl'])
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('RH_EVERYDAY_GRADES', f'{local / gl.NAME}:{gone}')
    assert gl.main(['check']) == 0
    assert 'no everyday grade ledger at' in capsys.readouterr().err
    row = json.loads((tmp_path / 'state' / 'harness-blocks.jsonl').read_text().splitlines()[-1])
    assert (row['gate'], row['outcome']) == ('grades-mirror', 'warn')


def test_a_stale_mirror_is_named(two_macs):
    local, mirror = two_macs
    stamp = mirror / gl.STAMP
    stamp.touch()
    spec = f'{local / gl.NAME}:{mirror / "*.jsonl"}'
    assert gl.problems(spec) == []
    old = time.time() - 3 * 3600
    os.utime(stamp, (old, old))
    assert ['last synced 3.0 h ago' in p for p in gl.problems(spec)] == [True]


def test_unset_reads_only_the_ledger_beside_the_receipts_as_before(two_macs, tmp_path, monkeypatch):
    local, mirror = two_macs
    monkeypatch.delenv('RH_EVERYDAY_GRADES', raising=False)
    assert gl.configured() == ''
    assert gl.ledgers(local) == [local / gl.NAME] and gl.ledgers(None) == []
    observations, _ = oa.collect(None, local, mr.canon, mr.obs)
    assert sorted(o['case'].split(':', 1)[1] for o in observations if o['source_kind'] == 'everyday') == ['g-a', 'g-b']
    assert sorted(jc.grades(local)) == ['a', 'b']
    # The host env file sets it (only that key is read from the file); the real environment wins.
    env = tmp_path / 'env'
    env.write_text(f'RH_OTHER=1\nRH_EVERYDAY_GRADES="{local / gl.NAME}:{mirror / "*.jsonl"}"\n')
    monkeypatch.setenv('RH_ENV_FILE', str(env))
    assert gl.ledgers(local) == [local / gl.NAME, mirror / 'codex.jsonl'] and 'RH_OTHER' not in os.environ
    monkeypatch.setenv('RH_EVERYDAY_GRADES', '')
    assert gl.ledgers(local) == [local / gl.NAME]


def test_a_mirrored_job_is_costed_from_its_own_receipts_and_the_log_manifest(tmp_path):
    local, mirror, state = tmp_path / 'receipts', tmp_path / 'm4', tmp_path / 'state'
    local.mkdir()
    (state / 'usage').mkdir(parents=True)
    jobs = ['j%d' % i for i in range(5)]
    usage, manifest = [], []
    for i, job in enumerate(jobs):
        start = T0 + i * 3600
        receipt(mirror / 'codex.receipts', job, start)
        manifest.append(f'{int(start + 600)}\t./{job}.log')           # the logs stay on the M4
        usage += [(start - 60, 10 + i), (start + 660, 11 + i)]
    (mirror / 'codex.receipts' / gl.MANIFEST).write_text('\n'.join(manifest) + '\n')
    write(mirror / 'codex.jsonl', [grade('g-' + j, j, 'pass' if i < 3 else 'fail') for i, j in enumerate(jobs)])
    (state / 'usage' / 'claude-history.jsonl').write_text(
        ''.join(json.dumps(dict(at=t, resets_at=RESET, weekly_percent=p)) + '\n' for t, p in usage))
    got = jc.per_pass(local, mr.canon, state, [local / gl.NAME, mirror / 'codex.jsonl'])[('batch', mr.canon(SONNET))]
    assert (got['n'], got['passes'], got['pct'], got['per_pass']) == (5, 3, 5.0, round(5 / 3, 3))


@pytest.mark.skipif(not shutil.which('zsh') or not Path('/usr/bin/stat').exists(), reason='needs zsh and BSD stat')
def test_the_mirror_copies_ledgers_receipts_and_log_times_only(tmp_path):
    remote = tmp_path / 'remote-home'
    src = remote / '.local/state/jobs/specs'
    receipt(src, 'x')
    (src / 'x.log').write_text('a long log that is never copied')
    (src / 'x.md').write_text('spec')
    write(src / gl.NAME, [grade('g-x', 'x', 'pass')])
    os.utime(src / 'x.log', (T0, T0))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    # Fakes for the remote side: "HOST:path" is a path under remote-home; the ssh command runs there.
    (bin_dir / 'ssh').write_text(f'#!/bin/sh\nshift\ncd "{remote}" && exec /bin/sh -c "$1"\n')
    (bin_dir / 'rsync').write_text(
        '#!/bin/sh\nargs=""\nfor a in "$@"; do shift; case "$a" in -e) skip=1; continue;; esac\n'
        '  if [ -n "$skip" ]; then skip=; continue; fi\n'
        f'  case "$a" in *:*) a="{remote}/${{a#*:}}";; esac\n  set -- "$@" "$a"\ndone\nexec /usr/bin/rsync "$@"\n')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    dest = tmp_path / 'grades-mirror' / 'm4'
    env = dict(os.environ, GRADES_MIRROR_SSH=str(bin_dir / 'ssh'), GRADES_MIRROR_RSYNC=str(bin_dir / 'rsync'))
    run = subprocess.run([str(MIRROR), 'm4', str(dest), '.local/state/jobs/specs'], env=env,
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    slug = dest / 'local-state-jobs-specs'
    assert json.loads(slug.with_suffix('.jsonl').read_text())['id'] == 'g-x'
    assert sorted(p.name for p in Path(str(slug) + '.receipts').iterdir()) == ['log-mtimes.tsv', 'x.log.selection.json']
    assert gl.log_mtimes(str(slug) + '.receipts') == {'x.log': T0}
    assert (dest / gl.STAMP).exists()
    assert gl.receipts_dir(slug.with_suffix('.jsonl')) == Path(str(slug) + '.receipts')
    # A failed copy keeps the last one and leaves the stamp alone, so the scorer can call it stale.
    (dest / gl.STAMP).unlink()
    run = subprocess.run([str(MIRROR), 'm4', str(dest), 'not/there'], env=env, capture_output=True, text=True)
    assert run.returncode == 1 and not (dest / gl.STAMP).exists() and slug.with_suffix('.jsonl').exists()
