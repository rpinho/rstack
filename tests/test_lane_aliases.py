"""A renamed lane is counted once, and both names use its existing ledgers."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'harness'))
import cadence
import intake_all
import lessons
import outreach
import retro
import rh
import settings
import upstream


@pytest.fixture
def renamed(tmp_path):
    lane = tmp_path / 'lanes' / 'open-source'
    lane.mkdir(parents=True)
    (lane.parent / 'bio').symlink_to('open-source', target_is_directory=True)
    (lane / 'INTAKE.toml').write_text('')
    (lane / 'SWEEP.toml').write_text('enabled = false\n')
    return tmp_path, lane


def load_tool(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cli(root, *args):
    return rh.main(['--root', str(root), *args])


def test_shared_paths_skip_aliases_and_non_directories(renamed):
    root, lane = renamed
    (lane.parent / 'REGISTRY.json').write_text('{}')
    assert list(rh.lane_dirs(root)) == [lane]
    assert rh.resolve_lane(root, 'bio') == rh.resolve_lane(root, 'open-source') == lane.name
    (lane.parent / 'older').symlink_to('bio', target_is_directory=True)
    assert rh.resolve_lane(root, 'older') == lane.name
    assert list(rh.lane_dirs(root)) == [lane]
    assert lessons.lane_at(root, 'bio') == lane
    assert settings.lane_dir('bio', root) == lane
    assert settings.lane_dir(lane.parent / 'bio', root) == lane


def test_cadence_lint_and_upstream_enumerate_once(renamed, monkeypatch):
    root, lane = renamed
    assert cadence.lanes(root) == cadence.lanes(root, 'bio') == [lane]
    assert [r['lane'] for r in cadence.report(root, rh)] == [lane.name]
    calls = []
    monkeypatch.setattr(rh, 'checked_lint', lambda path, report: calls.append(path) or {})
    assert rh.lint_all(root) == [{}]
    assert calls == [lane]
    (lane / upstream.CONFIG).write_text('{}')
    assert upstream.lanes_with_upstream(root) == [lane]


def test_outreach_quota_rows_are_counted_once_including_legacy_labels(renamed):
    root, lane = renamed
    row = dict(id='old-send', lane='bio', status='sent')
    rh.append(lane / 'OUTREACH.jsonl', row)
    assert list(outreach.all_rows(root, rh)) == [row]


def test_intake_enumerates_once_and_deduplicates_pinned_aliases(renamed, monkeypatch):
    root, lane = renamed
    monkeypatch.setattr(intake_all, 'ROOT', root)
    monkeypatch.delenv('RH_INTAKE_LANES', raising=False)
    assert intake_all.lanes() == [lane.name]
    monkeypatch.setenv('RH_INTAKE_LANES', 'bio,missing,open-source,bio')
    assert intake_all.lanes() == [lane.name]


def test_sweep_all_and_named_alias_visit_canonical_lane_once(renamed, capsys):
    root, _ = renamed
    for args in (('--all',), ('bio',), ('open-source',)):
        assert cli(root, 'sweep', *args, '--dry-run') == 0
        assert capsys.readouterr().out == 'SKIP open-source: sweep disabled\n'


def test_show_idea_has_one_match_after_rename(renamed, capsys):
    root, lane = renamed
    rh.append(lane / 'IDEAS.jsonl', dict(id='abc123', status='new'))
    assert cli(root, 'ideas', 'show', 'abc') == 0
    assert json.loads(capsys.readouterr().out)['lane'] == lane.name


def test_lessons_scan_each_lane_ledger_once(renamed, monkeypatch):
    root, lane = renamed
    row = lessons.make('bio', 'Synthetic old lesson.', 'control.md', 'Testing aliases', (), 'retro', rh)
    row['utc'] = '2020-01-01T00:00:00+00:00'
    rh.append(root / 'LESSONS.jsonl', row)
    read, original = [], rh.rows

    def tracked(path):
        read.append(path)
        return original(path)

    monkeypatch.setattr(rh, 'rows', tracked)
    assert any('lesson-stale' in w for w in lessons.warnings(lane, rh))
    assert [p for p in read if p.name == 'IDEAS.jsonl'] == [lane / 'IDEAS.jsonl']


def test_science_model_selection_reads_each_lane_once(renamed, monkeypatch):
    root, lane = renamed
    monkeypatch.setenv('CS_STATE', str(root / 'cs-state'))
    cs = load_tool('alias_cs', 'harness/cs.py')
    (lane / 'INTAKE.toml').write_text('claude_science_project = "http://localhost/projects/test"\n')
    monkeypatch.setattr(rh, 'ROOT', root)
    monkeypatch.setattr(rh, 'session_model', lambda: None)
    read, original = [], rh.config

    def tracked(path):
        read.append(path)
        return original(path)

    monkeypatch.setattr(rh, 'config', tracked)
    assert cs.model_for('test', {}) == rh.CS_DEFAULT_MODEL
    assert read == [lane / 'INTAKE.toml']


def test_rules_sync_visits_lane_once_from_unrelated_cwd(renamed, tmp_path):
    root, lane = renamed
    result = subprocess.run([sys.executable, str(REPO / 'harness/tools/lane-rules-sync/lane_rules_sync.py'),
                             '--root', str(root), '--repo', str(REPO)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'created open-source\n'
    assert 'success is never activity' in (lane / 'RULES.md').read_text()


def test_idea_writes_through_both_names_share_ledger(renamed, capsys):
    root, lane = renamed
    for name in ('bio', 'open-source'):
        assert cli(root, 'ideas', 'add', name, '--source-type', 'internal', '--claim', name) == 0
    capsys.readouterr()
    assert len(rh.rows(lane / 'IDEAS.jsonl')) == 2
    for name in ('bio', 'open-source'):
        assert cli(root, 'ideas', 'depth', name, '--quiet') == 0
        assert capsys.readouterr().out == '2\n'
    assert (lane.parent / 'bio').is_symlink()


def test_intake_x_search_alias_uses_canonical_capture(renamed):
    root, lane = renamed
    (lane / 'INTAKE.toml').write_text('x_local_file = "X_HITS.jsonl"\n')
    for name in ('bio', 'open-source'):
        assert cli(root, 'intake', 'x-search', name, '--query', 'synthetic',
                   '--result', 'none', '--n', '0') == 0
    assert len(rh.rows(lane / 'X_SEARCHES.jsonl')) == 2


def test_legacy_lessons_stay_in_the_same_lane_without_rewriting(renamed, capsys):
    root, lane = renamed
    own = lessons.make('bio', 'Synthetic legacy lesson.', 'control.md', 'Testing aliases', (), 'retro', rh)
    rh.append(root / 'LESSONS.jsonl', own)
    for name in ('other-a', 'other-b'):
        rh.append(root / 'LESSONS.jsonl', lessons.make(
            name, 'Synthetic other lesson.', 'control.md', 'Testing aliases', (), 'retro', rh))
    before = (root / 'LESSONS.jsonl').read_bytes()
    for name in ('bio', 'open-source'):
        assert cli(root, 'lessons', 'list', '--lane', name) == 0
        assert [json.loads(line)['id'] for line in capsys.readouterr().out.splitlines()] == [own['id']]
    assert own['id'] in {r['id'] for r in lessons.for_lane(lane, rh, n=2)}
    assert own['id'] in {r['id'] for r in retro.collect(lane, rh)['lessons']}
    assert (root / 'LESSONS.jsonl').read_bytes() == before
    evidence = root / 'control.md'
    evidence.write_text('Synthetic evidence.')
    added = lessons.add(root, rh, lane='bio', lesson='Another synthetic lesson.',
                        evidence=str(evidence), applies_when='Testing aliases')
    assert added['lane'] == lane.name


def test_outreach_draft_has_canonical_lane_and_shared_history(renamed, monkeypatch, capsys):
    root, lane = renamed
    draft = root / 'draft.txt'
    draft.write_text('A synthetic draft for alias testing.')
    monkeypatch.setenv('RH_DRAFT_ARCHIVE', str(root / 'archive'))
    for name in ('bio', 'open-source'):
        assert cli(root, 'outreach', 'draft', name, '--channel', 'linkedin', '--to', 'Fixture',
                   '--purpose', 'Synthetic alias test', '--file', str(draft)) == 0
    capsys.readouterr()
    rows = rh.rows(lane / 'OUTREACH.jsonl')
    assert len(rows) == 2 and {r['lane'] for r in rows} == {lane.name}
    for name in ('bio', 'open-source'):
        assert cli(root, 'outreach', 'status', name, '--json') == 0
        assert len(json.loads(capsys.readouterr().out)) == 2


def test_bughunt_alias_writes_canonical_coverage_ledger(renamed, capsys):
    root, lane = renamed
    doc = dict(target='fixture/tool', commit='a' * 40, round='r1',
               units=[dict(unit='fixture.py', bug_class='boundary', status='covered')])
    evidence = root / 'coverage.json'
    evidence.write_text(json.dumps(doc))
    assert cli(root, 'bughunt', 'coverage', 'bio', 'record', str(evidence)) == 0
    capsys.readouterr()
    assert len(rh.rows(lane / 'COVERAGE.jsonl')) == 1
    for name in ('bio', 'open-source'):
        assert cli(root, 'bughunt', 'coverage', name, 'show', 'fixture/tool') == 0
        assert capsys.readouterr().out.startswith('1 rounds at aaaaaaaaaa;')


def test_result_logger_resolves_old_lane_name(renamed, monkeypatch):
    root, lane = renamed
    monkeypatch.setenv('RH_ROOT', str(root))
    logger = load_tool('alias_log_result', 'harness/tools/lane-yield/log_result.py')
    assert logger.resolve_ledger('bio') == (lane / 'RESULTS.jsonl', None)
    assert logger.resolve_ledger('open-source') == (lane / 'RESULTS.jsonl', None)


def test_dangling_alias_is_reported_by_listing_and_commands(renamed, monkeypatch, capsys):
    root, lane = renamed
    (lane.parent / 'missing-alias').symlink_to('absent', target_is_directory=True)
    assert list(rh.lane_dirs(root)) == [lane]
    assert 'dangling lane alias:' in capsys.readouterr().err
    assert cli(root, 'ideas', 'depth', 'missing-alias') == 2
    assert 'rh: dangling lane alias:' in capsys.readouterr().err
    monkeypatch.setattr(intake_all, 'ROOT', root)
    monkeypatch.setenv('RH_INTAKE_LANES', 'missing-alias,bio')
    assert intake_all.lanes() == [lane.name]
    assert 'dangling lane alias:' in capsys.readouterr().err


def test_alias_loop_and_targets_outside_lanes_are_command_errors(renamed):
    root, lane = renamed
    (lane.parent / 'loop').symlink_to('loop', target_is_directory=True)
    with pytest.raises(ValueError, match='invalid lane alias'):
        rh.resolve_lane(root, 'loop')
    (lane.parent / 'outside').symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='must target a lane directory'):
        rh.resolve_lane(root, 'outside')
