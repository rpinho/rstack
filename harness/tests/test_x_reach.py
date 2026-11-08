"""Reach rules against isolated ledgers, local xlint, and a read-only replied fixture."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import outreach
import rh
from test_outreach import cli

@pytest.fixture(autouse=True)
def _legacy_one_post_quota(monkeypatch):
    """These tests were written for the original 1-per-day rule with no gap; the 3-per-day default is tested explicitly."""
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    monkeypatch.setenv('RH_X_MIN_GAP_MINUTES', '0')


@pytest.fixture(autouse=True)
def _before_the_reply_rules(monkeypatch):
    """These tests predate reply spacing and per-round reply approval (11-08) and post replies
    back to back under the standing approval; test_x_growth.py tests those rules' defaults."""
    defaults = outreach.x_defaults
    monkeypatch.setattr(outreach, 'x_defaults', lambda: dict(
        defaults(), x_reply_gap_minutes=0, x_reply_human_approval=False))


CLOCK = dt.datetime(2026, 11, 3, 19, 0, tzinfo=outreach.UTC)


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path / 'harness'
    for lane in ('a', 'b'):
        (root / 'lanes' / lane).mkdir(parents=True)
    replied = tmp_path / 'replied.json'
    replied.write_text('[]')
    monkeypatch.setattr(outreach, 'REPLIED', replied)
    monkeypatch.setattr(rh, 'now', lambda: CLOCK.isoformat())
    return root, replied


def draft(state, text='The table now has a checked bound.', channel='x_post', lane='a', **options):
    root, _ = state
    path = root / ('draft-' + str(len(list(root.glob('draft-*')))) + '.txt')
    path.write_text(text)
    args = ['draft', lane, '--to', '@scientist', '--channel', channel, '--purpose', 'Share a result', '--file', path]
    for key, value in options.items():
        for item in value if isinstance(value, list) else [value]:
            args.extend(['--' + key.replace('_', '-'), item])
    result = cli(root, *args)
    assert result[0] == 0, result
    return result[1].strip(), path


def history(state, ident='past', lane='b', text='An earlier result.', channel='x_post', age=1, status='sent', **extra):
    root, _ = state
    stamp = (CLOCK - dt.timedelta(hours=age)).isoformat()
    row = dict(id=ident, lane=lane, channel=channel, text=text, status=status,
               created=stamp, to_name='@another', to_key='@another', purpose='Historical test')
    if status == 'sent':
        row['sent'] = dict(utc=stamp, message_id='111', via='browser')
    elif status == 'approved':
        row['approval'] = dict(utc=stamp, sha256=hashlib.sha256(text.encode()).hexdigest(), quote=outreach.STANDING_APPROVAL)
    row.update(extra)
    rh.append(root / 'lanes' / lane / 'OUTREACH.jsonl', row)
    return row


def lint(state, ident, lane='a'):
    return cli(state[0], 'lint', lane, ident)


def approved(state, **kwargs):
    ident, path = draft(state, **kwargs)
    assert lint(state, ident, kwargs.get('lane', 'a'))[0] == 0
    assert cli(state[0], 'approve', kwargs.get('lane', 'a'), ident, '--quote', outreach.STANDING_APPROVAL)[0] == 0
    return ident, path


def test_original_pass_and_media_warning(state):
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 0 and 'PASS' in out and 'WARN: media recommended' in out


def test_media_suppresses_warning_and_records_path(state):
    media = state[0] / 'figure.png'
    media.write_bytes(b'local fixture')
    ident, _ = draft(state, media=media)
    result = lint(state, ident)
    assert result[0] == 0 and 'media recommended' not in result[1]
    assert outreach.current(state[0] / 'lanes/a', rh)[ident]['media'] == [str(media)]


def test_missing_media_fails(state):
    ident, _ = draft(state, media=state[0] / 'missing.png')
    assert 'media file missing' in lint(state, ident)[1]


@pytest.mark.parametrize('status', ['sent', 'approved'])
def test_one_original_per_utc_day_cross_lane(state, status, monkeypatch):
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    history(state, status=status, age=3)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'x_post daily limit (1 per UTC day' in out and 'b/past' in out


def test_default_allows_three_originals_spaced_out(state, monkeypatch):
    monkeypatch.delenv('RH_X_ORIGINALS_PER_DAY', raising=False)
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='p1', age=3)
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 0
    history(state, ident='p2', age=5)
    history(state, ident='p3', age=7)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'x_post daily limit (3 per UTC day' in out


def test_originals_need_a_gap(state, monkeypatch):
    monkeypatch.delenv('RH_X_ORIGINALS_PER_DAY', raising=False)
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='recent', age=1)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'within 120 min of another original' in out


def test_original_yesterday_does_not_consume_today(state):
    history(state, age=20)
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 0


