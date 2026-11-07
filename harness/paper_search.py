"""One paper search for every lane: polite sources, a shared cache, a shared quota.

11-07: lanes kept hitting paper-API rate limits. OpenAlex answers 429 with a retry-after of
about ten hours once the free daily allowance is gone, so the first lane to spend it locked
every other lane out until the next day, and `friends_tw_aires` alone logged hundreds of
lookups. Three things caused that, and this module fixes all three in one place rather than
per lane:

* **One source.** OpenAlex with Crossref behind it was the whole chain. Now OpenAlex,
  Semantic Scholar, Europe PMC and arXiv are tried in turn with Crossref last, and the
  answering source is returned so every receipt records which one answered.
* **No cache.** The same query was paid for again on every run. Lookups are now cached on
  disk by query, for 30 days by default.
* **No shared quota.** Parallel jobs each burned the full allowance. A token bucket per
  source now lives in the cache directory, so the lanes draw from one budget; when a
  source has no tokens left the search moves to the next source instead of waiting.

Keys are optional everywhere and are read from the host env file, never from a spec: with
no key at all the chain still works, because Europe PMC, arXiv and Crossref need none and
Semantic Scholar answers keyless at a low rate. `RH_PAPER_CONTACT` is the address sent to
OpenAlex's and Crossref's polite pools; it is deliberately unset by default, because a
contact address belongs to the operator and not to this repository.
"""
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:  # as a package (harness.paper_search) and as a loose module (tools/ scripts add harness/)
    from . import settings
except ImportError:  # pragma: no cover - exercised by the standalone tools
    import settings

AGENT = 'research-harness-paper-search/1'
DAY = 86400.0


def contact():
    """The address for OpenAlex's and Crossref's polite pools, or '' when the operator has
    not supplied one. Never defaulted to a person's address from this repository."""
    value = os.environ.get('RH_PAPER_CONTACT', '').strip()
    if value and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise ValueError('RH_PAPER_CONTACT: expected one email address')
    return value


def cache_dir():
    return settings.path('RH_PAPER_CACHE', Path('.runtime/paper-cache'))


def ttl_seconds():
    return float(os.environ.get('RH_PAPER_CACHE_TTL_DAYS', '30')) * DAY


# Sustained budget and burst per source. The rate spreads a daily allowance over the day, so
# a lane that wants sixty lookups at once gets its burst and then falls through to the next
# source rather than spending every other lane's day. Overridable per source: a paid OpenAlex
# or Semantic Scholar key raises the real limit, and only the operator knows which they have.
BUDGETS = {
    'openalex': (1000.0 / DAY, 50.0),        # free pool: 1,000/day, 429 + ~10 h retry-after
    'semanticscholar': (5000.0 / DAY, 10.0),  # keyless is a shared throttle; be modest
    'europepmc': (20000.0 / DAY, 20.0),       # no key, generous
    'arxiv': (1 / 3.0, 3.0),                  # their terms: one request every three seconds
    'crossref': (20000.0 / DAY, 20.0),        # polite pool with a mailto
    'opencitations': (10000.0 / DAY, 10.0),   # no key, no published limit; be modest anyway
}
ORDER = ['openalex', 'semanticscholar', 'europepmc', 'arxiv', 'crossref']


def budget(name):
    rate, burst = BUDGETS[name]
    rate = float(os.environ.get('RH_PAPER_%s_PER_DAY' % name.upper(), '') or rate * DAY) / DAY
    return rate, burst


