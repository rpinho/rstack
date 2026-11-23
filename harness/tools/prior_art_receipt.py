#!/usr/bin/env python3
"""Shared prior-art receipt generator.

Runs GitHub, papers (paper_search: OpenAlex, Semantic Scholar, Europe PMC, arXiv, then
Crossref, through one shared cache and quota), and leaderboard searches.
X uses only captured metadata from RH_XCAPTURE_ROOT/x_capture/KEY.jsonl.
Missing X captures are explicitly skipped. Paper source failures are recorded as
unavailable; promotion still requires a complete receipt.

The positional CLI is compatible with team_queue/pa_receipt.py callers:
  prior_art_receipt.py KEY PRIOR_ART_MD --baseline TEXT --query Q [--paper-query Q]
"""
import argparse, datetime as dt, hashlib, json, re, shutil, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_search

import os
Q = Path(os.environ.get('RH_XCAPTURE_ROOT', str(Path.cwd())))  # dir holding x_capture/<key>.jsonl
GH = os.environ.get('RH_GH', 'gh')
now = lambda: dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def get(url, tries=5):
    import time, urllib.error
    req = urllib.request.Request(url, headers={'User-Agent': 'research-harness-prior-art/1'})
    for k in range(tries):  # 11-03: back off on 429/5xx (OpenAlex / Hugging Face rate limits)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            ra = int(e.headers.get('retry-after') or 0) if e.headers else 0
            if e.code not in (429, 500, 502, 503, 504) or k == tries - 1 or ra > 300:
                raise  # a long retry-after (daily quota) means: use the fallback source now
            time.sleep(min(90, 10 * 2 ** k))


NO_GH = re.compile(r'gh auth login|not logged in|authentication|GH_TOKEN|GITHUB_TOKEN', re.I)


def github_public(q, n):
    """Repository search through GitHub's public API, no token (about 10 requests a minute)."""
    url = 'https://api.github.com/search/repositories?' + urllib.parse.urlencode({'q': q, 'per_page': n})
    return [paper_search._meta(item['html_url'], item.get('full_name'), item.get('pushed_at'))
            for item in get(url).get('items', []) if str(item.get('html_url', '')).startswith('http')]


def github(q, n=5, tries=4):
    import time
    # 11-09: on the m5 there was no gh at all, and every receipt (so every promotion) failed with
    # FileNotFoundError. A repository search needs no account, so a missing or signed-out gh falls back to
    # the public API rather than blocking; the results are the same search.
    try:
        out = _gh(q, n)
    except FileNotFoundError:
        return github_public(q, n)
    if out.returncode and NO_GH.search(out.stderr or ''):
        return github_public(q, n)
    for k in range(tries):  # search API allows ~30 requests/min; back off on rate limits
        if k:
            out = _gh(q, n)
        if out.returncode == 0 or k == tries - 1:
            break
        time.sleep(35)
    if out.returncode:
        raise RuntimeError('github search failed: ' + out.stderr[:200])
    for line in out.stdout.splitlines():  # url, name, last push
        cols = line.split('\t')
        if len(cols) == 3 and cols[0].startswith('http'):
            paper_search._meta(*cols)
    return [u for u in out.stdout.split() if u.startswith('http')]


def _gh(q, n):
    return subprocess.run([GH, 'api', '-X', 'GET', 'search/repositories', '-f', f'q={q}', '-f', f'per_page={n}',
                          '--jq', '.items[] | [.html_url, .full_name, .pushed_at] | @tsv'],
                          capture_output=True, text=True, timeout=60)


def boards(q, n=4):
    hits = []
    for kind in ('spaces', 'datasets'):
        d = get(f'https://huggingface.co/api/{kind}?limit={n}&search=' + urllib.parse.quote(q))
        hits += [paper_search._meta(f'https://huggingface.co/{kind}/{x["id"]}', x['id'], x.get('lastModified'))
                 for x in d]
    hits += github(q + ' benchmark', 3)
    return hits


def entry(query, hits, note, **extra):
    e = dict(status='hits' if hits else 'none', query=query, searched_at=now(), hits=sorted(set(hits)), note=note)
    e.update(extra)
    return e


