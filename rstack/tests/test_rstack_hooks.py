"""Every rstack hook: the real thing refused, the innocent thing allowed, broken input handled.

See rstack_hookcall.py for the four-part contract.
"""
import json
from pathlib import Path
import subprocess

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


# ------------------------------------------------------------------------------ poll-guard

def test_poll_guard_denies_the_third_identical_check(env):
    h = HOOKS / 'poll-guard.py'
    poll = bash('tail -5 train.log', session_id='s1')
    allowed(h, poll, env=env)
    allowed(h, bash('tail -20 train.log', session_id='s1'), env=env)   # same check, new literal
    r = blocked(h, poll, env=env)
    assert 'event-watch wait' in r['stdout']
    allowed(h, bash('tail -5 train.log', session_id='other'), env=env)  # per session


def test_poll_guard_never_blocks_the_escapes(env):
    h = HOOKS / 'poll-guard.py'
    for _ in range(4):
        allowed(h, bash('tail -5 train.log # poll-ok', session_id='s2'), env=env)
        allowed(h, {'tool_name': 'Bash', 'session_id': 's2',
                    'tool_input': {'command': 'tail -5 train.log', 'run_in_background': True}}, env=env)
        allowed(h, bash('git status', session_id='s2'), env=env)
        allowed(h, bash('cat a.log > b.log', session_id='s2'), env=env)   # writes: not a poll


def test_poll_guard_stays_open_but_not_silent(tmp_path):
    h = HOOKS / 'poll-guard.py'
    loud(h, 'not json')
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'poll-guard').write_text('a file where a directory should be')
    loud(h, bash('tail -5 train.log'), env={'RSTACK_STATE_DIR': str(state)})


# ----------------------------------------------------------------------------- trash-guard

FINDER = 'osascript -e \'tell application "Finder" to delete POSIX file "/tmp/x"\''


def test_trash_guard():
    h = HOOKS / 'trash-guard.py'
    blocked(h, bash(FINDER))
    allowed(h, bash('/usr/bin/trash /tmp/x'))
    allowed(h, bash('ls -la'))
    blocked(h, {'tool_name': 'Bash', 'tool_input': FINDER})            # unreadable, looks guarded
    loud(h, '{"tool_name": "Bash", "tool_input": {"command": "ls"')    # unreadable, unrelated


# ------------------------------------------------------------------ block-main-tree-commit

def git(*args, cwd):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                   cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def trees(tmp_path):
    main = tmp_path / 'main'
    main.mkdir()
    git('init', '-q', '-b', 'main', cwd=main)
    (main / 'a.txt').write_text('a')
    git('add', 'a.txt', cwd=main)
    git('commit', '-q', '-m', 'init', cwd=main)
    wt = tmp_path / 'wt'
    git('worktree', 'add', '-q', '-b', 'feature', str(wt), cwd=main)
    return main, wt


def test_main_tree_commit_refused_worktree_allowed(trees, tmp_path):
    main, wt = trees
    h = HOOKS / 'block-main-tree-commit.py'
    env = {'RSTACK_MAIN_TREES': str(main), 'RSTACK_ATTENDED': '1', 'RSTACK_STATE_DIR': str(tmp_path / 'state')}
    blocked(h, bash('git commit -m x', cwd=str(main)), env=env)
    blocked(h, bash('cd {} && git commit -qm x'.format(main), cwd=str(tmp_path)), env=env)
    blocked(h, bash('git -C {} commit -m x'.format(main), cwd=str(tmp_path)), env=env)
    blocked(h, bash('cd {}&&git commit -qm x'.format(main), cwd=str(tmp_path)), env=env)   # no spaces
    blocked(h, bash('cd {};git commit -qm x'.format(main), cwd=str(tmp_path)), env=env)
    allowed(h, bash('git commit -m x', cwd=str(wt)), env=env)
    allowed(h, bash('git log --oneline -5', cwd=str(main)), env=env)
    allowed(h, bash('git merge --ff-only feature', cwd=str(main)), env=env)   # the land step
    allowed(h, bash('echo "commit later"', cwd=str(main)), env=env)
    r = blocked(h, {'tool_name': 'Bash', 'tool_input': 'git commit -m x'}, env=env)
    assert r['decision'] == 'ask', 'a recoverable harm asks: ' + str(r)
    loud(h, 'not json', env=env)


def test_main_tree_guard_says_when_it_is_dead(tmp_path):
    """It once guarded a path that had moved four months earlier, and nobody could tell."""
    h = HOOKS / 'block-main-tree-commit.py'
    r = allowed(h, bash('git commit -m x', cwd=str(tmp_path)),
                env={'RSTACK_MAIN_TREES': str(tmp_path / 'moved-away')})
    assert 'not a directory' in r['stderr']


