"""Offline harvest safety, corruption, scheduling and alert regressions."""
import base64
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import harvest as h
import harvest_reader as reader
import pods
import rh
import storage

ORIGINAL_PROXY = h.Proxy
ORIGINAL_TRASH = storage.trash  # the autouse fixture replaces it with a reversible move


@pytest.fixture(autouse=True)
def no_live(monkeypatch, tmp_path):
    monkeypatch.setattr(h, 'notify', Mock(return_value=True))
    monkeypatch.setattr(h, 'Proxy', Mock(side_effect=AssertionError('live SSH forbidden')))
    monkeypatch.setattr(h.shutil, 'disk_usage', lambda _: SimpleNamespace(free=100_000_000_000))
    # Tests use reversible temporary moves, never the host Trash service.
    def trash(path):
        dest = tmp_path / 'test-trash' / path.name
        dest.parent.mkdir(exist_ok=True)
        path.rename(dest)
    monkeypatch.setattr(h.storage, 'trash', trash)
    def trash(directory):
        destination = tmp_path / 'Trash' / directory.name
        destination.parent.mkdir(exist_ok=True)
        directory.rename(destination)
    monkeypatch.setattr(h, 'trash_snapshot', trash)


@pytest.fixture
def setup(tmp_path):
    now = [dt.datetime(2026, 11, 2, 23, tzinfo=dt.timezone.utc)]
    clock = SimpleNamespace(now=lambda: now[0].isoformat())
    pod = dict(name='pod-a', pod_id='id1', lane='team', results=['/workspace/worker-a'],
               harvest_dest=str(tmp_path / 'lanes/team/results/pod-harvest'), ssh_target=('id1-a' + chr(64) + 'ssh.runpod.io'),
               vcpus=32, gpus=0, dollars_per_hour=.96, owner_note='fixture')
    content = {'/workspace/worker-a/results/x.json': b'{"result":42}\n'}
    class Fake:
        calls = []
        extra = []
        corrupt = False
        interrupted = False
        deadline = 7200
        def __init__(self, pod):
            self.pod = pod
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def manifest(self):
            for p, b in content.items():
                yield dict(path=p, size=len(b), sha256=hashlib.sha256(b).hexdigest())
            yield from self.extra
            yield dict(end=True, deadline_seconds=self.deadline)
        def download(self, item, target):
            self.calls.append(item['path'])
            target.write(b'corrupt' if self.corrupt else content[item['path']])
            if self.interrupted:
                raise OSError('private SSH banner MUST NOT APPEAR')
    return tmp_path, pod, content, Fake, clock, now


def run(setup, **kw):
    root, pod, _, fake, clock, _ = setup
    with contextlib.redirect_stdout(io.StringIO()):
        return h.harvest_one(root, pod, clock, transport=fake, **kw)


def test_incremental_preserves_revisions_and_deleted_sources(setup):
    root, pod, content, fake, clock, now = setup
    assert run(setup)['verified']
    first = list(Path(pod['harvest_dest']).rglob('x.json'))[0]
    assert run(setup)['unchanged'] == 1
    assert len(fake.calls) == 1
    assert first.read_bytes() == b'{"result":42}\n'
    content['/workspace/worker-a/results/x.json'] = b'new value'
    assert run(setup)['files'] == 1
    assert any(p.read_bytes() == b'{"result":42}\n' for p in Path(pod['harvest_dest']).rglob('x.json'))
    content.clear()
    assert run(setup)['verified']
    assert len(list(Path(pod['harvest_dest']).rglob('x.json'))) == 2
    index = json.loads((Path(pod['harvest_dest']) / 'pod-a/INDEX.json').read_text())
    assert '/workspace/worker-a/results/x.json' in index['files']


@pytest.mark.parametrize('kind', ['corrupt', 'interrupted'])
def test_bad_transfer_is_never_committed_and_old_copy_survives(setup, kind):
    root, pod, content, fake, *_ = setup
    assert run(setup)['verified']
    content['/workspace/worker-a/results/x.json'] = b'changed'
    setattr(fake, kind, True)
    h.notify.return_value = True
    row = run(setup)
    assert not row['verified'] and row['files'] == 0
    assert len(list(Path(pod['harvest_dest']).rglob('x.json'))) == 1
    assert not list(Path(pod['harvest_dest']).rglob('*.tmp'))
    assert 'private SSH' not in (h.state_root(root) / 'HARVEST.jsonl').read_text()


def test_unchanged_local_copy_is_rehashed_and_repaired(setup):
    root, pod, content, fake, *_ = setup
    run(setup)
    saved = list(Path(pod['harvest_dest']).rglob('x.json'))[0]
    saved.write_bytes(b'local corruption')
    assert run(setup)['files'] == 1
    assert len(fake.calls) == 2
    assert saved.read_bytes() == b'local corruption'  # never overwrite history


def test_guards_skips_are_logged_without_download(setup):
    root, pod, _, fake, *_ = setup
    fake.extra = [dict(path='/workspace/worker-a/big', skip='over_200_MB', size=h.MAX_BYTES+1),
                  dict(path='/workspace/worker-a/movie.mp4', skip='media', size=12)]
    row = run(setup)
    assert row['verified'] and len(row['skipped']) == 2
    assert fake.calls == ['/workspace/worker-a/results/x.json']


@pytest.mark.parametrize('bad', ['/workspace', '/workspace/', '/workspace/../root', '/etc', '/workspace/a/../b', '/workspace/a\nx'])
def test_invalid_paths_rejected_before_transport(setup, bad):
    root, pod, _, fake, *_ = setup
    pod['results'] = [bad]
    assert not run(setup)['verified']
    assert not fake.calls


def test_escape_and_local_symlink_are_refused(setup, tmp_path):
    root, pod, _, fake, *_ = setup
    fake.extra = [dict(path='/workspace/other/private', size=1, sha256='a'*64)]
    assert not run(setup)['verified']
    assert fake.calls == ['/workspace/worker-a/results/x.json']
    fake.extra = []
    pod['harvest_dest'] += '-symlink-test'
    dest = Path(pod['harvest_dest'])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'pod-a').symlink_to(tmp_path / 'elsewhere')
    assert not run(setup)['verified']
    assert not (tmp_path / 'elsewhere').exists()


def test_alert_after_two_failures_throttles_retries_and_resets(setup):
    root, pod, content, fake, clock, now = setup
    fake.extra = [dict(path='/workspace/worker-a/missing', error='unavailable')]
    h.notify.side_effect = None
    h.notify.return_value = True
    run(setup)
    h.notify.assert_not_called()
    now[0] += dt.timedelta(minutes=15)
    run(setup)
    assert h.notify.call_count == 1
    run(setup)
    assert h.notify.call_count == 1
    now[0] += dt.timedelta(hours=6)
    h.notify.return_value = False
    run(setup)
    h.notify.return_value = True
    run(setup)
    assert h.notify.call_count == 3
    fake.extra = []
    run(setup)
    fake.extra = [dict(path='/workspace/worker-a/missing', error='unavailable')]
    now[0] += dt.timedelta(hours=6)
    run(setup)
    assert h.notify.call_count == 3


def test_lint_freshness_missing_and_replaced_pod(setup):
    root, pod, _, fake, clock, now = setup
    assert '45 min' in h.lint(root, [pod], clock)[0]
    run(setup)
    assert not h.lint(root, [pod], clock)
    now[0] += dt.timedelta(minutes=45)
    assert not h.lint(root, [pod], clock)
    now[0] += dt.timedelta(seconds=1)
    assert h.lint(root, [pod], clock)
    pod['pod_id'] = 'replacement'
    now[0] -= dt.timedelta(minutes=30)
    assert h.lint(root, [pod], clock)
    pod.pop('results')
    assert any('no results' in s for s in h.lint(root, [pod], clock))
    lane = root / 'lanes/restricted-a'
    lane.mkdir(parents=True)
    assert pods.lint(lane, clock) == []


