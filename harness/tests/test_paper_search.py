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
import urllib.parse
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
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.delenv('RSTACK_ABLATE', raising=False)
    monkeypatch.delenv('RH_PAPER_CONTACT', raising=False)
    monkeypatch.setenv('RH_OPENALEX_KEY_FILE', str(tmp_path / 'openalex-key'))
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
    assert answer.tried == ['OpenAlex: unavailable: HTTP 429, Retry-After: 37971',
                            'Semantic Scholar: searched: 1 results']
    again = ps.search('a harmless query', 3)
    assert again.tried == answer.tried
    assert seen == ['api.openalex.org', 'api.semanticscholar.org']


def test_arxiv_uses_a_short_conjunction_for_a_question(monkeypatch):
    def urlopen(req, timeout):
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        assert params['search_query'] == [
            'all:"TESS" AND all:"transits" AND all:"Gaussian" AND all:"processes"']
        assert params['max_results'] == ['20']
        return io.StringIO(ARXIV_FEED)

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    question = 'Could TESS find transits with Gaussian processes and data from space?'
    answer = ps.search(question, 20, order=['arxiv'])
    assert answer.hits == ['https://arxiv.org/abs/2501.00001v1']


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


def test_an_empty_source_falls_through(monkeypatch):
    monkeypatch.setitem(BODIES, 'api.openalex.org', {'results': []})
    seen = stub(monkeypatch)
    answer = ps.search('nothing matches this', 3)
    assert answer.source == 'Semantic Scholar'
    assert answer.tried[0] == 'OpenAlex: unavailable: empty response'
    assert seen == ['api.openalex.org', 'api.semanticscholar.org']


def test_all_sources_unavailable_warns_and_returns_an_unavailable_answer(monkeypatch, capsys):
    def urlopen(req, timeout):
        host = urllib.parse.urlsplit(req.full_url).hostname
        if host == 'api.openalex.org':
            raise urllib.error.HTTPError(req.full_url, 429, 'limited',
                                         {'Retry-After': 'Mon, 23 Nov 2026 23:59:59 GMT'}, None)
        if host == 'export.arxiv.org':
            return io.StringIO('<feed xmlns="http://www.w3.org/2005/Atom"/>')
        return io.StringIO('not JSON')

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    # An old zero-hit cache entry must not mask the live source outcomes.
    ps.store('search', 'a harmless query', 3, 'arXiv', [])
    answer = ps.search('a harmless query', 3)
    assert (answer.source, answer.hits) == (None, [])
    assert answer.note.startswith('All paper sources unavailable.')
    assert 'OpenAlex: unavailable: HTTP 429, Retry-After: Mon, 23 Nov 2026 23:59:59 GMT' in answer.note
    assert 'arXiv: unavailable: empty response' in answer.note
    assert 'Crossref: unavailable: JSONDecodeError' in answer.note
    assert len(answer.tried) == 5
    row, = ps.harness_blocks.read()
    assert (row['gate'], row['class'], row['outcome']) == ('paper-search.unavailable', 'fail-open', 'warn')
    assert 'All paper sources unavailable' in row['reason']
    assert 'All paper sources unavailable' in capsys.readouterr().err


@pytest.mark.parametrize('legacy_cache', [False, True])
def test_openalex_search_preserves_metadata_in_the_shared_cache(monkeypatch, legacy_cache):
    query = 'a harmless query'
    doi = 'https://doi.org/10.1038/227680a0'
    work_id = 'https://openalex.org/W2100837269'
    other_id = 'https://openalex.org/W2138270253'
    title = 'Cleavage of Structural Proteins during the Assembly of the Head of Bacteriophage T4'
    monkeypatch.setattr(ps, 'META', {})
    monkeypatch.setitem(BODIES, 'api.openalex.org', {'results': [
        {'id': work_id, 'doi': doi, 'display_name': title,
         'publication_date': '1970-08-15', 'publication_year': 1970},
        {'id': other_id, 'doi': None, 'title': 'Title without a DOI', 'publication_year': 2024},
    ]})
    if legacy_cache:
        ps.store('search', query, 3, 'OpenAlex', [doi])
    seen = stub(monkeypatch)

    answer = ps.search(query, 3)
    assert answer.hits == [doi, other_id]
    assert ps.META[doi]['title'] == title
    monkeypatch.setattr(ps, 'META', {})  # simulate another process using the shared cache
    cached = ps.search(query, 3)
    assert cached.hits == answer.hits
    assert seen == ['api.openalex.org']
    assert ps.META[doi] == {'title': title, 'date': '1970-08-15', 'year': 1970,
                            'doi': doi, 'openalex_id': work_id}
    assert ps.META[other_id] == {'title': 'Title without a DOI', 'date': '2024', 'year': 2024,
                                 'doi': '', 'openalex_id': other_id}


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
    assert 'OpenAlex: unavailable: local request budget exhausted' in answer.note


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


