"""Bug-hunt lane rules as checks that refuse (docs/outreach.md, "Bug-hunt lane").

Each rule came from a miss. 11-08: a bug report went to a repository last committed 2021-07-23;
three emails went to one person in a day; a draft was readied for an address that had bounced;
a demanding reader was about to get a result checked once. Everything here runs on tmp_path with
synthetic contacts and a fake GitHub; nothing touches the network.
"""
import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bughunt
import contacts_ledger
import outreach
import rh
from test_outreach import VARIED, cli, env  # noqa: F401  (env is a fixture)

NOW = dt.datetime.now(dt.timezone.utc)
CONTACTS = [
    {'name': 'Contact Alpha', 'channels': 'alpha@lab.example.org (lab page, 11-01); X none',
     'last_out': '2026-10-01 email', 'ball': 'them'},
    {'name': 'Contact Beta', 'channels': 'beta@old.example.org BOUNCED 11-08'},
    {'name': 'Contact Gamma', 'channels': 'gamma@uni.example.edu', 'scrutiny': 'extra'},
]


@pytest.fixture
def lane(env, tmp_path, monkeypatch):
    root, lane = env
    contacts = tmp_path / 'contacts.json'
    contacts.write_text(json.dumps(CONTACTS))
    monkeypatch.setattr(outreach, 'CONTACTS', contacts)
    monkeypatch.setattr(contacts_ledger, 'CONTACTS', contacts)
    monkeypatch.delenv('RH_CONTACT_UPDATES', raising=False)
    (lane / 'OUTREACH.toml').write_text('question_limit = 3\n')
    return root, lane, contacts


def config(lane, text):
    (lane[1] / 'OUTREACH.toml').write_text('question_limit = 3\n' + text)


def draft(lane, text=VARIED[0], to='Contact Alpha', kind='code-bug', **options):
    root = lane[0]
    path = root / ('body-{}.txt'.format(len(list(root.glob('body-*')))))
    path.write_text(text)
    args = ['draft', 'test', '--to', to, '--channel', 'email', '--purpose', 'Report a bug', '--file', path]
    for k in ([kind] if isinstance(kind, str) else kind or []):
        args += ['--kind', k]
    for key, value in options.items():
        for item in value if isinstance(value, list) else [value]:
            args += ['--' + key.replace('_', '-'), item]
    result = cli(root, *args)
    assert result[0] == 0, result
    return result[1].strip(), path


def lint(lane, ident):
    rc, out, err = cli(lane[0], 'lint', 'test', ident)
    return rc, out + err


def send(lane, ident, quote='Send it'):
    assert lint(lane, ident)[0] == 0, lint(lane, ident)
    assert cli(lane[0], 'approve', 'test', ident, '--quote', quote)[0] == 0
    result = cli(lane[0], 'sent', 'test', ident, '--message-id', 'm-' + ident, '--via', 'browser')
    assert result[0] == 0, result


# ---- 1. target recency and activity -------------------------------------------------------

def fake_github(created='2019-01-01', commit='2026-10-01', release=None, tag=None, archived=False,
                readme='A tool for things.', exists=True):
    import base64

    def get(path):
        if not exists:
            return None
        if path.startswith('repos/') and path.count('/') == 2:
            return dict(archived=archived, default_branch='main', created_at=created)
        if '/commits?' in path and 'since=' in path:
            return [{}] * (3 if (commit or '') >= '2025' else 0)
        if '/commits?' in path:
            return [dict(commit=dict(committer=dict(date=commit + 'T12:00:00Z')))] if commit else []
        if path.endswith('/releases?per_page=1'):
            return [dict(published_at=release + 'T00:00:00Z')] if release else []
        if path.endswith('/tags?per_page=1'):
            return [dict(commit=dict(sha='abc'))] if tag else []
        if '/commits/abc' in path:
            return dict(commit=dict(committer=dict(date=tag + 'T00:00:00Z')))
        if '/issues?' in path:
            return [dict(updated_at='2026-09-01T00:00:00Z')]
        if '/pulls?' in path or '/branches?' in path:
            return []
        if path.endswith('/readme'):
            return dict(content=base64.b64encode(readme.encode()).decode())
        raise AssertionError('unexpected GitHub path ' + path)
    return get


