"""The fail-safe rule as a test: every registered guard runs through _hookfail, or says why not.

11-10: hook-audit on a KB project found three send gates that crashed on malformed events and so
failed open; none used the wrapper. These tests hold the wrapper's two refinements (a failed lookup
asks; a fail-closed guard refuses on any error) and the checker that makes the wrapper mandatory.
The live checks read this host's real settings only when RSTACK_LIVE_HOME names its home.
"""
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from rstack_hookcall import HOOKS, TOOLS, allowed, blocked, call, loud


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(TOOLS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


wc = load('hook-wrap-check')
audit = load('hook-audit')


def probe(tmp_path, body, triage='lambda raw, e: "danger" in raw', **kw):
    hook = tmp_path / 'probe.py'
    hook.write_text('import sys, subprocess\nsys.path.insert(0, {!r})\nimport _hookfail\n{}\n'
                    'sys.exit(_hookfail.run("probe.py", body, {}, guards="danger"{}))\n'.format(
                        str(HOOKS), body, triage, ''.join(', {}={!r}'.format(k, v) for k, v in kw.items())))
    return hook


# ---------------------------------------------------------------------- the two refinements

def test_a_failed_lookup_asks_and_names_what_it_could_not_read(tmp_path):
    hook = probe(tmp_path, 'def body(event):\n'
                           '    _hookfail.lookup("the forge (gh pr view)", subprocess.run, ["false"], check=True)\n'
                           '    return 0')
    r = call(hook, {'tool_input': {'command': 'gh pr merge 1'}})
    assert r['decision'] == 'ask' and 'could not read the forge (gh pr view)' in r['stdout']
    assert 'CalledProcessError' not in r['stdout'], 'the lookup error itself is not echoed'


def test_the_refusal_names_the_real_hook_file(tmp_path):
    """11-10: it said ~/.claude/hooks/NAME, wrong for a project hook such as a KB send gate."""
    hook = probe(tmp_path, 'def body(event):\n    raise RuntimeError("x")')
    r = blocked(hook, {'tool_input': 'danger'})
    assert 'Hook: {}'.format(os.path.abspath(hook)) in r['stdout'], r['stdout']
    assert '~/.claude/hooks/probe.py' not in r['stdout']


def test_fail_closed_refuses_on_any_error_whatever_the_triage_says(tmp_path):
    body = 'def body(event):\n    raise RuntimeError("x")'
    closed = probe(tmp_path, body, triage='lambda raw, e: False', fail_closed=True)
    r = blocked(closed, {'tool_input': 'harmless'})
    assert r['decision'] == 'deny'
    blocked(closed, 'not json at all')
    # The same hook without fail_closed lets an unguarded call through, loudly.
    open_ = probe(tmp_path, body, triage='lambda raw, e: False')
    loud(open_, {'tool_input': 'harmless'})


def test_the_fail_closed_acts_are_named():
    sys.path.insert(0, str(HOOKS))
    import _hookfail
    assert set(_hookfail.FAIL_CLOSED_ACTS) == {'send', 'merge', 'push', 'delete', 'publish'}


# ---------------------------------------------------------------------- the wrapper is the rule

@pytest.fixture
def hooks(tmp_path):
    d = tmp_path / 'hooks'
    d.mkdir()
    shutil.copy(HOOKS / '_hookfail.py', d / '_hookfail.py')   # the current wrapper, so nothing here drifts
    (d / 'wrapped.py').write_text('import _hookfail\nsys.exit(_hookfail.run("w", body))\n')
    (d / 'plain.py').write_text('import sys\ntry:\n    pass\nexcept Exception:\n    sys.exit(0)\n')
    (d / 'gate.sh').write_text('#!/bin/sh\nexit 0\n')
    (d / 'gate_shim.py').write_text('import _hookfail, subprocess\n'
                                    'sys.exit(_hookfail.run("gate", lambda e: subprocess.run(["gate.sh"]).returncode))\n')
    return d


def settings(tmp_path, *commands, name='settings.json'):
    p = tmp_path / name
    p.write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
        {'type': 'command', 'command': c} for c in commands]}]}}))
    return str(p)


def states(rows):
    return {Path(wc.script_of(r['command'], r['project'])).name: r['state'] for r in rows}


