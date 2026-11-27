"""Exercise the two Claude hook contracts and Wispr's queue through their entry points."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def local_env(tmp_path):
    return dict(os.environ, HOME=str(tmp_path), RSTACK_STATE_DIR=str(tmp_path / 'rstack'),
                RSTACK_ATTENDED='1', RSTACK_UNATTENDED='0', WISPR_LOCAL='1',
                RH_GATES_REGISTRY=str(REPO / 'rstack/gates.json'))


def hook(name, event, env):
    result = subprocess.run([sys.executable, str(REPO / 'rstack/hooks' / name)], env=env,
                            input=json.dumps(event), text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout else {}


def checkout(env, items, total=10, *, summary='Click Place your order', include_cart=True):
    if include_cart:
        summary += '\nCheckout: ' + json.dumps({'items': items, 'total': total})
    event = {'hook_event_name': 'PreToolUse', 'tool_name': 'mcp__claude-in-chrome__computer',
             'tool_input': {'action': 'left_click', 'action_summary': summary}}
    return hook('purchase-approval-gate.py', event, env)


@pytest.fixture
def glue_approved(tmp_path, local_env):
    path = tmp_path / '.local/state/purchase-approvals.jsonl'
    path.parent.mkdir(parents=True)
    approvals = [
        {'utc': '2026-11-27T14:00:00Z', 'approved_by': 'Ricardo',
         'items': ['Glue', 'Cable', 'Hub'], 'max_total': 100},
        {'utc': '2026-11-27T15:00:00Z', 'approved_by': 'Ricardo',
         'items': ['Glue'], 'max_total': 12},
    ]
    path.write_text(''.join(json.dumps(row) + '\n' for row in approvals))
    return local_env


def test_checkout_denies_unapproved_cable_and_hub(glue_approved):
    decision = checkout(glue_approved, ['Craft glue', 'USB-C cable', 'USB hub'])['hookSpecificOutput']
    assert decision['permissionDecision'] == 'deny'
    reason = decision['permissionDecisionReason']
    assert all(word in reason for word in ('USB-C cable', 'USB hub', 'remove', "Ricardo's approval"))


def test_checkout_allows_the_approved_cart(glue_approved):
    assert checkout(glue_approved, ['Craft GLUE'], 12) == {}


def test_checkout_without_an_approval_is_denied(local_env):
    decision = checkout(local_env, ['Glue'])['hookSpecificOutput']
    assert decision['permissionDecision'] == 'deny'
    assert "Ricardo's approval" in decision['permissionDecisionReason']


def test_checkout_with_missing_cart_details_or_over_cap_is_denied(glue_approved):
    for decision in (checkout(glue_approved, [], include_cart=False),
                     checkout(glue_approved, ['Glue'], 12.01)):
        assert decision['hookSpecificOutput']['permissionDecision'] == 'deny'
    event = {'tool_name': 'mcp__claude-in-chrome__browser_batch', 'tool_input': {'actions': [
        {'name': 'computer', 'input': {'action': 'left_click', 'target': 'Complete purchase'}},
    ]}}
    assert hook('purchase-approval-gate.py', event, glue_approved)['hookSpecificOutput'][
        'permissionDecision'] == 'deny'


def test_non_checkout_browser_click_is_untouched(local_env):
    assert checkout(local_env, [], summary='Click View cart', include_cart=False) == {}


def test_checkout_form_action_requires_the_latest_approval_even_if_older_one_matches(tmp_path, glue_approved):
    path = tmp_path / '.local/state/purchase-approvals.jsonl'
    with path.open('a') as stream:
        stream.write('incomplete approval record\n')
    event = {'tool_name': 'mcp__claude-in-chrome__form_submit', 'tool_input': {
        'target': 'Place order', 'action_summary': 'Submit form\nCheckout: {"items":["Glue"],"total":10}',
    }}
    decision = hook('purchase-approval-gate.py', event, glue_approved)['hookSpecificOutput']
    assert decision['permissionDecision'] == 'deny' and "Ricardo's approval" in decision['permissionDecisionReason']


@pytest.mark.parametrize(('message', 'warns'), [
    ('We never applied for the handle.', True),
    ('The application was not found in Gmail or the KB index.', False),
    ('We never applied based on what I found in Gmail and the KB index.', False),
    ('I can send you the application draft tomorrow.', False),
])
def test_absence_claims_warn_only_when_uncited(local_env, message, warns):
    event = {'hook_event_name': 'Stop', 'last_assistant_message': message}
    result = hook('absence-claim-check.py', event, local_env)
    if warns:
        assert 'searched' in result['systemMessage'] and 'not found in' in result['systemMessage']
        assert 'decision' not in result
    else:
        assert result == {}


def test_absence_claim_check_leaves_unattended_sessions_alone(local_env):
    event = {'hook_event_name': 'Stop', 'last_assistant_message': 'We never applied.'}
    assert hook('absence-claim-check.py', event, dict(local_env, RSTACK_UNATTENDED='1')) == {}


def test_wispr_rejects_options_before_queuing_any_word(tmp_path, local_env):
    state = tmp_path / '.local/state/wispr'
    state.mkdir(parents=True)
    tool = str(REPO / 'rstack/tools/wispr-add')
    for args in (['--help'], ['Glue', '-debug'], ['--list', 'Extra']):
        done = subprocess.run([tool, *args], env=local_env, capture_output=True, text=True, timeout=10)
        assert done.returncode != 0 and 'usage:' in done.stderr.lower()
        assert not (state / 'queue.txt').exists()
    subprocess.run([tool, 'Glue'], env=local_env, check=True, capture_output=True, timeout=10)
    listed = subprocess.check_output([tool, '--list'], env=local_env, text=True, timeout=10)
    assert (state / 'queue.txt').read_text() == 'Glue\n'
    assert 'Glue' in listed