CLOCK = dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)


def test_the_11_08_miss_fails_a_repository_last_committed_in_2021():
    row = bughunt.target_check('https://github.com/someone/old-tool', get=fake_github(commit='2021-07-23'),
                               clock=CLOCK)
    assert row['verdict'] == 'FAIL' and row['target'] == 'someone/old-tool'
    assert 'days ago (limit 365)' in row['reasons'][0]
    assert row['numbers']['last_commit'] == '2021-07-23'


@pytest.mark.parametrize('options, verdict', [
    (dict(commit='2026-06-19'), 'PASS'),
    (dict(commit='2024-01-01', release='2026-03-12'), 'PASS'),        # a recent release counts
    (dict(commit='2024-01-01', tag='2026-03-12'), 'PASS'),            # and so does a tag
    (dict(commit='2026-06-19', archived=True), 'FAIL'),
    (dict(commit='2026-06-19', readme='This project is no longer maintained.'), 'FAIL'),
    (dict(commit=None), 'FAIL'),
    (dict(exists=False), 'FAIL'),
])
def test_what_passes(options, verdict):
    assert bughunt.target_check('a/b', get=fake_github(**options), clock=CLOCK)['verdict'] == verdict


@pytest.mark.parametrize('target', ['https://zenodo.org/records/123', 'https://data.mendeley.com/datasets/x/1',
                                    'https://gitlab.com/a/b'])
def test_a_data_deposit_or_an_uncheckable_host_fails(target):
    row = bughunt.target_check(target, get=lambda p: pytest.fail('no GitHub read for ' + p), clock=CLOCK)
    assert row['verdict'] == 'FAIL'


def target_verdict(lane, target, verdict='PASS', days_ago=0):
    rh.append(lane[1] / 'TARGETS.jsonl', dict(target=target, verdict=verdict, reasons=[] if verdict == 'PASS'
                                              else ['last commit or release 1569 days ago (limit 365)'],
                                              utc=(NOW - dt.timedelta(days=days_ago)).isoformat()))


def test_the_cli_stores_the_verdict_and_lint_reads_it(lane, monkeypatch):
    monkeypatch.setattr(bughunt, 'github', fake_github(commit=(NOW - dt.timedelta(days=30)).date().isoformat()))
    rc, out, _ = rh_cli(lane, 'bughunt', 'target-check', 'test', 'Org/Tool')
    assert rc == 0 and out.startswith('PASS org/tool')
    ident, _ = draft(lane, target='https://github.com/org/tool')
    assert lint(lane, ident)[0] == 0


def rh_cli(lane, *args):
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = rh.main(['--root', str(lane[0]), *args])
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.parametrize('verdict, days_ago, code', [(None, 0, 'TARGET_UNCHECKED'),
                                                     ('FAIL', 0, 'TARGET_FAILED'),
                                                     ('PASS', 8, 'TARGET_STALE')])
def test_a_target_without_a_fresh_pass_refuses(lane, verdict, days_ago, code):
    if verdict:
        target_verdict(lane, 'org/tool', verdict, days_ago)
    ident, _ = draft(lane, target='org/tool')
    rc, out = lint(lane, ident)
    assert rc == 1 and code in out


def test_a_code_email_must_name_its_target_when_the_lane_says_so(lane):
    config(lane, 'target_required_kinds = ["code"]\n')
    ident, _ = draft(lane)
    assert 'TARGET_MISSING' in lint(lane, ident)[1]
    ident, _ = draft(lane, kind='paper')
    assert lint(lane, ident)[0] == 0


def test_an_override_turns_the_refusal_into_a_recorded_warning(lane):
    target_verdict(lane, 'org/tool', 'FAIL')
    ident, _ = draft(lane, target='org/tool', target_override='they asked about the 2019 release')
    rc, out = lint(lane, ident)
    assert rc == 0 and 'WARN: TARGET_FAILED' in out and 'overridden' in out


