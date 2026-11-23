"""Exercise the Claude Code hook protocol against real cap logic and a temporary usage ledger."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / 'rstack/hooks/claude-pace-gate.py'


@pytest.fixture
def env(tmp_path):
    return {'HOME': str(tmp_path), 'PATH': os.environ['PATH'], 'RSTACK_STATE_DIR': str(tmp_path / 'state'),
            'CONDUCTOR_CWD_SUFFIX': '/work/general', 'RH_CLAUDE_BUDGET_LINE': '0'}


def reading(env, percent, rate=0, age=30):
    now = time.time()
    usage = Path(env['RSTACK_STATE_DIR']) / 'usage'
    usage.mkdir(parents=True)
    (usage / 'claude.json').write_text(json.dumps(dict(at=now-age, weekly_percent=percent,
                                                      resets_at=now+20*3600)))
    rows = [dict(at=now-h*3600, weekly_percent=percent-h*rate) for h in (2, 0)]
    (usage / 'claude-history.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))


def spawn(env, model=None, *, cwd='/work/lane', tool='Agent', hook=HOOK):
    event = dict(tool_name=tool, tool_input={'model': model} if model is not None else {},
                 cwd=cwd, transcript_path=str(Path(env['HOME']) / 'transcript.jsonl'), session_id='fixture')
    result = subprocess.run([sys.executable, str(hook)], input=json.dumps(event), capture_output=True,
                            text=True, env=env, timeout=10, check=True)
    if not result.stdout:
        return {}, result.stderr
    output = json.loads(result.stdout)['hookSpecificOutput']
    assert output.pop('hookEventName') == 'PreToolUse'
    return output, result.stderr


def ledger(env):
    path = Path(env['RSTACK_STATE_DIR']) / 'harness-blocks.jsonl'
    return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize('percent', [12, 72])
def test_flat_usage_is_silent(env, percent):
    reading(env, percent)
    assert spawn(env) == ({}, '')
    assert ledger(env) == []


@pytest.mark.parametrize('model', [None, 'opus'])
def test_projected_over_ceiling_warns_opus(env, model):
    reading(env, 37, 2.5)  # 87% at reset
    out, _ = spawn(env, model)
    assert out == {'additionalContext': 'Claude is pacing: 37% now, 2.5%/h, 20 h to reset. '
                                         'Use model sonnet for mechanical work, or send build work to Codex.'}
    row, = ledger(env)
    assert (row['reason'], row['outcome'], row['lane']) == (out['additionalContext'], 'warn', 'lane')


@pytest.mark.parametrize('model', ['sonnet', 'haiku'])
def test_moderate_pacing_is_silent_for_explicit_non_opus(env, model):
    reading(env, 37, 2.5)
    assert spawn(env, model) == ({}, '')
    assert ledger(env) == []


@pytest.mark.parametrize('model', [None, 'opus', 'fable'])
def test_pace_off_denies_opus_with_fix(env, model):
    reading(env, 37, 3.3)  # 103% at reset
    out, _ = spawn(env, model)
    assert out['permissionDecision'] == 'deny'
    assert 'Use model sonnet or send it to Codex' in out['permissionDecisionReason']
    row, = ledger(env)
    assert row['outcome'] == 'block' and row['fix'] in out['permissionDecisionReason']


@pytest.mark.parametrize(('model', 'cwd'), [('sonnet', '/work/lane'), ('haiku', '/work/lane'),
                                            ('opus', '/work/general')])
def test_pace_off_allows_with_warning(env, model, cwd):
    reading(env, 37, 3.3)
    out, _ = spawn(env, model, cwd=cwd)
    assert set(out) == {'additionalContext'} and '3.3%/h' in out['additionalContext']
    row, = ledger(env)
    assert row['outcome'] == 'warn'


def test_moderate_pacing_warns_fable_like_opus(env):
    """Fable is priced above Opus (harness-m5 review, 11-20)."""
    reading(env, 37, 2.5)
    out, _ = spawn(env, 'fable')
    assert set(out) == {'additionalContext'} and 'pacing' in out['additionalContext']


@pytest.mark.parametrize('model', ['opus', 'sonnet', 'haiku', 'fable'])
def test_ceiling_applies_to_all_models_except_in_general(env, model):
    reading(env, 80)
    out, _ = spawn(env, model)
    assert out['permissionDecision'] == 'deny'
    assert 'send it to Codex: tools/launch.sh JOB WORKDIR with AGENT_BACKEND=codex' in out['permissionDecisionReason']
    assert spawn(env, model, cwd='/work/general') == ({}, '')
    row, = ledger(env)
    assert row['class'] == 'hard-line' and row['job'] == 'session:fixture'


@pytest.mark.parametrize('condition', ['missing', 'corrupt', 'stale'])
def test_unknown_usage_allows_and_logs_once(env, condition):
    if condition != 'missing':
        reading(env, 99, age=3*3600)
        if condition == 'corrupt':
            (Path(env['RSTACK_STATE_DIR']) / 'usage/claude.json').write_text('{invalid')
    out, _ = spawn(env)
    assert out == {}
    row, = ledger(env)
    assert (row['class'], row['outcome']) == ('fail-open', 'warn')
    assert 'usage' in row['reason']


def test_unrelated_tool_and_lane_share_do_not_deny(env):
    reading(env, 15)
    shares = Path(env['HOME']) / 'shares.json'
    shares.write_text(json.dumps({'lane': {'max_week_percent': 0}}))
    env['RSTACK_CLAUDE_SHARES'] = str(shares)
    assert spawn(env) == ({}, '')
    assert spawn(env, tool='Bash') == ({}, '')
    assert ledger(env) == []


def test_a_downgraded_limit_warns_and_allows(env):
    reading(env, 81)
    registry = json.loads((REPO / 'rstack/gates.json').read_text())
    limit = next(row for row in registry['gates'] if row['gate'] == 'claude-pace-gate.limit')
    limit['class'] = 'fail-open'
    path = Path(env['HOME']) / 'gates.json'
    path.write_text(json.dumps(registry))
    env['RH_GATES_REGISTRY'] = str(path)
    assert set(spawn(env)[0]) == {'additionalContext'}
    row, = ledger(env)
    assert row['outcome'] == 'warn'


def test_a_ledger_write_error_allows_at_the_ceiling(env):
    reading(env, 81)
    (Path(env['RSTACK_STATE_DIR']) / 'harness-blocks.jsonl').mkdir()
    out, err = spawn(env)
    assert 'permissionDecision' not in out
    assert 'could not write the ledger' in err


def test_installed_layout_and_policy_import_failure(env):
    home = Path(env['HOME'])
    hooks = home / '.claude/hooks'
    hooks.mkdir(parents=True)
    installed_hook = Path(shutil.copy(HOOK, hooks))
    shutil.copy(HOOK.with_name('_hookfail.py'), hooks)
    root = home / '.local/share/research-harness'
    (root / 'rstack/tools').mkdir(parents=True)
    shutil.copy(REPO / 'rstack/tools/allowance', root / 'rstack/tools')
    shutil.copy(REPO / 'rstack/gates.json', root / 'rstack')
    for name in ('harness_blocks.py', 'claude_cap.py'):
        shutil.copy(REPO / 'harness' / name, root)
    reading(env, 81)
    assert spawn(env, hook=installed_hook)[0]['permissionDecision'] == 'deny'
    (root / 'claude_cap.py').write_text('raise ImportError("broken fixture")\n')
    assert spawn(env, hook=installed_hook)[0] == {}
    block, warning = ledger(env)
    assert block['outcome'] == 'block'
    assert warning['outcome'] == 'warn' and 'ImportError' in warning['reason']


def test_ahead_of_the_budget_line_an_opus_agent_is_told_and_allowed(env):
    # 11-23: 72% with 20 h to the reset is ahead of the straight line to 77% (67.8%). A warning, never a deny.
    env['RH_CLAUDE_BUDGET_LINE'] = '1'
    reading(env, 72)
    out, _ = spawn(env, 'opus')
    assert 'budget line: 72% used' in out['additionalContext'] and 'permissionDecision' not in out
    assert spawn(env, 'sonnet') == ({}, '')
