"""The KB template's send gates and main-tree guard: each refuses what it guards, allows the rest,
fails closed on input it cannot read, and takes everything personal from its config file."""
import datetime as dt
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / 'kb/.claude/hooks'
BROWSER = 'mcp__claude-in-chrome__computer'


def call(script, event, env=None, raw=None, via=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(('KB_', 'RSTACK_', 'RH_'))}
    e.update(env or {})
    argv = ['bash', str(HOOKS / via)] if via else [sys.executable, str(HOOKS / script)]
    return subprocess.run(argv, input=raw if raw is not None else json.dumps(event), env=e,
                          text=True, capture_output=True, timeout=60)


def decision(proc):
    if not proc.stdout.strip():
        return None
    out = json.loads(proc.stdout)
    if 'systemMessage' in out:
        return 'warn'
    return out['hookSpecificOutput']['permissionDecision']


def click(summary, action='left_click'):
    return {'tool_name': BROWSER, 'tool_input': {'action': action, 'action_summary': summary}}


def stamp(path, minutes_ago=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    path.write_text(json.dumps({'utc': t.isoformat()}))


def gates(tmp_path, **sections):
    p = tmp_path / 'gates.json'
    p.write_text(json.dumps(sections))
    return {'KB_GATES_CONFIG': str(p)}


def test_the_kb_wrapper_is_the_rstack_wrapper():
    """The KB template ships its own copy so it works standalone; it must never drift from main."""
    assert (HOOKS / '_hookfail.py').read_bytes() == (REPO / 'rstack/hooks/_hookfail.py').read_bytes()


def test_the_gates_carry_no_personal_literals():
    text = ''.join((HOOKS / n).read_text() for n in (
        'friend-reply-gate.py', 'voice-send-gate.py', 'email-voice-gate.py', 'guard-main-tree.py', '_kbgate.py',
        'gates.example.json'))
    import re
    assert not re.search(r'/(?:Users|home)/[a-z]', text), 'a host path belongs in the gates config'
    assert not re.search(r'[\w.+-]+@(?!example\.invalid)[\w-]+\.[a-z]{2,}', text), 'no addresses in the gates'


def test_kb_settings_register_only_wrapped_guards():
    loader = importlib.machinery.SourceFileLoader('hook_wrap_check', str(REPO / 'rstack/tools/hook-wrap-check'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    wc = importlib.util.module_from_spec(spec)
    loader.exec_module(wc)
    rows = [r for r in wc.check([], [str(REPO / 'kb')], {}) if r.get('event', 'PreToolUse') == 'PreToolUse']
    assert rows and all(r['state'] == 'ok' for r in rows), rows


# ------------------------------------------------------------------------------ friend-reply

def test_friend_reply_gate_needs_a_fresh_lint_or_approval(tmp_path):
    lint = tmp_path / 'state/reply-lint/pass.json'
    env = gates(tmp_path, friend_reply={'reply_lint_stamp': str(lint), 'extra_reason': 'OWNER-LINE'})
    send = click('Click Send on the email reply to the thread')
    r = call('friend-reply-gate.py', send, env)
    assert decision(r) == 'deny' and 'OWNER-LINE' in r.stdout
    stamp(lint, minutes_ago=5)
    assert decision(call('friend-reply-gate.py', send, env)) is None
    stamp(lint, minutes_ago=45)
    assert decision(call('friend-reply-gate.py', send, env)) == 'deny'
    # not an email send, not this gate's business
    assert decision(call('friend-reply-gate.py', click('Click send on the tweet'), env)) is None
    assert decision(call('friend-reply-gate.py', click('Open the email'), env)) is None
    # a send inside a browser batch is seen too
    batch = {'tool_name': 'mcp__claude-in-chrome__browser_batch',
             'tool_input': {'actions': [{'name': 'computer', 'input': send['tool_input']}]}}
    assert decision(call('friend-reply-gate.py', batch, env)) == 'deny'


def test_friend_reply_gate_accepts_a_recent_outreach_approval(tmp_path):
    root = tmp_path / 'runtime'
    ledger = root / 'lanes/demo/OUTREACH.jsonl'
    ledger.parent.mkdir(parents=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    ledger.write_text(json.dumps({'id': 'o1', 'status': 'approved',
                                  'approval': {'utc': now, 'quote': 'yes, send it'}}) + '\n')
    env = gates(tmp_path, outreach_root=str(root))
    assert decision(call('friend-reply-gate.py', click('Click Send on the gmail reply'), env)) is None


def test_friend_reply_gate_refuses_what_it_cannot_read(tmp_path):
    r = call('friend-reply-gate.py', None, raw='{"tool_name": "' + BROWSER + '", "tool_input": {"action": "left_click", "action_summary": "Send the ema')
    assert decision(r) == 'deny'
    bad = tmp_path / 'gates.json'
    bad.write_text('{not json')
    r = call('friend-reply-gate.py', click('Click Send on the email'), {'KB_GATES_CONFIG': str(bad)})
    assert decision(r) == 'deny'
    # the shell trampoline passes the decision through
    r = call(None, click('Click Send on the email'), via='friend-reply-gate.sh')
    assert r.returncode == 0 and decision(r) == 'deny'


# -------------------------------------------------------------------------------- voice-send

def test_voice_send_gate_needs_a_fresh_voice_cuts_pass(tmp_path):
    state = tmp_path / 'voice-cuts'
    env = gates(tmp_path, voice_send={'voice_cuts_state': str(state)})
    send = click('Press Enter to send the message in the chat', action='key')
    assert decision(call('voice-send-gate.py', send, env)) == 'deny'
    stamp(state / 'pass.json', minutes_ago=1)
    assert decision(call('voice-send-gate.py', send, env)) is None
    stamp(state / 'pass.json', minutes_ago=30)
    for allowed in ('Click send on the email', 'Click send on the tweet', 'Click send, photo with no caption',
                    'Click send on the image model prompt'):
        assert decision(call('voice-send-gate.py', click(allowed), env)) is None, allowed
    assert decision(call('voice-send-gate.py', None, raw='[1, 2]')) == 'deny'


# ------------------------------------------------------------------------------------- email

def checker(tmp_path, fails=False):
    p = tmp_path / ('fail-check.py' if fails else 'ok-check.py')
    p.write_text('import sys\nsys.stdin.read()\n' + ('print("FAIL: sounds generated")\n' if fails else 'print("PASS")\n'))
    return [sys.executable, str(p)]


def gmail(body):
    return {'tool_name': 'mcp__claude_ai_Gmail__send_message', 'tool_input': {'to': 'a@example.invalid', 'body': body}}


def test_email_gate_runs_the_voice_check_then_the_approval(tmp_path):
    root = tmp_path / 'runtime'
    env = gates(tmp_path, outreach_root=str(root), email={'voice_command': checker(tmp_path, fails=True)})
    r = call('email-voice-gate.py', gmail('hello there'), env)
    assert decision(r) == 'deny' and 'sounds generated' in r.stdout

    env = gates(tmp_path, outreach_root=str(root), email={'voice_command': checker(tmp_path)})
    assert decision(call('email-voice-gate.py', gmail('hello there'), env)) == 'warn'
    env_deny = gates(tmp_path, outreach_root=str(root),
                     email={'voice_command': checker(tmp_path), 'outreach_gate': 'deny'})
    assert decision(call('email-voice-gate.py', gmail('hello there'), env_deny)) == 'deny'

    draft = tmp_path / 'draft.txt'
    draft.write_text('hello there')
    digest = hashlib.sha256(b'hello there').hexdigest()
    ledger = root / 'lanes/demo/OUTREACH.jsonl'
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({'id': 'o1', 'status': 'approved', 'draft_path': str(draft),
                                  'approval': {'sha256': digest, 'quote': 'ok', 'utc': 'x'}}) + '\n')
    assert decision(call('email-voice-gate.py', gmail('hello there'), env_deny)) is None
    assert decision(call('email-voice-gate.py', gmail('hello there!'), env_deny)) == 'deny'   # bytes differ


def test_email_gate_fails_closed(tmp_path):
    env = gates(tmp_path, email={'voice_command': [str(tmp_path / 'no-such-checker')]})
    r = call('email-voice-gate.py', gmail('hello'), env)
    assert decision(r) == 'deny' and 'unavailable' in r.stdout
    assert decision(call('email-voice-gate.py', None, raw='not json')) == 'deny'
    assert decision(call('email-voice-gate.py', {'tool_name': 'x', 'tool_input': ['a']})) == 'deny'


# --------------------------------------------------------------------------- guard-main-tree

def git(*args, cwd):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                   cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def kb(tmp_path):
    main = tmp_path / 'main'
    (main / 'wiki').mkdir(parents=True)
    (main / 'wiki/Page.md').write_text('# p\n')
    (main / '.gitignore').write_text('private/\n')
    git('init', '-q', '-b', 'main', cwd=main)
    git('add', 'wiki/Page.md', '.gitignore', cwd=main)
    git('commit', '-qm', 'init', cwd=main)
    git('worktree', 'add', '-q', str(tmp_path / 'wt'), '-b', 'session', cwd=main)
    return os.path.realpath(str(main)), os.path.realpath(str(tmp_path / 'wt'))


def edit(path):
    return {'tool_name': 'Edit', 'tool_input': {'file_path': path}}


def test_guard_main_tree_blocks_tracked_and_new_main_tree_files(kb):
    main, wt = kb
    env = {'CLAUDE_PROJECT_DIR': main}
    for via in (None, 'guard-main-tree.sh'):
        assert call('guard-main-tree.py', edit(main + '/wiki/Page.md'), env, via=via).returncode == 2
    assert call('guard-main-tree.py', edit(main + '/wiki/New Page.md'), env).returncode == 2
    assert call('guard-main-tree.py', edit(main + '/outbox/note.md'), env).returncode == 0
    assert call('guard-main-tree.py', edit(main + '/private/x.md'), env).returncode == 0
    assert call('guard-main-tree.py', edit(wt + '/wiki/Page.md'), {'CLAUDE_PROJECT_DIR': wt}).returncode == 0


def test_guard_main_tree_reads_its_areas_from_config_and_refuses_on_error(kb, tmp_path):
    main, _ = kb
    env = dict(gates(tmp_path, guard_main_tree={'tracked_areas': ['notes/']}), CLAUDE_PROJECT_DIR=main)
    assert call('guard-main-tree.py', edit(main + '/notes/a.md'), env).returncode == 2
    assert call('guard-main-tree.py', edit(main + '/wiki/New.md'), env).returncode == 0
    # unreadable input that names the main tree is refused; one that does not is allowed
    raw = '{"tool_input": {"file_path": "' + main + '/wiki/Page.md"'
    assert decision(call('guard-main-tree.py', None, {'CLAUDE_PROJECT_DIR': main}, raw=raw)) == 'deny'
    r = call('guard-main-tree.py', None, {'CLAUDE_PROJECT_DIR': main}, raw='{"tool_input": {"file_path": "/elsewhere"')
    assert r.returncode == 0 and decision(r) is None
