"""What a science email to a person must carry, from one lane's outreach postmortem (11-08).

Writing to scientists about their work: a plain question first got 3 replies of 3, a paper result
first 3 of 10, a bug report first 2 of 8. Every "no" was "this code isn't used" or "the number isn't
the interesting part", and five of the eight who replied asked what the sender does now. So a
science email (one that reports a result, a bound, a bug, a PR or a paper, or attaches a document)
fails lint when:

  SCIENCE_OPENER     its first paragraph asks nothing (unless they asked us something: answer first)
  LIFE_LINE_MISSING  it has no line about the sender's own life or work
  USERS_MISSING      it reports a bug with no evidence anyone still uses the code: the contact's
                     `users` field, or a named --target whose users check passed
  MEANING_MISSING    it gives a tighter number without saying what it means for their question
  CALL_MISSING       the contact has replied before and it offers no call (the lane's call_link)

Each has an override in the owner's words (`--opener-ok`, `--life-ok`, `--meaning-ok`,
`--nocall-ok`; `--users-override` for USERS_MISSING). To a friend (friend_email.py) the life line,
meaning and call offer are optional, since they add length; the question first stays. On in a lane with `science_email_rules = true`
in OUTREACH.toml; `life_words` adds the lane's own words for a life line (places, people), which
belong in the private lane config, not here; `call_link` is the booking link to offer. The matching
is lexical, English and Portuguese.
"""
import re

RESULT = re.compile(r"(?i)(\d[\d.,]*\s*(→|->|=>)\s*\d|\bfrom\s+\d[\d.,]*\s+to\s+\d|\bde\s+\d[\d.,]*\s+para\s+\d|"
                    r"\b(bound|tighter|improv\w*|beat|outperform\w*|theorem|lemma|proof|arxiv|preprint|bugs?|"
                    r"crash\w*|pull request|\bPR\b|melhor(ou|ia|ar)|limite|demonstra\w*|resultado|erro no c[oó]digo))")
BUG = re.compile(r"(?i)\b(bugs?|crash\w*|off-by-one|wrong output|erro no c[oó]digo|pull request|\bPRs?\b|patch)\b")
NUMBER_GAIN = re.compile(r"(?i)(\d[\d.,]*\s*(→|->|=>)\s*\d|\bfrom\s+\d[\d.,]*\s+to\s+\d|\bde\s+\d[\d.,]*\s+para\s+\d|"
                         r"\btighter\b|\bimproved? (the |your )?(bound|number|result|score)|"
                         r"\bmelhor(ou|ar) o (limite|resultado))")
MEANING = re.compile(r"(?i)\b(means|meaning|which says|so the|that tells|significa|quer dizer|ou seja|isto mostra)\b")
LIFE = (r"my (kids|boys|sons|family|wife|husband|partner|work|job|day)|the (kids|boys)|at work|"
        r"i'?m (now|working|doing|leading|at|in)|i (work|live|moved|run|started)|os (mi[uú]dos|meus filhos|rapazes)|"
        r"no trabalho|eu (trabalho|ando|estou|vivo|comecei|vim|fiquei|sou|mudei)|ando a|estou a (trabalhar|fazer)|"
        r"c[aá] em casa|por c[aá]|agora (sou|estou|trabalho|vivo)|sou agora|mud(ei|[aá]mos|amo-nos) para|vim para|"
        r"fiquei (em|no|na|por)|trabalho (em|numa?|n[ao]|como)")
CALL = r"\b(call|zoom|google meet|chamada|videochamada|falar(mos)?|conversar(mos)?|ligar|liga-me|catch up)\b"
IMAGE = re.compile(r"\.(jpe?g|png|heic|webp|gif)$", re.I)
GREETING = re.compile(r"(?i)^(ol[aá]|oi|hey|hi|hello|dear|querid[oa]|caro|cara)\b[^.?!\n]{0,40}[,!]?$")
SIGNOFF = re.compile(r"(?i)^(abra[cç]os?|beijinhos?|best|cheers|thanks|obrigad[oa])\b")
SCIENCE_KINDS = ('paper', 'code-bug', 'code-speedup', 'code')


