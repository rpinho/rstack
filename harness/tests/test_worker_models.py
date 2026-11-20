"""Model routing tests use local files and fake executors; no workers or APIs."""
import contextlib
import datetime as dt
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


def test_an_openrouter_model_is_selected_only_on_its_own_route(tmp_path, monkeypatch):
    monkeypatch.setenv('RH_ALLOW_OPENROUTER', '1')  # in-flight work only, since 11-19
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
def test_openrouter_candidate_selection_and_exploration(tmp_path, role, monkeypatch):
    monkeypatch.setenv('RH_ALLOW_OPENROUTER', '1')  # in-flight work only, since 11-19
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
    env['RH_ALLOW_OPENROUTER'] = '1'  # in-flight work only, since 11-19
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


@pytest.mark.parametrize('role', ['batch', 'review', 'mechanical'])
def test_an_openrouter_route_is_refused_without_the_in_flight_override(tmp_path, role, monkeypatch):
    # 11-19 Ricardo: "No pay-as-you-go. Do NOT top up OpenRouter." Refused, not swapped for another model.
    monkeypatch.delenv('RH_ALLOW_OPENROUTER', raising=False)
    p = roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text())
    data['roles'][role] = ['vendor/fixture-third', 'fixture-fast']
    data['routes']['vendor/fixture-third'] = dict(cli='openrouter', canonical='vendor/fixture-third')
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='pay-as-you-go.*RH_ALLOW_OPENROUTER=1'):
        wm.select(role, 'codex', path=p, made_by='claude-fixture')
    monkeypatch.setenv('RH_ALLOW_OPENROUTER', '1')
    assert wm.select(role, 'codex', path=p, made_by='claude-fixture')['executor'] == 'openrouter'


def test_an_agy_route_is_selected_for_gemini_on_its_own_executor(tmp_path):
    p = roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text())
    data['roles']['review'] = ['gemini-fixture']
    data['routes']['gemini-fixture'] = dict(cli='agy', canonical='google/gemini-fixture')
    p.write_text(json.dumps(data))
    got = wm.select('review', 'codex', path=p, made_by='claude-fixture')
    assert (got['model'], got['executor']) == ('gemini-fixture', 'agy')


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


def overflow_setup(tmp_path, monkeypatch, percent, limit='85'):
    import time
    state = tmp_path / 'state'
    (state / 'usage').mkdir(parents=True)
    (state / 'usage/claude.json').write_text(json.dumps({'weekly_percent': percent, 'at': time.time() - 60}))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(state))
    monkeypatch.delenv('RESETS_USAGE_DIR', raising=False)
    monkeypatch.delenv('LAUNCH_EFFORT', raising=False)
    if limit is None:
        monkeypatch.delenv('RH_CLAUDE_OVERFLOW_PERCENT', raising=False)
    else:
        monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', limit)
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {'batch': ['claude-opus-5-5'], 'cheap': ['claude-haiku-5-5']},
                             'routes': {'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'},
                                        'claude-haiku-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-haiku-5.5'}}}))
    return p


def test_above_the_threshold_a_claude_job_overflows_to_agys_claude_and_says_so(tmp_path, monkeypatch):
    p = overflow_setup(tmp_path, monkeypatch, 91)
    monkeypatch.delenv('RH_LAUNCHER_EXECUTORS', raising=False)
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'   # this launcher cannot run agy
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    got = wm.select('batch', 'claude', path=p)
    assert (got['model'], got['canonical']) == ('claude-opus-5-5', 'anthropic/claude-opus-5.5')
    assert (got['executor'], got['route_model']) == ('agy', 'claude-opus-5-5-high')
    assert got['overflow'] == 'claude overflow via agy (weekly at 91%)'
    log, receipt = tmp_path / 'job.log', tmp_path / 'r.json'
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert wm.main(['--role', 'batch', '--executor', 'claude', '--roles-file', str(p), '--print-route',
                        '--job', 'fixture-job', '--log', str(log), '--receipt', str(receipt)]) == 0
    assert out.getvalue().split() == ['claude-opus-5-5-high', 'agy']
    assert 'claude overflow via agy (weekly at 91%) job=fixture-job' in log.read_text()
    assert json.loads(receipt.read_text())['overflow'] == 'claude overflow via agy (weekly at 91%)'
    # agy serves only Opus and Sonnet; any other Claude model stays where it is.
    assert wm.select('cheap', 'claude', path=p)['executor'] == 'claude'