def x_entry(key):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
        raise ValueError('KEY must be a single capture key (letters, numbers, _, . or -)')
    cap = Q / 'x_capture' / f'{key}.jsonl'
    if not cap.is_file() or not cap.read_text().strip():
        return dict(status='skipped', query=f'capture lookup for {key}', hits=[],
                    note=f'no capture for {key}: X skipped; capture {cap} in the browser before promotion')
    rows = [json.loads(l) for l in cap.read_text().splitlines() if l.strip()]
    stable = Q / 'x_capture' / 'frozen' / f'{key}_{hashlib.sha256(cap.read_bytes()).hexdigest()[:12]}.jsonl'
    stable.parent.mkdir(exist_ok=True)
    if not stable.exists():
        shutil.copyfile(cap, stable)
    queries = sorted({r['query'] for r in rows})
    hits = []
    for r in rows:
        if isinstance(r.get('posts'), list):
            # 11-09: a search row's source_url is the search itself; its posts are the hits. Three zero-post
            # searches were reported as "hits, 3 posts".
            for post in r['posts']:
                url = (post.get('url') or post.get('source_url') or post.get('link') or '') if isinstance(post, dict) else str(post)
                if url.startswith('http'):
                    hits.append(url)
        elif r.get('source_url', '').startswith('http'):
            hits.append(r['source_url'])
    when = max(r['captured_at'] for r in rows)
    e = entry('; '.join(queries), hits, f'Captured X search (browser, {when}) for key {key}; '
              f'{len(hits)} posts. Key-level capture; no new X search was performed.',
              capture_path=str(stable), capture_sha256=hashlib.sha256(stable.read_bytes()).hexdigest())
    e['searched_at'] = when
    return e


def overlap(query):
    """Lane overlap check: is anyone already working on this problem? The same GitHub, paper and
    leaderboard searches as an idea receipt, run once on the lane's problem statement. A source that
    fails is recorded as unavailable with its reason; this never raises for a failed search."""
    runs = (('github', lambda: github(query, 5, tries=1), 'GitHub repository search; date = last push.'),
            ('papers', lambda: paper_search.search(query), None),
            ('leaderboards', lambda: boards(query), 'Hugging Face spaces/datasets and GitHub "<q> benchmark" repos.'))
    sources = {}
    for name, run, note in runs:
        try:
            result = run()
        except Exception as exc:  # offline, rate-limited, signed out: record it, never block the lane
            sources[name] = dict(status='unavailable', reason=f'{type(exc).__name__}: {str(exc)[:200]}', hits=[])
            continue
        urls = result.hits if name == 'papers' else result
        hits = [dict(title=paper_search.META.get(u, {}).get('title'), url=u,
                     date=paper_search.META.get(u, {}).get('date')) for u in dict.fromkeys(urls)]
        source = dict(status='hits' if hits else 'none', hits=hits, note=note)
        if name == 'papers':
            source.update(status='hits' if hits else 'unavailable', source=result.source,
                          note=result.note, source_statuses=result.tried)
            if not hits:
                source['reason'] = result.note
        sources[name] = source
    states = {v['status'] for v in sources.values()}
    status = 'unavailable' if states == {'unavailable'} else 'hits' if 'hits' in states else 'none'
    return dict(schema=1, check='overlap', query=query, searched_at=now(), status=status, sources=sources)


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('key', metavar='KEY'); a.add_argument('md', metavar='PRIOR_ART_MD'); a.add_argument('--baseline', required=True)
    a.add_argument('--query', required=True); a.add_argument('--paper-query')
    a = a.parse_args(argv)
    if not a.baseline.strip() or not a.query.strip() or (a.paper_query is not None and not a.paper_query.strip()):
        raise ValueError('baseline and queries must be nonempty')
    md = Path(a.md).expanduser()
    x = x_entry(a.key)
    pq = a.paper_query or a.query
    gh = github(a.query); pp = paper_search.search(pq); lb = boards(a.query)
    receipt = dict(schema=1, baseline=a.baseline.strip(), sources=dict(
        github=entry(a.query, gh, f'GitHub repository search, top {len(gh)} by best match.'),
        x=x,
        papers=entry(pq, pp.hits, pp.note, status='hits' if pp.hits else 'unavailable',
                     source=pp.source, source_statuses=pp.tried),
        leaderboards=entry(a.query, lb, 'Hugging Face spaces/datasets search and GitHub "<q> benchmark" repos.')))
    text = md.read_text() if md.exists() else ''
    text = re.sub(r'^```rh-prior-art[^\S\n]*\n.*?^```[^\S\n]*(?:\n|$)', '\n', text, flags=re.M | re.S).rstrip()
    md.write_text(text + '\n\n```rh-prior-art\n' + json.dumps(receipt, indent=1) + '\n```\n')
    print(md, {k: v['status'] for k, v in receipt['sources'].items()})
    print('paper source:', pp.source or 'unavailable')
    print(pp.note)
    print('X:', x['note'])
    return 0


if __name__ == '__main__':
    main()