def test_deadline_windows_dedup_and_restart(setup):
    root, pod, _, fake, clock, now = setup
    pod['ends_utc'] = (now[0] + dt.timedelta(minutes=21)).isoformat()
    with contextlib.redirect_stdout(io.StringIO()):
        assert h.run(root, [pod], clock, due=True, transport=fake) == 0
        assert not fake.calls
        now[0] += dt.timedelta(minutes=1)
        assert h.run(root, [pod], clock, due=True, transport=fake) == 0
        assert len(fake.calls) == 1
        h.run(root, [pod], clock, due=True, transport=fake)
        logs = h.rows(h.state_root(root) / 'HARVEST.jsonl')
        assert len(logs) == 1
        now[0] += dt.timedelta(minutes=15)
        h.run(root, [pod], clock, due=True, transport=fake)
        assert len(h.rows(h.state_root(root) / 'HARVEST.jsonl')) == 2
        now[0] += dt.timedelta(minutes=5)
        h.run(root, [pod], clock, due=True, transport=fake)
        assert len(h.rows(h.state_root(root) / 'HARVEST.jsonl')) == 2


def test_discovered_deadline_used_locally(setup):
    root, pod, _, fake, clock, now = setup
    run(setup)
    history = h.rows(h.state_root(root) / 'HARVEST.jsonl')
    assert h.latest_deadline(pod, history) == now[0] + dt.timedelta(hours=2)


