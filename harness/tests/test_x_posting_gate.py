"""Pipe every deployed gate, always with a local fake xurl. No X API calls."""
import concurrent.futures
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import outreach
import rh
import x_gate
from test_outreach import cli

@pytest.fixture(autouse=True)
def _legacy_one_post_quota(monkeypatch):
    """These tests were written for the original 1-per-day rule with no gap; the 3-per-day default is tested explicitly."""
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    monkeypatch.setenv('RH_X_MIN_GAP_MINUTES', '0')


@pytest.fixture(autouse=True)
def _before_the_reply_rules(monkeypatch):
    """These tests predate reply spacing and per-round reply approval (11-08) and post replies
    back to back under the standing approval; test_x_growth.py tests those rules' defaults."""
    defaults = outreach.x_defaults
    monkeypatch.setattr(outreach, 'x_defaults', lambda: dict(
        defaults(), x_reply_gap_minutes=0, x_reply_human_approval=False))


HARNESS = Path(rh.__file__).resolve().parent
# The PreToolUse hook that calls x_gate.hook_decision is installed outside this repository
# (it brings its own shell tokenizer). Point RH_X_HOOK at it to pipe the hook tests; unset, they skip.
HOOK = os.environ.get('RH_X_HOOK', '')
TEXT = 'Which landmark would you measure?\n'


@pytest.fixture
def local(tmp_path, monkeypatch):
    root = tmp_path / 'harness'
    (root / 'lanes/test').mkdir(parents=True)
    replied = tmp_path / 'replied.json'
    replied.write_text('[]')
    monkeypatch.setattr(outreach, 'REPLIED', replied)
    monkeypatch.setenv('RH_X_REPLIED', str(replied))
    monkeypatch.setenv('RH_OUTREACH_ROOT', str(root))
    monkeypatch.setenv('RH_X_GATE_LOG', str(tmp_path / 'x-gate.jsonl'))
    monkeypatch.delenv('RH_X_GATE', raising=False)
    binpath = tmp_path / 'bin'
    binpath.mkdir()
    fake = binpath / 'xurl'
    # The only xurl that can execute in this test is this local stand-in.
    fake.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
