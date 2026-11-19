"""Synthetic receipt joins, outcome semantics, ranking and daily publication behavior."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


@pytest.fixture
def setup_reader(tmp_path):
    roles = load('scorer_roles', 'model-roles.py')
    adapters = load('scorer_adapters', 'outcome_adapters.py')
    receipts = tmp_path / 'receipts'
    receipts.mkdir()
    for job, role in [('designer', 'design'), ('critic', 'judge'), ('reviewer', 'review'), ('author', 'builder')]:
        (receipts / f'{job}.log.selection.json').write_text(json.dumps(dict(
            model='claude-fable-5-2', role=role, job=job, made_by='synthetic', utc='2026-01-01')))
    reader = adapters.Outcomes(adapters.Receipts(receipts), roles.canon, roles.obs)
    return reader, roles, receipts


@pytest.mark.parametrize('kind,job,positive,negative', [
    ('design', 'designer', {'referee': 'HOLDS WITH CAVEATS'}, {'referee': 'FAILS'}),
    ('judge', 'critic', {'judge_outcome': 'confirmed'}, {'judge_outcome': 'overturned'}),
    ('review', 'reviewer', {'plant_caught': True}, {'plant_caught': False}),
    ('pull-request', 'author', {'merged_at': '2026-01-02', 'state': 'closed'}, {'state': 'closed'}),
])
def test_each_adapter_held_and_not_held(setup_reader, tmp_path, kind, job, positive, negative):
    reader, _, _ = setup_reader
    path = tmp_path / 'outcomes.jsonl'
    write_rows(path, [dict(id='a', source_kind=kind, job=job, date='2026-01-02', **positive),
                      dict(id='b', source_kind=kind, job=job, date='2026-01-03', **negative)])
    reader.read(path)
    assert [r['outcome'] for r in reader.observations.values()] == ['held', 'overturned']
    assert all(r['model'] == 'anthropic/claude-fable-5.2' for r in reader.observations.values())
    assert reader.stats[kind]['resolved'] == 2
    assert all(r['role'] == r['pick_role'] for r in reader.observations.values())


def test_ideation_scores_admission_and_prior_art_but_not_engineering_stops(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'IDEAS.jsonl'
    write_rows(path, [
        dict(id='a', event='add', job='designer', status='new', created='2026-01-01'),
        dict(id='a', status='testing', revised='2026-01-02'),
        dict(id='a', status='closed', close_kind='bar-failed', revised='2026-01-03'),
        dict(id='b', job='designer', status='closed', close_kind='prior-art', revised='2026-01-03'),
        dict(id='c', job='designer', status='closed', close_kind='infeasible', revised='2026-01-03'),
    ])
    reader.read(path)
    assert [r['outcome'] for r in reader.observations.values()] == ['held', 'overturned']
    assert reader.stats['ideation'] == dict(resolved=2, pending=1, unlinked=0)


def test_unlinked_or_conflicting_receipts_never_use_model_prose(setup_reader, tmp_path):
    reader, _, receipts = setup_reader
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(id='missing', job='absent', model='claude-opus-5-5', referee='HOLDS', utc='2026-01-02')])
    reader.read(path)
    assert not reader.observations
    assert reader.stats['design']['unlinked'] == 1
    other = receipts / 'other.selection.json'
    other.write_text(json.dumps(dict(job='designer', model='gpt-6-astra', role='design')))
    adapters = load('conflict_adapters', 'outcome_adapters.py')
    assert adapters.Receipts(receipts).get('designer') is None


def test_legacy_receipt_filename_supplies_job_and_zero_exit_does_not_score(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    (receipts / 'old.log.selection.json').write_text(json.dumps(dict(model='gpt-6-astra', role='design')))
    adapters = load('old_adapters', 'outcome_adapters.py')
    index = adapters.Receipts(receipts)
    assert index.get('old')['role'] == 'design'
    reader = adapters.Outcomes(index, roles.canon, roles.obs)
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(job='old', exit_code=0, utc='2026-01-02')])
    reader.read(path)
    assert not reader.observations and reader.stats['design']['pending'] == 1


def test_new_model_enters_unscored_and_can_move_only_with_existing_evidence_rule(setup_reader, tmp_path, monkeypatch):
    reader, roles, _ = setup_reader
    new = roles.canon('claude-fable-5-3')
    assert new != roles.canon('claude-fable-5-1')
    path = tmp_path / 'ledger.jsonl'
    write_rows(path, [roles.obs('synthetic', 'a', new, 'design', 'held', '2026-01-01', ['fixture'], 'synthetic')])
    monkeypatch.setattr(roles, 'LEDGER', path)
    data = roles.recompute(write=False)
    assert data['roles']['design'][-1] == 'claude-fable-5-3'
    page = tmp_path / 'LEADERBOARD.md'
    roles.public(data, page)
    # 11-19: after the two seeds and the six agy candidates (three Flash tiers, three Gemini 4).
    assert '| design | claude-fable-5-3 | 9 | - | - |' in page.read_text()
    strong = {'design': {new: dict(n=100, k=100, days={'2026-01-01', '2026-01-02'})}}
    assert roles.rank('design', strong)[0][0] == new
    assert roles.SEED['judge'] == roles.SEED['review']


def test_never_seen_provider_model_round_trips_through_fresh_process(setup_reader, tmp_path, monkeypatch):
    _, roles, _ = setup_reader
    new = roles.canon('example/model-v2')
    path = tmp_path / 'ledger.jsonl'
    write_rows(path, [roles.obs('synthetic', 'b', new, 'review', 'held', '2026-01-01', ['fixture'], 'synthetic')])
    monkeypatch.setattr(roles, 'LEDGER', path)
    roles_path = tmp_path / 'roles.json'
    roles.write_roles(roles.recompute(write=False), roles_path)
    env = dict(os.environ, MODEL_LEDGER=str(path), RH_ROLES_FILE=str(roles_path))
    result = subprocess.run([sys.executable, str(HERE / 'model-roles.py'), 'public', '--output', str(tmp_path / 'public.md')], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'example/model-v2' in (tmp_path / 'public.md').read_text()


def test_ingest_receipts_is_idempotent_and_reversals_supersede(setup_reader, tmp_path, monkeypatch):
    _, roles, receipts = setup_reader
    outcomes = tmp_path / 'outcomes'
    outcomes.mkdir()
    source = outcomes / 'test.jsonl'
    ledger = tmp_path / 'ledger.jsonl'
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('MODEL_OUTCOMES_ROOT', str(outcomes))
    monkeypatch.delenv('RH_EVIDENCE_ROOT', raising=False)
    monkeypatch.setattr(roles, 'LEDGER', ledger)
    write_rows(source, [dict(id='one', source_kind='design', job='designer', referee='HOLDS', utc='2026-01-02')])
    assert len(roles.ingest()[0]) == 1
    assert roles.ingest()[0] == []
    write_rows(source, [dict(id='one', source_kind='design', job='designer', referee='FAILS', utc='2026-01-03')])
    assert len(roles.ingest()[0]) == 1
    assert len(roles.validate(ledger.read_text())) == 1
    assert roles.validate(ledger.read_text())[0]['outcome'] == 'overturned'


def test_daily_dry_run_changes_only_scratch(setup_reader, tmp_path):
    _, _, receipts = setup_reader
    outcomes = tmp_path / 'outcomes'
    outcomes.mkdir()
    write_rows(outcomes / 'results.jsonl', [dict(id='a', source_kind='design', job='designer', referee='HOLDS', date='2026-01-02')])
    repo = HERE.parent
    before = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo)
    page = (repo / 'LEADERBOARD.md').read_bytes()
    roles_path, ledger = tmp_path / 'real-roles.json', tmp_path / 'real-ledger.jsonl'
    roles_path.write_text('untouched')
    scratch = tmp_path / 'scratch'
    env = dict(os.environ, MODEL_OUTCOMES_ROOT=str(outcomes), RH_LAUNCH_RECEIPTS=str(receipts),
               MODEL_LEDGER=str(ledger), RH_ROLES_FILE=str(roles_path))
    env.pop('RH_EVIDENCE_ROOT', None)
    result = subprocess.run(['/bin/zsh', str(HERE / 'daily.sh'), '--dry-run', '--scratch-dir', str(scratch)], cwd=repo, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo) == before
    assert (repo / 'LEADERBOARD.md').read_bytes() == page
    assert roles_path.read_text() == 'untouched' and not ledger.exists()
    assert 'claude-fable-5-2' in (scratch / 'LEADERBOARD.md').read_text()


def test_design_link_follows_run_spec_to_design_receipt(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    (receipts / 'runner.log.selection.json').write_text(json.dumps(dict(model='gpt-6-astra', role='builder')))
    (receipts / 'runner.md').write_text('Working dir: /synthetic/run\nRead /synthetic/designer/DESIGN.md first.\n')
    adapters = load('links_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts), roles.canon, roles.obs)
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(id='result', link='/synthetic/run/claim', referee='HOLDS', utc='2026-01-02')])
    reader.read(path)
    observation = next(iter(reader.observations.values()))
    assert observation['job'] == 'designer' and observation['pick_role'] == 'design'


def test_labelled_referee_markdown_and_unlinked_verdict(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'test.verdict.md'
    path.write_text('AUDIT: HOLDS WITH CAVEATS\nDesign job: designer\nJudge job: critic\nJudge outcome: overturned\nDate: 2026-01-02\n')
    reader.read(path)
    assert {r['pick_role']: r['outcome'] for r in reader.observations.values()} == dict(design='held', judge='overturned')
    assert reader.stats['design']['resolved'] == 1
    path.write_text('HOLDS\nDate: 2026-01-02\n')
    reader.read(path)
    assert reader.stats['design']['unlinked'] == 1


def test_taste_decision_uses_later_disposition(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'IDEAS.jsonl'
    write_rows(path, [dict(id='one', event='promote', decider_job='critic', status='testing', created='2026-01-01'),
                      dict(id='one', event='close', mechanical=True, status='closed', close_kind='prior-art', revised='2026-01-02')])
    reader.read(path)
    assert [(r['pick_role'], r['outcome']) for r in reader.observations.values()] == [('taste', 'overturned')]


def test_malformed_input_fails_with_source_line(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'bad.jsonl'
    path.write_text('{}\nnot json\n')
    with pytest.raises(ValueError, match='bad.jsonl:2:'):
        reader.read(path)


def test_daily_step_failure_is_nonzero_and_does_not_publish(setup_reader, tmp_path):
    _, _, receipts = setup_reader
    python = tmp_path / 'failing-python'
    python.write_text('#!/bin/sh\nexit 17\n')
    python.chmod(0o755)
    scratch = tmp_path / 'scratch'
    env = dict(os.environ, PYTHON=str(python), RH_LAUNCH_RECEIPTS=str(receipts), MODEL_OUTCOMES_ROOT=str(tmp_path))
    result = subprocess.run(['/bin/zsh', str(HERE / 'daily.sh'), '--dry-run', '--scratch-dir', str(scratch)], env=env, capture_output=True)
    assert result.returncode == 17
    assert not (scratch / 'LEADERBOARD.md').exists()


def test_native_referee_batch_counts_caught_and_missed_without_self_report(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'REFEREE.jsonl'
    write_rows(path, [dict(batch='a', file='/synthetic/reviewer/verdict.json', planted=2, caught=2, fooled=0, utc='2026-01-02'),
                      dict(batch='b', file='/synthetic/reviewer/verdict.json', planted=2, caught=1, fooled=1, utc='2026-01-03'),
                      dict(batch='c', file='/synthetic/missing/verdict.json', referee='claude-opus-5-5', planted=1, caught=1, utc='2026-01-03')])
    reader.read(path)
    assert [r['outcome'] for r in reader.observations.values()] == ['held', 'overturned']
    assert reader.stats['review']['unlinked'] == 1


def test_ingest_retains_distinct_long_source_paths_and_multiple_reversals(setup_reader, tmp_path, monkeypatch):
    _, roles, receipts = setup_reader
    outcomes = tmp_path / 'outcomes'
    outcomes.mkdir()
    source = outcomes / 'results.jsonl'
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('MODEL_OUTCOMES_ROOT', str(outcomes))
    monkeypatch.setattr(roles, 'LEDGER', tmp_path / 'ledger.jsonl')
    for outcome in ('HOLDS', 'FAILS', 'HOLDS', 'FAILS'):
        write_rows(source, [dict(id='a' * 160 + suffix, source_kind='design', job='designer', referee=outcome, date='2026-01-02') for suffix in ('one', 'two')])
        assert len(roles.ingest()[0]) == 2
        active = roles.validate(roles.LEDGER.read_text())
        assert len(active) == 2 and len({r['case'] for r in active}) == 2
        assert {r['outcome'] for r in active} == ({'held'} if outcome == 'HOLDS' else {'overturned'})


def test_upstream_native_cache_keeps_unlinked_and_pending_separate(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / '.upstream-prs.json'
    path.write_text(json.dumps(dict(fetched='2026-01-02', prs=[
        dict(url='https://example.test/pr/1', state='closed', merged_at='2026-01-01', opened_by_job='author'),
        dict(url='https://example.test/pr/2', state='closed', merged_at=None, opened_by_job='author'),
        dict(url='https://example.test/pr/3', state='closed', merged_at=None),
        dict(url='https://example.test/pr/4', state='open', merged_at=None),
    ])))
    reader.read(path)
    assert [r['outcome'] for r in reader.observations.values()] == ['held', 'overturned']
    assert reader.stats['pull-request'] == dict(resolved=2, pending=1, unlinked=1)
    assert [r['day'] for r in reader.observations.values()] == ['2026-01-01', '2026-01-02']


def test_daily_lands_only_page_in_worktree_and_skips_unchanged_page(setup_reader, tmp_path):
    import shutil
    _, _, receipts = setup_reader
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'leaderboard').mkdir()
    (repo / 'rstack/tools').mkdir(parents=True)
    for name in ('daily.sh', 'model-roles.py', 'model-eval.py', 'outcome_adapters.py'):
        shutil.copy2(HERE / name, repo / 'leaderboard' / name)
    shutil.copy2(HERE.parent / 'rstack/tools/egress-gate', repo / 'rstack/tools/egress-gate')
    (repo / 'LEADERBOARD.md').write_text('Initial snapshot\n')
    git = shutil.which('git')
    def run_git(*args):
        return subprocess.check_output([git, '-C', str(repo), *args], stderr=subprocess.STDOUT).decode().strip()
    run_git('init', '-b', 'main')
    run_git('config', 'user.name', 'Fixture')
    run_git('config', 'user.email', 'fixture@example.invalid')
    run_git('add', '.')
    run_git('commit', '-m', 'Initial fixture')
    initial = run_git('rev-parse', 'HEAD')
    remote = tmp_path / 'upstream.git'
    subprocess.run([git, 'clone', '--bare', str(repo), str(remote)], check=True, capture_output=True)
    run_git('remote', 'add', 'origin', str(remote))
    outcomes = tmp_path / 'outcomes'
    outcomes.mkdir()
    write_rows(outcomes / 'results.jsonl', [dict(id='one', source_kind='design', job='designer', referee='HOLDS', date='2026-01-02')])
    binary = tmp_path / 'bin'
    binary.mkdir()
    # All Git operations are real except push, which is recorded and never executed.
    wrapper = binary / 'git'
    wrapper.write_text('#!' + sys.executable + '\nimport json, os, sys\n'
                       'if "push" in sys.argv[1:]:\n'
                       ' with open(os.environ["PUSH_CALLS"], "a") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                       ' sys.exit(0)\n'
                       'os.execv(os.environ["REAL_GIT"], [os.environ["REAL_GIT"], *sys.argv[1:]])\n')
    wrapper.chmod(0o755)
    state = tmp_path / 'state'
    calls = tmp_path / 'push-calls.jsonl'
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], REAL_GIT=git, PUSH_CALLS=str(calls),
               PYTHON=sys.executable, MODEL_OUTCOMES_ROOT=str(outcomes), RH_LAUNCH_RECEIPTS=str(receipts),
               MODEL_STATE=str(state), MODEL_LEDGER=str(state / 'ledger.jsonl'), RH_ROLES_FILE=str(state / 'roles.json'))
    command = ['/bin/zsh', str(repo / 'leaderboard/daily.sh')]
    blocked = dict(env, RSTACK_EGRESS_DIR=str(tmp_path / 'missing-egress-config'))
    result = subprocess.run(command, env=blocked, text=True, capture_output=True)
    assert result.returncode == 2 and not calls.exists()
    assert run_git('rev-parse', 'HEAD') == initial
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    landing = state / 'landing'
    landed = subprocess.check_output([git, '-C', str(landing), 'rev-parse', 'HEAD']).decode().strip()
    assert landed != initial and run_git('rev-parse', 'HEAD') == initial
    assert subprocess.check_output([git, '-C', str(landing), 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD']).decode().strip() == 'LEADERBOARD.md'
    assert len(calls.read_text().splitlines()) == 1
    assert json.loads(calls.read_text())[1:3] == [str(landing), 'push']
    # Simulate the intercepted publication having landed by fetching its commit locally.
    subprocess.run([git, '--git-dir', str(remote), 'fetch', str(landing), 'HEAD:refs/heads/main'], check=True, capture_output=True)
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'unchanged' in result.stdout and len(calls.read_text().splitlines()) == 1
    assert subprocess.check_output([git, '-C', str(landing), 'rev-parse', 'HEAD']).decode().strip() == landed


def test_taste_artifact_link_uses_receipt_role_to_disambiguate(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    (receipts / 'taster.log.selection.json').write_text(json.dumps(dict(model='gpt-6-astra', role='taste')))
    (receipts / 'taster.md').write_text('Directory: /synthetic/claim (read-only except TASTE.md).\n')
    (receipts / 'runner.log.selection.json').write_text(json.dumps(dict(model='claude-opus-5-5', role='builder')))
    (receipts / 'runner.md').write_text('Directory: /synthetic/claim\n')
    adapters = load('taste_artifact_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts), roles.canon, roles.obs)
    path = tmp_path / 'IDEAS.jsonl'
    write_rows(path, [dict(id='one', event='promote', status='testing', result_path='/synthetic/claim/result.md', created='2026-01-01'),
                      dict(id='one', event='close', status='closed', close_kind='prior-art', revised='2026-01-02')])
    reader.read(path)
    assert [(r['job'], r['model'], r['outcome']) for r in reader.observations.values()] == [('taster', 'openai/gpt-6-astra', 'overturned')]


def test_receipt_mode_never_admits_legacy_self_attributed_sources(setup_reader, tmp_path, monkeypatch):
    _, roles, receipts = setup_reader
    source = tmp_path / 'outcomes'
    source.mkdir()
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('MODEL_OUTCOMES_ROOT', str(source))
    monkeypatch.setattr(roles, 'LEDGER', tmp_path / 'ledger.jsonl')
    def legacy_reader():
        raise AssertionError('receipt mode must not admit self-attributed observations')
    monkeypatch.setattr(roles, 'ADAPTERS', {'review': legacy_reader, 'message-draft': legacy_reader})
    assert roles.ingest()[0] == []


@pytest.mark.parametrize('field,value', [
    ('job_id', 'designer'), ('source_job', 'designer'),
    ('path', '/synthetic/designer/CLAIM.md'),
    ('run_dir', '/synthetic/designer'),
    ('job', '/synthetic/_codex/designer.md'),
])
def test_native_outcome_job_keys(setup_reader, tmp_path, field, value):
    reader, _, _ = setup_reader
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(utc='2026-01-02', referee='HOLDS (independent check)', **{field: value})])
    reader.read(path)
    observation = next(iter(reader.observations.values()))
    assert observation['job'] == 'designer'
    assert observation['link_kind'] == 'receipt'


def test_round_alias_and_proposed_by_job_link(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    (receipts / 'experiment.log.selection.json').write_text(json.dumps(dict(
        model='gpt-6-astra', role='design', round='round-007')))
    adapters = load('round_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts), roles.canon, roles.obs)
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(round='round-007', referee='FAILS', utc='2026-01-02')])
    reader.read(path)
    ideas = tmp_path / 'IDEAS.jsonl'
    write_rows(ideas, [dict(id='candidate', proposed_by='/synthetic/_codex/designer.md', status='testing', created='2026-01-02')])
    reader.read(ideas)
    assert {(r['job'], r['outcome']) for r in reader.observations.values()} == {('experiment', 'overturned'), ('designer', 'held')}


def make_launch(root, job, workdir, model='claude-fable-5-2', prompt=''):
    attempt = root / job / '20260101T120000-abc'
    attempt.mkdir(parents=True)
    (attempt / 'run.sh').write_text(
        f'cd {workdir} || exit 2\nexec env RH_JOB={job} nice -n 10 python3 /harness/agent_executor.py '
        f'--backend claude --directory {workdir} --model {model} --output /synthetic/_codex/{job}.last.md\n')
    (attempt / 'prompt').write_text(prompt)
    return attempt


def test_launch_command_identity_beats_self_report_and_lower_rank_conflicts(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    launch_root = tmp_path / 'launches'
    directory = tmp_path / 'actual-run'
    directory.mkdir()
    (directory / 'REPORT.md').write_text('Model: claude-opus-5-5\nHOLDS\n')
    make_launch(launch_root, 'producer', directory)
    adapters = load('launch_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts, launch_root), roles.canon, roles.obs)
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(source_job='producer', referee='HOLDS', utc='2026-01-02')])
    reader.read(path)
    observation = next(iter(reader.observations.values()))
    assert observation['model'] == 'anthropic/claude-fable-5.2'
    assert observation['link_kind'] == 'launch-command'
    # The selected model wins even when a lower-ranked launch record disagrees.
    make_launch(launch_root, 'designer', directory, model='gpt-6-astra')
    assert adapters.Receipts(receipts, launch_root).get('designer')['link_kind'] == 'receipt'
    # A different directory with only self-report never acquires provenance.
    unknown = tmp_path / 'unknown'
    unknown.mkdir()
    (unknown / 'REPORT.md').write_text('Model: claude-fable-5-2\nHOLDS\n')
    write_rows(path, [dict(job='unknown', referee='HOLDS', model='claude-fable-5-2', utc='2026-01-02')])
    reader.read(path)
    assert reader.stats['design']['unlinked'] == 1


@pytest.mark.parametrize('tool,args', [
    ('Bash', dict(command='cd /synthetic/launched && claude -p --model claude-fable-5-2 < prompt')),
    ('Bash', dict(command='codex exec --cd /synthetic/launched -m gpt-6-astra -')),
    ('Agent', dict(model='claude-fable-5-2', prompt='Working dir: /synthetic/launched (write here). Judge the record.')),
])
def test_launching_transcript_tool_call_links(setup_reader, tmp_path, tool, args):
    _, _, receipts = setup_reader
    transcripts = tmp_path / 'transcripts'
    transcripts.mkdir()
    write_rows(transcripts / 'session.jsonl', [dict(type='assistant', message=dict(role='assistant', content=[
        dict(type='tool_use', name=tool, input=args)]))])
    adapters = load('transcript_adapters', 'outcome_adapters.py')
    entry = adapters.Receipts(receipts, transcript_root=transcripts).get('launched')
    assert entry['link_kind'] == 'transcript-call'
    assert entry['model'] == args.get('model', 'gpt-6-astra' if 'codex' in args.get('command', '') else 'claude-fable-5-2')


def test_transcript_mentions_and_echoes_do_not_link(setup_reader, tmp_path):
    _, _, receipts = setup_reader
    transcripts = tmp_path / 'transcripts'
    transcripts.mkdir()
    write_rows(transcripts / 'session.jsonl', [dict(type='assistant', message=dict(content=[
        dict(type='text', text='claude -p --model claude-fable-5-2'),
        dict(type='tool_use', name='Bash', input=dict(command='echo claude -p --model claude-fable-5-2')),
        dict(type='tool_use', name='Agent', input=dict(model='claude-fable-5-2', prompt='Maybe inspect /synthetic/unknown later.')),
    ]))])
    adapters = load('mention_adapters', 'outcome_adapters.py')
    assert set(adapters.Receipts(receipts, transcript_root=transcripts).jobs) == {'designer', 'critic', 'reviewer', 'author'}


def test_injected_lessons_are_not_job_inputs(setup_reader, tmp_path):
    _, _, receipts = setup_reader
    launches = tmp_path / 'launches'
    directory = tmp_path / 'runner'
    directory.mkdir()
    make_launch(launches, 'runner', directory, prompt=(
        '--- LESSONS THIS LANE ALREADY PAID FOR ---\n'
        'Older work /synthetic/unrelated/DESIGN.md failed.\n---\n\n'
        'The design: /synthetic/designer/DESIGN.md.\n'))
    (receipts / 'unrelated.log.selection.json').write_text(json.dumps(dict(model='gpt-6-astra', role='design')))
    adapters = load('preamble_adapters', 'outcome_adapters.py')
    index = adapters.Receipts(receipts, launches)
    assert index.design_jobs('runner') == {'designer'}
    assert index.references['runner'] == {'designer'}


def test_native_referee_follows_spec_chain_and_deduplicates_design(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    launches = tmp_path / 'launches'
    run = tmp_path / 'experiment'
    audit = tmp_path / 'audit'
    final = tmp_path / 'final'
    for directory in (run, audit, final):
        directory.mkdir()
    make_launch(launches, 'experiment', run, prompt='Run /synthetic/designer/DESIGN.md exactly as written.\n')
    make_launch(launches, 'audit', audit, model='gpt-6-astra', prompt=f'The run: {run}/CLAIM.md.\n')
    make_launch(launches, 'final', final, prompt=f'Referee records: {audit}/referee_audit.md.\n')
    (audit / 'referee_audit.md').write_text('AUDIT: FAILS\nDate: 2026-01-02\n')
    (final / 'ledger_verdict.md').write_text('HOLDS WITH CAVEATS\nDate: 2026-01-03\n')
    adapters = load('chain_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts, launches), roles.canon, roles.obs)
    reader.read(audit / 'referee_audit.md')
    reader.read(final / 'ledger_verdict.md')
    assert len(reader.observations) == 1
    row = next(iter(reader.observations.values()))
    assert (row['job'], row['outcome'], row['link_kind']) == ('designer', 'held', 'receipt')
    assert str(final / 'ledger_verdict.md') in row['evidence']


@pytest.mark.parametrize('first_line,details,expected', [
    ('AUDIT: HOLDS', 'All ruling checks reproduce independently.', 'held'),
    ('AUDIT: HOLDS WITH CAVEATS', "The judge's critical value is miscalibrated and too lenient.", 'overturned'),
    ('AUDIT: FAILS', 'The ruling fails the independent check.', 'overturned'),
])
def test_later_audit_disposes_named_judge_not_its_own_model(setup_reader, tmp_path, first_line, details, expected):
    _, roles, receipts = setup_reader
    launches = tmp_path / 'launches'
    audit = tmp_path / 'audit'
    audit.mkdir()
    make_launch(launches, 'audit', audit, model='gpt-6-astra', prompt='The judge: /synthetic/critic/JUDGEMENT.md. Independently recompute every check.\n')
    verdict = audit / 'referee_audit.md'
    verdict.write_text(first_line + '\nDate: 2026-01-02\n' + details)
    adapters = load('ruling_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts, launches), roles.canon, roles.obs)
    reader.read(verdict)
    judges = [r for r in reader.observations.values() if r['pick_role'] == 'judge']
    assert len(judges) == 1
    assert judges[0]['job'] == 'critic' and judges[0]['outcome'] == expected
    assert judges[0]['model'] == 'anthropic/claude-fable-5.2'


def test_final_result_verdict_does_not_confirm_an_earlier_judge_without_disposition(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    launches = tmp_path / 'launches'
    final = tmp_path / 'final'
    final.mkdir()
    make_launch(launches, 'final', final, prompt='Your earlier judgement: /synthetic/critic/JUDGEMENT.md. Read the final note once.\n')
    path = final / 'ledger_verdict.md'
    path.write_text('HOLDS WITH CAVEATS\nDate: 2026-01-02\nThe result survives.\n')
    adapters = load('no_blanket_confirmation', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts, launches), roles.canon, roles.obs)
    reader.read(path)
    assert not [r for r in reader.observations.values() if r['pick_role'] == 'judge']
    (final / 'JUDGEMENT.md').write_text('VERDICT: forward after one fix. Both wrong phrases come from my own earlier edits.\n')
    reader.read(path)
    assert [r['outcome'] for r in reader.observations.values() if r['pick_role'] == 'judge'] == ['overturned']


def test_interim_full_panel_verdict_stays_pending(setup_reader, tmp_path):
    reader, _, _ = setup_reader
    path = tmp_path / 'partial.verdict.md'
    path.write_text('HOLDS WITH CAVEATS (INTERIM: 4 of 20 evaluated)\nDesign job: designer\nDate: 2026-01-02\n')
    reader.read(path)
    assert not reader.observations
    assert reader.stats['design']['pending'] == 1


def test_public_merge_retains_scored_and_observation_history(setup_reader, tmp_path, monkeypatch):
    _, roles, _ = setup_reader
    ledger = tmp_path / 'ledger.jsonl'
    new = roles.canon('claude-fable-5-3')
    write_rows(ledger, [roles.obs('synthetic', 'recent', new, 'design', 'held', '2026-01-03', ['fixture'], 'synthetic')])
    monkeypatch.setattr(roles, 'LEDGER', ledger)
    page = tmp_path / 'public.md'
    historical = ('| taste | claude-opus-5-5 | 1 | 0.333 | 0.097 | 2026-01-01 |\n'
                  '| taste | claude-opus-5-5 | 0, 4 | 2026-01-01 |\n')
    page.write_text(historical)
    data = roles.recompute(write=False)
    data['updated'] = '2026-01-03T00:00:00Z'
    roles.public(data, page)
    for line in historical.splitlines():
        assert line in page.read_text()
    assert '| design | claude-fable-5-3 | 9 | - | - | 2026-01-03 |' in page.read_text()
    once = page.read_text()
    roles.public(data, page)
    assert page.read_text() == once
    restored = roles.bootstrap(page)
    assert restored['roles']['design'][-1] == 'claude-fable-5-3'


def test_entered_role_is_public_even_without_resolved_observation(setup_reader, tmp_path, monkeypatch):
    _, roles, receipts = setup_reader
    directory = tmp_path / 'new-designer'
    directory.mkdir()
    (directory / 'IDEAS.md').write_text('Ranked choices.\n')
    (directory / 'DESIGN.md').write_text('Frozen plan.\n')
    launches = tmp_path / 'launches'
    make_launch(launches, 'new-designer', directory, prompt='Pick one idea and write DESIGN.md and IDEAS.md.\n')
    monkeypatch.setenv('RH_LAUNCH_RECEIPTS', str(receipts))
    monkeypatch.setenv('MODEL_LAUNCH_ROOT', str(launches))
    monkeypatch.delenv('RH_EVIDENCE_ROOT', raising=False)
    monkeypatch.delenv('MODEL_OUTCOMES_ROOT', raising=False)
    monkeypatch.setattr(roles, 'LEDGER', tmp_path / 'empty.jsonl')
    data = roles.recompute(write=False)
    for role in ('taste', 'design', 'ideation'):
        assert 'claude-fable-5-2' in data['roles'][role]
        assert 'claude-fable-5-2' not in data['evidence'][role]


def test_old_prompt_output_path_links_native_result_to_selected_role(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    (receipts / 'worker.log.selection.json').write_text(json.dumps(dict(model='gpt-6.1-sol', role='batch')))
    (receipts / 'worker.log.prompt').write_text('When the bar clears, write /synthetic/claims/target/CLAIM.md and stop.\n')
    adapters = load('prompt_output_adapters', 'outcome_adapters.py')
    reader = adapters.Outcomes(adapters.Receipts(receipts), roles.canon, roles.obs)
    path = tmp_path / 'RESULTS.jsonl'
    write_rows(path, [dict(link='/synthetic/claims/target', referee='HOLDS (independent referee)', utc='2026-01-02')])
    reader.read(path)
    row = next(iter(reader.observations.values()))
    assert (row['job'], row['pick_role'], row['link_kind']) == ('worker', 'batch', 'receipt')


def test_independent_claim_verdict_links_worker_receipt_from_old_prompt(setup_reader, tmp_path):
    _, roles, receipts = setup_reader
    claim = tmp_path / 'queue/claims/target'
    claim.mkdir(parents=True)
    (receipts / 'worker.log.selection.json').write_text(json.dumps(dict(model='gpt-6.1-sol', role='batch')))
    (receipts / 'worker.log.prompt').write_text(f'When done, write {claim}/CLAIM.md and stop.\n')
    (receipts / 'checker.log.selection.json').write_text(json.dumps(dict(model='gpt-6-astra', role='mechanical', utc='2026-01-02')))
    (receipts / 'checker.md').write_text(f'Your directory: {claim} (write only here). Write VERDICT.md.\n')
    (claim / 'VERDICT.md').write_text('HOLDS WITH CAVEATS\nReferee: claimed-model-9-9\n')
    adapters = load('claim_receipt_adapters', 'outcome_adapters.py')
    observations, stats = adapters.collect(None, receipts, roles.canon, roles.obs, outcomes_root=tmp_path)
    assert stats['result']['resolved'] == 1
    assert [(r['job'], r['model'], r['link_kind']) for r in observations] == [('worker', 'openai/gpt-6.1-sol', 'receipt')]
    assert observations[0]['pick_role'] == 'batch'


def test_codex_launching_transcript_function_call(setup_reader, tmp_path):
    _, _, receipts = setup_reader
    transcripts = tmp_path / 'transcripts'
    transcripts.mkdir()
    write_rows(transcripts / 'session.jsonl', [dict(type='response_item', payload=dict(
        type='function_call', name='exec_command', arguments=json.dumps(dict(
            cmd='codex exec --cd /synthetic/experiment -m gpt-6-astra -'))))])
    adapters = load('codex_transcript_adapters', 'outcome_adapters.py')
    row = adapters.Receipts(receipts, transcript_root=transcripts).get('experiment')
    assert row['model'] == 'gpt-6-astra' and row['link_kind'] == 'transcript-call'