def take(name, tokens=1.0, now=None):
    """Take one token from this source's shared bucket; False when the budget is spent.

    The bucket is a file in the cache directory, so every lane and every parallel job on the
    machine draws from the same budget. It is updated under an exclusive lock, because two
    jobs reading 1.0 and both writing 0.0 would double the real spend.
    """
    import fcntl
    rate, burst = budget(name)
    now = time.time() if now is None else now
    path = cache_dir() / ('bucket-%s.json' % name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            state = json.loads(fh.read() or '{}')
            have, when = float(state['tokens']), float(state['at'])
        except (ValueError, KeyError, TypeError):
            have, when = burst, now  # a corrupt or new bucket starts full, never empty
        have = min(burst, have + max(0.0, now - when) * rate)
        if have < tokens:
            allowed = False
        else:
            have, allowed = have - tokens, True
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({'tokens': round(have, 6), 'at': now}))
    return allowed


def _cache_path(kind, query, n):
    key = hashlib.sha256(('%s\n%s\n%d' % (kind, query, n)).encode()).hexdigest()[:40]
    return cache_dir() / ('%s-%s.json' % (kind, key))


def cached(kind, query, n, now=None):
    """The stored answer for this lookup, or None when absent or past its TTL."""
    now = time.time() if now is None else now
    try:
        row = json.loads(_cache_path(kind, query, n).read_text())
    except (OSError, ValueError):
        return None
    if now - float(row.get('at', 0)) > ttl_seconds():
        return None
    return row


def store(kind, query, n, source, hits, now=None):
    now = time.time() if now is None else now
    path = _cache_path(kind, query, n)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {'kind': kind, 'query': query, 'n': n, 'source': source, 'hits': hits,
           'at': now, 'fetched_utc': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat()}
    tmp = path.with_suffix('.tmp-%d' % os.getpid())
    tmp.write_text(json.dumps(row))
    os.replace(tmp, path)  # atomic: a reader never sees half a row
    return row


def get(url, headers=None, timeout=40, parse=json.load):
    head = {'User-Agent': AGENT + (' (mailto:%s)' % contact() if contact() else '')}
    head.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=timeout) as r:
        return parse(r)


def _polite(params):
    if contact():
        params['mailto'] = contact()
    return params


def _doi_url(doi):
    doi = (doi or '').strip()
    if not doi:
        return ''
    return doi if doi.startswith('http') else 'https://doi.org/' + doi.lstrip('/')


def openalex(query, n):
    params = _polite({'per-page': n, 'search': query})
    key = os.environ.get('RH_OPENALEX_KEY', '').strip()
    if key:
        params['api_key'] = key
    d = get('https://api.openalex.org/works?' + urllib.parse.urlencode(params))
    return [w.get('doi') or w['id'] for w in d['results']]


def semanticscholar(query, n):
    url = 'https://api.semanticscholar.org/graph/v1/paper/search?' + urllib.parse.urlencode(
        {'query': query, 'limit': n, 'fields': 'title,year,externalIds'})
    key = os.environ.get('RH_SEMANTIC_SCHOLAR_KEY', '').strip()
    d = get(url, headers={'x-api-key': key} if key else None)
    hits = []
    for p in d.get('data') or []:
        ids = p.get('externalIds') or {}
        if ids.get('DOI'):
            hits.append(_doi_url(ids['DOI']))
        elif ids.get('ArXiv'):
            hits.append('https://arxiv.org/abs/' + ids['ArXiv'])
        elif p.get('paperId'):
            hits.append('https://www.semanticscholar.org/paper/' + p['paperId'])
    return hits


def europepmc(query, n):
    d = get('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urllib.parse.urlencode(
        {'query': query, 'format': 'json', 'pageSize': n}))
    hits = []
    for r in (d.get('resultList') or {}).get('result') or []:
        if r.get('doi'):
            hits.append(_doi_url(r['doi']))
        elif r.get('id') and r.get('source'):
            hits.append('https://europepmc.org/article/%s/%s' % (r['source'], r['id']))
    return hits


def arxiv(query, n):
    import xml.etree.ElementTree as ET
    url = 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode(
        {'search_query': 'all:"%s"' % query.replace('"', ' '), 'max_results': n})
    feed = get(url, parse=lambda r: ET.fromstring(r.read()))
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    return [e.findtext('a:id', '', ns).strip() for e in feed.findall('a:entry', ns)
            if e.findtext('a:id', '', ns).strip()]


