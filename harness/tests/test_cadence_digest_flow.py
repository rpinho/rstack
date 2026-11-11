"""rh lanes cadence reports the digest -> lane loop (11-11: a week of digest ideas reached no live lane)."""
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cadence

NOW = dt.datetime(2026, 11, 11, 12, 0, tzinfo=dt.timezone.utc)


def write(lane, rows):
    lane.mkdir(parents=True, exist_ok=True)
    (lane / 'IDEAS.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


def idea(i, day, session='digest', status='new', event=None, claim='c'):
    return dict(id=i, created='2026-11-{:02d}T10:00:00+00:00'.format(day), session=session, status=status,
                event=event, claim=claim)


def test_counts_queued_started_and_verdicts_and_names_the_newest_unrun(tmp_path):
    lane = tmp_path / 'math'
    write(lane, [
        idea('old', 1),                                   # outside the window, still waiting
        idea('a', 9, claim='teams of ten agents'),        # waiting
        idea('b', 10), dict(idea('b', 10), status='testing', event='promote'),
        idea('c', 10), dict(idea('c', 10), status='closed', event='close'),
        idea('sweep', 11, session='sweep'),               # not from the digest
        idea('d', 11, claim='newest waiting idea'),
    ])
    flow = cadence.digest_flow(lane, NOW)
    assert (flow['queued'], flow['started'], flow['verdicts'], flow['unrun']) == (4, 2, 1, 3)
    assert flow['newest_unrun']['id'] == 'd' and flow['newest_unrun']['claim'] == 'newest waiting idea'


def test_no_ledger_is_none_and_no_digest_ideas_is_zero(tmp_path):
    assert cadence.digest_flow(tmp_path / 'none', NOW) is None
    write(tmp_path / 'p', [idea('x', 10, session='sweep')])
    flow = cadence.digest_flow(tmp_path / 'p', NOW)
    assert (flow['queued'], flow['unrun'], flow['newest_unrun']) == (0, 0, None)
