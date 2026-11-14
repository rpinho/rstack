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


@pytest.mark.parametrize('model', ['sonnet', 'haiku', 'claude-sonnet-5-5'])
@pytest.mark.parametrize('field', ['description', 'prompt'])
def test_cheap_agent_judgment_in_any_sentence_is_blocked(model, field):
    payload = {'model': model, 'description': 'Read the claim', 'prompt': 'Read the files.'}
    payload[field] = 'Read the files. Then referee the claim.'
    result = blocked(HOOK, {'tool_name': 'Agent', 'tool_input': payload})
    assert result['code'] == 2
    assert 'name the leaderboard role, not a model (LEADERBOARD.md).' in result['stderr']
    assert 'use launch.sh --role review --made-by MODEL' in result['stderr']


@pytest.mark.parametrize('prompt', ['extract the table', 'format the table', 'summarize the text'])
@pytest.mark.parametrize('model', ['sonnet', 'haiku'])
def test_cheap_agent_without_judgment_passes(model, prompt):
    allowed(HOOK, {'tool_name': 'Agent', 'tool_input': {'model': model, 'prompt': prompt}})


def test_other_agent_models_are_unaffected():
    for model in ('opus', ''):
        allowed(HOOK, {'tool_name': 'Agent', 'tool_input': {'model': model, 'prompt': 'referee the claim'}})


@pytest.mark.parametrize('command', [
    'claude -p --model claude-sonnet-5-5 "review this proof"',
    'claude -p -m haiku "referee the claim"',
    'claude -p --model=sonnet "Read first. Then audit the result."',
    'claude -p -mhaiku "design the next step"',
    'cd /tmp && env X=1 /opt/bin/claude -p --model sonnet "judge the proof"',
    'codex exec -m gpt-6-astra "review this proof"',
    'codex exec --model gpt-6.1-sol "referee the claim"',
    'codex exec --model=gpt-6-astra "audit the result"',
    'codex exec -mgpt-6-astra "taste the design"',
    'echo "review this proof" | codex exec -m gpt-6-astra -',
])
def test_direct_judgment_cli_pins_are_blocked(command):
    result = blocked(HOOK, bash(command))
    assert result['code'] == 2
    assert 'use launch.sh --role review --made-by MODEL' in result['stderr']


@pytest.mark.parametrize('command', [
    'claude -p --model sonnet "extract the table"',
    'claude -p --model haiku "summarize the text"',
    'codex exec -m gpt-6-astra "format the table"',
    'claude -p --model opus "review the proof"',
    'codex exec "review the proof"',
    'echo \'claude -p --model sonnet "review the proof"\'',
    'echo \'codex exec -m gpt-6-astra "review the proof"\'',
    'python3 score.py --model sonnet --review',
    'claude -p -- "review --model sonnet"',
])
def test_unrelated_cli_work_passes(command):
    allowed(HOOK, bash(command))


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
                    '{"tool_name":"Agent",',
                    {'tool_name': 'Agent', 'tool_input': {'model': 'sonnet', 'prompt': []}},
                    bash('claude -p --model sonnet "unterminated'),
                    bash('codex exec -m gpt-6-astra "unterminated'),
                    bash('tell-general fyi "unterminated')):
        blocked(HOOK, payload)
    loud(HOOK, 'not json')
    loud(HOOK, {'tool_name': 'Bash', 'tool_input': []})
    allowed(HOOK, {'tool_name': 'Read', 'tool_input': {}})
