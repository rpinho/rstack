"""Every rstack hook: the real thing refused, the innocent thing allowed, broken input handled.

See rstack_hookcall.py for the four-part contract.
"""
import json
from pathlib import Path

import pytest

from rstack_hookcall import HOOKS, allowed, bash, blocked, call, loud


@pytest.fixture
def env(tmp_path):
    # Attended, so the guards' own ask/deny choices are what these tests see; the ask default
    # outside the conductor has its own tests below.
    return {'RSTACK_STATE_DIR': str(tmp_path / 'state'), 'RSTACK_ATTENDED': '1'}


# ------------------------------------------------------------------------------- _hookfail

def test_wrapper_refuses_guarded_and_reports_unguarded(tmp_path):
    hook = tmp_path / 'probe.py'
    hook.write_text(
        'import sys\n'
        'sys.path.insert(0, {!r})\n'
        'import _hookfail\n'
        'def body(event):\n'
        '    raise RuntimeError("secret-token-in-the-message")\n'
        'sys.exit(_hookfail.run("probe.py", body, lambda raw, e: "danger" in raw, guards="danger"))\n'
        .format(str(HOOKS)))
    r = blocked(hook, {'tool_input': 'danger'})
    assert r['decision'] == 'deny'
    assert 'RuntimeError' in r['stdout']
    assert 'secret-token' not in r['stdout'] + r['stderr'], 'exception text must never be echoed'
    loud(hook, {'tool_input': 'harmless'})


def test_wrapper_treats_a_raising_triage_as_guarded(tmp_path):
    hook = tmp_path / 'probe2.py'
    hook.write_text(
        'import sys\n'
        'sys.path.insert(0, {!r})\n'
        'import _hookfail\n'
        'def triage(raw, e):\n'
        '    raise KeyError("x")\n'
        'sys.exit(_hookfail.run("probe2.py", lambda e: 0, triage))\n'.format(str(HOOKS)))
    blocked(hook, 'not json')
    allowed(hook, {'tool_name': 'Bash'})


# ----------------------------------------------------------------------------- trash-guard

FINDER = 'osascript -e \'tell application "Finder" to delete POSIX file "/tmp/x"\''


def test_trash_guard():
    h = HOOKS / 'trash-guard.py'
    blocked(h, bash(FINDER))
    allowed(h, bash('/usr/bin/trash /tmp/x'))
    allowed(h, bash('ls -la'))
    for bad in ({'tool_name': 'Bash', 'tool_input': FINDER},
                '{"tool_name": "Bash", "tool_input": {"command": "ls"'):
        assert 'could not complete its check' in allowed(h, bad)['context']


# ------------------------------------------------------------------------- pod-deadline-gate

POD = 'mcp__plugin_runpod_runpod__create-pod'
SELF_KILLING = {'tool_name': POD, 'tool_input': {'body': {
    'entrypoint': ['/bin/bash', '-c'],
    'cmd': ['(sleep 3600; curl -X POST podTerminate) & exec /start.sh']}}}


def test_pod_deadline_gate():
    h = HOOKS / 'pod-deadline-gate.py'
    allowed(h, SELF_KILLING)
    allowed(h, {'tool_name': POD, 'tool_input': SELF_KILLING['tool_input']['body']})   # flattened
    blocked(h, {'tool_name': POD, 'tool_input': {'body': {'cmd': ['exec /start.sh']}}})
    blocked(h, {'tool_name': POD, 'tool_input': {'body': {
        'entrypoint': ['/bin/bash', '-c'], 'cmd': ['(sleep 999999; curl podTerminate) &']}}})
    # Everything here is a pod creation, so there is no "unrelated" case: every unreadable input
    # refuses. This is the one that used to create a pod with no kill.
    for bad in ('not json', {}, [], {'tool_name': POD, 'tool_input': 'body'},
                {'tool_name': POD, 'tool_input': {'body': 'cmd'}}):
        blocked(h, bad)


