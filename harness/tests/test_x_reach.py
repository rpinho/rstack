"""Reach rules against isolated ledgers, local xlint, and a read-only replied fixture."""
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
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
    """11-27: no daily cap on originals; these tests run on the default 5-minute burst gap."""
    monkeypatch.delenv('RH_X_ORIGINALS_PER_DAY', raising=False)
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)


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


def test_a_fourth_original_in_one_utc_day_passes(state, monkeypatch):
    """11-27 Ricardo: "What daily limit? Why are we limiting ourselves? Just remove it." No daily cap, even when
    the old RH_X_ORIGINALS_PER_DAY is still set; only the few-minute burst gap applies."""
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    for n, age in enumerate((0.5, 1.0, 1.5)):
        history(state, ident='past{}'.format(n), text='Earlier result {}.'.format(n), age=age)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert 'daily limit' not in out and 'within' not in out, out


def test_originals_minutes_apart_still_refused_as_a_burst(state, monkeypatch):
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, age=2 / 60)   # two minutes ago, inside the 5-minute default
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'within 5 min of another original: b/past' in out


def test_an_old_unsent_approval_holds_no_slot(state, monkeypatch):
    """general, 11-17: x-post-ready re-approved four math originals each round, every image upload
    failed, and each approval held the 120-min gap and a daily slot, so no other original went out."""
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    for n, age in enumerate((0.6, 1, 1.5, 3)):
        history(state, ident='stuck%d' % n, status='approved', age=age)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 0, out
    # A fresh approval (under 30 min) is about to go out, so it still holds the burst gap.
    history(state, ident='fresh', status='approved', age=2 / 60)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'within 5 min of another original: b/fresh' in out and 'daily limit' not in out


def test_default_allows_many_originals_spaced_out(state, monkeypatch):
    monkeypatch.delenv('RH_X_ORIGINALS_PER_DAY', raising=False)
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='p1', age=3)
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 0
    history(state, ident='p2', age=5)
    history(state, ident='p3', age=7)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 0 and 'daily limit' not in out, out   # 11-27: no daily cap; a 4th original passes


def test_originals_need_a_gap(state, monkeypatch):
    monkeypatch.delenv('RH_X_ORIGINALS_PER_DAY', raising=False)
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='recent', age=3 / 60)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'within 5 min of another original' in out


@pytest.mark.parametrize('extra', [{}, {'gate_attempt': {'utc': (CLOCK - dt.timedelta(hours=1)).isoformat()}}])
def test_a_dropped_original_takes_no_slot(state, monkeypatch, extra):
    """general, 11-09: an original that failed on a media upload and one refused because the video was
    still processing were both dropped, yet the next original failed the 120-min gap against them."""
    monkeypatch.setenv('RH_X_ORIGINALS_PER_DAY', '1')
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='failed-upload', age=1, status='dropped', reason='media upload failed', **extra)
    history(state, ident='failed-video', age=1, status='dropped', reason='video still processing',
            gate_attempt={'utc': (CLOCK - dt.timedelta(minutes=30)).isoformat()})
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 0, out
    # An attempt that was not dropped still takes its slot: the hook cannot know it failed.
    history(state, ident='attempted', age=2 / 60, status='approved', gate_attempt={'utc': (CLOCK - dt.timedelta(minutes=2)).isoformat()})
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'attempted' in out


def test_original_yesterday_does_not_consume_today(state):
    history(state, age=20)
    ident, _ = draft(state)
    assert lint(state, ident)[0] == 0


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
    history(state, age=2 / 60)   # another original went out 2 minutes ago, after this one was approved
    result = cli(state[0], 'sent', 'a', ident, '--message-id', '123', '--via', 'browser')
    assert result[0] == 2 and 'within 5 min of another original' in result[2]


def test_batch_multiple_originals_fails(state):
    draft(state, batch='roundup')
    draft(state, text='A second distinct result.', batch='roundup')
    assert cli(state[0], 'lint', 'a', '--batch', 'roundup')[0] == 1


@pytest.mark.parametrize('url', ['https://example.org/paper', 'http://github.com/a', 'github.com/a', 'www.example.org/a',
                                'https://x.com.evil.test/a', 'ftp://example.org/a', 'https://t.co/123'])
def test_links_go_in_the_main_post(state, url):
    # 11-28 Ricardo: "That's a stupid rule. I hate that rule." Links go in the main post, any site.
    ident, _ = draft(state, text='The result is here. ' + url)
    result = lint(state, ident)
    assert 'external URL' not in result[1] and 'user@host' not in result[1], result


