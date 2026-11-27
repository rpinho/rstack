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
    # the executor-choice line (here: claude usage unknown, last policy kept) is a note, not a record
    lines=[l for l in log.read_text().splitlines() if not l.startswith('executor ')]
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


def fake_claude(fake_home):
    """The launcher may route a job to claude; never the real CLI in a test."""
    home, c, work, env = fake_home
    claude = c / 'fake-claude'
    claude.write_text('#!' + sys.executable + '\nimport json,os,sys\nfrom pathlib import Path\n'
                      'Path(os.environ["FAKE_CALL"]).write_text(json.dumps(sys.argv))\n'
                      'print(json.dumps({"is_error":False,"subtype":"success","result":"fixture"}))\n')
    claude.chmod(0o755)
    env['LAUNCH_CLAUDE'] = str(claude)


def test_launcher_reroutes_a_fixed_model_without_a_reason_to_the_leaderboard_pick(fake_home):
    # RULE #1 (11-20): it used to stop the job (exit 2); now the leaderboard's pick runs, with a warning.
    home,c,work,env=fake_home
    result=run_launcher(fake_home,'--model','fixture-fast')
    assert result.returncode==0,result.stderr
    assert 'hard-coded model refused' in result.stderr and '[launch.model-selection] WARNING' in result.stderr
    receipt=json.loads((c/'fixture-job.log.selection.json').read_text())
    assert receipt['source']=='leaderboard' and not receipt['model_override']


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
def test_judgment_pin_without_a_reason_refuses_and_names_pick(tmp_path, role):
    # 11-20: any non-empty reason pins a judgment role; a blank one still refuses, naming the pick.
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match=role + '.*leaderboard picks claude-opus-5-5'):
        wm.select(role, 'codex', 'claude-sonnet-5', '  ', path, made_by='gpt-6.1-sol')
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


def test_review_launch_pin_with_any_override_runs_the_pinned_model(fake_home):
    # 11-20 (general, RULE #1 audit): any non-empty --model-override pins a judgment role (math's Sonnet
    # control arm). It runs the pinned model and the ledger records allowed-override.
    _, _, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    fake_claude(fake_home)
    result = run_launcher(fake_home, '--role', 'review', '--made-by', 'gpt-6.1-sol',
                          '--model', 'claude-sonnet-5', '--model-override', 'control arm: Sonnet vs the pick')
    assert result.returncode == 0, result.stderr
    assert 'claude-sonnet-5' in json.loads(Path(env['FAKE_CALL']).read_text())


def test_review_pin_with_an_override_is_selected_and_logged(tmp_path, monkeypatch):
    path = judgment_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_MODEL_OVERRIDE_LOG', str(tmp_path / 'overrides.jsonl'))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    got = wm.select('review', 'codex', 'claude-sonnet-5', 'control arm', path, made_by='gpt-6.1-sol', job='j1')
    assert got['model'] == 'claude-sonnet-5'
    rows = [json.loads(l) for l in (tmp_path / 'state' / 'harness-blocks.jsonl').read_text().splitlines()]
    assert any(r['gate'] == 'selector.judgment-pin' and r['outcome'] == 'allowed-override' for r in rows)


def test_review_pin_refusal_names_pick_even_without_maker(tmp_path):
    path = judgment_roles(tmp_path / 'roles.json')
    with pytest.raises(ValueError, match='review.*leaderboard picks claude-opus-5-5'):
        wm.select('review', 'codex', 'claude-sonnet-5', ' ', path)  # a blank override still refuses


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
    assert 'requires --made-by MODEL' in result.stderr  # independence still refuses; the reason does not
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
    fake_claude(fake_home)
    result = run_launcher(fake_home, '--made-by', 'gpt-6.1-sol', job=job)
    assert result.returncode == 0, result.stderr       # RULE #1: warned, and the leaderboard pick runs
    assert 'the spec names a model for a judgment role' in result.stderr
    assert 'claude-opus-5-5' in json.loads(Path(env['FAKE_CALL']).read_text())


@pytest.mark.parametrize('name', ['sonnet', 'OPUS', 'gpt-6-astra', 'claude-fable-5-2', 'deepseek',
                                 'Gemini 4 Carbon', 'google/gemini-4-hydrogen'])
def test_judgment_spec_names_are_refused_before_executor(fake_home, name):
    _, artifacts, _, env = fake_home
    judgment_roles(Path(env['RH_ROLES_FILE']))
    (artifacts / 'fixture-job.md').write_text('Use {} for the next review.\n'.format(name))
    fake_claude(fake_home)
    result = run_launcher(fake_home, '--role', 'review', '--made-by', 'gpt-6.1-sol')
    assert result.returncode == 0, result.stderr       # RULE #1: warned, and the leaderboard pick runs
    assert ('fixture-job: the spec names a model for a judgment role; the leaderboard picks claude-opus-5-5'
            ) in result.stderr
    assert 'claude-opus-5-5' in json.loads(Path(env['FAKE_CALL']).read_text())


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
    monkeypatch.setenv('RH_CLAUDE_CAP', '0')   # these test the 85% brake; the 80% ceiling has its own tests
    if limit is None:
        monkeypatch.delenv('RH_CLAUDE_OVERFLOW_PERCENT', raising=False)
    else:
        monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', limit)
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {'batch': ['claude-opus-5-5'], 'cheap': ['claude-haiku-5-5']},
                             'routes': {'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'},
                                        'claude-haiku-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-haiku-5.5'}}}))
    return p


def test_agy_never_runs_claude_even_above_the_overflow_threshold(tmp_path, monkeypatch):
    """11-27 Ricardo: "why are we using that? we obviously have a Claude subscription. I think we should focus on
    Neon when using agy." The old 85% overflow to agy's Claude is gone."""
    p = overflow_setup(tmp_path, monkeypatch, 91)
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    got = wm.select('batch', 'claude', path=p)
    assert not (got['executor'] == 'agy' and str(got.get('route_model') or got['model']).startswith('claude')), got
    assert 'overflow' not in got and wm.claude_overflow('claude', 'claude-opus-5-5') is None


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
              'gpt-6.1-sol': ('codex', 'openai/gpt-6.1-sol'), 'gemini-4-hydrogen-high': ('agy', 'google/gemini-4-hydrogen-high'),
              'gemini-4-neon-high': ('agy', 'google/gemini-4-neon-high')}
    path.write_text(json.dumps({'roles': {'review': ['claude-opus-5-5', 'gpt-6.2-sol'], 'batch': ['claude-opus-5-5']},
        'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()},
        'evidence': {'review': {'gemini-4-hydrogen-high': {'n': 3, 'rate': 1.0}}}}))
    return path


def test_an_unpinned_job_goes_to_gemini_first_and_to_codex_only_when_agy_is_closed_or_blocked(tmp_path, monkeypatch):
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    for _ in range(3):
        assert wm.select('batch', 'claude', path=p)['model'] == 'gemini-4-hydrogen-high'
        assert wm.select('review', 'claude', path=p, made_by='gpt-6')['model'] == 'gemini-4-neon-high'
    got = wm.select('batch', 'claude', path=p)
    assert got['source'] == 'delegate' and got['delegate'].startswith('gemini first')
    monkeypatch.setenv('RH_AGY_CLOSED', 'quota')       # launch.sh: the agy run failed on quota
    got = wm.select('batch', 'claude', path=p)
    assert got['model'] == 'gpt-6.1-sol' and got['executor'] == 'codex'   # 11-26: bulk Codex work off 6.2 Sol
    monkeypatch.delenv('RH_AGY_CLOSED')
    state = tmp_path / 'state'                          # agy_quota.blocked() holds the model
    state.mkdir()
    until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).isoformat()
    (state / 'agy-quota.jsonl').write_text(json.dumps({'model': 'gemini-4-hydrogen-high', 'blocked_until': until}) + '\n')
    monkeypatch.setenv('RSTACK_STATE_DIR', str(state))
    got = wm.select('batch', 'claude', path=p)
    assert got['model'] == 'gpt-6.1-sol' and 'skipped gemini-4-hydrogen-high' in ' '.join(got['quota_skipped'])
    monkeypatch.delenv('RSTACK_STATE_DIR')
    monkeypatch.setenv('RH_CODEX_CLOSED', 'quota')
    assert wm.select('batch', 'claude', path=p)['model'] == 'gemini-4-hydrogen-high'
    monkeypatch.delenv('RH_CODEX_CLOSED')
    got = wm.select('review', 'codex', path=p, made_by='gemini-3')     # a Google producer: no Gemini judge
    assert not got['model'].startswith('gemini')


