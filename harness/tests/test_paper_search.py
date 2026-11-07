"""The shared paper chain: fallback order, the cache, and the quota lanes share.

Every network call is stubbed. What these lock down is the behaviour that was missing on 11-07,
when one lane spending OpenAlex's 1,000-a-day allowance locked every other lane out for ten hours:
a source that refuses is skipped rather than retried, a repeat lookup costs nothing, and a spent
budget is visible to the next process rather than discovered again by being rate-limited.
"""
import io
import json
import sys
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import paper_search as ps


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """A cache and buckets per test. Without this the tests would share the real cache and the
    second one to run would quietly pass on a cache hit."""
    monkeypatch.setenv('RH_PAPER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('RH_PAPER_CACHE_TTL_DAYS', '30')
    monkeypatch.delenv('RH_PAPER_CONTACT', raising=False)
    monkeypatch.delenv('RH_OPENALEX_KEY', raising=False)
    monkeypatch.delenv('RH_SEMANTIC_SCHOLAR_KEY', raising=False)
    monkeypatch.setattr(ps.urllib.request, 'urlopen',
                        lambda *a, **k: pytest.fail('unexpected network call'))


BODIES = {
    'api.openalex.org': {'results': [{'doi': 'https://doi.org/10.1/openalex', 'id': 'W1'}]},
    'api.semanticscholar.org': {'data': [{'paperId': 'p1', 'externalIds': {'DOI': '10.2/s2'}}]},
    'ebi.ac.uk': {'resultList': {'result': [{'doi': '10.3/epmc'}]}},
    'api.crossref.org': {'message': {'items': [{'DOI': '10.5/crossref'}]}},
}
ARXIV_FEED = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
              '<id>https://arxiv.org/abs/2501.00001v1</id></entry></feed>')


def stub(monkeypatch, fail=(), record=None):
    """urlopen that answers each source from BODIES, and raises for the hosts named in `fail`
    (host -> (code, retry-after))."""
    seen = record if record is not None else []

    def urlopen(req, timeout=None):
        url = req.full_url
        host = next(h for h in list(BODIES) + ['export.arxiv.org'] if h in url)
        seen.append(host)
        if host in fail:
            code, retry = fail[host]
            raise urllib.error.HTTPError(url, code, 'limited', {'retry-after': str(retry)}, None)
        if host == 'export.arxiv.org':
            return io.StringIO(ARXIV_FEED)
        return io.StringIO(json.dumps(BODIES[host]))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    return seen


def test_openalex_answers_first_and_no_other_source_is_touched(monkeypatch):
    seen = stub(monkeypatch)
    answer = ps.search('a harmless query', 3)
    assert answer.source == 'OpenAlex'
    assert answer.hits == ['https://doi.org/10.1/openalex']
    assert seen == ['api.openalex.org']


def test_the_daily_quota_falls_through_to_semantic_scholar_not_to_crossref(monkeypatch):
    # The old chain was OpenAlex then Crossref. Semantic Scholar now sits between them, so a
    # rate-limited OpenAlex costs one extra request, not the whole fallback chain.
    seen = stub(monkeypatch, fail={'api.openalex.org': (429, 37971)})
    answer = ps.search('a harmless query', 3)
    assert answer.source == 'Semantic Scholar'
    assert answer.hits == ['https://doi.org/10.2/s2']
    assert seen == ['api.openalex.org', 'api.semanticscholar.org']
    assert 'OpenAlex: HTTP 429, retry-after 37971s' in answer.note


@pytest.mark.parametrize('n_failing,source,host', [
    (2, 'Europe PMC', 'ebi.ac.uk'),
    (3, 'arXiv', 'export.arxiv.org'),
    (4, 'Crossref', 'api.crossref.org'),
])
def test_the_order_is_openalex_s2_europepmc_arxiv_then_crossref(monkeypatch, n_failing, source, host):
    hosts = ['api.openalex.org', 'api.semanticscholar.org', 'ebi.ac.uk', 'export.arxiv.org']
    seen = stub(monkeypatch, fail={h: (429, 100) for h in hosts[:n_failing]})
    answer = ps.search('a harmless query', 3)
    assert answer.source == source
    assert seen == hosts[:n_failing] + [host]


def test_a_source_that_answers_nothing_is_an_answer_not_a_failure(monkeypatch):
    monkeypatch.setitem(BODIES, 'api.openalex.org', {'results': []})
    seen = stub(monkeypatch)
    answer = ps.search('nothing matches this', 3)
    assert (answer.source, answer.hits) == ('OpenAlex', [])
    assert seen == ['api.openalex.org']  # no source after it is asked


