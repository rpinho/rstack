"""x-submit-gate and x-route: Grok, then the API, then the browser, and every attempt logged."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
GATE, ROUTE = TOOLS / 'x-submit-gate', TOOLS / 'x-route'
C = 'mcp__claude-in-chrome__'
GOOD_DEVICE, PRIVATE_DEVICE = 'device-project', 'device-private'


@pytest.fixture
def env(tmp_path):
    state = tmp_path / 'state'
    cfg = tmp_path / 'gate.json'
    cfg.write_text(json.dumps(dict(deny_devices=[PRIVATE_DEVICE], handle='example_sci')))
    return dict(RSTACK_STATE_DIR=str(state), X_SUBMIT_GATE_CONFIG=str(cfg), PATH='/usr/bin:/bin',
                X_ROUTE_CONFIG=str(tmp_path / 'route.json'))


def probe(env, session='s1', tab=7, device=GOOD_DEVICE, handle='example_sci', age=0):
    path = Path(env['RSTACK_STATE_DIR']) / 'x-handle-guard' / (session + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(device=device, tabs={str(tab): dict(handle=handle, device=device,
                                                                      utc=time.time() - age)})))


def ledger(env, *rows):
    path = Path(env['RSTACK_STATE_DIR']) / 'x-route.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')


def ago(minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).isoformat(timespec='seconds')


def gate(env, summary, action='left_click', tool='computer', session='s1', tab=7):
    event = dict(hook_event_name='PreToolUse', session_id=session, tool_name=C + tool,
                 tool_input=dict(action=action, tabId=tab, coordinate=[1, 2], action_summary=summary))
    out = subprocess.run([sys.executable, str(GATE)], input=json.dumps(event), capture_output=True,
                         text=True, env=env, timeout=10)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)['hookSpecificOutput']['permissionDecisionReason'] if out.stdout.strip() else None


REPLY = 'Posts the reply on X to @someone (https://x.com/someone/status/1234567)'


def test_browser_reply_is_denied_while_the_grok_route_works(env):
    probe(env)
    ledger(env, dict(utc=ago(2), kind='reply', target='7654321', route='grok', ok=True))
    reason = gate(env, REPLY)
    assert reason and 'run x-route reply first' in reason


def test_browser_reply_allowed_after_a_logged_grok_failure_for_that_post(env):
    probe(env)
    ledger(env, dict(utc=ago(3), kind='reply', target='1234567', route='grok', ok=False, detail='exit 3'))
    assert gate(env, REPLY) is None


def test_failure_older_than_fifteen_minutes_or_uncertain_or_done_refuses(env):
    probe(env)
    ledger(env, dict(utc=ago(20), kind='reply', target='1234567', route='grok', ok=False))
    assert 'run x-route reply first' in gate(env, REPLY)
    ledger(env, dict(utc=ago(1), kind='reply', target='1234567', route='grok', ok=False, uncertain=True))
    assert 'never retry' in gate(env, REPLY)
    ledger(env, dict(utc=ago(0), kind='reply', target='1234567', route='grok', ok=True))
    assert 'already done' in gate(env, REPLY)


def test_like_and_follow_need_a_failed_api_attempt(env):
    probe(env)
    like = "Likes @someone's post 1234567 on X"
    follow = 'Follows @someone on X'
    assert 'like has a api route' in gate(env, like)
    assert 'follow has a api route' in gate(env, follow)
    ledger(env, dict(utc=ago(1), kind='like', target='1234567', route='api', ok=False, detail='403'),
           dict(utc=ago(1), kind='follow', target='someone', route='api', ok=False, detail='403'))
    assert gate(env, like) is None and gate(env, follow) is None


def test_private_browser_is_always_denied(env):
    probe(env, device=PRIVATE_DEVICE)
    ledger(env, dict(utc=ago(1), kind='reply', target='1234567', route='grok', ok=False))
    assert 'denied device' in gate(env, REPLY)


def test_handle_probe_must_pass_in_that_tab(env):
    ledger(env, dict(utc=ago(1), kind='reply', target='1234567', route='grok', ok=False))
    assert 'no passing x-handle-guard probe' in gate(env, REPLY)
    probe(env, handle='someone_else')
    assert 'no passing x-handle-guard probe' in gate(env, REPLY)
    probe(env, tab=8)
    assert 'no passing x-handle-guard probe' in gate(env, REPLY)


def test_a_submit_must_name_its_target(env):
    probe(env)
    assert 'name the target' in gate(env, 'Posts the reply on X to @someone')


def test_reads_and_non_x_clicks_pass(env):
    for summary in ('Opens the thread by @someone', 'Scrolls the replies on X', 'Clicks the Save button',
                    ''):
        assert gate(env, summary) is None
    assert gate(env, REPLY, action='screenshot') is None


def test_repost_has_no_route_but_still_needs_the_checks(env):
    assert 'probe' in gate(env, 'Reposts @someone on X 1234567')
    probe(env)
    assert gate(env, 'Reposts @someone on X 1234567') is None


def test_no_config_refuses_every_x_submit(env, tmp_path):
    probe(env)
    env = dict(env, X_SUBMIT_GATE_CONFIG=str(tmp_path / 'missing.json'))
    assert 'refusing every X submit' in gate(env, REPLY)
    assert gate(env, 'Opens the thread by @someone') is None


def test_batch_submit_is_seen(env):
    probe(env)
    event = dict(hook_event_name='PreToolUse', session_id='s1', tool_name=C + 'browser_batch',
                 tool_input=dict(actions=[dict(name='navigate', input=dict(tabId=7, url='https://x.com')),
                                          dict(name='computer', input=dict(action='left_click', tabId=7,
                                                                           action_summary=REPLY))]))
    out = subprocess.run([sys.executable, str(GATE)], input=json.dumps(event), capture_output=True,
                         text=True, env=env, timeout=10)
    assert 'run x-route reply first' in json.loads(out.stdout)['hookSpecificOutput']['permissionDecisionReason']


# x-route: the route order and its ledger, with fake grok-post, grok-ask and xr.

def fake(tmp_path, name, body):
    path = tmp_path / name
    path.write_text('#!{}\nimport sys, json\n{}\n'.format(sys.executable, body))
    path.chmod(0o755)
    return str(path)


def route(env, tmp_path, *args, grok='print("Verified: https://x.com/example_sci/status/99")',
          xr='print(json.dumps({"data": {"liked": True}}))', ask='print(json.dumps([{"id": "42", "username": "someone"}]))'):
    (tmp_path / 'route.json').write_text(json.dumps(dict(
        account_id='1001', grok_post=fake(tmp_path, 'grok-post', grok), xr=fake(tmp_path, 'xr', xr),
        grok_ask=fake(tmp_path, 'grok-ask', ask))))
    out = subprocess.run([sys.executable, str(ROUTE), *args], capture_output=True, text=True, env=env, timeout=20)
    rows = [json.loads(l) for l in (Path(env['RSTACK_STATE_DIR']) / 'x-route.jsonl').read_text().splitlines()] \
        if (Path(env['RSTACK_STATE_DIR']) / 'x-route.jsonl').exists() else []
    return out, rows


def test_reply_goes_through_grok_and_is_logged(env, tmp_path):
    draft = tmp_path / 'd.txt'
    draft.write_text('x')
    out, rows = route(env, tmp_path, 'reply', '--rh', 'l/1', '--reply-to', 'https://x.com/a/status/1234567',
                      '--text-file', str(draft))
    assert out.returncode == 0 and 'status/99' in out.stdout
    assert rows[-1] == dict(rows[-1], kind='reply', target='1234567', route='grok', ok=True)


@pytest.mark.parametrize('rc,expect', [(3, 10), (4, 10), (2, 10), (5, 5)])
def test_grok_failure_opens_the_browser_only_when_nothing_was_sent(env, tmp_path, rc, expect):
    draft = tmp_path / 'd.txt'
    draft.write_text('x')
    out, rows = route(env, tmp_path, 'reply', '--rh', 'l/1', '--reply-to', 'https://x.com/a/status/1234567',
                      '--text-file', str(draft), grok='print("grok-post: no"); sys.exit({})'.format(rc))
    assert out.returncode == expect
    assert rows[-1]['ok'] is False and bool(rows[-1].get('uncertain')) == (expect == 5)
    probe(env)
    allowed = gate(env, REPLY) is None
    assert allowed == (expect == 10)


def test_reply_spacing_waits_instead_of_using_the_browser(env, tmp_path):
    draft = tmp_path / 'd.txt'
    draft.write_text('x')
    out, rows = route(env, tmp_path, 'reply', '--rh', 'l/1', '--reply-to', 'https://x.com/a/status/1234567',
                      '--text-file', str(draft),
                      grok='print("grok-post: rh X reach checks: x_reply within 4 min of another reply"); sys.exit(2)')
    assert out.returncode == 11


def test_like_goes_through_the_api_as_the_posting_account(env, tmp_path):
    out, rows = route(env, tmp_path, 'like', 'https://x.com/a/status/1234567',
                      xr='print(json.dumps({"data": {"liked": True}, "argv": sys.argv[1:]}))')
    assert out.returncode == 0 and rows[-1]['route'] == 'api' and rows[-1]['ok']
    again, _ = route(env, tmp_path, 'like', '1234567', xr='sys.exit(9)')
    assert again.returncode == 0 and 'already done' in again.stdout


def test_api_refusal_opens_the_browser(env, tmp_path):
    out, rows = route(env, tmp_path, 'like', '1234567', xr='print("403 spend-cap-reached"); sys.exit(1)')
    assert out.returncode == 10 and 'BROWSER ALLOWED' in out.stdout
    probe(env)
    assert gate(env, "Likes @a's post 1234567 on X") is None


def test_follow_looks_up_the_id_through_grok_then_follows(env, tmp_path):
    out, rows = route(env, tmp_path, 'follow', '@someone', xr='print(json.dumps({"data": {"following": True}}))',
                      ask='assert json.load(open(sys.argv[sys.argv.index("--schema") + 1])) == ["id", "username"]\n'
                          'print(json.dumps([{"id": "42", "username": "someone"}]))')
    assert out.returncode == 0 and rows[-1] == dict(rows[-1], kind='follow', target='someone', ok=True)
    out, rows = route(env, tmp_path, 'follow', '@other', ask='print("[]")')
    assert out.returncode == 10 and 'lookup failed' in rows[-1]['detail']