def test_a_returned_job_is_graded_into_its_log_and_the_grades_file(tmp_path):
    p = delegate_roles(tmp_path / 'roles.json')
    log, receipt = tmp_path / 'job.log', tmp_path / 'job.log.selection.json'
    assert wm.main(['--role', 'review', '--made-by', 'gpt-6', '--roles-file', str(p), '--job', 'j',
                    '--log', str(log), '--receipt', str(receipt)]) == 0
    assert wm.main(['--grade', 'partial', '--note', 'half the checks', '--receipt', str(receipt), '--log', str(log)]) == 0
    row = json.loads((tmp_path / 'everyday-grades.jsonl').read_text())
    assert (row['grade'], row['job'], row['model'], row['source_kind']) == ('partial', 'j', 'anthropic/claude-opus-5.5', 'everyday')
    assert 'MODEL_GRADE' in log.read_text()


def test_a_spec_that_pins_its_model_is_never_delegated(tmp_path, monkeypatch):
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
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


def returned_delegate(receipts, job, lane, hours_ago):
    sid = uuid_hex = job + 'sid'
    finished = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).isoformat()
    (receipts / (job + '.log.selection.json')).write_text(json.dumps(dict(
        selection_id=sid, job=job, lane=lane, role='batch', model='gemini-4-hydrogen-low', source='delegate')))
    (receipts / (job + '.log')).write_text('MODEL_OUTCOME ' + json.dumps(dict(selection_id=sid, finished=finished)) + '\n')
    return receipts / (job + '.log.selection.json')


def test_a_returned_delegated_job_is_recorded_ungraded_at_once_and_a_grade_replaces_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    receipts = tmp_path / 'receipts'; receipts.mkdir()
    receipt = returned_delegate(receipts, 'lane-a-job1', 'lane-a', 0)
    assert wm.main(['--record-ungraded', '--receipt', str(receipt), '--log', str(receipts / 'lane-a-job1.log')]) == 0
    rows = [json.loads(l) for l in (receipts / 'everyday-grades.jsonl').read_text().splitlines()]
    assert [(r['grade'], r['job']) for r in rows] == [('void: returned without a grade', 'lane-a-job1')]
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
    assert (row['grade'], row['job']) == ('void: returned without a grade', 'lane-a-old')
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
              'gemini-4-hydrogen-medium': ('agy', 'google/gemini-4-hydrogen-medium'), 'gemini-4-neon-high': ('agy', 'google/gemini-4-neon-high'),
              'gemini-4-hydrogen-high': ('agy', 'google/gemini-4-hydrogen-high')}
    path.write_text(json.dumps({'roles': {'review': ['gemini-4-hydrogen-medium', 'claude-opus-5-5', 'gpt-6.2-astra'],
                                          'batch': ['gemini-4-hydrogen-medium', 'gpt-6.2-sol']},
                                'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()}}))
    return path


@pytest.mark.parametrize('producer,family', [('gemini-3.8-flash-low', 'google'), ('claude-opus-5-5', 'anthropic')])
def test_a_referee_is_never_delegated_to_the_producers_family(tmp_path, monkeypatch, producer, family):
    from bug_verdicts import maker
    p = family_roles(tmp_path / 'roles.json')
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
                                                           hunter_model='gemini-4-hydrogen-low', hunter_maker='google')) + '\n')
    for _ in range(40):
        got = wm.select('review', 'codex', path=p, made_by='claude-opus-5-5', workdir=str(work), lane_dir=str(lane_dir))
        assert maker(got['model'], got['canonical']) not in ('google', 'anthropic'), got
    # A batch-role job on a planted batch: the base pick (Gemini first in batch) moves off the hunter's family too.
    got = wm.select('batch', 'codex', path=p, job='lane-hunt-x', workdir=str(work), lane_dir=str(lane_dir))
    assert got['model'] == 'gpt-6.2-sol' and got['executor'] == 'codex'


def test_a_judging_job_with_an_unknown_producer_is_not_delegated(tmp_path, monkeypatch):
    p = family_roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text()); data['roles']['taste'] = ['claude-opus-5-5']; p.write_text(json.dumps(data))
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
    monkeypatch.delenv('RH_LAUNCHER_EXECUTORS', raising=False)
    for _ in range(40):
        # A caller that runs the model name on its own CLI never gets an agy delegate.
        got = wm.select('batch', 'codex', path=p, follows_route=False)
        assert got['executor'] in ('codex', 'claude') and not got['model'].startswith('gemini'), got
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude')   # a launcher that names what it runs
    for _ in range(40):
        assert wm.select('batch', 'codex', path=p)['executor'] in ('codex', 'claude')


def test_the_stopgap_is_relaxed_a_route_following_caller_gets_delegates_on_all_three(tmp_path, monkeypatch):
    # 11-20: the lanes' launcher now execs rstack tools/launch.sh, which runs codex, claude and agy, so the
    # stopgap of 829d256 no longer holds a delegate to the executor asked for when the caller follows the route.
    p = family_roles(tmp_path / 'roles.json')
    monkeypatch.delenv('RH_LAUNCHER_EXECUTORS', raising=False)
    seen = {wm.select('batch', 'codex', path=p)['executor'] for _ in range(60)}
    assert 'agy' in seen, seen
    out = io.StringIO()
    routes = set()
    for i in range(30):
        out.seek(0); out.truncate()
        with contextlib.redirect_stdout(out):
            assert wm.main(['--role', 'batch', '--executor', 'codex', '--roles-file', str(p), '--print-route',
                            '--job', 'fixture-job', '--log', str(tmp_path / 'job.log'),
                            '--receipt', str(tmp_path / 'r{}.json'.format(i))]) == 0
        routes.add(out.getvalue().split()[1])
    assert 'agy' in routes, routes


def test_retract_marks_a_job_grade_retracted_and_needs_a_reason(tmp_path, capsys):
    import json as _json
    import worker_models as wm
    grades = tmp_path / 'everyday-grades.jsonl'
    grades.write_text(_json.dumps(dict(id='grade-s1', source_kind='everyday', job='job-a', grade='fail',
                                       model='model-1', role='review')) + '\n')
    assert wm.main(['--retract', 'job-a', '--receipt-dir', str(tmp_path)]) != 0
    assert wm.main(['--retract', 'job-a', '--receipt-dir', str(tmp_path), '--reason', 'launcher started agy without Bash']) == 0
    rows = [_json.loads(l) for l in grades.read_text().splitlines()]
    assert rows[-1]['grade'] == 'void: retracted' and rows[-1]['retracted'] == 'fail' and rows[-1]['id'] == 'grade-s1'
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
    monkeypatch.setenv('RH_CLAUDE_CAP', '0')   # these test the executor picker; the ceiling has its own tests
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
    got = wm.select('review', 'codex', path=p, made_by='gemini-4-hydrogen-low')
    assert (got['model'], got['executor']) == ('gpt-6.2-astra', 'codex')
    assert got['executor_choice'].startswith('executor codex: headroom 90% / 100h')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    assert wm.select('review', 'codex', path=p, made_by='gemini-4-hydrogen-low')['model'] == 'claude-opus-5-5'


def test_the_85_percent_brake_no_longer_sends_claude_to_agy(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(90, 20), codex=(99, 100))
    monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', '85')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    got = wm.select('batch', 'codex', path=p)
    assert not (got['executor'] == 'agy' and str(got.get('route_model') or got['model']).startswith('claude')), got


def test_the_headroom_pick_keeps_the_referee_out_of_the_producers_family(tmp_path, monkeypatch):
    from bug_verdicts import maker
    p = headroom_roles(tmp_path / 'roles.json')
    stub_allowance(monkeypatch, claude=(0, 63), codex=(95, 100))
    got = wm.select('review', 'codex', path=p, made_by='claude-opus-5-5')
    assert maker(got['model'], got['canonical']) != 'anthropic' and got['executor'] == 'codex'


def real_allowance_state(tmp_path, monkeypatch, claude_age_s, codex_used=95):
    """The real allowance reader over a temp state dir: codex from a fresh cached snapshot, claude from usage/claude.json."""
    import time
    now = time.time()
    state = tmp_path / 'state'
    (state / 'allowance').mkdir(parents=True)
    (state / 'usage').mkdir()
    (state / 'allowance/snapshot.json').write_text(json.dumps({'_read_at': now, 'codex': {
        'weekly_used_percent': codex_used, 'resets_at': now + 100 * 3600}}))
    if claude_age_s is not None:
        (state / 'usage/claude.json').write_text(json.dumps({'weekly_percent': 0, 'at': now - claude_age_s,
                                                              'source': 'claude-usage: test', 'resets_at': now + 63 * 3600}))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(state))
    monkeypatch.setenv('RSTACK_HOST', 'm5')
    monkeypatch.delenv('RESETS_USAGE_DIR', raising=False)
    monkeypatch.delenv('RH_HEADROOM_ROUTING', raising=False)
    return state / 'asks-waiting/m5-claude-usage.tsv'