def test_pod_deadline_gate_is_configurable():
    h = HOOKS / 'pod-deadline-gate.py'
    other = {'tool_name': 'create_machine', 'tool_input': {
        'cmd': '(sleep 600; provider-cli destroy-self) & exec serve'}}
    blocked(h, other)
    allowed(h, other, env={'RSTACK_POD_KILL_MARKER': 'destroy-self'})
    blocked(h, SELF_KILLING, env={'RSTACK_POD_MAX_SECONDS': '60'})


# --------------------------------------------------------------------------- pod-create-gate

def pod_request(lane='team'):
    return {'tool_name': POD, 'tool_input': {'body': {
        'name': lane + '-worker', 'env': {'RH_LANE': lane},
        'vcpuCount': 32, 'computeType': 'CPU', 'gpuCount': 0}}}


def test_pod_create_gate(tmp_path):
    h = HOOKS / 'pod-create-gate.py'
    env = {'RH_POD_GATE_AUDIT': str(tmp_path / 'audit.jsonl'),
           'RH_POD_GATE_CONFIG': str(tmp_path / 'absent.json')}
    allowed(h, bash('ls'), env=env)                         # not a create-pod call
    r = allowed(h, pod_request(), env=env)                  # audit mode: allowed, but recorded
    assert 'audit' in r['context']
    assert json.loads((tmp_path / 'audit.jsonl').read_text().splitlines()[-1])['mode'] == 'audit'
    blocked(h, 'not json', env=env)                         # used to exit 1, which allows

    cfg = tmp_path / 'enforce.json'
    cfg.write_text(json.dumps({'mode': 'enforce', 'enforce_lanes': ['team']}))
    blocked(h, pod_request(), env=dict(env, RH_POD_GATE_CONFIG=str(cfg)))   # no receipt


def test_pod_create_gate_refuses_when_its_implementation_is_gone(tmp_path):
    r = blocked(HOOKS / 'pod-create-gate.py', pod_request(),
                env={'RSTACK_POD_GATE_IMPL': str(tmp_path / 'missing.py')})
    assert r['decision'] == 'deny'


# ----------------------------------------------------------------------- conductor-inbox-gate

def test_conductor_inbox_gate(tmp_path):
    h = HOOKS / 'conductor-inbox-gate.py'
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    (inbox / 'conductor.addr').write_text('uds:/tmp/cc-sock-123')
    env = {'CONDUCTOR_INBOX_DIR': str(inbox), 'CONDUCTOR_NAME': 'conductor'}

    def send(to):
        return {'tool_name': 'SendMessage', 'tool_input': {'to': to, 'message': 'hi'}}

    blocked(h, send('conductor'), env=env)
    blocked(h, send('conductor [conductor session]'), env=env)
    blocked(h, send('uds:/tmp/cc-sock-123'), env=env)
    allowed(h, send('worker-a'), env=env)
    allowed(h, send('uds:/tmp/cc-sock-1234'), env=env)       # a different socket
    allowed(h, bash('relay fyi "done"'), env=env)
    blocked(h, '{"tool_name":"SendMessage","tool_input":{"to":"conductor"', env=env)   # truncated
    blocked(h, {'tool_name': 'SendMessage', 'tool_input': 'conductor'}, env=env)
    loud(h, 'not json', env=env)
    blocked(h, send('lead'), env=dict(env, CONDUCTOR_NAME='lead'))


# ---------------------------------------------------------------------- read-the-thread-first

def click(summary, action='left_click', sid='t1'):
    return {'tool_name': 'mcp__claude-in-chrome__computer', 'session_id': sid,
            'tool_input': {'action': action, 'action_summary': summary}}