def crossref(query, n):
    params = _polite({'rows': n, 'query.bibliographic': query})
    d = get('https://api.crossref.org/works?' + urllib.parse.urlencode(params))
    return [_doi_url(w['DOI']) for w in d['message']['items'] if w.get('DOI')]


ADAPTERS = {'openalex': openalex, 'semanticscholar': semanticscholar, 'europepmc': europepmc,
            'arxiv': arxiv, 'crossref': crossref}
LABELS = {'openalex': 'OpenAlex', 'semanticscholar': 'Semantic Scholar',
          'europepmc': 'Europe PMC', 'arxiv': 'arXiv', 'crossref': 'Crossref',
          'opencitations': 'OpenCitations'}


class Answer(object):
    """What a lookup returned, and which source returned it. `source` goes in the receipt."""

    def __init__(self, hits, source, note, tried=()):
        self.hits, self.source, self.note, self.tried = hits, source, note, list(tried)

    def __repr__(self):
        return 'Answer(%r, %r)' % (self.source, self.hits)


def search(query, n=6, order=None, kind='search', now=None):
    """Hits for a free-text query, from the first source that answers.

    A cache hit costs nothing and spends no token. A source with no tokens left, or one that
    rate-limits or fails, is recorded in the note and the next source is tried. When every
    source fails the last error is raised, because a failed search must not produce a receipt
    that looks like a search finding nothing.
    """
    row = cached(kind, query, n, now=now)
    if row is not None:
        return Answer(row['hits'], row['source'],
                      'cached %s answer from %s, fetched %s (TTL %d days)' % (
                          kind, row['source'], row.get('fetched_utc', '?'),
                          int(ttl_seconds() / DAY)))
    tried, error = [], None
    for name in (order or ORDER):
        if not take(name, now=now):
            tried.append('%s: daily budget spent here, not asked' % LABELS[name])
            continue
        try:
            hits = [h for h in ADAPTERS[name](query, n) if h]
        except urllib.error.HTTPError as e:
            retry = int((e.headers or {}).get('retry-after') or 0)
            tried.append('%s: HTTP %d%s' % (LABELS[name], e.code,
                                            ', retry-after %ds' % retry if retry else ''))
            error = e
            continue
        except Exception as e:  # a parse error or a connection failure is also just a miss
            tried.append('%s: %s' % (LABELS[name], str(e)[:120] or type(e).__name__))
            error = e
            continue
        store(kind, query, n, LABELS[name], hits, now=now)
        note = '%s relevance search, top %d' % (LABELS[name], len(hits))
        if tried:
            note += ' (after %s)' % '; '.join(tried)
        return Answer(hits, LABELS[name], note, tried)
    if error is not None:
        error.tried = tried
        raise error
    raise RuntimeError('no paper source was asked: ' + '; '.join(tried))


# --- forward citations -------------------------------------------------------------------
# `cited-by` asks a different question from a keyword search: who has cited this paper since
# it came out. Only some sources can answer it, so the chain here is OpenAlex then Semantic
# Scholar, and the answering source is reported the same way.
CITING_ORDER = ['openalex', 'semanticscholar', 'crossref']


def citing_ttl_seconds():
    """Citation lists get a shorter TTL than searches (7 days, not 30). A keyword search going
    a month stale costs a repeated lookup; a stale citation list can hide the paper that
    scooped the result last week, which is the one thing this check exists to catch."""
    return float(os.environ.get('RH_PAPER_CITING_TTL_DAYS', '7')) * DAY


