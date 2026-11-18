"""Owner asks: each mechanical pattern, exceptions and the real question hook."""
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ask_lint import HIS_ONLY, lint, lint_review_item
from rstack_hookcall import HOOKS, allowed, blocked


@pytest.mark.parametrize('text', [
    'upload the PDF at the AAS link',
    'paste this into the form',
    'click the submit button',
    'press Enter',
    'fill in the form',
    'fill out the form',
    'copy this text to the portal',
    'copy the reply into the form',
    'type your address',
    'attach the revised PDF',
    'run this command: brew install x',
    'run `brew install x`',
    'open the portal and do the upload',
    'submit at the AAS link',
    'enter the code',
    'follow the link to the form',
])
def test_mechanical_patterns(text):
    assert lint(text)[0] == 'do it yourself: ' + text


@pytest.mark.parametrize('prefix', [
    '', 'Please ', 'Ricardo, ', 'Can you ', 'Could you please ',
    'You need to ', 'You have to ', 'You should ', 'You must ',
    "You'll ", 'I need you to ', 'Action for Ricardo: ', '- [ ] ', '1. ',
])
def test_owner_address(prefix):
    assert lint(prefix + 'upload the PDF') == ['do it yourself: upload the PDF']


@pytest.mark.parametrize('text', [
    'read and OK the reply', 'sign in to GitLab', 'log in to the portal',
    'approve the $20 purchase', 'decide whether to publish', 'pay the invoice',
    'Please approve the reply', 'I will upload the PDF', 'I uploaded the PDF',
    'The upload failed', 'Do not click the link', "Don't paste your password",
    'Uploaded the revised PDF', 'The run finished', 'The type is optional',
    'I will read and upload the PDF', 'We will open the form, then paste the text',
])
def test_his_only_verbs_and_non_requests(text):
    assert lint(text) == []


@pytest.mark.parametrize('tag', HIS_ONLY)
def test_explicit_his_only_reasons(tag):
    assert lint('upload the PDF', tag) == []
    assert lint('[his-only: ' + tag + '] upload the PDF') == []
    assert lint('upload the PDF [his-only: ' + tag + ']') == []


def test_auth_tag_and_sign_in():
    assert lint('sign in to GitLab', 'auth') == []
    assert lint('sign in to GitLab [his-only: auth]') == []


@pytest.mark.parametrize('text', [
    'click the magic link to log in', 'follow the login link',
    'open the sign-in link', 'click the link to sign in to GitLab',
    'click the authentication link', 'follow the magic-link',
])
def test_login_links_need_auth(text):
    assert lint(text)
    assert lint(text, 'judgment')
    assert lint(text, 'auth') == []
    assert lint(text + ' [his-only: auth]') == []


def test_his_only_verb_does_not_excuse_later_mechanics():
    assert lint('approve the reply, then upload the PDF') == ['do it yourself: upload the PDF']
    assert lint('sign in to GitLab and paste the key') == ['do it yourself: paste the key']
    assert lint('read and OK the reply. Paste this into the form') == [
        'do it yourself: Paste this into the form']
    assert lint('I will read, then you upload the PDF') == ['do it yourself: upload the PDF']


def test_multiple_mechanical_steps():
    messages = lint('upload the PDF; paste this into the form')
    assert messages == ['do it yourself: upload the PDF', 'do it yourself: paste this into the form']


def test_invalid_reasons_are_not_exceptions():
    with pytest.raises(ValueError, match='unknown his-only class'):
        lint('upload the PDF', 'routine')
    with pytest.raises(ValueError, match='unknown his-only class'):
        lint('upload the PDF [his-only: routine]')


def test_review_visible_fields_and_saved_reason():
    item = dict(title='Read the reply', note='upload the PDF',
                checks=[dict(label='paste this into the form')])
    assert len(lint_review_item(item)) == 2
    assert lint_review_item(dict(item, his_only='attest')) == []
    assert lint_review_item(item, 'attest') == []
    assert lint_review_item(dict(title='upload the PDF'))
    assert lint_review_item(dict(note='upload the PDF',
        checks=[dict(label='read and OK [his-only: judgment]')]))


def test_cli_stdin_flag_and_exit_code():
    script = HOOKS.parent / 'tools/ask_lint.py'
    run = lambda *args: subprocess.run([sys.executable, str(script), *args],
        input='upload the PDF', text=True, capture_output=True, timeout=10)
    result = run()
    assert result.returncode == 2 and result.stderr.strip() == 'do it yourself: upload the PDF'
    assert run('--his-only', 'attest').returncode == 0
    assert run('--his-only', 'routine').returncode == 2
    assert run('--', 'sign in to GitLab').returncode == 0


CONDUCTOR = {'CONDUCTOR_CWD_SUFFIX': '/src/conductor', 'TMUX': ''}


def question_event(text, **question):
    return dict(tool_name='AskUserQuestion', cwd='/home/u/src/conductor',
                tool_input=dict(questions=[dict(question=text, **question)]))


def test_conductor_cannot_delegate_mechanical_steps():
    result = blocked(HOOKS / 'lane-no-questions.py', question_event('upload the PDF'), env=CONDUCTOR)
    assert 'do it yourself: upload the PDF' in result['stdout']
    allowed(HOOKS / 'lane-no-questions.py', question_event('read and OK the reply'), env=CONDUCTOR)
    allowed(HOOKS / 'lane-no-questions.py', question_event('sign in to GitLab'), env=CONDUCTOR)
    allowed(HOOKS / 'lane-no-questions.py', question_event(
        'click the magic link to log in [his-only: auth]'), env=CONDUCTOR)


def test_question_options_are_also_owner_text():
    event = question_event('Choose the next action', options=[
        dict(label='Continue', description='paste this into the form')])
    result = blocked(HOOKS / 'lane-no-questions.py', event, env=CONDUCTOR)
    assert 'do it yourself: paste this into the form' in result['stdout']


def test_question_tag_covers_options_but_not_other_questions():
    event = question_event('Authenticate [his-only: auth]', options=[
        dict(label='Continue', description='click the magic link to log in')])
    allowed(HOOKS / 'lane-no-questions.py', event, env=CONDUCTOR)
    event['tool_input']['questions'].append(dict(question='upload the PDF'))
    blocked(HOOKS / 'lane-no-questions.py', event, env=CONDUCTOR)


def test_tagged_lane_question_still_obeys_conductor_rule():
    event = question_event('click the magic link to log in [his-only: auth]')
    event['cwd'] = '/src/lane'
    result = blocked(HOOKS / 'lane-no-questions.py', event, env=CONDUCTOR)
    assert 'only the conductor' in result['stdout']


def test_question_lint_errors_refuse():
    for bad in ('upload the PDF [his-only: routine]', None):
        blocked(HOOKS / 'lane-no-questions.py', question_event(bad), env=CONDUCTOR)
