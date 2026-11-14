#!/usr/bin/env python3
"""guard-main-tree: PreToolUse hook (Edit|Write|NotebookEdit) for this KB.

Enforces the concurrency rule mechanically: agent edits to TRACKED files belong in a session
worktree (edit there, then land), never in the MAIN tree. Also blocks CREATING new files inside the
tracked areas of the main tree. Stays out of the way everywhere else:
  - any worktree (including ones that live inside the main tree's path) -> allowed
  - gitignored paths (private originals you keep out of git)            -> allowed
  - untracked scratch areas (inbox/, outbox/, settings.local.json)      -> allowed

The main tree is KB_MAIN, else discovered from git (the parent of the shared --git-common-dir).
The tracked areas and files come from the `guard_main_tree` section of the gates config (see
_kbgate.py); the defaults below are this template's own layout.

Why it is Python: the shell version failed open on every error (a python3 or git failure fell
through to exit 0, so the edit went ahead). It now runs through _hookfail: an error on a path in
the main tree refuses, a git lookup that errors asks, and any other path is allowed with the
failure on stderr. guard-main-tree.sh stays as a trampoline so settings keep working.
Exit 2 blocks the tool call and feeds stderr back to the model.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kbgate  # noqa: E402

NAME = 'guard-main-tree.py'
GUARDS = 'edits to tracked files in the main KB tree'
AREAS = ('wiki/', 'raw/', 'scripts/', 'memory/', 'templates/', '.agents/', '.claude/skills/')
FILES = ('state.md', 'index.md', 'log.md', 'goals.md', 'AGENTS.md', 'CLAUDE.md', 'CONVENTIONS.md',
         'README.md')


def main_tree():
    explicit = os.environ.get('KB_MAIN')
    if explicit:
        return os.path.realpath(os.path.expanduser(explicit))
    here = os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()
    run = subprocess.run(['git', '-C', here, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                         capture_output=True, text=True, timeout=8)
    if run.returncode != 0:
        return None          # not in a git repo: nothing to guard
    return os.path.realpath(os.path.dirname(run.stdout.strip()))


def git(main, *args):
    return subprocess.run(['git', '-C', main, *args], capture_output=True, text=True, timeout=8)


def tracked(main, rel):
    run = git(main, 'ls-files', '--', rel)
    if run.returncode != 0:
        raise RuntimeError('git ls-files exit {}'.format(run.returncode))
    return bool(run.stdout.strip())


def ignored(main, rel):
    run = git(main, 'check-ignore', '-q', '--', rel)
    if run.returncode not in (0, 1):   # 0 ignored, 1 not ignored, anything else is git failing
        raise RuntimeError('git check-ignore exit {}'.format(run.returncode))
    return run.returncode == 0


def in_nested_worktree(main, path):
    """A worktree inside the main tree's path has its own .git FILE somewhere between it and MAIN."""
    d = os.path.dirname(path)
    while d not in (main, '/', ''):
        if os.path.isfile(os.path.join(d, '.git')):
            return True
        d = os.path.dirname(d)
    return False


def block(msg):
    print(msg, file=sys.stderr)
    return 2


def body(event):
    ti = event.get('tool_input') or {}
    if not isinstance(ti, dict):
        raise TypeError('tool_input')
    fp = ti.get('file_path') or ti.get('notebook_path')
    if not fp:
        return 0
    if not isinstance(fp, str):
        raise TypeError('file_path')
    cfg = _kbgate.config('guard_main_tree')
    main = _hookfail.lookup('the main tree (git rev-parse)', main_tree)
    if not main:
        return 0
    path = os.path.realpath(os.path.expanduser(fp))
    if not path.startswith(main + '/') or in_nested_worktree(main, path):
        return 0
    rel = path[len(main) + 1:]
    if _hookfail.lookup('the KB index (git ls-files)', tracked, main, rel):
        return block("BLOCKED by guard-main-tree: '{}' is a TRACKED file in the MAIN tree ({}). Tracked edits "
                     "happen in a session worktree: edit there, then land onto main (AGENTS.md, Concurrency). "
                     "Untracked scratch areas and gitignored paths are not blocked.".format(rel, main))
    if _hookfail.lookup('the KB ignore rules (git check-ignore)', ignored, main, rel):
        return 0
    areas = tuple(cfg.get('tracked_areas') or AREAS)
    files = tuple(cfg.get('tracked_files') or FILES)
    if rel.startswith(areas) or rel in files:
        return block("BLOCKED by guard-main-tree: '{}' would create a new file in a TRACKED area of the MAIN "
                     "tree ({}). Create it in a session worktree instead, then land.".format(rel, main))
    return 0


def triage(raw, event):
    """On an error: could this be an edit in the main tree? Substring work on the raw text only."""
    for root in (os.environ.get('KB_MAIN'), os.environ.get('CLAUDE_PROJECT_DIR')):
        if root and os.path.expanduser(root).rstrip('/') in raw:
            return True
    return not (os.environ.get('KB_MAIN') or os.environ.get('CLAUDE_PROJECT_DIR'))


if __name__ == '__main__':
    try:
        _hookfail = _kbgate.load_wrapper()
    except Exception:
        raw = sys.stdin.read()
        if triage(raw, None):
            print(NAME + ': _hookfail.py would not load, so this possible main-tree edit is refused. '
                  'Repair .claude/hooks/_hookfail.py.', file=sys.stderr)
            sys.exit(2)
        print('[{}] _hookfail.py would not load; not a main-tree path, allowed.'.format(NAME), file=sys.stderr)
        sys.exit(0)
    sys.exit(_hookfail.run(NAME, body, triage, guards=GUARDS))