def test_main_tree_guard_unconfigured_allows():
    allowed(HOOKS / 'block-main-tree-commit.py', bash('git commit -m x'), env={'RSTACK_MAIN_TREES': ''})


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
    # (results-report-guard on SubagentStop) degrades to letting the report through instead.
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

def test_gate_pipe_guard(env):
    h = HOOKS / 'gate-pipe-guard.py'
    blocked(h, bash('python3 -m pytest -q | tail -3'), env=env)
    blocked(h, bash('npm run lint 2>&1 | grep error'), env=env)
    allowed(h, bash('set -o pipefail; python3 -m pytest -q | tail -3'), env=env)
    allowed(h, bash('python3 -m pytest -q'), env=env)
    allowed(h, bash('git log --oneline | head -5'), env=env)
    loud(h, '[1]', env=env)                                   # broken, and nothing gate-like is piped
    blocked(h, 'not json: pytest | tail', env=env)            # broken, and it looks like the real thing


def test_agent_stdin_guard(env):
    h = HOOKS / 'agent-stdin-guard.py'
    blocked(h, bash('codex exec --skip-git-repo-check "do it"'), env=env)
    blocked(h, bash('cd /tmp && claude -p "summarise"'), env=env)
    blocked(h, bash('env A=1 timeout 600 codex exec "x"'), env=env)
    allowed(h, bash('codex exec "do it" < /dev/null'), env=env)
    allowed(h, bash('cat prompt.md | claude -p'), env=env)
    allowed(h, bash("codex exec - <<'EOF'\nthe prompt\nEOF"), env=env)
    allowed(h, bash('echo "run codex exec later" && grep "claude -p" notes.md'), env=env)
    allowed(h, bash('codex exec --help'), env=env)
    loud(h, '[1]', env=env)


def test_results_brief_guard(env):
    h = HOOKS / 'results-brief-guard.py'
    agent = lambda prompt: {'tool_name': 'Agent', 'tool_input': {'prompt': prompt}}
    blocked(h, agent('Find every caller of foo() and list them.'), env=env)
    blocked(h, agent('You asked: the callers of foo(). I will: list them.'), env=env)   # no Done when
    allowed(h, agent('You asked: the callers of foo(). I will: list them with file:line.\n'
                     'Done when: every caller is listed.'), env=env)
    allowed(h, agent('[followup] also check bar()'), env=env)
    allowed(h, {'tool_name': 'SendMessage', 'tool_input': {'to': 'math', 'message': 'fixed'}}, env=env)
    r = call(h, 'not json "Agent"', env=env)
    assert r['decision'] == 'ask'                             # broken on a brief: asks, never allows


def test_results_report_guard(tmp_path):
    h = HOOKS / 'results-report-guard.py'
    r = call(h, {'last_assistant_message': 'I read twelve files and ran the tests.'})
    assert json.loads(r['stdout'])['decision'] == 'block'
    assert call(h, {'last_assistant_message': 'You asked: X. Shipped: 3 fixes.'})['stdout'] == ''
    assert call(h, {'last_assistant_message': 'activity only', 'stop_hook_active': True})['stdout'] == ''
    r = call(h, 'not json')
    assert r['stdout'] == '' and 'needs repair' in r['stderr']   # degrades, never suppresses a report


def test_lane_no_questions(tmp_path):
    h = HOOKS / 'lane-no-questions.py'
    ask = lambda cwd: {'tool_name': 'AskUserQuestion', 'tool_input': {}, 'cwd': cwd}
    e = {'CONDUCTOR_CWD_SUFFIX': '/src/conductor', 'TMUX': ''}
    blocked(h, ask('/home/u/src/lane-a'), env=e)
    allowed(h, ask('/home/u/src/conductor'), env=e)
    allowed(h, bash('ls'), env=e)
    blocked(h, 'not json AskUserQuestion', env=e)


def test_unattended_turns_ask_into_deny(tmp_path):
    h = HOOKS / 'results-brief-guard.py'
    r = call(h, 'not json "Agent"', env={'RSTACK_UNATTENDED': '1', 'RSTACK_STATE_DIR': str(tmp_path)})
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
    h = HOOKS / 'gate-pipe-guard.py'
    state = tmp_path / 'state'
    allowed(h, bash('ls'), env={'RSTACK_STATE_DIR': str(state)})
    blocked(h, bash('python3 -m pytest -q ' + chr(124) + ' tail -3'), env={'RSTACK_STATE_DIR': str(state)})
    assert not (state / 'hook-asks.jsonl').exists()
