"""Growing a small account on X (docs/outreach.md): the parts the ledger can check.

11-08: the owner asked for Nikita Bier's advice to be part of the outreach rules. Originals and
replies are spaced, never sent as a burst; a greeting with nothing in it is not posted; and a
person approves replies, because X removed 42,000 accounts that replied through chatbots with no
human in the loop. These run against isolated ledgers and the real posting gate; no network.
"""
import datetime as dt
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import outreach
import rh
import x_gate
from test_outreach import cli
from test_x_reach import CLOCK, draft, history, lint, state  # noqa: F401  (state is a fixture)

REPLY_TO = 'https://x.com/scientist/status/555'


def toml(state, text, lane='a'):
    (state[0] / 'lanes' / lane / 'OUTREACH.toml').write_text(text)


@pytest.mark.parametrize('text', ['gm', 'GM everyone!', 'Good morning, X', 'happy friday',
                                  'Hello world'])
def test_a_greeting_with_nothing_in_it_is_not_posted(state, text):
    ident, _ = draft(state, text=text)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'filler post' in out


def test_a_greeting_with_something_real_is_fine(state):
    ident, _ = draft(state, text='Good morning. The C44 bound is now checked in Lean.')
    rc, out, _ = lint(state, ident)
    assert rc == 0, out


def test_a_standing_approval_does_not_send_replies_by_default(state):
    ident, _ = draft(state, channel='x_reply', in_reply_to=REPLY_TO, text='Which split did you use?')
    assert lint(state, ident)[0] == 0
    rc, _, err = cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)
    assert rc != 0 and 'needs a person to approve this round' in err
    assert outreach.current(state[0] / 'lanes/a', rh)[ident]['status'] == 'linted'


def test_a_person_approving_the_round_sends_it(state):
    ident, _ = draft(state, channel='x_reply', in_reply_to=REPLY_TO, text='Which split did you use?')
    assert lint(state, ident)[0] == 0
    assert cli(state[0], 'approve', 'a', ident, '--quote', 'yes, post these three')[0] == 0


def test_an_owner_who_decided_otherwise_says_so_in_the_lane(state):
    toml(state, 'x_reply_human_approval = false\n')
    ident, _ = draft(state, channel='x_reply', in_reply_to=REPLY_TO, text='Which split did you use?')
    assert lint(state, ident)[0] == 0
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 0


def test_originals_standing_approval_is_unchanged(state):
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 0
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 0


@pytest.mark.parametrize('minutes_ago, ok', [(100, True), (80, False)])
def test_the_original_gap_is_a_lane_setting(state, minutes_ago, ok):
    toml(state, 'x_original_gap_minutes = 90\n')
    history(state, age=minutes_ago / 60)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert (rc == 0) is ok, out
    assert ok or 'within 90 min of another original' in out


def test_the_original_gap_defaults_to_two_hours(state):
    history(state, age=1.5)
    ident, _ = draft(state)
    assert 'within 120 min of another original' in lint(state, ident)[1]


@pytest.mark.parametrize('line', ['x_reply_gap_minutes = -1', 'x_reply_gap_minutes = "3"',
                                  'x_reply_human_approval = "no"', 'x_original_gap_minutes = 1.5'])
def test_a_typo_in_a_setting_refuses_rather_than_switching_the_check_off(state, line):
    toml(state, line + '\n')
    ident, _ = draft(state)
    rc, _, err = lint(state, ident)
    assert rc != 0 and ('OUTREACH x_' in err or 'unsupported' in err), err


def reply(other_minutes_ago, gap=3, kind='sent', channel='x_reply'):
    other = dict(id='earlier', lane='b', channel=channel, status='sent', to_name='@b', to_key='@b',
                 purpose='p', text='An earlier, unrelated answer about seeds.',
                 in_reply_to='https://x.com/b/status/9')
    other[kind] = dict(utc=(CLOCK - dt.timedelta(minutes=other_minutes_ago)).isoformat())
    row = dict(id='now', lane='a', channel='x_reply', in_reply_to=REPLY_TO, to_name='@scientist',
               to_key='@scientist', purpose='p', text='A real answer.')
    return outreach.x_checks(row, 'A real answer.', [other], CLOCK,
                             cfg=dict(x_reply_gap_minutes=gap), posting=True)[0]


def test_a_reply_right_after_another_is_held_at_the_posting_gate(state):
    failures = [f for f in reply(1) if 'x_reply within' in f]
    assert failures and 'next one from 19:02Z' in failures[0]


def test_a_posting_attempt_counts_as_much_as_a_receipt(state):
    assert any('x_reply within' in f for f in reply(1, kind='gate_attempt'))


@pytest.mark.parametrize('minutes, gap, channel', [(4, 3, 'x_reply'), (1, 0, 'x_reply'),
                                                   (1, 3, 'x_post')])
def test_spaced_replies_and_other_posts_go_through(state, minutes, gap, channel):
    assert not any('x_reply within' in f for f in reply(minutes, gap, channel=channel))


def test_lint_and_approval_do_not_space_replies(state):
    """A round's replies are reviewed and approved together; only their sending is spaced."""
    toml(state, 'x_reply_human_approval = false\n')
    ids = []
    texts = ['Which split did you use for the held-out set?', 'The second figure is lovely.',
             'Did the prior change much between seasons?']
    for n, text in enumerate(texts):
        ident, _ = draft(state, channel='x_reply', in_reply_to=REPLY_TO.replace('555', str(600 + n)),
                         text=text, batch='round')
        ids.append(ident)
    result = cli(state[0], 'lint', 'a', '--batch', 'round')
    assert result[0] == 0, result
    result = cli(state[0], 'approve', 'a', '--batch', 'round', '--quote', outreach.STANDING_APPROVAL)
    assert result[0] == 0, result


def test_the_gate_refusal_says_when_the_next_reply_may_go(tmp_path, monkeypatch):
    """End to end through x_gate: the second reply of a round, a minute after the first."""
    root = tmp_path / 'harness'
    lane = root / 'lanes/test'
    lane.mkdir(parents=True)
    (lane / 'OUTREACH.toml').write_text('x_reply_human_approval = false\n')
    replied = tmp_path / 'replied.json'
    replied.write_text('[]')
    monkeypatch.setattr(outreach, 'REPLIED', replied)
    monkeypatch.setenv('RH_X_GATE_LOG', str(tmp_path / 'gate.jsonl'))
    now = dt.datetime.now(outreach.UTC)
    rh.append(lane / 'OUTREACH.jsonl', dict(
        id='first', lane='test', channel='x_reply', status='sent', to_name='@a', to_key='@a',
        purpose='p', in_reply_to='https://x.com/a/status/1', text='An earlier answer about seeds.',
        sent=dict(utc=(now - dt.timedelta(minutes=1)).isoformat(), message_id='1', via='browser')))
    body = tmp_path / 'second.txt'
    body.write_text('A second, different answer.')
    result = cli(root, 'draft', 'test', '--to', '@b', '--channel', 'x_reply', '--purpose', 'p',
                 '--file', body, '--in-reply-to', 'https://x.com/b/status/2')
    assert result[0] == 0, result
    ident = result[1].strip()
    result = cli(root, 'lint', 'test', ident)
    assert result[0] == 0, result
    result = cli(root, 'approve', 'test', ident, '--quote', outreach.STANDING_APPROVAL)
    assert result[0] == 0, result
    row, reason = x_gate.check(root, 'browser', browser=True)
    assert row is None and 'x_reply within 3 min of another reply' in reason
    assert 'next one from' in reason