def test_reader_size_media_symlinks_and_specials(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    normal = tmp_path / 'x.json'
    normal.write_bytes(b'{}')
    assert reader.inspect(str(normal))['sha256'] == hashlib.sha256(b'{}').hexdigest()
    huge = tmp_path / 'huge'
    with huge.open('wb') as f:
        f.truncate(h.MAX_BYTES+1)
    assert reader.inspect(str(huge))['skip'] == 'over_200_MB'
    for name, data in [('x.MP4', b'anything'), ('hidden', b'RIFF1234WAVE...')]:
        p = tmp_path / name
        p.write_bytes(data)
        assert reader.inspect(str(p))['skip'] == 'media'
    symlink = tmp_path / 'link'
    symlink.symlink_to(normal)
    with pytest.raises(OSError):
        reader.inspect(str(symlink))
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    assert reader.inspect(str(fifo))['skip'] == 'special'
    found = list(reader.manifest([str(tmp_path)]))
    assert any(r.get('skip') == 'symlink' for r in found)


def test_timer_inventory_only_reads_sleep_processes(monkeypatch):
    probe = Mock(return_value=SimpleNamespace(stdout='12 4 sleep 86400\n30 1 sleep 9999\n50 5 sleep 60\n'))
    monkeypatch.setattr(reader.subprocess, 'run', probe)
    assert reader.deadline_seconds() == 86388
    assert probe.call_args.args[0] == ['ps', '-C', 'sleep', '-o', 'etimes=,ppid=,args=']


def test_cli_registration_requires_paths_and_accepts_deadline(setup, monkeypatch):
    root, pod, _, fake, clock, now = setup
    (root / 'lanes/theory').mkdir(parents=True)
    monkeypatch.setattr(pods, 'probe', Mock(return_value=dict(vcpus=32, gpus=0)))
    args = ['--root', str(root), 'pods', 'add', 'theory1', '--pod-id', 'theoryid',
            '--ssh-target', ('theoryid-a' + chr(64) + 'ssh.runpod.io'), '--lane', 'theory',
            '--dollars-per-hour', '1', '--owner-note', 'fixture']
    with pytest.raises(SystemExit):
        rh.main(args)
    assert not pods.probe.called
    assert rh.main(args + ['--results', '/workspace/theory/results', '--harvest-dest',
        str(root / 'lanes/theory/results'), '--ends-utc', '2026-11-03T12:00:00Z']) == 0
    saved = pods.registry(root)[0]
    assert saved['ends_utc'] == '2026-11-03T12:00:00Z'


def test_check_schedules_maintenance_without_sampling(setup, monkeypatch):
    root, pod, _, fake, clock, now = setup
    (root / 'pods.json').write_text(json.dumps([pod]))
    called = []
    monkeypatch.setattr(pods, 'check', lambda *_: called.append('check') or 0)
    monkeypatch.setattr(pods.pod_maintenance, 'schedule', lambda *_: called.append('schedule') or 1)
    monkeypatch.setattr(h, 'run', Mock(side_effect=AssertionError('harvest must be independent')))
    assert rh.main(['--root', str(root), 'pods', 'check']) == 1
    assert called == ['schedule']


@pytest.mark.parametrize('with_exclusion', [False, True])
def test_actual_pty_protocol_binary_frames_without_remote_files(tmp_path, monkeypatch, with_exclusion):
    """Real local PTY exercises terminal echo, CRLF and shell input limits."""
    import pty
    proxy_class = ORIGINAL_PROXY
    results = tmp_path / 'results'
    results.mkdir()
    data = bytes(range(256)) * 800
    (results / 'result.bin').write_bytes(data)
    for i in range(20):
        (results / ('extra%02d.json' % i)).write_bytes(b'{}')
    deep = results / ('d' * 180)
    deep.mkdir()
    (deep / 'long-request.json').write_bytes(b'{}')
    declarations = []
    if with_exclusion:
        states = results / 'bulk/native_states'
        states.mkdir(parents=True)
        (states / 'arm').write_bytes(b'states are omitted')
        declarations = [bulk_exclusion(path='bulk/native_states')]
    source = Path(reader.__file__).read_text().replace("path.startswith('/workspace/')", "path.startswith(" + repr(str(tmp_path) + '/') + ")")
    real_popen = subprocess.Popen
    master, slave = pty.openpty()
    child = real_popen(['/bin/bash', '--noprofile', '--norc', '-i'], stdin=slave, stdout=slave, stderr=slave,
                       env=dict(os.environ, PS1='# ', PS2='> '))
    os.close(slave)
    wrapper = SimpleNamespace(stdin=os.fdopen(os.dup(master), 'wb', buffering=0),
        stdout=os.fdopen(master, 'rb', buffering=0), poll=child.poll, wait=child.wait, kill=child.kill)
    popen = Mock(return_value=wrapper)
    monkeypatch.setattr(h.subprocess, 'Popen', popen)
    monkeypatch.setattr(Path, 'read_text', lambda *_a, **_k: source)
    try:
        with proxy_class(dict(results=[str(results)], ssh_target=('offline' + chr(64) + 'ssh.runpod.io'),
                              harvest_exclude_paths=declarations), timeout=15) as proxy:
            count, final = 0, None
            exclusions = []
            for item in proxy.manifest():
                if item.get('skip') == 'excluded_path':
                    exclusions.append(item)
                elif 'path' in item:
                    target = io.BytesIO()
                    proxy.download(item, target)
                    expected = data if item['path'].endswith('result.bin') else b'{}'
                    assert target.getvalue() == expected
                    count += 1
                final = item
            assert count == 22
            assert final['end'] is True
            if with_exclusion:
                assert exclusions == [dict(path=str(states), skip='excluded_path', files=1,
                                           bytes=len(b'states are omitted'), present=True)]
            else:
                assert not exclusions
        argv = popen.call_args.args[0]
        assert 'StrictHostKeyChecking=yes' in argv
        assert not list(results.glob('*.py'))
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def test_scope_change_invalidates_freshness(setup):
    root, pod, _, fake, clock, now = setup
    run(setup)
    assert not h.lint(root, [pod], clock)
    pod['results'].append('/workspace/other')
    assert h.lint(root, [pod], clock)


def test_per_pod_lock_logs_one_failure_and_cli_returns_nonzero(setup, monkeypatch, capsys):
    import fcntl
    root, pod, _, fake, *_ = setup
    (root / 'pods.json').write_text(json.dumps([pod]))
    monkeypatch.setattr(h, 'Proxy', fake)
    base = Path(pod['harvest_dest']) / pod['name']
    base.mkdir(parents=True)
    with (base / '.harvest.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert rh.main(['--root', str(root), 'pods', 'harvest', pod['name']]) == 1
        assert not fake.calls
        history = h.rows(h.state_root(root) / 'HARVEST.jsonl')
        assert len(history) == 1
        assert history[0]['verified'] is False
        assert history[0]['errors'] == [dict(error='PodBusy')]
        assert history[0]['reason'] == 'manual'
        assert h.identity(history[0], pod)
        assert json.loads(capsys.readouterr().out) == history[0]
    # The busy attempt does not satisfy freshness or prevent the next copy.
    assert h.lint(root, [pod], setup[4])
    assert rh.main(['--root', str(root), 'pods', 'harvest', pod['name']]) == 0
    history = h.rows(h.state_root(root) / 'HARVEST.jsonl')
    assert len(history) == 2 and history[-1]['verified'] is True


def test_due_failed_harvest_retries_and_new_timer_generation(setup):
    root, pod, content, fake, clock, now = setup
    pod['ends_utc'] = (now[0] + dt.timedelta(minutes=20)).isoformat()
    fake.corrupt = True
    with contextlib.redirect_stdout(io.StringIO()):
        assert h.run(root, [pod], clock, due=True, transport=fake) == 1
        fake.corrupt = False
        assert h.run(root, [pod], clock, due=True, transport=fake) == 0
        assert len(fake.calls) == 2
        # Renewal is a new generation, rather than a permanently satisfied lead.
        pod['ends_utc'] = (now[0] + dt.timedelta(minutes=35)).isoformat()
        now[0] += dt.timedelta(minutes=15)
        h.run(root, [pod], clock, due=True, transport=fake)
    assert len(h.rows(h.state_root(root) / 'HARVEST.jsonl')) == 3


def test_deadline_discovery_jitter_is_stable(setup):
    root, pod, _, fake, clock, now = setup
    run(setup)
    first = h.latest_deadline(pod, h.rows(h.state_root(root) / 'HARVEST.jsonl'))
    now[0] += dt.timedelta(minutes=15)
    fake.deadline -= 900 - 1
    run(setup)
    assert h.latest_deadline(pod, h.rows(h.state_root(root) / 'HARVEST.jsonl')) == first


def test_live_transport_startup_failure_reaps_local_child(monkeypatch):
    from unittest.mock import MagicMock
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr(h.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(ORIGINAL_PROXY, 'read', Mock(side_effect=TimeoutError('fixture')))
    monkeypatch.setattr(ORIGINAL_PROXY, 'send', Mock(side_effect=TimeoutError('fixture')))
    with pytest.raises(TimeoutError):
        ORIGINAL_PROXY(dict(results=['/workspace/results'], ssh_target=('offline' + chr(64) + 'ssh.runpod.io')))
    child.kill.assert_called_once()
    child.wait.assert_called_once()
    child.stdin.close.assert_called_once()
    child.stdout.close.assert_called_once()


def test_partial_inventory_preserves_hash_confirmed_progress_across_runs(setup):
    root, pod, content, fake, clock, now = setup
    normal_manifest = fake.manifest
    def interrupted(self):
        yield next(iter(normal_manifest(self)))
        raise OSError('fixture interruption')
    fake.manifest = interrupted
    result = run(setup)
    assert not result['verified'] and result['files'] == 1
    index_path = Path(pod['harvest_dest']) / 'pod-a/INDEX.json'
    assert '/workspace/worker-a/results/x.json' in json.loads(index_path.read_text())['files']
    fake.manifest = normal_manifest
    result = run(setup)
    assert result['verified'] and result['unchanged'] == 1
    assert len(fake.calls) == 1


def test_notification_throttle_is_per_pod_across_scope_changes(setup):
    root, pod, _, fake, clock, now = setup
    fake.extra = [dict(path='/workspace/worker-a/missing', error='unavailable')]
    run(setup)
    run(setup)
    assert h.notify.call_count == 1
    pod['results'].append('/workspace/new')
    run(setup)
    run(setup)
    assert h.notify.call_count == 1


def test_independent_pods_copy_concurrently_and_log_separately(setup):
    import threading
    root, pod, _, fake, clock, now = setup
    barrier = threading.Barrier(2, timeout=2)
    original = fake.manifest
    def synchronized(self):
        barrier.wait()
        yield from original(self)
    fake.manifest = synchronized
    other = dict(pod, name='pod-b', pod_id='other')
    with contextlib.redirect_stdout(io.StringIO()):
        assert h.run(root, [pod, other], clock, transport=fake) == 0
    logged = h.rows(h.state_root(root) / 'HARVEST.jsonl')
    assert {r['pod'] for r in logged} == {'pod-a', 'pod-b'}
    assert all(r['verified'] for r in logged)


@pytest.mark.parametrize('phase', ['scope', 'start_clock', 'startup', 'manifest', 'close', 'commit', 'end_clock'])
def test_exception_boundary_logs_one_failed_attempt_and_nonzero(setup, monkeypatch, phase):
    root, pod, _, fake, clock, _ = setup
    failure = Mock(side_effect=RuntimeError('private transport detail MUST NOT APPEAR'))
    if phase == 'scope':
        monkeypatch.setattr(h, 'scope', failure)
    elif phase == 'start_clock':
        monkeypatch.setattr(clock, 'now', Mock(side_effect=[RuntimeError('clock'), setup[5][0].isoformat()]))
    elif phase == 'startup':
        monkeypatch.setattr(fake, '__init__', failure)
    elif phase == 'manifest':
        original = fake.manifest
        def broken_manifest(self):
            yield next(iter(original(self)))
            raise RuntimeError('private transport detail MUST NOT APPEAR')
        monkeypatch.setattr(fake, 'manifest', broken_manifest)
    elif phase == 'close':
        monkeypatch.setattr(fake, '__exit__', failure)
    elif phase == 'commit':
        monkeypatch.setattr(h, 'atomic', failure)
    else:
        fake.deadline = None  # no intermediate clock read for deadline metadata
        monkeypatch.setattr(clock, 'now', Mock(side_effect=[setup[5][0].isoformat(), RuntimeError('clock')]))
    assert h.run(root, [pod], clock, name=pod['name'], transport=fake) == 1
    log = h.state_root(root) / 'HARVEST.jsonl'
    history = h.rows(log)
    assert len(history) == 1
    row = history[0]
    assert row['pod'] == pod['name'] and row['verified'] is False
    assert row['errors'] == [dict(error='RuntimeError')]
    assert 'private transport detail' not in log.read_text()
    h.timestamp(row['utc'])
    if phase in ('manifest', 'close', 'commit', 'end_clock'):
        assert row['files'] == 1
        assert list(Path(pod['harvest_dest']).rglob('x.json'))


@pytest.mark.parametrize('error', [KeyboardInterrupt, lambda: SystemExit(0)])
@pytest.mark.parametrize('phase', ['manifest', 'end_clock'])
def test_cancellation_logs_once_then_propagates_nonzero(setup, monkeypatch, error, phase):
    root, pod, _, fake, clock, _ = setup
    if phase == 'manifest':
        monkeypatch.setattr(fake, 'manifest', Mock(side_effect=error()))
    else:
        fake.deadline = None
        monkeypatch.setattr(clock, 'now', Mock(side_effect=[setup[5][0].isoformat(), error()]))
    with pytest.raises((KeyboardInterrupt, SystemExit)) as raised:
        h.run(root, [pod], clock, name=pod['name'], transport=fake)
    if isinstance(raised.value, SystemExit):
        assert raised.value.code != 0
    history = h.rows(h.state_root(root) / 'HARVEST.jsonl')
    assert len(history) == 1 and history[0]['verified'] is False
    assert history[0]['errors'][0]['error'] in ('KeyboardInterrupt', 'SystemExit')


def test_log_write_failure_propagates_without_retry_or_success(setup, monkeypatch):
    root, pod, _, fake, clock, _ = setup
    sink = Mock(side_effect=OSError('log unavailable'))
    original = h.append
    monkeypatch.setattr(h, 'append', lambda path, row: sink(path, row)
                        if path.name == 'HARVEST.jsonl' else original(path, row))
    with pytest.raises(OSError, match='log unavailable'):
        h.run(root, [pod], clock, name=pod['name'], transport=fake)
    sink.assert_called_once()
    h.notify.assert_not_called()


def test_state_root_requires_explicit_override_even_for_home_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    native = tmp_path / '.local/share/research-harness'
    native.mkdir(parents=True)
    alias = tmp_path / 'alias'
    alias.symlink_to(native, target_is_directory=True)
    production_state = tmp_path / '.local/state/research-harness'
    assert h.state_root(native) == native / '.harvest-state'
    assert h.state_root(alias) == alias / '.harvest-state'
    isolated = tmp_path / 'isolated'
    assert h.state_root(isolated) == isolated / '.harvest-state'
    monkeypatch.setenv('RH_HARVEST_STATE', str(production_state))
    assert h.state_root(native) == production_state


def manifests(setup):
    return h.snapshots(Path(setup[1]['harvest_dest']) / setup[1]['name'], setup[1])


def test_unchanged_snapshot_is_complete_hardlinked_and_fully_hashed(setup, monkeypatch):
    content = setup[2]
    content['/workspace/worker-a/results/other.json'] = b'another file'
    first = run(setup)
    calls = []
    original = h.digest
    def tracking(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(h, 'digest', tracking)
    second = run(setup)
    assert second['verified'] and second['files'] == second['bytes'] == 0
    assert second['linked_files'] == second['verified_files'] == 2
    assert second['linked_bytes'] == second['verified_bytes'] == sum(map(len, content.values()))
    old, new = Path(first['snapshot']), Path(second['snapshot'])
    for source, data in content.items():
        a, b = old / source.lstrip('/'), new / source.lstrip('/')
        assert a.stat().st_ino == b.stat().st_ino and b.read_bytes() == data
        assert b in calls  # final path itself is rehashed, in addition to temp
    record = json.loads((new / 'MANIFEST.json').read_text())
    assert all(item['stored'].startswith(str(new.relative_to(new.parent.parent)) + '/')
               for item in record['files_index'].values())


def test_same_size_changed_hash_copies_and_does_not_modify_linked_history(setup):
    source = next(iter(setup[2]))
    first = run(setup)
    setup[2][source] = b'x' * len(setup[2][source])
    second = run(setup)
    a, b = Path(first['snapshot']) / source.lstrip('/'), Path(second['snapshot']) / source.lstrip('/')
    assert second['verified'] and second['files'] == 1 and second['linked_files'] == 0
    assert a.stat().st_ino != b.stat().st_ino
    assert a.read_bytes() != b.read_bytes()


def test_final_verification_detects_corrupted_hardlink(setup, monkeypatch):
    first = run(setup)
    source = next(iter(setup[2]))
    def corrupt_on_close(self, *_):
        (Path(first['snapshot']) / source.lstrip('/')).write_bytes(b'corrupt after linking')
    monkeypatch.setattr(setup[3], '__exit__', corrupt_on_close)
    row = run(setup)
    assert not row['verified'] and row['linked_files'] == 1
    assert row['errors'] == [dict(path=source, error='snapshot_verification_failed')]


def test_failed_latest_snapshot_supplies_only_freshly_rehashed_files(setup):
    source = next(iter(setup[2]))
    first = run(setup)
    setup[2][source] = b'changed'
    setup[3].extra = [dict(path='/workspace/worker-a/missing', error='unavailable')]
    assert not run(setup)['verified']
    setup[3].extra = []
    last = run(setup)
    assert last['verified'] and last['files'] == 0 and last['linked_files'] == 1
    assert last['previous_verified_snapshot'] == first['snapshot']


def test_retention_keeps_newest_two_and_logs_removal(setup):
    runs = [run(setup) for _ in range(4)]
    assert [p for p, _ in manifests(setup)] == [Path(r['snapshot']) for r in runs[-2:]]
    removed = [r for r in h.rows(h.state_root(setup[0]) / 'HARVEST.jsonl')
               if r.get('event') == 'SNAPSHOT_REMOVED']
    assert [r['path'] for r in removed] == [r['snapshot'] for r in runs[:2]]
    assert all(r['files'] == 1 and r['bytes'] == len(next(iter(setup[2].values()))) for r in removed)


def test_retention_never_removes_unique_revisions_or_deleted_files(setup):
    source = next(iter(setup[2]))
    unique = run(setup)
    setup[2][source] = b'new revision'
    older = run(setup)
    run(setup)
    run(setup)
    assert Path(unique['snapshot']).exists()
    assert not Path(older['snapshot']).exists()
    setup[2].clear()
    run(setup)
    run(setup)
    run(setup)
    assert Path(unique['snapshot']).exists()
    assert any((p / source.lstrip('/')).exists() for p, _ in manifests(setup))


def test_retention_checks_actual_payload_and_rehashes_kept_copies(setup):
    first = run(setup)
    # An unindexed file is still unique data and prevents pruning.
    (Path(first['snapshot']) / 'unique.txt').write_text('preserve me')
    run(setup)
    run(setup)
    assert Path(first['snapshot']).exists()
    # A formerly verified but corrupted kept file cannot prove redundancy.
    source = next(iter(setup[2]))
    directory = manifests(setup)[-1][0]
    (directory / source.lstrip('/')).write_bytes(b'corrupt')
    h.retain(directory.parent.parent, setup[1], h.state_root(setup[0]) / 'HARVEST.jsonl',
             setup[4].now(), {})
    assert Path(first['snapshot']).exists()


def test_retention_protects_legacy_manifest_references(setup):
    first = run(setup)
    second = run(setup)
    p = Path(second['snapshot']) / 'MANIFEST.json'
    record = json.loads(p.read_text())
    record['snapshot_format'] = 1
    source = next(iter(setup[2]))
    record['files_index'][source]['stored'] = str(Path(first['snapshot']).relative_to(p.parent.parent.parent)) + '/' + source.lstrip('/')
    p.write_text(json.dumps(record))
    (p.parent / 'unique-legacy.txt').write_text('keeps this dependent manifest')
    run(setup)
    run(setup)
    assert Path(first['snapshot']).exists() and Path(second['snapshot']).exists()


def test_low_disk_skips_unchanged_and_large_changes_alerts_once_daily(setup, monkeypatch):
    first = run(setup)
    small = '/workspace/worker-a/results/new.json'
    setup[2][small] = b'small changed result'
    setup[3].extra = [dict(path='/workspace/worker-a/results/checkpoint.pth',
                          size=50_000_000, sha256='a' * 64)]
    monkeypatch.setattr(h.shutil, 'disk_usage', lambda _: SimpleNamespace(free=h.DISK_FLOOR_BYTES-1))
    row = run(setup)
    assert not row['verified'] and row['low_disk'] and not row['errors']
    assert row['files'] == 1 and row['bytes'] == len(setup[2][small])
    assert row['linked_files'] == 0 and len(row['skipped_low_disk']) == 2
    assert set(setup[3].calls) == {next(iter(setup[2])), small}
    alert = setup[0] / 'alerts/harvest-low-disk-pod-a'
    initial = alert.read_bytes()
    setup[5][0] += dt.timedelta(minutes=15)
    run(setup)
    assert alert.read_bytes() == initial
    setup[5][0] += dt.timedelta(days=1)
    run(setup)
    assert alert.read_bytes() != initial
    assert Path(first['snapshot']).exists()


def test_disk_floor_is_checked_before_each_file_and_exact_threshold_allowed(setup, monkeypatch):
    source = next(iter(setup[2]))
    setup[2]['/workspace/worker-a/results/second.json'] = b'new'
    free = iter([h.DISK_FLOOR_BYTES, h.DISK_FLOOR_BYTES, h.DISK_FLOOR_BYTES-1])
    monkeypatch.setattr(h.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(free)))
    row = run(setup)
    assert not row['verified'] and row['low_disk']
    assert row['files'] == 2  # both are new and under 50 MB
    assert row['verified_files'] == 2


def test_link_failure_falls_back_to_verified_copy(setup, monkeypatch):
    run(setup)
    monkeypatch.setattr(h.os, 'link', Mock(side_effect=OSError('unsupported')))
    row = run(setup)
    assert row['verified'] and row['files'] == 1 and row['linked_files'] == 0


def test_empty_inventory_still_obeys_disk_floor(setup, monkeypatch):
    setup[2].clear()
    monkeypatch.setattr(h.shutil, 'disk_usage', lambda _: SimpleNamespace(free=h.DISK_FLOOR_BYTES-1))
    row = run(setup)
    assert row['low_disk'] and not row['verified'] and not row['errors']
    assert (setup[0] / 'alerts/harvest-low-disk-pod-a').exists()


def test_failed_transfer_bytes_written_are_measured(setup):
    setup[3].interrupted = True
    row = run(setup)
    assert row['bytes'] == 0 and row['bytes_written'] == len(next(iter(setup[2].values())))
    assert not row['verified']


def test_retention_refuses_destinations_outside_pod_harvest(setup):
    setup[1]['harvest_dest'] = str(setup[0] / 'other-results')
    runs = [run(setup) for _ in range(4)]
    assert all(Path(row['snapshot']).exists() for row in runs)


def test_retention_refuses_symlink_payload_in_kept_snapshot(setup):
    first = run(setup)
    (Path(first['snapshot']) / 'unique.txt').write_text('unique')
    second = run(setup)
    run(setup)
    (Path(second['snapshot']) / 'escape').symlink_to(setup[0] / 'outside')
    with pytest.raises(ValueError, match='local symlink'):
        h.retain(Path(second['snapshot']).parent.parent, setup[1],
                 h.state_root(setup[0]) / 'HARVEST.jsonl', setup[4].now(), {})
    assert Path(first['snapshot']).exists()


def test_large_manifest_work_budget_crosses_old_ten_minute_limit(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(h.time, 'monotonic', lambda: clock[0])
    proxy = object.__new__(ORIGINAL_PROXY)
    proxy.started = proxy.last_progress = clock[0]
    proxy.deadline = clock[0] + 600
    proxy.max_deadline = clock[0] + 3600
    proxy.idle_timeout = 120
    position = [0]
    def request(_):
        if proxy.remaining() <= 0:
            raise TimeoutError('old wall clock exceeded')
        for _ in range(16):
            i = position[0]
            if i == 10000:
                break
            position[0] += 1
            yield dict(path='/workspace/results/file%d' % i, size=1000, sha256='a'*64)
        yield dict(end=True, more=position[0] < 10000)
        proxy.last_progress = clock[0]
    proxy.request = request
    count = 0
    for item in proxy.manifest():
        if 'path' in item:
            count += 1
            clock[0] += .1  # 1,000 seconds of useful per-file work
    assert count == 10000 and clock[0] > proxy.started + 600
    assert proxy.deadline <= proxy.max_deadline
    clock[0] = proxy.last_progress + 121
    assert proxy.remaining() < 0  # a hung reader still times out


@pytest.mark.parametrize('interrupt', ['hard_exit', 'sigint'])
def test_checkpoint_survives_process_exit_before_manifest_and_index_commit(setup, interrupt):
    root, pod, content, fake, clock, _ = setup
    script = '''
import datetime, hashlib, json, os, signal, sys
from pathlib import Path
from types import SimpleNamespace
import harvest
root, pod, content, now = json.loads(sys.argv[1])
signal.signal(signal.SIGINT, signal.default_int_handler)
class Remote:
    def __init__(self, pod): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def manifest(self):
        for path, data in content.items():
            data = data.encode()
            yield dict(path=path, size=len(data), sha256=hashlib.sha256(data).hexdigest())
            if sys.argv[2] == 'sigint': os.kill(os.getpid(), signal.SIGINT)
            else: os._exit(17)
    def download(self, item, target): target.write(content[item['path']].encode())
harvest.run(Path(root), [pod], SimpleNamespace(now=lambda: now), transport=Remote, name=pod['name'])
'''
    payload = json.dumps([str(root), pod, {p: b.decode() for p, b in content.items()}, clock.now()])
    result = subprocess.run([sys.executable, '-B', '-c', script, payload, interrupt],
                            cwd=Path(h.__file__).parent, capture_output=True, timeout=20)
    assert result.returncode == (17 if interrupt == 'hard_exit' else -2), result.stderr.decode()
    if interrupt == 'sigint':
        attempts = h.rows(h.state_root(root) / 'HARVEST.jsonl')
        assert len(attempts) == 1 and not attempts[0]['verified']
        assert attempts[0]['errors'] == [dict(error='KeyboardInterrupt')]
    base = Path(pod['harvest_dest']) / pod['name']
    assert not (base / 'INDEX.json').exists()
    assert not list(base.glob('snapshots/*/MANIFEST.json'))
    checkpoint = base / 'VERIFY-CHECKPOINTS.jsonl'
    assert len(h.rows(checkpoint)) == 1
    # Simulate an interrupted second append. The next durable row stays valid.
    with checkpoint.open('ab') as f:
        f.write(b'{"incomplete":')
    new_source = '/workspace/worker-a/next-result.json'
    content[new_source] = b'new result'
    row = run(setup)
    assert row['verified'] and row['linked_files'] == 1 and row['files'] == 1
    assert fake.calls == [new_source] and len(h.rows(checkpoint)) == 2


def test_checkpoint_corruption_forces_fresh_download(setup):
    _, pod, _, fake, *_ = setup
    normal = fake.manifest
    def interrupted(self):
        yield next(iter(normal(self)))
        raise OSError('interrupted')
    fake.manifest = interrupted
    first = run(setup)
    source = next(iter(setup[2]))
    (Path(first['snapshot']) / source.lstrip('/')).write_bytes(b'bad checkpoint bytes')
    fake.manifest = normal
    row = run(setup)
    assert row['verified'] and row['files'] == 1 and row['linked_files'] == 0


@pytest.mark.parametrize('kind', ['pod', 'scope'])
def test_checkpoint_identity_changes_prevent_reuse(setup, kind):
    _, pod, _, fake, *_ = setup
    first = run(setup)
    if kind == 'pod':
        pod['pod_id'] = 'replacement'
    else:
        pod['results'].append('/workspace/another-root')
    row = run(setup)
    assert row['verified'] and row['files'] == 1 and row['linked_files'] == 0
    assert Path(first['snapshot']).exists()


def test_maximum_length_filename_is_copied(setup):
    source = '/workspace/worker-a/' + 'x'*255
    setup[2][source] = b'maximum length'
    row = run(setup)
    assert row['verified'] and row['verified_files'] == 2
    assert (Path(row['snapshot']) / source.lstrip('/')).read_bytes() == b'maximum length'


def test_unrepresentable_local_path_is_recorded_without_failing_other_files(setup):
    setup[2]['/workspace/worker-a/' + 'x'*256] = b'too long locally'
    row = run(setup)
    assert row['verified'] and row['verified_files'] == 1
    assert row['skipped'][0]['skip'] == 'local_path_unrepresentable'


def test_bad_remote_name_is_skipped_without_losing_remaining_manifest(setup):
    setup[3].extra = [dict(path='/workspace/worker-a/odd\nname', skip='invalid_remote_path')]
    row = run(setup)
    assert row['verified'] and row['verified_files'] == 1
    assert row['skipped'][0]['skip'] == 'invalid_remote_path'


def test_reader_bad_filename_does_not_abort_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)) and '\n' not in p)
    (tmp_path / 'bad\nname').write_bytes(b'bad')
    (tmp_path / 'good').write_bytes(b'good')
    inventory = list(reader.manifest([str(tmp_path)]))
    assert len(inventory) == 2
    assert any(r.get('skip') == 'invalid_remote_path' for r in inventory)
    assert any(r.get('sha256') == hashlib.sha256(b'good').hexdigest() for r in inventory)


def test_changing_file_is_an_explicit_exclusion_and_next_file_verifies(setup, monkeypatch):
    content, fake = setup[2:4]
    source = next(iter(content))
    content['/workspace/worker-a/second'] = b'next file succeeds'
    download = fake.download
    def changed(self, item, target):
        if item['path'] == source:
            target.write(b'uncommitted partial data')
            raise h.RemoteFileSkipped('changed_during_harvest', 'manifest_hash_changed')
        download(self, item, target)
    monkeypatch.setattr(fake, 'download', changed)
    row = run(setup)
    assert row['verified'] and row['verified_files'] == 1
    assert row['skipped'] == [dict(path=source, skip='changed_during_harvest', detail='manifest_hash_changed')]
    assert not list(Path(row['snapshot']).rglob('*.tmp'))


def test_reader_reports_changed_hash_and_keeps_protocol_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    path = tmp_path / 'best.json'
    path.write_bytes(b'before')
    item = reader.inspect(str(path))
    path.write_bytes(b'after')
    requests = [dict(op='get', **item), dict(op='get', **reader.inspect(str(path))), dict(op='quit')]
    wire = ''.join(base64.b64encode(json.dumps(r).encode()).decode()+'\n' for r in requests)
    monkeypatch.setattr(reader.sys, 'stdin', io.StringIO(wire))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        reader.serve('TOKEN:', [str(tmp_path)])
    frames = [json.loads(base64.b64decode(line[6:])) for line in output.getvalue().splitlines()
              if line.startswith('TOKEN:')]
    assert frames[1] == dict(end=True, error='remote_read_failed', skip='changed_during_harvest', detail='manifest_hash_changed')
    assert frames[-1]['sha256'] == hashlib.sha256(b'after').hexdigest()
    assert base64.b64decode(frames[2]['data']) == b'after'


def test_retention_moves_redundant_snapshot_reversibly(setup):
    first = run(setup)
    run(setup)
    run(setup)
    moved = setup[0] / 'Trash' / Path(first['snapshot']).name
    assert not Path(first['snapshot']).exists()
    assert moved.is_dir() and (moved / 'MANIFEST.json').exists()
    source = next(iter(setup[2]))
    assert (moved / source.lstrip('/')).read_bytes() == setup[2][source]


def test_dependency_exclusions_are_explicit_recursive_and_preserve_project_files(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    for relative in ['.elan/toolchains/binary', '.lake/packages/library',
                     'verification/clean/.lake/packages/compiled',
                     'verification/clean/proof.lean', 'receipts/check.json', '.cache/mathlib/archive']:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'research')
    full = list(reader.manifest([str(tmp_path)]))
    assert len(full) == 6 and all('sha256' in r for r in full)
    selected = list(reader.manifest([str(tmp_path)], ['.lake', '.elan', '.cache']))
    assert sum(r.get('skip') == 'excluded_dependency_directory' for r in selected) == 4
    copied = {r['path'] for r in selected if 'sha256' in r}
    assert copied == {str(tmp_path / 'verification/clean/proof.lean'), str(tmp_path / 'receipts/check.json')}


def test_environment_directories_are_never_walked(tmp_path, monkeypatch):
    """11-03: every file of every pod .venv was listed (scipy test .wav files skipped one by one)."""
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    for relative in ['.venv/lib/python3.12/site-packages/scipy/io/tests/data/t.wav', 'venv/bin/tool',
                     'src/__pycache__/fit.cpython-312.pyc', 'web/node_modules/pkg/index.js',
                     'vendor/site-packages/x.py', 'results/fit.json', '.git/HEAD']:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'research')
    walked = []
    real = reader.os.walk
    def spy(*a, **kw):
        for item in real(*a, **kw):
            walked.append(item[0])
            yield item
    monkeypatch.setattr(reader.os, 'walk', spy)
    found = list(reader.manifest([str(tmp_path)]))
    assert {r['path'] for r in found if 'sha256' in r} == {str(tmp_path / 'results/fit.json'), str(tmp_path / '.git/HEAD')}
    assert sum(r.get('skip') == 'excluded_dependency_directory' for r in found) == 5
    assert not any(part in w for w in walked for part in ('.venv', '/venv', '__pycache__', 'node_modules', 'site-packages'))