@pytest.mark.parametrize('percent,limit', [(84, '85'), (99, None)])
def test_below_the_threshold_or_with_none_set_nothing_changes(tmp_path, monkeypatch, percent, limit):
    p = overflow_setup(tmp_path, monkeypatch, percent, limit)
    got = wm.select('batch', 'claude', path=p)
    assert got['executor'] == 'claude' and 'overflow' not in got and 'route_model' not in got


def test_a_stale_weekly_reading_does_not_overflow(tmp_path, monkeypatch):
    p = overflow_setup(tmp_path, monkeypatch, 95)
    (tmp_path / 'state/usage/claude.json').write_text(json.dumps({'weekly_percent': 95, 'at': 1000.0}))
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'


def test_the_receipt_shows_everyday_rate_and_n_first_and_the_bench_apart(tmp_path):
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {'batch': ['fixture-a', 'fixture-b']},
        'routes': {'fixture-a': {'cli': 'codex', 'canonical': 'openai/fixture-a'},
                   'fixture-b': {'cli': 'codex', 'canonical': 'openai/fixture-b'}},
        'evidence': {'batch': {'fixture-a': {'n': 100, 'rate': 0.91}, 'fixture-b': {'n': 3, 'rate': 1.0}}},
        'bench': {'batch': {'fixture-b': {'n': 8, 'rate': 1.0}}}}))
    a = wm.select('batch', 'codex', path=p)
    assert a['everyday'] == {'rate': 0.91, 'n': 100} and 'bench' not in a
    b = wm.select('batch', 'codex', path=p, explore='fixture-b')
    assert b['everyday'] == 'n<5' and b['bench'] == {'rate': 1.0, 'n': 8}


def delegate_roles(path):
    routes = {'claude-opus-5-5': ('claude', 'anthropic/claude-opus-5.5'), 'gpt-6.2-sol': ('codex', 'openai/gpt-6.2-sol'),
              'gemini-4-argon-low': ('agy', 'google/gemini-4-argon-low'),
              'gemini-4-neon-low': ('agy', 'google/gemini-4-neon-low')}
    path.write_text(json.dumps({'roles': {'review': ['claude-opus-5-5', 'gpt-6.2-sol'], 'batch': ['claude-opus-5-5']},
        'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()},
        'evidence': {'review': {'gemini-4-argon-low': {'n': 3, 'rate': 1.0}}}}))
    return path


def test_a_delegated_share_goes_to_the_delegate_with_fewest_graded_outcomes_and_says_so(tmp_path, monkeypatch):
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    got = wm.select('review', 'codex', path=p, made_by='gpt-6')
    assert got['source'] == 'delegate' and got['model'] == 'gemini-4-neon-low' and got['executor'] == 'agy'
    assert got['delegate'] == ('delegated share 1 of review: gemini-4-neon-low (everyday n=0) instead of the '
                               'leaderboard pick claude-opus-5-5')
    # Never to the job's own maker for judgment, and only in the delegated roles.
    assert wm.select('review', 'codex', path=p, made_by='gemini-3')['model'] == 'gpt-6.2-sol'
    assert wm.select('batch', 'claude', path=p)['source'] == 'delegate'   # batch is delegated too (11-19)
    monkeypatch.setenv('RH_DELEGATE_ROLES', 'review')
    assert wm.select('batch', 'claude', path=p)['source'] == 'leaderboard'
    monkeypatch.delenv('RH_DELEGATE_ROLES')
    log, receipt = tmp_path / 'job.log', tmp_path / 'job.log.selection.json'
    assert wm.main(['--role', 'review', '--made-by', 'gpt-6', '--roles-file', str(p), '--job', 'j',
                    '--log', str(log), '--receipt', str(receipt)]) == 0
    assert 'delegated share 1 of review' in log.read_text()


def test_with_no_share_set_the_leaderboard_pick_stands(tmp_path, monkeypatch):
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.delenv('RH_DELEGATE_SHARE', raising=False)
    got = wm.select('review', 'codex', path=p, made_by='gpt-6')
    assert got['source'] == 'leaderboard' and got['model'] == 'claude-opus-5-5' and 'delegate' not in got


