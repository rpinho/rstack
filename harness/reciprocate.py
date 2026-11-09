"""Reciprocate: a reply mirrors the message it answers.

The owner, 11-08: "you copy their mood, you copy their tone, you copy their friendliness, you copy
their form... we're like a mirror." Reminders in prose did not hold, so each part is a lint finding
on a reply, checked against their latest message (`rh outreach draft ... --incoming FILE`):

  RECIPROCATE_LENGTH     our body within reciprocate_min_ratio..reciprocate_max_ratio of theirs
                         (0.7-1.6x), up to reciprocate_max_ratio_answering (2.0x) when they asked
                         us something; a short message (under reciprocate_short_words, 40) may get
                         that many words back, since a few words rarely carry a full answer.
                         The floor never exceeds reciprocate_floor_cap (120), the owner's cap on
                         a reply to a friend: above it the two rules could not both pass (friends,
                         11-09, 189 words in). A shorter reply takes --short-ok in the owner's words.
  RECIPROCATE_GREETING   they greet, we greet, in the same register (hi/hey/hello/ola vs
                         dear/caro); they greet us by name, we greet them by name
  RECIPROCATE_SIGNOFF    they sign off, we sign off
  RECIPROCATE_WARMTH     "good to hear from you" in, something as warm out
  RECIPROCATE_QUESTION   every question they ask gets an answer; asked about our life (how we
                         are, where we live, what we do), we say what we're doing and ask about theirs
  RECIPROCATE_FAMILY     they mention family, ours goes in; they don't, ours stays out
  RECIPROCATE_LANGUAGE   we answer in the language they wrote in
  RECIPROCATE_EMOTICON   none from us unless they used one, and then at most as many

Quoted text ("> ..." and everything after an "On ... wrote:" line) is never counted. Every
finding carries the evidence: their line and ours. The matching is lexical, English and
Portuguese, deliberately simple, so a finding is easy to check and easy to argue with.
"""
import re
import unicodedata

import mixed_language

GREETING = re.compile(r'^\s*(hi|hey|hello|dear|ol[aá]|oi|caro|cara|querid[oa]|prezad[oa]|bom dia|boa tarde)\b(.*)$', re.I)
CASUAL = {'hi', 'hey', 'hello', 'ola', 'oi', 'bom dia', 'boa tarde'}
CLOSER = re.compile(r'^\s*(best( wishes| regards)?|cheers|thanks|thank you|regards|kind regards|warm(ly| regards)|'
                    r'all the best|take care|(um |grande )?abra[cç]o(s)?|beijinhos?|beijos?|cumprimentos|obrigad[oa]|'
                    r'at[eé] breve)\b[ ,.!]*$', re.I)
QUOTE_START = re.compile(r'^\s*(on .+ wrote:|em .+ escreveu:|-----original message-----)', re.I)
WARM = re.compile(r"(?i)\b(good|great|nice|lovely|glad|happy|so good) to hear|\bhope (you|all|things|everything)|"
                  r"\bmiss (you|those)|\bque bom\b|\bbom saber\b|\bsaudades\b|\bfico (muito )?contente\b|"
                  r"\bespero que (estejas|esteja|est[aã]o)\b|\bgood to see\b|\bgreat to see\b")
FAMILY = re.compile(r"(?i)\b(kids?|children|son|sons|daughters?|wife|husband|partner|baby|babies|family|grandkids|"
                    r"filhos?|filhas?|mi[uú]dos|mulher|marido|fam[ií]lia|beb[eé]s?|netos?)\b")
EMOTICON = re.compile(r'[:;=]-?[)(DPp]|[\U0001F600-\U0001F64F\U0001F900-\U0001F9FF]')
LIFE = re.compile(r"(?i)what are you up to|how are you|how have you been|how('s| is) (life|it going|everything|the family)|"
                  r"what('s| is) new|what do you do|where are you|where do you live|are you (still )?(in|at|living|working)\b|"
                  r"como est[aá]s|como vais|o que andas|e tu\b|tudo bem|est[aá]s (em|a viver|a trabalhar|por)\b|"
                  r"onde (est[aá]s|vives|moras|trabalhas)|o que fazes|fizeste carreira|ainda est[aá]s|trabalhas (em|onde|n[ao])\b")
# Portuguese first person is mostly in the verb ending, so the usual verbs and a bare "eu" count (friends,
# 11-09: "eu vim para Stanford... Agora sou Head of Data" was missed).
FIRST_PERSON = re.compile(r"(?i)\b(i'm|i am|i've|i have been|we're|we've|i've been|lately i|these days i|i (work|live|moved)|"
                          r"estou|ando|tenho estado|temos estado|cá estamos|eu|sou|fiquei|vim|vivo|moro|trabalho|"
                          r"mudei|mud[aá]mos|mudamo-nos|agora sou|continuo)\b")
STOP = set('what when where which while with would could should there their them they this that these those '
           'have been from your yours about into just also some more much very really still then than will '
           'como para isso esta este estas estes mais muito também porque quando onde qual quais você voce '
           'vocês teus tuas seus suas nossa nosso'.split())


def defaults():
    return dict(reciprocate_min_ratio=0.7, reciprocate_max_ratio=1.6,
                reciprocate_max_ratio_answering=2.0, reciprocate_short_words=40, reciprocate_floor_cap=120)


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()