def test_exclusion_policy_changes_scope_and_invalidates_freshness(setup):
    root, pod, *_ = setup
    original = h.scope(pod)
    assert run(setup)['verified']
    pod['harvest_exclude_dirs'] = ['.lake', '.elan']
    h.validate(pod)
    assert h.scope(pod) != original
    assert h.lint(root, [pod], setup[4])
    selected = h.scope(pod)
    pod['harvest_exclude_dirs'].reverse()
    assert h.scope(pod) == selected
    pod['harvest_exclude_dirs'] = []
    assert h.scope(pod) == original


@pytest.mark.parametrize('bad', [['verification'], ['.lake', '.lake'], ['../.lake'], '.lake', [None]])
def test_dependency_exclusion_policy_rejects_unsupported_names(setup, bad):
    setup[1]['harvest_exclude_dirs'] = bad
    with pytest.raises(ValueError, match='harvest_exclude_dirs'):
        h.validate(setup[1])


def test_checkpoint_journal_does_not_grow_for_unchanged_verified_runs(setup):
    _, pod, content, *_ = setup
    for _ in range(5):
        assert run(setup)['verified']
    journal = Path(pod['harvest_dest']) / pod['name'] / 'VERIFY-CHECKPOINTS.jsonl'
    assert len(h.rows(journal)) == 1
    source = next(iter(content))
    content[source] = b'changed result'
    assert run(setup)['verified']
    assert len(h.rows(journal)) == 2