def test_only_wrapped_python_passes(tmp_path, hooks):
    s = settings(tmp_path, 'python3 {}/wrapped.py'.format(hooks), 'python3 {}/plain.py'.format(hooks),
                 'bash {}/gate.sh'.format(hooks), 'python3 {}/gate_shim.py'.format(hooks),
                 'python3 {}/gone.py'.format(hooks))
    got = states(wc.check([s], [], {}))
    assert got == {'wrapped.py': 'ok', 'plain.py': 'UNWRAPPED', 'gate.sh': 'UNWRAPPED',
                   'gate_shim.py': 'ok', 'gone.py': 'MISSING'}
    assert wc.main([s, '--allow', str(tmp_path / 'none.json')]) == 1


def test_a_shell_trampoline_counts_only_in_its_fail_closed_shape(tmp_path, hooks):
    """KB b723a00bc: a .sh kept for its name, handing off to a wrapped .py and refusing if that cannot run."""
    (hooks / 'send-gate.py').write_text('import _hookfail\nsys.exit(_hookfail.run("s", body))\n')
    (hooks / 'plain-gate.py').write_text('import sys\nsys.exit(0)\n')
    shapes = {
        'closed.sh': '#!/bin/bash\n# why\npython3 "$(dirname "$0")/send-gate.py" && exit 0\n'
                     'echo "gate could not run" >&2\nexit 2\n',
        'exec.sh': '#!/bin/bash\nexec python3 "$(dirname "$0")/send-gate.py"\n',   # cannot start: exit 1, allow
        'open.sh': '#!/bin/bash\npython3 "$(dirname "$0")/send-gate.py" && exit 0\nexit 0\n',
        'unwrapped.sh': '#!/bin/bash\npython3 "$(dirname "$0")/plain-gate.py" && exit 0\nexit 2\n',
        'more.sh': '#!/bin/bash\npython3 "$(dirname "$0")/send-gate.py" && exit 0\nrm x\nexit 2\n',
    }
    for name, text in shapes.items():
        (hooks / name).write_text(text)
    s = settings(tmp_path, *['bash {}/{}'.format(hooks, n) for n in shapes])
    got = states(wc.check([s], [], {}))
    assert got == {'closed.sh': 'ok', 'exec.sh': 'UNWRAPPED', 'open.sh': 'UNWRAPPED',
                   'unwrapped.sh': 'UNWRAPPED', 'more.sh': 'UNWRAPPED'}


def test_a_hook_on_an_old_wrapper_is_drifted_until_main_is_installed(tmp_path, hooks, monkeypatch):
    """11-10: the KB send gates import ~/.claude/hooks/_hookfail.py, which was older than main and had
    neither lookup nor fail_closed."""
    s = settings(tmp_path, 'python3 {}/wrapped.py'.format(hooks))
    (hooks / '_hookfail.py').write_text('def run(*a, **k):\n    return 0\n')
    rows = wc.check([s], [], {})
    assert rows[0]['state'] == 'DRIFTED' and 'install it from main' in rows[0]['detail']
    assert wc.main([s, '--allow', str(tmp_path / 'none.json')]) == 1
    shutil.copy(HOOKS / '_hookfail.py', hooks / '_hookfail.py')
    assert states(wc.check([s], [], {})) == {'wrapped.py': 'ok'}
    # A project hook that loads the user-level wrapper is held to the same copy.
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    proj = tmp_path / 'proj'
    (proj / '.claude/hooks').mkdir(parents=True)
    (proj / '.claude/hooks/send-gate.py').write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path.home() / '.claude/hooks'))\n"
        "import _hookfail\nsys.exit(_hookfail.run('send-gate.py', body))\n")
    (proj / '.claude/settings.json').write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
        {'type': 'command', 'command': '"$CLAUDE_PROJECT_DIR/.claude/hooks/send-gate.py"'}]}]}}))
    rows = wc.check([], [str(proj)], {})
    assert rows[0]['state'] == 'DRIFTED' and 'missing' in rows[0]['detail']
    (home / '.claude/hooks').mkdir(parents=True)
    shutil.copy(HOOKS / '_hookfail.py', home / '.claude/hooks/_hookfail.py')
    assert [r['state'] for r in wc.check([], [str(proj)], {})] == ['ok']
    assert [r['state'] for r in wc.check([], [str(proj)], {}, lib=None)] == ['ok']


