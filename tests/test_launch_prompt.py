"""The launcher's word cap counts the ask, and every job's prompt carries the shared context.

Before 11-06 the repo launcher had no cap at all, although AGENTS.md's hard rule says it
enforces one, and no job prompt carried the rules, the lane goal or the lane's lessons: prior
art was enforced only on the `rh ideas promote` path and lessons reached only sweep prompts.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import date, timedelta

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / 'tools/launch.sh'
ASK = 'Find a better bound for C44 than the printed one, or say plainly that you did not.'


@pytest.mark.parametrize('state', ['retired', 'ended', 'held'])
@pytest.mark.parametrize('job_lane,explicit', [('closedb', ''), ('long-lane', ''), ('other', 'closedb')])
def test_inactive_registry_refuses_before_host_checks_registration_or_executor(tmp_path, state, job_lane, explicit):
    row = {'status': 'active' if state == 'ended' else state, 'why': 'challenge finished',
           'sessions': ['closedb']}
    if state == 'ended':
        row['end'] = str(date.today() - timedelta(days=1))
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'lanes': {'long-lane': row}}))
    proc, prompt = run(tmp_path, ASK, lane=job_lane,
                       env={'RH_LANE_REGISTRY': str(path), 'LAUNCH_LANE': explicit,
                            'LAUNCH_HOST': 'unreachable', 'LAUNCH_RESUME': '1'})
    assert proc.returncode == 78, proc.stderr
    assert 'long-lane: ' + state in proc.stderr and 'challenge finished' in proc.stderr
    assert not prompt and not (tmp_path / 'registry').exists()


def test_active_registry_runs_and_default_registry_uses_lanes_root(tmp_path):
    jobs, env = harness(tmp_path, ASK)
    (Path(env['LAUNCH_LANE_ROOT']) / 'lanes/REGISTRY.json').write_text(
        json.dumps({'lanes': {'fixture': {'status': 'active', 'end': str(date.today())}}}))
    proc = subprocess.run(['zsh', str(LAUNCH), 'fixture-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_invalid_registry_refuses_launch(tmp_path):
    path = tmp_path / 'registry.json'
    path.write_text('{')
    proc, prompt = run(tmp_path, ASK, env={'RH_LANE_REGISTRY': str(path)})
    # RULE #1 (11-20): a broken registry is the harness's error; the job runs under its own lane name.
    assert proc.returncode == 0 and 'lane registry unreadable' in proc.stderr and prompt


def harness(tmp_path, spec_text, lane='fixture', goal=None, lessons=None):
    """A launcher environment whose agent CLI is a stub: no model, no network, no spend."""
    jobs = tmp_path / 'jobs'
    jobs.mkdir(exist_ok=True)
    (jobs / (lane + '-job.md')).write_text(spec_text)
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={'batch': ['fixture-claude']}, routes={
        'fixture-claude': {'canonical': 'fixture-claude', 'cli': 'claude'}})))
    fake = tmp_path / 'fake-cli'
    # The claude path parses the provider's result JSON, so the stub returns a success result.
    fake.write_text('#!' + sys.executable + '\nimport sys\n'
                    'print(\'{"is_error":false,"subtype":"success","result":"fixture"}\')\n'
                    'sys.exit(0)\n')
    fake.chmod(0o755)
    root = tmp_path / 'runtime'
    (root / 'lanes' / lane).mkdir(parents=True, exist_ok=True)
    if goal is not None:
        (root / 'lanes' / lane / 'GOAL.md').write_text(goal)
    env = dict(os.environ, AGENT_BACKEND='claude', LAUNCH_CLAUDE=str(fake),
               LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
               RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1', LAUNCH_LANE_ROOT=str(root))
    env.pop('LAUNCH_RESUME', None)
    env.pop('SPEC_OVER_CAP', None)
    return jobs, env


def run(tmp_path, spec_text, lane='fixture', **kw):
    extra = kw.pop('env', {})
    jobs, env = harness(tmp_path, spec_text, lane=lane, **kw)
    env.update(extra)
    proc = subprocess.run(['zsh', str(LAUNCH), lane + '-job', str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=60)
    prompt = jobs / (lane + '-job.log.prompt')
    return proc, (prompt.read_text() if prompt.exists() else '')


def generated(ask=ASK, policy_words=2000):
    """Shaped like a sweep-generated spec: a small ask wrapped in injected lane policy."""
    return '\n'.join([ask, '',
                      '--- BEGIN VERBATIM LANE POLICY: /x/lanes/c5/RULES.md ---',
                      ' '.join(['rule'] * policy_words),
                      '--- END VERBATIM LANE POLICY ---'])


def test_a_sweep_generated_spec_is_not_refused_for_its_injected_policy(tmp_path):
    """The 11-06 failure: c5's 472-word ask counted as 3,047 words and every generated job
    was refused "spec over 1,000 words".
    """
    proc, prompt = run(tmp_path, generated())
    assert proc.returncode == 0, proc.stderr
    assert ASK in prompt


def test_a_genuinely_long_ask_is_warned_and_runs(tmp_path):
    proc, _ = run(tmp_path, ' '.join(['ceremony'] * 1200))
    assert proc.returncode == 0 and '[launch.spec-word-cap] WARNING' in proc.stderr   # RULE #1
    assert 'over the 1000 cap' in proc.stderr and 'job-specific words' in proc.stderr


def test_an_over_cap_spec_runs_with_a_recorded_reason(tmp_path):
    proc, _ = run(tmp_path, ' '.join(['ceremony'] * 1200),
                  env={'SPEC_OVER_CAP': 'porting a frozen protocol verbatim'})
    assert proc.returncode == 0, proc.stderr
    log = (tmp_path / 'jobs/fixture-job.log').read_text()
    assert 'spec over cap allowed' in log and 'porting a frozen protocol' in log


def test_every_prompt_carries_the_rules_the_goal_and_the_lanes_lessons(tmp_path):
    proc, prompt = run(tmp_path, ASK, goal='Beat the printed constant. Nothing else counts.')
    assert proc.returncode == 0, proc.stderr
    assert 'Begin with prior art' in prompt, 'the rules, so prior art reaches every job'
    assert "Before relaunching, count this job's processes with `pgrep -f JOBNAME | wc -l` only" in prompt
    assert '[launch.spec-process-listing]' not in prompt
    assert 'Beat the printed constant' in prompt and "owner's words" in prompt
    assert prompt.index('Begin with prior art') < prompt.index(ASK), 'shared context comes first'


def test_a_missing_goal_or_lessons_does_not_stop_the_job(tmp_path):
    """A lane with no GOAL.md still runs: the gap shows as absence, not as a dead lane."""
    proc, prompt = run(tmp_path, ASK, goal=None)
    assert proc.returncode == 0, proc.stderr
    assert ASK in prompt and 'LANE GOAL' not in prompt


def test_the_shared_blocks_are_not_counted_against_the_cap(tmp_path):
    """The rules file alone is ~270 words; injecting it must not eat the ask's budget."""
    near = ' '.join(['word'] * 980)
    proc, prompt = run(tmp_path, near)
    assert proc.returncode == 0, proc.stderr
    assert len(prompt.split()) > 1100, 'the prompt is over the cap once shared blocks are added'
