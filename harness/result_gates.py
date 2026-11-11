"""What a lane counts as a result, read by log-result, outreach and lane-yield from one file.

Ricardo, 11-11, to the friends lane: "take their recent papers from 2025, 2026 and try to show something
new. It shouldn't be fixed. It shouldn't be a bug for the paper. It should be actually new science."
Then "potatoes hierarchy": code, not prose. A lane that sets lanes/<lane>/RESULT_GATES.json, e.g.

    {"paper_since": "2025-01-01", "novelty": ["new-science"]}

gets three refusals from it. log-result refuses a `--new yes` row whose novelty is not allowed or whose
source paper predates paper_since; outreach refuses a paper email whose claims do not carry an allowed
`Novelty:` and a `Paper date:` in the window; and lane-yield counts only allowed-novelty HOLDS as yield.
A lane without the file is unchanged.
"""
import datetime as dt
import json
from pathlib import Path
import re

FILE = 'RESULT_GATES.json'
NOVELTIES = ('new-science', 'repro', 'bug', 'tightening')


def load(lane_dir):
    """The lane's gates, or None when it has none. A malformed file raises: a gate that switches
    itself off on a typo is worse than no gate."""
    path = Path(lane_dir) / FILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    since = data.get('paper_since', '')
    allowed = data.get('novelty', [])
    if not isinstance(since, str) or (since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', since)):
        raise ValueError(FILE + ': paper_since must be "" or YYYY-MM-DD')
    if not isinstance(allowed, list) or any(n not in NOVELTIES for n in allowed):
        raise ValueError(FILE + ': novelty must be a list drawn from ' + ', '.join(NOVELTIES))
    return dict(paper_since=since, novelty=allowed)


def _field(text, name):
    m = re.search(rf'^\s*[-*]?\s*\**{name}\**\s*:\s*(.+)$', text, re.I | re.M)
    return m.group(1).strip() if m else None


def claim_fields(claim_dir):
    """(novelty, paper date) from a claim's CLAIM.md or RESULT.md `Novelty:` and `Paper date:` lines."""
    d = Path(claim_dir)
    doc = next((d / n for n in ('CLAIM.md', 'RESULT.md') if (d / n).is_file()), None)
    if doc is None:
        return None, None
    text = doc.read_text(errors='replace')
    novelty = (_field(text, 'Novelty') or '').split()
    date = re.search(r'\d{4}-\d{2}-\d{2}', _field(text, 'Paper date') or '')
    return (novelty[0].lower().strip('.,;:') if novelty else None), (date.group() if date else None)


def errors(gates, novelty, paper_date):
    """Why a result with this novelty and source-paper date does not count, or []."""
    if not gates:
        return []
    out = []
    if gates['novelty'] and novelty not in gates['novelty']:
        out.append('novelty is {}, and this lane counts only {} (Novelty: line in CLAIM.md or --novelty); '
                   'a reproduction, a bug or a tighter number is not new science'.format(
                       novelty or 'missing', ' or '.join(gates['novelty'])))
    if gates['paper_since']:
        try:
            ok = paper_date and dt.date.fromisoformat(paper_date) >= dt.date.fromisoformat(gates['paper_since'])
        except ValueError:
            ok = False
        if not ok:
            out.append('source paper date is {}, and this lane works only on papers from {} on '
                       '(Paper date: line in CLAIM.md or --paper-date)'.format(paper_date or 'missing',
                                                                               gates['paper_since']))
    return out


def counts(gates, row):
    """Whether a RESULTS.jsonl row counts as yield under the gates (always, without gates)."""
    if not gates:
        return True
    return not errors(gates, row.get('novelty'), row.get('paper_date'))