def test_an_allowlisted_guard_needs_a_reason_and_expires(tmp_path, hooks):
    s = settings(tmp_path, 'bash {}/gate.sh'.format(hooks))
    allow = {'gate.sh': {'reason': 'migration to a wrapped shim in progress', 'until': '2026-11-12'}}
    assert states(wc.check([s], [], allow, today=dt.date(2026, 11, 11))) == {'gate.sh': 'allowed'}
    rows = wc.check([s], [], allow, today=dt.date(2026, 11, 13))
    assert rows[0]['state'] == 'UNWRAPPED' and 'expired 2026-11-12' in rows[0]['detail']
    pol = tmp_path / 'policy.json'
    pol.write_text(json.dumps({'allow': {'gate.sh': {'reason': 'ok'}}}))
    with pytest.raises(ValueError):
        wc.load_policy(pol)


def test_project_settings_are_held_to_the_same_rule(tmp_path, hooks):
    proj = tmp_path / 'proj'
    (proj / '.claude').mkdir(parents=True)
    (proj / '.claude/settings.json').write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Edit', 'hooks': [
        {'type': 'command', 'command': 'bash "$CLAUDE_PROJECT_DIR/gate.sh"'}]}]}}))
    (proj / 'gate.sh').write_text('#!/bin/sh\nexit 0\n')
    rows = wc.check([], [str(proj)], {})
    assert [r['state'] for r in rows] == ['UNWRAPPED']


def test_the_shipped_example_settings_are_all_wrapped(tmp_path):
    example = json.loads((HOOKS / 'settings.example.json').read_text())
    for groups in example['hooks'].values():
        for g in groups:
            for h in g['hooks']:
                h['command'] = h['command'].replace('~/src/rstack/rstack/hooks', str(HOOKS))
    p = tmp_path / 'example.json'
    p.write_text(json.dumps(example))
    rows = wc.check([str(p)], [], {})
    assert rows and all(r['state'] == 'ok' for r in rows), [r for r in rows if r['state'] != 'ok']


# ---------------------------------------------------------------------- this host's live settings
# The suite is hermetic (conftest replaces HOME), so these read the real settings only when asked:
#     RSTACK_LIVE_HOME=$HOME python3 -m pytest -q rstack/tests/test_hook_policy.py
# hook-audit-daily and the install step run exactly that.

LIVE_HOME = os.environ.get('RSTACK_LIVE_HOME')
live = pytest.mark.skipif(not LIVE_HOME or not (Path(LIVE_HOME) / '.config/rstack/hook-allowlist.json').is_file(),
                          reason='live hook checks are opt-in: set RSTACK_LIVE_HOME to a home that has '
                                 '.config/rstack/hook-allowlist.json')


@pytest.fixture
def real_home(monkeypatch):
    monkeypatch.setenv('HOME', LIVE_HOME)
    monkeypatch.delenv('RSTACK_HOOK_ALLOWLIST', raising=False)
    home = Path(LIVE_HOME)
    allow, projects = wc.load_policy(home / '.config/rstack/hook-allowlist.json')
    user = home / '.claude/settings.json'
    return allow, projects, [str(user)] if user.is_file() else []


@live
def test_every_live_guard_on_this_host_runs_through_the_wrapper(real_home):
    allow, projects, user = real_home
    rows = wc.check(user, [p for p in projects if (Path(p) / '.claude/settings.json').is_file()], allow)
    bad = [(r['state'], r['detail'], r['settings']) for r in rows if r['state'] not in ('ok', 'allowed')]
    assert rows and not bad, bad


@live
def test_no_live_guard_on_this_host_crashes_on_malformed_input(real_home):
    """hook-audit as the backstop: a crash is an allow. Guards on a live allowlist entry are the
    known exceptions while they are migrated."""
    allow, projects, paths = real_home
    found = audit.hooks(paths)
    for p in projects:
        f = Path(p) / '.claude/settings.json'
        if f.is_file():
            found += [dict(h, project=p) for h in audit.hooks([str(f)])]
    today = dt.date.today()
    excused = {n for n, e in allow.items() if not e.get('until') or dt.date.fromisoformat(e['until']) >= today}
    crashes = []
    for h in found:
        name = Path(wc.script_of(h['command'], h.get('project'))).name
        rows = audit.audit([h], h.get('project'))
        crashes += [(name, r['payload'], r['result']) for r in rows
                    if r['result'].startswith('CRASHED') and name not in excused]
    assert not crashes, crashes
