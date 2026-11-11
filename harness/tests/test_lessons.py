"""Offline synthetic acceptance cases for shared knowledge and local field retros."""
import concurrent.futures
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rh
import lessons
import retro
import sweep


@pytest.fixture
def lab(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    for name in ('sample-a', 'sample-b'):
        lane = root / 'lanes' / name
        lane.mkdir(parents=True)
        (lane / 'INTAKE.toml').write_text('keywords = ["evaluation"]\n')
    (root / 'control.md').write_text('Synthetic control evidence.\n')
    monkeypatch.setattr(rh, 'taste_models', lambda: ('fixture-judge',))
    monkeypatch.setattr(rh.cadence, 'lint', lambda *a, **kw: [])
    return root


def cli(root, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rh.main(['--root', str(root), *args])
    return code, out.getvalue(), err.getvalue()


def add(root, lane='sample-a', text='A count-only control exposed a shortcut.', values=('evaluation',), **kw):
    return lessons.add(root, rh, lane=lane, lesson=text, evidence='control.md',
                       applies_when='Evaluating synthetic labels', values=values, **kw)


def test_add_for_supersede_promote_round_trip(lab):
    code, key, err = cli(lab, 'lessons', 'add', '--lane', 'sample-a', '--source', 'backfill',
                         '--lesson', 'A count-only control exposed a shortcut.', '--evidence', 'control.md',
                         '--applies-when', 'Testing labels', '--tags', 'Evaluation,Controls', 'EVALUATION')
    assert code == 0, err
    key = key.strip()
    first = lessons.current(lab, rh)[key]
    assert first['tags'] == ['controls', 'evaluation']
    code, out, err = cli(lab, 'lessons', 'for', 'sample-b', '--tags', 'Controls', '-n', '1')
    assert code == 0, err
    assert json.loads(out)['id'] == key
    replacement = add(lab, text='The synthetic shortcut depends on label frequency.', source='correction')
    assert cli(lab, 'lessons', 'supersede', key, '--by', replacement['id'])[0] == 0
    current = lessons.current(lab, rh)
    assert current[key]['status'] == 'superseded'
    assert current[replacement['id']]['supersedes'] == [key]
    assert key not in [r['id'] for r in lessons.for_lane(lab / 'lanes/sample-b', rh)]
    assert cli(lab, 'lessons', 'promote', replacement['id'], '--to', 'control.md')[0] == 0
    code, out, err = cli(lab, 'lessons', 'list', '--status', 'promoted')
    assert code == 0, err
    row = json.loads(out)
    assert row['promoted_to'] == 'control.md'
    assert row['id'] == replacement['id']
    history = rh.rows(lab / 'LESSONS.jsonl')
    assert len(history) == 5 and history[0] == first
    assert all(set(r) == {'id', 'utc', 'lane', 'source', 'tags', 'lesson', 'evidence', 'applies_when',
                          'status', 'supersedes', 'promoted_to'} for r in history)


def test_ranking_cross_lane_then_overlap_then_recency_and_idea(lab, monkeypatch):
    monkeypatch.setattr(rh, 'now', lambda: '2026-01-01T00:00:00+00:00')
    relevant_old = add(lab, values=('evaluation', 'controls'))
    monkeypatch.setattr(rh, 'now', lambda: '2026-01-02T00:00:00+00:00')
    relevant_new = add(lab, values=('evaluation', 'controls'))
    irrelevant = add(lab, values=('unrelated',))
    own = add(lab, lane='sample-b', values=('evaluation', 'controls'))
    lane = lab / 'lanes/sample-b'
    idea = rh.new_idea('internal', '', 'Invented control', data_tags=['controls'])
    rh.append(lane / 'IDEAS.jsonl', idea)
    found = lessons.for_lane(lane, rh, idea=idea['id'][:10])
    assert [r['id'] for r in found] == [relevant_new['id'], relevant_old['id'], irrelevant['id'], own['id']]
    assert lessons.for_lane(lane, rh, n=0) == []
    assert cli(lab, 'lessons', 'for', 'sample-b', '--idea', 'missing')[0] == 2


@pytest.mark.parametrize('flags', [
    ['--lesson', 'One. Two. Three.'], ['--lesson', ''],
    ['--lesson', 'two\nlines'], ['--evidence', 'missing-file'],
    ['--applies-when', ''], ['--lane', '../escape'],
    ['--promoted-to', 'missing-test'], ['--supersedes', 'missing-id'],
])
def test_bad_add_does_not_change_log(lab, flags):
    first = add(lab)
    before = (lab / 'LESSONS.jsonl').read_bytes()
    args = dict(lane='sample-a', lesson='One claim.', evidence='control.md', applies_when='Testing')
    field = flags[0][2:].replace('-', '_')
    if field == 'supersedes':
        args[field] = flags[1:]
    else:
        args[field] = flags[1]
    with pytest.raises(ValueError):
        lessons.add(lab, rh, **args)
    assert (lab / 'LESSONS.jsonl').read_bytes() == before
    assert first['id'] in lessons.current(lab, rh)


def test_supersession_guards_and_add_correction(lab):
    old = add(lab)
    newer = add(lab, text='A corrected control depends on the split.', supersedes=[old['id']])
    assert lessons.current(lab, rh)[old['id']]['status'] == 'superseded'
    assert newer['supersedes'] == [old['id']]
    before = (lab / 'LESSONS.jsonl').read_bytes()
    for key, replacement in ((newer['id'], newer['id']), (newer['id'], old['id']), ('missing', newer['id'])):
        assert cli(lab, 'lessons', 'supersede', key, '--by', replacement)[0] == 2
    assert cli(lab, 'lessons', 'promote', old['id'], '--to', 'control.md')[0] == 2
    assert (lab / 'LESSONS.jsonl').read_bytes() == before


def test_empty_read_is_read_only(lab):
    before = {p: p.read_bytes() for p in lab.rglob('*') if p.is_file()}
    assert cli(lab, 'lessons', 'list') == (0, '', '')
    assert cli(lab, 'lessons', 'for', 'sample-b') == (0, '', '')
    assert before == {p: p.read_bytes() for p in lab.rglob('*') if p.is_file()}


@pytest.mark.parametrize('required,flags,expected', [
    (False, [], 0), (True, [], 2),
    (True, ['--no-lesson', 'Administrative duplicate; no new observation'], 0),
    (True, ['--no-lesson', '   '], 2),
    (False, ['--lesson', ''], 2),
    (True, ['--lesson', 'A control exposed a shortcut.', '--lesson-tags', 'Controls,Evaluation'], 0),
    (False, ['--lesson', 'A control exposed a shortcut.'], 0),
    (False, ['--lesson-tags', 'controls'], 2),
])
def test_close_requirement_on_off_and_lesson_link(lab, required, flags, expected):
    lane = lab / 'lanes/sample-b'
    (lane / 'INTAKE.toml').write_text('keywords = []\nlessons_required = ' + str(required).lower() + '\n')
    row = rh.new_idea('internal', '', 'Synthetic hypothesis', data_tags=['evaluation'])
    rh.append(lane / 'IDEAS.jsonl', row)
    before = (lane / 'IDEAS.jsonl').read_bytes()
    code, _, err = cli(lab, 'idea', 'close', 'sample-b', row['id'], '--closed-reason', 'Source exclusion',
                        '--no-test-reason', 'Source exclusion', '--decided-by', 'fixture-judge', *flags)
    assert code == expected, err
    if code:
        assert (lane / 'IDEAS.jsonl').read_bytes() == before
        assert not (lab / 'LESSONS.jsonl').exists()
    else:
        closed = rh.latest(rh.rows(lane / 'IDEAS.jsonl'))[row['id']]
        assert closed['status'] == 'closed'
        assert closed['lessons_required_at_close'] is required
        if '--lesson' in flags:
            lesson = lessons.current(lab, rh)[closed['lesson_ids'][0]]
            assert lesson['source'] == 'close' and lesson['lane'] == 'sample-b'
            assert Path(lesson['evidence']) == lane / 'IDEAS.jsonl'
        elif '--no-lesson' in flags:
            assert closed['no_lesson_reason'] == flags[1]


def test_invalid_close_does_not_land_lesson(lab):
    lane = lab / 'lanes/sample-b'
    row = rh.new_idea('internal', '', 'Synthetic hypothesis')
    rh.append(lane / 'IDEAS.jsonl', row)
    assert cli(lab, 'ideas', 'close', 'sample-b', row['id'], '--closed-reason', 'No evidence',
               '--lesson', 'A control matters.', '--decided-by', 'fixture-judge')[0] == 2
    assert not (lab / 'LESSONS.jsonl').exists()


def test_required_config_is_boolean(lab):
    with pytest.raises(ValueError, match='lessons_required'):
        rh.validate_config({'lessons_required': 'true'})


def configure_sweep(lane):
    (lane / 'RULES.md').write_text('Synthetic policy: do not read hidden labels.\n')
    cfg = dict(enabled=True, start_date=dt.date.today().isoformat(), working_directory='.',
               rules_files=['RULES.md'], search_targets=['invented labels'], sources=['https://example.org/toy'],
               banned_sources=['hidden labels'], allowed_tests=['toy controls'], allowed_writes=['work/'],
               run_directory='work/runs', search_report='work/{date}-search.md', read_report='work/{date}-read.md',
               kill_report='work/{date}-kill.md', launcher='unused-launcher', testing_max_age_days=2, stagger_seconds=0)
    (lane / 'SWEEP.toml').write_text('\n'.join(k + ' = ' + json.dumps(v) for k, v in cfg.items()) + '\n')


def test_sweep_embeds_exact_snapshot_and_receipt(lab, monkeypatch, capsys):
    lane = lab / 'lanes/sample-b'
    first = add(lab)
    configure_sweep(lane)
    cfg = sweep.load(lane, rh)
    before = {p: p.read_bytes() for p in lab.rglob('*') if p.is_file()}
    assert sweep.run_lane(lane, cfg, rh, dry=True) == 0
    preview = capsys.readouterr().out
    assert 'rh lessons for sample-b -n 12' in preview
    assert preview.count(lessons.render([first]).strip()) == 3
    assert before == {p: p.read_bytes() for p in lab.rglob('*') if p.is_file()}
    shown = []
    def worker(spec, config):
        shown.append(spec.read_text())
        assert lessons.render([first]).strip() in spec.read_text()
        stage = spec.stem.split('-', 1)[1]
        (spec.parent / (stage + '.report.md')).write_text(
            {'search': 'NOTHING NEW\nDONE\n', 'read': 'No queued ideas.\nDONE\n',
             'kill': 'RESULT NONE\nDONE\n'}[stage])
        if len(shown) == 1:
            add(lab, text='An arriving lesson must wait for the next sweep.')
        return 0
    monkeypatch.setattr(sweep, 'run_worker', worker)
    monkeypatch.setattr(sweep, 'notify', lambda *a: pytest.fail('unexpected notification'))
    assert sweep.run_lane(lane, cfg, rh) == 0
    receipt = rh.rows(lane / 'SWEEP_RUNS.jsonl')[-1]
    assert len(shown) == 3 and receipt['lesson_ids'] == [first['id']]
    assert receipt['lessons_sha256'] == lessons.snapshot([first])
    assert receipt['lessons_command'] == 'rh lessons for sample-b -n 12'


def test_interrupted_sweep_receipt_records_shown_ids(lab, monkeypatch):
    lane = lab / 'lanes/sample-b'
    first = add(lab)
    configure_sweep(lane)
    monkeypatch.setattr(sweep, 'guard', lambda *a: None)
    monkeypatch.setattr(sweep, 'run_worker', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        sweep.run_locked(lane, sweep.load(lane, rh), rh, threading.Event())
    receipt = rh.rows(lane / 'SWEEP_RUNS.jsonl')[-1]
    assert receipt['status'] == 'finished' and receipt['ok'] is False
    assert receipt['lesson_ids'] == [first['id']]


def test_lint_warns_empty_sweep_and_unreferenced_old_lesson(lab, monkeypatch):
    lane = lab / 'lanes/sample-b'
    configure_sweep(lane)
    old_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91)).isoformat()
    real_now = rh.now
    monkeypatch.setattr(rh, 'now', lambda: old_time)
    old = add(lab)
    monkeypatch.setattr(rh, 'now', real_now)
    rh.append(lane / 'SWEEP_RUNS.jsonl', dict(id='run', status='finished', ok=False, lesson_ids=[]))
    warning = lessons.warnings(lane, rh)
    assert any('lessons-unread' in w for w in warning)
    assert any(old['id'] in w and 'lesson-stale' in w for w in warning)
    result = rh.lint_result(lane)
    assert all(w in result['warnings'] for w in warning)
    failures_before = result['failure_count']
    rh.append(lane / 'SWEEP_RUNS.jsonl', dict(id='next-run', status='finished', ok=False, lesson_ids=[old['id']]))
    assert lessons.warnings(lane, rh) == []
    assert rh.lint_result(lane)['failure_count'] == failures_before
    (lane / 'SWEEP.toml').write_text('enabled = false\n')
    assert lessons.warnings(lane, rh) == []


def test_promoted_and_superseded_lessons_do_not_go_stale(lab, monkeypatch):
    old_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)).isoformat()
    real_now = rh.now
    monkeypatch.setattr(rh, 'now', lambda: old_time)
    first = add(lab, promoted_to='control.md')
    old = add(lab)
    add(lab, supersedes=[old['id']], promoted_to='control.md')
    monkeypatch.setattr(rh, 'now', real_now)
    assert lessons.warnings(lab / 'lanes/sample-b', rh) == []
    assert first['status'] == 'promoted'