# ---- 6. kind --------------------------------------------------------------------------------

def test_every_email_says_what_it_reports(lane):
    ident, _ = draft(lane, kind=None)
    assert 'KIND_MISSING' in lint(lane, ident)[1]


# ---- 2. one email per person per day, batched -----------------------------------------------

def test_a_second_email_the_same_day_refuses_at_lint_and_at_send(lane):
    config(lane, 'emails_per_contact_per_day = 1\n')
    first, _ = draft(lane, text=VARIED[0])
    second, _ = draft(lane, text=VARIED[1])
    assert lint(lane, second)[0] == 0                    # nothing sent yet
    assert cli(lane[0], 'approve', 'test', second, '--quote', 'Send it')[0] == 0
    send(lane, first)
    assert 'DAILY_LIMIT' in lint(lane, draft(lane, text=VARIED[2])[0])[1]
    rc, _, err = cli(lane[0], 'sent', 'test', second, '--message-id', 'm2', '--via', 'browser')
    assert rc != 0 and 'DAILY_LIMIT' in err


def test_unsent_drafts_to_one_person_are_merged_into_one(lane):
    config(lane, 'emails_per_contact_per_day = 1\n')
    a, _ = draft(lane, text=VARIED[0], target='org/one')
    b, _ = draft(lane, text=VARIED[1], kind='paper')
    assert 'rh outreach batch' in lint(lane, a)[1]
    out = lane[0] / 'merged.txt'
    rc, stdout, _ = cli(lane[0], 'batch', 'test', 'Contact Alpha', '--file', out)
    assert rc == 0
    merged = stdout.split()[0]
    rows = outreach.current(lane[1], rh)
    assert rows[a]['status'] == rows[b]['status'] == 'dropped'
    assert rows[merged]['targets'] == ['org/one'] and rows[merged]['kinds'] == ['code-bug', 'paper']
    assert 'MERGE_UNEDITED' in lint(lane, merged)[1], 'a concatenation is not an email'
    out.write_text(VARIED[0] + '\n\n' + VARIED[3])
    target_verdict(lane, 'org/one')
    rc, text = lint(lane, merged)
    assert 'MERGE_UNEDITED' not in text


# ---- 3. contacts kept current ----------------------------------------------------------------

def test_addresses_are_read_from_free_text_with_their_bounces():
    book = contacts_ledger.addresses({'channels': 'a@x.example.org (lab page); b@y.example.org BOUNCED 11-08; X @a'})
    assert [(a['address'], a['status']) for a in book] == [('a@x.example.org', 'live'), ('b@y.example.org', 'bounced')]
    assert book[0]['source'] == 'lab page'


def test_a_contact_whose_only_address_bounced_cannot_be_written_to(lane):
    ident, _ = draft(lane, to='Contact Beta')
    assert 'ADDRESS_DEAD' in lint(lane, ident)[1]


def test_send_reply_and_bounce_keep_the_contact_current_without_touching_the_file(lane):
    root, _, contacts = lane
    before = contacts.read_bytes()
    ident, _ = draft(lane)
    send(lane, ident)
    row = contacts_ledger.merged(root, 'Contact Alpha')
    assert row['ball'] == 'them' and 'email: Report a bug' in row['last_out']
    assert cli(root, 'reply', 'test', ident, '--summary', 'They will look at it')[0] == 0
    row = contacts_ledger.merged(root, 'Contact Alpha')
    assert row['ball'] == 'us' and 'They will look at it' in row['last_in']
    assert cli(root, 'bounce', 'test', ident)[0] == 0
    row = contacts_ledger.merged(root, 'Contact Alpha')
    assert row['needs_find'] and not contacts_ledger.live_addresses(row)
    assert 'ADDRESS_DEAD' in lint(lane, draft(lane, text=VARIED[4])[0])[1]
    assert contacts.read_bytes() == before, 'the contacts file is the owner\'s; updates go to the ledger'
    pending = contacts_ledger.pending(root)['Contact Alpha']
    assert pending['ball'] == 'us' and pending['addresses'][0]['status'] == 'bounced'
    assert '@' not in (lane[1] / 'OUTREACH.jsonl').read_text().replace('@a', ''), 'no address in the lane ledger'


