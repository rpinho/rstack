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


def on_x(run, tab, session='s1', url='https://x.com/home'):
    """The tab is on X: what navigate's Tab Context tells the guard."""
    run('PostToolUse', 'navigate', dict(tabId=tab, url=url),
        response=[dict(type='text', text='Navigated to ' + url),
                  dict(type='text', text='\n\nTab Context:\n- Executed on tabId: {0}\n- Available tabs:\n'
                                        '  \u2022 tabId {0}: "Home / X" ("{1}")'.format(tab, url))], session=session)


def probe(run, tab, answer, session='s1'):
    on_x(run, tab, session=session)
    run('PreToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=tab, text=guard.PROBE), session=session)
    run('PostToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=tab, text=guard.PROBE),
        response=[dict(type='text', text='XHANDLE=' + answer)], session=session)


LIKE = dict(action='left_click', tabId=7, coordinate=[1, 2], action_summary='Likes the post')


def test_click_refused_until_probe_returns_the_handle(run):
    run('PostToolUse', 'select_browser', dict(deviceId='dev-a'), response=[])
    on_x(run, 7)
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
    on_x(run, 7)
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'


def test_reads_and_navigation_pass_without_a_probe(run):
    for tool, inp in (('computer', dict(action='screenshot', tabId=7)), ('navigate', dict(tabId=7, url='https://x.com/home')),
                      ('get_page_text', dict(tabId=7)), ('list_connected_browsers', {}),
                      ('javascript_tool', dict(action='javascript_exec', tabId=7, text=guard.PROBE))):
        assert run('PreToolUse', tool, inp) is None


def test_other_scripts_typing_and_batches_act(run):
    on_x(run, 7)
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
    on_x(run, 8)
    assert run('PreToolUse', 'computer', dict(LIKE, tabId=8))['permissionDecision'] == 'deny'


def test_a_lookalike_probe_does_not_count(run):
    on_x(run, 7)
    fake = dict(action='javascript_exec', tabId=7, text="'XHANDLE=example_sci'")
    run('PostToolUse', 'javascript_tool', fake, response=[dict(type='text', text='XHANDLE=example_sci')])
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'


def test_unclear_answer_and_bad_input_refuse(run):
    on_x(run, 7)
    run('PostToolUse', 'javascript_tool', dict(action='javascript_exec', tabId=7, text=guard.PROBE),
        response=[dict(type='text', text='XHANDLE=example_sci XHANDLE=other')])
    assert run('PreToolUse', 'computer', LIKE)['permissionDecision'] == 'deny'
    # A call it cannot read is refused on a known X tab, and passes anywhere else.
    bad_x = dict(actions='not a list', tabId=7, action='left_click')
    assert run('PreToolUse', 'browser_batch', bad_x)['permissionDecision'] == 'deny'
    assert run('PreToolUse', 'browser_batch', dict(bad_x, tabId=3)) is None
    assert run('PreToolUse', 'computer', 'not an object') is None


def test_sessions_are_separate_and_other_tools_ignored(run):
    probe(run, 7, 'example_sci', session='s1')
    on_x(run, 7, session='s2')
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
    call(dict(hook_event_name='PostToolUse', session_id='s1', tool_name=C + 'navigate',
              tool_input=dict(tabId=7, url='https://x.com/home'), tool_response=[]))
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



def test_non_x_tabs_are_not_this_guards_business(run):
    """11-19, general: a page script on any other tab (MecCog, Gmail, a review page) must pass."""
    title = dict(action='javascript_exec', tabId=1, text='document.title')
    assert run('PreToolUse', 'javascript_tool', title) is None          # a tab never seen
    on_x(run, 1, url='https://mail.google.com/mail/u/0/')
    assert run('PreToolUse', 'javascript_tool', title) is None          # a tab seen on Gmail
    assert run('PreToolUse', 'form_input', dict(tabId=1, ref='ref_3', value='hello')) is None
    assert run('PreToolUse', 'computer', dict(action='left_click', tabId=1, coordinate=[3, 4],
                                               action_summary='Clicks Send in Gmail')) is None
    on_x(run, 1, url='https://twitter.com/home')                         # the same tab moved to X
    assert run('PreToolUse', 'javascript_tool', title)['permissionDecision'] == 'deny'


def test_tab_urls_come_from_tab_context_and_tabs_json(run):
    run('PostToolUse', 'tabs_context_mcp', {}, response=[dict(type='text', text=json.dumps(dict(availableTabs=[
        dict(tabId=4, title='Home / X', url='https://x.com/home'), dict(tabId=5, title='Inbox', url='https://mail.google.com/')])))])
    assert run('PreToolUse', 'computer', dict(LIKE, tabId=4))['permissionDecision'] == 'deny'
    assert run('PreToolUse', 'computer', dict(LIKE, tabId=5)) is None



# hook-audit's probe inputs (rstack/tools/hook-audit PAYLOADS), with the tool name its matcher gives.
AUDIT_TOOL = 'mcp__claude-in-chrome__'
AUDIT = [('unparseable text', 'not json {'), ('a JSON string', json.dumps('tool_input')),
         ('a JSON list', json.dumps([{'tool_name': AUDIT_TOOL}])),
         ('tool_input a string', json.dumps({'tool_name': AUDIT_TOOL, 'tool_input': 'rm -rf /'})),
         ('tool_input a list', json.dumps({'tool_name': AUDIT_TOOL, 'tool_input': [{'command': 'x'}]})),
         ('fields of the wrong type', json.dumps({'tool_name': AUDIT_TOOL, 'tool_input': {
             'command': ['x'], 'action_summary': {'a': 1}, 'actions': 'x', 'body': 3, 'file_path': None}}))]


@pytest.mark.parametrize('label,raw', AUDIT)
def test_hook_audit_probes_never_crash(tmp_path, label, raw):
    """11-19: both X guards exited 1 on a JSON string or list, and a crash is an allow."""
    out = subprocess.run([sys.executable, str(TOOL)], input=raw, capture_output=True, text=True, timeout=10,
                         env=dict(RSTACK_STATE_DIR=str(tmp_path), X_HANDLE_GUARD_HANDLE='example_sci', PATH='/usr/bin:/bin'))
    assert out.returncode == 0, out.stderr
    assert not out.stdout.strip() or json.loads(out.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_handle_comes_from_the_shared_config(tmp_path):
    cfg = tmp_path / 'gate.json'
    cfg.write_text(json.dumps(dict(handle='example_sci', deny_devices=[])))
    env = dict(RSTACK_STATE_DIR=str(tmp_path), X_SUBMIT_GATE_CONFIG=str(cfg), PATH='/usr/bin:/bin')

    def call(name, inp, event='PreToolUse', response=None):
        ev = dict(hook_event_name=event, session_id='s1', tool_name=C + name, tool_input=inp)
        if response is not None:
            ev['tool_response'] = response
        out = subprocess.run([sys.executable, str(TOOL)], input=json.dumps(ev), capture_output=True,
                             text=True, env=env, timeout=10)
        return json.loads(out.stdout)['hookSpecificOutput'] if out.stdout.strip() else None
    call('navigate', dict(tabId=7, url='https://x.com/home'), 'PostToolUse', [])
    js = dict(action='javascript_exec', tabId=7, text=guard.PROBE)
    call('javascript_tool', js, 'PostToolUse', [dict(type='text', text='XHANDLE=example_sci')])
    assert call('computer', LIKE) is None
