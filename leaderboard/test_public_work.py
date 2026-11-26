"""Public rates are joined run outcomes, with independent owner and evidence ranks."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('public_roles', HERE / 'model-roles.py')
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)
import run_grades
import score_canary
from run_grades import run_records

NOW = dt.datetime(2026, 11, 26, 18, tzinfo=dt.timezone.utc)
CARBON, OPUS, SOL = 'gemini-4-carbon-high', 'claude-opus-5-5', 'gpt-6.2-sol'


@pytest.fixture
def world(tmp_path, monkeypatch):
    runs = tmp_path / 'model-runs.jsonl'
    monkeypatch.setenv('RH_MODEL_RUNS_LOG', str(runs))
    monkeypatch.setenv('RH_EVERYDAY_GRADES', str(tmp_path / 'everyday-grades.jsonl'))
    monkeypatch.setattr(mr, 'now', lambda: NOW)
    return tmp_path


def attempt(world, ident, model=CARBON, grade=None, role='batch', **extra):
    fields = extra.pop('grade_fields', {})
    row = dict(run_id=ident, utc=(NOW - dt.timedelta(hours=1)).isoformat(),
               job=ident, model=model, role=role, **extra)
    run_records.append(world / 'model-runs.jsonl', row)
    if grade:
        g = run_records.grade_fields(ident, row['job'], model, role, grade, 'synthetic')
        g.update(date=NOW.date().isoformat(), **fields)
        run_records.append(world / 'everyday-grades.jsonl', g)
    return row


def render(world, **data):
    page = world / 'public.md'
    mr.public(dict(updated=NOW.isoformat(), roles={'batch': [SOL, OPUS]}, **data), page)
    return page.read_text()


def rows(text):
    return [[c.strip() for c in line.strip('|').split('|')] for line in text.splitlines()
            if line.startswith('| ') and line.split('|')[1].strip() not in ('Model', 'Role')]


def model_rows(text, model):
    return [r for r in rows(text) if r[0] == model]


def test_model_with_runs_and_zero_grades_appears(world):
    for i in range(16):
        attempt(world, f'carbon-{i}')
    text = render(world)
    row, = model_rows(text, CARBON)
    assert row[2] == '16'
    assert row[3] == '- (n=0)' and row[5] == '- (n=0)'


def test_n19_prints_rate_interval_but_no_role_rank(world):
    for i in range(19):
        attempt(world, f'run-{i}', grade='pass')
    row, = model_rows(render(world), CARBON)
    assert row[5] == '100.0% [83.2%, 100.0%] (n=19)'
    assert row[6] == 'n<20, unranked'


def test_wilson_interval_and_role_order_use_own_role_counts(world):
    for i in range(20):
        attempt(world, f'carbon-{i}', grade='pass' if i < 10 else 'fail')
        attempt(world, f'opus-{i}', OPUS, 'pass' if i < 18 else 'fail')
    for i in range(19):
        attempt(world, f'opus-review-{i}', OPUS, 'pass', role='review')
    text = render(world)
    batch = [r for r in rows(text) if r[4] == 'batch']
    assert [r[0] for r in batch] == [OPUS, CARBON]
    assert [r[6] for r in batch] == ['1', '2']
    assert batch[0][5] == '90.0% [69.9%, 97.2%] (n=20)'
    review, = [r for r in model_rows(text, OPUS) if r[4] == 'review']
    assert review[6] == 'n<20, unranked' and '(n=39)' in review[3]
    assert mr.wilson_high(18, 20) == pytest.approx(.9721341)


def test_false_workdir_fail_excluded_and_counted(world):
    attempt(world, 'bad', grade='fail', grade_fields=dict(missing_files=['output.json']))
    attempt(world, 'old', grade='fail', grade_fields=dict(note='workdir incomplete: REPORT.md'))
    attempt(world, 'good', grade='pass')
    text = render(world)
    row, = model_rows(text, CARBON)
    assert row[2] == '3' and row[5].endswith('(n=1)') and row[5].startswith('100.0%')
    assert 'Dropped 2 grade rows: workdir incomplete=2' in text


def test_old_remote_controller_grade_is_excluded_but_real_remote_fail_counts(world, monkeypatch):
    receipts = world / 'receipts'
    receipts.mkdir()
    monkey_ledger = receipts / 'everyday-grades.jsonl'
    attempt(world, 'oldremote', grade='fail', host='m5')
    attempt(world, 'realremote', grade='fail', host='m5', grade_fields=dict(grade_host='m5'))
    attempt(world, 'logremote', grade='fail')
    (receipts / 'logremote.log').write_text('=== attempt 1 model x host m5 Thu Nov 26\n')
    # Discovery uses grade-ledger locations, including old *.log headers.
    grades = world / 'everyday-grades.jsonl'
    monkey_ledger.write_bytes(grades.read_bytes())
    grades.write_text('')
    monkeypatch.setenv('RH_EVERYDAY_GRADES', str(monkey_ledger))
    text = render(world)
    row, = model_rows(text, CARBON)
    assert row[5].startswith('0.0%') and row[5].endswith('(n=1)')
    assert 'remote controller grade=2' in text


def test_quota_is_ungraded_even_if_legacy_grade_says_fail(world):
    attempt(world, 'quota', grade='fail', reason='quota')
    text = render(world)
    row, = model_rows(text, CARBON)
    assert row[2] == '1' and row[5] == '- (n=0)'
    assert 'quota=1' in text


def test_bench_is_a_footnote_and_cannot_rank(world):
    attempt(world, 'ordinary', grade='fail')
    attempt(world, 'synthetic', OPUS, 'pass', bench=True)
    text = render(world, bench={'batch': {OPUS: dict(n=24, rate=1.0)}})
    header = next(l for l in text.splitlines() if l.startswith('| Model |'))
    assert 'Bench' not in header
    assert 'Everyday work ranks models, never synthetic. Bench (saturated):' in text
    assert not model_rows(text, OPUS)


def test_rank_values_and_tied_owner_preferences_survive_new_evidence(world):
    page = world / 'public.md'
    page.write_text('| Model | Rank | Other |\n| gemini-4-carbon-high | 7 | old |\n'
                    '| claude-opus-5-5 | 1 | old |\n| gemini-4-neon-high | 1 | old |\n')
    for model in (CARBON, OPUS, 'gemini-4-neon-high'):
        for i in range(20):
            attempt(world, f'{model}-{i}', model, 'fail' if model == OPUS else 'pass')
    text = render(world, owner_rank=mr.OWNER_RANK)
    assert '| Rank (Ricardo: taste + cost) |' in text
    assert {m: model_rows(text, m)[0][1] for m in (CARBON, OPUS, 'gemini-4-neon-high')} == {
        CARBON: '7', OPUS: '1', 'gemini-4-neon-high': '1'}
    assert model_rows(render(world), CARBON)[0][1] == '7'


def test_driver_outputs_count_only_real_grades(world):
    attempt(world, 'driver1', 'gemini-4-neon-high', 'pass', backend='agy-driver')
    attempt(world, 'driver2', 'gemini-4-neon-high', 'void: no output', backend='agy-driver')
    attempt(world, 'driver3', 'gemini-4-neon-high', backend='agy-driver')
    text = render(world)
    assert 'Driver-session work (most Gemini Neon use) is ungraded until driver outputs are scored; 1/3 driver outputs have a grade.' in text


@pytest.mark.parametrize('extra', [{'purpose': 'probe'}, {'job': 'canary-legacy'}])
def test_probe_runs_are_void_and_absent_from_table_and_owed(world, extra, capsys):
    row = dict(run_id='probe', utc=(NOW - dt.timedelta(days=2)).isoformat(), job='health', model=CARBON)
    row.update(extra)
    run_records.append(world / 'model-runs.jsonl', row)
    (run, record), = run_grades.table()[0]
    assert record[0]['grade'] == 'void: probe'
    assert not score_canary.report([(run, record)], NOW, owed=True)
    out = capsys.readouterr().out
    assert 'owed >24h: 0' in out and CARBON not in out
    assert not model_rows(render(world), CARBON)


def test_executor_persists_probe_purpose_and_void_grade(world, monkeypatch):
    fake = world / 'fake-codex'
    fake.write_text(f'#!{sys.executable}\nprint("OK")\n')
    fake.chmod(0o755)
    monkeypatch.setenv('RH_RUN_PURPOSE', 'probe')
    monkeypatch.setenv('RH_JOB', 'arbitrary-health-name')
    result = subprocess.run([sys.executable, str(HERE.parent / 'harness/agent_executor.py'),
        '--backend', 'codex', '--executable', str(fake), '--directory', str(world), '--model', SOL,
        '--effort', 'medium', '--output', str(world / 'last')], input='', text=True,
        capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    raw = list(run_records.read_jsonl(world / 'model-runs.jsonl'))
    assert raw and all(r['purpose'] == 'probe' for r in raw)
    grade, = run_records.read_jsonl(world / 'everyday-grades.jsonl')
    assert grade['grade'] == 'void: probe'


def test_window_and_partial_credit_are_explicit(world):
    attempt(world, 'partial', grade='partial')
    run_records.append(world / 'model-runs.jsonl', dict(run_id='ancient', job='ancient', model=OPUS,
                        utc=(NOW - dt.timedelta(days=31)).isoformat()))
    text = render(world)
    row, = model_rows(text, CARBON)
    assert row[5].startswith('50.0%') and 'partial=half' in text
    assert '30 days' in text and not model_rows(text, OPUS)


def test_legacy_grader_missing_headers_are_checked_against_raw_files(world):
    work = world / 'work'
    work.mkdir()
    stem = world / 'legacy'
    Path(str(stem) + '.md').write_text(f'Work dir: {work}\n')
    fields = dict(auto=True, grader='checks', reason='exit 0; Shipped line no; You asked line no')
    run = attempt(world, str(stem), grade='fail', grade_fields=fields)
    text = render(world)
    assert 'workdir incomplete=1' in text
    assert model_rows(text, CARBON)[0][5] == '- (n=0)'
    # Headers missing from existing files are not evidence that files were absent.
    (work / 'STATUS.md').write_text('wrong first line\n')
    (work / 'REPORT.md').write_text('wrong first line\n')
    text = render(world)
    assert model_rows(text, CARBON)[0][5].startswith('0.0%')
    assert 'Dropped 0 grade rows: none' in text


def test_legacy_launch_matching_uses_full_output_path_not_reused_job_name(world, monkeypatch):
    import shlex
    root = world / 'launches'
    monkeypatch.setenv('MODEL_LAUNCH_ROOT', str(root))
    work = world / 'correct-work'
    work.mkdir()
    other_work = world / 'wrong-work'
    other_work.mkdir()
    (other_work / 'STATUS.md').write_text('present')
    (other_work / 'REPORT.md').write_text('present')
    job = world / 'a' / '0-read'
    for directory, name, output in ((work, 'one', job), (other_work, 'two', world / 'b' / '0-read')):
        script = root / '0-read' / name / 'run.sh'
        script.parent.mkdir(parents=True)
        script.write_text('cd ' + shlex.quote(str(directory)) + '\nexec python3 executor --output '
                          + shlex.quote(str(output) + '.last.md') + '\n')
    attempt(world, str(job), grade='fail', grade_fields=dict(
        auto=True, grader='checks', reason='exit 0; Shipped line no; You asked line no'))
    assert 'workdir incomplete=1' in render(world)


def test_probe_with_old_fail_cannot_leak_into_ingested_evidence(world, monkeypatch):
    from outcome_adapters import Outcomes, Receipts
    receipts = world / 'receipts'
    receipts.mkdir()
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    attempt(world, 'canary-old', grade='fail')
    reader = Outcomes(Receipts(receipts), mr.canon, mr.obs)
    reader.read_grades([world / 'everyday-grades.jsonl'])
    assert not reader.observations


def test_canary_executor_invocation_sets_probe_environment(world, monkeypatch):
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader('public_test_canary', str(HERE.parent / 'rstack/tools/canary'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    canary = importlib.util.module_from_spec(spec)
    loader.exec_module(canary)
    fake = world / 'fake-executor'
    fake.write_text(f'#!{sys.executable}\nimport os\nassert os.environ["RH_RUN_PURPOSE"] == "probe"\nprint("OK")\n')
    fake.chmod(0o755)
    cfg = dict(executor=str(fake), claude_model='fixture', codex_model=SOL, codex_effort='medium', timeout=15)
    assert canary.probe_executor('codex', cfg) == (True, '')


def test_launcher_probe_is_void_without_artifact_checks_or_owed_alert(world, monkeypatch):
    import auto_grade
    receipt = world / 'probe.log.selection.json'
    receipt.write_text(json.dumps(dict(selection_id='probe', job='canary-launched',
                                      model=CARBON, source='delegate', role='batch', purpose='probe')))
    log = world / 'probe.log'
    log.write_text('MODEL_OUTCOME ' + json.dumps(dict(selection_id='probe', exit_code=0)) + '\n')
    def forbidden(*args, **kwargs):
        pytest.fail('a health probe cannot require artifacts or an owed alert')
    monkeypatch.setattr(auto_grade, 'inspect_workdir', forbidden)
    monkeypatch.setattr(auto_grade.wm, 'morning_report', forbidden)
    assert auto_grade.grade(receipt, log, world / 'no-files', None)['grade'] == 'void: probe'