def _oa_work(ref, n=1):
    doi = re.search(r'(10\.\d{4,9}/\S+)', ref)
    if doi:
        w = get('https://api.openalex.org/works/doi:' + doi.group(1))
    else:
        arx = re.search(r'(\d{4}\.\d{4,5})', ref)
        w = None
        if arx and re.search(r'arxiv', ref, re.I):
            try:
                w = get('https://api.openalex.org/works/doi:10.48550/arXiv.' + arx.group(1))
            except urllib.error.HTTPError:
                w = None
        if w is None:
            found = get('https://api.openalex.org/works?' + urllib.parse.urlencode(
                _polite({'search': ref, 'per-page': 1})))['results']
            if not found:
                return []
            w = found[0]
    return [{'title': w.get('display_name') or '', 'year': w.get('publication_year'),
             'doi': _doi_url(w.get('doi')), 'key': w['id'].rsplit('/', 1)[-1],
             'count': w.get('cited_by_count')}]


def _s2_work(ref, n=1):
    fields = 'title,year,externalIds,citationCount'
    doi = re.search(r'(10\.\d{4,9}/\S+)', ref)
    arx = re.search(r'(\d{4}\.\d{4,5})', ref)
    if doi:
        ident = 'DOI:' + doi.group(1)
    elif arx and re.search(r'arxiv', ref, re.I):
        ident = 'arXiv:' + arx.group(1)
    else:
        ident = None
    key = os.environ.get('RH_SEMANTIC_SCHOLAR_KEY', '').strip()
    head = {'x-api-key': key} if key else None
    if ident:
        p = get('https://api.semanticscholar.org/graph/v1/paper/%s?fields=%s' % (ident, fields),
                headers=head)
    else:
        found = get('https://api.semanticscholar.org/graph/v1/paper/search?' +
                    urllib.parse.urlencode({'query': ref, 'limit': 1, 'fields': fields}),
                    headers=head).get('data') or []
        if not found:
            return []
        p = found[0]
    ids = p.get('externalIds') or {}
    return [{'title': p.get('title') or '', 'year': p.get('year'),
             'doi': _doi_url(ids.get('DOI')), 'key': p['paperId'],
             'count': p.get('citationCount')}]


def _oa_citing(key, limit):
    d = get('https://api.openalex.org/works?' + urllib.parse.urlencode(_polite(
        {'filter': 'cites:' + key, 'per-page': limit, 'sort': 'publication_date:desc',
         'select': 'display_name,publication_year,doi'})))
    return [{'title': w.get('display_name') or '', 'year': w.get('publication_year'),
             'doi': _doi_url(w.get('doi'))} for w in d['results']]


def _s2_citing(key, limit):
    sskey = os.environ.get('RH_SEMANTIC_SCHOLAR_KEY', '').strip()
    d = get('https://api.semanticscholar.org/graph/v1/paper/%s/citations?' % key +
            urllib.parse.urlencode({'limit': min(1000, limit), 'fields': 'title,year,externalIds'}),
            headers={'x-api-key': sskey} if sskey else None)
    rows = []
    for row in d.get('data') or []:
        p = row.get('citingPaper') or {}
        rows.append({'title': p.get('title') or '', 'year': p.get('year'),
                     'doi': _doi_url((p.get('externalIds') or {}).get('DOI'))})
    rows.sort(key=lambda r: (r['year'] is None, -(r['year'] or 0)))
    return rows


def _chain(kind, query, n, adapters, ttl, now=None):
    """The search() loop, reused for the citation lookups: cache, shared bucket, next source."""
    row = cached(kind, query, n, now=now)
    if row is not None and (time.time() if now is None else now) - float(row['at']) <= ttl:
        return Answer(row['hits'], row['source'], 'cached %s from %s (%s)' % (
            kind, row['source'], row.get('fetched_utc', '?')))
    tried, error = [], None
    for name, call in adapters:
        if not take(name, now=now):
            tried.append('%s: daily budget spent here, not asked' % LABELS[name])
            continue
        try:
            hits = call()
        except urllib.error.HTTPError as e:
            tried.append('%s: HTTP %d' % (LABELS[name], e.code)); error = e; continue
        except Exception as e:
            tried.append('%s: %s' % (LABELS[name], str(e)[:120] or type(e).__name__)); error = e; continue
        store(kind, query, n, LABELS[name], hits, now=now)
        note = LABELS[name] + (' (after %s)' % '; '.join(tried) if tried else '')
        return Answer(hits, LABELS[name], note, tried)
    if error is not None:
        error.tried = tried  # a bare 'HTTP Error 429' hides which sources were asked and why
        raise error
    raise RuntimeError('no citation source was asked: ' + '; '.join(tried))