def defaults():
    return dict(science_email_rules=False, life_words=[], call_link='')


def check_settings(cfg):
    for key, default in defaults().items():
        cfg.setdefault(key, default)
    if type(cfg['science_email_rules']) is not bool:
        raise ValueError('OUTREACH science_email_rules must be true or false')
    if type(cfg['life_words']) is not list or any(type(w) is not str or not w.strip() for w in cfg['life_words']):
        raise ValueError('OUTREACH life_words must be a list of words or phrases')
    if type(cfg['call_link']) is not str:
        raise ValueError('OUTREACH call_link must be a link')
    return cfg


def paragraphs(draft):
    lines = [l for l in draft.splitlines() if not l.lstrip().startswith('>')]
    paras = [p.strip() for p in '\n'.join(lines).split('\n\n') if p.strip()]
    if paras and GREETING.match(paras[0]):
        paras = paras[1:]
    return [p for p in paras if not SIGNOFF.match(p)]


def is_science(draft, attachments=(), kinds=()):
    docs = [p for p in attachments if not IMAGE.search(str(p))]
    return bool(RESULT.search(draft) or docs or set(kinds) & set(SCIENCE_KINDS))


def findings(contact, incoming, draft, attachments=(), kinds=(), overrides=None, cfg=None, users_ok=False,
             friend=False):
    """Failure strings for a science email; [] for any other message.

    OVERRIDES maps opener/life/meaning/nocall/users to the owner's words. USERS_OK is True when the
    caller already has evidence of use (a target whose users check passed). For a FRIEND
    (friend_email.py) the life line, meaning and call offer are optional: they add length, and
    length is what a friend reads as AI."""
    cfg = check_settings(dict(cfg or {}))
    overrides = {k: (v or '').strip() for k, v in (overrides or {}).items()}
    contact = contact or {}
    if not draft.strip() or not is_science(draft, attachments, kinds):
        return []
    out = []
    paras = paragraphs(draft)
    if paras and '?' not in paras[0] and '?' not in (incoming or '') and not overrides.get('opener'):
        out.append('SCIENCE_OPENER: a science email opens with a plain question, not the result (question first '
                   'got 3 of 3 replies, result first 3 of 10); or --opener-ok in the owner\'s words')
    life = re.compile(r'(?i)\b(' + '|'.join([LIFE] + [re.escape(w) for w in cfg['life_words']]) + r')\b')
    if not life.search(draft) and not overrides.get('life') and not friend:
        out.append('LIFE_LINE_MISSING: add one line about your own life or work (5 of 8 who replied asked what '
                   'you do now); or --life-ok')
    if BUG.search(draft) and not (contact.get('users') or '').strip() and not users_ok and not overrides.get('users'):
        out.append('USERS_MISSING: a bug report with no evidence the code is still used: the contact\'s users '
                   'field, a --target whose users check passed, or --users-override with their words (bug first '
                   'got 2 of 8, both "this code isn\'t used")')
    gain = NUMBER_GAIN.search(draft)
    if gain and not MEANING.search(draft) and not overrides.get('meaning') and not friend:
        out.append('MEANING_MISSING: a tighter number alone ("{}"): say what it means for their question; or '
                   '--meaning-ok'.format(gain.group(0)))
    call = re.compile(r'(?i)(' + (re.escape(cfg['call_link']) + '|' if cfg['call_link'] else '') + CALL + ')')
    if (contact.get('last_in') or '').strip() and not call.search(draft) and not overrides.get('nocall') \
            and not friend:
        out.append('CALL_MISSING: {} has replied before: offer a call{}; or --nocall-ok'.format(
            contact.get('name', 'they'), ' ({})'.format(cfg['call_link']) if cfg['call_link'] else ''))
    return out