def test_unknown_or_stale_claude_usage_keeps_the_last_policy_and_leaves_an_alert_row(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    for age in (None, 3 * 3600):   # missing, then three hours old (the reader runs every 15 min)
        alert = real_allowance_state(tmp_path / str(age), monkeypatch, age)
        got = wm.select('batch', 'codex', path=p)
        assert (got['model'], got['executor']) == ('gpt-6.2-sol', 'codex')   # the leaderboard pick, not moved
        assert 'claude usage unknown' in got['executor_choice'] and 'last policy kept' in got['executor_choice']
        row = alert.read_text().split('\t')
        assert row[1] == 'claude-usage' and 'Claude usage unknown' in row[2]
    # A fresh reading routes by headroom again (Claude 100% left vs Codex 5%).
    real_allowance_state(tmp_path / 'fresh', monkeypatch, 600)
    got = wm.select('batch', 'codex', path=p)
    assert (got['model'], got['executor']) == ('claude-sonnet-5-5', 'claude')


def test_the_picker_does_not_overwrite_the_readers_own_failure_row(tmp_path, monkeypatch):
    p = headroom_roles(tmp_path / 'roles.json')
    alert = real_allowance_state(tmp_path, monkeypatch, None)
    alert.parent.mkdir(parents=True)
    alert.write_text('0.0h\tclaude-usage\tClaude usage not read: usage endpoint answered HTTP 401.\n')
    wm.select('batch', 'codex', path=p)
    assert 'HTTP 401' in alert.read_text()


def science_gate(tmp_path, monkeypatch):
    gate = tmp_path / 'science-publish-gate'
    gate.write_text("#!/usr/bin/env python3\nREVIEWERS = ('fable', 'claude-science', 'opus', 'astra')\nMIN_ACCEPTS = 2\n")
    monkeypatch.setenv('RH_SCIENCE_PUBLISH_GATE', str(gate))
    routes = {'claude-sonnet-5-5': ('claude', 'anthropic/claude-sonnet-5.5'), 'claude-opus-5-5': ('claude', 'anthropic/claude-opus-5.5'),
              'gemini-4-neon-high': ('agy', 'google/gemini-4-neon-high'), 'gpt-6.2-astra': ('codex', 'openai/gpt-6.2-astra'),
              'gpt-6.2-sol': ('codex', 'openai/gpt-6.2-sol'), 'claude-fable-5-2': ('claude', 'anthropic/claude-fable-5.2')}
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {'review': ['claude-sonnet-5-5', 'gemini-4-neon-high', 'claude-opus-5-5', 'gpt-6.2-astra']},
                             'routes': {m: {'cli': c, 'canonical': k} for m, (c, k) in routes.items()}}))
    return p


def test_a_science_publish_review_is_held_to_the_gates_reviewers_and_a_plain_review_still_delegates(tmp_path, monkeypatch):
    # 11-20, math: math_c82r12rvb2_1120 (a public PR text review) was delegated to claude-sonnet-5-5, a reviewer
    # science-publish-gate never counts, so it could not reach the two accepts.
    p = science_gate(tmp_path, monkeypatch)
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    for made_by in ('gpt-6.2-sol', 'claude-opus-5-5'):
        for _ in range(30):
            got = wm.select('review', 'codex', path=p, made_by=made_by, gate='science-publish')
            assert got['model'] in ('claude-opus-5-5', 'gpt-6.2-astra'), got
            assert got['source'] != 'delegate' and got['model_pin'].startswith('science-publish gate')
    assert wm.select('review', 'codex', path=p, made_by='gpt-6.2-sol', gate='science-publish')['executor'] == 'claude'
    # Without the gate line a review still takes part in the delegated share.
    seen = {wm.select('review', 'codex', path=p, made_by='gpt-6.2-sol')['source'] for _ in range(20)}
    assert 'delegate' in seen
    # The spec line is what turns it on, through the CLI the launcher calls.
    spec = tmp_path / 'job.md'
    spec.write_text('Review the PR text.\nGate: science-publish\n')
    assert wm.spec_gate(spec.read_text()) == 'science-publish' and wm.spec_gate('Review the PR text.\n') == ''
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert wm.main(['--role', 'review', '--made-by', 'gpt-6.2-sol', '--roles-file', str(p), '--spec', str(spec),
                        '--print-route', '--job', 'j', '--log', str(tmp_path / 'j.log'),
                        '--receipt', str(tmp_path / 'j.json')]) == 0
    assert out.getvalue().split()[0] == 'claude-opus-5-5'
    # An unreadable gate refuses rather than guessing a reviewer.
    monkeypatch.setenv('RH_SCIENCE_PUBLISH_GATE', str(tmp_path / 'absent'))
    with pytest.raises(ValueError, match='REVIEWERS cannot be read'):
        wm.select('review', 'codex', path=p, made_by='gpt-6.2-sol', gate='science-publish')


@pytest.mark.parametrize('role_args,expected', [(['--role', 'review', '--made-by', 'claude-opus-5-5'], 'referee'),
                                                ([], 'batch')])
def test_the_codex_call_is_told_whether_it_referees(fake_home, role_args, expected):
    """11-20: the Codex wrapper's referee bucket admits only referee calls; launch.sh says which one this is."""
    _, artifacts, _, env = fake_home
    if role_args:
        judgment_roles(Path(env['RH_ROLES_FILE']))
    codex = Path(env['LAUNCH_CODEX'])
    codex.write_text('#!' + sys.executable + '\nimport json,os,sys\nfrom pathlib import Path\n'
                     'Path(os.environ["FAKE_CALL"]).write_text(json.dumps(os.environ.get("RSTACK_CALL_ROLE")))\n')
    result = run_launcher(fake_home, *role_args)
    assert result.returncode == 0, result.stderr
    assert json.loads(Path(env['FAKE_CALL']).read_text()) == expected
    assert json.loads((artifacts / 'fixture-job.log.selection.json').read_text())['call_role'] == expected


# ---- 11-20: Claude ceiling, pacing, Sonnet default, lane shares ---------------------------------------------

def cap_setup(tmp_path, monkeypatch, used, hours=100, history=None, shares=None):
    """A real allowance reader over a fake state dir: claude.json at `used`%, resetting in `hours` h."""
    import time
    now = time.time()
    state = tmp_path / 'state'
    (state / 'usage').mkdir(parents=True, exist_ok=True)
    (state / 'usage/claude.json').write_text(json.dumps(
        {'weekly_percent': used, 'at': now - 60, 'resets_at': dt.datetime.fromtimestamp(
            now + hours * 3600, dt.timezone.utc).isoformat()}))
    if history:
        (state / 'usage/claude-history.jsonl').write_text(''.join(
            json.dumps({'at': now - h * 3600, 'weekly_percent': pct}) + '\n' for h, pct in history))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(state))
    monkeypatch.delenv('RESETS_USAGE_DIR', raising=False)
    monkeypatch.delenv('RH_CLAUDE_CAP', raising=False)
    monkeypatch.delenv('RH_CLAUDE_OVERFLOW_PERCENT', raising=False)
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    monkeypatch.setenv('RSTACK_CLAUDE_SHARES', str(tmp_path / 'shares.json'))
    monkeypatch.setenv('RH_CLAUDE_PROJECTS', str(tmp_path / 'no-projects'))
    if shares is not None:
        (tmp_path / 'shares.json').write_text(json.dumps(shares))
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {'batch': ['claude-opus-5-5'], 'review': ['claude-opus-5-5']}, 'routes': {
        'claude-opus-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'},
        'claude-sonnet-5-5': {'cli': 'claude', 'canonical': 'anthropic/claude-sonnet-5.5'},
        'gpt-6.2-astra': {'cli': 'codex', 'canonical': 'openai/gpt-6.2-astra'},
        'gpt-6.2-sol': {'cli': 'codex', 'canonical': 'openai/gpt-6.2-sol'}}}))
    return p


