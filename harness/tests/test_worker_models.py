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
    for role,executor in [('missing','codex'),('taste','codex'),('batch','claude')]:
        with pytest.raises(ValueError):wm.select(role,executor,path=p)
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


def run_launcher(fake_home,*extra,rc=0):
    home,c,work,env=fake_home
    env=dict(env,FAKE_RC=str(rc))
    launcher=Path(__file__).resolve().parents[2] / 'tools/launch.sh'
    return subprocess.run(['/bin/zsh',str(launcher),'fixture-job',str(work),*extra],
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