def test_openalex_uses_the_generic_agent_and_crossref_can_use_contact(monkeypatch):
    urls = []

    def urlopen(req, timeout=None):
        urls.append((req.full_url, req.headers.get('User-agent', '')))
        host = urllib.parse.urlsplit(req.full_url).hostname
        return io.StringIO(json.dumps(BODIES[host]))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    monkeypatch.setenv('RH_PAPER_CONTACT', 'papers@example.org')
    ps.openalex('a harmless query', 3)
    ps.crossref('a harmless query', 3)
    assert 'mailto' not in urls[0][0]
    assert urls[0][1] == ps.AGENT
    assert 'mailto=papers%40example.org' in urls[1][0]
    assert 'mailto:papers@example.org' in urls[1][1]


def test_invalid_contact_marks_the_sources_unavailable(monkeypatch):
    stub(monkeypatch, fail={'api.openalex.org': (429, 60)})
    monkeypatch.setenv('RH_PAPER_CONTACT', 'not an address')
    answer = ps.search('a harmless query', 3)
    assert len(answer.tried) == 5
    assert 'OpenAlex: unavailable: HTTP 429' in answer.tried[0]
    assert all('unavailable: ValueError: RH_PAPER_CONTACT' in status for status in answer.tried[1:])


def test_openalex_rereads_its_key_file_at_request_time(monkeypatch, tmp_path):
    seen = []

    def urlopen(req, timeout=None):
        seen.append(req)
        return io.StringIO(json.dumps(BODIES['api.openalex.org']))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    key_file = tmp_path / 'openalex-key'
    for i, key in enumerate(('fake-openalex-first', 'fake-openalex-rotated')):
        key_file.write_text(f' \n{key}\t\n')
        if i == 1:
            assert 'cached' in ps.search('query 0', 3).note
        assert ps.search(f'query {i}', 3).source == 'OpenAlex'
        request = seen[i]
        assert request.get_header('Authorization') == f'Bearer {key}'
        assert 'Authorization' not in request.headers  # urllib does not forward it on redirects
        assert 'api_key' not in urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        assert key not in request.full_url
    assert len(seen) == 2


@pytest.mark.parametrize('unreadable', [False, True])
def test_openalex_requests_are_keyless_without_a_readable_key(monkeypatch, tmp_path, unreadable):
    if unreadable:
        (tmp_path / 'openalex-key').mkdir()
    seen = []

    def urlopen(req, timeout=None):
        seen.append(req.get_header('Authorization'))
        return io.StringIO(json.dumps(BODIES['api.openalex.org']))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    assert ps.search('a harmless query', 3).source == 'OpenAlex'
    assert seen == [None]


@pytest.mark.parametrize('code', [401, 403])
def test_openalex_retries_a_rejected_key_once_without_auth(monkeypatch, tmp_path, code):
    key = 'fake-openalex-rejected'
    (tmp_path / 'openalex-key').write_text(key)
    seen = []

    def urlopen(req, timeout=None):
        seen.append((req.full_url, req.get_header('Authorization')))
        if len(seen) == 1:
            raise urllib.error.HTTPError(req.full_url, code, 'rejected', {}, None)
        return io.StringIO(json.dumps(BODIES['api.openalex.org']))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    assert ps.search('a harmless query', 3).hits == ['https://doi.org/10.1/openalex']
    assert seen == [(seen[0][0], f'Bearer {key}'), (seen[0][0], None)]


def test_openalex_transport_exception_with_key_is_safe(monkeypatch, tmp_path, capsys):
    key = 'fake-openalex-echo'
    (tmp_path / 'openalex-key').write_text(key)

    def urlopen(req, timeout=None):
        raise ValueError(req.get_header('Authorization'))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    answer = ps.search('a harmless query', 3, order=['openalex'])
    assert answer.tried == ['OpenAlex: unavailable: ValueError']
    assert key not in answer.note + capsys.readouterr().err


