"""agy quota is infrastructure: a blocked (model, tier) is not picked until its reset, and a quota hit is never a grade.

11-20 (harness-m5): gemini-4-hydrogen-medium answered "Resets in 152h14m46s" and kept being delegated, so each job
failed at once. Every CLI here is a stub: no model, no network, no spend.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'harness'))
import agy_quota  # noqa: E402
import auto_grade  # noqa: E402
import worker_models as wm  # noqa: E402

ERROR = 'Individual quota reached. Please upgrade your subscription to increase your limits. Resets in {}.'
NOW = dt.datetime(2026, 11, 20, 13, 0, tzinfo=dt.timezone.utc)
ROLES = {'roles': {'batch': ['gemini-4-hydrogen-medium', 'gpt-6.2-sol'], 'review': ['claude-opus-5-5']},
         'routes': {'gemini-4-hydrogen-medium': {'cli': 'agy', 'canonical': 'google/gemini-4-hydrogen-medium'},
                    'gemini-4-hydrogen-high': {'cli': 'agy', 'canonical': 'google/gemini-4-hydrogen-high'},
                    'gpt-6.2-sol': {'cli': 'codex', 'canonical': 'openai/gpt-6.2-sol'},
                    'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'}}}


def quota_row(model, reset, utc=NOW, tier=None, job='j'):
    return dict(utc=utc.isoformat(timespec='seconds'), model=model, tier=tier or agy_quota.tier_of(model),
                job=job, error=ERROR.format(reset))


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    for k in ('RH_CLAUDE_OVERFLOW_PERCENT', 'LAUNCH_EFFORT'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    monkeypatch.setenv('RH_CLAUDE_CAP', '0')   # these test the 85% overflow and agy quota; the 80% ceiling has its own tests
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    (tmp_path / 'roles.json').write_text(json.dumps(ROLES))
    return tmp_path


def write(state, *rows):
    path = state / 'state/agy-quota.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')


def test_the_reset_parses_into_blocked_until_and_its_window():
    assert agy_quota.reset_seconds(ERROR.format('152h14m46s')) == 152 * 3600 + 14 * 60 + 46
    assert agy_quota.reset_seconds(ERROR.format('4h52m1s')) == 4 * 3600 + 52 * 60 + 1
    assert agy_quota.reset_seconds('Resets in 2d3h') == 2 * 86400 + 3 * 3600
    assert agy_quota.reset_seconds('HTTP 429: try later') is None
    assert agy_quota.window(4 * 3600 + 52 * 60) == '5h' and agy_quota.window(152 * 3600) == 'weekly'
    row = agy_quota.annotate(quota_row('gemini-4-hydrogen-medium', '152h14m46s'))
    assert row['blocked_until'] == '2026-11-26T21:14:46+00:00' and row['window'] == 'weekly'
    row = agy_quota.annotate(quota_row('claude-opus-5-5-high', '4h52m1s'))
    assert row['blocked_until'] == '2026-11-20T17:52:01+00:00' and (row['window'], row['tier']) == ('5h', 'high')


def test_only_resets_still_ahead_block_and_the_latest_wins(state):
    write(state, quota_row('gemini-4-hydrogen-medium', '152h14m46s'), quota_row('claude-opus-5-5-high', '4h52m1s'),
          dict(quota_row('gemini-4-hydrogen-low', '1h'), error='429 too many requests'))   # no reset named: not blocked
    table = agy_quota.blocked(NOW + dt.timedelta(hours=6))
    assert set(table) == {('gemini-4-hydrogen-medium', 'medium')}   # the 5-hour window has passed
    assert agy_quota.blocked_until('gemini-4-hydrogen-medium', table=table)
    # 11-28: every Gemini model shares one pool, so the weekly block on Hydrogen-medium blocks Hydrogen-low too
    assert agy_quota.blocked_until('gemini-4-hydrogen-low', table=table)['model'] == 'gemini-4-hydrogen-medium'
    assert agy_quota.blocked_until('claude-opus-5-5-high', table=table) is None   # agy's other pool
    assert set(agy_quota.blocked(NOW)) == {('gemini-4-hydrogen-medium', 'medium'), ('claude-opus-5-5-high', 'high')}
    assert agy_quota.blocked(NOW + dt.timedelta(days=7)) == {}


def test_the_default_pick_skips_a_blocked_agy_model_and_the_receipt_says_until_when(state):
    write(state, quota_row('gemini-4-hydrogen-medium', '152h', utc=dt.datetime.now(dt.timezone.utc)),
          quota_row('gemini-4-hydrogen-high', '152h', utc=dt.datetime.now(dt.timezone.utc)))
    receipt = wm.select('batch', 'codex', path=state / 'roles.json', job='j')
    assert (receipt['model'], receipt['executor']) == ('gpt-6.2-sol', 'codex')
    assert receipt['quota_skipped'][0].startswith('skipped gemini-4-hydrogen-medium: agy quota until ')
    assert 'weekly window' in receipt['quota_skipped'][0]
    with pytest.raises(ValueError, match='agy quota until'):
        wm.select('batch', 'agy', model='gemini-4-hydrogen-medium', override='test', path=state / 'roles.json')
    (state / 'state/agy-quota.jsonl').write_text('')
    assert wm.select('batch', 'agy', path=state / 'roles.json')['model'] == 'gemini-4-hydrogen-high'


def test_a_blocked_agy_model_sends_the_job_to_codex(state):
    write(state, quota_row('gemini-4-hydrogen-high', '3h', utc=dt.datetime.now(dt.timezone.utc)))
    receipt = wm.select('batch', 'codex', path=state / 'roles.json', job='j')
    assert (receipt['source'], receipt['model'], receipt['executor']) == ('delegate', 'gpt-6.2-sol', 'codex')
    assert any('gemini-4-hydrogen-high' in s and '5h window' in s for s in receipt['quota_skipped'])


def test_a_claude_job_does_not_overflow_to_an_agy_claude_out_of_quota(state, monkeypatch):
    import time
    monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', '85')
    (state / 'state/usage').mkdir(parents=True)
    (state / 'state/usage/claude.json').write_text(json.dumps({'weekly_percent': 90, 'at': time.time()}))
    roles = {'roles': {'writing': ['claude-opus-5-5']}, 'routes': ROLES['routes']}
    (state / 'roles.json').write_text(json.dumps(roles))
    # 11-27: agy never runs Claude, so there is no overflow route to skip, quota or not.
    receipt = wm.select('writing', 'claude', path=state / 'roles.json')
    assert receipt['executor'] == 'claude' and 'route_model' not in receipt
    write(state, quota_row('claude-opus-5-5-high', '4h52m1s', utc=dt.datetime.now(dt.timezone.utc)))
    receipt = wm.select('writing', 'claude', path=state / 'roles.json')
    assert receipt['executor'] == 'claude' and 'route_model' not in receipt


def returned(tmp_path, quota_line, executor='agy'):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    (work / 'REPORT.md').write_text('Shipped: half of it\n')
    (work / 'STATUS.md').write_text('You asked: x. I will: y.\n')
    receipt = tmp_path / 'job.log.selection.json'
    sel = dict(selection_id='sid1', job='job', lane='l', role='batch', model='gemini-4-hydrogen-medium',
               executor=executor, source='delegate')
    receipt.write_text(json.dumps(sel))
    log = tmp_path / 'job.log'
    log.write_text('MODEL_SELECTION ' + json.dumps(sel) + '\n=== attempt 1\n' + quota_line + '\nexit 1 x\n'
                   'MODEL_OUTCOME ' + json.dumps(dict(sel, exit_code=1)) + '\n')
    (tmp_path / 'job.md').write_text('Check: true\n')
    return receipt, log, work


def test_a_quota_hit_is_recorded_ungraded_and_never_pass_partial_or_fail(state):
    mark = agy_quota.MARK + json.dumps(agy_quota.annotate(quota_row('gemini-4-hydrogen-medium', '152h14m46s')))
    receipt, log, work = returned(state, mark)
    row = auto_grade.grade(receipt, log, work, state / 'job.md')
    assert (row['grade'], row['grader']) == ('void: quota', 'quota') and row['note'].startswith('quota')
    assert 'weekly window' in row['note']
    # The controller learns the block from the job log, so a --host job's quota reaches its picker.
    assert ('gemini-4-hydrogen-medium', 'medium') in {(r['model'], r['tier']) for r in agy_quota.rows()}
    # An executor older than the AGY_QUOTA line: agy's own error text is enough.
    receipt, log, work = returned(state, 'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): ' + ERROR.format('4h') + '"}')
    assert auto_grade.grade(receipt, log, work, state / 'job.md')['grade'] == 'void: quota'
    # A session's grade for it is recorded void: quota too, with what it said kept in the note.
    assert wm.main(['--grade', 'partial', '--note', 'half done', '--receipt', str(receipt), '--log', str(log)]) == 0
    row = json.loads((state / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert row['grade'] == 'void: quota' and row['note'].startswith('quota') and 'given partial: half done' in row['note']
    # No quota in the log, or not an agy run: graded as before.
    receipt, log, work = returned(state, 'some output')
    assert auto_grade.grade(receipt, log, work, state / 'job.md')['grade'] == 'fail'
    receipt, log, work = returned(state, 'Individual quota reached', executor='codex')
    assert auto_grade.grade(receipt, log, work, state / 'job.md')['grade'] == 'fail'


def test_the_launcher_grades_a_delegated_agy_quota_failure_ungraded_and_the_next_pick_skips_it(state):
    agy = state / 'fake-agy'
    agy.write_text('#!' + sys.executable + '\nimport json, sys\nfrom pathlib import Path\n'
                   'Path("STATUS.md").write_text("You asked: x. I will: y.\\n")\n'
                   'Path("REPORT.md").write_text("Shipped: part\\n")\n'
                   'print(json.dumps({"status": "ERROR", "response": "", "error": ' + json.dumps(ERROR.format('152h14m46s')) + '}))\n')
    agy.chmod(0o755)
    jobs = state / 'jobs'
    jobs.mkdir()
    (jobs / 'fixture-q.md').write_text('Write out.txt.\nCheck: true\n')
    roles = {'roles': {'batch': ['gpt-6.2-sol']}, 'routes': ROLES['routes']}
    (state / 'roles.json').write_text(json.dumps(roles))
    env = dict(os.environ, LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(state / 'registry'),
               RH_ROLES_FILE=str(state / 'roles.json'), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(state / 'runtime'),
               LAUNCH_YIELD_LEDGER=str(state / 'yield.jsonl'), LAUNCH_AGY=str(agy),
               RH_LAUNCHER_EXECUTORS='agy')
    for k in ('LAUNCH_RESUME', 'SPEC_OVER_CAP', 'LAUNCH_HOST', 'TMUX', 'LAUNCH_DETACHED', 'AGENT_BACKEND',
              'LAUNCH_BACKEND', 'LAUNCH_ROLE'):
        env.pop(k, None)
    proc = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), 'fixture-q', str(state)], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1, proc.stderr
    receipt = json.loads((jobs / 'fixture-q.log.selection.json').read_text())
    assert receipt['executor'] == 'agy'
    row = json.loads((jobs / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['grader']) == ('void: quota', 'quota')
    blocked = agy_quota.blocked()
    assert [r['window'] for r in blocked.values()] == ['weekly']
    model = next(iter(blocked))[0]
    # The next delegate draw leaves that model out.
    proc = subprocess.run([sys.executable, str(REPO / 'harness/worker_models.py'), '--role', 'batch',
                           '--executor', 'codex', '--roles-file', str(state / 'roles.json'), '--job', 'next',
                           '--log', str(state / 'next.log'), '--receipt', str(state / 'next.json')],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0 and proc.stdout.split()[0] != model
    assert 'skipped {}: agy quota until'.format(model) in proc.stderr


def test_an_agy_run_that_hits_its_quota_is_rerun_on_codex(state):
    """11-24: the mirror of the Codex quota rerun (RH_AGY_CLOSED); the quota failure is not an attempt."""
    agy = state / 'fake-agy'
    agy.write_text('#!' + sys.executable + '\nimport json\nprint(json.dumps({"status": "ERROR", "response": "", "error": '
                   + json.dumps(ERROR.format('3h')) + '}))\n')
    codex = state / 'fake-codex'
    codex.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nimport sys\n'
                     'Path("STATUS.md").write_text("You asked: x. I will: y.\\n")\nPath("REPORT.md").write_text("Shipped: x\\n")\n'
                     'Path(sys.argv[sys.argv.index("-o") + 1]).write_text("done")\n')
    agy.chmod(0o755); codex.chmod(0o755)
    jobs = state / 'jobs'
    jobs.mkdir()
    (jobs / 'fixture-r.md').write_text('Write out.txt.\n')
    (state / 'roles.json').write_text(json.dumps({'roles': {'batch': ['gpt-6.2-sol']}, 'routes': ROLES['routes']}))
    env = dict(os.environ, LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(state / 'registry'),
               RH_ROLES_FILE=str(state / 'roles.json'), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(state / 'runtime'),
               LAUNCH_YIELD_LEDGER=str(state / 'yield.jsonl'), LAUNCH_AGY=str(agy), LAUNCH_CODEX=str(codex),
               RH_LAUNCHER_EXECUTORS='agy,codex')
    for k in ('LAUNCH_RESUME', 'SPEC_OVER_CAP', 'LAUNCH_HOST', 'TMUX', 'LAUNCH_DETACHED', 'AGENT_BACKEND',
              'LAUNCH_BACKEND', 'LAUNCH_ROLE'):
        env.pop(k, None)
    proc = subprocess.run(['zsh', str(REPO / 'tools/launch.sh'), 'fixture-r', str(state)], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads((jobs / 'fixture-r.log.selection.json').read_text())['executor'] == 'codex'
    assert 'agy hit its quota: rerunning' in (jobs / 'fixture-r.log').read_text()



def test_a_block_on_one_gemini_model_routes_every_gemini_model_elsewhere(state):
    # 11-28 (open-source): Neon-high was blocked until 12-03, the selector sent pyfaidx_gapfill_1127 to Neon-medium, and
    # it died in 3 s on a 429. agy's Gemini models draw on one weekly pool.
    write(state, quota_row('gemini-4-neon-high', '126h', utc=dt.datetime.now(dt.timezone.utc)))
    for model in ('gemini-4-neon-medium', 'gemini-4-neon-low', 'gemini-4-carbon-high', 'gemini-4-hydrogen-high'):
        assert agy_quota.blocked_until(model)['model'] == 'gemini-4-neon-high', model
    receipt = wm.select('batch', 'codex', path=state / 'roles.json', job='j')
    assert receipt['executor'] != 'agy' and any('agy quota until' in n for n in receipt.get('quota_skipped', []))
