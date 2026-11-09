"""Local outreach ledger and gates. This module never sends or fetches anything."""
import settings
import claim_evidence
import mixed_language
import ops_mentions
import bughunt
import contacts_ledger
import friend_email
import reciprocate
import science_email
import voice_cuts
import speedup
import promise_words
import datetime as dt
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import urlsplit
import uuid

CONTACTS = settings.path('RH_CONTACTS', Path('.runtime/contacts.json'))
VOICE_COMMAND = settings.command('RH_VOICE_COMMAND', 'voice-check')
SCIENCE_COMMAND = settings.command('RH_SCIENCE_CHECK_COMMAND', 'science-check')
CHANNELS = ('email', 'x_reply', 'x_post', 'x_dm', 'linkedin')
# 11-08 addendum: code splits into the two things the bug-hunt skill delivers. Rows stored
# before then as 'code' were all bug reports, and count as code-bug.
KINDS = ('paper', 'code-bug', 'code-speedup', 'other')
EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
URL = re.compile(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>]+|\bwww\.[^\s<>]+')
UTC = dt.timezone.utc
REPLIED = settings.path('RH_X_REPLIED', Path('.runtime/x-replied.json'))
# The X rounds' activity log, beside replied.json unless set. Read only, to tell a like from a reply.
X_ACTIVITY = os.environ.get('RH_X_ACTIVITY_LOG')
# Actions that touch a post without replying to it. A post whose log rows are all of these, with at least
# one like or answer among them, was liked, not replied to. Any other action (reply, post, a failed reply,
# anything new) keeps the replied.json entry binding.
NOT_A_REPLY = {'like', 'like_error', 'answer_recorded', 'answer_received', 'capture_answer', 'conversation_read',
               'draft_reply', 'drop_draft', 'draft_dropped', 'notifications_check', 'mentions_read', 'follow'}
LIKED = {'like', 'answer_recorded', 'answer_received', 'capture_answer'}
# Before 11-07 some sessions logged a reply with only OUR reply's URL, so an old post can look liked-only
# when it was answered. Rounds draft for fresh posts, so the exemption needs every row inside this window.
LIKED_WINDOW = dt.timedelta(hours=72)
STANDING_APPROVAL = 'standing-approval-10-30'
X_PUBLIC = ('x_post', 'x_reply')
MENTION = re.compile(r'(?<![\w/])@([A-Za-z0-9_]{1,15})\b')
# Include bare domains: a missing scheme does not turn a link into plain text.
X_URL = re.compile(r'\b(?:[a-zA-Z][a-zA-Z0-9+.-]*://|www\.)[^\s<>]+|'
                   r'(?<![\w@/])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s<>]*)?')


def backup(path):
    """Keep the first preimage for this job, including empty preimages of new files."""
    dest = Path(str(path) + '.bak')
    if not dest.exists():
        if path.exists():
            shutil.copy2(path, dest)
        else:
            dest.touch(mode=0o600)