def test_new_lane_prints_and_records_lessons(lab):
    first = add(lab)
    code, out, err = cli(lab, 'lane', 'new', 'sample-c', '--problem', 'Synthetic evaluation',
        '--metric', 'accuracy', '--dev-set', 'toy-dev', '--hidden-test', 'toy-hidden',
        '--split', 'group', '--split-reason', 'Synthetic subjects are held out',
        '--sealed-set-id', 'synthetic-held-out', '--deadline-days', '7', '--submissions', '1',
        '--submission-rules', 'One synthetic file')
    assert code == 0, err
    lane = lab / 'lanes/sample-c'
    receipt = json.loads((lane / 'LESSONS_READ.json').read_text())
    assert receipt['lesson_ids'] == [first['id']]
    assert receipt['lessons_sha256'] == lessons.snapshot([first])
    assert lessons.render([first]).strip() in out
    assert rh.lane_config(lane)['lessons_required'] is False
    assert not (lane / 'IDEAS.jsonl').exists()
    assert not (lane / 'SWEEP_RUNS.jsonl').exists()


def test_retro_field_sections_with_private_data_separate(lab):
    lane = lab / 'lanes/sample-b'
    (lane / 'result.json').write_text('{"score": 0.42, "selected": "floor"}\n')
    (lane / 'prior.md').write_text('Synthetic method, https://example.org/method\n')
    row = rh.new_idea('internal', '', 'SENTINEL restart the worker process')
    row.update(status='closed', closed_reason='SENTINEL restart the worker process.',
               result_path='result.json', verification='L0', finite_component='none', prior_art='prior.md',
               selection_records=[dict(decision_path='result.json')])
    rh.append(lane / 'IDEAS.jsonl', row)
    rh.append(lane / 'SEALED_SCORING.jsonl', dict(id='synthetic-decision', accepted=False))
    rh.append(lane / 'OPTIMISM.jsonl', dict(id='synthetic-optimism', drop=0.1))
    rh.append(lane / 'OUTREACH.jsonl', dict(id='synthetic-reply', reply=dict(summary='Synthetic source reply.')))
    lesson = add(lab, lane='sample-b', text='SENTINEL restart a bounded worker.', values=('method',))
    original = (lab / 'LESSONS.jsonl').read_bytes()
    code, out, err = cli(lab, 'retro', 'sample-b')
    assert code == 0, err
    target = lane / 'RETRO.draft.md'
    text = target.read_text()
    assert [line[3:] for line in text.splitlines() if line.startswith('## ')] == list(retro.SECTIONS)
    assert 'SENTINEL' not in text and '## Ops' not in text and '## Agent' not in text
    assert '1 recorded ideas' in text and row['id'] in text
    assert 'score=0.42' in text
    data = json.loads(target.with_suffix('.sources.json').read_text())
    assert data['ideas'][0]['closed_reason'] == row['closed_reason']
    assert data['artifacts']['result.json']['data']['score'] == 0.42
    assert data['ideas'][0]['verification'] == 'L0'
    assert data['selection'][0]['accepted'] is False
    assert data['outreach_replies'][0]['reply']['summary'] == 'Synthetic source reply.'
    assert data['lessons'][0]['id'] == lesson['id']
    proposed = rh.rows(target.with_suffix('.lessons.proposed.jsonl'))
    assert len(proposed) == 1 and proposed[0]['source'] == 'retro'
    assert proposed[0]['id'] not in lessons.current(lab, rh)
    assert (lab / 'LESSONS.jsonl').read_bytes() == original
    before = {p: p.read_bytes() for p in lane.rglob('*') if p.is_file()}
    assert cli(lab, 'retro', 'sample-b')[0] == 2
    assert before == {p: p.read_bytes() for p in lane.rglob('*') if p.is_file()}
    assert cli(lab, 'retro', 'sample-b', '--out', str(lab / 'drafts/review.md'))[0] == 0