def fake_sources(page):
    def get(url, accept='application/json'):
        if 'openalex.org/authors' in url:
            return json.dumps(dict(results=[dict(id='https://openalex.org/A1', display_name='Contact Alpha',
                                                 orcid='https://orcid.org/0000-0001', works_count=12,
                                                 last_known_institutions=[dict(display_name='A University')])]))
        if 'openalex.org/works' in url:
            return json.dumps(dict(results=[dict(publication_date='2026-05-01', display_name='A paper',
                                                 doi='https://doi.org/10.1/x')]))
        if 'orcid.org' in url:
            return json.dumps(dict(email=[]))
        if url == 'https://lab.example.org/people':
            return page
        raise OSError('unreachable')
    return get


def test_find_reads_public_sources_and_records_only_what_it_found(lane, monkeypatch):
    root = lane[0]
    monkeypatch.setattr(contacts_ledger, 'fetch', fake_sources(
        '<a href="mailto:c.alpha@new.example.org">mail</a> office: admin [at] new.example.org'))
    found = contacts_ledger.find('Contact Alpha', ['https://lab.example.org/people'], get=contacts_ledger.fetch)
    assert [c['address'] for c in found['candidates']][0] == 'c.alpha@new.example.org'
    assert found['candidates'][0]['matches_name'] and {'kind': 'work'}.items() <= found['sources'][1].items()
    rc, _, err = cli(root, 'contact', 'find', 'Contact Alpha', '--record', 'made.up@example.org')
    assert rc != 0 and 'was not found' in err
    ident, _ = draft(lane)
    send(lane, ident)
    assert cli(root, 'bounce', 'test', ident)[0] == 0
    assert contacts_ledger.merged(root, 'Contact Alpha')['needs_find']
    rc, out, _ = cli(root, 'contact', 'find', 'Contact Alpha', '--url', 'https://lab.example.org/people',
                     '--record', 'c.alpha@new.example.org')
    assert rc == 0
    row = contacts_ledger.merged(root, 'Contact Alpha')
    assert contacts_ledger.live_addresses(row) == ['c.alpha@new.example.org'] and not row['needs_find']
    assert row['addresses'][-1]['source'] == 'https://lab.example.org/people'


# ---- 4. scrutiny ---------------------------------------------------------------------------

def verdict_dir(tmp, name, text='| B1 | CONFIRMED | repro.sh |'):
    d = tmp / name
    d.mkdir()
    (d / 'VERDICTS.md').write_text(text)
    return d


def test_an_extra_scrutiny_contact_needs_two_rechecks_and_a_review_of_the_exact_text(lane, tmp_path):
    one = verdict_dir(tmp_path, 'ref1')
    failed = verdict_dir(tmp_path, 'ref-failed', '| B1 | NOT REPRODUCED |')
    ident, path = draft(lane, to='Contact Gamma', recheck=[one, failed])
    text = lint(lane, ident)[1]
    assert 'SECOND_RECHECK_MISSING' in text and 'found 1' in text and 'TEXT_REVIEW_MISSING' in text
    two = verdict_dir(tmp_path, 'ref2', '# Verdict\nPASS: both bugs reproduce.')
    ident, path = draft(lane, to='Contact Gamma', recheck=[one, two])
    assert 'SECOND_RECHECK_MISSING' not in lint(lane, ident)[1]
    assert cli(lane[0], 'review', 'test', ident, '--by', 'a second model', '--verdict', 'pass')[0] == 0
    assert lint(lane, ident)[0] == 0
    path.write_text(path.read_text() + '\nOne more line.')
    assert 'TEXT_REVIEW_MISSING' in lint(lane, ident)[1], 'the review was of different text'


def test_scrutiny_can_be_set_for_a_contact(lane):
    assert cli(lane[0], 'contact', 'scrutiny', 'Contact Alpha', 'extra')[0] == 0
    assert 'SECOND_RECHECK_MISSING' in lint(lane, draft(lane)[0])[1]


