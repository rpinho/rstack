"""Exercise the real deploy retention function on synthetic histories and live links."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import release_sync as sync
from protected_paths import assert_disposable

RETENTION = Path(__file__).parent / 'fixtures/release-protect/release-retention.mjs'


@pytest.fixture
def deployment(tmp_path):
    root = tmp_path / 'deploy'
    (root / 'bin').mkdir(parents=True)
    (root / 'live').mkdir()
    shutil.copyfile(RETENTION, root / 'bin/release-retention.mjs')
    (root / 'deploy.json').write_text(json.dumps({'games': {'game': {}, 'other': {}}}))
    registry = tmp_path / 'state/registry.json'
    registry.parent.mkdir()
    return root, registry


def release(root, version, app='game'):
    path = root / 'releases' / app / version
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def history(root, versions, app='game'):
    (root / 'promotions.log').write_text(''.join(
        '2026-11-18T00:00:00Z PROMOTED {} old -> {}; health ok\n'.format(app, v) for v in versions))


def register(registry, paths=(), **extra):
    registry.write_text(json.dumps(dict(paths=list(paths), **extra)))


def run_sync(root, registry, *extra):
    return subprocess.run([sys.executable, str(TOOLS / 'release-protect'), 'sync',
        '--from-deploy', str(root), '--registry', str(registry), *extra],
        capture_output=True, text=True, timeout=40)


def snapshot(path):
    return {str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in path.rglob('*') if p.is_file()}


def test_sync_adds_new_live_release_for_every_app(deployment):
    root, registry = deployment
    old, new, other = release(root, 'old'), release(root, 'new'), release(root, 'v1', 'other')
    history(root, ['old'])  # New link before its success log must still be kept.
    (root / 'live/game').symlink_to(new)
    (root / 'live/other').symlink_to(other)
    register(registry, [old])
    result = run_sync(root, registry)
    assert result.returncode == 0, result.stderr
    assert set(json.loads(registry.read_text())['paths']) == {old, new, other}
    assert set(json.loads(result.stdout)['add']) == {new, other}
    log = json.loads(registry.with_name('release-protect-sync.jsonl').read_text())
    assert set(log['add']) == {new, other}
    with pytest.raises(ValueError, match='protected release'):
        assert_disposable([new], registry)


def test_sync_removes_release_outside_last_three_distinct_successes(deployment):
    root, registry = deployment
    paths = [release(root, v) for v in ('v1', 'v2', 'v3', 'v4')]
    history(root, ['v1', 'v2', 'v3', 'v4', 'v3'])
    (root / 'live/game').symlink_to(paths[-2])
    register(registry, paths)
    result = run_sync(root, registry)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['remove'] == paths[:1]
    assert set(json.loads(registry.read_text())['paths']) == set(paths[1:])
    assert_disposable([paths[0]], registry)


def test_current_live_is_kept_in_addition_to_last_three(deployment):
    root, registry = deployment
    paths = [release(root, v) for v in ('old-live', 'v2', 'v3', 'v4')]
    history(root, ['v2', 'v3', 'v4'])
    (root / 'live/game').symlink_to(paths[0])
    register(registry, paths)
    assert run_sync(root, registry).returncode == 0
    assert set(json.loads(registry.read_text())['paths']) == set(paths)


@pytest.mark.parametrize('pointer', ['symlink', 'broken-symlink', 'current-json'])
def test_refuses_to_remove_live_release_even_if_deploy_result_omits_it(deployment, pointer):
    root, registry = deployment
    live = release(root, 'live') if pointer != 'broken-symlink' else str(root / 'releases/game/missing')
    if pointer == 'current-json':
        (root / 'live/current.json').write_text(json.dumps({'game': 'live', 'updatedAt': 'now'}))
    else:
        (root / 'live/game').symlink_to(live)
    register(registry, [live])
    # A faulty/stale deploy query must not be allowed to remove an actual pointer.
    (root / 'bin/release-retention.mjs').write_text('export const releaseProtection = () => ({paths:[]});\n')
    before = registry.read_bytes()
    result = run_sync(root, registry)
    assert result.returncode == 1 and 'currently live' in result.stderr
    assert registry.read_bytes() == before
    assert not registry.with_name('release-protect-sync.jsonl').exists()


def test_dry_run_prints_diff_and_writes_nothing(deployment):
    root, registry = deployment
    old, new = release(root, 'old'), release(root, 'new')
    history(root, ['new'])
    register(registry, [old])
    before = snapshot(root.parent)
    result = run_sync(root, registry, '--dry-run')
    assert result.returncode == 0, result.stderr
    diff = json.loads(result.stdout)
    assert diff['add'] == [new] and diff['remove'] == [old]
    assert snapshot(root.parent) == before
    missing = root.parent / 'absent/registry.json'
    assert run_sync(root, missing, '--dry-run').returncode == 0
    assert not missing.parent.exists()


def test_installed_bundle_symlinks_call_exported_function(deployment):
    root, registry = deployment
    script = root / 'bin/release-retention.mjs'
    bundle = root / 'bin/bundles/toy'
    bundle.mkdir(parents=True)
    script.rename(bundle / script.name)
    (root / 'bin/current').symlink_to('bundles/toy')
    script.symlink_to('current/release-retention.mjs')
    history(root, ['v1', 'v2', 'v3', 'v4'])
    paths = [release(root, v) for v in ('v2', 'v3', 'v4')]
    register(registry)
    result = run_sync(root, registry)
    assert result.returncode == 0, result.stderr
    assert set(json.loads(registry.read_text())['paths']) == set(paths)


def test_non_release_entries_and_registered_sources_are_kept(deployment):
    root, registry = deployment
    old, new = release(root, 'old'), release(root, 'new')
    history(root, ['new'])
    source, nested = root / 'protected-releases.json', root / 'other-source.json'
    manual = str(root.parent / 'important-data')
    other_deploy = str(root.parent / 'other-deploy/releases/game/keep')
    nested.write_text(json.dumps({'schema': 1, 'paths': [manual, old]}))
    source.write_text(json.dumps({'paths': [old, manual], 'sources': [str(nested)]}))
    register(registry, [old, other_deploy, manual], sources=[str(source)], schema=1)
    result = run_sync(root, registry)
    assert result.returncode == 0, result.stderr
    assert json.loads(registry.read_text()) == {
        'schema': 1, 'paths': [other_deploy, manual, new], 'sources': [str(source)]}
    assert json.loads(source.read_text()) == {'paths': [manual], 'sources': [str(nested)]}
    assert json.loads(nested.read_text()) == {'schema': 1, 'paths': [manual]}
    assert_disposable([old], registry)
    with pytest.raises(ValueError):
        assert_disposable([manual], registry)
    before = snapshot(root.parent)
    assert run_sync(root, registry).returncode == 0
    assert snapshot(root.parent) == before  # idempotent; no repeated log writes


def test_source_alias_is_preserved(deployment):
    root, registry = deployment
    new = release(root, 'new')
    history(root, ['new'])
    actual = root / 'actual.json'
    actual.write_text(json.dumps({'paths': [release(root, 'old')]}))
    alias = root / 'alias.json'
    alias.symlink_to(actual)
    register(registry, sources=[str(alias)])
    assert run_sync(root, registry).returncode == 0
    assert alias.is_symlink() and json.loads(actual.read_text())['paths'] == []
    assert json.loads(registry.read_text())['paths'] == [new]


def test_live_entries_in_registered_sources_are_preserved(deployment):
    root, registry = deployment
    live = release(root, 'live')
    (root / 'live/game').symlink_to(live)
    source = root / 'protected-releases.json'
    source.write_text(json.dumps({'paths': [live]}))
    register(registry, sources=[str(source)])
    before = source.read_bytes(), source.stat().st_mtime_ns
    assert run_sync(root, registry).returncode == 0
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert json.loads(registry.read_text())['paths'] == [live]


@pytest.mark.parametrize('failure', ['bad-output', 'missing-source', 'bad-history', 'no-deploy'])
def test_invalid_deploy_or_registry_refuses_without_rewriting(deployment, failure):
    root, registry = deployment
    register(registry, [release(root, 'old')])
    if failure == 'bad-output':
        (root / 'bin/release-retention.mjs').write_text('console.log("not-json");')
    elif failure == 'missing-source':
        register(registry, sources=[str(root / 'missing.json')])
    elif failure == 'bad-history':
        (root / 'deploy.json').write_text('{bad')
    else:
        root = root / 'absent'
    before = registry.read_bytes()
    result = run_sync(root, registry)
    assert result.returncode == 1
    assert registry.read_bytes() == before


def test_live_change_during_sync_refuses(deployment):
    root, registry = deployment
    old, new = release(root, 'old'), release(root, 'new')
    history(root, ['new'])
    register(registry, [old])
    change = sync.plan(root, registry)
    (root / 'live/game').symlink_to(old)
    before = registry.read_bytes()
    with pytest.raises(ValueError, match='live pointers changed'):
        sync.apply_plan(change)
    assert registry.read_bytes() == before


def test_health_waits_more_than_hour_and_resets_on_recovery(deployment):
    root, registry = deployment
    history(root, ['new'])
    register(registry, [release(root, 'old')])
    state = root.parent / 'health/timers.json'
    entries = [dict(deploy_root=str(root), registry=str(registry))]
    now = 100000
    assert sync.health_problems(entries, now, state) == []
    assert sync.health_problems(entries, now + 3600, state) == []
    rows = sync.health_problems(entries, now + 3601, state)
    assert rows[0][0] == 'release-protection' and '1 missing, 1 stale' in rows[0][2]
    sync.sync(root, registry)
    assert sync.health_problems(entries, now + 4000, state) == []
    assert json.loads(state.read_text()) == {}
    register(registry)
    assert sync.health_problems(entries, now + 5000, state) == []


def test_health_dry_run_writes_nothing_and_failures_do_not_clear_timer(deployment):
    root, registry = deployment
    history(root, ['new'])
    register(registry)
    state = root.parent / 'health/timers.json'
    entries = [dict(deploy_root=str(root), registry=str(registry))]
    assert sync.health_problems(entries, 10000, state, write=False) == []
    assert not state.parent.exists()
    sync.health_problems(entries, 10000, state)
    before = snapshot(state.parent)
    rows = sync.health_problems(entries, 14000, state, write=False)
    assert rows and snapshot(state.parent) == before
    (root / 'deploy.json').write_text('{bad')
    rows = sync.health_problems(entries, 15000, state)
    assert 'comparison unavailable' in rows[0][2]


def test_job_health_uses_existing_alert_and_recovery(deployment, monkeypatch):
    root, registry = deployment
    loader = importlib.machinery.SourceFileLoader('job_health_release_test', str(TOOLS / 'job-health'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    jh = importlib.util.module_from_spec(spec)
    loader.exec_module(jh)
    state = root.parent / 'health'
    monkeypatch.setenv('RSTACK_STATE_DIR', str(state))
    monkeypatch.setenv('RSTACK_HOST', 'test')
    monkeypatch.setattr(jh, 'launchd_jobs', lambda prefix: {})
    clock = [10000]
    monkeypatch.setattr(jh.time, 'time', lambda: clock[0])
    history(root, ['new'])
    register(registry)
    config = root.parent / 'jobs.json'
    config.write_text(json.dumps({'release_protection': [dict(deploy_root=str(root), registry=str(registry))]}))
    sent = root.parent / 'sent'
    args = ['--prefix', 'com.example.', '--registry', str(config),
            '--alert', "/bin/sh -c 'echo \"$0\" >> {}'".format(sent)]
    assert jh.main(args) == 0
    clock[0] += 3601
    assert jh.main(args + ['--dry']) == 1
    assert not sent.exists()
    assert jh.main(args) == 0 and jh.main(args) == 0
    assert sent.read_text().count('release-protection') == 1
    assert 'release-protection' in (state / 'asks-waiting/test-jobs.tsv').read_text()
    sync.sync(root, registry)
    assert jh.main(args) == 0
    assert (state / 'asks-waiting/test-jobs.tsv').read_text() == ''
    assert 'RECOVERED release-protection' in (state / 'job-health/log').read_text()