@pytest.fixture
def deadline_registry(tmp_path):
    entry = dict(kind='competition', what='Fixture final',
                 ends=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)).isoformat(timespec='minutes'))
    lanes = tmp_path / 'lanes'
    lanes.mkdir()
    (lanes / 'REGISTRY.json').write_text(json.dumps({'lanes': {
        'timed': {'status': 'active', 'deadlines': [entry]},
        'plain': {'status': 'active'},
    }}))
    return lanes, entry


@pytest.mark.parametrize('history,pressure', [
    ([(5, 35), (0, 40)], 'projects 140%'),
    ([(5, 40), (0, 40)], 'budget line'),
])
def test_live_deadline_keeps_opus_above_pacing_or_budget_line(tmp_path, monkeypatch, deadline_registry,
                                                           history, pressure):
    lanes, entry = deadline_registry
    p = cap_setup(tmp_path, monkeypatch, 40, history=history)
    monkeypatch.setenv('RH_CLAUDE_BUDGET_LINE', '1')
    plain = wm.select('batch', 'claude', path=p, lane='plain', lane_dir=lanes / 'plain')
    assert plain['executor'] == 'codex' and pressure in plain['claude_cap']
    timed = wm.select('batch', 'claude', path=p, lane='timed', lane_dir=lanes / 'timed')
    assert (timed['executor'], timed['model']) == ('claude', 'claude-opus-5-5')
    assert timed['deadline'] == entry
    assert 'Fixture final ends ' + entry['ends'] in timed['claude_cap']


def test_live_deadline_is_exempt_from_share(tmp_path, monkeypatch, deadline_registry):
    lanes, _ = deadline_registry
    p = cap_setup(tmp_path, monkeypatch, 10, history=[(5, 10), (0, 10)],
                  shares={'default': {'max_week_percent': 0, 'models': ['sonnet']}})
    plain = wm.select('review', 'claude', path=p, lane='plain', made_by='gemini-3')
    assert plain['executor'] == 'codex' and '0% share' in plain['claude_cap']
    monkeypatch.setenv('RH_LANE_REGISTRY', str(lanes / 'REGISTRY.json'))
    timed = wm.claude_cap.decide('claude-opus-5-5', 'timed', 'review', True, wm._allowance())
    assert timed['leave'] == '' and timed['model'] == 'claude-opus-5-5'
    assert any('share do not apply' in note for note in timed['notes'])


def test_live_deadline_still_hits_claude_ceiling(tmp_path, monkeypatch, deadline_registry):
    lanes, entry = deadline_registry
    p = cap_setup(tmp_path, monkeypatch, 80)
    result = wm.select('batch', 'claude', path=p, lane='timed', lane_dir=lanes / 'timed')
    assert result['executor'] == 'codex' and '>= 80% ceiling' in result['claude_cap']
    assert result['deadline'] == entry


def test_live_deadline_skips_gemini_first_and_exploration(tmp_path, monkeypatch, deadline_registry):
    lanes, entry = deadline_registry
    p = delegate_roles(tmp_path / 'roles.json')
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    plain = wm.select('batch', 'claude', path=p, lane='plain')
    assert plain['model'] == 'gemini-4-hydrogen-high' and 'gemini first' in plain['delegate']
    log, receipt = tmp_path / 'timed.log', tmp_path / 'timed.selection.json'
    assert wm.main(['--role', 'batch', '--executor', 'codex', '--roles-file', str(p),
                    '--lane', 'timed', '--lane-dir', str(lanes / 'timed'), '--print-route',
                    '--log', str(log), '--receipt', str(receipt)]) == 0
    timed = json.loads(receipt.read_text())
    assert (timed['executor'], timed['model'], timed['source']) == ('claude', 'claude-opus-5-5', 'leaderboard')
    assert timed['deadline'] == entry
    logged = next(line for line in log.read_text().splitlines() if line.startswith('MODEL_SELECTION '))
    assert json.loads(logged.split(' ', 1)[1])['deadline'] == entry
    trial = tmp_path / 'trial.json'
    trial.write_text(json.dumps(dict(name='fixture trial', role='batch',
                                     models=['gemini-4-hydrogen-high', '@leaderboard'])))
    monkeypatch.setenv('RH_MODEL_TRIAL', str(trial))
    plain = wm.select('batch', 'claude', path=p, lane='plain', job='plain-job', explore='gpt-6.2-sol')
    assert plain['trial'] == 'fixture trial'
    timed = wm.select('batch', 'claude', path=p, lane='timed', lane_dir=lanes / 'timed',
                      job='timed-job', explore='gpt-6.2-sol')
    # an explicit --explore is the operator's own choice and runs; a deadline lane only skips joining the trial
    assert timed['model'] == 'gpt-6.2-sol' and 'trial' not in timed


def test_deadline_ranking_respects_quota_family_and_executor(tmp_path, monkeypatch, deadline_registry):
    lanes, entry = deadline_registry
    p = delegate_roles(tmp_path / 'roles.json')
    data = json.loads(p.read_text())
    data['roles']['review'].insert(0, 'gemini-4-neon-high')
    p.write_text(json.dumps(data))
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    select = dict(path=p, lane='timed', lane_dir=lanes / 'timed', made_by='claude-sonnet-5-5')
    top = wm.select('review', 'codex', **select)
    assert top['model'] == 'gemini-4-neon-high' and top['deadline'] == entry

    until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat()
    (tmp_path / 'agy-quota.jsonl').write_text(json.dumps(
        {'model': 'gemini-4-neon-high', 'blocked_until': until}) + '\n')
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    quota = wm.select('review', 'codex', **select)
    assert quota['model'] == 'gpt-6.2-sol' and 'gemini-4-neon-high' in quota['quota_skipped'][0]

    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'no-quota'))
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude')
    available = wm.select('review', 'claude', **dict(select, made_by='gpt-6.2-sol'))
    assert (available['executor'], available['model']) == ('claude', 'claude-opus-5-5')


def test_unreadable_deadline_registry_changes_nothing(tmp_path, monkeypatch, deadline_registry):
    lanes, entry = deadline_registry
    p = cap_setup(tmp_path, monkeypatch, 40, history=[(5, 35), (0, 40)])
    valid = wm.select('batch', 'claude', path=p, lane='timed', lane_dir=lanes / 'timed')
    assert valid['deadline'] == entry and valid['executor'] == 'claude'
    plain = wm.select('batch', 'claude', path=p, lane='plain', lane_dir=lanes / 'plain')
    (tmp_path / 'broken.json').write_text('{')
    for registry in ('missing.json', 'broken.json'):
        monkeypatch.setenv('RH_LANE_REGISTRY', str(tmp_path / registry))
        timed = wm.select('batch', 'claude', path=p, lane='timed', lane_dir=lanes / 'timed')
        assert timed['executor'] == plain['executor'] == 'codex'
        assert timed['claude_cap'] == plain['claude_cap'] and 'deadline' not in timed


def test_sonnet_is_preferred_only_for_mechanical_and_batch_claude_picks(tmp_path, monkeypatch):
    # 11-20 (Ricardo): "it shouldn't be the default ... it's more for mechanical work." No global Sonnet default.
    p = cap_setup(tmp_path, monkeypatch, 10, hours=160, history=[(2, 9.5), (0, 10)])
    data = json.loads(p.read_text())
    data['roles'].update({r: ['claude-opus-5-5'] for r in ('mechanical', 'review', 'judge', 'taste', 'ideation', 'builder', 'design')})
    p.write_text(json.dumps(data))
    for role in ('batch', 'mechanical'):
        got = wm.select(role, 'claude', path=p)
        assert got['model'] == 'claude-sonnet-5-5' and 'Sonnet 5.5 preferred' in got['claude_cap'], role
    for role in ('review', 'judge', 'taste', 'ideation', 'builder', 'design'):
        got = wm.select(role, 'claude', path=p, made_by='gpt-6.2-sol')
        assert got['model'] == 'claude-opus-5-5' and 'claude_cap' not in got, role
    # an explicit model or spec pin wins over the preference
    assert wm.select('batch', 'claude', path=p, pin='sealed referee')['model'] == 'claude-opus-5-5'
    # a spec line "Model: opus" is no longer parsed or required
    spec, log, receipt = tmp_path / 'spec.md', tmp_path / 'job.log', tmp_path / 'r.json'
    spec.write_text('do it\nModel: opus\n')
    assert wm.main(['--role', 'review', '--made-by', 'gpt-6.2-sol', '--executor', 'claude', '--roles-file', str(p),
                    '--spec', str(spec), '--job', 'j', '--log', str(log), '--receipt', str(receipt)]) == 0
    assert json.loads(receipt.read_text())['model'] == 'claude-opus-5-5'