def test_every_source_failing_raises_so_no_receipt_claims_an_empty_search(monkeypatch):
    hosts = ['api.openalex.org', 'api.semanticscholar.org', 'ebi.ac.uk', 'export.arxiv.org',
             'api.crossref.org']
    stub(monkeypatch, fail={h: (503, 0) for h in hosts})
    with pytest.raises(urllib.error.HTTPError):
        ps.search('a harmless query', 3)


def test_a_repeat_lookup_is_served_from_the_cache_and_spends_nothing(monkeypatch):
    seen = stub(monkeypatch)
    first = ps.search('the same query', 3)
    before = json.loads((ps.cache_dir() / 'bucket-openalex.json').read_text())['tokens']
    again = ps.search('the same query', 3)
    assert seen == ['api.openalex.org']            # no second request
    assert again.hits == first.hits
    assert again.source == 'OpenAlex'              # the source that answered is remembered
    assert 'cached' in again.note
    after = json.loads((ps.cache_dir() / 'bucket-openalex.json').read_text())['tokens']
    assert after >= before                         # a cache hit takes no token


def test_a_different_query_or_a_larger_n_is_a_different_lookup(monkeypatch):
    seen = stub(monkeypatch)
    ps.search('query one', 3)
    ps.search('query two', 3)
    ps.search('query one', 9)
    assert seen == ['api.openalex.org'] * 3


def test_the_cache_expires_after_its_ttl(monkeypatch):
    seen = stub(monkeypatch)
    now = time.time()
    ps.search('an old query', 3, now=now)
    ps.search('an old query', 3, now=now + 29 * ps.DAY)
    assert seen == ['api.openalex.org']
    ps.search('an old query', 3, now=now + 31 * ps.DAY)
    assert seen == ['api.openalex.org'] * 2


def test_a_budget_another_process_has_spent_skips_the_source(monkeypatch):
    # The bucket is a file, so this is exactly what a parallel job leaves behind. The point of
    # the shared bucket: the next lane reads it instead of learning the same 429 the hard way.
    ps.cache_dir().mkdir(parents=True, exist_ok=True)
    now = time.time()
    (ps.cache_dir() / 'bucket-openalex.json').write_text(json.dumps({'tokens': 0.0, 'at': now}))
    seen = stub(monkeypatch)
    answer = ps.search('a harmless query', 3, now=now)
    assert answer.source == 'Semantic Scholar'
    assert seen == ['api.semanticscholar.org']     # OpenAlex is not even asked
    assert 'OpenAlex: daily budget spent here, not asked' in answer.note


def test_the_budget_refills_over_time(monkeypatch):
    now = time.time()
    ps.cache_dir().mkdir(parents=True, exist_ok=True)
    (ps.cache_dir() / 'bucket-openalex.json').write_text(json.dumps({'tokens': 0.0, 'at': now}))
    rate, _ = ps.budget('openalex')
    assert not ps.take('openalex', now=now)
    assert ps.take('openalex', now=now + 1.0 / rate + 1)


def test_the_bucket_never_hands_out_more_than_the_burst(monkeypatch):
    now = time.time()
    rate, burst = ps.budget('openalex')
    taken = sum(1 for _ in range(int(burst) + 20) if ps.take('openalex', now=now))
    assert taken == int(burst)  # a year of idleness does not buy a year's requests at once


def test_a_corrupt_bucket_does_not_block_every_lookup(monkeypatch):
    ps.cache_dir().mkdir(parents=True, exist_ok=True)
    (ps.cache_dir() / 'bucket-openalex.json').write_text('not json')
    seen = stub(monkeypatch)
    assert ps.search('a harmless query', 3).source == 'OpenAlex'
    assert seen == ['api.openalex.org']


def test_the_polite_pool_address_is_sent_only_when_the_operator_sets_one(monkeypatch):
    urls = []

    def urlopen(req, timeout=None):
        urls.append((req.full_url, req.headers.get('User-agent', '')))
        return io.StringIO(json.dumps(BODIES['api.openalex.org']))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    ps.search('a harmless query', 3)
    assert 'mailto' not in urls[0][0] and 'mailto' not in urls[0][1]
    monkeypatch.setenv('RH_PAPER_CONTACT', 'papers@example.org')
    ps.search('another query', 3)
    assert 'mailto=papers%40example.org' in urls[1][0]
    assert 'mailto:papers@example.org' in urls[1][1]


def test_a_contact_that_is_not_an_address_is_refused(monkeypatch):
    monkeypatch.setenv('RH_PAPER_CONTACT', 'not an address')
    with pytest.raises(ValueError):
        ps.search('a harmless query', 3)


