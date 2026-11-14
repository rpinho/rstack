"""general-relay-check: the conductor cannot end a turn that skipped an injected report (11-14)."""
import json

from rstack_hookcall import HOOKS, call as _call


def call(hook, event, env):
    """A Stop hook blocks with {"decision": "block"} on stdout, which the shared helper does not read."""
    r = _call(hook, event, env=env)
    r['blocked'] = any(line.strip().startswith('{') and json.loads(line).get('decision') == 'block'
                       for line in r['stdout'].splitlines())
    return r

HOOK = HOOKS / 'general-relay-check.py'


def setup(tmp_path, rows, reply, aliases=None):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    (inbox / 'inbox.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (inbox / 'relayed.cursor').write_text(str(len(rows)))      # all of them were injected
    (inbox / 'relay-check.cursor').write_text('0')
    if aliases:
        (inbox / 'aliases.json').write_text(json.dumps(aliases))
    transcript = tmp_path / 't.jsonl'
    transcript.write_text('\n'.join(json.dumps(r) for r in [
        {'type': 'user', 'message': {'content': 'what happened?'}},
        {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': reply}]}}]) + '\n')
    conductor = tmp_path / 'wt' / 'general'
    conductor.mkdir(parents=True)
    env = {'RSTACK_CONDUCTOR_INBOX': str(inbox), 'CONDUCTOR_CWD_SUFFIX': '/wt/general', 'CONDUCTOR_TMUX': 'none'}
    event = {'cwd': str(conductor), 'transcript_path': str(transcript), 'stop_hook_active': False}
    return inbox, event, env


ROWS = [dict(utc='2026-11-14T18:00:00Z', **{'from': 'friends'}, text='Vieira holds'),
        dict(utc='2026-11-14T18:01:00Z', **{'from': 'ai-research-tools'}, text='gate shipped'),
        dict(utc='2026-11-14T18:02:00Z', **{'from': 'launch'}, text='job ended without the hard-rule lines')]


def test_a_reply_missing_a_session_is_blocked_and_the_cursor_holds(tmp_path):
    inbox, event, env = setup(tmp_path, ROWS, 'Harness shipped the gate.', {'ai-research-tools': ['harness']})
    r = call(HOOK, event, env=env)
    assert r['blocked'] and 'friends' in r['stdout'] and 'launch' not in r['stdout']
    assert (inbox / 'relay-check.cursor').read_text() == '0'


def test_a_reply_naming_every_session_or_alias_passes_and_advances(tmp_path):
    inbox, event, env = setup(tmp_path, ROWS, 'friends: Vieira holds. Harness: gate shipped.',
                              {'ai-research-tools': ['harness']})
    r = call(HOOK, event, env=env)
    assert not r['blocked'] and (inbox / 'relay-check.cursor').read_text() == '3'


def test_the_second_stop_and_other_sessions_always_pass(tmp_path):
    inbox, event, env = setup(tmp_path, ROWS, 'nothing')
    assert not call(HOOK, dict(event, stop_hook_active=True), env=env)['blocked']
    lane = tmp_path / 'wt' / 'math'
    lane.mkdir()
    assert not call(HOOK, dict(event, cwd=str(lane)), env=env)['blocked']


def test_a_broken_transcript_allows_the_stop(tmp_path):
    inbox, event, env = setup(tmp_path, ROWS, 'nothing')
    r = call(HOOK, dict(event, transcript_path=str(tmp_path / 'missing.jsonl')), env=env)
    assert not r['blocked']