def test_at_the_ceiling_claude_is_refused_and_the_job_takes_codex_then_agy(tmp_path, monkeypatch):
    p = cap_setup(tmp_path, monkeypatch, 80)
    got = wm.select('batch', 'claude', path=p)
    assert (got['executor'], got['model']) == ('codex', 'gpt-6.2-sol')
    assert '>= 80% ceiling' in got['claude_cap'] and 'general' in got['claude_cap']
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude,agy')   # no Codex on this launcher
    got = wm.select('batch', 'claude', path=p)
    assert not (got['executor'] == 'agy' and str(got.get('route_model') or got['model']).startswith('claude')), got
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude')
    # RULE #1 (11-20): with nowhere to reroute, the job stays on Claude with a warning instead of stopping
    got = wm.select('batch', 'claude', path=p)
    assert got['executor'] == 'claude' and 'no fallback route' in got['claude_cap']
    # a pinned or explicit model has no fallback either: it is refused, not swapped
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    with pytest.raises(ValueError, match='ceiling'):
        wm.select('batch', 'claude', path=p, pin='sealed referee')
    # the ceiling is a knob, and below it nothing is refused
    monkeypatch.setenv('RH_CLAUDE_CEILING_PERCENT', '95')
    monkeypatch.setenv('RH_CLAUDE_PACE_OFF_PERCENT', '1000')
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'


def test_a_claude_hold_falls_back_to_agys_gemini_not_agys_claude(tmp_path, monkeypatch):
    # 11-22 (bio via general): Codex refused a builder job and the fallback took claude-sonnet-5-5 during a hold.
    p = cap_setup(tmp_path, monkeypatch, 40, hours=160, history=[(2, 40), (0, 40)],
                  shares={'default': {'max_week_percent': 0}})
    data = json.loads(p.read_text())
    data['routes'].update({m: {'cli': 'agy', 'canonical': 'google/' + m}
                           for m in ('gemini-4-neon-high', 'gemini-4-hydrogen-high')})
    data['roles']['builder'] = ['claude-opus-5-5']
    p.write_text(json.dumps(data))
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude,agy')   # Codex closed or absent
    got = wm.select('batch', 'claude', path=p)
    assert (got['executor'], got['model'], got['route_model']) == ('agy', 'gemini-4-hydrogen-high', 'gemini-4-hydrogen-high')
    got = wm.select('builder', 'claude', path=p, made_by='gpt-6.2-sol')
    assert (got['executor'], got['model']) == ('agy', 'gemini-4-neon-high')
    # with Codex open the hold still takes Codex first
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    assert wm.select('batch', 'claude', path=p)['executor'] == 'codex'
    # (the ceiling without a hold still takes agy's Claude: test_at_the_ceiling_..._then_agy)


def test_a_referee_never_falls_back_into_the_family_it_judges(tmp_path, monkeypatch):
    p = cap_setup(tmp_path, monkeypatch, 85)
    data = json.loads(p.read_text())
    data['roles']['review'] = ['claude-opus-5-5']
    p.write_text(json.dumps(data))
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude,agy')
    got = wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol')
    assert not (got['executor'] == 'agy' and str(got.get('route_model') or got['model']).startswith('claude')), got
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude,codex')   # Codex is the producer's family, agy absent
    got = wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol')
    assert got['executor'] == 'claude' and 'no fallback route' in got['claude_cap']   # never into GPT


def test_from_70_percent_the_receipt_warns(tmp_path, monkeypatch):
    p = cap_setup(tmp_path, monkeypatch, 72, hours=160, history=[(2, 72), (0, 72)])
    got = wm.select('batch', 'claude', path=p)
    assert got['executor'] == 'claude' and 'warning from 70%' in got['claude_warning']
    p = cap_setup(tmp_path, monkeypatch, 69, hours=160, history=[(2, 69), (0, 69)])
    assert 'claude_warning' not in wm.select('batch', 'claude', path=p)


def test_pacing_downshifts_opus_to_sonnet_then_claude_to_codex(tmp_path, monkeypatch):
    # 40% now, +0.2%/h x 100 h = 60%: under 80, Opus (with a reason) stays
    p = cap_setup(tmp_path, monkeypatch, 40, history=[(5, 39), (0, 40)])
    assert wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol')['model'] == 'claude-opus-5-5'
    # +0.5%/h x 100 h = 90%: past 80, short of the wall: Opus goes to Sonnet and the receipt says why
    p = cap_setup(tmp_path, monkeypatch, 40, history=[(5, 37.5), (0, 40)])
    got = wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol')
    assert got['model'] == 'claude-sonnet-5-5' and got['executor'] == 'claude'
    assert 'projects 90% > 80%' in got['claude_cap'] and 'Opus downshifted' in got['claude_cap']
    # +1%/h x 100 h = 140%: on course for 100%, so the job leaves Claude
    p = cap_setup(tmp_path, monkeypatch, 40, history=[(5, 35), (0, 40)])
    got = wm.select('review', 'claude', path=p, made_by='gemini-3.8-flash-low')
    assert got['executor'] == 'codex' and 'projects 140%' in got['claude_cap'] and 'leaves Claude' in got['claude_cap']
    # no history yet: this week's average (28% over 168-100=68 h is 0.41%/h; x 100 h = 69%)
    (tmp_path / 'state/usage/claude-history.jsonl').unlink()
    p = cap_setup(tmp_path, monkeypatch, 28)
    assert wm.claude_cap.burn_rate(wm._allowance(), __import__('time').time(), 28, 100)[1].startswith('week average')


def test_a_pinned_job_on_course_for_the_wall_stays_on_claude(tmp_path, monkeypatch):
    # 11-27: a math referee (science-publish gate, GPT producer) had no route at a 130% projection and was refused.
    # A projection is not the ceiling, so a pinned or gated job stays on its model with the reason in the receipt.
    p = cap_setup(tmp_path, monkeypatch, 40, history=[(5, 35), (0, 40)])
    got = wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol', model='claude-opus-5-5', override='test pin')
    assert got['executor'] == 'claude' and got['model'] == 'claude-opus-5-5'
    assert 'projects 140%' in got['claude_cap'] and 'pinned, so it stays on Claude' in got['claude_cap']
    # the ceiling itself still refuses a pinned job
    p = cap_setup(tmp_path, monkeypatch, 85, history=[(5, 84), (0, 85)])
    with pytest.raises(ValueError, match='ceiling'):
        wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol', model='claude-opus-5-5', override='test pin')


def test_burn_rate_ignores_readings_from_before_a_reset(tmp_path, monkeypatch):
    cap_setup(tmp_path, monkeypatch, 5, history=[(5, 90), (3, 1), (0, 5)])
    import time
    rate, basis = wm.claude_cap.burn_rate(wm._allowance(), time.time(), 5, 100)
    assert abs(rate - 4 / 3) < 0.01 and 'readings' in basis


def write_transcript(root, project, model, tokens, hours_ago=1):
    import time
    d = root / project
    d.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.fromtimestamp(time.time() - hours_ago * 3600, dt.timezone.utc).isoformat()
    with (d / 's.jsonl').open('a') as f:
        f.write(json.dumps({'timestamp': ts, 'message': {'id': 'm' + str(len(list(d.iterdir()))) + model + str(tokens),
                'model': model, 'usage': {'input_tokens': tokens, 'output_tokens': 0}}}) + '\n')


def test_a_lane_over_its_share_is_refused_claude_and_falls_back(tmp_path, monkeypatch):
    shares = {'meccog-apoe4': {'max_week_percent': 5, 'models': ['sonnet']}, 'default': {'max_week_percent': 60}}
    p = cap_setup(tmp_path, monkeypatch, 30, hours=100, history=[(5, 29.9), (0, 30)], shares=shares)
    proj = tmp_path / 'projects'
    monkeypatch.setenv('RH_CLAUDE_PROJECTS', str(proj))
    # meccog holds 600 of 1000 weighted tokens = 18% of the 30% week; other lanes hold the rest
    write_transcript(proj, '-h-wt-kb-meccog-apoe4', 'claude-sonnet-5-5', 600)
    write_transcript(proj, '-h-dev-tools', 'claude-sonnet-5-5', 400)
    got = wm.select('batch', 'claude', path=p, lane='meccog-apoe4')
    assert got['executor'] == 'codex'
    assert 'lane meccog-apoe4 used 18.0% of 30% weekly' in got['claude_cap'] and '5% share' in got['claude_cap']
    # the same week, a lane without an entry gets the default cap and keeps Claude
    write_transcript(proj, '-h-share-lanes-math-j1', 'claude-sonnet-5-5', 100)
    got = wm.select('batch', 'claude', path=p, lane='math')
    assert got['executor'] == 'claude' and 'share' in got['claude_cap']
    # a lane under its cap stays on Claude; its models list moves Opus to Sonnet
    shares['meccog-apoe4']['max_week_percent'] = 50
    (tmp_path / 'shares.json').write_text(json.dumps(shares))
    (tmp_path / 'state/usage/claude-lanes-cache.json').unlink()
    got = wm.select('review', 'claude', path=p, lane='meccog-apoe4', made_by='gpt-6.2-sol')
    assert (got['executor'], got['model']) == ('claude', 'claude-sonnet-5-5') and 'allows sonnet' in got['claude_cap']


