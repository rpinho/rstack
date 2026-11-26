"""11-22 (Ricardo): "use the grades from the mini here as well... and vice versa... We just combine them together."
The two-way grades feed: ingest the other machine's snapshot, export this one's, rank on both."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gf = load('grades_feed', 'grades_feed.py')
mr = load('model_roles_feed', 'model-roles.py')
HEAD = '\t'.join(gf.COLUMNS)


def feed(*rows, machine='laptop'):
    return HEAD + '\n' + ''.join('\t'.join(('2026-11-20', machine) + r) + '\n' for r in rows)


def item(inbox, stamp, text, sender='laptop', kind='grades-feed'):
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / (stamp + '.md')).write_text('---\nfrom: {}\nto: mini\ntype: {}\nip_clean: yes\n---\n\n# feed\n'.format(sender, kind))
    (inbox / stamp).mkdir()
    (inbox / stamp / 'grades.tsv').write_text(text)


def test_free_text_unknown_columns_and_the_receivers_own_machine_are_refused(tmp_path):
    with pytest.raises(ValueError, match='header'):
        gf.parse(HEAD + '\tnote\n')
    with pytest.raises(ValueError, match='free text'):
        gf.parse(feed(('openai/gpt-6.2-astra', 'everyday', 'build', 'pass because it fixed the bug', '0')))
    with pytest.raises(ValueError, match='model'):
        gf.parse(feed(('fixed the login page', 'everyday', 'build', 'pass', '0')))
    inbox, store = tmp_path / 'inbox', tmp_path / 'store'
    item(inbox, '20261122-0100-grades-feed', feed(('openai/gpt-6.2-astra', 'everyday', 'build', 'pass', '0'), machine='mini'),
         sender='mini')
    item(inbox, '20261122-0200-grades-feed', feed(('openai/gpt-6.2-astra', 'everyday', 'build', 'pass', '0'), machine='mini'))
    report = gf.ingest(inbox, store, me='mini')
    assert all(line.startswith('REFUSED') for line in report) and len(report) == 2
    assert not store.exists() and (inbox / '20261122-0100-grades-feed.md').exists()   # left where it was


def test_a_newer_snapshot_replaces_the_older_and_the_item_is_filed(tmp_path):
    inbox, store = tmp_path / 'inbox', tmp_path / 'store'
    item(inbox, '20261122-0100-grades-feed', feed(*[('openai/gpt-6.2-astra', 'judge', 'review', 'pass', '0')] * 3))
    (inbox / 'other.md').write_text('---\nfrom: laptop\ntype: note\n---\n')
    assert gf.ingest(inbox, store)[0].startswith('ingested 20261122-0100-grades-feed.md: 3 rows from laptop')
    item(inbox, '20261123-0100-grades-feed', feed(('openai/gpt-6.2-astra', 'judge', 'review', 'fail', '0')))
    gf.ingest(inbox, store)
    assert len(gf.parse((store / 'laptop.tsv').read_text())) == 1                   # replaced, not appended
    assert sorted(p.name for p in (inbox / 'processed').iterdir()) == [
        '20261122-0100-grades-feed', '20261122-0100-grades-feed.md', '20261123-0100-grades-feed', '20261123-0100-grades-feed.md']
    assert (inbox / 'other.md').exists()                                             # not a feed: untouched


def test_a_laptop_feed_raises_the_combined_count_keeps_the_split_and_skips_unknown_ids(tmp_path, monkeypatch):
    ledger = tmp_path / 'ledger.jsonl'
    astra = 'openai/gpt-6.2-astra'
    rows = [mr.obs('receipt-everyday', 'job-%d' % i, astra, 'review', 'held', '2026-11-20', ['fixture'], 'everyday')
            for i in range(2)]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(mr, 'LEDGER', ledger)
    monkeypatch.delenv('RH_LAUNCH_RECEIPTS', raising=False)
    snap = tmp_path / 'laptop.tsv'
    snap.write_text(feed(*[('openai/gpt-6.2-astra', 'judge', '', 'pass', '0')] * 3,
                         ('openai/gpt-6.2-astra', 'everyday', 'review', 'partial', '0'),
                         ('openai/gpt-6.2-astra', 'everyday', 'review', 'fail', '1'),        # harness: never counts
                         ('openai/gpt-6.2-astra', 'judge', 'review', 'void', '0'),           # void: never counts
                         ('openai/gpt-6.2-astra', 'bench', 'chore', 'pass', '0'),            # bench: bench only
                         ('codex-chrome', 'everyday', 'build', 'pass', '0')))                # unknown id: skipped
    monkeypatch.setenv('MODEL_GRADES_FEED', str(snap))
    data = mr.recompute(write=False)
    row = data['evidence']['review']['gpt-6.2-astra']
    assert row['n'] == 6 and row['feed'] == {'laptop': {'n': 4, 'k': 3.5}}             # 2 here + 4 from the laptop
    assert row['rate'] == round(5.5 / 6, 3) and row['scored']
    assert data['bench']['mechanical']['gpt-6.2-astra']['n'] == 1
    assert data['feed_skipped'] == {'codex-chrome': 1}
    # The public routing snapshot uses the combined order; raw joined grades alone supply pass rates.
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    text = page.read_text()
    assert '| review | gpt-6.2-astra | ' in text
    assert '\n| gpt-6.2-astra |' not in text  # no raw run or grade in this fixture
    monkeypatch.setenv('MODEL_PUBLIC_FEED', '1')
    mr.public(data, page, previous=tmp_path / 'none.md')
    assert '\n| gpt-6.2-astra |' not in page.read_text()  # a feed cannot fabricate run-linked evidence


def test_a_model_graded_only_in_the_feed_has_no_public_row_and_never_stops_the_page(tmp_path):
    # 11-23: the laptop's API-route ids (google/gemini-4-neon) are not public models; the first scorer run with
    # the feed refused the whole page over them.
    data = {'updated': '2026-11-23T12:00:00Z', 'roles': {'builder': ['gpt-6.2-sol']},
            'evidence': {'builder': {'google/gemini-4-neon': {'n': 8, 'rate': 0.938, 'feed': {'laptop': {'n': 8, 'k': 7.5}}}}},
            'bench': {'mechanical': {'x-ai/grok-4.7': {'n': 16, 'rate': 0.969, 'feed': {'laptop': {'n': 16, 'k': 15.5}}}}}}
    page = tmp_path / 'LEADERBOARD.md'
    mr.public(data, page)
    assert 'gemini-4-neon |' not in page.read_text() and 'grok' not in page.read_text()
    data['evidence']['builder']['google/gemini-4-neon']['n'] = 9                 # one row of this machine's own
    with pytest.raises(ValueError, match='unknown public model'):
        mr.public(data, page)


def test_this_machines_rows_come_from_the_scorer_ledger_and_stage_as_an_item(tmp_path):
    ledger = tmp_path / 'ledger.jsonl'
    rows = [mr.obs('receipt-everyday', 'a', 'openai/gpt-6.2-sol', 'batch', 'held', '2026-11-21', ['x'], 'e'),
            mr.obs('receipt-everyday', 'b', 'openai/gpt-6.2-astra', 'review', 'overturned', '2026-11-21', ['x'], 'e'),
            dict(mr.obs('receipt-review', 'c', 'google/gemini-4-hydrogen-low', 'batch', 'held', '2026-11-21', ['x'], 'p'),
                 source='receipt-review'),
            mr.obs('receipt-everyday', 'd', 'openai/gpt-6.2-sol', 'batch', 'ungraded', '2026-11-21', ['x'], 'e')]
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    got = [(r['model'], r['task_class'], r['role'], r['verdict']) for r in gf.ledger_rows(ledger)]
    assert got == [('openai/gpt-6.2-sol', 'everyday', 'batch', 'pass'), ('openai/gpt-6.2-astra', 'judge', 'review', 'fail'),
                   ('google/gemini-4-hydrogen-low', 'bench', 'batch', 'pass'), ('openai/gpt-6.2-sol', 'everyday', 'batch', 'void')]
    tsv = tmp_path / 'mini.tsv'
    tsv.write_text(gf.tsv(gf.ledger_rows(ledger)))
    md = gf.stage(tsv, tmp_path / 'staging')
    head = gf.manifest(md)
    assert (head['from'], head['to'], head['type'], head['ip_clean']) == ('mini', 'laptop', 'grades-feed', 'yes')
    assert len(gf.parse((md.with_suffix('') / 'grades.tsv').read_text())) == 4
    assert gf.main(['rows', '--ledger', str(ledger)]) == 0



def test_the_daily_run_ingests_then_stages_and_sends_this_machines_snapshot(tmp_path):
    inbox, store, staging = tmp_path / 'inbox', tmp_path / 'store', tmp_path / 'staging'
    item(inbox, '20261122-1934-grades-feed', feed(('openai/gpt-6.2-astra', 'judge', 'review', 'pass', '0')))
    ledger = tmp_path / 'ledger.jsonl'
    ledger.write_text(json.dumps(mr.obs('receipt-everyday', 'a', 'openai/gpt-6.2-sol', 'batch', 'held', '2026-11-21', ['x'], 'e')) + '\n')
    sent = tmp_path / 'sent.txt'
    send = tmp_path / 'fake-send'
    send.write_text('#!/bin/sh\necho "$1" > ' + str(sent) + '\necho "handoff-send: moved into outbox"\n')
    send.chmod(0o755)
    report = gf.daily(inbox, store, ledger, staging, send=str(send))
    assert report[0].startswith('ingested 20261122-1934-grades-feed.md: 1 rows from laptop')
    assert report[1].startswith('staged ') and report[1].endswith('with 1 rows')
    assert report[2] == 'handoff-send: moved into outbox' and sent.read_text().strip().endswith('-grades-feed.md')
    assert not (staging / '.grades-feed.tsv').exists()
    assert 'not found' in gf.daily(inbox, store, ledger, staging, send=str(tmp_path / 'none'))[-1]