def time_of(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must have a timezone')
    return parsed


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(value, field):
    if not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value:
        raise ValueError(field + ' must be a nonempty single line')
    if EMAIL.search(value):
        raise ValueError(field + ': email addresses belong only in private contacts')
    return value.strip()


def settings(lane, rh):
    path = lane / 'OUTREACH.toml'
    cfg = rh.config(path) if path.exists() else {}
    for key, default in (('question_limit', 1), ('x_question_limit', 1), ('follow_up_days', 7)):
        cfg.setdefault(key, default)
        if type(cfg[key]) is not int or cfg[key] < 0 or (key == 'follow_up_days' and cfg[key] == 0):
            raise ValueError('OUTREACH ' + key + ' must be a positive integer (question_limit may be zero)')
    # A gate that switches itself off on a typo is worse than no gate, so these are checked
    # here rather than defaulted quietly inside the check.
    cfg.setdefault('recheck_roots', [])
    if type(cfg['recheck_roots']) is not list or any(type(r) is not str or not r.strip()
                                                     for r in cfg['recheck_roots']):
        raise ValueError('OUTREACH recheck_roots must be a list of directory paths or globs')
    if type(cfg.setdefault('require_claims', False)) is not bool:
        raise ValueError('OUTREACH require_claims must be true or false')
    if cfg.get('pod_incident_utc') is not None:
        if type(cfg['pod_incident_utc']) is not str or not claim_evidence.time_of(cfg['pod_incident_utc']):
            raise ValueError('OUTREACH pod_incident_utc must be an ISO 8601 time')
    if cfg['require_claims'] and not cfg['recheck_roots']:
        raise ValueError('OUTREACH require_claims needs recheck_roots to check against')
    bughunt.check_settings(cfg)
    science_email.check_settings(cfg)
    friend_email.check_settings(cfg)
    if cfg.setdefault('voice_cuts', 'auto') not in ('auto', 'on', 'off'):
        raise ValueError('OUTREACH voice_cuts must be "auto" (on when RH_VOICE_BANKS is set), "on" or "off"')
    for key, default in voice_cuts.defaults().items():
        cfg.setdefault(key, default)
        if type(cfg[key]) not in (int, float) or not 0 <= cfg[key] <= 1:
            raise ValueError('OUTREACH ' + key + ' must be a fraction between 0 and 1')
    for key, default in x_defaults().items():
        cfg.setdefault(key, default)
        if type(default) is bool and type(cfg[key]) is not bool:
            raise ValueError('OUTREACH ' + key + ' must be true or false')
        if type(default) is int and (type(cfg[key]) is not int or cfg[key] < 0):
            raise ValueError('OUTREACH ' + key + ' must be a whole number of minutes, 0 or more')
    return cfg


def x_defaults():
    """The X pacing and approval settings, for a lane with no OUTREACH.toml or without the keys.

    See docs/outreach.md, "Growing a small account on X". The original gap keeps its older
    environment override, RH_X_MIN_GAP_MINUTES, so an installation that set it is unchanged.
    """
    return dict(x_original_gap_minutes=int(os.environ.get('RH_X_MIN_GAP_MINUTES', '') or 120),
                x_reply_gap_minutes=3,
                x_reply_human_approval=True)


def contact_key(name):
    contacts = json.loads(CONTACTS.read_text())
    exact = [r['name'] for r in contacts if r['name'].casefold() == name.casefold()]
    hits = exact or [r['name'] for r in contacts if name.casefold() in r['name'].casefold()]
    if len(hits) != 1:
        raise ValueError('email recipient must uniquely match a name in private contacts.json')
    return hits[0]


def contact_language(name):
    """The recipient's `language` field from private contacts; None means English.

    Unset is English, so an installation that never fills the field keeps its old behaviour.
    """
    contacts = json.loads(CONTACTS.read_text())
    for row in contacts:
        if row['name'].casefold() == name.casefold():
            return mixed_language.code(row.get('language'))
    return None


def current(lane, rh):
    return rh.latest(rh.rows(lane / 'OUTREACH.jsonl'))


def all_rows(root, rh):
    for lane in sorted((root / 'lanes').glob('*')):
        if lane.is_dir():
            yield from current(lane, rh).values()


def record(lane, row, rh):
    # Reject addresses even in optional metadata (quotes, summaries, reasons, paths).
    if EMAIL.search(json.dumps(row, ensure_ascii=False)):
        raise ValueError('ledger metadata contains an email address; use a private contacts name')
    path = lane / 'OUTREACH.jsonl'
    backup(path)
    rh.append(path, row)


def body(row):
    return row['text'] if 'text' in row else Path(row['draft_path']).read_bytes().decode('utf-8')


def titles(text):
    text = re.sub(r'\[[^\]]+\]\([^\s)]+\)', ' LINK ', text)
    text = re.sub(r'["“][^"”]+["”]', ' TITLE ', text)
    return re.sub(r'\b(reading|your)\s+[^.!?\n]*?(?=\(https?://)', r'\1 TITLE ', text, flags=re.I)


def normalise(text, names=()):
    for name in sorted(names, key=len, reverse=True):
        for part in [name] + name.split():
            if len(part) > 1:
                text = re.sub(r'(?<!\w)' + re.escape(part) + r'(?!\w)', ' NAME ', text, flags=re.I)
    text = titles(text)
    text = URL.sub(' LINK ', text)
    text = unicodedata.normalize('NFKC', text).casefold()
    return ' '.join(re.findall(r'\w+', text))


def features(text, names=()):
    whole_body = text
    # Strip greetings and trailing signatures before choosing the boundary sentences.
    text = re.sub(r'^\s*(?:hi|hello|dear|hey|olá)\b[^\n]*\n+', '', text, flags=re.I)
    # Sign-off names (the owner's first name) come from RH_SIGNATURE_NAMES, comma-separated.
    signoffs = ['thanks', 'thank you', 'best', 'regards', 'cheers', 'obrigado', 'operator'] + [
        re.escape(n.strip()) for n in os.environ.get('RH_SIGNATURE_NAMES', '').split(',') if n.strip()]
    text = re.split(r'\n\s*(?:' + '|'.join(signoffs) + r')(?:[,!\s]|$)', text, maxsplit=1, flags=re.I)[0]
    # Protect periods and question marks inside URLs before splitting sentences.
    text = URL.sub(' LINK ', titles(text))
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
    first = normalise(sentences[0], names) if sentences else ''
    last = normalise(sentences[-1], names) if sentences else ''
    words = normalise(whole_body, names).split()
    return first, last, {tuple(words[i:i + 5]) for i in range(len(words) - 4)}


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a or b else 0.0


def similarities(left, right):
    names = (left['to_name'], right['to_name'])
    a, b = features(body(left), names), features(body(right), names)
    scores = [jaccard(a[0].split(), b[0].split()), jaccard(a[1].split(), b[1].split()), jaccard(a[2], b[2])]
    return [(label, score) for label, score, limit in zip(('first', 'last', 'body-5gram'), scores, (.6, .6, .35))
            if score >= limit]


def recent_sent(row, days, clock):
    try:
        return bool(row.get('sent')) and dt.timedelta(0) <= clock - time_of(row['sent']['utc']) <= dt.timedelta(days=days)
    except (KeyError, ValueError, TypeError):
        return False


def collisions(row, everyone, clock):
    return [other for other in everyone if (other['lane'], other['id']) != (row['lane'], row['id']) and
            other.get('to_key', '').casefold() == row['to_key'].casefold() and recent_sent(other, 7, clock)
            and other.get('status') != 'bounced']   # a bounce never reached them


def postmortem_check(row, text, cfg, lane, rh):
    """science_email.py: what a science email to a person carries (on with science_email_rules)."""
    try:
        person = contacts_ledger.merged(lane.parent.parent, row['to_key'])
    except (OSError, ValueError, KeyError):
        person = {'name': row.get('to_name', '')}
    incoming = ''
    if row.get('incoming'):
        try:
            incoming = Path(row['incoming']).read_text()
        except (OSError, UnicodeError):
            pass
    users_ok = any(((bughunt.latest_verdict(lane, rh, t) or {}).get('usage') or {}).get('verdict') == 'PASS'
                   for t in row.get('targets', []))
    overrides = dict(opener=row.get('opener_ok'), life=row.get('life_ok'), meaning=row.get('meaning_ok'),
                     nocall=row.get('nocall_ok'), users=row.get('users_override'))
    return science_email.findings(person, incoming, text, row.get('attachments', []), bughunt.kinds_of(row),
                                  overrides, {k: cfg[k] for k in science_email.defaults()}, users_ok,
                                  friend=friend_email.is_friend(person, cfg))


def awaiting_reply(row, text, everyone, lane):
    """AWAITING_REPLY (friends postmortem, 11-08): no new science email to someone whose last one has no
    reply yet, follow-ups included. A send they asked for (--requested) is a reply and passes, and so
    does a contact whose cadence is "fast" (they said they don't mind)."""
    if row.get('requested') or not science_email.is_science(text, row.get('attachments', []), bughunt.kinds_of(row)):
        return []
    try:
        person = contacts_ledger.merged(lane.parent.parent, row['to_key'])
    except (OSError, ValueError, KeyError):
        person = {}
    if person.get('cadence') == 'fast':
        return []
    key = row['to_key'].casefold()
    mine = [r for r in everyone if r.get('to_key', '').casefold() == key and r.get('channel') == 'email'
            and (r['lane'], r['id']) != (row['lane'], row['id'])]
    science = [sent_time(r) for r in mine if r.get('sent') and r.get('status') != 'bounced'
               and set(bughunt.kinds_of(r)) & set(science_email.SCIENCE_KINDS)]
    science = [t for t in science if t]
    if not science:
        return []
    last = max(science)
    replies = [time_of(r['reply']['utc']) for r in mine if (r.get('reply') or {}).get('utc')]
    try:
        if person.get('last_in'):
            replies.append(time_of(person['last_in']))
    except (ValueError, TypeError):
        pass
    if any(t and t >= last for t in replies):
        return []
    return ['AWAITING_REPLY: the last science email to {} ({}) has no reply yet; wait for it, or draft with '
            '--requested "their words" if they asked for this'.format(row.get('to_name') or row['to_key'],
                                                                      last.isoformat()[:10])]


def cut_check(row, text, cfg, checks):
    """Paper-cut (voice_cuts.py): the draft is built from the author's own messages, listed in
    DRAFT.cuts. On whenever banks are configured, unless the lane says voice_cuts = "off"."""
    if cfg['voice_cuts'] == 'off' or row.get('owner_wrote'):
        return []
    try:
        banks = voice_cuts.load_banks()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks['cuts'].append('VOICE_BANKS_MISSING: the banks file is unreadable ({})'.format(type(exc).__name__))
        return []
    if not banks:
        if cfg['voice_cuts'] == 'on':
            checks['cuts'].append('VOICE_BANKS_MISSING: the lane requires paper-cut drafts and RH_VOICE_BANKS is unset')
        return []
    incoming = ''
    if row.get('incoming'):
        try:
            incoming = Path(row['incoming']).read_text()
        except (OSError, UnicodeError):
            pass
    names = [n.strip() for n in os.environ.get('RH_SIGNATURE_NAMES', '').split(',') if n.strip()]
    found, stats = voice_cuts.check(text, voice_cuts.cuts_for(row['draft_path']) if row.get('draft_path') else None,
                                    incoming, banks,
                                    {k: cfg[k] for k in voice_cuts.defaults()}, names)
    checks['cuts'] += found
    return ['cuts: {} lines, {:.0%} of words and {:.0%} of pairs from them'.format(
        stats['cuts'], stats['word_cover'], stats['pair_cover'])] if stats else []


def voice(text, channel):
    command = list(VOICE_COMMAND) + (['--reply'] if channel == 'x_reply' else [])
    try:
        run = subprocess.run(command, input=text, text=True, capture_output=True, timeout=30)
        fails = [l for l in run.stdout.splitlines() if l.startswith('FAIL:')]
        return fails or (['xlint could not complete'] if run.returncode else [])
    except (OSError, subprocess.TimeoutExpired):
        return ['xlint could not complete']


def science_checks(text, attachments, language=None, claims=(), kinds=()):
    """Optional lane check: stdin JSON, stdout FAIL: lines, nonzero means refusal.

    `language` carries the recipient's contact language so an installation's own checker can
    apply the mixed-language rule as well, and `claims` the claim directories this message
    reports, so the checker can apply the re-check gates to them. A checker that ignores
    either field is unaffected.
    """
    try:
        run = subprocess.run(SCIENCE_COMMAND, input=json.dumps({'text': text, 'language': language,
                                                                'attachments': [str(p) for p in attachments],
                                                                'claims': [str(c) for c in claims],
                                                                'kinds': list(kinds)}),
                             text=True, capture_output=True, timeout=30)
        errors = [line for line in run.stdout.splitlines() if line.startswith('FAIL:')]
        return errors or (['science checker could not complete'] if run.returncode else [])
    except (OSError, subprocess.TimeoutExpired):
        return ['science checker could not complete']


def link_errors(text):
    errors = []
    for match in URL.finditer(text):
        url = match.group().rstrip('.,;!?)]}')
        try:
            p = urlsplit(url)
            if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.port == 0:
                raise ValueError()
            host = p.hostname.encode('idna').decode('ascii')
            if not re.fullmatch(r'[A-Za-z0-9.-]+|[0-9a-fA-F:]+', host) or '..' in host:
                raise ValueError()
        except (ValueError, UnicodeError):
            errors.append('malformed URL (not fetched)')
    # Catch incomplete schemes and spaces immediately following a scheme too.
    if re.search(r'https?:(?!//)|https?://(?:\s|$)', text, re.I):
        errors.append('malformed URL (not fetched)')
    return errors


def same_row(left, right):
    return (left['lane'], left['id']) == (right['lane'], right['id'])


def post_id(value):
    if not isinstance(value, str):
        return None
    if value.isdecimal():
        return value
    match = re.fullmatch(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/(?:[A-Za-z0-9_]+|i/web)/status/(\d+)(?:[/?#].*)?', value, re.I)
    return match[1] if match else None


def only_liked(target, log=None, now=None):
    """True when the X activity log shows TARGET was liked or its answer recorded, and nothing that could
    be a reply. general, 11-09: the drafting round added a post to replied.json when it liked an answer,
    so the thanks it drafted under the same post was refused as already replied and could never post.
    Without log evidence the replied.json entry stands: a reply recorded only there is still protected.
    Every row about TARGET must be inside LIKED_WINDOW; an unparseable time counts as outside it."""
    now = now or dt.datetime.now(UTC)
    path = Path(log or X_ACTIVITY or REPLIED.parent / 'log.jsonl').expanduser()
    try:
        lines = Path(path).read_text().splitlines()
    except (OSError, UnicodeError):
        return False
    actions = set()
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        fields = [str(row.get(k) or '') for k in ('target_url', 'in_reply_to')]
        if any(post_id(f) == target or ('/' + target) in f for f in fields):
            actions.add(str(row.get('action', '')))
            try:
                when = dt.datetime.fromisoformat(str(row.get('utc', '')).replace('Z', '+00:00'))
                if when.tzinfo is None or now - when > LIKED_WINDOW:
                    return False
            except ValueError:
                return False
    return bool(actions & LIKED) and actions <= NOT_A_REPLY


def reply_target(row):
    return post_id(row.get('in_reply_to')) or post_id(row.get('self_reply_to'))


def original(row):
    return row.get('channel') == 'x_post' and not row.get('self_reply_to')


def topics(row, text):
    return ({m.casefold() for m in re.findall(r'\bC\d+[a-z]?\b', text, re.I)} |
            {m.casefold() for m in re.findall(r'(?<!\w)#([\w-]+)', text)} |
            {p.casefold() for p in row.get('projects', [])})


def mainly_question(text):
    text = X_URL.sub('', text)
    sentences = [s.strip() for s in re.findall(r'[^.!?]+[.!?]?', text) if s.strip()]
    questions = [s for s in sentences if s.endswith('?')]
    return bool(questions) and (len(questions) * 2 >= len(sentences) or
                               sum(len(s) for s in questions) * 2 >= sum(map(len, sentences)))


def activity_time(row):
    # A posting attempt also consumes a slot: the hook cannot know whether the network succeeded.
    # A dropped row does not: dropping it is the record that it never went out (general, 11-09: two
    # originals that failed on a media upload and on a still-processing video, both dropped, kept
    # the next original out for 120 min and counted toward the day's limit).
    if row.get('status') == 'dropped':
        return None
    for key in ('sent', 'gate_attempt'):
        if row.get(key, {}).get('utc'):
            return time_of(row[key]['utc'])
    if row.get('status') == 'approved':
        return time_of(row['approval']['utc'])
    return None


# A post that is only a greeting. X's own product lead said posts like "gm" waste reach; a
# greeting with anything real in it is not matched.
FILLER = re.compile(r'^\W*(?:gm|gn|good\s+(?:morning|night|evening)|happy\s+(?:monday|tuesday|'
                    r'wednesday|thursday|friday|saturday|sunday|weekend|new\s+week)|hello\s+'
                    r'(?:world|everyone|x|twitter))(?:[\s,]+(?:everyone|all|friends|folks|x|twitter|'
                    r'fam))?\W*$', re.I)


def sent_time(row):
    """When a row actually went out (or a posting attempt was made), never its approval time. A dropped
    row never went out."""
    if row.get('status') == 'dropped':
        return None
    for key in ('sent', 'gate_attempt'):
        if row.get(key, {}).get('utc'):
            return time_of(row[key]['utc'])
    return None


def x_checks(row, text, everyone, clock, selected=(), cfg=None, posting=False):
    """Cross-lane reach checks; warnings never affect PASS. No network access.

    cfg is the row's lane OUTREACH settings (defaults when None). posting=True is the posting
    gate's call, at the moment a post would go out: only then are replies spaced, because a
    round's replies are approved together and must not leave together.
    """
    failures, warnings = [], []
    if row.get('channel') not in X_PUBLIC:
        return failures, warnings
    cfg = dict(x_defaults(), **(cfg or {}))
    others = [r for r in everyone if not same_row(row, r)]
    if posting and row['channel'] == 'x_reply' and cfg['x_reply_gap_minutes']:
        gap = dt.timedelta(minutes=cfg['x_reply_gap_minutes'])
        for other in others:
            stamp = sent_time(other) if other.get('channel') == 'x_reply' else None
            if stamp and abs(clock - stamp) < gap:
                failures.append('x_reply within {} min of another reply ({}/{} at {}); post a '
                                'round\'s replies spaced, not as a burst; next one from {}'.format(
                                    cfg['x_reply_gap_minutes'], other['lane'], other['id'],
                                    stamp.astimezone(UTC).strftime('%H:%MZ'),
                                    (stamp + gap).astimezone(UTC).strftime('%H:%MZ')))
    if original(row) and FILLER.match(X_URL.sub('', text)):
        failures.append('filler post (a greeting with nothing in it); post when there is something '
                        'real, or not at all')
    if original(row):
        # 11-03: the daily limit was 1; now RH_X_ORIGINALS_PER_DAY (default 3) across all lanes,
        # and x_original_gap_minutes (OUTREACH.toml; default 120, or RH_X_MIN_GAP_MINUTES) between
        # originals so they don't land as a burst.
        limit = int(os.environ.get('RH_X_ORIGINALS_PER_DAY', '3'))
        gap = dt.timedelta(minutes=cfg['x_original_gap_minutes'])
        today = []
        for other in others:
            if original(other):
                stamp = activity_time(other)
                if stamp and stamp.astimezone(UTC).date() == clock.astimezone(UTC).date():
                    today.append(other)
                if stamp and abs(clock - stamp) < gap:
                    failures.append('x_post within {} min of another original: {}/{}'.format(
                        int(gap.total_seconds() // 60), other['lane'], other['id']))
        if len(today) >= limit:
            failures.append('x_post daily limit ({} per UTC day across all lanes) reached: {}'.format(
                limit, ', '.join('{}/{}'.format(o['lane'], o['id']) for o in today)))
        if sum(original(r) for r in selected) > limit:
            failures.append('x_post daily limit ({}); split batch contains more originals'.format(limit))
        for match in X_URL.finditer(text):
            url = match.group().rstrip('.,;!?)]}')
            try:
                parsed = urlsplit(url if '://' in url else 'https://' + url)
                if parsed.hostname != 'x.com' or parsed.username or parsed.password:
                    failures.append('external URL in main post; put the link in a separate --self-reply-to ID row')
            except ValueError:
                failures.append('invalid URL in main post')
        if mainly_question(text) and not MENTION.search(text):
            failures.append('question addressed to nobody; use x_reply on that person\'s post with --in-reply-to URL')
        own_topics = topics(row, text)
        counts = {topic: set() for topic in own_topics}
        for other in others:
            if not original(other):
                continue
            stamp = activity_time(other)
            is_selected = any(same_row(other, r) for r in selected)
            if not is_selected and not (stamp and dt.timedelta(0) <= clock - stamp <= dt.timedelta(hours=48)):
                continue
            try:
                shared = own_topics & topics(other, body(other))
            except (OSError, UnicodeError):
                failures.append('topic comparison draft unreadable: ' + other['id'])
                continue
            for topic in shared:
                counts[topic].add((other['lane'], other['id']))
        for topic, matches in counts.items():
            if len(matches) >= 4:
                failures.append('five or more x_posts on topic {} within 48 h; bundle as a roundup'.format(topic))
        if not row.get('media'):
            warnings.append('media recommended: add --media PATH when a real, suitable image is available')
    if row.get('media'):
        for path in row['media']:
            if not Path(path).is_file():
                failures.append('media file missing: ' + path)
    if row['channel'] == 'x_reply':
        target = post_id(row.get('in_reply_to'))
        if not target or not str(row.get('in_reply_to', '')).startswith(('https://', 'http://')):
            failures.append('x_reply requires --in-reply-to URL for an X post')
        try:
            replied = json.loads(REPLIED.read_text())
            if not isinstance(replied, (list, dict)):
                raise ValueError('expected IDs')
            ids = {post_id(str(k)) for k in replied}
            if target and target in ids:
                if only_liked(target):
                    warnings.append('replied.json lists {} but the X log shows only a like or an answer, no reply; '
                                    'not counted as replied'.format(target))
                else:
                    failures.append('already replied to this post in read-only replied.json: ' + target)
        except (OSError, ValueError, TypeError):
            failures.append('cannot read replied.json; duplicate reply check unavailable')
        for other in others:
            if other.get('channel') != 'x_reply':
                continue
            if target and reply_target(other) == target and (other.get('sent') or other.get('gate_attempt') or other.get('status') == 'approved'):
                failures.append('already replied or reserved reply to this post: {}/{}'.format(other['lane'], other['id']))
            if recent_sent(other, 14, clock) or any(same_row(other, r) for r in selected):
                try:
                    for label, score in similarities(row, other):
                        failures.append('near-duplicate reply {}/{}: {} Jaccard {:.3f}'.format(other['lane'], other['id'], label, score))
                except (OSError, UnicodeError):
                    failures.append('reply comparison draft unreadable: ' + other['id'])
    mentions = {m.casefold() for m in MENTION.findall(text)}
    credited = {h.lstrip('@').casefold() for h in row.get('credit', [])}
    target_author = re.match(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/', row.get('in_reply_to', ''), re.I)
    if target_author:
        credited.add(target_author[1].casefold())
    for handle in sorted(mentions - credited):
        warnings.append('@{}: tagging for reach is discouraged; use --credit @handle only for real credit, or reply to their post'.format(handle))
    return failures, warnings


def lint_rows(lane, selected, rh, allow_collision=None):
    cfg = settings(lane, rh)
    clock = time_of(rh.now())
    everyone = list(all_rows(lane.parent.parent, rh))
    peers = {r['id']: r for r in everyone if r['lane'] == lane.name and
             (recent_sent(r, 14, clock) or any(s.get('batch') and r.get('batch') == s['batch'] for s in selected))}
    peers.update({r['id']: r for r in selected})
    results = {}
    for row in selected:
        checks = dict(voice=[], questions=[], contact=[], collision=[], links=[], science=[],
                      language=[], evidence=[], ops=[], promise=[], bughunt=[], reciprocate=[], cuts=[], postmortem=[],
                      friend=[])
        try:
            text = body(row)
        except (OSError, UnicodeError):
            results[row['id']] = dict(ok=False, utc=rh.now(), checks={'draft': ['draft unreadable']})
            continue
        checks['voice'] = voice(text, row['channel'])
        cut_stats = cut_check(row, text, cfg, checks)
        limit = cfg['question_limit'] if row['channel'] in ('email', 'linkedin') else cfg['x_question_limit']
        questions = URL.sub('', text).count('?')
        if questions > limit:
            checks['questions'].append('at most {} question(s); found {}'.format(limit, questions))
        language = None
        if row['channel'] == 'email':
            try:
                if contact_key(row['to_key']) != row['to_key']:
                    checks['contact'].append('to_key must be the canonical contacts name')
            except (OSError, ValueError, KeyError):
                checks['contact'].append('recipient missing from private contacts.json')
            else:
                try:
                    language = contact_language(row['to_key'])
                except ValueError as error:
                    checks['contact'].append(str(error))
                except (OSError, KeyError):
                    # An unreadable contacts file is the check above's business, not this one's.
                    language = None
        for other in ([] if row['channel'] in X_PUBLIC else collisions(row, everyone, clock)):
            # A send they asked for is a reply, not outreach (11-08); the request is the reason.
            if not allow_collision and not row.get('requested'):
                checks['collision'].append('recent send: {}/{}'.format(other['lane'], other['id']))
        evidence_warnings = []
        checks['links'] = link_errors(text)
        # No ops in a message to a person (Ricardo, 11-06). A public post is not covered: Ricardo
        # names his own tools and hosts in public, and this is about what a friend is told.
        ops_warnings = []
        if row['channel'] not in X_PUBLIC:
            checks['ops'], ops_warnings = ops_mentions.findings(text, row.get('asked_about', []))
        # Don't sell an unrefereed result (Ricardo, 11-02, after a friends email ranked unrefereed
        # lane results as "most promising"). The verdict has to be in the words the recipient
        # reads, not only in our ledger, which they cannot see. Public posts are covered too: the
        # rule is about overstating a result, and that is worse in public, not better.
        checks['promise'], promise_warnings = promise_words.findings(text)
        # Mixed language: the technical paragraphs in English, the rest in the recipient's own.
        checks['language'], language_warnings = mixed_language.findings(
            text, language if row['channel'] == 'email' else None, row.get('attachments', []))
        science_warnings = []
        if cfg.get('science_checks', False) and row['channel'] == 'email':
            attachments = row.get('attachments', [])
            if 'code-speedup' in bughunt.kinds_of(row):
                covered = speedup.covered_attachments(row)
                attachments = [a for a in attachments if a not in covered]
                science_warnings = ['{} is the verified speedup patch (VERIFY.json PASS); the result-claim '
                                    'checks do not apply to it'.format(Path(a).name) for a in covered]
            checks['science'] = science_checks(text, attachments, language, row.get('claims', []),
                                               bughunt.kinds_of(row))
        # The two postmortem gates (Ricardo, 11-05): a result is sendable only once a separate
        # model has rebuilt it from the public inputs, and pod-touched evidence only once it has
        # been re-run after the host incident. Both read the lane's own re-check ledger.
        if row['channel'] == 'email':
            checks['evidence'], evidence_warnings = claim_evidence.findings(
                row.get('claims', []), cfg.get('recheck_roots', []),
                cfg.get('pod_incident_utc'), cfg.get('require_claims', False))
        # Two emails in a batch resembling each other is a warning, not a failure (Ricardo,
        # 11-05): "I don't think anybody will be comparing emails. What's important is that it
        # doesn't sound like AI slop and that it uses my voice." A shared closing is the usual
        # cause, and the two-language rule makes a shared Portuguese closing likelier still, so
        # this must never block recording or sending. The voice check is what guards slop.
        batch_warnings = []
        for other in ([] if row['channel'] == 'x_reply' else peers.values()):
            if other['id'] == row['id']:
                continue
            try:
                for label, score in similarities(row, other):
                    batch_warnings.append('pair {} / {}: {} Jaccard {:.3f}; vary it if it reads '
                                          'as a template'.format(row['id'], other['id'], label, score))
            except (OSError, UnicodeError):
                batch_warnings.append('comparison draft unreadable: ' + other['id'])
        # The bug-hunt lane rules (docs/outreach.md, "Bug-hunt lane"). Those driven by the draft or
        # the contact always apply (a kind, a named target, a dead address, an extra-scrutiny
        # contact); the daily limit and the required questions are on when OUTREACH.toml says so.
        bughunt_warnings, reciprocate_warnings = [], []
        # Reciprocate (11-08): a reply mirrors their latest message. Hard wherever we owe a reply:
        # the contact's ball is with us, or they asked for this send.
        if row['channel'] == 'email':
            try:
                person = contacts_ledger.merged(lane.parent.parent, row['to_key'])
            except (OSError, ValueError, KeyError):
                person = {'name': row.get('to_name', '')}
            if row.get('incoming'):
                try:
                    found, notes = reciprocate.findings(Path(row['incoming']).read_text(), text, person, cfg,
                                                        short_ok=row.get('short_ok') or '')
                    checks['reciprocate'] += found
                    reciprocate_warnings += notes
                except (OSError, UnicodeError):
                    checks['reciprocate'].append('RECIPROCATE_INCOMING_MISSING: cannot read ' + row['incoming'])
            elif person.get('ball') == 'us' or row.get('requested'):
                checks['reciprocate'].append('RECIPROCATE_INCOMING_MISSING: this is a reply (the ball is with us, '
                                             'or they asked for it); draft it with --incoming THEIR_MESSAGE so it '
                                             'can mirror them')
        # A friend reads a long, well-formed email as AI (a friend's call, 11-09): short, no lists.
        if row['channel'] == 'email':
            checks['friend'] = friend_email.findings(person, text, cfg, row.get('owner_wrote') or '')
        if row['channel'] == 'email' and cfg['science_email_rules']:
            checks['postmortem'] = postmortem_check(row, text, cfg, lane, rh) + awaiting_reply(row, text, everyone, lane)
        if row['channel'] == 'email':
            if not bughunt.kinds_of(row) or set(bughunt.kinds_of(row)) - set(KINDS):
                checks['bughunt'].append('KIND_MISSING: every email draft says what it reports '
                                         '(--kind paper|code|other)')
            found, bughunt_warnings = bughunt.findings(row, text, cfg, lane, rh, everyone, clock)
            checks['bughunt'] += found
        warnings = (list(language_warnings) + evidence_warnings + ops_warnings
                    + promise_warnings + batch_warnings + bughunt_warnings + science_warnings
                    + reciprocate_warnings + cut_stats)
        if row['channel'] in X_PUBLIC:
            checks['reach'], reach_warnings = x_checks(row, text, everyone, clock, selected, cfg)
            warnings += reach_warnings
        results[row['id']] = dict(warnings=warnings, ok=not any(checks.values()), utc=rh.now(), sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), checks=checks)
        if allow_collision:
            results[row['id']]['allow_collision'] = safe(allow_collision, 'collision reason')
    return results


def health(lane, rh):
    clock = time_of(rh.now())
    errors = []
    for row in current(lane, rh).values():
        approval = row.get('approval') or {}
        if row['status'] == 'approved':
            try:
                if clock - time_of(approval['utc']) > dt.timedelta(hours=48):
                    errors.append('outreach {}: approved over 48 h ago, never sent'.format(row['id']))
            except (KeyError, ValueError, TypeError):
                errors.append('outreach {}: invalid approval timestamp'.format(row['id']))
        if row['status'] == 'sent' and row['channel'] not in X_PUBLIC:
            if not all(approval.get(k) for k in ('utc', 'by', 'sha256', 'quote')):
                errors.append('outreach {}: sent without approval'.format(row['id']))
            try:
                if not row.get('reply') and time_of(row['follow_up_due']) < clock:
                    errors.append('outreach {}: follow-up overdue'.format(row['id']))
            except (KeyError, ValueError, TypeError):
                errors.append('outreach {}: invalid or missing follow-up date'.format(row['id']))
    return errors


def in_temp_dir(path):
    if os.environ.get('RH_DRAFT_TEMP_OK') == '1':
        return False
    roots = {os.path.realpath(d) for d in ('/tmp', '/var/folders', tempfile.gettempdir())}
    real = os.path.realpath(str(path))
    return any(real == r or real.startswith(r.rstrip('/') + '/') for r in roots)


def note_contact(root, row, action):
    """Keep the contact current from the ledger: a send moves the ball to them, a reply to us.
    Written to the private update ledger, never to the contacts file (contacts_ledger)."""
    try:
        if action == 'reply':
            contacts_ledger.record_reply(root, row['to_key'], row['reply']['utc'], row['reply']['summary'])
        else:
            contacts_ledger.record_sent(root, row['to_key'], row['sent']['utc'], row['purpose'], row['channel'])
    except (OSError, ValueError, KeyError) as error:
        print('  WARN: contact not updated: {}'.format(error))


def stats(rows, contact=None):
    """Emails sent, replies, reply rate, by kind, last in and out, per contact and in total."""
    emails = [r for r in rows if r.get('channel') == 'email' and r.get('sent')]
    if contact:
        emails = [r for r in emails if r.get('to_key', '').casefold() == contact.casefold()]

    def tally(group):
        out = dict(sent=len(group), replies=sum(bool(r.get('reply')) for r in group),
                   bounced=sum(r.get('status') == 'bounced' for r in group))
        out['reply_rate'] = round(out['replies'] / out['sent'], 3) if out['sent'] else None
        return out

    # An email counts once in the totals and once under each kind it carries, so the kinds can
    # add up to more than the total.
    def kinds(r):
        return bughunt.kinds_of(r) or ['unknown']

    def by_kind(group):
        return {k: tally([r for r in group if k in kinds(r)]) for k in sorted({k for r in group for k in kinds(r)})}

    people = {}
    for key in sorted({r['to_key'] for r in emails}):
        mine = [r for r in emails if r['to_key'] == key]
        last_out = max(r['sent']['utc'] for r in mine)
        last_in = max([r['reply']['utc'] for r in mine if r.get('reply')] or [None], key=lambda v: v or '')
        people[key] = dict(tally(mine), by_kind=by_kind(mine), last_out=last_out, last_in=last_in,
                           ball='us' if last_in and last_in > last_out else 'them')
    return dict(total=dict(tally(emails), by_kind=by_kind(emails), contacts=len(people)), contacts=people)


def batch_draft(lane, rh, contact, out):
    """Merge a contact's unsent email drafts into one new draft; the originals are dropped."""
    rows = [r for r in current(lane, rh).values() if r.get('channel') == 'email'
            and r.get('to_key') == contact and r['status'] in ('drafted', 'linted', 'approved')]
    if len(rows) < 2:
        raise ValueError('batch needs two or more unsent emails to {}; found {}'.format(contact, len(rows)))
    rows.sort(key=lambda r: r['created'])
    parts = [body(r).strip() for r in rows]
    out = Path(out).expanduser().resolve()
    out.write_text(bughunt.MERGE_MARK + '\n\n' + '\n\n'.join(parts) + '\n')
    kinds = []
    for r in rows:
        kinds += [k for k in bughunt.kinds_of(r) if k not in kinds]
    merged = dict(id=uuid.uuid4().hex[:16], lane=lane.name, channel='email', to_name=rows[0]['to_name'],
                  to_key=contact, purpose=safe('batched: ' + '; '.join(r['purpose'] for r in rows), 'purpose')[:300],
                  draft_path=str(out), draft_sha256=sha(out), status='drafted', created=rh.now(),
                  batched_from=[r['id'] for r in rows])
    if kinds:
        merged.update(kind=kinds[0], kinds=kinds)
    for key in ('targets', 'claims', 'rechecks', 'attachments'):
        values = sorted({v for r in rows for v in r.get(key, [])})
        if values:
            merged[key] = values
    overrides = [r['target_override'] for r in rows if r.get('target_override')]
    if overrides:
        merged['target_override'] = '; '.join(overrides)
    return merged, rows


@contextlib.contextmanager
def send_lock(root, action):
    # Serialize cross-lane check + receipt, while preserving the usual per-lane append lock.
    if action in ('status', 'due'):
        yield
        return
    with (root / '.outreach.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def arguments(sub):
    parser = sub.add_parser('outreach', help='draft, lint, approve and track outreach; never sends')
    actions = parser.add_subparsers(dest='action', required=True)
    p = actions.add_parser('stats', help='emails sent, replies and reply rate, per contact and in total')
    p.add_argument('lane', nargs='?')
    p.add_argument('--contact')
    p.add_argument('--json', action='store_true')
    p.add_argument('--aggregate', action='store_true', help='totals and kinds only, no names (for publishing)')
    p = actions.add_parser('batch', help="merge a contact's unsent emails into one draft")
    p.add_argument('lane')
    p.add_argument('contact')
    p.add_argument('--file', required=True, type=Path, help='where to write the merged draft')
    p = actions.add_parser('bounce', help='an email bounced: mark the address dead and queue a find')
    p.add_argument('lane')
    p.add_argument('id')
    p.add_argument('--address', help='the address that bounced (default: every live one on record)')
    p = actions.add_parser('adopt', help='bookkeeping: make a hand-logged send (sent_at, no status) a sent row')
    p.add_argument('lane')
    p.add_argument('id')
    p.add_argument('--kind', required=True, choices=KINDS)
    p.add_argument('--via', default='browser', choices=('api', 'browser'))
    p.add_argument('--message-id', default='not recorded')
    p.add_argument('--reason', required=True)
    p.add_argument('--purpose', help='replace the purpose: a hand-logged purpose may hold an address, which no ledger row may')
    p = actions.add_parser('set-kind', help='bookkeeping: say what an email that already went out reported')
    p.add_argument('lane')
    p.add_argument('id')
    p.add_argument('kind', choices=KINDS)
    p.add_argument('--reason', required=True)
    p = actions.add_parser('review', help='record a review of the exact text of a draft')
    p.add_argument('lane')
    p.add_argument('id')
    p.add_argument('--by', required=True, help='who or what reviewed it, not the drafter')
    p.add_argument('--verdict', required=True, choices=('pass', 'fail'))
    p.add_argument('--notes', default='')
    contact = actions.add_parser('contact', help='contacts kept current').add_subparsers(dest='contact_action', required=True)
    p = contact.add_parser('show')
    p.add_argument('name')
    p = contact.add_parser('find', help='look for current addresses in public sources')
    p.add_argument('name')
    p.add_argument('--url', action='append', default=[], help='a lab page or university profile to read')
    p.add_argument('--record', action='append', default=[], metavar='ADDRESS', help='record this found address')
    p = contact.add_parser('answered', help='record that the contact already answered a required question')
    p.add_argument('name')
    p.add_argument('question')
    p.add_argument('--source', required=True)
    p = contact.add_parser('engagement', help='how this person prefers to be engaged, from their own words')
    p.add_argument('name')
    p.add_argument('text')
    p.add_argument('--source', required=True)
    p = contact.add_parser('scrutiny')
    p.add_argument('name')
    p.add_argument('level', choices=('normal', 'extra'))
    contact.add_parser('pending', help='updates the contacts file does not have yet, for its owner to land')
    for action in ('draft', 'lint', 'approve', 'sent', 'record-sent', 'reply', 'close', 'drop', 'status', 'due'):
        p = actions.add_parser(action)
        if action == 'due':
            p.add_argument('--all', action='store_true', help='include future follow-ups')
            p.add_argument('--json', action='store_true')
            continue
        p.add_argument('lane', nargs='?' if action == 'status' else None)
        if action == 'status':
            p.add_argument('--json', action='store_true')
        elif action == 'draft':
            p.add_argument('--to', required=True)
            p.add_argument('--channel', required=True, choices=CHANNELS)
            p.add_argument('--purpose', required=True)
            p.add_argument('--file', required=True, type=Path)
            p.add_argument('--batch')
            p.add_argument('--in-reply-to', help='X post URL for x_reply')
            p.add_argument('--self-reply-to', help='our X post ID; x_post link self-reply, linted separately')
            p.add_argument('--credit', action='append', default=[], help='real credit: @handle')
            p.add_argument('--media', action='append', default=[], type=Path)
            p.add_argument('--project', action='append', default=[], help='stable project tag for the 48 h series check')
            p.add_argument('--attach', action='append', default=[], help='attached results, checked with the configured science command')
            p.add_argument('--claim', action='append', default=[], help='claim directory this reports; gated on its independent re-check')
            p.add_argument('--kind', action='append', default=[], choices=KINDS, help='what the email reports (required for email); repeat it for an email that carries more than one, e.g. bugs and a speedup')
            p.add_argument('--speedup', action='append', default=[], metavar='DIR', help='a verified speedup (SPEEDUP.json + VERIFY.json); code-speedup emails need one')
            p.add_argument('--overlap-checked', help='how we checked their own work on speed (asked them, read their open PRs)')
            p.add_argument('--incoming', type=Path, help='their latest message, which a reply must mirror (reciprocate)')
            p.add_argument('--users-override', help="the recipient's own words that this code is in their current pipeline")
            for flag, what in (('opener', 'opening with the result'), ('life', 'no line about your life'),
                               ('meaning', 'a number without its meaning'), ('nocall', 'no call offer')):
                p.add_argument('--{}-ok'.format(flag), help="the owner's words allowing {} (science_email.py)".format(what))
            p.add_argument('--short-ok', help="the owner's words allowing a reply shorter than the reciprocate floor (reciprocate.py)")
            p.add_argument('--owner-wrote', help="the owner's words that they wrote this text themselves; it is then not held to the paper-cut or friend-email checks (friend_email.py)")
            p.add_argument('--requested', help='the recipient asked for this send, in their words; a reply, not outreach, so the daily limit does not hold it')
            p.add_argument('--target', action='append', default=[], help='OWNER/REPO the email is about; gated on rh bughunt target-check')
            p.add_argument('--target-override', help='why an unchecked or failing target is written about anyway (the recipient asked)')
            p.add_argument('--recheck', action='append', default=[], metavar='DIR', help='a re-check directory with a verdict file; extra-scrutiny contacts need two')
            p.add_argument('--asked-about', action='append', default=[], metavar='TERM',
                           help='an ops term the recipient raised themselves ({}); it drops to '
                                'a warning so a reply can answer them. A term from this list, '
                                'never their words.'.format(', '.join(ops_mentions.vocabulary())))
        elif action in ('lint', 'approve'):
            p.add_argument('id', nargs='?')
            p.add_argument('--batch')
            if action == 'lint':
                p.add_argument('--allow-collision')
            else:
                p.add_argument('--quote', required=True)
        else:
            p.add_argument('id')
            if action in ('sent', 'record-sent'):
                p.add_argument('--message-id', required=True)
                p.add_argument('--thread-id')
                p.add_argument('--via', required=True, choices=('api', 'browser'))
                if action == 'sent':
                    p.add_argument('--utc', help='when it actually went out, when that was before now')
                else:
                    p.add_argument('--utc', required=True, help='when it actually went out')
                    p.add_argument('--reason', required=True,
                                   help='why this is being recorded after the fact, in the '
                                        'operator\'s own words')
            elif action == 'reply':
                p.add_argument('--summary', required=True)
            else:
                p.add_argument('--reason', required=True)
                if action == 'drop':
                    p.add_argument('--purpose', help='replace the purpose (a hand-logged row whose purpose holds an address)')


def main(root, args, rh):
    root = root.expanduser().resolve()
    lane_name = getattr(args, 'lane', None)
    if lane_name and not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', lane_name):
        raise ValueError('invalid lane name')
    lane = root / 'lanes' / lane_name if lane_name else None
    if lane and not lane.is_dir():
        raise ValueError('lane directory missing')
    if args.action == 'contact':
        return contact_main(root, args)
    if args.action == 'stats':
        rows = list(current(lane, rh).values()) if lane else list(all_rows(root, rh))
        result = stats(rows, args.contact)
        if args.aggregate:
            result = result['total']
        if args.json or args.aggregate:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            total = result['total']
            print('total: {sent} sent, {replies} replies, rate {reply_rate}, {contacts} contacts'.format(**total))
            for kind, t in total['by_kind'].items():
                print('  {}: {} sent, {} replies'.format(kind, t['sent'], t['replies']))
            for name, t in result['contacts'].items():
                print('{}: {} sent, {} replies, last out {}, last in {}, ball {}'.format(
                    name, t['sent'], t['replies'], t['last_out'][:16], (t['last_in'] or '-')[:16], t['ball']))
        return 0
    if args.action in ('status', 'due'):
        selected = list(current(lane, rh).values()) if lane else list(all_rows(root, rh))
        if args.action == 'due':
            clock = time_of(rh.now())
            selected = [r for r in selected if r['status'] == 'sent' and r['channel'] not in X_PUBLIC and not r.get('reply') and
                        (args.all or time_of(r['follow_up_due']) < clock)]
        selected.sort(key=lambda r: (r['status'], r['lane'], r['id']))
        if args.json:
            print(json.dumps(selected, indent=2, ensure_ascii=False))
        else:
            for r in selected:
                print('{} {} {} {} {}{}'.format(r['status'], r['lane'], r['id'], r['to_name'], r['purpose'],
                      ' due=' + r['follow_up_due'] if r.get('follow_up_due') else ''))
        return 0
    with send_lock(root, args.action), rh.locked(lane):
        if args.action == 'draft':
            name = safe(args.to, 'recipient')
            key = contact_key(name) if args.channel == 'email' else name
            path = args.file.expanduser().resolve()
            if in_temp_dir(path):
                # 11-08: two sent drafts of 11-03 lived in a session scratchpad under /tmp; the
                # 11-07 reset emptied it, and every lint since warns that it cannot compare them.
                raise ValueError('the draft is in a temporary directory, which a restart empties and '
                                 'the ledger then loses its text; keep drafts in the lane\'s outbox')
            row = dict(id=uuid.uuid4().hex[:16], lane=lane.name, channel=args.channel, to_name=name, to_key=key,
                       purpose=safe(args.purpose, 'purpose'), draft_path=str(path), draft_sha256=sha(path),
                       status='drafted', created=rh.now())
            if args.channel not in X_PUBLIC and (args.in_reply_to or args.self_reply_to or args.media or args.credit or args.project):
                raise ValueError('X reach options require x_post or x_reply')
            if args.self_reply_to:
                if args.channel != 'x_post' or not args.self_reply_to.isdecimal() or args.in_reply_to:
                    raise ValueError('--self-reply-to requires x_post and a numeric own-post ID; do not combine with --in-reply-to')
                row['self_reply_to'] = args.self_reply_to
            if args.in_reply_to:
                if args.channel != 'x_reply' or not post_id(args.in_reply_to) or '://' not in args.in_reply_to:
                    raise ValueError('--in-reply-to requires x_reply and an X post URL')
                row['in_reply_to'] = args.in_reply_to
            if args.credit:
                if any(not re.fullmatch(r'@[A-Za-z0-9_]{1,15}', h) for h in args.credit):
                    raise ValueError('--credit must be @handle')
                row['credit'] = args.credit
            if args.media:
                row['media'] = [str(p.expanduser().resolve()) for p in args.media]
            if args.project:
                row['projects'] = [safe(p, 'project') for p in args.project]
            if args.batch:
                row['batch'] = safe(args.batch, 'batch')
            if args.attach:
                row['attachments'] = [str(Path(p).expanduser().resolve()) for p in args.attach]
            if args.claim:
                row['claims'] = [str(Path(c).expanduser().resolve()) for c in args.claim]
            if args.kind:
                kinds = list(dict.fromkeys(args.kind))
                row['kind'] = kinds[0]
                if len(kinds) > 1:
                    row['kinds'] = kinds
            if args.target:
                row['targets'] = sorted({bughunt.normalise(t) for t in args.target})
            if args.target_override:
                row['target_override'] = safe(args.target_override, 'target override')
            if args.recheck:
                row['rechecks'] = [str(Path(d).expanduser().resolve()) for d in args.recheck]
            if args.speedup:
                row['speedups'] = [str(Path(d).expanduser().resolve()) for d in args.speedup]
            if args.overlap_checked:
                row['overlap_checked'] = safe(args.overlap_checked, 'overlap check')
            if args.requested:
                row['requested'] = safe(args.requested, 'their request')
            if args.users_override:
                row['users_override'] = safe(args.users_override, 'users override')
            for flag in ('opener_ok', 'life_ok', 'meaning_ok', 'nocall_ok', 'short_ok', 'owner_wrote'):
                if getattr(args, flag, None):
                    row[flag] = safe(getattr(args, flag), flag.replace('_', ' '))
            if args.incoming:
                row['incoming'] = str(args.incoming.expanduser().resolve())
            if args.asked_about:
                # Only this module's own terms, so a typo cannot quietly turn the check off and
                # the ledger records our word for the subject, never the recipient's wording.
                terms = sorted({t.strip().casefold() for t in args.asked_about})
                if not set(terms) <= set(ops_mentions.vocabulary()):
                    raise ValueError('--asked-about takes one of: '
                                     + ', '.join(ops_mentions.vocabulary()))
                row['asked_about'] = terms
            record(lane, row, rh)
            print(row['id'])
            return 0
        have = current(lane, rh)
        if args.action == 'batch':
            key = contact_key(args.contact)
            row, originals = batch_draft(lane, rh, key, args.file)
            for old in originals:
                record(lane, dict(old, status='dropped', updated=rh.now(), reason='batched into ' + row['id']), rh)
            record(lane, row, rh)
            print(row['id'])
            print('  merged {} drafts into {}; edit it into one email, then lint'.format(len(originals), row['draft_path']))
            return 0
        if args.action == 'adopt':
            # 11-08: fifteen sends were appended to the ledger by hand, with sent_at and no status,
            # so counts, the daily limit and follow-ups never saw them. This makes such a row an
            # ordinary sent row. Bookkeeping like record-sent: no `approval` is added, so it can
            # never authorize a send.
            row = dict(have[args.id], updated=rh.now())
            if row.get('status') or row.get('sent') or not row.get('sent_at'):
                raise ValueError('adopt is for a hand-logged send: a row with sent_at and no status')
            sent_at = time_of(row['sent_at'])
            if sent_at > time_of(rh.now()):
                raise ValueError('sent_at is in the future')
            row.update(status='sent', kind=args.kind, created=row.get('created') or sent_at.isoformat(),
                       sent=dict(utc=sent_at.isoformat(), message_id=safe(args.message_id, 'message id'), via=args.via),
                       recorded_after_the_fact=dict(utc=rh.now(), reason=safe(args.reason, 'reason'),
                                                    adopted_from_hand_log=True),
                       follow_up_due=(sent_at + dt.timedelta(days=settings(lane, rh)['follow_up_days'])).isoformat())
            row.setdefault('to_name', row.get('to_key', ''))
            if args.purpose:
                row.update(purpose=safe(args.purpose, 'purpose'), purpose_replaced=rh.now())
            if row.get('draft_path') and Path(row['draft_path']).is_file():
                row['draft_sha256'] = sha(row['draft_path'])
            record(lane, row, rh)
            print('{} sent ({}, adopted)'.format(row['id'], row['kind']))
            return 0
        if args.action == 'set-kind':
            # Bookkeeping for counts, never a change to what was checked: an unsent draft's kind
            # decides which rules lint applies, so it is set at draft time and only there.
            row = dict(have[args.id], updated=rh.now())
            if not row.get('sent'):
                raise ValueError('set-kind is for emails that went out; draft an unsent one again with --kind')
            row['kind_set'] = dict(utc=rh.now(), was=row.get('kind'), reason=safe(args.reason, 'reason'))
            row['kind'] = args.kind
            row.pop('kinds', None)
            record(lane, row, rh)
            print('{} kind {}'.format(row['id'], row['kind']))
            return 0
        if args.action in ('bounce', 'review'):
            row = dict(have[args.id], updated=rh.now())
            if args.action == 'bounce':
                if row['channel'] != 'email' or not row.get('sent'):
                    raise ValueError('bounce is for an email that was sent')
                contacts_ledger.record_bounce(root, row['to_key'], rh.now(), args.address)
                row.update(status='bounced', bounce=dict(utc=rh.now()))
            else:
                row['text_review'] = dict(utc=rh.now(), by=safe(args.by, 'reviewer'), verdict=args.verdict,
                                          sha256=sha(row['draft_path']),
                                          notes=args.notes.strip()[:500])
            record(lane, row, rh)
            print('{} {}'.format(row['id'], row['status'] if args.action == 'bounce' else 'reviewed ' + args.verdict))
            return 0
        if args.action in ('lint', 'approve'):
            if bool(args.id) == bool(args.batch):
                raise ValueError('select exactly one ID or --batch')
            selected = [r for r in have.values() if r.get('batch') == args.batch] if args.batch else [have[args.id]]
            if not selected:
                raise ValueError('empty batch')
        else:
            selected = [have[args.id]]
        if args.action == 'lint':
            results = lint_rows(lane, selected, rh, args.allow_collision)
            for old in selected:
                row = dict(old, lint=results[old['id']])
                # Auditing historical sends must never turn them into sendable drafts.
                if row['status'] in ('drafted', 'linted', 'approved'):
                    row['status'] = 'linted' if row['lint']['ok'] else 'drafted'
                    row.pop('approval', None)
                    if row['lint'].get('sha256'):
                        row['draft_sha256'] = row['lint']['sha256']
                record(lane, row, rh)
                print('{} {} {}'.format('PASS' if row['lint']['ok'] else 'FAIL', row['id'], row['to_name']))
                for warning in row['lint'].get('warnings', []):
                    print('  WARN: ' + warning)
                for check, failures in row['lint']['checks'].items():
                    for failure in failures:
                        print('  {}: {}'.format(check, failure))
            return int(not all(r['ok'] for r in results.values()))
        # Validate the entire batch before appending any approval.
        for row in selected:
            if args.action == 'approve':
                if row['status'] != 'linted' or not row.get('lint', {}).get('ok'):
                    raise ValueError('approval requires linted PASS')
                if sha(row['draft_path']) != row['lint']['sha256']:
                    raise ValueError('draft changed since lint; run outreach lint again')
                safe(args.quote, 'approval quote')
                if args.quote == STANDING_APPROVAL and row['channel'] not in X_PUBLIC:
                    raise ValueError('standing approval is for public X posts/replies only; email and DMs need the owner\'s own words')
                cfg = settings(lane, rh)
                if (args.quote == STANDING_APPROVAL and row['channel'] == 'x_reply'
                        and cfg['x_reply_human_approval']):
                    # X removed 42,000 accounts that replied through chatbots with no human in
                    # the loop (2026-07-24). A standing approval is exactly that loop with no
                    # human in it, so replies need a person's approval of this round.
                    raise ValueError('x_reply needs a person to approve this round '
                                     '(x_reply_human_approval = true in OUTREACH.toml); a standing '
                                     'approval is no human in the loop')
                if row['channel'] in X_PUBLIC:
                    failures, _ = x_checks(row, body(row), list(all_rows(root, rh)), time_of(rh.now()), selected, cfg)
                    if failures:
                        raise ValueError('X reach changed; lint again: ' + '; '.join(failures))
            elif args.action == 'sent':
                if row['status'] != 'approved' or not row.get('approval'):
                    raise ValueError('sent requires approved draft')
                if sha(row['draft_path']) != row['approval']['sha256']:
                    raise ValueError('draft changed after approval; lint and obtain approval again')
                # Once the posting gate recorded an attempt, this is a receipt,
                # not another authorization. replied.json may already include it.
                if row['channel'] in X_PUBLIC and not row.get('gate_attempt'):
                    failures, _ = x_checks(row, body(row), list(all_rows(root, rh)), time_of(rh.now()),
                                           cfg=settings(lane, rh))
                    if failures:
                        raise ValueError('X reach changed before sent: ' + '; '.join(failures))
                if row['channel'] == 'email':
                    limit = settings(lane, rh)['emails_per_contact_per_day']
                    clock = time_of(args.utc) if args.utc else time_of(rh.now())
                    recent = [o for o in all_rows(root, rh) if o.get('channel') == 'email'
                              and o.get('to_key') == row.get('to_key') and o['id'] != row['id']
                              and bughunt.sent_at(o) and o.get('status') != 'bounced'
                              and abs(clock - bughunt.sent_at(o)) < dt.timedelta(hours=24)]
                    if limit and len(recent) >= limit and not row.get('requested'):
                        raise ValueError('DAILY_LIMIT: already {} email(s) to this contact within 24 h ({}); '
                                         'batch them'.format(len(recent), ', '.join(o['id'] for o in recent)))
                if row['channel'] not in X_PUBLIC and collisions(row, list(all_rows(root, rh)), time_of(rh.now())) and not row.get('lint', {}).get('allow_collision') and not row.get('requested'):
                    raise ValueError('recent contact collision; lint with --allow-collision and obtain approval again')
            elif args.action == 'record-sent':
                # A message that already left. Refusing to record it does not un-send it; it
                # only puts a hole in the ledger, and on 11-05 that cost a thread its record:
                # the reply had nothing to attach to, so the row had to be dropped. So lint
                # runs and is kept, but it does not block. This is bookkeeping, never
                # authorization: the row gets no `approval`, so the send hook, which matches
                # bytes against an approved entry only, can never authorize it.
                if row['status'] in ('sent', 'replied', 'closed'):
                    raise ValueError('already recorded as sent')
                if row['status'] == 'approved':
                    raise ValueError('this draft is approved; record it with `sent`')
            elif args.action == 'reply' and row['status'] != 'sent':
                raise ValueError('reply requires a sent message')
            elif args.action in ('close', 'drop') and row.get('status') in ('closed', 'dropped'):
                raise ValueError('message already closed or dropped')
        for old in selected:
            row = dict(old, updated=rh.now())
            if args.action == 'approve':
                row.update(status='approved', approval=dict(utc=rh.now(), by='owner (standing approval)' if args.quote == STANDING_APPROVAL else 'owner (relayed)', quote=args.quote,
                                                           sha256=sha(row['draft_path'])))
            elif args.action == 'sent':
                # A send recorded after the fact keeps its real time, so the follow-up falls
                # due from when the recipient got it rather than from the bookkeeping.
                sent_at = time_of(args.utc) if args.utc else time_of(rh.now())
                if sent_at > time_of(rh.now()):
                    raise ValueError('--utc is in the future')
                row.update(status='sent', sent=dict(utc=sent_at.isoformat(), message_id=safe(args.message_id, 'message id'), via=args.via),
                           follow_up_due=(sent_at + dt.timedelta(days=settings(lane, rh)['follow_up_days'])).isoformat())
                if args.thread_id:
                    row['sent']['thread_id'] = safe(args.thread_id, 'thread id')
            elif args.action == 'record-sent':
                sent_at = time_of(args.utc)
                if sent_at > time_of(rh.now()):
                    raise ValueError('--utc is in the future')
                result = lint_rows(lane, [row], rh)[row['id']]
                kept = ['{}: {}'.format(check, failure)
                        for check, failures in result['checks'].items() for failure in failures]
                row.update(status='sent',
                           sent=dict(utc=sent_at.isoformat(), message_id=safe(args.message_id, 'message id'), via=args.via),
                           recorded_after_the_fact=dict(utc=rh.now(), reason=safe(args.reason, 'reason'),
                                                        lint_ok=result['ok'], findings=kept),
                           follow_up_due=(sent_at + dt.timedelta(days=settings(lane, rh)['follow_up_days'])).isoformat())
                row.pop('approval', None)
                if args.thread_id:
                    row['sent']['thread_id'] = safe(args.thread_id, 'thread id')
            elif args.action == 'reply':
                summary = safe(args.summary, 'reply summary')
                if re.search(r'["“”«»]|^>|(?<!\w)\x27[^\x27\n]+\x27(?!\w)', summary):
                    raise ValueError('reply summary must paraphrase without quoted text')
                row.update(status='replied', reply=dict(utc=rh.now(), summary=summary))
            else:
                row.update(status='closed' if args.action == 'close' else 'dropped', reason=safe(args.reason, 'reason'))
                if getattr(args, 'purpose', None):
                    row.update(purpose=safe(args.purpose, 'purpose'), purpose_replaced=rh.now())
            record(lane, row, rh)
            print('{} {}'.format(row['id'], row['status']))
            if row['channel'] == 'email' and args.action in ('sent', 'record-sent', 'reply'):
                note_contact(root, row, args.action)
            if args.action == 'record-sent':
                for finding in row['recorded_after_the_fact']['findings']:
                    print('  WARN: went out before it was recorded: ' + finding)
    return 0


def contact_main(root, args):
    if args.contact_action == 'pending':
        print(json.dumps(contacts_ledger.pending(root), indent=1, ensure_ascii=False))
        return 0
    name = contacts_ledger.resolve(args.name)['name']
    now = dt.datetime.now(UTC).isoformat()
    if args.contact_action == 'show':
        print(json.dumps(contacts_ledger.merged(root, name), indent=1, ensure_ascii=False))
    elif args.contact_action == 'answered':
        contacts_ledger.append_event(root, dict(event='answered', name=name, utc=now,
                                                question=safe(args.question, 'question'),
                                                source=safe(args.source, 'source')))
        print('{}: {!r} answered'.format(name, args.question))
    elif args.contact_action == 'engagement':
        contacts_ledger.append_event(root, dict(event='engagement', name=name, utc=now,
                                                text=safe(args.text, 'engagement'), source=safe(args.source, 'source')))
        print('{}: engagement {!r}'.format(name, args.text))
    elif args.contact_action == 'scrutiny':
        contacts_ledger.append_event(root, dict(event='scrutiny', name=name, utc=now, level=args.level))
        print('{}: scrutiny {}'.format(name, args.level))
    elif args.contact_action == 'find':
        if args.record:
            found = contacts_ledger.find(name, args.url)
            sources = {c['address']: c['source'] for c in found['candidates']}
            for address in args.record:
                address = address.strip().casefold()
                if not contacts_ledger.EMAIL.fullmatch(address):
                    raise ValueError('not an address: ' + address)
                if address not in sources:
                    raise ValueError('{} was not found in the sources read; give the page it is on with --url'.format(address))
                contacts_ledger.append_event(root, dict(event='address', name=name, utc=now,
                                                        address=address, source=sources[address]))
                print('recorded {} ({})'.format(address, sources[address]))
            return 0
        print(json.dumps(contacts_ledger.find(name, args.url), indent=1, ensure_ascii=False))
    return 0
