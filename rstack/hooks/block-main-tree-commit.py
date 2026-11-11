#!/usr/bin/env python3
"""PreToolUse(Bash) guard: block a `git commit` that would land in a repository's MAIN checkout.

Why: the repository this came from uses a worktree workflow. Agents work in a worktree, then a
`land` step merges main in and fast-forwards main. The main checkout is still visible to agents,
because it holds gitignored files they must read and that exist nowhere else. A session read those
files from the main checkout, then edited and committed tracked files there too, putting commits
straight on main and skipping the land step. The worktree had identical files the whole time.

Configure the protected checkouts with RSTACK_MAIN_TREES (paths separated by ':'). With nothing
configured the hook allows everything.

It denies a Bash `git commit` whose EFFECTIVE working tree resolves to a protected checkout. It is
intentionally narrow:
  - only an actual `git commit` subcommand, so merges and fast-forwards (the land step) pass, as do
    `git log`, `git status` and a script that commits internally,
  - never a worktree, because `rev-parse --show-toplevel` inside a worktree returns the worktree,
  - it follows `cd` and `git -C` within the command.

Two failures it was fixed for, both of which looked like a quiet guard:
  1. It was DEAD for four months. Its protected path was a directory a consolidation had moved,
     so the comparison could never be true. It now says so on stderr when a configured path is
     not a directory, every time it sees a commit.
  2. It failed OPEN on unreadable input. An internal error on a command that mentions `commit`
     now ASKS. Ask rather than deny: this fires on every Bash call carrying the word, and a
     commit on main is recoverable with git.
"""
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hookfail  # noqa: E402

REASON = ('Blocked: this `git commit` runs in a protected MAIN checkout, which bypasses the '
          'worktree/land flow. Commit in your worktree and land it. '
          '(Check with: git rev-parse --show-toplevel.)')
SEPARATORS = ('&&', '||', ';', '|', '&')


def configured():
    return [p for p in os.environ.get('RSTACK_MAIN_TREES', '').split(os.pathsep) if p.strip()]


def main_trees():
    trees = set()
    for p in configured():
        real = os.path.realpath(os.path.expanduser(p))
        if not os.path.isdir(real):
            print('[block-main-tree-commit] protected path is not a directory, so it can never '
                  'match: {}. Fix RSTACK_MAIN_TREES.'.format(p), file=sys.stderr)
        trees.add(real)
    return trees


def resolve(path, base):
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    return os.path.realpath(path)


def git_toplevel(directory):
    try:
        out = subprocess.run(['git', '-C', directory, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return os.path.realpath(out.stdout.strip()) if out.returncode == 0 else None


def parse_git_segment(tokens):
    """For one shell segment: False if not `git ... commit`, else the -C value (or None)."""
    if 'git' not in tokens:
        return False
    i = tokens.index('git') + 1
    c_dir = None
    while i < len(tokens):
        t = tokens[i]
        if t in ('-C', '--git-dir', '--work-tree'):
            if i + 1 >= len(tokens):
                break
            if t == '-C':
                c_dir = tokens[i + 1]
            i += 2
            continue
        if t == '-c':
            i += 2
            continue
        if t.startswith('-'):
            i += 1
            continue
        return c_dir if t == 'commit' else False
    return False


def triage(raw, event):
    return 'commit' in raw


def body(event):
    if event.get('tool_name') != 'Bash':
        return 0
    command = str((event.get('tool_input') or {}).get('command', ''))
    if 'commit' not in command or not configured():
        return 0
    trees = main_trees()
    workdir = os.path.realpath(event.get('cwd') or os.getcwd())

    try:
        # punctuation_chars splits `cd X&&git commit` into separate tokens; plain shlex.split
        # keeps `X&&git` as one word and the commit slipped through (found in review, 11-07).
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = None

    if tokens is None:
        # Unparseable quoting: deny if it plainly runs git from inside a protected tree.
        in_main = workdir in trees or any('cd ' + t in command for t in trees)
        if in_main and 'git' in command:
            _hookfail.decide('deny', REASON)
        return 0

    segment = []
    for tok in tokens + ['&&']:
        if tok not in SEPARATORS:
            segment.append(tok)
            continue
        if segment:
            if segment[0] == 'cd' and len(segment) >= 2:
                workdir = resolve(segment[1], workdir)
            else:
                c = parse_git_segment(segment)
                if c is not False:
                    gitdir = resolve(c, workdir) if c else workdir
                    if git_toplevel(gitdir) in trees:
                        _hookfail.decide('deny', REASON)
                        return 0
        segment = []
    return 0


if __name__ == '__main__':
    sys.exit(_hookfail.run('block-main-tree-commit.py', body, triage,
                           guards='`git commit` landing directly in a protected main checkout',
                           on_error='ask'))
