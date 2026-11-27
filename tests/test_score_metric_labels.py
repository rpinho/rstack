"""Exercise the feed manifest and public score labels with the same verdicts."""
import datetime as dt
import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parents[1] / 'leaderboard'
sys.path.insert(0, str(HERE))
import grades_feed


def test_public_weighted_score_and_feed_verdict_tally_are_labeled(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('score_metric_roles', HERE / 'model-roles.py')
    roles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roles)
    import run_grades

    stamp = dt.datetime(2026, 11, 27, 12, tzinfo=dt.timezone.utc)
    model = 'gpt-6.2-sol'
    grades = ('pass', 'partial', 'fail')
    historical = [(dict(date='2026-11-26', model=model, role='batch', grade=grade), tmp_path, n)
                  for n, grade in enumerate(grades, 1)]
    monkeypatch.setattr(run_grades, 'table', lambda: ([], historical))
    monkeypatch.setattr(roles, 'now', lambda: stamp)
    page = tmp_path / 'LEADERBOARD.md'
    roles.public({'updated': stamp.isoformat(), 'roles': {'batch': [model]}}, page)
    rendered = page.read_text()
    assert 'Overall weighted score (Wilson 95%)' in rendered
    assert 'run start time when available' in rendered
    assert '2026-10-28 through 2026-11-27 (UTC)' in rendered   # dates only: a timestamp would change the page every run
    assert 'partial=half' in rendered and '50.0% [12.5%, 87.5%] (n=3)' in rendered

    tsv = tmp_path / 'rows.tsv'
    tsv.write_text(grades_feed.tsv([
        dict(date='2026-11-26', machine='mini', model=model, task_class='everyday', role='batch',
             verdict=grade, harness_fail='0') for grade in grades
    ]))
    manifest = grades_feed.stage(tsv, tmp_path, now=stamp)
    assert 'counts pass, partial and fail separately' in manifest.read_text()
    rows = grades_feed.parse((manifest.with_suffix('') / 'grades.tsv').read_text())
    assert [row['verdict'] for row in rows] == list(grades)