@pytest.mark.parametrize('names', [('Answer.md', 'answer.md'), ('caf\u00e9.md', 'cafe\u0301.md')])
def test_filesystem_name_alias_does_not_overwrite_first_file(setup, names):
    root, _, content, *_ = setup
    probe = root / names[0]
    probe.write_bytes(b'filesystem probe')
    aliases = (root / names[1]).exists()
    content.clear()
    a, b = ['/workspace/worker-a/' + name for name in names]
    content[a], content[b] = b'first revision', b'distinct second revision'
    row = run(setup)
    assert row['verified']
    assert (Path(row['snapshot']) / a.lstrip('/')).read_bytes() == content[a]
    if aliases:
        assert row['snapshot_files'] == 1
        assert row['skipped'][0]['path'] == b
        assert row['skipped'][0]['skip'] == 'local_name_collision'
    else:
        assert row['snapshot_files'] == 2 and not row['skipped']
        assert (Path(row['snapshot']) / b.lstrip('/')).read_bytes() == content[b]


def test_parent_directory_alias_is_recorded_without_merging_sources(setup):
    root, _, content, *_ = setup
    (root / 'Probe').mkdir()
    aliases = (root / 'probe').exists()
    content.clear()
    a, b = '/workspace/worker-a/Results/a.json', '/workspace/worker-a/results/b.json'
    content[a], content[b] = b'first directory', b'second directory'
    row = run(setup)
    assert row['verified']
    assert (Path(row['snapshot']) / a.lstrip('/')).read_bytes() == content[a]
    if aliases:
        assert row['snapshot_files'] == 1
        assert row['skipped'][0]['path'] == b
        assert row['skipped'][0]['skip'] == 'local_name_collision'
    else:
        assert row['snapshot_files'] == 2 and not row['skipped']