def test_read_the_thread_first(env):
    h = HOOKS / 'read-the-thread-first.py'
    send = click('click Send on the email reply in the thread')
    blocked(h, send, env=env)
    allowed(h, click('click Send on the tweet'), env=env)                 # posts are not gated
    allowed(h, click('click Send on the email reply # thread-read-ok'), env=env)
    allowed(h, click('take a screenshot of the thread', action='screenshot'), env=env)
    blocked(h, send, env=env)                                             # a screenshot is not a read
    allowed(h, {'tool_name': 'mcp__claude-in-chrome__get_page_text', 'session_id': 't1',
                'tool_input': {}}, env=env)
    allowed(h, send, env=env)                                             # now it may send
    blocked(h, click('click Send on the email reply in the thread', sid='t2'), env=env)
    batch = {'tool_name': 'mcp__claude-in-chrome__browser_batch', 'session_id': 't3',
             'tool_input': {'actions': [{'tool': 'computer', 'input': {
                 'action': 'left_click', 'action_summary': 'click Send on the email reply'}}]}}
    blocked(h, batch, env=env)
    blocked(h, {'tool_name': 'mcp__claude-in-chrome__computer', 'session_id': 't1',
                'tool_input': 'left_click Send the email'}, env=env)       # unreadable, looks guarded
    loud(h, 'not json', env=env)


def test_every_hook_uses_the_failsafe_wrapper():
    # The wrapper's contract is PreToolUse (allow/deny/ask). A hook wired only to another event
    # would have to degrade to letting the call through instead.
    settings = json.loads((HOOKS / 'settings.example.json').read_text())
    pre = {Path(h['command'].split()[-1]).name for g in settings['hooks']['PreToolUse'] for h in g['hooks']}
    for hook in sorted(HOOKS.glob('*.py')):
        if hook.name.startswith('_') or hook.name not in pre:
            continue
        assert '_hookfail.run(' in hook.read_text(), hook.name + ' does not run fail-safe'


def test_settings_example_names_only_hooks_that_exist():
    settings = json.loads((HOOKS / 'settings.example.json').read_text())
    named = set()
    for groups in settings['hooks'].values():
        for group in groups:
            for h in group['hooks']:
                if '/hooks/' in h['command']:
                    named.add(Path(h['command'].split()[-1]).name)
    on_disk = {p.name for p in HOOKS.glob('*.py') if not p.name.startswith('_')}
    assert named == on_disk, (named ^ on_disk)


# ------------------------------------------------------------------- adopted from the laptop, 11-11

def test_lane_no_questions(tmp_path):
    h = HOOKS / 'lane-no-questions.py'
    ask = lambda cwd: {'tool_name': 'AskUserQuestion', 'tool_input': {}, 'cwd': cwd}
    e = {'CONDUCTOR_CWD_SUFFIX': '/src/conductor', 'TMUX': ''}
    blocked(h, ask('/home/u/src/lane-a'), env=e)
    allowed(h, ask('/home/u/src/conductor'), env=e)
    allowed(h, bash('ls'), env=e)
    blocked(h, 'not json AskUserQuestion', env=e)


def test_unattended_turns_ask_into_deny(tmp_path):
    h = asker(tmp_path)
    r = call(h, ev('/home/u/kb/general'), env={'RSTACK_UNATTENDED': '1', 'RSTACK_STATE_DIR': str(tmp_path)})
    assert r['decision'] == 'deny' and 'RSTACK_UNATTENDED=1' in r['stdout']


# --------------------------------------------------- asks only where someone answers (11-11 PM)

def asker(tmp_path):
    hook = tmp_path / 'asker.py'
    hook.write_text('import sys\nsys.path.insert(0, {!r})\nimport _hookfail\n'
                    'def body(event):\n'
                    '    _hookfail.decide("ask", "probe wants a person")\n'
                    '    return 0\n'
                    'sys.exit(_hookfail.run("asker.py", body, guards="probe"))\n'.format(str(HOOKS)))
    return hook


