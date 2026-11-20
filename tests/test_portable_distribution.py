"""Extraction boundary regressions: public exports, config, toy preview and local jobs."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from unittest.mock import Mock

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'harness'))
import rh
import sweep
import outreach
import settings
import worker_models

spec = importlib.util.spec_from_file_location('model_roles_public', REPO / 'leaderboard/model-roles.py')
roles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roles)


def data():
    return {'updated': '2026-01-02T03:04:05+00:00',
            'roles': {'batch': ['gpt-6.1-sol']},
            'evidence': {'batch': {'gpt-6.1-sol': {'rate': .8, 'low': .6, 'n': 20}}},
            'prompt': 'PRIVATE_SENTINEL', 'why': 'PRIVATE_SENTINEL',
            'overrides': {'private': 'PRIVATE_SENTINEL'}, 'cost_usd': 12345}


def test_public_export_keeps_only_routing_scores_and_date(tmp_path):
    path = tmp_path / 'LEADERBOARD.md'
    roles.public(data(), path)
    text = path.read_text()
    assert 'PRIVATE_SENTINEL' not in text and '12345' not in text
    assert '| batch | gpt-6.1-sol | 1 | 0.8 | 20 | - | - | 2026-01-02 |' in text
    restored = roles.bootstrap(path)
    assert restored['roles'] == {'batch': ['gpt-6.1-sol']}
    path.write_text('PRIVATE_SENTINEL')
    assert restored['roles']['batch'] == ['gpt-6.1-sol']


@pytest.mark.parametrize('field,value', [('role', 'unregistered'), ('model', 'unregistered'),
                                       ('model', 'bad|cell'), ('model', 'bad\ncell')])
def test_export_rejects_unregistered_or_unsafe_names_before_writing(tmp_path, field, value):
    source = data()
    if field == 'role':
        source['roles'] = {value: ['gpt-6.1-sol']}
    else:
        source['roles'] = {'batch': [value]}
    path = tmp_path / 'export.md'
    path.write_text('existing export')
    with pytest.raises(ValueError):
        roles.public(source, path)
    assert path.read_text() == 'existing export'


@pytest.mark.parametrize('value', [True, -1, 2, float('nan'), float('inf'), 'private'])
def test_export_rejects_non_scores(tmp_path, value):
    source = data()
    source['evidence']['batch']['gpt-6.1-sol']['rate'] = value
    with pytest.raises(ValueError):
        roles.public(source, tmp_path / 'export.md')
    assert not (tmp_path / 'export.md').exists()


@pytest.mark.parametrize('positions', [[0], [-1], [2], [1, 1], [1, 3]])
def test_bootstrap_rejects_missing_or_repeated_rank(tmp_path, positions):
    path = tmp_path / 'export.md'
    models = ['gpt-6.1-sol', 'gpt-6-astra']
    path.write_text('\n'.join(f'| batch | {models[i]} | {p} | - | - | 2026-01-02 |'
                              for i, p in enumerate(positions)))
    with pytest.raises(ValueError):
        roles.bootstrap(path)


def test_current_snapshot_routes_are_consumable_without_private_state(tmp_path):
    restored = roles.bootstrap(REPO / 'LEADERBOARD.md')
    path = tmp_path / 'roles.json'
    roles.write_roles(restored, path)
    result = worker_models.select('batch', 'codex', path=path)
    assert result['model'] == restored['roles']['batch'][0]
    assert result['source'] == 'leaderboard'
    with pytest.raises(ValueError, match='no compatible'):
        worker_models.select('batch', 'claude', path=path)


def test_ranking_needs_five_graded_everyday_tasks_then_ranks_by_them():
    # 11-19: n<5 ranks below every model with data; at n>=5 the everyday record decides, not the seed order.
    a, b = roles.SEED['batch']
    def observations(n, k, days):
        return {'n': n, 'k': k, 'days': set(days)}
    few = {'batch': {b: observations(4, 4, ['2026-01-01', '2026-01-02'])}}
    assert roles.rank('batch', few)[0][0] == a
    some = {'batch': {b: observations(5, 4, ['2026-01-01'])}}
    assert roles.rank('batch', some)[0][0] == b
    both = {'batch': {a: observations(50, 30, ['2026-01-01']), b: observations(50, 45, ['2026-01-01'])}}
    assert roles.rank('batch', both)[0][:2] == [b, a]


def test_killed_at_own_bar_is_not_a_taste_failure(tmp_path, monkeypatch):
    lane = tmp_path / 'lanes/toy'
    lane.mkdir(parents=True)
    rows = [dict(id='idea', event='promote', status='testing', decided_by='claude-opus-5-5',
                 created='2026-01-01T00:00:00+00:00'),
            dict(id='idea', event='close', status='closed', close_kind='bar-failed',
                 closed_reason='prior art in background, but killed on its frozen metric',
                 created='2026-01-01T00:00:00+00:00', revised='2026-01-02T00:00:00+00:00')]
    ledger = lane / 'IDEAS.jsonl'
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(roles, 'RH_LANES', tmp_path / 'lanes')
    observations, pending, _ = roles.from_rh()
    assert not observations and pending == 1
    rows[1]['close_kind'] = 'prior-art'
    ledger.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    observations, pending, _ = roles.from_rh()
    assert len(observations) == 1 and observations[0]['outcome'] == 'overturned' and pending == 0


def test_bad_private_ledger_cannot_silently_become_a_ranking(tmp_path, monkeypatch):
    path = tmp_path / 'ledger.jsonl'
    path.write_text('{"model": "gpt-6.1-sol"}\n')
    monkeypatch.setattr(roles, 'LEDGER', path)
    with pytest.raises(ValueError, match='missing'):
        roles.recompute(write=False)


def test_ingest_requires_explicit_evidence_root(monkeypatch, capsys):
    monkeypatch.delenv('RH_EVIDENCE_ROOT', raising=False)
    assert roles.main(['ingest']) == 2
    assert 'requires explicit' in capsys.readouterr().err


def test_configured_taste_routes_replace_home_executable(tmp_path, monkeypatch):
    path = tmp_path / 'roles.json'
    path.write_text(json.dumps({'roles': {'taste': ['fixture-reviewer']}}))
    monkeypatch.setattr(rh, 'ROLES_FILE', path)
    monkeypatch.setattr(rh.subprocess, 'run', Mock(side_effect=AssertionError('no executable lookup')))
    assert rh.taste_models() == ('fixture-reviewer', 'claude-science')


def test_settings_commands_are_argument_vectors(monkeypatch):
    monkeypatch.setenv('RH_VOICE_COMMAND', '"/tmp/check with spaces" --mode "a b"')
    assert settings.command('RH_VOICE_COMMAND', 'unused') == ['/tmp/check with spaces', '--mode', 'a b']
    monkeypatch.setenv('RH_POD_LANES', 'toy,second_lane')
    assert settings.names('RH_POD_LANES') == {'toy', 'second_lane'}
    monkeypatch.setenv('RH_POD_LANES', '../escape')
    with pytest.raises(ValueError):
        settings.names('RH_POD_LANES')


def test_missing_voice_and_science_commands_refuse(monkeypatch):
    monkeypatch.setattr(outreach, 'VOICE_COMMAND', ['/not/an/installed/checker'])
    monkeypatch.setattr(outreach, 'SCIENCE_COMMAND', ['/not/an/installed/checker'])
    assert outreach.voice('A question?', 'email')
    assert outreach.science_checks('A question?', [])


def test_example_policy_parses_with_both_toml_readers(monkeypatch):
    folder = REPO / 'examples/toy-lane'
    for path in folder.glob('*.toml'):
        normal = rh.config(path)
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, 'tomllib', None)
            assert rh.config(path) == normal
    cfg = sweep.load(folder, rh)
    assert cfg['enabled'] and cfg['cores'] == 1
    for stage in ('search', 'read', 'kill'):
        text = sweep.generate(stage, folder, cfg, sweep.reports(cfg, '2026-01-02'), '2026-01-02', [])
        assert (folder / 'RULES.md').read_text() in text


def test_toy_quickstart_previews_and_refuses_overwrite(tmp_path):
    root = tmp_path / 'runtime'
    command = [sys.executable, str(REPO / 'examples/toy_demo.py'), '--root', str(root)]
    run = subprocess.run(command, text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert 'DRY RUN' in run.stdout and 'SEALED' not in run.stderr
    assert not list(root.glob('**/*.worker.log'))
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    run = subprocess.run(command, text=True, capture_output=True, timeout=10)
    assert run.returncode == 2 and 'already exists' in run.stderr
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_intake_scheduler_uses_code_path_and_explicit_root(tmp_path, monkeypatch):
    import intake_all
    (tmp_path / 'lanes/toy').mkdir(parents=True)
    (tmp_path / 'lanes/toy/INTAKE.toml').write_text('')
    fake = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(intake_all, 'ROOT', tmp_path)
    monkeypatch.setattr(intake_all.subprocess, 'run', fake)
    assert intake_all.main() == 0
    argv = fake.call_args.args[0]
    assert str(REPO / 'harness/rh.py') in argv
    assert argv[argv.index('--root') + 1] == str(tmp_path)


def test_scheduler_templates_are_inactive_placeholders():
    for path in (REPO / 'harness/templates').glob('*.plist.template'):
        data = plistlib.loads(path.read_bytes())
        assert data['ProgramArguments'][0] == '@PYTHON@'
        assert '@REPO_ROOT@' in data['ProgramArguments'][1]
        assert data['EnvironmentVariables']['RH_ROOT'] == '@RH_ROOT@'


def test_ideation_credits_admission_even_after_a_fair_kill(tmp_path, monkeypatch):
    lane = tmp_path / 'lanes/toy'
    lane.mkdir(parents=True)
    rows = [dict(id='idea', event='add', claim='synthetic candidate', proposed_by='gpt-6-astra',
                 status='new', created='2026-01-01T00:00:00+00:00'),
            dict(id='idea', event='promote', status='testing', revised='2026-01-02T00:00:00+00:00'),
            dict(id='idea', event='close', status='closed', close_kind='bar-failed',
                 revised='2026-01-03T00:00:00+00:00')]
    (lane / 'IDEAS.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    monkeypatch.setattr(roles, 'RH_LANES', tmp_path / 'lanes')
    observations, pending, _ = roles.from_ideation()
    assert len(observations) == 1 and observations[0]['outcome'] == 'held' and pending == 0


def test_review_adapter_tracks_revised_bytes_from_explicit_root(tmp_path, monkeypatch):
    for version, sha, verdicts in [(1, 'a' * 64, [('gpt-6-astra', 'FLAG'), ('claude-opus-5-5', 'PASS')]),
                                    (2, 'b' * 64, [('gpt-6-astra', 'PASS')])]:
        row = dict(file='toy-proof', date=f'2026-01-0{version}', sha256=sha,
                   reviews=[dict(model=m, verdict=v) for m, v in verdicts])
        (tmp_path / f'{version}.reviews.json').write_text(json.dumps(row))
    monkeypatch.setattr(roles, 'REVIEW_ROOT', tmp_path)
    observations, _, _ = roles.from_reviews()
    earliest = {row['model']: row['outcome'] for row in observations if row['date'] == '2026-01-01'}
    assert earliest == {'openai/gpt-6-astra': 'held', 'anthropic/claude-opus-5.5': 'overturned'}


def test_draft_adapter_ignores_recipient_content(tmp_path, monkeypatch):
    path = tmp_path / 'draft-outcomes.jsonl'
    path.write_text(json.dumps(dict(model='claude-opus-5-5', outcome='sent_as_drafted',
                     utc='2026-01-01T00:00:00+00:00', draft_sha='a' * 64,
                     channel='email', to='PRIVATE_SENTINEL')) + '\n')
    monkeypatch.setattr(roles, 'DRAFTS_LOG', path)
    observations, pending, _ = roles.from_drafts()
    assert len(observations) == 1 and observations[0]['pick_role'] == 'writing' and pending == 0
    assert 'PRIVATE_SENTINEL' not in json.dumps(observations)


def test_score_export_discards_private_observation_fields(tmp_path):
    path = tmp_path / 'export.md'
    observation = dict(model='gpt-6.1-sol', pick_role='batch', score=4, date='2026-01-01',
                       note='PRIVATE_SENTINEL', case='PRIVATE_SENTINEL', cost_usd=99999,
                       evidence=['PRIVATE_SENTINEL'])
    roles.public(data(), path, [observation])
    text = path.read_text()
    assert '| batch | gpt-6.1-sol | 4 | 2026-01-01 |' in text
    assert 'PRIVATE_SENTINEL' not in text and '99999' not in text
    assert roles.bootstrap(path)['roles'] == {'batch': ['gpt-6.1-sol']}


def test_failed_trash_command_keeps_the_original_file(tmp_path, monkeypatch):
    import storage
    path = tmp_path / 'retained.txt'
    path.write_text('recoverable data')
    monkeypatch.setenv('RH_TRASH_COMMAND', '/not/an/installed/trash-command')
    with pytest.raises(FileNotFoundError):
        storage.trash(path)
    assert path.read_text() == 'recoverable data'