def work(ref, now=None):
    """Find one paper by DOI, arXiv id or title. `hits` holds zero or one normalized paper."""
    adapters = {'openalex': lambda: _oa_work(ref), 'semanticscholar': lambda: _s2_work(ref),
                'crossref': lambda: _cr_work(ref)}
    return _chain('work', ref, 1, [(n, adapters[n]) for n in CITING_ORDER], ttl_seconds(), now=now)


def citing(paper, source, limit=200, now=None):
    """Papers citing this one, newest first. `source` is the label that found it, because a
    Semantic Scholar paper id is not an OpenAlex work id; the chain starts at that source."""
    name = {v: k for k, v in LABELS.items()}[source]
    doi = re.sub(r'^https?://doi\.org/', '', paper.get('doi') or '')
    # The source that found the paper goes first, because it holds the richest list. Then anything
    # else that can be keyed by the DOI: on 11-07 the first smoke test failed with a bare
    # "HTTP Error 429" because this chain was one source long, so a rate limit on the citing call
    # had no fallback even though the DOI was already in hand.
    steps = []
    if name == 'openalex':
        steps.append(('openalex', lambda: _oa_citing(paper['key'], limit)))
    elif name == 'semanticscholar':
        steps.append(('semanticscholar', lambda: _s2_citing(paper['key'], limit)))
    if doi:
        steps.append(('opencitations', lambda: _oc_citing(doi, limit)))
        if name != 'semanticscholar':
            steps.append(('semanticscholar', lambda: _s2_citing('DOI:' + doi, limit)))
    if not steps:
        raise ValueError('no forward-citation source can be keyed for a paper from ' + source)
    # Keyed by DOI where there is one, so the same paper found through a different source reuses
    # the cached list. The stored row records which source answered.
    return _chain('citing', doi or '%s:%s' % (name, paper['key']), limit, steps,
                  citing_ttl_seconds(), now=now)


def _cr_work(ref, n=1):
    """Crossref as a third way to resolve a paper, so the forward-citation check still works when
    OpenAlex and Semantic Scholar are both rate-limited, which on 11-07 they both were. The key is
    the DOI itself, which is what OpenCitations takes."""
    doi = re.search(r'(10\.\d{4,9}/\S+)', ref)
    if doi:
        w = get('https://api.crossref.org/works/' + urllib.parse.quote(doi.group(1)))['message']
    else:
        found = get('https://api.crossref.org/works?' + urllib.parse.urlencode(
            _polite({'rows': 1, 'query.bibliographic': ref})))['message']['items']
        if not found:
            return []
        w = found[0]
    year = ((w.get('issued') or {}).get('date-parts') or [[None]])[0][0]
    return [{'title': (w.get('title') or [''])[0], 'year': year, 'doi': _doi_url(w.get('DOI')),
             'key': w.get('DOI') or '', 'count': w.get('is-referenced-by-count')}]


def _oc_citing(doi, limit):
    """OpenCitations gives citing DOIs with no titles or years. A DOI list is worse than a title
    list for reading the closest work, and it is far better than no forward-citation check at all,
    so the caller is told the titles are missing rather than shown blanks."""
    rows = get('https://opencitations.net/index/api/v1/citations/' + urllib.parse.quote(doi))
    out = []
    for row in rows[:limit]:
        citing = (row.get('citing') or '').strip()
        if citing:
            out.append({'title': '', 'year': None, 'doi': _doi_url(citing)})
    return out
