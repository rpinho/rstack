"""An email to a close friend (a friend's call, 11-09): short, plain, and the owner's own once they noticed.
Synthetic text only."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import friend_email
import reciprocate
import science_email
from test_bughunt import config, draft, lane, lint  # noqa: F401
from test_outreach import env  # noqa: F401

FRIEND = {'name': 'Dana Example', 'group': 'friend'}
SHORT = 'Hi Dana,\n\nDid the second estimator ever work on the 2019 data? I got it running here.\n\nAbraço,\nSam\n'
# Every sentence could be the owner's; the shape is what a friend read as AI.
LONG = """Hi Dana,

Did the second estimator ever work on the 2019 data? I got it running here last week and the numbers held.

I'm now working on open problems with agents, mostly in the evenings. It has been a good way to read papers again.

The bound moved from 0.31 to 0.29, which means the gap you left open is smaller than the conjecture needs.

Happy to have a call if it helps.

Best,
Sam
"""


def codes(contact, text, **kw):
    return [f.split(':')[0] for f in friend_email.findings(contact, text, **kw)]


def test_a_short_plain_note_to_a_friend_passes():
    assert codes(FRIEND, SHORT) == []


def test_paragraphs_of_well_formed_prose_fail_for_a_friend_only():
    assert set(codes(FRIEND, LONG)) == {'FRIEND_LENGTH', 'FRIEND_PARAGRAPHS'}
    assert codes({'name': 'Dana Example', 'group': 'cold'}, LONG) == []
    assert codes({'name': 'Dana Example'}, LONG) == []


def test_the_greeting_signoff_and_quoted_history_are_not_counted():
    quoted = SHORT + '\nOn Mon, Dana wrote:\n> ' + 'a long earlier message ' * 40 + '\n'
    assert codes(FRIEND, quoted) == []
    words = ' '.join(['word'] * 60)
    assert codes(FRIEND, 'Hi Dana,\n\n{}\n\nBest,\nSam\n'.format(words)) == []
    assert codes(FRIEND, 'Hi Dana,\n\n{} more\n\nBest,\nSam\n'.format(words)) == ['FRIEND_LENGTH']


def test_no_lists_to_a_friend():
    for bullet in ('- the estimator', '* the estimator', '1. the estimator', '2) the estimator'):
        text = 'Hi Dana,\n\nTwo things:\n{}\nand the data.\n\nSam\n'.format(bullet)
        assert codes(FRIEND, text) == ['FRIEND_BULLETS'], bullet


@pytest.mark.parametrize('pref', ['Noticed AI in our emails, 11-09', 'Expects one sentence, go.'])
def test_a_friend_who_noticed_gets_only_the_owners_own_text(pref):
    noticed = dict(FRIEND, engagement=pref)
    assert codes(noticed, SHORT) == ['AGENT_NOTICED']
    assert codes(noticed, LONG, owner_wrote='"I wrote this one myself" (owner, chat)') == []
    assert codes(dict(FRIEND, engagement='Prefers a call to more result emails'), SHORT) == []


def test_the_caps_are_lane_settings_and_bad_ones_refuse():
    assert codes(FRIEND, LONG, cfg=dict(friend_max_words=200, friend_max_paragraphs=6)) == []
    assert codes({'name': 'X', 'group': 'family'}, LONG, cfg=dict(friend_groups=['friend', 'family'])) != []
    for bad in (dict(friend_groups='friend'), dict(friend_max_words=0), dict(friend_max_paragraphs='2')):
        with pytest.raises(ValueError):
            friend_email.check_settings(bad)


def test_the_science_elements_that_add_length_are_optional_for_a_friend():
    bare = 'Hi Dana,\n\nDid you see this? I tightened your bound from 3 to 4.\n\nSam\n'
    cfg = dict(science_email_rules=True)
    person = dict(FRIEND, last_in='2026-11-01 reply')
    other = [f.split(':')[0] for f in science_email.findings(dict(person, group='cold'), '', bare, kinds=['paper'], cfg=cfg)]
    assert {'LIFE_LINE_MISSING', 'MEANING_MISSING', 'CALL_MISSING'} <= set(other)
    mine = [f.split(':')[0] for f in science_email.findings(person, '', bare, kinds=['paper'], cfg=cfg, friend=True)]
    assert mine == []
    late = bare.replace('Did you see this? I', 'I')
    assert science_email.findings(person, '', late, kinds=['paper'], cfg=cfg, friend=True)[0].startswith('SCIENCE_OPENER')


def test_there_is_no_reply_floor_to_a_friend():
    theirs = 'Hi Sam,\n\n' + ' '.join(['We moved the simulation code to the new version.'] * 15) + '\n\nBest,\nDana\n'
    ours = 'Hi Dana,\n\nGood to hear from you. ' + ' '.join(['word'] * 30) + '\n\nBest,\nSam\n'
    length = lambda contact: [f for f in reciprocate.findings(theirs, ours, contact)[0] if 'LENGTH' in f]
    assert length({'name': 'Dana Example', 'group': 'cold'})
    assert length(FRIEND) == []


def test_lint_applies_it_and_owner_wrote_lets_their_own_text_through(lane):
    root, _, contacts = lane
    rows = json.loads(contacts.read_text())
    rows[0].update(group='friend', engagement='Noticed AI in our emails; one sentence, go.')
    contacts.write_text(json.dumps(rows))
    ident, _ = draft(lane, kind='other', text=LONG.replace('Dana', 'Contact'))
    out = lint(lane, ident)[1]
    assert 'AGENT_NOTICED' in out and 'FRIEND_LENGTH' in out and 'FRIEND_PARAGRAPHS' in out
    ident, _ = draft(lane, kind='other', text=LONG.replace('Dana', 'Contact'),
                     owner_wrote='"I wrote this one myself" (owner, chat)')
    out = lint(lane, ident)[1]
    assert 'AGENT_NOTICED' not in out and 'FRIEND_' not in out
