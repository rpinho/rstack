"""Instruction guard follows the neighbouring hooks' guarded/broken/innocent contract."""
import pytest

from rstack_hookcall import TOOLS, allowed, bash, blocked, loud

HOOK = TOOLS / 'model-instruction-gate'


def message(text):
    return {'tool_name': 'SendMessage', 'tool_input': {'message': text}}


def test_judgment_messages():
    result = blocked(HOOK, message('use Sonnet referees for the next round'))
    assert result['code'] == 2
    assert 'name the leaderboard role, not a model (LEADERBOARD.md).' in result['stderr']
    allowed(HOOK, message('use the review role for referees'))
    allowed(HOOK, message('Sonnet is cheaper'))
    allowed(HOOK, message('Sonnet is cheaper. Use the review role for referees.'))
    allowed(HOOK, message('Sonnet version 5. Use the review role for referees.'))
    blocked(HOOK, message('use Sonnet\nreferees for the next round'))
    allowed(HOOK, message('Review the solar design.'))  # word boundaries


@pytest.mark.parametrize('name', ['HAIKU', 'Opus', 'Fable', 'Astra', 'Sol', 'gpt-6.1-sol',
                                  'claude-fable-5.2', 'deepseek', 'kimi', 'glm'])
def test_all_model_names_block_in_judgment_sentences(name):
    blocked(HOOK, message('Use {} for review'.format(name)))


def test_tell_general_only_checks_outgoing_commands():
    blocked(HOOK, bash('tell-general fyi "use Sonnet referees for the next round"'))
    blocked(HOOK, bash('cd /tmp && env X=1 /opt/bin/tell-general fyi "Astra for audit"'))
    allowed(HOOK, bash('tell-general fyi "use the review role for referees"'))
    allowed(HOOK, bash('echo "tell-general fyi use Sonnet referees"'))
    allowed(HOOK, bash('echo "Sonnet review"; tell-general fyi "no change"'))
    allowed(HOOK, bash('python3 score.py --model sonnet --review'))


@pytest.mark.parametrize('tool,key', [('Write', 'content'), ('Edit', 'new_string')])
def test_lane_briefs(tool, key):
    payload = {'tool_name': tool, 'tool_input': {'file_path': '/work/lane-briefs/round.md',
                                              key: 'Use Sonnet referees'}}
    blocked(HOOK, payload)
    payload['tool_input'][key] = 'Use the review role for referees'
    allowed(HOOK, payload)
    payload['tool_input'][key] = 'Use Sonnet referees'
    payload['tool_input']['file_path'] = '/work/notes/round.md'
    allowed(HOOK, payload)


def test_guarded_broken_inputs_refuse_and_unrelated_errors_are_loud():
    for payload in ('{"tool_name":"SendMessage",',
                    {'tool_name': 'SendMessage', 'tool_input': 'use Sonnet referees'},
                    message(['Sonnet review']),
                    {'tool_name': 'Write', 'tool_input': {'file_path': '/lane-briefs/x', 'content': []}},
                    bash('tell-general fyi "unterminated')):
        blocked(HOOK, payload)
    loud(HOOK, 'not json')
    loud(HOOK, {'tool_name': 'Bash', 'tool_input': []})
    allowed(HOOK, {'tool_name': 'Read', 'tool_input': {}})
