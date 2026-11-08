"""Reciprocate (11-08): a reply mirrors the message it answers. Synthetic pairs only; the real
pairs this was calibrated on stay private."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reciprocate
from test_bughunt import VARIED, cli, draft, lane, lint  # noqa: F401
from test_outreach import env  # noqa: F401

PERSON = {'name': 'Dana Example'}
THEIRS = """Hey Sam!

Good to hear from you! What are you up to these days? We finally moved the
group to the new building, so half my week is boxes.

I looked at the plotting script again and I think the old version is fine for
now, nobody else runs it.

Best,
Dana
"""
OURS = """Hey Dana,

Great to hear from you too. I'm mostly writing analysis code for an open
dataset, and lately I've been cleaning up old scripts nobody remembers.

Fair enough on the plotting script. If it ever breaks, send me the error and
I'll take a look.

How's the new lab?

Sam
"""
PT_IN = """Olá Sam,
Recebi os ficheiros ontem. Corri o script nos dados de março e os gráficos
batem certo com os nossos, só a última coluna sai com outra escala.
Na próxima semana vejo isso com calma :-)

Abraço,
Rui
"""
PT_OUT = """Olá Rui,

Obrigado por correres isso tão depressa. A escala da última coluna é minha,
mudei as unidades sem avisar. Mando a versão corrigida amanhã. :-)

Abraço,
Sam
"""


def codes(incoming, draft_text, person=PERSON):
    return [f.split(':')[0] for f in reciprocate.findings(incoming, draft_text, person)[0]]


def test_a_reply_that_mirrors_them_passes():
    assert codes(THEIRS, OURS) == []
    assert codes(PT_IN, PT_OUT, {'name': 'Rui Exemplo'}) == []


def test_quoted_text_is_not_counted():
    assert codes(THEIRS, OURS + '\nOn Sat, Dana wrote:\n> ' + 'old words ' * 200) == []


def test_a_long_reply_to_a_short_message_fails():
    long = OURS.replace('How\'s the new lab?', ' '.join(['More detail on the method.'] * 30) + ' How\'s the new lab?')
    assert 'RECIPROCATE_LENGTH' in codes(THEIRS, long)


@pytest.mark.parametrize('change, code', [
    (('Hey Dana,', 'Dear Dana,'), 'RECIPROCATE_GREETING'),           # register
    (('Hey Dana,', 'Hey there,'), 'RECIPROCATE_GREETING'),           # they used our name
    (('Hey Dana,\n', ''), 'RECIPROCATE_GREETING'),                   # no greeting
    (('\nSam\n', '\n'), 'RECIPROCATE_SIGNOFF'),
    (('Great to hear from you too. ', ''), 'RECIPROCATE_WARMTH'),
    (("I'm mostly writing analysis code for an open\ndataset, and lately I've been cleaning",
      'Analysis code for an open\ndataset, and lately cleaning'), 'RECIPROCATE_QUESTION'),  # say what we do
    (("How's the new lab?", 'Talk soon.'), 'RECIPROCATE_QUESTION'),   # ask about theirs
    (("I'll take a look.", "I'll take a look; my kids say hi."), 'RECIPROCATE_FAMILY'),
    (("I'll take a look.", "I'll take a look :-)"), 'RECIPROCATE_EMOTICON'),
])
def test_each_miss_is_named(change, code):
    assert code in codes(THEIRS, OURS.replace(*change))


def test_their_family_means_ours_goes_in():
    theirs = THEIRS.replace('Good to hear from you!', 'Good to hear from you! The kids are growing fast.')
    assert 'RECIPROCATE_FAMILY' in codes(theirs, OURS)
    assert 'RECIPROCATE_FAMILY' not in codes(theirs, OURS.replace('Fair enough', 'Our kids too. Fair enough'))


def test_a_direct_question_must_be_answered():
    theirs = THEIRS.replace('What are you up to these days?', 'Which compiler flags did the fix need?')
    assert 'RECIPROCATE_QUESTION' in codes(theirs, OURS)
    assert 'RECIPROCATE_QUESTION' not in codes(theirs, OURS.replace('Fair enough', 'The compiler flags were the default ones. Fair enough'))


def test_answering_in_another_language_fails():
    assert 'RECIPROCATE_LANGUAGE' in codes(PT_IN, OURS.replace('Hey Dana', 'Olá Rui').replace('Sam\n', 'Abraço,\nSam\n'), {'name': 'Rui Exemplo'})


def test_a_reply_owed_must_name_their_message(lane):
    root = lane[0]
    assert cli(root, 'contact', 'engagement', 'Contact Alpha', 'Prefers short notes', '--source', 's')[0] == 0
    # The ball is with us once they replied; a draft that ignores their message is refused.
    sent, _ = draft(lane, text=VARIED[0])
    assert cli(root, 'lint', 'test', sent)[0] == 0
    assert cli(root, 'approve', 'test', sent, '--quote', 'Send it')[0] == 0
    assert cli(root, 'sent', 'test', sent, '--message-id', 'm', '--via', 'api')[0] == 0
    assert cli(root, 'reply', 'test', sent, '--summary', 'they wrote back')[0] == 0
    ident, _ = draft(lane, text=VARIED[1])
    assert 'RECIPROCATE_INCOMING_MISSING' in lint(lane, ident)[1]
    incoming = root / 'their-message.txt'
    incoming.write_text(VARIED[1])
    ident, _ = draft(lane, text=VARIED[1], incoming=incoming)
    rc, out = lint(lane, ident)
    assert 'RECIPROCATE_INCOMING_MISSING' not in out and 'reciprocate:' in out