@pytest.mark.parametrize('url', ['https://x.com@evil.test/a', 'https://owner@github.com/owner/a'])
def test_a_url_hiding_its_host_behind_user_at_still_fails(state, url):
    ident, _ = draft(state, text='The result is here. ' + url)
    result = lint(state, ident)
    # Refused either way: as an email-like string in the ledger (2) or by the main-post URL check (1).
    assert result[0] in (1, 2) and ('user@host' in result[1] or 'email address' in result[2]), result


def test_owner_approved_text_may_carry_a_link_in_the_main_post(state):
    ident, _ = draft(state, text='The result is here. https://example.org/paper', owner_wrote='approved in chat, exact text')
    assert 'external URL' not in lint(state, ident)[1]


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
        ident, _ = draft(state, text='A separate thought about the graph.', channel=channel,
                         **({'kind': 'other'} if channel == 'email' else {}))
        assert lint(state, ident)[0] == 0
        assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2
        assert cli(state[0], 'approve', 'a', ident, '--quote', 'Send this text')[0] == 0


def test_standing_does_not_bypass_failed_or_changed_lint(state):
    ident, _ = draft(state, text='Is this the right bound?')
    assert lint(state, ident)[0] == 1
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2
    ident, path = draft(state)
    assert lint(state, ident)[0] == 0
    path.write_text('A changed result.')
    assert cli(state[0], 'approve', 'a', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 2



def test_a_retracted_original_takes_no_slot(state, monkeypatch):
    """general, 11-09: a post that went out with the wrong video was deleted, and its replacement, same
    text, was held 120 min by the post it replaced. `retract` records the deletion once X confirms it."""
    monkeypatch.delenv('RH_X_MIN_GAP_MINUTES', raising=False)
    history(state, ident='wrong-video', age=2 / 60)
    ident, _ = draft(state)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'within 5 min of another original' in out
    root = state[0]
    monkeypatch.setattr(outreach, 'post_gone', lambda pid: False)
    rc, _, err = cli(root, 'retract', 'b', 'wrong-video', '--reason', 'wrong video')
    assert rc != 0 and 'still on X' in err
    monkeypatch.setattr(outreach, 'post_gone', lambda pid: None)
    rc, _, err = cli(root, 'retract', 'b', 'wrong-video', '--reason', 'wrong video')
    assert rc != 0 and '--deleted-confirmed' in err
    monkeypatch.setattr(outreach, 'post_gone', lambda pid: pid == '111' or pytest.fail(pid))
    assert cli(root, 'retract', 'b', 'wrong-video', '--reason', 'wrong video',
               '--replaced-by', 'https://x.com/someone/status/222')[0] == 0
    row = outreach.current(root / 'lanes/b', rh)['wrong-video']
    assert row['status'] == 'retracted' and row['sent']['utc'] and row['retracted']['replaced_by'].endswith('222')
    rc, out, _ = lint(state, ident)
    assert rc == 0, out
    # A sent post that was not retracted still holds its slot.
    history(state, ident='kept', age=2 / 60)
    rc, out, _ = lint(state, ident)
    assert rc == 1 and 'kept' in out


def test_only_a_sent_x_post_can_be_retracted(state, monkeypatch):
    monkeypatch.setattr(outreach, 'post_gone', lambda pid: True)
    history(state, ident='draft-only', status='approved')
    rc, _, err = cli(state[0], 'retract', 'b', 'draft-only', '--reason', 'x')
    assert rc != 0 and 'sent X post' in err
    history(state, ident='offline')
    assert cli(state[0], 'retract', 'b', 'offline', '--reason', 'x', '--deleted-confirmed', 'checked by hand: page says deleted')[0] == 0
    rc, _, err = cli(state[0], 'retract', 'b', 'offline', '--reason', 'x')
    assert rc != 0 and 'already retracted' in err


def test_a_sent_reply_whose_draft_file_is_gone_is_still_compared(state, monkeypatch):
    """general, 11-09: three sent replies of 11-07 had drafts in /private/tmp; it was wiped, and every
    new reply failed lint with "reply comparison draft unreadable"."""
    text = 'That matches what I saw on the second estimator, the bound holds.'
    first, path = approved(state, text=text, channel='x_reply', in_reply_to='https://x.com/a/status/1')
    assert cli(state[0], 'sent', 'a', first, '--message-id', '11', '--via', 'browser')[0] == 0
    near, _ = draft(state, text=text + ' Thanks.', channel='x_reply', in_reply_to='https://x.com/b/status/2')
    path.unlink()
    rc, out, _ = lint(state, near)
    assert rc == 1 and 'near-duplicate reply' in out and 'unreadable' not in out
    # Gone from the archive too: one lost draft warns, it does not block every later reply.
    for kept in Path(os.environ['RH_DRAFT_ARCHIVE']).iterdir():
        kept.unlink()
    rc, out, _ = lint(state, near)
    assert rc == 0 and 'near-duplicate check skipped' in out, out


def test_dropped_row_releases_its_reply_reservation(state):
    # 11-26: a dropped row whose posting attempt sent nothing still blocked the retry row for the same post.
    history(state, ident='old', channel='x_reply', status='dropped', in_reply_to='https://x.com/anna/status/123',
            gate_attempt={'utc': CLOCK.isoformat(), 'path': 'browser'})
    ident, _ = draft(state, text='The error bars shrink when the window grows.', channel='x_reply',
                     in_reply_to='https://x.com/anna/status/123')
    assert 'already replied or reserved' not in lint(state, ident)[1]


REFEREED = dict(lane='math', purpose='Original post, cand c1: [refereed: referee HOLDS]',
                text='A new upper bound on problem 1\n\nLean-checked: https://github.com/example/certs/tree/abc/p1')


@pytest.fixture
def math_lane(state, tmp_path, monkeypatch):
    """11-26: refereed bare math results post with their link and no .cuts. Synthetic bank only."""
    (state[0] / 'lanes' / 'math').mkdir()
    (tmp_path / 'en.jsonl').write_text(json.dumps({'text': 'thanks, that makes sense'}) + '\n')
    (tmp_path / 'banks.json').write_text(json.dumps({'en': {'path': 'en.jsonl', 'lang': 'en'}}))
    monkeypatch.setenv('RH_VOICE_BANKS', str(tmp_path / 'banks.json'))
    return state


def test_a_refereed_math_result_needs_no_cuts_and_keeps_its_link(math_lane):
    ident, _ = draft(math_lane, **REFEREED)
    rc, out, _ = lint(math_lane, ident, 'math')
    assert rc == 0 and 'VOICE_CUTS' not in out and 'external URL' not in out, out


@pytest.mark.parametrize('change', [dict(purpose='Original post, cand c1'), dict(lane='a'),
                                    dict(text=REFEREED['text'].replace('Lean-checked', 'Proof'))])
def test_without_the_marker_math_lane_or_certificate_line_both_rules_hold(math_lane, change):
    row = dict(REFEREED, **change)
    ident, _ = draft(math_lane, **row)
    rc, out, _ = lint(math_lane, ident, row['lane'])
    assert rc == 1 and 'VOICE_CUTS_MISSING' in out, out


def test_a_refereed_math_result_still_says_i(math_lane):
    ident, _ = draft(math_lane, **dict(REFEREED, text='We prove it.\n\nCertificate: https://github.com/example/certs'))
    rc, out, _ = lint(math_lane, ident, 'math')
    assert rc == 1 and 'VOICE_PLURAL' in out and 'VOICE_CUTS_MISSING' not in out, out


@pytest.mark.parametrize('age, projects, other_author, blocked', [
    (3, ['lean-golf-wave'], 'anna', True),      # same campaign, same person, 3 h ago
    (30, ['lean-golf-wave'], 'anna', False),    # more than a day ago
    (3, ['lean-golf-wave'], 'bob', False),      # another person
    (3, ['other-campaign'], 'anna', False),     # another campaign
    (3, [], 'anna', False)])                    # an ordinary reply thread is never held to it
def test_a_campaign_replies_to_each_person_at_most_once_a_day(state, age, projects, other_author, blocked):
    # 11-28 (general 1128e): the Lean Golf wave answers posts as a person would, one reply per person per day.
    history(state, ident='earlier', channel='x_reply', age=age, text='A different earlier reply about proofs.',
            in_reply_to=f'https://x.com/{other_author}/status/999', projects=projects)
    ident, _ = draft(state, text='Your agent could take this record.', channel='x_reply',
                     in_reply_to='https://x.com/anna/status/123', project='lean-golf-wave')
    assert ('already replied to @anna in the last 24 h' in lint(state, ident)[1]) == blocked
