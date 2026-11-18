"""Deletion actions are guarded; writing or quoting deletion code is ordinary text."""
import json
import shlex

import pytest

from rstack_hookcall import HOOKS, allowed, bash, blocked

HOOK = HOOKS / 'trash-guard.py'


@pytest.fixture
def protection(tmp_path):
    keep = tmp_path / 'release'
    keep.mkdir()
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    return keep, {'RSTACK_PROTECTED_PATHS': str(registry)}


@pytest.mark.parametrize('tool,key', [('Edit', 'new_string'), ('Write', 'content')])
def test_file_contents_are_never_deletion_actions(tool, key, protection):
    keep, env = protection
    for content in ('/usr/bin/trash $f', f'rm -rf {keep}',
                    f'osascript -e \'tell application "Finder" to delete POSIX file "{keep}"\''):
        allowed(HOOK, {'tool_name': tool, 'tool_input': {
            'file_path': '/work/cleanup.sh', key: content}}, env=env)
    # Even a broken payload must not send Edit/Write text through raw error triage.
    allowed(HOOK, {'tool_name': tool, 'tool_input': '/usr/bin/trash $f'}, env=env)


@pytest.mark.parametrize('command', [
    'echo "use trash not rm"',
    'echo trash "$f"',
    'printf "%s\\n" rm /protected',
    'echo \'osascript -e tell application "Finder" to delete POSIX file "/protected"\'',
    "cat <<'EOF'\n/usr/bin/trash $f\nrm -rf ~/x\nEOF",
    "python3 - <<'EOF'\ns = '''it's fine: /usr/bin/trash $f'''\nEOF\nls",
    'echo "use trash not rm',  # same unfinished-quote fallback as the model gate
])
def test_mentions_pass_even_with_unreadable_protection_metadata(command, tmp_path):
    registry = tmp_path / 'broken.json'
    registry.write_text('not json')
    allowed(HOOK, bash(command), env={'RSTACK_PROTECTED_PATHS': str(registry)})


@pytest.mark.parametrize('prefix', ['', 'env X=1 ', 'sudo ', 'command '])
@pytest.mark.parametrize('flags', ['-rf', '-fr', '-r -f', '--recursive --force'])
def test_forced_recursive_rm_is_blocked_without_a_registry(prefix, flags):
    blocked(HOOK, bash(prefix + '/bin/rm ' + flags + ' ~/x'))


@pytest.mark.parametrize('template', [
    '/usr/bin/trash {path}', 'rm -f {path}', 'rmdir {path}', 'unlink {path}',
    'echo ready; /usr/bin/trash {path}', 'echo ready\n/usr/bin/trash {path}',
    'env X=1 /usr/bin/trash {path}', 'sudo /usr/bin/trash {path}',
    'env -u UNUSED /usr/bin/trash {path}', 'sudo -u root /usr/bin/trash {path}',
    'printf "" | xargs /usr/bin/trash {path}',
    'find . -exec /usr/bin/trash {path} \\;',
    'mv {path} ~/.Trash/',
    '/usr/bin/trash "{path}',  # malformed quote still checks the actual operand
])
def test_real_protected_deletions_stay_blocked(template, protection):
    keep, env = protection
    blocked(HOOK, bash(template.format(path=keep)), env=env)
    assert keep.exists()


def test_quoted_protected_paths_are_only_checked_when_executed(protection):
    keep, env = protection
    deletion = f'/usr/bin/trash {shlex.quote(str(keep))}'
    allowed(HOOK, bash('echo ' + shlex.quote(deletion)), env=env)
    allowed(HOOK, bash(f"cat <<'EOF'\n{deletion}\nEOF"), env=env)
    for wrapper in ('sh -c ', 'bash -lc ', 'ssh example.invalid '):
        blocked(HOOK, bash(wrapper + shlex.quote(deletion)), env=env)


def test_finder_delete_is_checked_only_on_execution(protection):
    keep, env = protection
    command = 'osascript -e ' + shlex.quote(f'tell application "Finder" to delete POSIX file "{keep}"')
    blocked(HOOK, bash(command), env=env)
    blocked(HOOK, bash('ssh example.invalid ' + shlex.quote(command)), env=env)
    allowed(HOOK, bash('echo ' + shlex.quote(command)), env=env)


def test_actual_unresolved_deletions_still_refuse(protection):
    _, env = protection
    blocked(HOOK, bash('/usr/bin/trash "$UNRESOLVED_RELEASE"'), env=env)
    blocked(HOOK, bash('mv "$UNRESOLVED_RELEASE" ~/.Trash'), env=env)


def test_quotes_in_actual_protected_filenames_are_preserved(tmp_path):
    keep = tmp_path / "release'"
    keep.mkdir()
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    blocked(HOOK, bash('/usr/bin/trash ' + shlex.quote(str(keep))),
            env={'RSTACK_PROTECTED_PATHS': str(registry)})
