"""The osascript shim: a Finder delete becomes a silent trash; nothing else changes (11-12).

The real osascript and trash are stubs that record their arguments, so no test ever reaches Finder.
"""
import os
import subprocess
import sys

from rstack_hookcall import TOOLS

SHIM = TOOLS / 'osascript'
FINDER = 'tell application "Finder" to delete POSIX file "{}"'


def setup(tmp_path):
    log = tmp_path / 'calls.log'
    for name in ('real', 'trash'):
        stub = tmp_path / name
        stub.write_text('#!/bin/sh\necho "{} $*" >> {}\n'.format(name, log))
        stub.chmod(0o755)
    env = dict(os.environ, OSASCRIPT_REAL=str(tmp_path / 'real'), OSASCRIPT_TRASH=str(tmp_path / 'trash'))
    return log, env


def run(env, *args):
    return subprocess.run([sys.executable, '-I', str(SHIM), *args], env=env, capture_output=True, text=True,
                          timeout=30)


def test_a_finder_delete_goes_to_the_trash_and_never_to_finder(tmp_path):
    log, env = setup(tmp_path)
    victim = tmp_path / 'old results.csv'
    victim.write_text('x')
    assert run(env, '-e', FINDER.format(victim)).returncode == 0
    assert log.read_text().splitlines() == ['trash {}'.format(victim)]


def test_the_argv_form_is_caught_too(tmp_path):
    log, env = setup(tmp_path)
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.write_text('x'); b.write_text('y')
    script = 'on run argv\ntell application "Finder" to delete (POSIX file (item 1 of argv))\nend run'
    run(env, '-e', script, str(a), str(b))
    assert log.read_text().splitlines() == ['trash {} {}'.format(a, b)]


def test_everything_else_reaches_the_real_osascript_unchanged(tmp_path):
    log, env = setup(tmp_path)
    run(env, '-e', 'display notification "done"')
    run(env, '-e', FINDER.format(tmp_path / 'missing-file'))      # nothing to trash: not ours to handle
    run(env, '-l', 'JavaScript', '-e', '1+1')                    # flags it does not model pass through
    lines = log.read_text().splitlines()
    assert [l.split()[0] for l in lines] == ['real'] * 3
    assert lines[0] == 'real -e display notification "done"'


def test_icloud_files_and_failed_trashes_go_to_finder(tmp_path):
    """11-14: the KB backup prunes old iCloud bundles through Finder (they belong in Recently Deleted), and
    /usr/bin/trash cannot move iCloud Drive files, so every prune failed after the shim went in."""
    log, env = setup(tmp_path)
    home = tmp_path / 'home'
    icloud = home / 'Library/Mobile Documents/com~apple~CloudDocs/backups'
    icloud.mkdir(parents=True)
    old = icloud / 'old.bundle.enc'
    old.write_text('x')
    run(dict(env, HOME=str(home)), '-e', FINDER.format(old))
    assert [l.split()[0] for l in log.read_text().splitlines()] == ['real']      # straight to Finder
    log.write_text('')
    failing = tmp_path / 'trash'
    failing.write_text('#!/bin/sh\necho "trash $*" >> {}\nexit 1\n'.format(log))
    local = tmp_path / 'local.txt'
    local.write_text('x')
    run(env, '-e', FINDER.format(local))
    assert [l.split()[0] for l in log.read_text().splitlines()] == ['trash', 'real']   # tried, then fell back
