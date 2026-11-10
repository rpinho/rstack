"""harness-sync installs only committed harness files and reports every kind of drift."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'harness/tools/harness-sync'
sys.path.insert(0, str(TOOL))
import harness_sync as hs  # noqa: E402


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo, root, backups = tmp_path / 'repo', tmp_path / 'installed', tmp_path / 'backups'
    (repo / 'harness/tools').mkdir(parents=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'user.email', 'test' + chr(64) + 'example.invalid')
    git(repo, 'config', 'user.name', 'test')
    (repo / 'harness/rh.py').write_text('VERSION = 1\n')
    (repo / 'harness/tools/run.sh').write_text('#!/bin/sh\n')
    os.chmod(repo / 'harness/tools/run.sh', 0o755)
    (repo / 'README.md').write_text('outside harness/: never installed\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'one')
    (root / 'lanes/team').mkdir(parents=True)
    (root / 'lanes/team/IDEAS.jsonl').write_text('{}\n')
    (root / 'PODS.jsonl').write_text('{}\n')
    trash = tmp_path / 'Trash'
    trash.mkdir()
    mover = tmp_path / 'fake-trash'
    mover.write_text('#!/bin/sh\nmv "$1" ' + shlex.quote(str(trash)) + '/\n')
    os.chmod(mover, 0o755)
    monkeypatch.setenv('RH_TRASH_COMMAND', str(mover))
    monkeypatch.setattr(hs, 'running_jobs', lambda: [])

    def run(*flags):
        return hs.main(['--repo', str(repo), '--root', str(root), '--backups', str(backups), *flags])
    return repo, root, backups, trash, run


def commit(repo, rel, text, message):
    (repo / 'harness' / rel).write_text(text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)


def test_install_then_clean_check_and_state_untouched(env, capsys):
    repo, root, _, _, run = env
    assert run('--check') == 2
    assert 'MISSING   rh.py' in capsys.readouterr().out
    assert run() == 0
    assert (root / 'rh.py').read_text() == 'VERSION = 1\n'
    assert not os.access(root / 'rh.py', os.W_OK)
    assert os.access(root / 'tools/run.sh', os.X_OK)
    assert not (root / 'README.md').exists()
    assert (root / 'lanes/team/IDEAS.jsonl').read_text() == '{}\n'
    assert (root / 'PODS.jsonl').read_text() == '{}\n'
    receipt = json.loads((root / hs.RECEIPT).read_text())
    assert receipt['ref'] == 'main' and len(receipt['commit']) == 40
    assert run('--check') == 0


def test_working_tree_edits_are_never_installed(env):
    repo, root, _, _, run = env
    (repo / 'harness/rh.py').write_text('VERSION = half-finished\n')
    assert run() == 0
    assert (root / 'rh.py').read_text() == 'VERSION = 1\n'


def test_auto_fast_forwards_when_only_behind(env, capsys):
    repo, root, _, _, run = env
    run()
    commit(repo, 'rh.py', 'VERSION = 2\n', 'two')
    commit(repo, 'new_module.py', 'X = 1\n', 'three')
    capsys.readouterr()
    assert run('--check') == 2
    out = capsys.readouterr().out
    assert 'BEHIND    rh.py' in out and 'MISSING   new_module.py' in out
    assert run('--auto') == 0
    assert (root / 'rh.py').read_text() == 'VERSION = 2\n'
    assert run('--check') == 0


def test_hand_edit_blocks_auto_and_full_install_backs_it_up(env, capsys):
    repo, root, backups, _, run = env
    run()
    os.chmod(root / 'rh.py', 0o644)
    (root / 'rh.py').write_text('VERSION = hand-fix\n')
    capsys.readouterr()
    assert run('--auto') == 2
    assert 'EDITED    rh.py' in capsys.readouterr().out
    assert (root / 'rh.py').read_text() == 'VERSION = hand-fix\n'
    assert run() == 0
    assert (root / 'rh.py').read_text() == 'VERSION = 1\n'
    saved = list(backups.glob('*/rh.py'))
    assert [p.read_text() for p in saved] == ['VERSION = hand-fix\n']


def test_stray_module_blocks_auto_and_goes_to_trash(env, capsys):
    repo, root, backups, trash, run = env
    run()
    (root / 'hand_module.py').write_text('Y = 1\n')
    (root / 'rh.py.bak-1103a').write_text('old\n')
    (root / 'lanes/team/helper.py').write_text('lane code is state\n')
    capsys.readouterr()
    assert run('--auto') == 2
    out = capsys.readouterr().out
    assert 'STRAY     hand_module.py' in out and '.bak' not in out and 'helper.py' not in out
    assert run() == 0
    assert not (root / 'hand_module.py').exists()
    assert (trash / 'hand_module.py').read_text() == 'Y = 1\n'
    assert list(backups.glob('*/hand_module.py'))
    assert (root / 'rh.py.bak-1103a').exists() and (root / 'lanes/team/helper.py').exists()


def test_an_archived_lane_copy_is_data_not_a_stray_module(env, capsys):
    """11-10: the m5 keeps stale-lanes-1107/ (11 GB of old lane copies) under its root, and two
    runs retired 4,454 of its scripts to the Trash as stray modules."""
    repo, root, backups, trash, run = env
    run()
    kept = root / 'stale-lanes-1107/math/watch/poll.sh'
    kept.parent.mkdir(parents=True)
    kept.write_text('echo old lane\n')
    capsys.readouterr()
    assert run('--auto') == 0
    assert 'stale-lanes' not in capsys.readouterr().out
    assert kept.read_text() == 'echo old lane\n'


def test_file_removed_from_repo_is_retired(env):
    repo, root, _, trash, run = env
    run()
    git(repo, 'rm', '-q', 'harness/tools/run.sh')
    git(repo, 'commit', '-qm', 'drop')
    assert run('--auto') == 0
    assert not (root / 'tools/run.sh').exists() and (trash / 'run.sh').exists()


def test_running_job_blocks_install(env, monkeypatch, capsys):
    repo, root, _, _, run = env
    monkeypatch.setattr(hs, 'running_jobs', lambda: ['com.example.research-harness-pods'])
    assert run() == 2
    assert 'harness job running' in capsys.readouterr().out
    assert not (root / 'rh.py').exists()
    assert run('--allow-running') == 0
