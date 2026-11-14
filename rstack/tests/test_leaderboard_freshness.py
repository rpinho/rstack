"""Freshness checks and alerts use fixture leaderboards, receipts and executables."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

TOOL = Path(__file__).resolve().parents[1] / 'tools/leaderboard-freshness'


def board(path, models=('gpt-6-astra',), age=0):
    day = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=age)).date()
    path.write_text('| Role | Model | Date |\n|---|---|---|\n' + ''.join(
        '| review | {} | {} |\n'.format(m, day) for m in models))
    return path


def run(path, *args, env=None):
    return subprocess.run([sys.executable, str(TOOL), str(path), *map(str, args)],
                          env=env, capture_output=True, text=True, timeout=10)


def test_used_model_must_have_a_role_row_and_ids_are_normalised(tmp_path):
    path = board(tmp_path / 'LEADERBOARD.md')
    used = tmp_path / 'used'
    used.write_text('claude-fable-5-2\n')
    result = run(path, '--used', used)
    assert result.returncode == 1 and 'claude-fable-5-2 is on no role row' in result.stdout
    board(path, models=('gpt-6-astra', 'anthropic/claude-fable-5.2'))
    assert run(path, '--used', used).returncode == 0


def test_old_date_fails_and_newest_table_date_is_used(tmp_path):
    path = board(tmp_path / 'LEADERBOARD.md', age=3)
    assert 'older than 2 days' in run(path).stdout
    assert run(path).returncode == 1
    assert run(path, '--max-age-days', '3').returncode == 0
    today = dt.datetime.now(dt.timezone.utc).date()
    with path.open('a') as stream:
        stream.write('\n| Note | Date |\n|---|---|\n| recent | {} |\n'.format(today))
    assert run(path).returncode == 0


def test_receipts_use_selection_utc_and_ignore_older_than_seven_days(tmp_path):
    path = board(tmp_path / 'LEADERBOARD.md', models=('anthropic/claude-fable-5.2',))
    receipts = tmp_path / 'receipts'
    receipts.mkdir()
    now = dt.datetime.now(dt.timezone.utc)
    for name, age, model in [('recent', 1, 'claude-fable-5-2'), ('old', 8, 'unranked-old')]:
        (receipts / (name + '.selection.json')).write_text(json.dumps(
            {'utc': (now - dt.timedelta(days=age)).isoformat(), 'model': model}))
    assert run(path, '--used-from-receipts', receipts).returncode == 0
    (receipts / 'bad.selection.json').write_text(json.dumps({'utc': now.isoformat(), 'model': 'unranked'}))
    result = run(path, '--used-from-receipts', receipts)
    assert result.returncode == 1 and 'unranked is on no role row' in result.stdout


def test_alert_once_a_day_then_refresh(tmp_path):
    path = board(tmp_path / 'LEADERBOARD.md', age=10)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    calls = tmp_path / 'calls'
    for name in ('tell-general', 'refresh'):
        script = bin_dir / name
        script.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                          'with open(os.environ["FIXTURE_CALLS"], "a") as stream:\n'
                          '    stream.write(json.dumps(sys.argv) + "\\n")\n')
        script.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
               RSTACK_STATE_DIR=str(tmp_path / 'state'), FIXTURE_CALLS=str(calls))
    for _ in range(2):
        result = run(path, '--alert', '--refresh-command', str(bin_dir / 'refresh'), env=env)
        assert result.returncode == 1, result.stdout
    rows = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [Path(row[0]).name for row in rows] == ['tell-general', 'refresh']
    assert rows[0][1] == 'fyi' and 'older than 2 days' in rows[0][2]


def test_unreadable_board_and_receipts_fail(tmp_path):
    assert run(tmp_path / 'missing').returncode == 1
    path = board(tmp_path / 'LEADERBOARD.md')
    assert run(path, '--used-from-receipts', tmp_path / 'missing').returncode == 1
    (tmp_path / 'bad.selection.json').write_text('{}')
    assert run(path, '--used-from-receipts', tmp_path).returncode == 1