def ev(cwd):
    return {'tool_name': 'Bash', 'tool_input': {'command': 'SECRET-INPUT-TEXT'}, 'cwd': cwd,
            'session_id': 'sess-1'}


def test_an_ask_stays_an_ask_only_where_someone_answers(tmp_path):
    """Interactive lanes run unwatched in tmux, and an ask prompts even with permissions bypassed:
    a silent stall. Only the conductor, or a session started with RSTACK_ATTENDED=1, keeps an ask."""
    h = asker(tmp_path)
    base = {'RSTACK_STATE_DIR': str(tmp_path / 'state'), 'CONDUCTOR_CWD_SUFFIX': '/kb/general'}
    assert call(h, ev('/home/u/kb/general'), env=base)['decision'] == 'ask'
    lane = call(h, ev('/home/u/kb/math'), env=base)
    assert lane['decision'] == 'deny' and 'Nobody can answer a prompt' in lane['stdout']
    assert 'probe wants a person' in lane['stdout']                       # the guard's own reason is kept
    assert call(h, ev('/home/u/kb/math'), env=dict(base, RSTACK_ATTENDED='1'))['decision'] == 'ask'
    assert call(h, ev('/home/u/kb/general'), env=dict(base, RSTACK_UNATTENDED='1'))['decision'] == 'deny'
    assert call(h, ev('/home/u/kb/math'), env={'RSTACK_STATE_DIR': str(tmp_path / 's2')})['decision'] == 'deny'


def test_every_ask_is_ledgered_without_the_tool_input(tmp_path):
    h = asker(tmp_path)
    base = {'RSTACK_STATE_DIR': str(tmp_path / 'state'), 'CONDUCTOR_CWD_SUFFIX': '/kb/general'}
    call(h, ev('/home/u/kb/general'), env=base)
    call(h, ev('/home/u/kb/math'), env=base)
    text = (tmp_path / 'state/hook-asks.jsonl').read_text()
    rows = [json.loads(l) for l in text.splitlines()]
    assert [(r['cwd'], r['outcome'], r['guard'], r['session_id']) for r in rows] == [
        ('general', 'ask', 'asker.py', 'sess-1'), ('math', 'deny', 'asker.py', 'sess-1')]
    assert 'SECRET-INPUT-TEXT' not in text
    assert set(rows[0]) == {'utc', 'session_id', 'cwd', 'guard', 'outcome', 'reason'}


def test_an_unwritable_ledger_leaves_the_decision_alone(tmp_path):
    h = asker(tmp_path)
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('a file where the state directory should be')
    r = call(h, ev('/home/u/kb/general'), env={'RSTACK_STATE_DIR': str(blocker), 'CONDUCTOR_CWD_SUFFIX': '/kb/general'})
    assert r['decision'] == 'ask' and 'ask ledger' in r['stderr']


def test_allow_and_deny_are_untouched_and_not_ledgered(tmp_path):
    h = HOOKS / 'trash-guard.py'
    state = tmp_path / 'state'
    allowed(h, bash('ls'), env={'RSTACK_STATE_DIR': str(state)})
    blocked(h, bash(FINDER), env={'RSTACK_STATE_DIR': str(state)})
    assert not (state / 'hook-asks.jsonl').exists()


def test_gate_pipe_guard(env):
    h = HOOKS / 'gate-pipe-guard.py'
    blocked(h, bash('python3 -m pytest -q | tail -3'), env=env)
    blocked(h, bash('npm run lint 2>&1 | grep error'), env=env)
    allowed(h, bash('set -o pipefail; python3 -m pytest -q | tail -3'), env=env)
    allowed(h, bash('python3 -m pytest -q'), env=env)
    allowed(h, bash('git log --oneline | head -5'), env=env)
    loud(h, '[1]', env=env)                                   # broken, and nothing gate-like is piped
    blocked(h, 'not json: pytest | tail', env=env)            # broken, and it looks like the real thing