Path(os.environ['XURL_TEST_RECORD']).write_text(json.dumps(sys.argv[1:]))
print(json.dumps({'data': {'id': '987654321'}}))
sys.exit(int(os.environ.get('XURL_TEST_EXIT', '0')))
''')
    fake.chmod(0o700)
    # xr is a thin launcher around x_gate.wrapper; this one runs the code under test.
    xr = binpath / 'xr'
    xr.write_text('#!' + sys.executable + '\nimport sys\nsys.path.insert(0, ' + repr(str(HARNESS)) +
                  ')\nfrom x_gate import wrapper\nsys.exit(wrapper(sys.argv[1:]))\n')
    xr.chmod(0o700)
    monkeypatch.setenv('RH_X_ACCOUNT', 'test_account')
    monkeypatch.setenv('XURL_TEST_RECORD', str(tmp_path / 'called.json'))
    monkeypatch.setenv('PATH', str(binpath) + os.pathsep + os.environ['PATH'])
    assert shutil.which('xurl') == str(fake)
    return root


def approve(root, channel='x_reply', text=TEXT, **metadata):
    draft = root / 'body.txt'
    draft.write_text(text)
    args = ['draft', 'test', '--to', '@anna', '--channel', channel, '--purpose', 'Ask about staging', '--file', draft]
    if channel == 'x_reply':
        args += ['--in-reply-to', 'https://x.com/anna/status/123']
    for key, val in metadata.items():
        args += ['--' + key.replace('_', '-'), str(val)]
    result = cli(root, *args)
    assert result[0] == 0, result
    ident = result[1].strip()
    result = cli(root, 'lint', 'test', ident)
    assert result[0] == 0, result
    result = cli(root, 'approve', 'test', ident, '--quote', outreach.STANDING_APPROVAL)
    assert result[0] == 0, result
    return outreach.current(root / 'lanes/test', rh)[ident]


def update(root, row, **extra):
    row = dict(row, **extra)
    rh.append(root / 'lanes/test/OUTREACH.jsonl', row)
    return row


def payload(text=TEXT, reply='123'):
    value = {'text': text}
    if reply:
        value['reply'] = {'in_reply_to_tweet_id': reply}
    return value


def event(path, value=None, summary=None):
    if path == 'bash':
        words = ['xurl', '-X', 'POST', '/2/tweets', '-d', json.dumps(value or payload())]
        return dict(tool_name='Bash', tool_input=dict(command=shlex.join(words)))
    item = dict(action='left_click', action_summary=summary or 'Click Reply to post the reply on X')
    if path == 'batch':
        return dict(tool_name='mcp__claude-in-chrome__browser_batch', tool_input={'actions': [{'name': 'mcp__claude-in-chrome__computer', 'input': item}]})
    return dict(tool_name='mcp__claude-in-chrome__computer', tool_input=item)


def hook_pipe(root, ev, mode='enforce'):
    if not HOOK or not Path(HOOK).is_file():
        pytest.skip('RH_X_HOOK not set to an installed hook')
    env = dict(os.environ)
    if mode is None:
        env.pop('RH_X_GATE', None)
    else:
        env['RH_X_GATE'] = mode
    # Pre-import this repository's x_gate so the hook's own `import x_gate` reuses it.
    shim = ('import sys, runpy; sys.path.insert(0, ' + repr(str(HARNESS)) + '); import x_gate; '
            'sys.argv = [' + repr(HOOK) + ']; runpy.run_path(' + repr(HOOK) + ", run_name='__main__')")
    run = subprocess.run([sys.executable, '-c', shim], input=json.dumps(ev), capture_output=True, text=True, env=env, timeout=10)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout) if run.stdout else None


def xr_pipe(root, value, mode='enforce', args=None):
    env = dict(os.environ)
    if mode is None:
        env.pop('RH_X_GATE', None)
    else:
        env['RH_X_GATE'] = mode
    expected = Path(env['XURL_TEST_RECORD']).parent / 'bin/xurl'
    assert Path(shutil.which('xurl', path=env['PATH'])) == expected
    # JSON tweet is piped into xr -d - as it would be from a local file. Deny network where the OS allows it.
    sandbox = ['/usr/bin/sandbox-exec', '-p', '(version 1)(allow default)(deny network*)'] if Path('/usr/bin/sandbox-exec').exists() else []
    return subprocess.run(sandbox + [str(expected.parent / 'xr'), *(args or ['-X', 'POST', '/2/tweets', '-d', '-'])],
                          input=json.dumps(value), capture_output=True, text=True, env=env, timeout=10)


def logs():
    p = Path(os.environ['RH_X_GATE_LOG'])
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


@pytest.mark.parametrize('value, refused', [(None, True), ('', True), ('enforce', True), ('nonsense', True),
                                             ('warn', False)])
def test_the_gate_is_enforced_unless_warn_is_explicit(local, value, refused):
    """11-09: with RH_X_GATE unset, xr warned and posted a link self-reply that had no approved row."""
    run = xr_pipe(local, payload('Unapproved words.'), value)
    assert Path(os.environ['XURL_TEST_RECORD']).exists() == (not refused)
    assert run.returncode == (2 if refused else 0) and ('REFUSED' if refused else 'WARNING') in run.stderr


@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_xr_pipe_requires_exact_approved_text(local, mode):
    run = xr_pipe(local, payload('Unapproved words.'), mode)
    called = Path(os.environ['XURL_TEST_RECORD']).exists()
    assert called == (mode == 'warn')
    assert run.returncode == (0 if mode == 'warn' else 2)
    assert 'rh outreach draft' in run.stderr and 'rh outreach lint' in run.stderr and 'rh outreach approve' in run.stderr
    assert len(logs()) == 1 and logs()[0]['path'] == 'xr' and logs()[0]['would_block']
    assert 'Unapproved words' not in Path(os.environ['RH_X_GATE_LOG']).read_text()


@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_xr_pipe_approved_pass_preserves_account_and_records_sent(local, mode):
    row = approve(local)
    run = xr_pipe(local, payload(), mode)
    assert run.returncode == 0, run.stderr
    words = json.loads(Path(os.environ['XURL_TEST_RECORD']).read_text())
    assert words[:2] == ['-u', 'test_account']
    latest = outreach.current(local / 'lanes/test', rh)[row['id']]
    assert latest['status'] == 'sent' and latest['sent']['message_id'] == '987654321'
    assert logs() == []


def test_xr_default_enforces(local):
    run = xr_pipe(local, payload('No approval.'), None)
    assert run.returncode == 2 and 'REFUSED' in run.stderr and logs()[0]['mode'] == 'enforce'


@pytest.mark.parametrize('path', ['bash', 'browser', 'batch'])
@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_hook_paths_pipe_unapproved(local, path, mode):
    result = hook_pipe(local, event(path), mode)
    if mode == 'warn':
        assert 'WARNING' in result['systemMessage'] and 'permissionDecision' not in json.dumps(result)
    else:
        assert result['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert logs()[0]['path'] == ('bash-xurl' if path == 'bash' else 'browser')
    assert not Path(os.environ['XURL_TEST_RECORD']).exists()


@pytest.mark.parametrize('path', ['bash', 'browser', 'batch'])
@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_hook_paths_pipe_approved(local, path, mode):
    row = approve(local)
    assert hook_pipe(local, event(path), mode) is None
    latest = outreach.current(local / 'lanes/test', rh)[row['id']]
    assert latest['gate_attempt']['path'] == ('bash-xurl' if path == 'bash' else 'browser')
    assert logs() == [] and not Path(os.environ['XURL_TEST_RECORD']).exists()


def test_hook_default_warn(local):
    assert 'WARNING' in hook_pipe(local, event('bash'), None)['systemMessage']
    assert logs()[0]['mode'] == 'warn'


@pytest.mark.parametrize('status', ['drafted', 'linted', 'sent', 'dropped', 'closed'])
def test_nonapproved_latest_status_refused(local, status):
    row = approve(local)
    update(local, row, status=status)
    assert hook_pipe(local, event('bash'))['hookSpecificOutput']['permissionDecision'] == 'deny'


@pytest.mark.parametrize('change', ['text', 'disk', 'hash', 'lint', 'channel', 'target'])
def test_exact_payload_and_approval_binding(local, change):
    row = approve(local)
    value = payload()
    if change == 'text':
        value['text'] = TEXT.strip()
    elif change == 'disk':
        Path(row['draft_path']).write_text('Changed disk bytes.')
    elif change == 'hash':
        update(local, row, approval=dict(row['approval'], sha256='f' * 64))
    elif change == 'lint':
        update(local, row, lint=dict(ok=False, sha256=row['lint']['sha256']))
    elif change == 'channel':
        update(local, row, channel='email')
    elif change == 'target':
        value['reply']['in_reply_to_tweet_id'] = '124'
    assert hook_pipe(local, event('bash', value))['hookSpecificOutput']['permissionDecision'] == 'deny'


@pytest.mark.parametrize('minutes,allowed', [(19, True), (21, False), (-1, False)])
def test_browser_20_minute_freshness(local, minutes, allowed):
    row = approve(local)
    stamp = (dt.datetime.now(outreach.UTC) - dt.timedelta(minutes=minutes)).isoformat()
    update(local, row, approval=dict(row['approval'], utc=stamp))
    result = hook_pipe(local, event('browser'))
    assert (result is None) == allowed


def test_freshness_exact_20_minute_boundary(local):
    row = approve(local)
    clock = dt.datetime.now(outreach.UTC)
    update(local, row, approval=dict(row['approval'], utc=(clock - dt.timedelta(minutes=20)).isoformat()))
    assert list(x_gate.candidates(local, browser=True, clock=clock))
    assert not list(x_gate.candidates(local, browser=True, clock=clock + dt.timedelta(microseconds=1)))


def test_browser_original_approval_does_not_authorize_reply(local):
    approve(local, channel='x_post', text='The table now has a certificate.')
    assert hook_pipe(local, event('browser'))['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_api_original_and_self_reply_are_bound_to_payload_kind(local):
    row = approve(local, channel='x_post', text='The table now has a certificate.')
    assert hook_pipe(local, event('bash', payload('The table now has a certificate.', '123')))['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert hook_pipe(local, event('bash', payload('The table now has a certificate.', None))) is None


def test_link_self_reply_gate(local):
    text = 'The certificate is at https://github.com/example/results.'
    approve(local, channel='x_post', text=text, self_reply_to='111')
    assert hook_pipe(local, event('bash', payload(text, '111'))) is None


def test_replied_registry_rechecked_after_approval(local):
    approve(local)
    Path(os.environ['RH_X_REPLIED']).write_text('["123"]')
    assert hook_pipe(local, event('bash'))['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_daily_limit_rechecked_at_posting_gate(local):
    approve(local, channel='x_post', text='A checked certificate is ready.')
    other = local / 'lanes/other'
    other.mkdir()
    rh.append(other / 'OUTREACH.jsonl', dict(id='past', lane='other', channel='x_post', text='A previous original.', status='sent', sent={'utc': rh.now()}))
    assert hook_pipe(local, event('bash', payload('A checked certificate is ready.', None)))['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_one_approval_cannot_be_reused(local):
    approve(local)
    assert hook_pipe(local, event('browser')) is None
    assert hook_pipe(local, event('browser'))['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_concurrent_commands_cannot_borrow_one_approval(local):
    approve(local)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(hook_pipe, local, event('browser')) for _ in range(2)]
        results = [j.result(timeout=10) for j in jobs]
    assert sum(r is None for r in results) == 1
    assert len(logs()) == 1


@pytest.mark.parametrize('args', [
    ['-XPOST', '/2/tweets', '-d', '-'],
    ['--request=POST', 'https://api.x.com/2/tweets', '--data', '-'],
    ['--request', 'POST', 'https://api.twitter.com/2/tweets', '--data=-'],
])
def test_xr_method_and_endpoint_forms(local, args):
    assert xr_pipe(local, payload('No approval.'), args=args).returncode == 2


def test_literal_data_file_bash_gate(local):
    approve(local)
    file = local / 'payload.json'
    file.write_text(json.dumps(payload()))
    ev = dict(tool_name='Bash', cwd=str(local), tool_input=dict(command="xurl -X POST /2/tweets --data @payload.json"))
    assert hook_pipe(local, ev) is None


def test_xr_data_file_gate(local):
    approve(local)
    file = local / 'payload.json'
    file.write_text(json.dumps(payload()))
    assert xr_pipe(local, payload(), args=['-X', 'POST', '/2/tweets', '-d', '@' + str(file)]).returncode == 0


@pytest.mark.parametrize('command', [
    'xurl -X POST /2/tweets -d "$TWEET"',
    'cat body.json | xurl -X POST /2/tweets -d -',
    'xurl -X POST /2/tweets -d invalid',
    'xurl -X POST /2/tweets',
    'xurl -X POST /2/tweets -d \'{"text":"One"}\' --data \'{"text":"Two"}\'',
])
def test_opaque_and_ambiguous_payloads_fail_enforce(local, command):
    ev = dict(tool_name='Bash', tool_input={'command': command})
    assert hook_pipe(local, ev)['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert logs()


@pytest.mark.parametrize('command', [
    'xurl -X POST /2/users/1/likes -d \'{"tweet_id":"123"}\'',
    'xurl -X POST /2/users/1/following -d \'{"target_user_id":"123"}\'',
    'xurl -X POST /2/dm_conversations/with/1/messages -d \'{"text":"hi"}\'',
    'xurl -X GET /2/tweets/123',
    'echo \'xurl -X POST /2/tweets -d invalid\'',
    "cat <<'EOF'\nxurl -X POST /2/tweets -d invalid\nEOF\n",
])
def test_bash_nonposting_paths_unchanged(local, command):
    assert hook_pipe(local, dict(tool_name='Bash', tool_input={'command': command})) is None
    assert logs() == []


@pytest.mark.parametrize('summary', ['Like the post on X', 'Follow the author on X', 'Send a DM on X', 'Open the reply composer on X', 'Post the reply in Gmail'])
def test_browser_nonposting_paths_unchanged(local, summary):
    assert hook_pipe(local, event('browser', summary=summary)) is None
    assert logs() == []


@pytest.mark.parametrize('summary', ['Post a reply on Twitter', 'Click Reply to submit on x.com', 'Send the reply on X', 'Posting a reply on X'])
def test_browser_reply_wording(local, summary):
    assert hook_pipe(local, event('browser', summary=summary))['hookSpecificOutput']['permissionDecision'] == 'deny'


@pytest.mark.parametrize('words', [['-X', 'POST', '/2/users/1/likes'], ['-X', 'POST', '/2/users/1/following'], ['-X', 'POST', '/2/dm_conversations/with/1/messages']])
def test_xr_likes_follows_dms_not_in_gate(local, words):
    assert xr_pipe(local, {}, args=words).returncode == 0
    assert logs() == []


@pytest.mark.parametrize('words', [['-X', 'DELETE', '/2/tweets/123'], ['-X', 'POST', '/2/users/1/blocking'], ['-X', 'POST', '/2/users/1/bookmarks']])
def test_existing_xr_forbidden_operations_still_blocked(local, words):
    assert xr_pipe(local, {}, args=words).returncode == 2
    assert not Path(os.environ['XURL_TEST_RECORD']).exists()


def test_invalid_mode_enforces(local):
    assert xr_pipe(local, payload(), mode='typo').returncode == 2


def test_malformed_ledger_logged_and_blocked(local):
    (local / 'lanes/test/OUTREACH.jsonl').write_text('not json\n')
    assert hook_pipe(local, event('bash'))['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert logs()


def test_failed_transport_keeps_attempt_for_conservative_duplicate_protection(local, monkeypatch):
    row = approve(local)
    monkeypatch.setenv('XURL_TEST_EXIT', '7')
    assert xr_pipe(local, payload()).returncode == 7
    latest = outreach.current(local / 'lanes/test', rh)[row['id']]
    assert latest['status'] == 'approved' and latest['gate_attempt']
    assert xr_pipe(local, payload()).returncode == 2


@pytest.mark.parametrize('wrap', [
    lambda command: 'bash -c ' + shlex.quote(command),
    lambda command: '/bin/zsh -lc ' + shlex.quote(command),
    lambda command: '/usr/bin/env -i ' + command,
    lambda command: 'command ' + command,
    lambda command: 'sudo -u someone ' + command,
])
@pytest.mark.parametrize('mode', ['warn', 'enforce'])
def test_literal_shell_wrappers_cannot_bypass_hook(local, wrap, mode):
    ev = event('bash')
    ev['tool_input']['command'] = wrap(ev['tool_input']['command'])
    result = hook_pipe(local, ev, mode)
    if mode == 'warn':
        assert 'WARNING' in result['systemMessage']
    else:
        assert result['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert logs() and not Path(os.environ['XURL_TEST_RECORD']).exists()


def test_xr_forwards_the_checked_json_snapshot(local):
    approve(local)
    file = local / 'payload.json'
    file.write_text(json.dumps(payload()))
    assert xr_pipe(local, payload(), args=['-X', 'POST', '/2/tweets', '-d', '@' + str(file)]).returncode == 0
    words = json.loads(Path(os.environ['XURL_TEST_RECORD']).read_text())
    assert '@' + str(file) not in words
    assert json.loads(words[words.index('--data') + 1]) == payload()


def test_browser_receipt_can_be_recorded_after_registry_update(local):
    row = approve(local)
    assert hook_pipe(local, event('browser')) is None
    replied = Path(os.environ['RH_X_REPLIED'])
    replied.write_text('["123"]')
    before = replied.read_bytes()
    result = cli(local, 'sent', 'test', row['id'], '--message-id', '456', '--via', 'browser')
    assert result[0] == 0, result
    assert outreach.current(local / 'lanes/test', rh)[row['id']]['status'] == 'sent'
    assert replied.read_bytes() == before


def test_xr_refuses_to_post_without_a_configured_account(local, monkeypatch):
    approve(local)
    monkeypatch.delenv('RH_X_ACCOUNT')
    run = xr_pipe(local, payload())
    assert run.returncode == 2 and 'RH_X_ACCOUNT' in run.stderr
    assert not Path(os.environ['XURL_TEST_RECORD']).exists()


def x_log(rows):
    path = Path(os.environ['RH_X_REPLIED']).parent / 'log.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


NOW = dt.datetime.now(dt.timezone.utc).isoformat()
LIKE = dict(utc=NOW, action='like', target_url='https://x.com/i/status/123')
ANSWER = dict(utc=NOW, action='answer_recorded', target_url='https://x.com/i/status/123')


def lint_reply(root):
    draft = root / 'body.txt'
    draft.write_text(TEXT)
    result = cli(root, 'draft', 'test', '--to', '@anna', '--channel', 'x_reply', '--purpose', 'Thank them',
                 '--file', draft, '--in-reply-to', 'https://x.com/anna/status/123')
    assert result[0] == 0, result
    return cli(root, 'lint', 'test', result[1].strip())


def test_a_liked_answer_in_replied_json_does_not_block_the_thanks(local):
    """general, 11-09: the drafting round added a post to replied.json when it liked an answer, so the
    thanks it drafted under the same post was refused as already replied and could never post."""
    Path(os.environ['RH_X_REPLIED']).write_text('["123"]')
    x_log([LIKE, ANSWER, dict(utc=NOW, action='draft_reply', target_url='https://x.com/i/status/123')])
    assert outreach.only_liked('123')
    result = lint_reply(local)
    assert result[0] == 0, result
    assert 'shows only a like' in ''.join(map(str, result))


@pytest.mark.parametrize('rows', [
    [],                                                                       # no evidence: replied.json stands
    [LIKE, dict(action='reply', target_url='https://x.com/rpinho_sci/status/9', in_reply_to='https://x.com/a/status/123')],
    [LIKE, dict(action='reply_failed_403', target_url='https://x.com/a/status/123')],   # unknown: binding
    [dict(utc=NOW, action='conversation_read', target_url='https://x.com/i/status/123')],  # no like or answer
    # Before 11-07 a reply could be logged with only our URL, so an old like proves nothing.
    [dict(LIKE, utc='2026-10-22T13:56:25Z')],
    [dict(LIKE, utc='not a time')],
])
def test_replied_json_still_binds_without_proof_of_a_like_only(local, rows):
    Path(os.environ['RH_X_REPLIED']).write_text('["123"]')
    x_log(rows)
    assert not outreach.only_liked('123')
    result = lint_reply(local)
    assert result[0] != 0 and 'already replied to this post' in ''.join(map(str, result)), result
