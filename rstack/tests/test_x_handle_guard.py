"""x-handle-guard: no X action from a browser that is not logged in as the posting account."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'x-handle-guard'
LOADER = importlib.machinery.SourceFileLoader('x_handle_guard', str(TOOL))
SPEC = importlib.util.spec_from_loader('x_handle_guard', LOADER)
guard = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(guard)
C = 'mcp__claude-in-chrome__'


@pytest.fixture
def run(tmp_path, monkeypatch):
    env = dict(RSTACK_STATE_DIR=str(tmp_path), X_HANDLE_GUARD_HANDLE='example_sci', PATH='/usr/bin:/bin')

    def call(event_name, tool, tool_input, response=None, session='s1'):
        event = dict(hook_event_name=event_name, session_id=session, tool_name=C + tool, tool_input=tool_input)
        if response is not None:
            event['tool_response'] = response
        out = subprocess.run([sys.executable, str(TOOL)], input=json.dumps(event), capture_output=True,
                             text=True, env=env, timeout=10)
        assert out.returncode == 0
        return json.loads(out.stdout)['hookSpecificOutput'] if out.stdout.strip() else None
    return call


def probe(run, tab, answer, session='s1'):
    run('PreToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=tab, text=guard.PROBE), session=session)
    run('PostToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=tab, text=guard.PROBE),
        response=[dict(type='text', text='XHANDLE=' + answer)], session=session)


LIKE = dict(action='left_click', tabId=7, coordinate=[1, 2], action_summary='Likes the post')


def test_click_refused_until_probe_returns_the_handle(run):
    run('PostToolUse', 'select_browser', dict(deviceId='dev-a'), response=[])
    denied = run('PreToolUse', 'computer', LIKE)
    assert denied['permissionDecision'] == 'deny' and guard.PROBE in denied['permissionDecisionReason']
    probe(run, 7, 'example_sci')
    assert run('PreToolUse', 'computer', LIKE) is None


def test_wrong_account_is_refused_and_named(run):
    run('PostToolUse', 'select_browser', dict(deviceId='dev-main'), response=[])
    probe(run, 7, 'someone_else')
    denied = run('PreToolUse', 'computer', LIKE)
    assert denied['permissionDecision'] == 'deny' and '@someone_else' in denied['permissionDecisionReason']


def test_switching_browser_forgets_the_probe(run):
    run('PostToolUse', 'select_browser', dict(deviceId='dev-a'), response=[])
    probe(run, 7, 'example_sci')
    run('PostToolUse', 'select_browser', dict(deviceId='dev-b'), response=[])
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'


def test_reads_and_navigation_pass_without_a_probe(run):
    for tool, inp in (('computer', dict(action='screenshot', tabId=7)), ('navigate', dict(tabId=7, url='https://x.com/home')),
                      ('get_page_text', dict(tabId=7)), ('list_connected_browsers', {}),
                      ('javascript_tool', dict(action='javascript_exec', tabId=7, text=guard.PROBE))):
        assert run('PreToolUse', tool, inp) is None


def test_other_scripts_typing_and_batches_act(run):
    script = dict(action='javascript_exec', tabId=7, text="document.querySelector('[data-testid=like]').click()")
    assert run('PreToolUse', 'javascript_tool', script)['permissionDecision'] == 'deny'
    assert run('PreToolUse', 'computer', dict(action='type', tabId=7, text='hi'))['permissionDecision'] == 'deny'
    batch = dict(actions=[dict(name='navigate', input=dict(tabId=7, url='https://x.com/a')),
                          dict(name='computer', input=LIKE)])
    assert run('PreToolUse', 'browser_batch', batch)['permissionDecision'] == 'deny'
    probe(run, 7, 'example_sci')
    assert run('PreToolUse', 'browser_batch', batch) is None


def test_probe_in_one_tab_does_not_clear_another(run):
    probe(run, 7, 'example_sci')
    assert run('PreToolUse', 'computer', dict(LIKE, tabId=8))['permissionDecision'] == 'deny'


def test_a_lookalike_probe_does_not_count(run):
    fake = dict(action='javascript_exec', tabId=7, text="'XHANDLE=example_sci'")
    run('PostToolUse', 'javascript_tool', fake, response=[dict(type='text', text='XHANDLE=example_sci')])
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'


def test_unclear_answer_and_missing_tab_and_bad_input_refuse(run):
    run('PostToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=7, text=guard.PROBE),
        response=[dict(type='text', text='XHANDLE=example_sci XHANDLE=other')])
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'
    assert run('PreToolUse', 'computer', dict(action='left_click'))['permissionDecision'] == 'deny'
    assert run('PreToolUse', 'computer', 'not an object')['permissionDecision'] == 'deny'


def test_sessions_are_separate_and_other_tools_ignored(run):
    probe(run, 7, 'example_sci', session='s1')
    assert run('PreToolUse', 'computer', LIKE, session='s2')['permissionDecision'] == 'deny'
    bash = subprocess.run([sys.executable, str(TOOL)], input=json.dumps(dict(
        hook_event_name='PreToolUse', session_id='s1', tool_name='Bash', tool_input=dict(command='ls'))),
        capture_output=True, text=True, timeout=10)
    assert bash.returncode == 0 and not bash.stdout.strip()


def test_no_configured_handle_refuses_everything(tmp_path):
    def call(event):
        out = subprocess.run([sys.executable, str(TOOL)], input=json.dumps(event), capture_output=True, text=True,
                             env=dict(RSTACK_STATE_DIR=str(tmp_path), PATH='/usr/bin:/bin'), timeout=10)
        return json.loads(out.stdout)['hookSpecificOutput'] if out.stdout.strip() else None
    js = dict(action='javascript_exec', tabId=7, text=guard.PROBE)
    call(dict(hook_event_name='PostToolUse', session_id='s1', tool_name=C + 'javascript_tool', tool_input=js,
              tool_response=[dict(type='text', text='XHANDLE=')]))
    assert call(dict(hook_event_name='PreToolUse', session_id='s1', tool_name=C + 'computer',
                     tool_input=LIKE))['permissionDecision'] == 'deny'


def test_expired_probe_refuses(run, tmp_path):
    probe(run, 7, 'example_sci')
    state = tmp_path / 'x-handle-guard' / 's1.json'
    data = json.loads(state.read_text())
    data['tabs']['7']['utc'] -= 3 * 3600
    state.write_text(json.dumps(data))
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'
