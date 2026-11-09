"""A science email to a person (11-08 outreach postmortem). Synthetic text only."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import science_email
from test_bughunt import config, draft, lane, lint  # noqa: F401
from test_outreach import env  # noqa: F401

CFG = dict(science_email_rules=True, life_words=['Lisbon'], call_link='https://example.org/book')
GOOD = """Hi Dana,

Did you ever try the second estimator on the 2019 data?

I'm now working on open problems with agents. I tightened your bound from 0.31 to 0.29, which means the gap you left open is smaller than the conjecture needs.

Happy to have a call if it helps: https://example.org/book

Best,
Sam
"""


def codes(*args, **kw):
    return [f.split(':')[0] for f in science_email.findings(*args, cfg=CFG, **kw)]


def test_a_good_science_email_passes():
    assert codes({'name': 'Dana', 'last_in': '2026-10-01'}, '', GOOD) == []


def test_a_plain_message_is_not_a_science_email():
    assert codes({'last_in': 'x'}, '', 'Hi Dana,\n\nHow was the trip?\n\nSam') == []


@pytest.mark.parametrize('change, code', [
    (('Did you ever try the second estimator on the 2019 data?', 'I tightened it.'), 'SCIENCE_OPENER'),
    (("I'm now working on open problems with agents. ", ''), 'LIFE_LINE_MISSING'),
    ((', which means the gap you left open is smaller than the conjecture needs', ''), 'MEANING_MISSING'),
    (('Happy to have a call if it helps: https://example.org/book', ''), 'CALL_MISSING'),
    (('I tightened your bound', 'I found a bug in your bound code and tightened your bound'), 'USERS_MISSING'),
])
def test_each_miss_is_named(change, code):
    assert code in codes({'name': 'Dana', 'last_in': '2026-10-01'}, '', GOOD.replace(*change))


def test_overrides_and_evidence():
    person = {'name': 'Dana', 'last_in': 'x'}
    bare = 'Hi Dana,\n\nI found a bug in your code from 3 to 4.\n\nSam'
    assert len(codes(person, '', bare)) == 5
    words = dict(opener='he asked for the result first', life='close friend, writes weekly',
                 meaning='he knows what it means', nocall='he never takes calls', users='"it runs nightly"')
    assert codes(person, '', bare, overrides=words) == []
    assert 'USERS_MISSING' not in codes(dict(person, users='used by two labs'), '', bare)
    assert 'USERS_MISSING' not in codes(person, '', bare, users_ok=True)
    assert 'SCIENCE_OPENER' not in codes(person, 'Did it work?', bare), 'they asked: answer first'
    assert 'LIFE_LINE_MISSING' not in codes(person, '', bare.replace('Hi Dana,\n\n', 'Hi Dana,\n\nBack in Lisbon. '))


def test_bad_settings_refuse():
    for bad in (dict(science_email_rules='yes'), dict(life_words='Lisbon'), dict(call_link=3)):
        with pytest.raises(ValueError):
            science_email.check_settings(bad)


def test_lint_applies_them_when_the_lane_turns_them_on(lane):
    ident, _ = draft(lane, kind='paper', text='Hi Contact,\n\nI tightened your bound from 3 to 4.\n\nSam\n')
    assert 'SCIENCE_OPENER' not in lint(lane, ident)[1]
    config(lane, 'science_email_rules = true\n')
    out = lint(lane, ident)[1]
    assert 'SCIENCE_OPENER' in out and 'LIFE_LINE_MISSING' in out and 'MEANING_MISSING' in out


def test_no_second_science_email_until_they_answer(lane):
    """friends postmortem (a): one science email until they answer, follow-ups included."""
    from test_bughunt import cli, send
    first, _ = draft(lane, kind='paper', text='Hi Contact,\n\nI read your paper on growth rates.\n\nSam\n')
    send(lane, first)
    config(lane, 'science_email_rules = true\nlife_words = ["growth"]\n')
    nxt, _ = draft(lane, kind='paper', text='Hi Contact,\n\nDid you see the arxiv note? I read your growth paper.\n\nSam\n')
    assert 'AWAITING_REPLY' in lint(lane, nxt)[1]
    asked, _ = draft(lane, kind='paper', requested='"send me the note" (their email)',
                     text='Hi Contact,\n\nDid you see the arxiv note? I read your growth paper.\n\nSam\n')
    assert 'AWAITING_REPLY' not in lint(lane, asked)[1], 'a send they asked for is a reply'
    other, _ = draft(lane, kind='other', text='Hi Contact,\n\nHow was the trip?\n\nSam\n')
    assert 'AWAITING_REPLY' not in lint(lane, other)[1], 'a plain message is not a science email'
    assert cli(lane[0], 'reply', 'test', first, '--summary', 'Thanks')[0] == 0
    assert 'AWAITING_REPLY' not in lint(lane, nxt)[1]


@pytest.mark.parametrize('line', ['Agora sou analista numa empresa pequena.', 'Eu vim para o Porto e fiquei por cá.',
                                  'Mudamo-nos para o sul há dois anos.', 'Trabalho numa empresa de dados.'])
def test_a_portuguese_life_line_counts(line):
    """friends, 11-09: "mudamo-nos para ..." and "Agora sou ..." were not seen as a life line."""
    text = 'Olá Rui,\n\nPosso perguntar uma coisa sobre o código?\n\n{}\n\nEncontrei um bug no fit.\n\nAbraço'.format(line)
    out = science_email.findings({'name': 'Rui', 'users': 'they run it'}, '', text, kinds=['code-bug'],
                                 cfg={'science_email_rules': True})
    assert not [f for f in out if f.startswith('LIFE_LINE_MISSING')], out
