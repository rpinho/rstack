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


def test_named_agent_assignment_uses_the_same_rule():
    blocked(HOOK, {'tool_name': 'Agent', 'tool_input': {'model': 'opus', 'prompt': 'referee the claim'}})
    allowed(HOOK, {'tool_name': 'Agent', 'tool_input': {'model': '', 'prompt': 'referee the claim'}})


@pytest.mark.parametrize('command', [
    'claude -p --model claude-sonnet-5-5 "review this proof"',
    'claude -p --model opus "review the proof"',
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
                    # 11-14: unbalanced quotes are read by the fallback split, not refused outright
                    bash('claude -p --model sonnet "review unterminated'),
                    bash('codex exec -m gpt-6-astra "audit unterminated'),
                    bash('tell-general fyi "use Sonnet referees unterminated')):
        blocked(HOOK, payload)
    loud(HOOK, 'not json')
    loud(HOOK, {'tool_name': 'Bash', 'tool_input': []})
    allowed(HOOK, {'tool_name': 'Read', 'tool_input': {}})


def test_a_heredoc_with_an_open_quote_is_checked_not_refused():
    """11-14: shlex raised on a heredoc holding an apostrophe, and the hook failed closed on ordinary Bash."""
    allowed(HOOK, bash("python3 - <<'EOF'\ns = '''it's fine'''\nEOF\nls ~/.claude/hooks"))
    blocked(HOOK, bash("cat <<EOF\nit's late\nEOF\nclaude -p --model claude-sonnet-5-5 'review this proof"))
    allowed(HOOK, bash('claude -p --model sonnet "extract the table unterminated'))


@pytest.mark.parametrize('text', [
    'Did the scoring jobs on gpt-6.2-astra, including the audits, exhaust our weekly allowance?',
    'The opus test report has been passed on to general; the review scores are in the handoff.',
    'Review plant batches caught: 2/2 for gpt-6.2-astra, 1/2 for opus. No role change proposed.',
    'gpt-6.2-astra audits used 403 calls yesterday; all scoring jobs have stopped.',
    'opus for review costs 120 credits per batch; gpt-6.2-astra used 30.',
    'Astra: audit report sent to general yesterday.',
    'opus: review 2/2, judge 3/3.\ngpt-6.2-astra: review 2/2, judge 2/3.',
    'Could we ask opus to judge the proof?',
    'Should gpt-6.2-astra review the claim?',
    'Do not use opus for review.',
    'Yesterday we asked opus to judge the claim.',
    'The report says "Use opus to review the claim" was the old instruction.',
    'Model | review plants | judge agreement\ngpt-6.2-astra | 2/2 | 3/3\nopus | 1/2 | 2/3',
])
@pytest.mark.parametrize('surface', ['message', 'tell-general', 'Write', 'Edit'])
def test_reports_questions_and_scores_pass(text, surface):
    import shlex
    if surface == 'message':
        event = message(text)
    elif surface == 'tell-general':
        event = bash('tell-general fyi ' + shlex.quote(text))
    else:
        event = {'tool_name': surface, 'tool_input': {
            'file_path': '/work/lane-briefs/status.md',
            'content' if surface == 'Write' else 'new_string': text}}
    allowed(HOOK, event)


@pytest.mark.parametrize('text', [
    'Have gpt-6.2-astra to review the patch.',
    'Let opus judge the claim.',
    'Use gpt-6.2-astra to referee the result.',
    'Ask opus to judge the proof.',
    'gpt-6.2-astra should review the change.',
    'Please use opus for the next audit.',
    'Models and budget:\n- **Opus** (you) for purpose analysis and review.\n- **Astra:** adversarial review of each proposal.',
    'Same bar as today: an Opus-confirmed referee pass before submission.',
])
def test_imperative_assignments_block(text):
    blocked(HOOK, message(text))


@pytest.mark.parametrize('command', [
    'tools/launch.sh lane_review_1117 /work --model gpt-6.2-astra',
    'tools/launch.sh lane /work --role review --model=opus',
    'runner run --model opus --role judge',
    'model=opus runner exec --role audit',
    'run --model opus "Review the results"',
    'runner exec --model=opus --job=lane_review_1117',
    'claude -p --model opus "Review the completed patch"',
    'echo "review unrelated"; codex exec -m gpt-6.2-astra "format the table"',
])
def test_command_assignment_scope(command):
    if command.startswith('echo'):
        allowed(HOOK, bash(command))
    else:
        blocked(HOOK, bash(command))


@pytest.mark.parametrize('prompt', [
    'Extract the table from this systematic review.',
    'Summarize the opus review scores and report the accounting.',
    'Did the gpt-6.2-astra audits exhaust the allowance?',
])
def test_agent_mentions_are_not_judgment_assignments(prompt):
    allowed(HOOK, {'tool_name': 'Agent', 'tool_input': {'model': 'sonnet', 'prompt': prompt}})


@pytest.mark.parametrize('command', [
    'tell-general --from harness fyi "Use opus to review the patch"',
    'tell-general fyi --from harness "Use opus to review the patch"',
])
def test_tell_general_flags_preserve_assignments(command):
    blocked(HOOK, bash(command))