def bulk_exclusion(**changes):
    return dict(dict(path='results/F057/native_states', reason='Deterministic arm states; no claim depends on them',
                     regenerate='python regenerate.py --receipts results/F057/receipts/arms.json',
                     approved_by='general', utc='2026-11-03T21:00:00Z'), **changes)


def test_path_exclusion_validation_and_root_selection(setup):
    pod = setup[1]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    h.validate(pod)
    assert reader.path_exclusions(pod['results'], pod['harvest_exclude_paths'])[0]['source'] == '/workspace/worker-a/results/F057/native_states'
    pod['results'].append('/workspace/other')
    with pytest.raises(ValueError, match='root'):
        h.validate(pod)
    pod['harvest_exclude_paths'][0]['root'] = '/workspace/worker-a'
    h.validate(pod)


@pytest.mark.parametrize('key', ['reason', 'regenerate', 'approved_by', 'utc'])
@pytest.mark.parametrize('value', [None, '', '  ', 42])
def test_path_exclusion_requires_metadata(setup, key, value):
    entry = bulk_exclusion()
    if value is None:
        entry.pop(key)
    else:
        entry[key] = value
    setup[1]['harvest_exclude_paths'] = [entry]
    with pytest.raises(ValueError, match='harvest_exclude_paths'):
        h.validate(setup[1])


@pytest.mark.parametrize('path', ['/workspace/other/states', '../states', 'results/../states',
                                  'results/..', 'results/*', 'results/?', 'results/[ab]', '.', '',
                                  './states', 'results//states', 'results/states/', 'results\\states',
                                  'results\nstates', 'results/\x7fstates', None])
