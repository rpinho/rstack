"""New-lane safety boundaries without fabricated reading, trials or results."""
import datetime as dt
import json
from pathlib import Path
import sys

import pytest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
import rh
import lane_setup


def create(root, *extra):
    return rh.main(['--root', str(root), 'lane', 'new', 'sequence',
        '--problem', 'Predict the next integer', '--metric', 'exact-match accuracy',
        '--dev-set', 'public-dev', '--hidden-test', 'organizer-hidden',
        '--split', 'group', '--split-reason', 'Provisionally hold out sequence families; sampling unverified',
        '--sealed-set-id', 'organizer-fixed-hidden', '--deadline-days', '7',
        '--submissions', '2', '--submission-rules', 'Two uploads by deadline', *extra])


def lane(root):
    return root / 'lanes/sequence'


def test_create_is_honest_frozen_and_lint_clean(tmp_path):
    assert create(tmp_path) == 0
    target = lane(tmp_path)
    record, policy = lane_setup.read(target)
    assert policy['policy_version'] == 2 and policy['submissions'] == 2
    assert policy['sealed_budget'] == 1 and policy['n_trials_total'] == 0
    assert policy['split'] == 'group' and policy['trials'] == []
    assert (lane_setup.stamp(record['frozen']['deadline']) - lane_setup.stamp(record['created'])).days == 7
    assert record['frozen']['worker_sealed_access'] is False
    assert record['frozen']['public_board_selection'] is False
    assert not list(target.glob('*.jsonl'))
    assert rh.main(['--root', str(tmp_path), 'lint', 'sequence']) == 0
    assert create(tmp_path) == 2  # refuse overwriting the frozen lane


def test_random_requires_affirmative_shared_unit_statement(tmp_path):
    assert create(tmp_path, '--split', 'random') == 2
    assert not lane(tmp_path).exists()
    assert create(tmp_path, '--split', 'random', '--test-shares-units-statement',
                  'Organizer confirms unseen rows from the same generators') == 0


@pytest.mark.parametrize('filename,key,value', [
    ('SELECTION.json', 'submissions', 3),
    ('SELECTION.json', 'sealed_set_id', 'replacement-hidden'),
    ('LANE.json', 'bar', 'lowered after results'),
    ('LANE.json', 'worker_sealed_access', True),
])
def test_mutation_refuses_lint_and_dry_run(tmp_path, filename, key, value):
    assert create(tmp_path) == 0
    path = lane(tmp_path) / filename
    data = json.loads(path.read_text())
    (data['frozen'] if filename == 'LANE.json' else data)[key] = value
    path.write_text(json.dumps(data))
    assert rh.main(['--root', str(tmp_path), 'lint', 'sequence']) == 1
    assert rh.main(['--root', str(tmp_path), 'sweep', 'sequence', '--dry-run']) == 1