# ---- 5. required questions -----------------------------------------------------------------

QUESTIONS = ('required_questions_kinds = ["code"]\n'
             'required_question_names = ["uses AI", "useful or slop"]\n'
             'required_questions = [["ai", "ia", "agents", "agentes"], ["useful", "útil", "slop"]]\n')


def test_a_bug_email_asks_the_required_questions(lane):
    config(lane, QUESTIONS)
    bare, _ = draft(lane)
    out = lint(lane, bare)[1]
    assert "QUESTION_MISSING: a code-bug email asks 'uses AI'" in out and "'useful or slop'" in out
    asked, _ = draft(lane, text=VARIED[1] + '\n\nDo you use AI in your research, and is this useful or slop?')
    assert lint(lane, asked)[0] == 0
    pt, _ = draft(lane, text=VARIED[2] + '\n\nÉ útil ou é slop? Usas agentes de IA na tua investigação?')
    assert lint(lane, pt)[0] == 0
    paper, _ = draft(lane, kind='paper')
    assert lint(lane, paper)[0] == 0


def test_a_question_already_answered_is_not_asked_again(lane):
    config(lane, QUESTIONS)
    assert cli(lane[0], 'contact', 'answered', 'Contact Alpha', 'uses AI', '--source', 'said so on 11-08')[0] == 0
    ident, _ = draft(lane, text=VARIED[1] + '\n\nIs this useful or slop?')
    rc, out = lint(lane, ident)
    assert rc == 0 and "'uses AI' not asked: already answered (said so on 11-08)" in out


@pytest.mark.parametrize('line', ['required_questions = ["ai"]', 'emails_per_contact_per_day = -1',
                                  'required_question_names = ["one"]\nrequired_questions = [["a"], ["b"]]'])
def test_a_bad_setting_refuses(lane, line):
    config(lane, line + '\n')
    rc, _, err = cli(lane[0], 'lint', 'test', draft(lane)[0])
    assert rc != 0 and ('OUTREACH' in err or 'unsupported' in err), err


# ---- 6. counts -------------------------------------------------------------------------------

def test_stats_count_sends_replies_and_kinds(lane):
    a, _ = draft(lane, kind='code-bug')
    send(lane, a)
    assert cli(lane[0], 'reply', 'test', a, '--summary', 'Thanks, fixed')[0] == 0
    b, _ = draft(lane, to='Contact Gamma', kind='paper', recheck=[])
    rows = outreach.current(lane[1], rh)
    rh.append(lane[1] / 'OUTREACH.jsonl', dict(rows[b], status='sent', sent=dict(utc=NOW.isoformat(), message_id='x', via='api')))
    result = json.loads(cli(lane[0], 'stats', 'test', '--json')[1])
    assert result['total']['sent'] == 2 and result['total']['replies'] == 1 and result['total']['reply_rate'] == 0.5
    assert result['total']['by_kind']['code-bug'] == dict(sent=1, replies=1, bounced=0, reply_rate=1.0)
    assert result['contacts']['Contact Alpha']['ball'] == 'us'
    aggregate = cli(lane[0], 'stats', '--aggregate')[1]
    assert 'Contact' not in aggregate and json.loads(aggregate)['contacts'] == 2
    assert json.loads(cli(lane[0], 'stats', '--contact', 'contact gamma', '--json')[1])['total']['sent'] == 1


def test_the_example_lane_config_loads(tmp_path):
    lane = tmp_path / 'lanes/friends'
    lane.mkdir(parents=True)
    example = Path(__file__).resolve().parents[2] / 'examples/friends-lane/OUTREACH.toml'
    (lane / 'OUTREACH.toml').write_text(example.read_text())
    cfg = outreach.settings(lane, rh)
    assert cfg['emails_per_contact_per_day'] == 1 and cfg['target_required_kinds'] == ['code-bug', 'code-speedup']
    assert len(cfg['required_questions']) == len(cfg['required_question_names']) == 2