def test_a_returned_job_is_graded_into_its_log_and_the_grades_file(tmp_path):
    p = delegate_roles(tmp_path / 'roles.json')
    log, receipt = tmp_path / 'job.log', tmp_path / 'job.log.selection.json'
    assert wm.main(['--role', 'review', '--made-by', 'gpt-6', '--roles-file', str(p), '--job', 'j',
                    '--log', str(log), '--receipt', str(receipt)]) == 0
    assert wm.main(['--grade', 'partial', '--note', 'half the checks', '--receipt', str(receipt), '--log', str(log)]) == 0
    row = json.loads((tmp_path / 'everyday-grades.jsonl').read_text())
    assert (row['grade'], row['job'], row['model'], row['source_kind']) == ('partial', 'j', 'claude-opus-5-5', 'everyday')
    assert 'MODEL_GRADE' in log.read_text()


def test_a_spec_that_pins_its_model_is_never_delegated(tmp_path, monkeypatch):
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    assert wm.spec_pin('Do the thing.\n- Model pin: sealed referee for batch 3\n') == 'sealed referee for batch 3'
    assert wm.spec_pin('We discussed whether a model pin: matters') == ''
    got = wm.select('review', 'codex', path=p, made_by='gpt-6', pin='cross-family check')
    assert got['source'] == 'leaderboard' and got['model_pin'] == 'cross-family check' and 'delegate' not in got
    spec = tmp_path / 'job.md'
    spec.write_text('Referee the claims.\nModel pin: sealed referee\n')
    receipt = tmp_path / 'r.json'
    assert wm.main(['--role', 'batch', '--executor', 'claude', '--roles-file', str(p), '--spec', str(spec),
                    '--log', str(tmp_path / 'l'), '--receipt', str(receipt)]) == 0
    assert json.loads(receipt.read_text())['model_pin'] == 'sealed referee'
    assert 'batch' in wm.DELEGATE_ROLES


def returned_delegate(receipts, job, lane, hours_ago):
    sid = uuid_hex = job + 'sid'
    finished = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).isoformat()
    (receipts / (job + '.log.selection.json')).write_text(json.dumps(dict(
        selection_id=sid, job=job, lane=lane, role='batch', model='gemini-4-argon-low', source='delegate')))
    (receipts / (job + '.log')).write_text('MODEL_OUTCOME ' + json.dumps(dict(selection_id=sid, finished=finished)) + '\n')
    return receipts / (job + '.log.selection.json')


def test_a_returned_delegated_job_is_recorded_ungraded_at_once_and_a_grade_replaces_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    receipts = tmp_path / 'receipts'; receipts.mkdir()
    receipt = returned_delegate(receipts, 'lane-a-job1', 'lane-a', 0)
    assert wm.main(['--record-ungraded', '--receipt', str(receipt), '--log', str(receipts / 'lane-a-job1.log')]) == 0
    rows = [json.loads(l) for l in (receipts / 'everyday-grades.jsonl').read_text().splitlines()]
    assert [(r['grade'], r['job']) for r in rows] == [('ungraded', 'lane-a-job1')]
    assert 'lane-a-job1' in next((tmp_path / 'state/asks-waiting').glob('*-ungraded.tsv')).read_text()
    assert wm.main(['--grade', 'pass', '--receipt', str(receipt), '--log', str(receipts / 'lane-a-job1.log')]) == 0
    rows = [json.loads(l) for l in (receipts / 'everyday-grades.jsonl').read_text().splitlines()]
    assert rows[-1]['grade'] == 'pass' and rows[-1]['id'] == rows[0]['id']   # same selection: the grade replaces it
    assert wm.main(['--record-ungraded', '--receipt', str(receipt), '--log', str(receipts / 'lane-a-job1.log')]) == 0
    assert len((receipts / 'everyday-grades.jsonl').read_text().splitlines()) == 2


