#!/usr/bin/env python3
"""cited-by: who has cited this paper since it came out? (forward-citation prior-art check)

A result on a 2018 paper is most likely to be scooped by a paper that cites it. Searching arXiv for keywords
misses those. This prints the paper's year, its citing-paper count and the citing titles (newest first), plus
a ready `Cited by:` line for CLAIM.md (result-lint requires it on NEW: yes claims).

    cited_by.py 10.1016/j.cor.2021.105357
    cited_by.py arXiv:2011.13478
    cited_by.py "Monotone Lagrangians in cotangent bundles of spheres"

Sources are OpenAlex then Semantic Scholar, through the shared cache and quota in
harness/paper_search.py, and the line records which one answered. Citation lists are cached for
seven days rather than thirty: a stale list can hide the paper that scooped the result last week.

Read the closest titles yourself; the count alone proves nothing. Exit 0 found, 1 not found, 2 network error.
"""
import argparse, datetime as dt, os, sys
from pathlib import Path

HARNESS = Path(os.environ.get('RH_HARNESS', str(Path(__file__).resolve().parents[2] / 'harness')))
sys.path.insert(0, str(HARNESS))
import paper_search


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('ref', help='DOI, arXiv id or title')
    p.add_argument('--limit', type=int, default=200)
    a = p.parse_args(argv)
    def failed(e):
        # Name the sources that were asked. "HTTP Error 429" alone sent me looking in the wrong
        # place on 11-07, when OpenAlex and keyless Semantic Scholar were both limited at once.
        tried = '; '.join(getattr(e, 'tried', []) or [])
        print(f'network error: {e}' + (f' (tried {tried})' if tried else ''), file=sys.stderr)
        return 2

    try:
        found = paper_search.work(a.ref)
    except Exception as e:
        return failed(e)
    if not found.hits:
        print(f'not found in {found.source}; do the forward-citation check by hand '
              '(Google Scholar "Cited by")')
        return 1
    w = found.hits[0]
    try:
        cites = paper_search.citing(w, found.source, a.limit)
    except Exception as e:
        return failed(e)
    print(f"{w['title']} ({w['year']}), cited by {w['count']}  [{found.source}]")
    for x in cites.hits:
        year = x['year'] if x['year'] is not None else '????'
        print(f"  {year}  {x['title'][:120] or x.get('doi') or ''}  {x.get('doi') or ''}".rstrip())
    if cites.hits and not any(x['title'] for x in cites.hits):
        print('  (this source gives citing DOIs without titles; open the closest few)')
    today = dt.date.today().isoformat()
    print(f"\nCited by: {w['count']} papers since {w['year']} "
          f"({found.source} {w['key']}, checked {today}); closest: <title, or none>")
    if cites.source != found.source:
        print(f"(citing list from {cites.source})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