def test_utc_offset_converted_before_day_limit(state):
    row = history(state, age=1)
    row['sent']['utc'] = '2026-11-02T23:30:00-05:00'
    rh.append(state[0] / 'lanes/b/OUTREACH.jsonl', row)
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 1


def test_daily_reservation_is_atomic_at_approval(state):
    a, _ = draft(state)
    b, _ = draft(state, text='A distinct result about a different experiment.', lane='b')
    assert lint(state, a)[0] == lint(state, b, 'b')[0] == 0
    assert cli(state[0], 'approve', 'a', a, '--quote', outreach.STANDING_APPROVAL)[0] == 0
    assert cli(state[0], 'approve', 'b', b, '--quote', outreach.STANDING_APPROVAL)[0] == 2


def test_parallel_approvals_across_lanes_use_root_lock(state):
    root, _ = state
    a, _ = draft(state)
    b, _ = draft(state, text='A distinct result about a different experiment.', lane='b')
    assert lint(state, a)[0] == lint(state, b, 'b')[0] == 0
    def run(lane, ident):
        return subprocess.run([sys.executable, str(Path(rh.__file__)), '--root', str(root), 'outreach',
                               'approve', lane, ident, '--quote', outreach.STANDING_APPROVAL], capture_output=True, text=True).returncode
    # Use current real time for subprocess checks: both linted fixtures have no sent history.
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(run, 'a', a), pool.submit(run, 'b', b)]
        assert sorted(j.result(timeout=10) for j in jobs) == [0, 2]


def test_daily_limit_rechecked_when_recording_sent(state):
    ident, _ = approved(state)
    history(state)
    result = cli(state[0], 'sent', 'a', ident, '--message-id', '123', '--via', 'browser')
    assert result[0] == 2 and 'x_post daily limit' in result[2]


def test_batch_multiple_originals_fails(state):
    draft(state, batch='roundup')
    draft(state, text='A second distinct result.', batch='roundup')
    assert cli(state[0], 'lint', 'a', '--batch', 'roundup')[0] == 1


@pytest.mark.parametrize('url', ['https://example.org/paper', 'http://github.com/a', 'github.com/a', 'www.example.org/a',
                                'https://x.com.evil.test/a', 'https://x.com@evil.test/a', 'ftp://example.org/a', 'https://t.co/123'])
def test_external_links_fail_main_post(state, url):
    ident, _ = draft(state, text='The result is here. ' + url)
    result = lint(state, ident)
    assert result[0] == 1 and 'external URL' in result[1]


@pytest.mark.parametrize('url', ['https://x.com/alice/status/123', 'x.com/alice/status/123'])
def test_x_com_link_allowed(state, url):
    ident, _ = draft(state, text='The result is here. ' + url)
    assert lint(state, ident)[0] == 0


def test_link_self_reply_lints_separately_and_is_not_daily_original(state):
    history(state)
    ident, _ = draft(state, text='The certificate: https://github.com/example/result', self_reply_to='111')
    result = lint(state, ident)
    assert result[0] == 0 and 'media recommended' not in result[1]
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 0


@pytest.mark.parametrize('text', ['Which landmark would you measure?', 'I am checking the map. Which landmark would you measure?',
                                'How does the map change? The diagram is small.'])
def test_question_addressed_to_nobody_fails(state, text):
    ident, _ = draft(state, text=text)
    result = lint(state, ident)
    assert result[0] == 1 and 'question addressed to nobody' in result[1]