def test_opus_weighs_five_times_sonnet_in_a_lanes_share(tmp_path):
    proj = tmp_path / 'p'
    write_transcript(proj, '-a-lanes-x', 'claude-opus-5-5', 100)
    write_transcript(proj, '-a-lanes-y', 'claude-sonnet-5-5', 500)
    import time
    w = wm.claude_cap.lane_weights(time.time() - 86400, proj)
    assert w == {'-a-lanes-x': 500.0, '-a-lanes-y': 500.0}


def test_claude_usage_keeps_a_history_for_pacing(tmp_path):
    from importlib.machinery import SourceFileLoader
    mod = SourceFileLoader('claude_usage_h', str(ROOT.parent / 'rstack/tools/claude-usage')).load_module()
    path = tmp_path / 'claude-history.jsonl'
    mod.append_history(path, {'at': 1000, 'weekly_percent': 5.0, 'resets_at': 'x'})
    mod.append_history(path, {'at': 1000 + 900, 'weekly_percent': 5.5, 'resets_at': 'x', 'source': 'ignored'})
    mod.append_history(path, {'at': 1000 + 15 * 86400, 'weekly_percent': 9.0})   # drops the two older than 14 days
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert rows == [{'at': 1000 + 15 * 86400, 'weekly_percent': 9.0}]


def test_math_producers_and_proof_run_on_astra_and_carbon_referees_math(tmp_path, monkeypatch):
    """11-26 (Ricardo: "Cinna Davis: best math model"): math producer jobs and proof go to Astra 6.2; math referees
    stay on Carbon-high, so Astra-made math work is never graded by Astra. Neon/Hydrogen high elsewhere."""
    routes = {m: {'cli': 'agy', 'canonical': 'google/' + m} for m in (
        'gemini-4-argon-low', 'gemini-4-argon-medium', 'gemini-4-carbon-low', 'gemini-4-carbon-medium',
        'gemini-4-carbon-high', 'gemini-4-neon-high', 'gemini-4-neon-medium',
        'gemini-4-hydrogen-low', 'gemini-4-hydrogen-medium', 'gemini-4-hydrogen-high')}
    routes['gpt-6.2-sol'] = {'cli': 'codex', 'canonical': 'openai/gpt-6.2-sol'}
    routes['gpt-6.2-astra'] = {'cli': 'codex', 'canonical': 'openai/gpt-6.2-astra'}
    routes['claude-opus-5-5'] = {'cli': 'claude', 'canonical': 'anthropic/claude-opus-5.5'}
    gemini_roles = wm.GEMINI_ROLES['neon'] + wm.GEMINI_ROLES['hydrogen']
    p = tmp_path / 'roles.json'
    p.write_text(json.dumps({'roles': {r: ['gpt-6.2-sol', 'claude-opus-5-5'] for r in gemini_roles}, 'routes': routes}))
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
    for role in gemini_roles:
        got = wm.select(role, 'codex', path=p, lane='planets',
                        made_by='claude-opus-5-5' if role in wm.INDEPENDENT else '')
        assert got['model'] == ('gemini-4-hydrogen-high' if role in wm.GEMINI_ROLES['hydrogen']
                                else 'gemini-4-neon-high'), (role, got['model'])
        got_math = wm.select(role, 'codex', path=p, lane='math',
                             made_by='gpt-6.2-astra' if role in wm.INDEPENDENT else '')
        want = ('gemini-4-carbon-high', 'agy') if role in wm.JUDGMENT else ('gpt-6.2-astra', 'codex')
        assert (got_math['model'], got_math['executor']) == want, (role, got_math)
    # with Codex closed, math producer work falls back to Carbon-high
    monkeypatch.setenv('RH_CODEX_CLOSED', 'rate limit')
    got = wm.select('builder', 'codex', path=p, lane='math')
    assert (got['model'], got['executor']) == ('gemini-4-carbon-high', 'agy')
    monkeypatch.delenv('RH_CODEX_CLOSED')
    # proof goes to Astra from any lane (even with a Claude leaderboard pick), via ROLE_ROWS -> builder
    p.write_text(json.dumps({'roles': {**{r: ['gpt-6.2-sol'] for r in gemini_roles}, 'builder': ['claude-opus-5-5']},
                             'routes': routes}))
    got_proof = wm.select('proof', 'claude', path=p, lane='planets')
    assert (got_proof['model'], got_proof['executor']) == ('gpt-6.2-astra', 'codex')
    # Cross-family independence: a Carbon-produced review in math is refereed off Gemini
    got_rev = wm.select('review', 'codex', path=p, lane='math', made_by='gemini-4-carbon-high')
    assert not got_rev['model'].startswith('gemini')
    assert wm.gemini_floor('gemini-4-carbon-low', json.loads(p.read_text()))[0] == 'gemini-4-carbon-medium'


def test_no_gemini_job_runs_below_medium(tmp_path, monkeypatch):
    p = tmp_path / 'roles.json'
    routes = {m: {'cli': 'agy', 'canonical': 'google/' + m} for m in ('gemini-3.8-flash-low', 'gemini-3.8-flash-medium')}
    p.write_text(json.dumps({'roles': {'batch': ['gemini-3.8-flash-low']}, 'routes': routes}))
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'agy')
    monkeypatch.setenv('RH_HEADROOM_ROUTING', '0')
    got = wm.select('batch', 'agy', path=p)
    assert got['model'] == 'gemini-3.8-flash-medium' and 'gemini floor' in got['gemini_floor']
    assert wm.gemini_floor('gemini-4-neon-high', json.loads(p.read_text())) is None

def test_a_model_trial_alternates_by_job_keeps_a_jobs_arm_and_stops_at_n(tmp_path, monkeypatch):
    # 11-22 (Ricardo via general): Neon-medium vs Opus 5.5 on the next builder jobs, by turns, graded as usual.
    p = cap_setup(tmp_path, monkeypatch, 10, hours=160, history=[(2, 9.5), (0, 10)])
    data = json.loads(p.read_text())
    data['roles']['builder'] = ['claude-opus-5-5', 'gpt-6.2-sol']
    data['routes']['gemini-4-neon-medium'] = {'cli': 'agy', 'canonical': 'google/gemini-4-neon-medium'}
    p.write_text(json.dumps(data))
    (tmp_path / 'trial.json').write_text(json.dumps({'name': 't1', 'role': 'builder', 'n': 3,
                                                     'models': ['gemini-4-neon-medium', 'claude-opus-5-5']}))
    monkeypatch.setenv('RH_MODEL_TRIAL', str(tmp_path / 'trial.json'))
    monkeypatch.setenv('RH_MODEL_TRIAL_LEDGER', str(tmp_path / 'trial.jsonl'))

    def run(job, role='builder', executor='codex'):
        log, receipt = tmp_path / (job + '.log'), tmp_path / (job + '.log.selection.json')
        assert wm.main(['--role', role, '--executor', executor, '--roles-file', str(p), '--job', job,
                        '--print-route', '--log', str(log), '--receipt', str(receipt)]) == 0
        return json.loads(receipt.read_text())
    got = [run(j) for j in ('a', 'b', 'c')]
    assert [(r['model'], r['executor'], r['trial']) for r in got] == [
        ('gemini-4-neon-medium', 'agy', 't1'), ('claude-opus-5-5', 'claude', 't1'), ('gemini-4-neon-medium', 'agy', 't1')]
    assert 'model trial t1 (builder job 2 of 3)' in got[1]['delegate']
    assert run('b')['model'] == 'claude-opus-5-5'          # a reselected job keeps its arm
    assert 'trial' not in run('d', executor='claude')                          # n reached: back to the leaderboard and the draw
    assert 'trial' not in run('e', role='batch', executor='claude')           # other roles are untouched
    # the report reads grades and wall time beside each receipt
    rec = json.loads((tmp_path / 'a.log.selection.json').read_text())
    (tmp_path / 'everyday-grades.jsonl').write_text(json.dumps({'id': 'grade-' + rec['selection_id'], 'grade': 'pass'}) + '\n')
    lines = wm.trial_report('t1', [tmp_path / 'trial.jsonl'], p)
    assert any(l.startswith('builder gemini-4-neon-medium: 1 graded (pass 1') and '1 pending' in l for l in lines)
    assert any(l.startswith('builder claude-opus-5-5: 0 graded') and '1 pending' in l for l in lines)


