"""An email to a close friend is short and plain, and never agent-written once they have noticed.

A friend, on a call (11-09), about emails whose every line had been cut from the sender's own
messages: he thought they were written by an AI and was slightly offended. The sender's emails to
him are usually one sentence; these were well-formulated paragraphs. The wording passed every check.
The length and the structure gave it away. So an email to a contact whose `group` is in
friend_groups (default: friend) fails lint when:

  FRIEND_LENGTH      its body, greeting and sign-off left out, is over friend_max_words (60)
  FRIEND_PARAGRAPHS  it has more than friend_max_paragraphs (2) paragraphs
  FRIEND_BULLETS     it has a bulleted or numbered list
  AGENT_NOTICED      the contact's `engagement` field says they noticed AI or want one sentence,
                     and the owner did not write the text (`--owner-wrote` in the owner's words)

For these contacts the science-email elements that add length (a life line, what a number means,
a call offer) are optional and there is no reciprocate length floor. A text the
owner wrote is theirs: none of these apply to it and it is not held to the paper-cut check.
"""
import re

import reciprocate

NOTICED = re.compile(r'(?i)\bnoticed\b.{0,20}\bAI\b|\bone sentence\b')
BULLET = re.compile(r'^\s*([-*•–]|\d{1,2}[.)])\s+\S')


def defaults():
    return dict(friend_groups=['friend'], friend_max_words=60, friend_max_paragraphs=2)


def check_settings(cfg):
    for key, default in defaults().items():
        cfg.setdefault(key, default)
    groups = cfg['friend_groups']
    if type(groups) is not list or any(type(g) is not str or not g.strip() for g in groups):
        raise ValueError('OUTREACH friend_groups must be a list of contact groups')
    for key in ('friend_max_words', 'friend_max_paragraphs'):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError('OUTREACH ' + key + ' must be a positive integer')
    return cfg


def is_friend(contact, cfg=None):
    groups = (cfg or {}).get('friend_groups', defaults()['friend_groups'])
    return str((contact or {}).get('group') or '').strip().casefold() in {g.strip().casefold() for g in groups}


def paragraphs(text):
    """The body's paragraphs: no quoted history, greeting or sign-off."""
    greeting, body, signoff = reciprocate.parts(text)
    lines = []
    for line in text.replace('\r', '').split('\n'):
        if reciprocate.QUOTE_START.match(line):
            break
        if not line.lstrip().startswith('>'):
            lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if greeting and lines and lines[0] == greeting:
        lines.pop(0)
    for _ in signoff:
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.pop()
    return [p.strip() for p in re.split(r'\n\s*\n', '\n'.join(lines)) if p.strip()]


def findings(contact, text, cfg=None, owner_wrote=''):
    """Failure strings for an email DRAFT to CONTACT; [] for anyone not in friend_groups."""
    cfg = check_settings(dict(cfg or {}))
    contact = contact or {}
    if owner_wrote.strip() or not is_friend(contact, cfg):
        return []
    out = []
    pref = (contact.get('engagement') or '').strip()
    hit = NOTICED.search(pref)
    if hit:
        out.append('AGENT_NOTICED: {} noticed agent-written email ("{}"); only text the owner wrote goes to them '
                   '(--owner-wrote in the owner\'s words)'.format(contact.get('name', 'they'), hit.group(0)))
    paras = paragraphs(text)
    n = sum(len(p.split()) for p in paras)
    if n > cfg['friend_max_words']:
        out.append('FRIEND_LENGTH: {} words to a friend (at most {}); they read a long, well-formed email as AI. '
                   'Drop what does not fit'.format(n, cfg['friend_max_words']))
    if len(paras) > cfg['friend_max_paragraphs']:
        out.append('FRIEND_PARAGRAPHS: {} paragraphs to a friend (at most {})'.format(
            len(paras), cfg['friend_max_paragraphs']))
    bullets = [l.strip() for p in paras for l in p.splitlines() if BULLET.match(l)]
    if bullets:
        out.append('FRIEND_BULLETS: no lists to a friend ("{}")'.format(bullets[0][:60]))
    return out
