"""The X adapter uses stub executables; no Grok app, account or network."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools/grok-x-search'


@pytest.fixture
def setup(tmp_path):
    lane = tmp_path / 'runtime/lanes/fixture'
    lane.mkdir(parents=True)
    (lane / 'INTAKE.toml').write_text('x_local_file = "X_HITS.jsonl"\n')
    calls = tmp_path / 'calls'
    for name in ('grok-ask', 'rh'):
        stub = tmp_path / name
        stub.write_text('#!' + sys.executable + '\n'
                        'import json,os,sys\n'
                        'with open(os.environ["STUB_CALLS"], "a") as out:\n'
                        '    out.write(json.dumps({"tool":os.path.basename(sys.argv[0]), '
                        '"args":sys.argv[1:], "caller":os.environ.get("RSTACK_CALLER")}) + "\\n")\n'
                        'if os.path.basename(sys.argv[0]) == "grok-ask":\n'
                        '    print(os.environ["STUB_ROWS"])\n'
                        '    print("stub diagnostic", file=sys.stderr) if os.environ.get("STUB_FAIL") else None\n'
                        '    sys.exit(int(os.environ.get("STUB_FAIL", "0")))\n'
                        'sys.exit(int(os.environ.get("STUB_RH_FAIL", "0")))\n')
        stub.chmod(0o755)
    env = dict(os.environ, GROK_ASK=str(tmp_path / 'grok-ask'), RH=str(tmp_path / 'rh'),
               STUB_CALLS=str(calls), STUB_ROWS='[{"post_id":"123", "text":"lead"}]')
    return lane, env, calls


def run(setup, *args):
    lane, env, _ = setup
    return subprocess.run([sys.executable, str(TOOL), '--root', str(lane.parents[1]),
                           'fixture', '--query', 'fixture topic', *args], env=env,
                          capture_output=True, text=True, timeout=8)


@pytest.mark.parametrize('rows', [[dict(post_id='123', text='lead')], []])
def test_saved_rows_rh_evidence_and_leads_notice(setup, rows):
    lane, env, calls = setup
    env['STUB_ROWS'] = json.dumps(rows)
    result = run(setup, '--since', '2026-11-14', '--host', 'fixture-host')
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('Grok rows are leads: exact text must be read in the browser before anything is scored.') == 1
    files = list((lane / 'intake/x-search').glob('*.json'))
    assert len(files) == 1 and json.loads(files[0].read_text()) == rows
    query = 'fixture topic since:2026-11-14'
    assert files[0].stem.endswith(hashlib.sha256(query.encode()).hexdigest()[:16])
    log = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [row['tool'] for row in log] == ['grok-ask', 'rh']
    assert log[0]['caller'] == 'grok-x-search'
    assert log[0]['args'][:4] == ['--timeout', '120', '--host', 'fixture-host'] or log[0]['args'][:4] == ['--timeout', '120.0', '--host', 'fixture-host']
    assert query in log[0]['args'][-1]
    expected = ['--root', str(lane.parents[1]), 'intake', 'x-search', 'fixture', '--query', query,
                '--result', 'hits' if rows else 'none', '--n', str(len(rows)),
                '--hits-file', str(files[0]), '--captured-by', 'grok-x-search']
    assert log[1]['args'] == expected


def test_ask_failure_preserved_no_intake_record(setup):
    lane, env, calls = setup
    env['STUB_FAIL'] = '3'
    result = run(setup)
    assert result.returncode == 3 and 'stub diagnostic' in result.stderr
    assert not (lane / 'intake').exists()
    assert len(calls.read_text().splitlines()) == 1


def test_rh_failure_keeps_saved_leads(setup):
    lane, env, _ = setup
    env['STUB_RH_FAIL'] = '2'
    result = run(setup)
    assert result.returncode == 2 and 'saved leads remain at' in result.stderr
    assert len(list((lane / 'intake/x-search').glob('*.json'))) == 1


def test_bad_ask_output_never_records_success(setup):
    lane, env, calls = setup
    env['STUB_ROWS'] = '{}'
    result = run(setup)
    assert result.returncode == 3 and 'array of objects' in result.stderr
    assert len(calls.read_text().splitlines()) == 1
    assert not (lane / 'intake').exists()


def test_since_must_be_iso_date(setup):
    result = run(setup, '--since', 'yesterday')
    assert result.returncode == 2
    assert not setup[2].exists()