def parts(text):
    """(greeting line or '', body lines, sign-off lines), with quoted text removed."""
    lines = []
    for line in text.replace('\r', '').split('\n'):
        if QUOTE_START.match(line):
            break
        if not line.lstrip().startswith('>'):
            lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    greeting = ''
    if lines and GREETING.match(lines[0]) and len(lines[0].split()) <= 6:
        greeting = lines.pop(0)
    # A sign-off: a closing word, or a name line with or without a closing word above it.
    signoff = []
    is_name = lambda line: (0 < len(line.split()) <= 3 and not re.search(r'[.?:;!)]$|\d', line.strip())
                            and not EMOTICON.search(line))
    if lines and CLOSER.match(lines[-1]):
        signoff = [lines.pop()]
    elif len(lines) > 1 and is_name(lines[-1]):
        signoff = [lines.pop()]
        if lines and CLOSER.match(lines[-1]):
            signoff.insert(0, lines.pop())
    return greeting, [l for l in lines if l.strip()], signoff


def questions(lines):
    return [q.strip() for q in re.findall(r'[^.!?\n]*\?', ' '.join(lines)) if len(q.split()) >= 2]


def keywords(text):
    return {w for w in re.findall(r'\w{4,}', fold(text)) if w not in STOP}


def findings(incoming, draft, contact=None, cfg=None, short_ok=''):
    """(failures, notes) for a reply DRAFT to the INCOMING message. SHORT_OK is the owner's words
    allowing a reply below the length floor."""
    cfg = dict(defaults(), **(cfg or {}))
    contact = contact or {}
    failures, notes = [], []
    g_in, body_in, sign_in = parts(incoming)
    g_out, body_out, sign_out = parts(draft)
    text_in, text_out = '\n'.join(body_in), '\n'.join(body_out)
    n_in, n_out = len(text_in.split()), len(text_out.split())
    asked = questions(body_in)
    # Length.
    ratio_max = cfg['reciprocate_max_ratio_answering'] if asked else cfg['reciprocate_max_ratio']
    ceiling = max(int(n_in * ratio_max), cfg['reciprocate_short_words'])
    floor = int(n_in * cfg['reciprocate_min_ratio']) if n_in >= cfg['reciprocate_short_words'] else 0
    floor = min(floor, cfg['reciprocate_floor_cap'])
    if short_ok.strip():
        floor = 0
    if n_out > ceiling or n_out < floor:
        failures.append('RECIPROCATE_LENGTH: they wrote {} words, we write {} (keep it between {} and {}){}'.format(
            n_in, n_out, floor, ceiling, '; or --short-ok in the owner\'s words' if n_out < floor else ''))
    # Greeting and sign-off.
    if g_in:
        word_in = fold(GREETING.match(g_in).group(1))
        if not g_out:
            failures.append('RECIPROCATE_GREETING: they opened with "{}"; we open with no greeting'.format(g_in.strip()))
        else:
            word_out = fold(GREETING.match(g_out).group(1))
            if (word_in in CASUAL) != (word_out in CASUAL):
                failures.append('RECIPROCATE_GREETING: "{}" in, "{}" out: a different register'.format(
                    g_in.strip(), g_out.strip()))
            first = fold((contact.get('name') or '').split()[0]) if contact.get('name') else ''
            named_us = len(GREETING.match(g_in).group(2).strip(' ,!.').split()) >= 1
            if named_us and first and first not in fold(g_out):
                failures.append('RECIPROCATE_GREETING: they greeted us by name ("{}"); greet them by name'.format(
                    g_in.strip()))
    if sign_in and not sign_out:
        failures.append('RECIPROCATE_SIGNOFF: they signed off ("{}"); we end without one'.format(' / '.join(sign_in)))
    # Warmth.
    warm_in = WARM.search(incoming)
    if warm_in and not WARM.search(draft):
        failures.append('RECIPROCATE_WARMTH: they said "{}"; say something as warm back'.format(warm_in.group(0)))
    # Questions.
    for q in asked:
        if LIFE.search(q):
            if not FIRST_PERSON.search(text_out):
                failures.append('RECIPROCATE_QUESTION: they asked "{}"; say what you are doing'.format(q))
            if not questions(body_out):
                failures.append('RECIPROCATE_QUESTION: they asked about our life ("{}"); ask about theirs'.format(q))
        elif not keywords(q) & keywords(text_out) and keywords(q):
            failures.append('RECIPROCATE_QUESTION: their question "{}" has no answer in the draft'.format(q))
    # Family.
    fam_in, fam_out = FAMILY.search(text_in), FAMILY.search(text_out)
    if fam_in and not fam_out:
        failures.append('RECIPROCATE_FAMILY: they mentioned "{}"; ours goes in too'.format(fam_in.group(0)))
    elif fam_out and not fam_in:
        failures.append('RECIPROCATE_FAMILY: they said nothing about family; leave "{}" out'.format(fam_out.group(0)))
    # Language.
    lang_in, lang_out = mixed_language.language_of(text_in), mixed_language.language_of(text_out)
    if lang_in and lang_out and lang_in != lang_out:
        failures.append('RECIPROCATE_LANGUAGE: they wrote in {}; the reply is in {}'.format(lang_in, lang_out))
    # Emoticons.
    e_in, e_out = len(EMOTICON.findall(incoming)), len(EMOTICON.findall(draft))
    if e_out > e_in:
        failures.append('RECIPROCATE_EMOTICON: {} emoticon(s) from us, {} from them'.format(e_out, e_in))
    notes.append('reciprocate: {} words in, {} out; {} question(s) asked'.format(n_in, n_out, len(asked)))
    return failures, notes
