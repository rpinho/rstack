"""general-inbox-relay: the conductor sees each unrelayed report once; nobody else sees anything (11-14)."""
import json

from rstack_hookcall import HOOKS, allowed, call

HOOK = HOOKS / 'general-inbox-relay.py'


def setup(tmp_path, rows):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    (inbox / 'inbox.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (inbox / 'relayed.cursor').write_text('0')
    conductor = tmp_path / 'wt' / 'general'
    conductor.mkdir(parents=True)
    env = {'RSTACK_CONDUCTOR_INBOX': str(inbox), 'CONDUCTOR_CWD_SUFFIX': '/wt/general', 'CONDUCTOR_TMUX': 'none'}
    return inbox, conductor, env


def test_the_conductor_gets_each_report_once_without_launcher_noise(tmp_path):
    inbox, conductor, env = setup(tmp_path, [
        dict(utc='2026-11-14T18:00:00Z', **{'from': 'math'}, text='C49 PR opened'),
        dict(utc='2026-11-14T18:01:00Z', **{'from': 'launch'}, text='job x ended without the hard-rule lines')])
    first = call(HOOK, {'cwd': str(conductor), 'prompt': 'hi'}, env=env)
    assert first['code'] == 0 and 'C49 PR opened' in first['stdout'] and 'hard-rule' not in first['stdout']
    second = call(HOOK, {'cwd': str(conductor), 'prompt': 'hi'}, env=env)
    assert second['stdout'] == ''                    # cursor advanced: nothing twice
    assert (inbox / 'relayed.cursor').read_text() == '2'


def test_a_lane_session_sees_nothing_and_moves_no_cursor(tmp_path):
    inbox, _, env = setup(tmp_path, [dict(utc='2026-11-14T18:00:00Z', text='report')])
    lane = tmp_path / 'wt' / 'math'
    lane.mkdir()
    r = allowed(HOOK, {'cwd': str(lane), 'prompt': 'hi'}, env=env)
    assert r['stdout'] == '' and (inbox / 'relayed.cursor').read_text() == '0'


def test_a_broken_inbox_never_blocks_the_prompt(tmp_path):
    inbox, conductor, env = setup(tmp_path, [])
    (inbox / 'inbox.jsonl').unlink()
    (inbox / 'inbox.jsonl').mkdir()                  # unreadable as a file
    r = call(HOOK, {'cwd': str(conductor), 'prompt': 'hi'}, env=env)
    assert not r['blocked']