def test_path_exclusion_rejects_unsafe_paths_before_transport(setup, path):
    setup[1]['harvest_exclude_paths'] = [bulk_exclusion(path=path)]
    with pytest.raises(ValueError, match='harvest_exclude_paths'):
        h.validate(setup[1])
    assert not run(setup)['verified']
    assert not setup[3].calls


@pytest.mark.parametrize('bad', [None, {}, 'native_states', [None], [bulk_exclusion(root='/workspace/other')],
                                 [bulk_exclusion(utc='2026-11-03T21:00:00')],
                                 [bulk_exclusion(utc='not-a-time')],
                                 [bulk_exclusion(utc='2026-11-03T21:00:00+01:00')],
                                 [bulk_exclusion(), bulk_exclusion()],
                                 [bulk_exclusion(), bulk_exclusion(path='results/F057/native_states/deeper')]])
def test_path_exclusion_rejects_invalid_declarations(setup, bad):
    setup[1]['harvest_exclude_paths'] = bad
    with pytest.raises(ValueError, match='harvest_exclude_paths'):
        h.validate(setup[1])


@pytest.mark.parametrize('key,value', [('path', 'results/F057/other'), ('reason', 'revised reason'),
                                      ('regenerate', 'new recipe; receipts/arms.json'), ('approved_by', 'owner'),
                                      ('utc', '2026-11-03T22:00:00Z')])
def test_path_exclusion_metadata_changes_scope_and_freshness(setup, key, value):
    pod = setup[1]
    original = h.scope(pod)
    assert run(setup)['verified']
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    selected = h.scope(pod)
    assert selected != original
    assert h.lint(setup[0], [pod], setup[4])
    pod['harvest_exclude_paths'][0][key] = value
    assert h.scope(pod) != selected
    pod['harvest_exclude_paths'] = []
    assert h.scope(pod) == original


def test_path_exclusion_order_does_not_change_scope(setup):
    pod = setup[1]
    pod['harvest_exclude_paths'] = [bulk_exclusion(), bulk_exclusion(path='results/other')]
    selected = h.scope(pod)
    pod['harvest_exclude_paths'].reverse()
    assert h.scope(pod) == selected


def test_reader_counts_only_exact_subtree_without_opening_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    excluded = tmp_path / 'results/F057/native_states'
    excluded.mkdir(parents=True)
    (excluded / 'arm').write_bytes(b'1234567')
    (excluded / 'nested').mkdir()
    (excluded / 'nested/arm').write_bytes(b'12345')
    (excluded / 'empty').write_bytes(b'')
    # Count oversized and media files by metadata too, without inspecting them.
    with (excluded / 'huge.mp4').open('wb') as f:
        f.truncate(h.MAX_BYTES + 1)
    (excluded / 'link').symlink_to(tmp_path)
    os.mkfifo(excluded / 'fifo')
    siblings = ['results/F057/receipts/arms.json', 'results/F057/native_states_backup/arm',
                'results/other/native_states/arm']
    for relative in siblings:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'research')
    original_opened = reader.opened
    def opened(path, directory=False):
        if path == str(excluded) or path.startswith(str(excluded) + '/'):
            assert directory, 'excluded payload opened'
        return original_opened(path, directory=directory)
    monkeypatch.setattr(reader, 'opened', opened)
    original_inspect = reader.inspect
    inspected = []
    def inspect(path):
        assert not path.startswith(str(excluded) + '/')
        inspected.append(path)
        return original_inspect(path)
    monkeypatch.setattr(reader, 'inspect', inspect)
    declaration = bulk_exclusion()
    found = list(reader.manifest([str(tmp_path)], [], [declaration]))
    reports = [r for r in found if r.get('skip') == 'excluded_path']
    assert reports == [dict(path=str(excluded), skip='excluded_path', files=4, bytes=h.MAX_BYTES+13, present=True)]
    assert set(inspected) == {str(tmp_path / relative) for relative in siblings}
    assert {r['path'] for r in found if 'sha256' in r} == set(inspected)


def test_reader_missing_exclusion_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    assert list(reader.manifest([str(tmp_path)], [], [bulk_exclusion()])) == [
        dict(path=str(tmp_path / bulk_exclusion()['path']), skip='excluded_path', files=0, bytes=0, present=False)]


@pytest.mark.parametrize('kind', ['symlink', 'unreadable'])
def test_reader_exclusion_count_failure_is_reported(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    path = tmp_path / bulk_exclusion()['path']
    path.parent.mkdir(parents=True)
    if kind == 'symlink':
        path.symlink_to(tmp_path, target_is_directory=True)
    else:
        path.mkdir()
        monkeypatch.setattr(reader, 'exclusion_counts', Mock(side_effect=PermissionError()))
    found = list(reader.manifest([str(tmp_path)], [], [bulk_exclusion()]))
    assert found == [dict(path=str(path), error='exclusion_count_failed')]


def test_reader_get_refuses_excluded_content(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    path = str(tmp_path / bulk_exclusion()['path'] / 'arm')
    request = dict(op='get', path=path, size=1, sha256='a'*64)
    monkeypatch.setattr(reader.sys, 'stdin', io.StringIO(base64.b64encode(json.dumps(request).encode()).decode()+'\n'))
    inspect = Mock(side_effect=AssertionError('excluded content must not be read'))
    monkeypatch.setattr(reader, 'inspect', inspect)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        reader.serve('TOKEN:', [str(tmp_path)], [], [bulk_exclusion()])
    frames = [json.loads(base64.b64decode(line[6:])) for line in output.getvalue().splitlines() if line.startswith('TOKEN:')]
    assert frames == [dict(ready=True), dict(end=True, error='remote_read_failed')]
    inspect.assert_not_called()


def test_path_exclusion_snapshot_manifest_sibling_and_lint(setup, monkeypatch, capsys):
    root, pod, _, fake, clock, _ = setup
    source_root = root / 'remote-fixture'
    source_root.mkdir()
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    relative_files = {'results/F057/native_states/arm1': b'large states',
                      'results/F057/native_states/nested/arm2': b'other states',
                      'results/F057/receipts/arms.json': b'{"inputs":"pinned"}',
                      'results/F057/native_states_backup/arm': b'sibling'}
    for relative, data in relative_files.items():
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(reader, 'valid', lambda p: p.startswith(str(source_root)) or p.startswith('/workspace/'))
    def manifest(self):
        declarations = [dict(entry, root=str(source_root)) for entry in self.pod['harvest_exclude_paths']]
        for item in reader.manifest([str(source_root)], [], declarations):
            yield dict(item, path='/workspace/worker-a' + item['path'][len(str(source_root)):])
        yield dict(end=True)
    def download(self, item, target):
        relative = item['path'].removeprefix('/workspace/worker-a/')
        assert not relative.startswith(bulk_exclusion()['path'] + '/')
        self.calls.append(item['path'])
        target.write(relative_files[relative])
    monkeypatch.setattr(fake, 'manifest', manifest)
    monkeypatch.setattr(fake, 'download', download)
    row = run(setup)
    assert row['verified'] and not row['errors']
    assert row['snapshot_files'] == row['verified_files'] == row['files'] == 2
    assert row['verified_bytes'] == row['snapshot_bytes'] == len(relative_files['results/F057/receipts/arms.json']) + len(b'sibling')
    record = json.loads((Path(row['snapshot']) / 'MANIFEST.json').read_text())
    entry = record['harvest_exclude_paths'][0]
    for key, value in bulk_exclusion().items():
        assert entry[key] == value
    assert entry['files'] == 2 and entry['bytes'] == len(b'large statesother states') and entry['present']
    assert all('/native_states/' not in path for path in record['files_index'])
    assert not (Path(row['snapshot']) / 'workspace/worker-a/results/F057/native_states').exists()
    assert len(fake.calls) == 2
    (root / 'pods.json').write_text(json.dumps([pod]))
    clock.rows = h.rows
    info = []
    assert not pods.lint(root / 'lanes/team', clock, info=info)
    assert len(info) == 1 and 'excluded: pod-a/worker-a/results/F057/native_states, 2 files, 0.000 GB, regenerate:' in info[0]
    result = dict(lane='team', depth=3, warnings=[], failures=[], grandfathered=[], info=info)
    rh.print_lint(result)
    assert 'INFO team: excluded: pod-a/' in capsys.readouterr().out
    monkeypatch.setattr(rh, 'now', clock.now)
    assert rh.lint_result(root / 'lanes/team')['info'] == info
    # Scope-specific lint never reuses counts from the old approval.
    pod['harvest_exclude_paths'][0]['reason'] = 'new reason'
    info = []
    assert h.lint(root, [pod], clock, info=info)
    assert 'counts unavailable' in info[0]


@pytest.mark.parametrize('report', [None, dict(files=-1, bytes=0, present=True),
                                   dict(files=True, bytes=0, present=True),
                                   dict(files=2, bytes=0, present=False),
                                   dict(files=2, bytes=None, present=True),
                                   dict(files=2, bytes=4, present='yes'),
                                   dict(files=2, bytes=4, present=True, path='/workspace/worker-a/other')])
def test_missing_or_invalid_exclusion_reports_never_verify(setup, report):
    pod, fake = setup[1], setup[3]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    if report is not None:
        fake.extra = [dict(dict(path='/workspace/worker-a/' + bulk_exclusion()['path'], skip='excluded_path'), **report)]
    row = run(setup)
    assert not row['verified'] and row['errors']


def test_duplicate_exclusion_report_fails(setup):
    pod, fake = setup[1], setup[3]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    report = dict(path='/workspace/worker-a/' + bulk_exclusion()['path'], skip='excluded_path', files=2, bytes=8, present=True)
    fake.extra = [report, report]
    assert not run(setup)['verified']


def test_excluded_payload_from_transport_is_never_downloaded(setup):
    pod, content, fake = setup[1:4]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    content['/workspace/worker-a/' + bulk_exclusion()['path'] + '/arm'] = b'states'
    row = run(setup)
    assert not row['verified']
    assert not any('/native_states/' in path for path in fake.calls)


def test_exclusion_does_not_waive_missing_results_or_corrupt_sibling(setup):
    pod, fake = setup[1], setup[3]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    fake.extra = [dict(path='/workspace/worker-a/' + bulk_exclusion()['path'], skip='excluded_path', files=2, bytes=8, present=True),
                  dict(path='/workspace/worker-a/missing', error='results_path_unavailable')]
    assert not run(setup)['verified']
    fake.extra.pop()
    fake.corrupt = True
    setup[2]['/workspace/worker-a/results/x.json'] = b'changed sibling'
    assert not run(setup)['verified']


def test_reader_path_exclusion_selects_one_root_and_keeps_dependency_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, 'valid', lambda p: str(p).startswith(str(tmp_path)))
    first, second = tmp_path / 'one', tmp_path / 'two'
    for root in (first, second):
        for relative in ['F057/native_states/arm', 'F057/receipts/arms.json', '.lake/packages/dependency']:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'data')
    roots = [str(first), str(second)]
    entry = bulk_exclusion(path='F057/native_states', root=str(first))
    found = list(reader.manifest(roots, ['.lake'], [entry]))
    harvested = {r['path'] for r in found if 'sha256' in r}
    assert harvested == {str(first / 'F057/receipts/arms.json'), str(second / 'F057/receipts/arms.json'),
                         str(second / 'F057/native_states/arm')}
    assert sum(r.get('skip') == 'excluded_dependency_directory' for r in found) == 2
    assert [r for r in found if r.get('skip') == 'excluded_path'] == [
        dict(path=str(first / 'F057/native_states'), skip='excluded_path', files=1, bytes=4, present=True)]


