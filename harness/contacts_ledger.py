"""Contacts kept current: the private contacts file, plus what outreach has learned since.

The contacts file (RH_CONTACTS) stays the one record and this module never writes it. An
installation may keep that file in a repository whose changes land by review, so a send, a reply,
a bounce or a newly found address is appended to a private update ledger beside the harness root
(RH_CONTACT_UPDATES, mode 0600) and read over the file. `rh outreach contact pending` prints the
updates that are not yet in the file, so its owner can land them; once landed they change nothing.

Addresses are read from a row's `email` field and from free text in `channels`, where an address
followed by BOUNCED (before the next ';') is dead. Nothing here goes into a lane ledger: those
refuse address-shaped strings.

Finding an address (`contact find`) reads public sources only: OpenAlex for the person's recent
works and ORCID iD, ORCID's public record, and any page given with --url (a lab page, a
university profile). Each address is kept with the URL it came from and the date.
"""
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

import settings

EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}')
STAMP = re.compile(r'(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::\d{2})?Z?)?')
UTC = dt.timezone.utc
FIELDS_FROM_EVENTS = ('last_in', 'last_out', 'ball')
# 11-08, the owner: "treat people like they want to be treated." A contact's `engagement` field
# says, from their own words, how they prefer to be engaged. Someone who said "just send it" gets
# the thing, not a question about whether or in what form to send it.
JUST_SEND = re.compile(r"(?i)just send|no need to ask|don.t ask")
PERMISSION_ASK = re.compile(r"(?i)(do you want (me|us) to|would you like (me|us) to|want me to|"
                            r"should (i|we) (send|submit|open)|shall (i|we)|\bPR or (a )?patch\b|"
                            r"\bpatch or (a )?PR\b|let me know if you('d)? (want|like))")
USER_AGENT = 'research-harness contact finder (+https://github.com/rpinho/rstack)'


CONTACTS = settings.path('RH_CONTACTS', Path('.runtime/contacts.json'))


def contacts_path():
    return CONTACTS


def updates_path(root):
    return settings.path('RH_CONTACT_UPDATES', Path(root) / 'contact-updates.jsonl')


def base_rows():
    rows = json.loads(contacts_path().read_text())
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get('name') for r in rows):
        raise ValueError('contacts file must be an array of objects with a name')
    return rows


def resolve(name, rows=None):
    """The one row whose name matches exactly, or else contains NAME (case-insensitive)."""
    rows = base_rows() if rows is None else rows
    exact = [r for r in rows if r['name'].casefold() == name.casefold()]
    hits = exact or [r for r in rows if name.casefold() in r['name'].casefold()]
    if len(hits) != 1:
        raise ValueError('{} contacts match {!r}'.format(len(hits), name))
    return hits[0]


def events(root, name=None):
    path = updates_path(root)
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if name is None or r.get('name', '').casefold() == name.casefold()]


def append_event(root, event):
    path = updates_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'a') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    return event


def when(text):
    """The first date (and time) in a free-text field, as UTC, or None."""
    m = STAMP.search(text or '')
    if not m:
        return None
    try:
        return dt.datetime.fromisoformat(m[1] + 'T' + (m[2] or '00:00') + '+00:00')
    except ValueError:
        return None


def addresses(row):
    """[{address, status, source}] from the row's text fields, in the order they appear."""
    found = {}
    texts = [row.get('email') or ''] + (row.get('channels') or '').split(';')
    for text in texts:
        for m in EMAIL.finditer(text or ''):
            address = m.group().rstrip('.').casefold()
            dead = 'BOUNCED' in text[m.end():].upper()
            note = re.search(r'\(([^)]*)\)', text[m.end():])
            item = found.setdefault(address, dict(address=address, status='live',
                                                  source=note[1] if note else ''))
            if dead:
                item['status'] = 'bounced'
    return list(found.values())


def merged(root, name):
    """The contact row with every update newer than what the file already says."""
    row = dict(resolve(name))
    base_time = max([t for t in (when(row.get('last_in')), when(row.get('last_out'))) if t] or
                    [dt.datetime.min.replace(tzinfo=UTC)])
    book = {a['address']: a for a in addresses(row)}
    answered = dict(row.get('answered') or {})
    last_bounce, last_found = '', ''
    for event in events(root, row['name']):
        kind = event.get('event')
        if kind in ('sent', 'reply') and dt.datetime.fromisoformat(event['utc']) > base_time:
            row.update({k: event[k] for k in FIELDS_FROM_EVENTS if k in event})
        elif kind == 'address':
            item = book.setdefault(event['address'], dict(address=event['address'], status='live',
                                                          source=event.get('source', '')))
            item.update(status='live', source=event.get('source', ''), found=event.get('utc', '')[:10])
            last_found = max(last_found, event.get('utc', ''))
        elif kind == 'bounce':
            for address in event.get('addresses', []):
                book.setdefault(address, dict(address=address, source=''))['status'] = 'bounced'
            last_bounce = max(last_bounce, event.get('utc', ''))
        elif kind == 'answered':
            answered[event['question']] = event.get('source', '')
        elif kind == 'scrutiny':
            row['scrutiny'] = event['level']
        elif kind == 'engagement':
            row['engagement'] = event['text']
    row['addresses'] = list(book.values())
    row['answered'] = answered
    # A bounce queues a find; an address found after it answers the queue.
    row['needs_find'] = bool(last_bounce) and last_found <= last_bounce
    return row