def test_a_past_send_can_be_given_its_kind_for_the_counts_but_a_draft_cannot(lane):
    sent, _ = draft(lane, kind=None)
    rows = outreach.current(lane[1], rh)
    rh.append(lane[1] / 'OUTREACH.jsonl', dict(rows[sent], status='sent',
                                              sent=dict(utc=NOW.isoformat(), message_id='x', via='api')))
    assert json.loads(cli(lane[0], 'stats', '--aggregate')[1])['by_kind'] == {
        'unknown': dict(sent=1, replies=0, bounced=0, reply_rate=0.0)}
    assert cli(lane[0], 'set-kind', 'test', sent, 'code-bug', '--reason', 'a bug report')[0] == 0
    row = outreach.current(lane[1], rh)[sent]
    assert row['kind'] == 'code-bug' and row['kind_set']['was'] is None
    assert list(json.loads(cli(lane[0], 'stats', '--aggregate')[1])['by_kind']) == ['code-bug']
    unsent, _ = draft(lane, kind=None)
    rc, _, err = cli(lane[0], 'set-kind', 'test', unsent, 'code-bug', '--reason', 'r')
    assert rc != 0 and 'draft an unsent one again' in err


def test_a_hand_logged_send_is_adopted_into_the_counts_and_the_daily_limit(lane):
    """11-08: fifteen sends were appended by hand (sent_at, no status) and nothing counted them."""
    config(lane, 'emails_per_contact_per_day = 1\n')
    path = lane[0] / 'hand.txt'
    path.write_text(VARIED[5])
    when = (NOW - dt.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    rh.append(lane[1] / 'OUTREACH.jsonl', dict(id='hand1', lane='test', channel='email', to_name='Contact Alpha',
                                              to_key='Contact Alpha', purpose='bug report', draft_path=str(path),
                                              sent_at=when, sent_by='a session, browser', approved_by='the owner'))
    assert json.loads(cli(lane[0], 'stats', '--aggregate')[1])['sent'] == 0
    rc, out, err = cli(lane[0], 'adopt', 'test', 'hand1', '--kind', 'code-bug', '--reason', 'logged by hand on 11-08')
    assert rc == 0, err
    row = outreach.current(lane[1], rh)['hand1']
    assert row['status'] == 'sent' and 'approval' not in row and row['approved_by'] == 'the owner'
    assert json.loads(cli(lane[0], 'stats', '--aggregate')[1])['by_kind']['code-bug']['sent'] == 1
    assert 'DAILY_LIMIT' in lint(lane, draft(lane, text=VARIED[6])[0])[1]
    assert cli(lane[0], 'adopt', 'test', 'hand1', '--kind', 'code-bug', '--reason', 'again')[0] != 0


def test_a_draft_in_a_temporary_directory_is_refused(lane, monkeypatch):
    """11-08: drafts kept in a session scratchpad under /tmp vanished at the 11-07 reset."""
    monkeypatch.delenv('RH_DRAFT_TEMP_OK')
    path = Path('/tmp') / 'rh-test-draft-{}.txt'.format(id(lane))
    path.write_text(VARIED[0])
    try:
        rc, _, err = cli(lane[0], 'draft', 'test', '--to', 'Contact Alpha', '--channel', 'email',
                         '--purpose', 'p', '--file', path, '--kind', 'code-bug')
    finally:
        path.unlink()
    assert rc != 0 and 'temporary directory' in err


def test_a_hand_logged_row_with_an_address_in_its_purpose_is_adopted_or_dropped_without_it(lane):
    base = dict(lane='test', channel='email', to_name='Contact Alpha', to_key='Contact Alpha',
                sent_at=(NOW - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), sent_by='a session')
    rh.append(lane[1] / 'OUTREACH.jsonl', dict(base, id='resend', purpose='Resend to a@x.example.org'))
    rh.append(lane[1] / 'OUTREACH.jsonl', dict(base, id='bounce', purpose='BOUNCE from a@x.example.org'))
    rc, _, err = cli(lane[0], 'adopt', 'test', 'resend', '--kind', 'code-bug', '--reason', 'hand-logged')
    assert rc != 0 and 'email address' in err
    assert cli(lane[0], 'adopt', 'test', 'resend', '--kind', 'code-bug', '--reason', 'hand-logged',
               '--purpose', 'Resend of the bug report')[0] == 0
    assert cli(lane[0], 'drop', 'test', 'bounce', '--reason', 'recorded with bounce instead',
               '--purpose', 'BOUNCE notice')[0] == 0
    rows = outreach.current(lane[1], rh)
    assert rows['resend']['status'] == 'sent' and rows['bounce']['status'] == 'dropped'
    assert '@x.example.org' not in rows['resend']['purpose'] + rows['bounce']['purpose']


def test_a_send_that_skipped_the_ledger_is_recorded_with_its_findings_kept(lane):
    """A code email that went out before the rules existed, on a target that fails today."""
    target_verdict(lane, 'org/old', 'FAIL')
    ident, _ = draft(lane, target='org/old')
    when = (NOW - dt.timedelta(hours=5)).isoformat()
    rc, out, err = cli(lane[0], 'record-sent', 'test', ident, '--message-id', 'not recorded', '--via', 'browser',
                       '--utc', when, '--reason', 'sent on 11-08 before it was logged')
    assert rc == 0, err
    row = outreach.current(lane[1], rh)[ident]
    assert row['status'] == 'sent' and 'approval' not in row
    assert any('TARGET_FAILED' in f for f in row['recorded_after_the_fact']['findings'])
    assert cli(lane[0], 'bounce', 'test', ident, '--address', 'alpha@lab.example.org')[0] == 0
    assert json.loads(cli(lane[0], 'stats', '--aggregate')[1])['bounced'] == 1


# ---- engagement (11-08: "treat people like they want to be treated") ------------------------

def test_engagement_is_shown_on_every_draft_and_a_just_send_contact_gets_no_permission_question(lane):
    assert cli(lane[0], 'contact', 'engagement', 'Contact Alpha', 'Just send it, no need to ask first',
               '--source', 'his reply of 11-08')[0] == 0
    plain, _ = draft(lane, text=VARIED[0])
    rc, out = lint(lane, plain)
    assert rc == 0 and 'engagement: Just send it' in out
    for ask in ('Do you want me to open a PR?', 'Would you prefer a PR or patch?', 'Shall I send the fix?'):
        ident, _ = draft(lane, text=VARIED[1] + '\n\n' + ask)
        rc, out = lint(lane, ident)
        assert rc == 1 and 'ENGAGEMENT:' in out, ask


def test_a_contact_who_likes_to_be_asked_can_be_asked(lane):
    assert cli(lane[0], 'contact', 'engagement', 'Contact Alpha', 'Ask before sending code; prefers PRs',
               '--source', 'email of 11-01')[0] == 0
    ident, _ = draft(lane, text=VARIED[1] + '\n\nDo you want me to open a PR?')
    rc, out = lint(lane, ident)
    assert rc == 0 and 'engagement: Ask before sending' in out


def test_engagement_lands_through_pending_like_every_other_contact_update(lane):
    cli(lane[0], 'contact', 'engagement', 'Contact Beta', 'Prefers WhatsApp', '--source', 's')
    assert contacts_ledger.pending(lane[0])['Contact Beta']['engagement'] == 'Prefers WhatsApp'


def test_a_send_they_asked_for_is_a_reply_not_outreach_so_the_daily_limit_does_not_hold_it(lane):
    config(lane, 'emails_per_contact_per_day = 1\n')
    first, _ = draft(lane, text=VARIED[0])
    send(lane, first)
    unrequested, _ = draft(lane, text=VARIED[2])
    assert 'DAILY_LIMIT:' in lint(lane, unrequested)[1]
    asked, _ = draft(lane, text=VARIED[3], requested='"just send it" (his reply today)')
    rc, out = lint(lane, asked)
    assert rc == 0 and 'DAILY_LIMIT not applied: they asked for this' in out
    send(lane, asked)
    assert outreach.current(lane[1], rh)[asked]['status'] == 'sent'