def test_the_trial_runs_in_several_roles_against_each_jobs_own_pick_and_takes_explore_jobs(tmp_path, monkeypatch):
    # 11-23 (Ricardo via general: "Keep using Neon."): the 11-22 trial drew one job in a day. Builder only, and
    # lanes launch builder work with --explore, which skipped it.
    p = cap_setup(tmp_path, monkeypatch, 10, hours=160, history=[(2, 9.5), (0, 10)])
    data = json.loads(p.read_text())
    data['roles']['builder'] = ['claude-opus-5-5', 'gpt-6.2-sol']
    data['roles']['review'] = ['gpt-6.2-astra', 'claude-opus-5-5']
    data['routes']['gemini-4-neon-medium'] = {'cli': 'agy', 'canonical': 'google/gemini-4-neon-medium'}
    p.write_text(json.dumps(data))
    (tmp_path / 'trial.json').write_text(json.dumps({'name': 't2', 'roles': ['builder', 'review'], 'n': 2,
                                                     'models': ['gemini-4-neon-medium', '@leaderboard']}))
    monkeypatch.setenv('RH_MODEL_TRIAL', str(tmp_path / 'trial.json'))
    monkeypatch.setenv('RH_MODEL_TRIAL_LEDGER', str(tmp_path / 'trial.jsonl'))

    def run(job, *extra, role='builder', executor='claude'):
        log, receipt = tmp_path / (job + '.log'), tmp_path / (job + '.log.selection.json')
        assert wm.main(['--role', role, '--executor', executor, '--roles-file', str(p), '--job', job, *extra,
                        '--print-route', '--log', str(log), '--receipt', str(receipt)]) == 0
        return json.loads(receipt.read_text())
    a = run('a', '--explore', 'gpt-6.2-sol')                      # an explore job joins: Neon's turn first
    assert (a['model'], a['trial'], a['source']) == ('gemini-4-neon-medium', 't2', 'delegate')
    b = run('b', '--explore', 'gpt-6.2-sol')                      # the other arm is what the job would have run
    assert (b['model'], b['trial']) == ('gpt-6.2-sol', 't2')
    assert 'trial' not in run('c', '--explore', 'gpt-6.2-sol')    # builder n reached
    r1 = run('r1', '--made-by', 'claude-opus-5-5', role='review', executor='codex')
    r2 = run('r2', '--made-by', 'claude-opus-5-5', role='review', executor='codex')
    assert [(r['model'], r.get('trial')) for r in (r1, r2)] == [('gemini-4-neon-medium', 't2'), ('gpt-6.2-astra', 't2')]
    assert wm.gradeable(a) and wm.gradeable(r1)                   # every trial job owes a grade
    pinned = run('d', '--model', 'gpt-6.2-sol', '--model-override', 'operator choice', executor='codex')
    assert 'trial' not in pinned                                  # an explicit model is never taken
    # an arm listed twice gets two turns in three
    (tmp_path / 'trial.json').write_text(json.dumps({'name': 't3', 'roles': ['builder'], 'n': 6,
                                                     'models': ['gemini-4-neon-medium', 'gemini-4-neon-medium', '@leaderboard']}))
    assert [run('w%d' % i, '--explore', 'gpt-6.2-sol')['model'] for i in range(6)] == [
        'gemini-4-neon-medium', 'gemini-4-neon-medium', 'gpt-6.2-sol'] * 2
    # a role can have its own arms: Fable 1 in 6 in review only
    (tmp_path / 'trial.json').write_text(json.dumps({'name': 't4', 'roles': ['builder', 'review'], 'n': 6,
        'models': ['gemini-4-neon-medium', '@leaderboard'],
        'role_models': {'review': ['gemini-4-neon-medium', 'gemini-4-neon-medium', '@leaderboard',
                                     'gemini-4-neon-medium', 'claude-fable-5-2', '@leaderboard']}}))
    data = json.loads(p.read_text())
    data['routes'].setdefault('claude-fable-5-2', {'cli': 'claude', 'canonical': 'anthropic/claude-fable-5.2'})
    p.write_text(json.dumps(data))
    got = [run('v%d' % i, '--made-by', 'gpt-6.2-sol', role='review', executor='codex')['model'] for i in range(6)]
    assert got.count('gemini-4-neon-medium') == 3 and got.count('claude-fable-5-2') == 1, got
    assert [run('u%d' % i, '--explore', 'gpt-6.2-sol')['model'] for i in range(2)] == [
        'gemini-4-neon-medium', 'gpt-6.2-sol']                       # builder keeps the common arms
    lines = wm.trial_report('t2', [tmp_path / 'trial.jsonl'], p)
    assert sum(l.startswith('review ') for l in lines) == 2 and sum(l.startswith('builder ') for l in lines) == 2


def test_biology_draws_neon_as_a_delegate():
    assert 'biology' in wm.GEMINI_ROLES['neon']


def test_the_last_hours_before_the_reset_spend_down_on_their_own(tmp_path, monkeypatch):
    # 11-22 (Ricardo via general): "You have 5 hours to spend the money." No dated file, no manual step.
    p = cap_setup(tmp_path, monkeypatch, 85, hours=4, history=[(2, 70), (0, 85)])
    data = json.loads(p.read_text())
    data['roles']['builder'] = ['claude-opus-5-5']
    p.write_text(json.dumps(data))
    got = wm.select('builder', 'claude', path=p, made_by='gpt-6.2-sol')
    assert (got['executor'], got['model']) == ('claude', 'claude-opus-5-5')           # no Sonnet move, no leave
    assert 'spend-down' in got['claude_cap'] and 'ceiling 95%' in got['claude_cap']
    monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', '85')
    assert wm.claude_overflow('claude', 'claude-opus-5-5') is None                     # 85% brake moved to 95
    (tmp_path / "b").mkdir()
    p96 = cap_setup(tmp_path / "b", monkeypatch, 96, hours=4)
    assert '>= 95% ceiling' in wm.select('batch', 'claude', path=p96)['claude_cap']     # general's last 5%
    (tmp_path / "c").mkdir()
    p = cap_setup(tmp_path / "c", monkeypatch, 85, hours=30, history=[(2, 84), (0, 85)])
    assert '>= 80% ceiling' in wm.select('batch', 'claude', path=p)['claude_cap']      # earlier in the week: 80
    monkeypatch.setenv('RH_CLAUDE_OVERFLOW_PERCENT', '85')   # cap_setup clears it
    assert wm.claude_overflow('claude', 'claude-opus-5-5') is None                     # 11-27: agy never runs Claude

def test_a_returned_review_job_owes_a_grade_however_it_was_picked(tmp_path, monkeypatch, capsys):
    # 11-22: Astra is the leaderboard's own review pick, so its referee runs were never on the ungraded list.
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setattr(wm, 'UNGRADED_TODAY', [])
    receipts = tmp_path / 'receipts'; receipts.mkdir()
    for job, role in (('lane-a-ref', 'review'), ('lane-a-batch', 'batch')):
        r = returned_delegate(receipts, job, 'lane-a', 25)
        r.write_text(json.dumps(dict(json.loads(r.read_text()), role=role, source='leaderboard', model='gpt-6.2-astra')))
    assert wm.main(['--sweep-ungraded', str(receipts)]) == 0
    out = capsys.readouterr().out
    assert 'ungraded after 24 h: lane-a-ref' in out and 'lane-a-batch' not in out
    assert wm.gradeable({'source': 'explore', 'role': 'ideation'}) and not wm.gradeable({'source': 'leaderboard', 'role': 'builder'})