def test_expert_question_as_reply_passes(state):
    ident, _ = draft(state, text='Which landmark would you measure?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert lint(state, ident)[0] == 0


def test_named_question_passes_with_credit_warning(state):
    ident, _ = draft(state, text='Which landmark would @anna measure?')
    result = lint(state, ident)
    assert result[0] == 0 and 'tagging for reach' in result[1]


def test_statement_with_short_question_is_not_mainly_question(state):
    ident, _ = draft(state, text='The table lists every verified certificate from this week. Each bound includes its assumptions and source file. Other cases?')
    assert lint(state, ident)[0] == 0


@pytest.mark.parametrize('topic,meta', [('C44', {}), ('a project', {'projects': ['project-alpha']})])
def test_fifth_same_topic_in_48h_fails(state, topic, meta):
    for i in range(4):
        history(state, ident=str(i), text='Earlier ' + topic + '.', age=20 + i, **meta)
    options = {'project': 'project-alpha'} if meta else {}
    ident, _ = draft(state, text='The ' + topic + ' bound changed.', **options)
    result = lint(state, ident)
    assert result[0] == 1 and 'five or more' in result[1] and 'roundup' in result[1]


def test_four_topics_pass_and_old_topics_ignored(state):
    for i in range(3):
        history(state, ident=str(i), text='C44 changed.', age=24 + i)
    history(state, ident='old', text='C44 changed.', age=49)
    ident, _ = draft(state, text='C44 now has another certificate.')
    assert lint(state, ident)[0] == 0


def test_different_constants_are_different_topics(state):
    for i in range(4):
        history(state, ident=str(i), text='C45 changed.', age=24 + i)
    ident, _ = draft(state, text='C44 now has another certificate.')
    assert lint(state, ident)[0] == 0


def test_reply_requires_post_url(state):
    ident, _ = draft(state, channel='x_reply')
    result = lint(state, ident)
    assert result[0] == 1 and 'requires --in-reply-to URL' in result[1]


def test_xlint_reply_specific_fail_and_pass(state):
    ident, _ = draft(state, text='a' * 241, channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert 'reply longer' in lint(state, ident)[1]
    ident, _ = draft(state, text='which landmark would you measure?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert lint(state, ident)[0] == 0


def test_near_duplicate_reply_across_lanes_in_14_days(state):
    history(state, channel='x_reply', text='Which landmark would you measure?', age=24 * 13, in_reply_to='https://x.com/bob/status/222')
    ident, _ = draft(state, text='Which landmark would you measure first?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    result = lint(state, ident)
    assert result[0] == 1 and 'near-duplicate reply b/past' in result[1]


def test_old_reply_does_not_trigger_sameness(state):
    history(state, channel='x_reply', text='Which landmark would you measure?', age=24 * 15, in_reply_to='https://x.com/bob/status/222')
    ident, _ = draft(state, text='Which landmark would you measure?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert lint(state, ident)[0] == 0


def test_distinct_reply_to_same_person_on_another_post_allowed(state):
    history(state, channel='x_reply', text='Which landmark would you measure?', age=1, to_name='@scientist', to_key='@scientist', in_reply_to='https://x.com/scientist/status/222')
    ident, _ = draft(state, text='The error bars shrink when the window grows.', channel='x_reply', in_reply_to='https://x.com/scientist/status/123')
    assert lint(state, ident)[0] == 0


@pytest.mark.parametrize('existing', [['123'], {'123': {'utc': '2026-01-01'}}])
def test_never_reply_twice_replied_json_is_read_only(state, existing):
    _, replied = state
    replied.write_text(json.dumps(existing))
    before = replied.read_bytes()
    ident, _ = draft(state, text='Which landmark?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    result = lint(state, ident)
    assert result[0] == 1 and 'already replied' in result[1]
    assert replied.read_bytes() == before


def test_duplicate_target_from_ledger_ignores_age_and_url_handle(state):
    history(state, channel='x_reply', age=24 * 30, in_reply_to='https://twitter.com/anna/status/123')
    ident, _ = draft(state, channel='x_reply', in_reply_to='https://x.com/othername/status/123?s=20')
    assert 'already replied or reserved reply' in lint(state, ident)[1]


def test_unreadable_replied_fails_closed(state):
    state[1].write_text('invalid')
    ident, _ = draft(state, channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert 'cannot read replied.json' in lint(state, ident)[1]


@pytest.mark.parametrize('options,warn', [({}, True), ({'credit': '@anna'}, False), ({'credit': '@bob'}, True)])
def test_real_credit_avoids_tagging_warning(state, options, warn):
    ident, _ = draft(state, text='The table uses @anna\'s method.', **options)
    result = lint(state, ident)
    assert result[0] == 0 and ('tagging for reach' in result[1]) == warn


def test_reply_to_mentioned_person_avoids_tagging_warning(state):
    ident, _ = draft(state, text='Does @anna have a staging control?', channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    assert 'tagging for reach' not in lint(state, ident)[1]


def test_reply_to_someone_else_still_warns(state):
    ident, _ = draft(state, text='Does @anna have a staging control?', channel='x_reply', in_reply_to='https://x.com/bob/status/123')
    assert 'tagging for reach' in lint(state, ident)[1]


def test_public_x_standing_approval_and_email_dm_exclusion(state, monkeypatch):
    ident, _ = approved(state, channel='x_reply', in_reply_to='https://x.com/anna/status/123')
    row = outreach.current(state[0] / 'lanes/a', rh)[ident]
    assert row['approval']['quote'] == 'standing-approval-10-30'
    monkeypatch.setattr(outreach, 'contact_key', lambda name: name)
    for channel in ('email', 'x_dm'):
        ident, _ = draft(state, text='A separate thought about the graph.', channel=channel)
        assert lint(state, ident)[0] == 0
        assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2
        assert cli(state[0], 'approve', 'a', ident, '--quote', 'Send this text')[0] == 0


def test_standing_does_not_bypass_failed_or_changed_lint(state):
    ident, _ = draft(state, text='A result at https://example.org.')
    assert lint(state, ident)[0] == 1
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2
    ident, path = draft(state)
    assert lint(state, ident)[0] == 0
    path.write_text('A changed result.')
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2