def test_preview_is_read_only_and_real_run_requires_enabling(tmp_path, capsys):
    assert create(tmp_path) == 0
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert rh.main(['--root', str(tmp_path), 'sweep', 'sequence', '--dry-run']) == 0
    text = capsys.readouterr().out
    assert 'DRY RUN' in text and 'stage. Run synchronously' in text
    assert 'search -> read -> kill' in text and 'No submissions' in text
    assert rh.main(['--root', str(tmp_path), 'sweep', 'sequence']) == 1
    assert 'workers disabled' in capsys.readouterr().err
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_setup_grace_expires_and_work_ends_it(tmp_path, monkeypatch):
    assert create(tmp_path) == 0
    target = lane(tmp_path)
    assert lane_setup.in_setup(target, rh)
    real_datetime = dt.datetime

    class Tomorrow(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + dt.timedelta(hours=25)

    monkeypatch.setattr(lane_setup.dt, 'datetime', Tomorrow)
    assert not lane_setup.in_setup(target, rh)
    result = rh.checked_lint(target)
    assert result['status'] == 'FAIL'
    assert {'queue-depth', 'external-reading', 'intake-freshness'} <= {x['check'] for x in result['failures']}
    monkeypatch.setattr(lane_setup.dt, 'datetime', real_datetime)
    rh.append(target / 'IDEAS.jsonl', dict(id='DEV-1', status='new', source_type='internal', created=rh.now()))
    assert not lane_setup.in_setup(target, rh)
    assert rh.checked_lint(target)['status'] == 'FAIL'


def test_lane_limits_and_new_experiments_cannot_downgrade_v2(tmp_path):
    assert create(tmp_path) == 0
    target = lane(tmp_path)
    rh.append(target / 'IDEAS.jsonl', dict(id='DEV-1', status='testing', policy_version=1))
    assert 'require v2' in ';'.join(lane_setup.audit(target, rh))
    path = target / 'INTAKE.toml'
    path.write_text(path.read_text().replace('selection_submissions = 2', 'selection_submissions = 3'))
    assert 'submissions' in ';'.join(lane_setup.audit(target, rh))


def test_new_lane_writes_overlap_receipt_from_the_prior_art_search(tmp_path, monkeypatch):
    # 11-19: lane creation asks whether anyone is already working on the problem, with the
    # same search an idea receipt uses. Stub the network under it; the receipt sits outside
    # the frozen files.
    import io, subprocess
    monkeypatch.delenv('RH_OVERLAP', raising=False)
    monkeypatch.setenv('RH_PAPER_CACHE', str(tmp_path / 'paper-cache'))
    search = lane_setup.prior_art()
    gh = subprocess.CompletedProcess([], 0, 'https://github.com/someone/next-int\tsomeone/next-int\t2026-11-01T00:00:00Z\n', '')
    monkeypatch.setattr(search, '_gh', lambda q, n: gh)
    def urlopen(req, timeout):
        url = req.full_url
        if 'api.openalex.org' in url:
            return io.StringIO(json.dumps({'results': [{'doi': 'https://doi.org/10.1/x', 'id': 'W1',
                'display_name': 'Integer sequence prediction', 'publication_date': '2024-03-02'}]}))
        if 'huggingface.co/api/spaces' in url:
            return io.StringIO(json.dumps([{'id': 'org/int-board', 'lastModified': '2026-10-30T12:00:00.000Z'}]))
        assert 'huggingface.co/api/datasets' in url
        return io.StringIO('[]')
    monkeypatch.setattr(search.urllib.request, 'urlopen', urlopen)
    assert create(tmp_path) == 0
    receipt = json.loads((lane(tmp_path) / 'OVERLAP.json').read_text())
    assert receipt['query'] == 'Predict the next integer' and receipt['status'] == 'hits' and receipt['searched_at']
    assert set(receipt['sources']) == {'github', 'papers', 'leaderboards'}
    assert receipt['sources']['github']['hits'] == [dict(title='someone/next-int', url='https://github.com/someone/next-int', date='2026-11-01')]
    assert receipt['sources']['papers']['hits'] == [dict(title='Integer sequence prediction', url='https://doi.org/10.1/x', date='2024-03-02')]
    assert dict(title='org/int-board', url='https://huggingface.co/spaces/org/int-board', date='2026-10-30') in receipt['sources']['leaderboards']['hits']
    record, policy = lane_setup.read(lane(tmp_path))
    assert 'overlap' not in json.dumps(record).lower() and 'overlap' not in json.dumps(policy).lower()
    assert rh.main(['--root', str(tmp_path), 'lint', 'sequence']) == 0


def test_new_lane_is_created_when_the_overlap_search_is_offline(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.delenv('RH_OVERLAP', raising=False)
    monkeypatch.setenv('RH_PAPER_CACHE', str(tmp_path / 'paper-cache'))
    search = lane_setup.prior_art()
    def offline(*args, **kwargs):
        raise urllib.error.URLError('offline')
    def no_gh(q, n):
        raise FileNotFoundError('gh')
    monkeypatch.setattr(search.urllib.request, 'urlopen', offline)
    monkeypatch.setattr(search, '_gh', no_gh)
    assert create(tmp_path) == 0
    receipt = json.loads((lane(tmp_path) / 'OVERLAP.json').read_text())
    assert receipt['status'] == 'unavailable'
    assert {v['status'] for v in receipt['sources'].values()} == {'unavailable'}
    assert all('offline' in v['reason'] for v in receipt['sources'].values())
    assert rh.main(['--root', str(tmp_path), 'lint', 'sequence']) == 0
    # A failure outside any one source (the search itself breaking) still leaves a lane.
    monkeypatch.setattr(search, 'overlap', Mock(side_effect=RuntimeError('broken search')))
    assert rh.main(['--root', str(tmp_path), 'lane', 'new', 'second', '--problem', 'Predict the next integer',
        '--metric', 'exact-match accuracy', '--dev-set', 'public-dev', '--hidden-test', 'organizer-hidden',
        '--split', 'group', '--split-reason', 'Provisional', '--sealed-set-id', 'organizer-fixed-hidden',
        '--deadline-days', '7', '--submissions', '2', '--submission-rules', 'Two uploads by deadline']) == 0
    receipt = json.loads((tmp_path / 'lanes/second/OVERLAP.json').read_text())
    assert receipt['status'] == 'unavailable' and 'broken search' in receipt['reason']