def engagement_findings(contact, text):
    """(failures, notes): the contact's engagement preference, shown on every draft, and a
    permission or format question refused when they asked to just be sent things."""
    pref = (contact.get('engagement') or '').strip()
    if not pref:
        return [], []
    notes = ['engagement: ' + pref]
    ask = PERMISSION_ASK.search(text)
    if JUST_SEND.search(pref) and ask:
        return ['ENGAGEMENT: {} prefers "{}"; no permission or format questions, send the thing '
                '(matched "{}")'.format(contact['name'], pref[:80], ask.group(0))], notes
    return [], notes


def live_addresses(row):
    return [a['address'] for a in row.get('addresses', []) if a.get('status') == 'live']


def record_sent(root, name, utc, purpose, channel):
    return append_event(root, dict(event='sent', name=name, utc=utc, ball='them',
                                   last_out='{} {}: {}'.format(utc[:16] + 'Z', channel, purpose)))


def record_reply(root, name, utc, summary):
    return append_event(root, dict(event='reply', name=name, utc=utc, ball='us',
                                   last_in='{} reply: {}'.format(utc[:16] + 'Z', summary)))


def record_bounce(root, name, utc, address=None):
    """Mark ADDRESS (default: every live address) dead and queue a find."""
    row = merged(root, name)
    dead = [address.casefold()] if address else live_addresses(row)
    if not dead:
        raise ValueError('no live address on record for ' + row['name'])
    return append_event(root, dict(event='bounce', name=row['name'], utc=utc, addresses=dead))


def pending(root):
    """Updates the contacts file does not reflect yet, per contact, for its owner to land."""
    out = {}
    for name in sorted({e['name'] for e in events(root)}):
        try:
            base = resolve(name)
        except ValueError:
            out[name] = {'error': 'no longer in the contacts file'}
            continue
        now = merged(root, name)
        diff = {k: now[k] for k in FIELDS_FROM_EVENTS if now.get(k) != base.get(k)}
        base_book = {a['address']: a['status'] for a in addresses(base)}
        changed = [a for a in now['addresses'] if base_book.get(a['address']) != a['status']]
        if changed:
            diff['addresses'] = changed
        if now['answered'] != (base.get('answered') or {}):
            diff['answered'] = now['answered']
        if now.get('scrutiny') != base.get('scrutiny'):
            diff['scrutiny'] = now.get('scrutiny')
        if now.get('engagement') != base.get('engagement'):
            diff['engagement'] = now.get('engagement')
        if diff:
            out[name] = diff
    return out


# ---- finding an address -------------------------------------------------------------------

def fetch(url, accept='application/json', timeout=20):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': accept})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def page_addresses(text):
    text = html.unescape(urllib.parse.unquote(text))
    text = re.sub(r'\s*(?:\[at\]|\(at\)|\s+at\s+)\s*', '@', text, flags=re.I)
    text = re.sub(r'\s*(?:\[dot\]|\(dot\))\s*', '.', text, flags=re.I)
    return sorted({m.group().rstrip('.').casefold() for m in EMAIL.finditer(text)})


def plausible(address, name):
    """An address whose local part carries the person's family name or initials-and-name."""
    local = address.split('@')[0].replace('.', '').replace('-', '').replace('_', '')
    parts = [p.casefold() for p in re.findall(r'[^\W\d_]+', name) if len(p) > 1]
    return bool(parts) and (parts[-1] in local or any(p in local for p in parts if len(p) > 3))


def find(name, urls=(), get=None, today=None):
    """Candidate addresses and the sources read. Network only through `get` (default: fetch)."""
    get = get or fetch
    today = (today or dt.date.today()).isoformat()
    sources, candidates = [], {}

    def add(address, source):
        if address not in candidates:
            candidates[address] = dict(address=address, source=source, found=today,
                                       matches_name=plausible(address, name))

    try:
        authors = json.loads(get('https://api.openalex.org/authors?search=' +
                                 urllib.parse.quote(name) + '&per-page=3'))['results']
    except (OSError, ValueError, KeyError):
        authors = []
    for author in authors[:1]:
        institution = (author.get('last_known_institutions') or [{}])[0].get('display_name', '')
        sources.append(dict(kind='openalex', url=author.get('id', ''), name=author.get('display_name'),
                            institution=institution, works=author.get('works_count')))
        try:
            works = json.loads(get('https://api.openalex.org/works?filter=author.id:' +
                                   author['id'].rsplit('/', 1)[-1] +
                                   '&sort=publication_date:desc&per-page=5'))['results']
        except (OSError, ValueError, KeyError):
            works = []
        for work in works:
            sources.append(dict(kind='work', date=work.get('publication_date'),
                                title=work.get('display_name'), url=work.get('doi') or work.get('id')))
        orcid = (author.get('orcid') or '').rsplit('/', 1)[-1]
        if orcid:
            url = 'https://pub.orcid.org/v3.0/{}/email'.format(orcid)
            try:
                for item in json.loads(get(url)).get('email', []):
                    if EMAIL.fullmatch(item.get('email', '')):
                        add(item['email'].casefold(), url)
                sources.append(dict(kind='orcid', url=url))
            except (OSError, ValueError, AttributeError):
                sources.append(dict(kind='orcid', url=url, error='unreadable'))
    for url in urls:
        try:
            text = get(url, accept='text/html')
        except (OSError, ValueError) as error:
            sources.append(dict(kind='page', url=url, error=str(error)[:120]))
            continue
        sources.append(dict(kind='page', url=url))
        for address in page_addresses(text):
            add(address, url)
    ranked = sorted(candidates.values(), key=lambda c: (not c['matches_name'], c['address']))
    return dict(name=name, sources=sources, candidates=ranked)