def test_semantic_scholar_keeps_its_own_header_on_fallback(monkeypatch, tmp_path):
    sent = []

    def urlopen(req, timeout=None):
        sent.append((req.full_url, dict(req.header_items())))
        host = 'api.openalex.org' if 'openalex' in req.full_url else 'api.semanticscholar.org'
        if host == 'api.openalex.org':
            raise urllib.error.HTTPError(req.full_url, 429, 'limited', {'retry-after': '60'}, None)
        return io.StringIO(json.dumps(BODIES[host]))

    (tmp_path / 'openalex-key').write_text('fake-openalex-quota')
    monkeypatch.setenv('RH_SEMANTIC_SCHOLAR_KEY', 's2-secret')
    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    ps.search('a harmless query', 3)
    assert len(sent) == 2
    assert sent[0][1].get('Authorization') == 'Bearer fake-openalex-quota'
    assert sent[1][1].get('X-api-key') == 's2-secret'
    assert 'Authorization' not in sent[1][1]
    assert all('s2-secret' not in url for url, _ in sent)


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


@pytest.mark.parametrize('legacy_cache', [False, True])
def test_openalex_work_and_cited_by_accept_title_and_display_name(monkeypatch, legacy_cache):
    work_id = 'https://openalex.org/W1775749144'
    work_doi = 'https://doi.org/10.1016/s0021-9258(19)52451-6'
    citing_id = 'https://openalex.org/W2100837269'
    citing_doi = 'https://doi.org/10.1038/227680a0'
    other_id = 'https://openalex.org/W2138270253'
    if legacy_cache:
        ps.store('work', work_doi, 1, 'OpenAlex', [
            {'title': '', 'year': 1951, 'doi': work_doi, 'key': 'W1775749144', 'count': 2}])
        ps.store('citing', work_doi.removeprefix('https://doi.org/'), 5, 'OpenAlex', [
            {'title': '', 'year': 2024, 'doi': ''}])

    def urlopen(req, timeout=None):
        url = urllib.parse.urlsplit(req.full_url)
        assert url.hostname == 'api.openalex.org'
        if url.path.startswith('/works/doi:'):
            return io.StringIO(json.dumps({
                'id': work_id, 'doi': work_doi, 'title': 'Protein measurement',
                'publication_year': 1951, 'cited_by_count': 2}))
        params = urllib.parse.parse_qs(url.query)
        assert params['filter'] == ['cites:W1775749144']
        assert params['sort'] == ['publication_date:desc']
        fields = set(params['select'][0].split(','))
        works = [
            {'id': other_id, 'doi': None, 'title': 'Title only', 'publication_year': 2024},
            {'id': citing_id, 'doi': citing_doi, 'display_name': 'Display name only',
             'publication_year': 1970},
        ]
        return io.StringIO(json.dumps({'results': [
            {k: v for k, v in work.items() if k in fields} for work in works]}))

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    found = ps.work(work_doi)
    cited_by = ps.citing(found.hits[0], found.source, 5)
    assert cited_by.hits == [
        {'title': 'Title only', 'year': 2024, 'doi': '', 'openalex_id': other_id},
        {'title': 'Display name only', 'year': 1970, 'doi': citing_doi, 'openalex_id': citing_id},
    ]
    assert found.hits == [{'title': 'Protein measurement', 'year': 1951, 'doi': work_doi,
                           'openalex_id': work_id, 'key': 'W1775749144', 'count': 2}]


def test_openalex_work_and_citations_share_auth_and_fail_open(monkeypatch, tmp_path):
    key = 'fake-openalex-citations'
    (tmp_path / 'openalex-key').write_text(key)
    auth = []

    def urlopen(req, timeout=None):
        auth.append(req.get_header('Authorization'))
        if '/works/doi:' in req.full_url:
            return io.StringIO(json.dumps({'id': 'https://openalex.org/W1'}))
        assert 'filter=cites%3AW1' in req.full_url
        code = 401 if auth[-1] else 429
        raise urllib.error.HTTPError(req.full_url, code, 'rejected', {}, None)

    monkeypatch.setattr(ps.urllib.request, 'urlopen', urlopen)
    found = ps.work('10.1234/example')
    assert found.source == 'OpenAlex'
    cites = ps.citing(found.hits[0], found.source, 5)
    assert (cites.source, cites.hits) == (None, [])
    assert cites.tried == ['OpenAlex: unavailable: 401 key / 429 keyless']
    assert auth == [f'Bearer {key}', f'Bearer {key}', None]


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


def test_an_arxiv_atom_error_is_unavailable(monkeypatch):
    feed = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            '<id>http://arxiv.org/api/errors#bad_query</id><summary>bad query</summary></entry></feed>')
    monkeypatch.setattr(ps.urllib.request, 'urlopen', lambda *a, **k: io.StringIO(feed))
    answer = ps.search('a harmless query', order=['arxiv'])
    assert answer.hits == []
    assert answer.tried == ['arXiv: unavailable: ValueError: bad query']
