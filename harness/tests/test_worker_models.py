"""Model routing tests use local files and fake executors; no workers or APIs."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import worker_models as wm
import sweep


def roles(path,first='fixture-fast'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(dict(updated='2026-11-02T00:00:00Z',roles={
        'batch':[first,'fixture-second'],'mechanical':[first],'taste':['fixture-taste']},
        routes={
            'fixture-fast':{'cli':'codex','canonical':'openai/fixture-fast'},
            'fixture-second':{'cli':'codex','canonical':'openai/fixture-second'},
            'fixture-taste':{'cli':'claude','canonical':'anthropic/fixture-taste'}})))
    return path


def test_role_selection_follows_table_changes(tmp_path):
    p=roles(tmp_path/'roles.json')
    a=wm.select('batch','codex',path=p)
    roles(p,'fixture-second')
    b=wm.select('batch','codex',path=p)
    assert a['model']=='fixture-fast' and b['model']=='fixture-second'
    assert a['roles_sha256']!=b['roles_sha256']
    assert a['role']==b['role']=='batch' and a['source']=='leaderboard'


def test_even_ranked_hardcoded_model_requires_override_reason(tmp_path):
    p=roles(tmp_path/'roles.json')
    for reason in ('','  '):
        with pytest.raises(ValueError,match='hard-coded model refused'):
            wm.select('batch','codex','fixture-fast',reason,p)
    selected=wm.select('batch','codex','fixture-second','bounded compatibility experiment',p)
    assert selected['source']=='override' and selected['model_override']=='bounded compatibility experiment'


def test_missing_role_or_incompatible_route_never_falls_back(tmp_path):
    p=roles(tmp_path/'roles.json')
    for role,executor in [('missing','codex'),('batch','claude')]:
        with pytest.raises(ValueError):wm.select(role,executor,path=p)
    assert wm.select('taste', 'codex', path=p)['executor'] == 'claude'
    with pytest.raises(ValueError):wm.select('batch','codex',override='reason without model',path=p)
    p.write_text('{}')
    with pytest.raises((ValueError,KeyError)):wm.select('batch','codex',path=p)


def test_model_exclusion_cannot_be_overridden(tmp_path):
    p=roles(tmp_path/'roles.json');data=json.loads(p.read_text());data['overrides']={'batch':{'exclude':['openai/fixture-fast']}};p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='excluded'):wm.select('batch','codex',path=p)
    with pytest.raises(ValueError,match='excluded'):wm.select('batch','codex','fixture-fast','owner exception',p)


def test_selection_and_exit_receipts_bind_role_model_and_table(tmp_path):
    p=roles(tmp_path/'roles.json');log=tmp_path/'launch.log';receipt=tmp_path/'selection.json'
    args=['--role','batch','--executor','codex','--roles-file',str(p),'--log',str(log),'--receipt',str(receipt)]
    with contextlib.redirect_stdout(io.StringIO()): assert wm.main(args)==0
    selected=json.loads(receipt.read_text())
    roles(p,'fixture-second') # completion keeps the actual selection, not today's model
    assert wm.main(args+['--outcome','17'])==0
    lines=log.read_text().splitlines()
    assert lines[0].startswith('MODEL_SELECTION ') and lines[1].startswith('MODEL_OUTCOME ')
    outcome=json.loads(lines[1].split(' ',1)[1])
    assert outcome['selection_id']==selected['selection_id'] and outcome['roles_sha256']==selected['roles_sha256']
    assert outcome['exit_code']==17 and outcome['quality']=='unscored' and outcome['model']=='fixture-fast'


@pytest.fixture
def fake_home(tmp_path):
    # All runtime paths, including launcher log, registry and selector, are temporary.
    home=tmp_path/'home';home.mkdir()
    selector=home/'.local/share/research-harness/worker_models.py';selector.parent.mkdir(parents=True)
    shutil.copyfile(ROOT/'worker_models.py',selector)
    roles(home/'.config/model-leaderboard/roles.json')
    codex=tmp_path/'fake-codex'
    codex.write_text('#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["FAKE_CALL"]).write_text(json.dumps(sys.argv))\nprint("local executor fixture")\nsys.exit(int(os.environ.get("FAKE_RC","0")))\n')
    codex.chmod(0o755)
    c=home/'.local/state/ai-research-tools/jobs';c.mkdir(parents=True)
    (c/'fixture-job.md').write_text('Offline executor fixture, no worker.\n')
    work=tmp_path/'work';work.mkdir()
    env=dict(os.environ,HOME=str(home),LAUNCH_DETACHED='1',FORCE_LAUNCH='1',
             LAUNCH_CODEX=str(codex),LAUNCH_STATE=str(tmp_path/'registry'),
             LAUNCH_ARTIFACT_DIR=str(c),AGENT_BACKEND='codex',
             FAKE_CALL=str(tmp_path/'call.json'),PYTHONDONTWRITEBYTECODE='1', RH_ROLES_FILE=str(home/'.config/model-leaderboard/roles.json'))
    for key in ('LAUNCH_ROLE','LAUNCH_MODEL','LAUNCH_MODEL_OVERRIDE','LAUNCH_RESUME'):env.pop(key,None)
    return home,c,work,env


def run_launcher(fake_home,*extra,rc=0,job='fixture-job'):
    home,c,work,env=fake_home
    env=dict(env,FAKE_RC=str(rc))
    launcher=Path(__file__).resolve().parents[2] / 'tools/launch.sh'
    return subprocess.run(['/bin/zsh',str(launcher),job,str(work),*extra],
                          env=env,text=True,capture_output=True,timeout=10)


def test_launcher_uses_role_model_and_propagates_failure(fake_home):
    home,c,work,env=fake_home
    result=run_launcher(fake_home,rc=9)
    assert result.returncode==9,result.stderr
    argv=json.loads(Path(env['FAKE_CALL']).read_text())
    assert argv[argv.index('-m')+1]=='fixture-fast'
    lines=(c/'fixture-job.log').read_text().splitlines()
    selected=json.loads(next(s for s in lines if s.startswith('MODEL_SELECTION ')).split(' ',1)[1])
    outcome=json.loads(next(s for s in lines if s.startswith('MODEL_OUTCOME ')).split(' ',1)[1])
    assert selected['role']=='batch' and outcome['exit_code']==9
    assert not (Path(env['LAUNCH_STATE'])/'fixture-job.job').exists()


def test_launcher_refuses_fixed_model_before_executor(fake_home):
    home,c,work,env=fake_home
    result=run_launcher(fake_home,'--model','fixture-fast')
    assert result.returncode==2
    assert not Path(env['FAKE_CALL']).exists()
    assert 'hard-coded model refused' in result.stderr


def test_launcher_explicit_override_is_logged(fake_home):
    home,c,work,env=fake_home
    result=run_launcher(fake_home,'--model','fixture-second','--model-override','compare frozen benchmark config')
    assert result.returncode==0,result.stderr
    argv=json.loads(Path(env['FAKE_CALL']).read_text())
    assert argv[argv.index('-m')+1]=='fixture-second'
    assert 'compare frozen benchmark config' in (c/'fixture-job.log').read_text()


def test_sweep_worker_environment_carries_selected_role_not_parent_override(tmp_path):
    # Exercise only environment construction. Popen is a stand-in, never an executor.
    spec=tmp_path/'worker.md';spec.write_text('fixture')
    launcher=tmp_path/'launcher';launcher.write_text('fixture')
    cfg=dict(launcher_path=launcher,cwd=tmp_path,cores=1,memory_gib=1,worker_timeout_minutes=1,worker_role='mechanical')
    with patch.object(sweep,'guard'),patch.object(sweep.subprocess,'Popen') as popen,\
            patch.object(sweep.os,'killpg'),patch.dict(os.environ,{'LAUNCH_MODEL':'stale-fixed-model','LAUNCH_MODEL_OVERRIDE':'parent reason'}):
        popen.return_value.poll.return_value=0;popen.return_value.returncode=0;popen.return_value.pid=123456
        assert sweep.run_worker(spec,cfg)==0
    env=popen.call_args.kwargs['env']
    assert env['LAUNCH_ROLE']=='mechanical' and env['LAUNCH_MODEL']=='' and env['LAUNCH_MODEL_OVERRIDE']==''


def test_capacity_retry_stops_after_success_and_keeps_outcomes(fake_home):
    home, artifacts, work, env = fake_home
    executor = Path(env['LAUNCH_CODEX'])
    executor.write_text('#!' + sys.executable + "\n" +
        'import os,sys\nfrom pathlib import Path\n' +
        'p=Path(os.environ["FAKE_CALL"])\nn=int(p.read_text()) if p.exists() else 0\n' +
        'p.write_text(str(n+1))\nprint("at capacity" if n == 0 else "completed")\nsys.exit(1 if n == 0 else 0)\n')
    env = dict(env, LAUNCH_RETRY_SECONDS='0')
    result = subprocess.run(['/bin/zsh', str(ROOT.parent/'tools/launch.sh'), 'fixture-job', str(work)],
                            env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert Path(env['FAKE_CALL']).read_text() == '2'
    events = [json.loads(line.split(' ', 1)[1]) for line in (artifacts/'fixture-job.log').read_text().splitlines()
              if line.startswith('MODEL_OUTCOME ')]
    assert [event['exit_code'] for event in events] == [1, 0]
    assert events[0]['selection_id'] != events[1]['selection_id']


def test_sweep_worker_environment_carries_the_lanes_execution_host(tmp_path):
    """The lane's `host` has to reach launch.sh, which only reads --host and LAUNCH_HOST. Without
    this the setting would validate, measure the right disk, and still run the job on the m4."""
    spec=tmp_path/'worker.md';spec.write_text('fixture')
    launcher=tmp_path/'launcher';launcher.write_text('fixture')
    cfg=dict(launcher_path=launcher,cwd=tmp_path,cores=1,memory_gib=1,worker_timeout_minutes=1,host='m5')
    # The work dir on the host has its own tests; here it is a precondition, not the subject.
    with patch.object(sweep,'guard'),patch.object(sweep.subprocess,'Popen') as popen,\
            patch.object(sweep,'host_sync',return_value=True),\
            patch.object(sweep,'host_workdir_missing',return_value=[]),\
            patch.object(sweep.os,'killpg'),patch.dict(os.environ,{},clear=False):
        os.environ.pop('LAUNCH_HOST',None)
        popen.return_value.poll.return_value=0;popen.return_value.returncode=0;popen.return_value.pid=123456
        assert sweep.run_worker(spec,cfg)==0
    assert popen.call_args.kwargs['env']['LAUNCH_HOST']=='m5'


def test_a_lane_with_no_host_sends_an_empty_one(tmp_path):
    spec=tmp_path/'worker.md';spec.write_text('fixture')
    launcher=tmp_path/'launcher';launcher.write_text('fixture')
    cfg=dict(launcher_path=launcher,cwd=tmp_path,cores=1,memory_gib=1,worker_timeout_minutes=1)
    with patch.object(sweep,'guard'),patch.object(sweep.subprocess,'Popen') as popen,\
            patch.object(sweep.os,'killpg'),patch.dict(os.environ,{},clear=False):
        os.environ.pop('LAUNCH_HOST',None)
        popen.return_value.poll.return_value=0;popen.return_value.returncode=0;popen.return_value.pid=123456
        assert sweep.run_worker(spec,cfg)==0
    assert popen.call_args.kwargs['env']['LAUNCH_HOST']==''


def test_an_openrouter_model_is_selected_only_on_its_own_route(tmp_path):
    p=roles(tmp_path/'roles.json')
    data=json.loads(p.read_text())
    data['routes']['vendor/fixture-third']={'cli':'openrouter','canonical':'vendor/fixture-third'}
    p.write_text(json.dumps(data))
    got=wm.select('batch','openrouter',model='vendor/fixture-third',override='third-family referee',path=p)
    assert got['executor']=='openrouter' and got['source']=='override'
    with pytest.raises(ValueError,match='no compatible'):
        wm.select('batch','codex',model='vendor/fixture-third',override='x',path=p)
    with pytest.raises(ValueError,match='no compatible'):
        wm.select('batch','openrouter',path=p)
    out=subprocess.run([sys.executable,str(ROOT/'worker_models.py'),'--role','batch','--executor','openrouter',
        '--model','vendor/fixture-third','--model-override','x','--roles-file',str(p),'--log',str(tmp_path/'l'),
        '--receipt',str(tmp_path/'r.json')],capture_output=True,text=True)
    assert out.returncode==0 and out.stdout.strip()=='vendor/fixture-third', out.stderr


@pytest.mark.parametrize('role', ['batch', 'mechanical', 'review', 'judge', 'ideation', 'design'])
def test_openrouter_candidate_selection_and_exploration(tmp_path, role):
    p = roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text())
    carbon, hydrogen = 'google/gemini-4-carbon', 'google/gemini-4-hydrogen'
    data['roles'][role] = [carbon, hydrogen, 'fixture-fast']
    for m in (carbon, hydrogen):
        data['routes'][m] = dict(cli='openrouter', canonical=m)
    p.write_text(json.dumps(data))
    assert wm.select(role, 'codex', path=p, made_by='claude-fixture')['executor'] == 'openrouter'
    got = wm.select(role, 'codex', path=p, made_by='claude-fixture', explore=hydrogen)
    assert (got['model'], got['executor'], got['source'], got['model_override']) == (
        hydrogen, 'openrouter', 'explore', '')
    with pytest.raises(ValueError, match='not in.*pool'):
        wm.select(role, 'codex', path=p, made_by='claude-fixture', explore='unlisted/model')
    with pytest.raises(ValueError, match='cannot be combined'):
        wm.select(role, 'codex', path=p, model='fixture-fast', override='fixture comparison',
                  made_by='claude-fixture', explore=hydrogen)
    if role in wm.JUDGMENT:
        assert wm.select(role, 'codex', path=p, made_by=carbon)['model'] == 'fixture-fast'
        with pytest.raises(ValueError, match='different model family'):
            wm.select(role, 'codex', path=p, made_by=carbon, explore=hydrogen)
    data['overrides'] = {role: dict(exclude=[hydrogen])}
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='excluded'):
        wm.select(role, 'codex', path=p, made_by='claude-fixture', explore=hydrogen)


@pytest.mark.parametrize('explore', [False, True])
def test_launcher_runs_openrouter_through_codex_with_private_auth(fake_home, explore):
    home, artifacts, _, env = fake_home
    p = Path(env['RH_ROLES_FILE'])
    data = json.loads(p.read_text())
    model = 'google/gemini-4-hydrogen'
    data['routes'][model] = dict(cli='openrouter', canonical=model)
    data['roles']['batch'] = [model]
    p.write_text(json.dumps(data))
    key = home / '.config/openrouter/key'
    key.parent.mkdir(parents=True)
    key.write_text('synthetic-secret-never-log')
    cli = Path(env['LAUNCH_CODEX'])
    cli.write_text('#!' + sys.executable + '\nimport json,os,sys\nfrom pathlib import Path\n'
                   'assert os.environ["OPENROUTER_API_KEY"] == "synthetic-secret-never-log"\n'
                   'assert os.environ["LAUNCH_PROVIDER"] == "openrouter"\n'
                   'Path(os.environ["FAKE_CALL"]).write_text(json.dumps(sys.argv))\n')
    result = run_launcher(fake_home, *(['--explore', model] if explore else []))
    assert result.returncode == 0, result.stderr
    argv = json.loads(Path(env['FAKE_CALL']).read_text())
    assert argv[argv.index('-m') + 1] == model
    assert 'model_provider="openrouter"' in argv
    assert 'model_providers.openrouter.env_key="OPENROUTER_API_KEY"' in argv
    receipt = json.loads((artifacts / 'fixture-job.log.selection.json').read_text())
    assert receipt['executor'] == 'openrouter'
    assert receipt['source'] == ('explore' if explore else 'leaderboard')
    assert 'synthetic-secret-never-log' not in (artifacts / 'fixture-job.log').read_text()


def judgment_roles(path):
    ranked = ['claude-opus-5-5', 'gpt-6-astra', 'claude-fable-5-2', 'gpt-6.1-sol']
    routes = {m: {'cli': 'claude' if m.startswith('claude') else 'codex',
                  'canonical': ('anthropic/' if m.startswith('claude') else 'openai/') + m}
              for m in ranked + ['claude-sonnet-5']}
    path.write_text(json.dumps({'roles': {'review': ranked, 'taste': ranked, 'ideation': ranked},
                                'routes': routes}))
    return path


@pytest.mark.parametrize('role', sorted(wm.JUDGMENT))
def test_judgment_pin_requires_owner_reason_and_names_pick(tmp_path, role):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match=role + '.*leaderboard picks claude-opus-5-5'):
        wm.select(role, 'codex', 'claude-sonnet-5', 'save budget', path, made_by='gpt-6.1-sol')
    assert not (tmp_path / 'model-overrides.jsonl').exists()


@pytest.mark.parametrize('role', ['review', 'judge', 'audit'])
def test_review_requires_maker_and_uses_first_other_family(tmp_path, role):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match='requires --made-by'):
        wm.select(role, 'codex', path=path)
    got = wm.select(role, 'codex', path=path, made_by='gpt-6.1-sol')
    assert (got['model'], got['executor']) == ('claude-opus-5-5', 'claude')
    got = wm.select(role, 'claude', path=path, made_by='claude-opus-5-5')
    assert (got['model'], got['executor']) == ('gpt-6-astra', 'codex')


def test_judgment_own_row_and_exclusions_are_respected(tmp_path):
    path = judgment_roles(tmp_path / 'roles.json')
    data = json.loads(path.read_text())
    data['roles']['judge'] = ['claude-fable-5-2']
    data['overrides'] = {'review': {'exclude': ['anthropic/claude-opus-5-5']}}
    path.write_text(json.dumps(data))
    assert wm.select('judge', 'codex', path=path, made_by='gpt-6.1-sol')['model'] == 'claude-fable-5-2'
    assert wm.select('audit', 'codex', path=path, made_by='gpt-6.1-sol')['model'] == 'claude-fable-5-2'


def test_owner_override_env_is_accepted_and_logged(tmp_path, monkeypatch):
    path = judgment_roles(tmp_path / 'roles.json')
    target = tmp_path / 'owner-overrides.jsonl'
    monkeypatch.setenv('RH_MODEL_OVERRIDE_LOG', str(target))
    monkeypatch.setenv('MODEL_OVERRIDE_REASON', 'Ricardo: frozen comparison')
    monkeypatch.setenv('LAUNCH_MADE_BY', 'gpt-6.1-sol')
    got = wm.select('review', 'codex', 'claude-sonnet-5', path=path, job='fixture-review')
    assert got['executor'] == 'claude'
    row = json.loads(target.read_text())
    assert row == dict(role='review', model='claude-sonnet-5', reason='Ricardo: frozen comparison',
                       job='fixture-review', utc=got['utc'])


def test_review_launch_pin_refused_before_executor(fake_home):
    _, _, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    result = run_launcher(fake_home, '--role', 'review', '--made-by', 'gpt-6.1-sol',
                          '--model', 'claude-sonnet-5', '--model-override', 'save budget')
    assert result.returncode == 2
    assert 'review' in result.stderr and 'leaderboard picks claude-opus-5-5' in result.stderr
    assert not Path(env['FAKE_CALL']).exists()


def test_review_pin_refusal_names_pick_even_without_maker(tmp_path):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match='review.*leaderboard picks claude-opus-5-5'):
        wm.select('review', 'codex', 'claude-sonnet-5', 'save budget', path)


@pytest.mark.parametrize('job', ['math_c38ref_1104', 'math_l1chk_a_1103',
                                 'math_codetablespkgrev_1106', 'referee', 'review2',
                                 'lane_ref_1', 'lane_rev_1', 'lane_judge', 'lane_audit',
                                 'lane_taste', 'lane_design', 'lane_chk', 'lane_check',
                                 'lane_verify'])
def test_judgment_batch_names_use_review_rules(tmp_path, job):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match='job name .*judgment job.*--role review --made-by MODEL'):
        wm.select('batch', 'codex', path=path, job=job)
    got = wm.select('batch', 'codex', path=path, job=job, made_by='gpt-6.1-sol')
    assert (got['role'], got['model'], got['executor']) == ('review', 'claude-opus-5-5', 'claude')


@pytest.mark.parametrize('reason', ['ordinary reason', 'different-model-independent-checker'])
@pytest.mark.parametrize('model', ['gpt-6-astra', 'claude-sonnet-5'])
def test_inferred_review_pin_refuses_before_executor(fake_home, reason, model):
    _, artifacts, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    job = 'math_c38ref_1104'
    (artifacts / (job + '.md')).write_text('Referee the claim.\n')
    result = run_launcher(fake_home, '--model', model, '--model-override', reason, job=job)
    assert result.returncode == 2
    assert 'job name math_c38ref_1104 makes this a judgment job' in result.stderr
    assert '--role review --made-by MODEL' in result.stderr
    assert 'hard-coded model refused' in result.stderr
    assert not Path(env['FAKE_CALL']).exists()
    assert not (Path(env['RH_ROLES_FILE']).parent / 'model-overrides.jsonl').exists()


def test_inferred_review_owner_pin_still_requires_other_family(tmp_path):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match='judgment job.*different model family'):
        wm.select('batch', 'codex', 'gpt-6-astra', 'Ricardo: frozen comparison', path,
                  made_by='gpt-6.1-sol', job='math_c38ref_1104')


@pytest.mark.parametrize('job', ['planets_dosegrid2_1114', 'lane_reference',
                                 'lane_reviewing', 'lane_checkpoint', 'lane_designate'])
def test_ordinary_batch_names_are_unaffected(tmp_path, job):
    path = roles(tmp_path / 'roles.json')
    got = wm.select('batch', 'codex', path=path, job=job)
    assert (got['role'], got['model']) == ('batch', 'fixture-fast')


def test_explicit_nonbatch_role_is_preserved(tmp_path):
    path = roles(tmp_path / 'roles.json')
    got = wm.select('mechanical', 'codex', path=path, job='lane_review')
    assert got['role'] == 'mechanical'


def test_inferred_review_also_refuses_models_in_spec(fake_home):
    _, artifacts, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    job = 'math_c38ref_1104'
    (artifacts / (job + '.md')).write_text('Use Sonnet to referee the claim.\n')
    result = run_launcher(fake_home, '--made-by', 'gpt-6.1-sol', job=job)
    assert result.returncode == 2
    assert 'name the leaderboard role, not a model' in result.stderr
    assert not Path(env['FAKE_CALL']).exists()


@pytest.mark.parametrize('name', ['sonnet', 'OPUS', 'gpt-6-astra', 'claude-fable-5-2', 'deepseek',
                                 'Gemini 4 Carbon', 'google/gemini-4-hydrogen'])
def test_judgment_spec_names_are_refused_before_executor(fake_home, name):
    _, artifacts, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    (artifacts / 'fixture-job.md').write_text('Use {} for the next review.\n'.format(name))
    result = run_launcher(fake_home, '--role', 'review', '--made-by', 'gpt-6.1-sol')
    assert result.returncode == 2
    assert ('launch.sh refused fixture-job: name the leaderboard role, not a model (LEADERBOARD.md); '
            'the leaderboard picks claude-opus-5-5') in result.stderr
    assert not Path(env['FAKE_CALL']).exists()


@pytest.mark.parametrize('made_by,expected', [('gpt-6.1-sol', 'claude-opus-5-5'),
                                           ('claude-opus-5-5', 'gpt-6-astra')])
@pytest.mark.parametrize('job,role_args', [('fixture-job', ['--role', 'review']),
                                         ('math_c38ref_1104', ['--role', 'review']),
                                         ('math_c38ref_1104', [])])
def test_review_launch_switches_executor_and_preserves_receipt(fake_home, made_by, expected, job, role_args):
    _, artifacts, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    claude = artifacts / 'fake-claude'
    claude.write_text('#!' + sys.executable + '\nimport json,os,sys\nfrom pathlib import Path\n'
                      'Path(os.environ["FAKE_CALL"]).write_text(json.dumps(sys.argv))\n'
                      'print(json.dumps({"is_error":False,"subtype":"success","result":"fixture"}))\n')
    claude.chmod(0o755)
    env['LAUNCH_CLAUDE'] = str(claude)
    env['AGENT_BACKEND'] = 'codex' if made_by.startswith('gpt') else 'claude'
    (artifacts / (job + '.md')).write_text('Referee the claim.\n')
    result = run_launcher(fake_home, *role_args, '--made-by', made_by, job=job)
    assert result.returncode == 0, result.stderr
    argv = json.loads(Path(env['FAKE_CALL']).read_text())
    assert expected in argv
    assert argv[1] == ('-p' if made_by.startswith('gpt') else 'exec')
    receipt = json.loads((artifacts / (job + '.log.selection.json')).read_text())
    assert {k: receipt[k] for k in ('model', 'role', 'lane', 'job', 'made_by')} == dict(
        model=expected, role='review', lane=job.split('_')[0] if '_' in job else 'fixture', job=job, made_by=made_by)
    assert receipt['utc'] and receipt['roles_sha256']


@pytest.mark.parametrize('text', [
    'Did the scoring jobs on gpt-6.2-astra, including audits, use the weekly allowance?',
    'The opus test report has been passed to general; the review scores are attached.',
    'Review plant batches caught: 2/2 for gpt-6.2-astra, 1/2 for opus.',
    'Do not use opus for review.',
    'Referee the claim. The previous gpt-6.2-astra audit caught 2/2 plants.',
])
def test_judgment_spec_reports_and_questions_pass(tmp_path, text):
    path = judgment_roles(tmp_path / 'roles.json')
    spec = tmp_path / 'job.md'
    spec.write_text(text)
    with contextlib.redirect_stdout(io.StringIO()):
        assert wm.main(['--role', 'review', '--made-by', 'gpt-6.1-sol',
                        '--roles-file', str(path), '--spec', str(spec),
                        '--log', str(tmp_path / 'launch.log'),
                        '--receipt', str(tmp_path / 'receipt.json')]) == 0