def test_root_lock_blocks_writer_and_concurrent_adds_preserve_all(lab):
    base = [sys.executable, str(Path(rh.__file__).resolve()), '--root', str(lab),
            'lessons', 'add', '--lane', 'sample-a', '--evidence', 'control.md',
            '--applies-when', 'Concurrent synthetic imports', '--tags', 'concurrency']
    with rh.locked(lab):
        process = subprocess.Popen(base + ['--lesson', 'The root lock serializes writers.'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=0.15)
            assert not (lab / 'LESSONS.jsonl').exists()
        except BaseException:
            process.kill()
            process.communicate()
            raise
    out, err = process.communicate(timeout=20)
    assert process.returncode == 0, err
    def writer(i):
        return subprocess.run(base + ['--lesson', 'Synthetic observation {}.'.format(i)],
                              capture_output=True, text=True, timeout=30)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(writer, range(16)))
    assert all(p.returncode == 0 for p in results), [p.stderr for p in results]
    history = rh.rows(lab / 'LESSONS.jsonl')
    assert len(history) == len({r['id'] for r in history}) == 17
    assert len(lessons.current(lab, rh)) == 17


def test_free_text_lane_and_domain_tags_rank_without_configuration_edits(lab, monkeypatch):
    lane = lab / 'lanes/sample-b'
    (lane / 'INTAKE.toml').write_text('keywords = ["synthetic perturbation prediction"]\n')
    monkeypatch.setattr(rh, 'now', lambda: '2026-01-01T00:00:00+00:00')
    relevant = add(lab, values=['domain:perturbation', 'controls'])
    monkeypatch.setattr(rh, 'now', lambda: '2026-01-02T00:00:00+00:00')
    add(lab, values=['unrelated'])
    assert lessons.for_lane(lane, rh, n=1)[0]['id'] == relevant['id']