def test_an_api_key_is_sent_where_each_source_wants_it(monkeypatch):
    sent = []

    def urlopen(req, timeout=None):
        sent.append((req.full_url, dict(req.headers)))
        host = 'api.openalex.org' if 'openalex' in req.full_url else 'api.semanticscholar.org'
        if host == 'api.openalex.org':
            raise urllib.error.HTTPError(req.full_url, 429, 'limited', {'retry-after': '60'}, None)
        return io.StringIO(json.dumps(BODIES[host]))

    monkeypatch.setenv('RH_OPENALEX_KEY', 'oa-secret')
    monkeypatch.setenv('RH_SEMANTIC_SCHOLAR_KEY', 's2-secret')
    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    ps.search('a harmless query', 3)
    assert 'api_key=oa-secret' in sent[0][0]          # OpenAlex takes it as a parameter
    assert sent[1][1].get('X-api-key') == 's2-secret'  # Semantic Scholar as a header
    assert 's2-secret' not in sent[1][0]               # and never in the URL


def test_forward_citations_fall_back_to_semantic_scholar_with_its_own_ids(monkeypatch):
    calls = []

    def urlopen(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if 'openalex' in url:
            raise urllib.error.HTTPError(url, 429, 'limited', {'retry-after': '37971'}, None)
        if '/citations' in url:
            return io.StringIO(json.dumps({'data': [
                {'citingPaper': {'title': 'Newer', 'year': 2025, 'externalIds': {'DOI': '10.9/new'}}},
                {'citingPaper': {'title': 'Older', 'year': 2019, 'externalIds': {}}}]}))
        return io.StringIO(json.dumps({'paperId': 'p1', 'title': 'The paper', 'year': 2018,
                                       'externalIds': {'DOI': '10.1016/j.cor.2021.105357'},
                                       'citationCount': 7}))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    found = ps.work('10.1016/j.cor.2021.105357')
    assert found.source == 'Semantic Scholar'
    assert found.hits[0]['count'] == 7 and found.hits[0]['key'] == 'p1'
    cites = ps.citing(found.hits[0], found.source, 50)
    assert [c['year'] for c in cites.hits] == [2025, 2019]   # newest first
    assert 'DOI:10.1016/j.cor.2021.105357' in calls[1]                           # looked up by DOI, not by title


def test_citation_lists_get_a_shorter_ttl_than_searches(monkeypatch):
    # A keyword search going stale costs a repeated lookup. A stale citation list can hide the
    # paper that scooped the result last week, which is the only thing this check is for.
    assert ps.citing_ttl_seconds() < ps.ttl_seconds()
    monkeypatch.setenv('RH_PAPER_CITING_TTL_DAYS', '2')
    assert ps.citing_ttl_seconds() == 2 * ps.DAY


def test_a_rate_limited_citing_call_falls_back_to_the_doi(monkeypatch):
    # The first live smoke test on 11-07 died with a bare "HTTP Error 429": OpenAlex found the
    # paper and was then limited on the citing call, and that chain was one source long. Anything
    # that can be keyed by the DOI now stands behind it.
    def urlopen(req, timeout=None):
        url = req.full_url
        if 'opencitations.net' in url:
            assert '10.1016/j.cor.2021.105357' in url
            return io.StringIO(json.dumps([{'citing': '10.9/newer'}]))
        if 'filter=cites' in url:
            raise urllib.error.HTTPError(url, 429, 'limited', {}, None)
        return io.StringIO(json.dumps({'results': [{
            'id': 'https://openalex.org/W1', 'display_name': 'The paper', 'publication_year': 2021,
            'doi': 'https://doi.org/10.1016/j.cor.2021.105357', 'cited_by_count': 59}]}))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    found = ps.work('a paper by title')
    assert found.source == 'OpenAlex'
    cites = ps.citing(found.hits[0], found.source, 10)
    assert cites.source == 'OpenCitations'
    assert cites.hits == [{'title': '', 'year': None, 'doi': 'https://doi.org/10.9/newer'}]
    assert 'OpenAlex: HTTP 429' in cites.note


def test_the_raised_error_names_the_sources_that_were_asked(monkeypatch):
    hosts = ['api.openalex.org', 'api.semanticscholar.org', 'ebi.ac.uk', 'export.arxiv.org',
             'api.crossref.org']
    stub(monkeypatch, fail={h: (429, 0) for h in hosts})
    with pytest.raises(urllib.error.HTTPError) as caught:
        ps.search('a harmless query', 3)
    assert len(caught.value.tried) == 5
    assert 'OpenAlex: HTTP 429' in caught.value.tried[0]