def test_active_exclusion_without_history_has_info_and_still_fails_freshness(setup):
    root, pod, _, _, clock, _ = setup
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    info = []
    assert h.lint(root, [pod], clock, info=info)
    assert len(info) == 1 and 'counts unavailable' in info[0]
    assert bulk_exclusion()['regenerate'] in info[0]


def test_exclusion_count_error_is_saved_with_metadata_and_never_verified(setup):
    pod, fake = setup[1], setup[3]
    pod['harvest_exclude_paths'] = [bulk_exclusion()]
    fake.extra = [dict(path='/workspace/worker-a/' + bulk_exclusion()['path'], error='exclusion_count_failed')]
    row = run(setup)
    assert not row['verified']
    record = json.loads((Path(row['snapshot']) / 'MANIFEST.json').read_text())
    entry = record['harvest_exclude_paths'][0]
    assert entry['files'] is None and entry['bytes'] is None and entry['present'] is None
    assert entry['reason'] == bulk_exclusion()['reason']
    assert entry['regenerate'] == bulk_exclusion()['regenerate']
    assert record['verified_files'] == 1  # only the remaining sibling


def test_media_filter_keeps_code_named_like_media_11_03():
    """11-03: a pod's mime table called Snakemake .smk video, and .ts was treated as MPEG-TS; both are code."""
    import harvest_reader as h
    assert not h.media('MB24/sources/mras_workflow.smk', b'rule all:\n')
    assert not h.media('src/app.ts', b'import x from "y";\n' * 30)
    ts = bytearray(600)
    ts[0] = ts[188] = ts[376] = 0x47
    assert h.media('capture.ts', bytes(ts))
    assert h.media('clip.mp4', b'')


def test_a_prune_that_cannot_move_is_journaled_and_keeps_the_verified_run(setup, monkeypatch, tmp_path):
    """11-04: a Trash move that hit its timeout killed the prune, so six good harvests of
    friends/fz67 were journaled unverified and notified as "results not copied" although the
    copy had worked and the snapshot's own MANIFEST said verified.
    Disposal is the last act of an already verified harvest: its failure keeps the snapshot,
    records its own event, and says nothing about the copy.
    """
    def refuse(directory):
        raise subprocess.TimeoutExpired('/usr/bin/trash', 30)
    first, second = run(setup), run(setup)
    monkeypatch.setattr(h, 'trash_snapshot', refuse)
    third = run(setup)
    assert third['verified'] and third['errors'] == []
    assert Path(first['snapshot']).exists(), 'a snapshot that will not move is kept'
    journal = h.rows(h.state_root(setup[0]) / 'HARVEST.jsonl')
    failed = [r for r in journal if r.get('event') == 'SNAPSHOT_REMOVE_FAILED']
    assert [r['path'] for r in failed] == [first['snapshot']]
    assert failed[0]['error'] == 'TimeoutExpired' and failed[0]['disposition'] == 'kept'
    assert not [r for r in journal if r.get('event') == 'SNAPSHOT_REMOVED']
    # The next run disposes of it normally, so a transient refusal is not a dead end.
    def move(directory):
        destination = tmp_path / 'retry-trash' / directory.name
        destination.parent.mkdir(exist_ok=True)
        directory.rename(destination)
    monkeypatch.setattr(h, 'trash_snapshot', move)
    assert run(setup)['verified']
    assert not Path(first['snapshot']).exists() and not Path(second['snapshot']).exists()


def test_trash_budget_grows_with_the_tree_and_stops_at_the_ceiling(tmp_path, monkeypatch):
    """A flat 30 seconds was a thin ceiling for a tree; the budget now scales with one."""
    one = tmp_path / 'alert.json'
    one.write_text('{}')
    assert storage.timeout(one) == pytest.approx(storage.TIMEOUT_FLOOR + storage.TIMEOUT_PER_ENTRY)
    tree = tmp_path / 'snapshot'
    (tree / 'workspace').mkdir(parents=True)
    for i in range(300):
        (tree / 'workspace' / ('f%d.h5' % i)).write_text('x')
    assert storage.timeout(tree) > 60 and storage.timeout(tree) < storage.TIMEOUT_CEILING
    assert storage.entries(tree) == 302  # the tree, its directory and 300 files
    monkeypatch.setattr(storage, 'COUNT_LIMIT', 10)
    assert storage.timeout(tree) == pytest.approx(storage.TIMEOUT_FLOOR + 2.0)
    # The command is given that budget, and a hang is still bounded.
    seen = {}
    def record(argv, **kw):
        seen.update(kw)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(storage.subprocess, 'run', record)
    ORIGINAL_TRASH(one)
    assert seen['timeout'] == pytest.approx(storage.TIMEOUT_FLOOR + storage.TIMEOUT_PER_ENTRY)
    assert seen['check'] is True