def test_read_receipt_references_old_lesson_and_disabled_lane_has_no_sweep_warning(lab, monkeypatch):
    lane = lab / 'lanes/sample-b'
    old_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91)).isoformat()
    real_now = rh.now
    monkeypatch.setattr(rh, 'now', lambda: old_time)
    old = add(lab)
    monkeypatch.setattr(rh, 'now', real_now)
    rh.append(lane / 'SWEEP_RUNS.jsonl', dict(id='disabled-run', lesson_ids=[]))
    (lane / 'SWEEP.toml').write_text('enabled = false\n')
    assert all('lessons-unread' not in w for w in lessons.warnings(lane, rh))
    assert any(old['id'] in w for w in lessons.warnings(lane, rh))
    lessons.record_read(lane, rh)
    assert lessons.warnings(lane, rh) == []


def test_a_lanes_own_lessons_are_not_crowded_out_by_other_lanes(lab):
    """11-11, friends: with more than n cross-lane lessons stored, every slot went to other lanes and a
    lesson friends had just recorded never reached its next jobs. Each group now gets half the slots."""
    for i in range(14):
        add(lab, lane='sample-a', text='Other lane lesson {}.'.format(i))
    own = add(lab, lane='sample-b', text='This lane just learned this.')
    picked = lessons.for_lane(lab / 'lanes/sample-b', rh, n=12)
    assert len(picked) == 12 and own['id'] in [r['id'] for r in picked]
    assert sum(r['lane'] == 'sample-a' for r in picked) == 11     # unused own slots go to cross-lane
    assert [r['id'] for r in lessons.for_lane(lab / 'lanes/sample-b', rh, n=1)] != []