def test_a_one_off_ceiling_raise_ends_on_its_own(tmp_path, monkeypatch):
    # 11-22 (Ricardo via general, 95% with 2 h left): "honestly, you could spend it." 99% until the reset only.
    p = cap_setup(tmp_path, monkeypatch, 96, hours=2)
    monkeypatch.setenv('RH_CLAUDE_CEILING_PERCENT', '99')
    monkeypatch.setenv('RH_CLAUDE_CEILING_UNTIL', (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat())
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'                 # 96% < 97%
    # 11-23: 99% put general out at 100% overnight; a raise stops at 97%, so the last 3% is always general's.
    p = cap_setup(tmp_path, monkeypatch, 97, hours=2)
    monkeypatch.setenv('RH_CLAUDE_CEILING_PERCENT', '99')
    monkeypatch.setenv('RH_CLAUDE_CEILING_UNTIL', (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat())
    assert '>= 97% ceiling' in wm.select('batch', 'claude', path=p)['claude_cap']
    monkeypatch.setenv('RH_CLAUDE_CEILING_UNTIL', '2026-01-01T00:00:00Z')
    assert '>= 95% ceiling' in wm.select('batch', 'claude', path=p)['claude_cap']      # expired: the rule is back
    monkeypatch.setenv('RH_CLAUDE_CEILING_UNTIL', 'not a date')
    assert '>= 95% ceiling' in wm.select('batch', 'claude', path=p)['claude_cap']      # unreadable: default


def test_an_old_receipt_with_no_job_never_stops_the_ungraded_sweep(tmp_path):
    # 11-23: a pre-grading-gate receipt (no job field) for a judgment role raised KeyError 'job' in the nightly
    # sweep, so no later receipt was swept.
    (tmp_path / 'old_1103.log.selection.json').write_text(json.dumps(
        {'source': 'leaderboard', 'role': 'review', 'model': 'gpt-6.2-astra', 'selection_id': 'a' * 32}))
    (tmp_path / 'old_1103.log').write_text('MODEL_OUTCOME ' + json.dumps({'selection_id': 'a' * 32, 'finished': '2026-11-03T12:00:00+00:00'}) + '\n')
    assert wm.ungraded(tmp_path) == []


def test_claude_is_off_by_default_in_build_and_review_roles_unless_pinned(tmp_path, monkeypatch):
    # 11-23 (Ricardo via general): "We're already at 21%, and it's Monday... run more on Codex and on Gemini".
    p = cap_setup(tmp_path, monkeypatch, 10, hours=160, history=[(2, 9.5), (0, 10)])
    data = json.loads(p.read_text())
    data['roles'].update({r: ['claude-opus-5-5'] for r in ('builder', 'mechanical', 'judge', 'taste')})
    data['routes'].update({m: {'cli': 'agy', 'canonical': 'google/' + m} for m in
                           ('gemini-4-neon-high', 'gemini-4-hydrogen-high')})
    p.write_text(json.dumps(data))
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '1')
    for role in ('builder', 'mechanical', 'batch', 'review', 'judge'):
        got = wm.select(role, 'claude', path=p, made_by='gpt-6.2-sol' if role in wm.INDEPENDENT else '')
        assert got['executor'] in ('codex', 'agy') and 'gemini first' in got['delegate'], (role, got)
        assert got['source'] == 'delegate', role
    got = wm.select('taste', 'claude', path=p)                       # Ricardo-facing writing keeps Claude
    assert got['executor'] == 'claude'
    got = wm.select('review', 'claude', path=p, made_by='gpt-6.2-sol', pin='sealed cross-lab referee')
    assert got['executor'] == 'claude' and got['model'] == 'claude-opus-5-5'
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'claude')            # nowhere to go: stays, and says so
    got = wm.select('builder', 'claude', path=p)
    assert got['executor'] == 'claude' and 'neither Codex nor Gemini is open' in got['delegate_skipped']
    monkeypatch.setenv('RH_LAUNCHER_EXECUTORS', 'codex,claude,agy')
    monkeypatch.setenv('RH_CLAUDE_DELEGATE_DEFAULT', '0')
    assert wm.select('builder', 'claude', path=p)['executor'] == 'claude'


def test_ahead_of_the_straight_line_budget_unpinned_claude_work_leaves(tmp_path, monkeypatch):
    # 11-23: 21% on Monday afternoon. 77% by the reset (80% ceiling, 3% kept back): 38 h in, the line is 17.4%.
    monkeypatch.setenv('RH_CLAUDE_BUDGET_LINE', '1')
    p = cap_setup(tmp_path, monkeypatch, 21, hours=130, history=[(2, 20.5), (0, 21)])
    got = wm.select('batch', 'claude', path=p)
    assert got['executor'] == 'codex' and 'budget line: 21% used, the line is at 17.4%' in got['claude_cap']
    assert '77% by the reset' in got['claude_cap']
    got = wm.select('batch', 'claude', path=p, pin='sealed referee')
    assert got['executor'] == 'claude' and 'pinned, so it stays' in got['claude_cap']
    p = cap_setup(tmp_path, monkeypatch, 15, hours=130, history=[(2, 14.5), (0, 15)])
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'      # under the line
    monkeypatch.setenv('RH_CLAUDE_KEEP_BACK_PERCENT', '30')                  # 50% by the reset: 11.3% now
    assert wm.select('batch', 'claude', path=p)['executor'] == 'codex'
    monkeypatch.setenv('RH_CLAUDE_BUDGET_LINE', '0')
    assert wm.select('batch', 'claude', path=p)['executor'] == 'claude'


def test_the_daily_line_gives_each_session_and_lane_its_claude_share(tmp_path, monkeypatch):
    import time
    p = cap_setup(tmp_path, monkeypatch, 20, hours=130)
    proj = tmp_path / 'projects'
    lanes = tmp_path / 'lanes'
    for lane in ('bio', 'adaptyv-c4'):
        (lanes / lane).mkdir(parents=True)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    for name, tokens in (('-Users-x--worktrees-notes-kb-general', 2500), ('-Users-x--worktrees-notes-kb-claude-adaptyv-c4-v2', 1500),
                         ('-Users-x--local-state-bio-jobs-hunt-h2-ref', 500), ('-Users-x--local-state-bio-jobs-hunt-h3-ref', 500)):
        (proj / name).mkdir(parents=True)
        (proj / name / 's.jsonl').write_text(json.dumps({'timestamp': stamp, 'uuid': name, 'message': {
            'id': name, 'model': 'claude-sonnet-5-5', 'usage': {'input_tokens': tokens}}}) + '\n')
    text = wm.claude_cap.lanes_text(wm._allowance(), projects=proj, lanes_root=lanes)
    assert text.startswith('Claude this week: 20% of the weekly limit, the budget line is at ')
    assert 'general 10.0%, adaptyv-c4 6.0%, bio 4.0%' in text, text
    assert 'ahead of it' in text


def test_work_leaving_claude_goes_to_codex_first_whatever_the_codex_week(tmp_path, monkeypatch):
    # 11-24 (general): no Codex usage gate and no "tight" mode; Codex is first while the credits last.
    p = cap_setup(tmp_path, monkeypatch, 80)
    data = json.loads(p.read_text())
    data['routes']['gemini-4-hydrogen-high'] = {'cli': 'agy', 'canonical': 'google/gemini-4-hydrogen-high'}
    p.write_text(json.dumps(data))
    got = wm.select('batch', 'claude', path=p)                         # past the Claude ceiling
    assert (got['executor'], got['model']) == ('codex', 'gpt-6.2-sol'), got


def test_a_trial_of_one_model_still_runs_when_the_jobs_pick_is_another(tmp_path, monkeypatch):
    # 11-23 (general): the neon-1123 trial's third arm left Claude, so every arm is Neon-high.
    p = cap_setup(tmp_path, monkeypatch, 10, hours=160, history=[(2, 9.5), (0, 10)])
    data = json.loads(p.read_text())
    data['roles']['builder'] = ['claude-opus-5-5']
    data['routes']['gemini-4-neon-high'] = {'cli': 'agy', 'canonical': 'google/gemini-4-neon-high'}
    p.write_text(json.dumps(data))
    (tmp_path / 'trial.json').write_text(json.dumps({'name': 't1', 'roles': ['builder'], 'n': 3,
                                                     'models': ['gemini-4-neon-high'] * 3}))
    monkeypatch.setenv('RH_MODEL_TRIAL', str(tmp_path / 'trial.json'))
    monkeypatch.setenv('RH_MODEL_TRIAL_LEDGER', str(tmp_path / 'trial.jsonl'))
    got = wm.select('builder', 'claude', path=p, job='j1')
    assert got['model'] == 'gemini-4-neon-high' and got['trial'] == 't1' and 'model trial t1' in got['delegate']
    data['roles']['builder'] = ['gemini-4-neon-high']                  # the job's own pick: nothing to compare
    p.write_text(json.dumps(data))
    assert 'trial' not in wm.select('builder', 'agy', path=p, job='j2')
