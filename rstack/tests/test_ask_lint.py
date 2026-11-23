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
    'use the magic link',
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
    assert lint(prefix + 'open the login link', 'auth') == [
        'do it yourself: open the login link']


@pytest.mark.parametrize('text', [
    'read and OK the reply', 'sign in to GitLab', 'log in to the portal',
    'sign in with your password to GitLab',
    'approve the $20 purchase', 'decide whether to publish', 'pay the invoice',
    'Please approve the reply', 'I will upload the PDF', 'I uploaded the PDF',
    'The upload failed', 'Do not click the link', "Don't paste your password",
    'Uploaded the revised PDF', 'The run finished', 'The type is optional',
    'I will read and upload the PDF', 'We will open the form, then paste the text',
    'I upload everything myself', 'upload everything myself', "I'll paste it",
    'The agent will open the form and upload everything',
    'Agent will read, then paste the text',
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
    'use the magic link', 'use your login link',
    'click the sign-in link in your email', 'open the login link',
])
def test_password_free_login_links_are_agent_work(text):
    assert lint(text) == ['do it yourself: ' + text]
    for tag in ('auth', 'judgment', 'money', 'delete', 'attest', 'first-email', 'terms'):
        assert lint(text, tag) == ['do it yourself: ' + text]
        assert lint(text + ' [his-only: ' + tag + ']') == ['do it yourself: ' + text]


@pytest.mark.parametrize('tag', ['password', '2fa', 'oauth', 'sso'])
@pytest.mark.parametrize('text', [
    'enter the 2FA code', 'type your password', 'approve the OAuth consent',
    'open the login link and enter your password',
])
def test_password_and_consent_stay_with_owner(text, tag):
    assert lint(text, tag) == []
    assert lint(text + ' [his-only: ' + tag + ']') == []


def test_his_only_verb_does_not_excuse_later_mechanics():
    assert lint('approve the reply, then upload the PDF') == ['do it yourself: upload the PDF']
    assert lint('sign in to GitLab and paste the key') == ['do it yourself: paste the key']
    assert lint('read and OK the reply. Paste this into the form') == [
        'do it yourself: Paste this into the form']
    assert lint('I will read, then you upload the PDF') == ['do it yourself: upload the PDF']
    assert lint('The agent will read, then you upload the PDF') == ['do it yourself: upload the PDF']


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
    for tag in ('password', '2fa', 'oauth', 'sso'):
        assert run('--his-only', tag, 'enter the 2FA code').returncode == 0
    assert run('--his-only', 'auth', 'click the magic link to log in').returncode == 2


CONDUCTOR = {'CONDUCTOR_CWD_SUFFIX': '/src/conductor', 'TMUX': ''}


def question_event(text, **question):
    return dict(tool_name='AskUserQuestion', cwd='/home/u/src/conductor',
                tool_input=dict(questions=[dict(question=text, **question)]))


def test_the_question_hook_no_longer_lints_the_conductors_asks():
    # 11-22 (general): it refused cards that were Ricardo's by rule. ask_lint still serves notify-ricardo and review-add.
    allowed(HOOKS / 'lane-no-questions.py', question_event('upload the PDF'), env=CONDUCTOR)
    allowed(HOOKS / 'lane-no-questions.py', question_event('Open the first GitHub issue in your name?'), env=CONDUCTOR)


def test_tagged_lane_question_still_obeys_conductor_rule():
    event = question_event('enter the 2FA code [his-only: password]')
    event['cwd'] = '/src/lane'
    result = blocked(HOOKS / 'lane-no-questions.py', event, env=CONDUCTOR)
    assert 'only the conductor' in result['stdout']