def test_after_24_hours_an_ungraded_job_is_recorded_and_listed_for_the_morning(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(wm, 'UNGRADED_TODAY', [])
    receipts = tmp_path / 'receipts'; receipts.mkdir()
    returned_delegate(receipts, 'lane-a-old', 'lane-a', 25)
    assert wm.main(['--sweep-ungraded', str(receipts)]) == 0
    assert 'ungraded after 24 h: lane-a-old' in capsys.readouterr().out
    row = json.loads((receipts / 'everyday-grades.jsonl').read_text().splitlines()[-1])
    assert (row['grade'], row['job']) == ('ungraded', 'lane-a-old')
    listed = list((tmp_path / 'state/asks-waiting').glob('*-ungraded.tsv'))
    assert listed and 'lane-a-old' in listed[0].read_text()


def test_a_lane_with_an_ungraded_returned_job_still_launches(fake_home):
    # 11-19 (general): grading never blocks a lane.
    home, c, work, env = fake_home
    assert run_launcher(fake_home).returncode == 0
    lane = json.loads((c / 'fixture-job.log.selection.json').read_text())['lane']
    returned_delegate(c, 'earlier-job', lane, 1)
    result = run_launcher(fake_home)
    assert result.returncode == 0, result.stderr
    assert 'refused' not in result.stderr


def family_roles(path):
    routes = {'claude-opus-5-5': ('claude', 'anthropic/claude-opus-5.5'), 'claude-sonnet-5-5': ('claude', 'anthropic/claude-sonnet-5.5'),
              'gpt-6.2-sol': ('codex', 'openai/gpt-6.2-sol'), 'gpt-6.2-astra': ('codex', 'openai/gpt-6.2-astra'),
              'gemini-4-argon-low': ('agy', 'google/gemini-4-argon-low'), 'gemini-4-neon-low': ('agy', 'google/gemini-4-neon-low')}
    path.write_text(json.dumps({'roles': {'review': ['gemini-4-argon-low', 'claude-opus-5-5', 'gpt-6.2-astra'],
                                          'batch': ['gemini-4-argon-low', 'gpt-6.2-sol']},
                                'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()}}))
    return path


@pytest.mark.parametrize('producer,family', [('gemini-3.8-flash-low', 'google'), ('claude-opus-5-5', 'anthropic')])
def test_a_referee_is_never_delegated_to_the_producers_family(tmp_path, monkeypatch, producer, family):
    from bug_verdicts import maker
    p = family_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    for _ in range(40):
        got = wm.select('review', 'codex', path=p, made_by=producer)
        assert maker(got['model'], got['canonical']) != family, got
        assert got['producer_family'] == [family]


def test_a_planted_referee_batch_reads_the_hunters_family_from_plants(tmp_path, monkeypatch):
    # The open-source lane's case: the hunter's family is in PLANTS.jsonl, whatever LAUNCH_MADE_BY says.
    from bug_verdicts import maker
    p = family_roles(tmp_path / 'roles.json')
    lane_dir, work = tmp_path / 'lane', tmp_path / 'ref-job'
    lane_dir.mkdir(); work.mkdir()
    (lane_dir / 'PLANTS.jsonl').write_text(json.dumps(dict(batch='b1', workdir=str(work), hunter_family='Google',
                                                           hunter_model='gemini-4-argon-low', hunter_maker='google')) + '\n')
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    for _ in range(40):
        got = wm.select('review', 'codex', path=p, made_by='claude-opus-5-5', workdir=str(work), lane_dir=str(lane_dir))
        assert maker(got['model'], got['canonical']) not in ('google', 'anthropic'), got
    # A batch-role job on a planted batch: the base pick (Gemini first in batch) moves off the hunter's family too.
    monkeypatch.setenv('RH_DELEGATE_SHARE', '0')
    got = wm.select('batch', 'codex', path=p, job='lane-hunt-x', workdir=str(work), lane_dir=str(lane_dir))
    assert got['model'] == 'gpt-6.2-sol' and got['executor'] == 'codex'


def test_a_judging_job_with_an_unknown_producer_is_not_delegated(tmp_path, monkeypatch):
    p = family_roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text()); data['roles']['taste'] = ['claude-opus-5-5']; p.write_text(json.dumps(data))
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    monkeypatch.setenv('RH_DELEGATE_ROLES', 'taste')
    got = wm.select('taste', 'claude', path=p)
    assert got['source'] == 'leaderboard' and got['producer_family'] == 'unknown'
    assert 'unknown producer family' in got['delegate_skipped']


def test_a_job_recorded_at_return_says_so_and_a_later_grade_clears_its_row(tmp_path):
    """11-19: rows recorded at return said 'not graded within 24 h' hours after launch, and a graded
    pass still showed in the morning report."""
    import worker_models as wm
    state = tmp_path / 'state'
    wm.morning_report([('job-a', 'lane-x', 'model-1'), ('job-b', 'lane-x', 'model-2')], state=state, host='h',
                      reason='returned without a grade')
    target = state / 'asks-waiting' / 'h-ungraded.tsv'
    text = target.read_text()
    assert 'returned without a grade' in text and 'within 24 h' not in text
    wm.clear_ungraded('job-a', state=state, host='h')
    rows = target.read_text().splitlines()
    assert [r.split('\t')[0] for r in rows] == ['job-b']


def test_a_delegate_runs_only_on_an_executor_the_launcher_can_run(tmp_path, monkeypatch):
    # 11-19 23:52, games: the lanes' launcher ran Codex with a delegated gemini-4-neon-medium and exited in 17 s.
    p = family_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_DELEGATE_SHARE', '1')
    monkeypatch.delenv('RH_LAUNCHER_EXECUTORS', raising=False)
    for _ in range(40):
        got = wm.select('batch', 'codex', path=p)
        # Both launchers in use run claude; neither the lanes' launcher nor a codex job runs agy.
        assert got['executor'] in ('codex', 'claude') and not got['model'].startswith('gemini'), got
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    seen = {wm.select('batch', 'codex', path=p)['executor'] for _ in range(60)}
    assert 'agy' in seen or 'claude' in seen


def test_retract_marks_a_job_grade_retracted_and_needs_a_reason(tmp_path, capsys):
    import json as _json
    import worker_models as wm
    grades = tmp_path / 'everyday-grades.jsonl'
    grades.write_text(_json.dumps(dict(id='grade-s1', source_kind='everyday', job='job-a', grade='fail',
                                       model='model-1', role='review')) + '\n')
    assert wm.main(['--retract', 'job-a', '--receipt-dir', str(tmp_path)]) != 0
    assert wm.main(['--retract', 'job-a', '--receipt-dir', str(tmp_path), '--reason', 'launcher started agy without Bash']) == 0
    rows = [_json.loads(l) for l in grades.read_text().splitlines()]
    assert rows[-1]['grade'] == 'retracted' and rows[-1]['retracted'] == 'fail' and rows[-1]['id'] == 'grade-s1'
    assert 'launcher' in rows[-1]['note']


def headroom_roles(path):
    routes = {'claude-opus-5-5': ('claude', 'anthropic/claude-opus-5.5'), 'claude-sonnet-5-5': ('claude', 'anthropic/claude-sonnet-5.5'),
              'gpt-6.2-sol': ('codex', 'openai/gpt-6.2-sol'), 'gpt-6.2-astra': ('codex', 'openai/gpt-6.2-astra')}
    path.write_text(json.dumps({'roles': {'batch': ['gpt-6.2-sol', 'claude-sonnet-5-5'],
                                          'review': ['claude-opus-5-5', 'gpt-6.2-astra']},
                                'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()}}))
    return path


def stub_allowance(monkeypatch, claude, codex):
    import time
    now = time.time()
    class Stub:
        def cached(self, now=None):
            return {'claude': {'weekly_used_percent': claude[0], 'resets_at': now_ + claude[1] * 3600},
                    'codex': {'weekly_used_percent': codex[0], 'resets_at': now_ + codex[1] * 3600}}
        def claude_weekly(self, now=None):
            return {'weekly_used_percent': claude[0]}
    now_ = now
    monkeypatch.setattr(wm, '_allowance', lambda: Stub())
    monkeypatch.setenv('RH_DELEGATE_SHARE', '0')
    monkeypatch.delenv('RH_HEADROOM_ROUTING', raising=False)


def test_claude_takes_codex_work_when_codex_is_tight(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(0, 63), codex=(95, 100))
    got = wm.select('batch', 'codex', path=p)
    assert (got['model'], got['executor']) == ('claude-sonnet-5-5', 'claude')
    assert got['executor_choice'].startswith('executor claude: headroom 100% / 63h to reset vs codex 5% / 100h')
    assert 'moved to claude-sonnet-5-5' in got['executor_choice']


def test_codex_takes_claude_work_when_claude_is_tight(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(90, 20), codex=(10, 100))
    got = wm.select('review', 'codex', path=p, made_by='gemini-4-argon-low')
    assert (got['model'], got['executor']) == ('gpt-6.2-astra', 'codex')
    assert got['executor_choice'].startswith('executor codex: headroom 90% / 100h')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    assert wm.select('review', 'codex', path=p, made_by='gemini-4-argon-low')['model'] == 'claude-opus-5-5'


def test_the_85_percent_brake_still_sends_claude_to_agy(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(90, 20), codex=(99, 100))
    monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', '85')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    got = wm.select('batch', 'codex', path=p)
    assert got['model'] == 'claude-sonnet-5-5' and got['executor'] == 'agy'
    assert got['route_model'] == 'claude-sonnet-5-5-high' and 'weekly at 90%' in got['overflow']


def test_the_headroom_pick_keeps_the_referee_out_of_the_producers_family(tmp_path, monkeypatch):
    from bug_verdicts import maker
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(0, 63), codex=(95, 100))
    got = wm.select('review', 'codex', path=p, made_by='claude-opus-5-5')
    assert maker(got['model'], got['canonical']) != 'anthropic' and got['executor'] == 'codex'
