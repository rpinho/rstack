import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
spec = importlib.util.spec_from_file_location('protected_paths', TOOLS / 'protected_paths.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture(autouse=True)
def tools_import_path(monkeypatch):
    # The spec loader above doesn't add the tool's directory as a normal import
    # or script invocation would. Make its sibling parser importable too.
    monkeypatch.syspath_prepend(str(TOOLS))


def test_releases_contents_parents_and_aliases_refuse(tmp_path):
    release = tmp_path / 'releases/game/old'
    release.mkdir(parents=True)
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(release)]}))
    alias = tmp_path / 'alias'
    alias.symlink_to(release, target_is_directory=True)
    for p in (release, release / 'asset', release.parent, tmp_path, alias, alias / 'asset', registry):
        with pytest.raises(ValueError, match='protected release'):
            module.assert_disposable([p], registry)
    module.assert_disposable([release.parent / 'unprotected'], registry)
    assert release.exists()


def test_sources_reread_and_invalid_sources_fail_closed(tmp_path):
    source, registry = tmp_path / 'source.json', tmp_path / 'registry.json'
    registry.write_text(json.dumps({'sources': [str(source)]}))
    with pytest.raises(FileNotFoundError):
        module.assert_disposable([tmp_path / 'other'], registry)
    source.write_text(json.dumps({'paths': [str(tmp_path / 'old')]}))
    with pytest.raises(ValueError):
        module.assert_disposable([tmp_path / 'old'], registry)
    source.write_text(json.dumps({'paths': [str(tmp_path / 'new')]}))
    module.assert_disposable([tmp_path / 'old'], registry)
    with pytest.raises(ValueError):
        module.assert_disposable([tmp_path / 'new'], registry)
    source.write_text(json.dumps({'sources': [str(registry)]}))
    with pytest.raises(ValueError, match='cycle'):
        module.assert_disposable([tmp_path], registry)


def test_cli_and_finder_shim_cannot_trash_protected_release(tmp_path):
    keep = tmp_path / 'keep'
    keep.mkdir()
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    import os
    env = {**os.environ, 'RSTACK_PROTECTED_PATHS': str(registry),
           'OSASCRIPT_TRASH': '/usr/bin/false', 'OSASCRIPT_REAL': '/usr/bin/true'}
    for command in ([sys.executable, str(TOOLS / 'release-protect'), '--registry', str(registry), str(keep)],
                    [sys.executable, str(TOOLS / 'osascript'), '-e', f'tell application "Finder" to delete POSIX file "{keep}"']):
        r = subprocess.run(command, env=env, capture_output=True, text=True)
        assert r.returncode == 1, r.stderr
        assert 'protected release' in r.stderr
        assert keep.exists()


def test_shell_trash_and_rm_check_protected_operands(tmp_path):
    keep = tmp_path / 'release'
    keep.mkdir()
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    for command in (f'/usr/bin/trash "{keep}"', f'rm -rf -- "{keep.parent}"',
                    f'echo ready; trash "{keep}"', f'trash "{keep}/*"', 'trash "$UNRESOLVED_RELEASE"'):
        with pytest.raises(ValueError):
            module.assert_shell_disposable(command, registry)
    module.assert_shell_disposable(f'trash "{tmp_path}/unrelated"', registry)


def test_harness_only_install_keeps_the_trash_guard(tmp_path):
    import os
    import shutil
    harness = TOOLS.parents[1] / 'harness'
    installed = tmp_path / 'installed'
    installed.mkdir()
    for name in ('storage.py', 'settings.py', 'protected_paths.py'):
        shutil.copyfile(harness / name, installed / name)
    keep = tmp_path / 'release'
    keep.mkdir()
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    code = "import storage; storage.trash(" + repr(str(keep)) + ")"
    result = subprocess.run([sys.executable, '-c', code], cwd=installed,
                            env={**os.environ, 'PYTHONPATH': str(installed),
                                 'RSTACK_PROTECTED_PATHS': str(registry)},
                            text=True, capture_output=True)
    assert result.returncode == 1
    assert 'protected release' in result.stderr
    assert keep.exists()


def test_copied_hook_and_helpers_work_without_a_repo_or_harness(tmp_path):
    import os
    import shutil
    home = tmp_path / 'home'
    hooks = home / '.claude/hooks'
    tools = home / '.local/bin'
    hooks.mkdir(parents=True)
    tools.mkdir(parents=True)
    for name in ('trash-guard.py', '_hookfail.py'):
        shutil.copyfile(TOOLS.parent / 'hooks' / name, hooks / name)
    for name in ('protected_paths.py', 'shell_commands.py'):
        shutil.copyfile(TOOLS / name, tools / name)
    keep = home / 'release'
    keep.mkdir()
    registry = home / 'protected.json'
    registry.write_text(json.dumps({'paths': [str(keep)]}))
    env = {**os.environ, 'HOME': str(home), 'PYTHONPATH': '',
           'RSTACK_PROTECTED_PATHS': str(registry)}
    for command, denied in ((f'/usr/bin/trash "{keep}"', True),
                            ('echo "use trash not rm"', False)):
        result = subprocess.run([sys.executable, str(hooks / 'trash-guard.py')],
                                input=json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}}),
                                cwd=home, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        assert ('"permissionDecision": "deny"' in result.stdout) == denied
    assert keep.exists()
