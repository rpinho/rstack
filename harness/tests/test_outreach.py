"""Outreach commands and deterministic policy checks; all data stays in tmp_path."""
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import itertools
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import outreach
import rh

# Eight independently written approaches, rather than edits to a common template.
VARIED = ['A sine wave has one extra peak. Which sample interval reveals the alias? I would inspect the sampling grid.\n\nRegards,\nOperator', 'The square sequence changes sign at every step. Can a shorter period explain it? An exact enumeration would settle this.\n\nRegards,\nOperator', 'A sparse impulse can shift a spectral estimate. Where should an independent control place that impulse? The noise model remains fixed.\n\nRegards,\nOperator', 'Sorting the integers changes their adjacency. Does preserving the sum preserve the histogram too? My current check uses only a sum.\n\nRegards,\nOperator', 'A recursive sequence stops at a fixed depth. What terminal condition distinguishes zero from missing output? I can enumerate the shallow cases.\n\nRegards,\nOperator', 'The checker returns an empty certificate. Is that evidence of failure or a valid empty set? A type contract would clarify it.\n\nRegards,\nOperator', 'An interpolation has equal endpoints. Could it still exceed the endpoint range? I want a counterexample before adding a bound.\n\nRegards,\nOperator', 'A rotated grid preserves distances. Which invariant would expose an accidental reflection? I would test oriented areas.\n\nRegards,\nOperator']


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / 'harness'
    lane = root / 'lanes/test'
    lane.mkdir(parents=True)
    contacts = tmp_path / 'contacts.json'
    contacts.write_text(json.dumps([{'name': n} for n in ('Contact Alpha', 'Contact Beta')]))
    monkeypatch.setattr(outreach, 'CONTACTS', contacts)
    monkeypatch.setattr(outreach.contacts_ledger, 'CONTACTS', contacts)
    monkeypatch.setattr(rh, 'get_url', lambda *a: pytest.fail('network forbidden'))
    return root, lane


def cli(root, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = rh.main(['--root', str(root), 'outreach', *map(str, args)])
    return rc, out.getvalue(), err.getvalue()


def draft(env, text=None, to='Contact Alpha', channel='email', batch=None, lane_name='test', attach=None, claim=None, asked_about=()):
    root, _ = env
    path = root / ('body-' + str(len(list(root.glob('body-*')))) + '.txt')
    path.write_text(text or VARIED[0])
    args = ['draft', lane_name, '--to', to, '--channel', channel, '--purpose', 'Learn a biological constraint', '--file', path]
    if channel == 'email':
        args += ['--kind', 'other']
    if batch:
        args += ['--batch', batch]
    if attach:
        args += ['--attach', attach]
    if claim:
        args += ['--claim', claim]
    for term in asked_about:
        args += ['--asked-about', term]
    rc, out, err = cli(root, *args)
    assert rc == 0, err
    return out.strip(), path


def approve(env):
    ident, path = draft(env)
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    assert cli(env[0], 'approve', 'test', ident, '--quote', 'Send this one')[0] == 0
    return ident, path


def test_lifecycle_all_commands(env):
    root, lane = env
    ident, path = approve(env)
    before = rh.rows(lane / 'OUTREACH.jsonl')
    row = outreach.current(lane, rh)[ident]
    assert row['to_key'] == 'Contact Alpha'
    assert row['approval']['quote'] == 'Send this one'
    assert row['approval']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert cli(root, 'sent', 'test', ident, '--message-id', 'm1', '--thread-id', 't1', '--via', 'api')[0] == 0
    row = outreach.current(lane, rh)[ident]
    assert outreach.time_of(row['follow_up_due']) - outreach.time_of(row['sent']['utc']) == dt.timedelta(days=7)
    assert row['sent']['thread_id'] == 't1'
    assert ident in cli(root, 'due', '--all')[1]
    assert ident not in cli(root, 'due')[1]
    assert cli(root, 'reply', 'test', ident, '--summary', 'A staging control exists')[0] == 0
    assert ident not in cli(root, 'due', '--all')[1]
    assert cli(root, 'close', 'test', ident, '--reason', 'Question answered')[0] == 0
    assert outreach.current(lane, rh)[ident]['status'] == 'closed'
    assert rh.rows(lane / 'OUTREACH.jsonl')[:len(before)] == before
    assert json.loads(cli(root, 'status', '--json')[1])[0]['status'] == 'closed'
    assert ident in cli(root, 'status', 'test')[1]
    assert (lane / 'OUTREACH.jsonl.bak').exists()


def test_drop_command(env):
    ident, _ = draft(env)
    assert cli(env[0], 'drop', 'test', ident, '--reason', 'No longer useful')[0] == 0
    assert outreach.current(env[1], rh)[ident]['status'] == 'dropped'


@pytest.mark.parametrize('stage', ['lint', 'approval'])
def test_edit_invalidates_hash(env, stage):
    ident, path = draft(env)
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    if stage == 'approval':
        assert cli(env[0], 'approve', 'test', ident, '--quote', 'Looks fine')[0] == 0
    path.write_text(path.read_text() + '\nAnother sentence.')
    if stage == 'lint':
        rc, _, err = cli(env[0], 'approve', 'test', ident, '--quote', 'Fine')
    else:
        rc, _, err = cli(env[0], 'sent', 'test', ident, '--message-id', 'm', '--via', 'browser')
    assert rc == 2 and 'changed' in err


def test_approve_and_sent_require_predecessor(env):
    ident, _ = draft(env)
    assert cli(env[0], 'approve', 'test', ident, '--quote', 'Fine')[0] == 2
    assert cli(env[0], 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 2
    assert cli(env[0], 'reply', 'test', ident, '--summary', 'Reply')[0] == 2


def test_approval_batch_all_or_none(env):
    a, _ = draft(env, VARIED[0], batch='b')
    b, path = draft(env, VARIED[1], to='Contact Beta', batch='b')
    assert cli(env[0], 'lint', 'test', '--batch', 'b')[0] == 0
    path.write_text('Edited.')
    assert cli(env[0], 'approve', 'test', '--batch', 'b', '--quote', 'Both')[0] == 2
    assert all(r['status'] == 'linted' for r in outreach.current(env[1], rh).values())
    assert cli(env[0], 'lint', 'test', '--batch', 'b')[0] == 0
    assert cli(env[0], 'approve', 'test', '--batch', 'b', '--quote', 'Both')[0] == 0


def test_varied_batch_passes_every_check(env):
    for i, text in enumerate(VARIED):
        draft(env, text, to='@varied' + str(i), channel='x_dm', batch='varied')
    rc, out, err = cli(env[0], 'lint', 'test', '--batch', 'varied')
    assert rc == 0, out + err
    assert out.count('PASS') == 8


def test_identical_batch_warns_without_blocking(env):
    """Ricardo, 11-05: "I don't think anybody will be comparing emails. What's important is
    that it doesn't sound like AI slop and that it uses my voice." Two emails that resemble
    each other are still reported, but as a warning, so a shared Portuguese closing -- which
    the two-language rule makes likely -- can never block recording or sending.
    """
    a, _ = draft(env, batch='same')
    b, _ = draft(env, to='Contact Beta', batch='same')
    rc, out, _ = cli(env[0], 'lint', 'test', '--batch', 'same')
    assert rc == 0 and out.count('PASS') == 2
    assert 'WARN: pair ' + a + ' / ' + b in out or 'WARN: pair ' + b + ' / ' + a in out
    assert 'body-5gram' in out and 'first Jaccard' in out and 'last Jaccard' in out
    # Approval and the send receipt both go through, which is the point of the change.
    assert cli(env[0], 'approve', 'test', a, '--quote', 'Send this one')[0] == 0
    assert cli(env[0], 'sent', 'test', a, '--message-id', 'm1', '--via', 'browser')[0] == 0


def test_recent_sends_compared_even_without_batch(env):
    ident, _ = approve(env)
    assert cli(env[0], 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 0
    new, _ = draft(env, to='Contact Beta')
    rc, out, _ = cli(env[0], 'lint', 'test', new)
    assert rc == 0 and 'WARN: pair ' + new + ' / ' + ident in out


def test_a_send_recorded_after_the_fact_keeps_its_real_time(env):
    """An email that went out before the ledger caught up (friends, 11-05) is recorded at the
    time it actually left, so the follow-up falls due from when the recipient got it.
    """
    ident, _ = approve(env)
    earlier = '2026-11-05T18:13:00+00:00'
    assert cli(env[0], 'sent', 'test', ident, '--message-id', 'd', '--via', 'api',
               '--utc', '2099-01-01T00:00:00+00:00')[0] != 0, 'a send cannot be in the future'
    rc, _, err = cli(env[0], 'sent', 'test', ident, '--message-id', 'abc', '--thread-id', 'thr',
                     '--via', 'browser', '--utc', earlier)
    assert rc == 0, err
    row = outreach.current(env[1], rh)[ident]
    assert row['sent']['utc'] == earlier and row['sent']['thread_id'] == 'thr'
    assert row['follow_up_due'] > earlier


def test_old_sends_not_compared(env):
    ident, _ = draft(env)
    old = outreach.current(env[1], rh)[ident]
    old.update(status='sent', sent={'utc': (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=15)).isoformat()})
    rh.append(env[1] / 'OUTREACH.jsonl', old)
    new, _ = draft(env, to='Contact Beta')
    assert cli(env[0], 'lint', 'test', new)[0] == 0


@pytest.mark.parametrize('text,check', [('Hello! Can you help?', 'voice'), ('What changed? Why?', 'questions'),
                                       ('See https:// for details.', 'links'), ('Read http://bad:port/test.', 'links')])
def test_lint_failures(env, text, check):
    ident, _ = draft(env, text)
    rc, out, _ = cli(env[0], 'lint', 'test', ident)
    assert rc == 1 and check + ':' in out
    assert outreach.current(env[1], rh)[ident]['status'] == 'drafted'


def test_x_reply_uses_reply_flag(env):
    ident, _ = draft(env, 'A' * 245 + '.', to='@scientist', channel='x_reply')
    rc, out, _ = cli(env[0], 'lint', 'test', ident)
    assert rc == 1 and 'reply longer' in out


def test_contact_validation_and_ledger_privacy(env):
    root, lane = env
    path = root / 'private.txt'
    path.write_text('A question?')
    assert cli(root, 'draft', 'test', '--to', 'Unknown', '--channel', 'email', '--purpose', 'Learn', '--file', path)[0] == 2
    assert cli(root, 'draft', 'test', '--to', ('private' + chr(64) + 'example.org'), '--channel', 'email', '--purpose', 'Learn', '--file', path)[0] == 2
    ident, _ = draft(env)
    env_contacts = json.loads(outreach.CONTACTS.read_text())
    outreach.CONTACTS.write_text('[]')
    assert 'contact:' in cli(root, 'lint', 'test', ident)[1]
    outreach.CONTACTS.write_text(json.dumps(env_contacts))
    assert cli(root, 'lint', 'test', ident)[0] == 0
    assert cli(root, 'approve', 'test', ident, '--quote', ('send private' + chr(64) + 'example.org'))[0] == 2
    assert not outreach.EMAIL.search((lane / 'OUTREACH.jsonl').read_text())


def test_cross_lane_collision_and_override(env):
    root, lane = env
    ident, _ = approve(env)
    assert cli(root, 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 0
    other = root / 'lanes/other'
    other.mkdir()
    new, _ = draft(env, VARIED[2], lane_name='other')
    rc, out, _ = cli(root, 'lint', 'other', new)
    assert rc == 1 and 'collision:' in out and 'test/' + ident in out
    assert cli(root, 'lint', 'other', new, '--allow-collision', 'Operator requested a second message')[0] == 0
    assert cli(root, 'approve', 'other', new, '--quote', 'Send again')[0] == 0
    assert cli(root, 'sent', 'other', new, '--message-id', 'second', '--via', 'browser')[0] == 0


def test_collision_rechecked_at_sent(env):
    root, lane = env
    ident, _ = approve(env)
    other = root / 'lanes/other'
    other.mkdir()
    new, _ = draft(env, VARIED[2], lane_name='other')
    assert cli(root, 'lint', 'other', new)[0] == 0
    assert cli(root, 'approve', 'other', new, '--quote', 'Send')[0] == 0
    assert cli(root, 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 0
    assert cli(root, 'sent', 'other', new, '--message-id', 'second', '--via', 'api')[0] == 2


def test_team_reuses_science_checks_and_two_questions(env):
    root, _ = env
    (root / 'lanes/team').mkdir()
    (root / 'lanes/team/OUTREACH.toml').write_text('question_limit = 2\nscience_checks = true\n')
    ident, _ = draft(env, 'Would this help? Is it useful or slop?', lane_name='team')
    assert cli(root, 'lint', 'team', ident)[0] == 0
    with patch.object(outreach, 'science_checks', wraps=outreach.science_checks) as check:
        assert cli(root, 'lint', 'team', ident)[0] == 0
        check.assert_called_once()
    # Actual legacy function supplies the results/slop diagnostic as well as review requirements.
    errors = outreach.science_checks('Would this help?', [root / 'results.pdf'])
    assert any('useful or slop' in e for e in errors)


def test_config_question_limit_and_follow_up(env):
    root, lane = env
    (lane / 'OUTREACH.toml').write_text('question_limit = 2\nfollow_up_days = 10\n')
    ident, _ = draft(env, 'Which landmark? At what age?')
    assert cli(root, 'lint', 'test', ident)[0] == 0
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send')[0] == 0
    assert cli(root, 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 0
    row = outreach.current(lane, rh)[ident]
    assert outreach.time_of(row['follow_up_due']) - outreach.time_of(row['sent']['utc']) == dt.timedelta(days=10)


def test_health_due_stale_approval_and_no_approval(env):
    root, lane = env
    ident, _ = approve(env)
    row = outreach.current(lane, rh)[ident]
    row['approval']['utc'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=49)).isoformat()
    rh.append(lane / 'OUTREACH.jsonl', row)
    assert 'over 48 h' in ' '.join(outreach.health(lane, rh))
    row.update(status='sent', approval=None, follow_up_due='2000-01-01T00:00:00+00:00')
    rh.append(lane / 'OUTREACH.jsonl', row)
    assert 'without approval' in ' '.join(outreach.health(lane, rh))
    assert 'overdue' in ' '.join(outreach.health(lane, rh))
    assert ident in cli(root, 'due', '--json')[1]
    assert cli(root, 'close', 'test', ident, '--reason', 'Done')[0] == 0
    assert outreach.health(lane, rh) == []


def test_rh_lint_integration(env):
    root, lane = env
    ident, _ = draft(env)
    row = outreach.current(lane, rh)[ident]
    row.update(status='sent', follow_up_due='2000-01-01T00:00:00+00:00')
    rh.append(lane / 'OUTREACH.jsonl', row)
    with patch.object(rh.cadence, 'lint', return_value=[]), patch.object(rh.pods, 'lint', return_value=[]):
        result = rh.lint_result(lane)
    assert result['outreach']['status'] == 'FAIL'
    assert any(f['check'] == 'outreach' for f in result['failures'])


def test_normalisation_names_links_titles_and_signature():
    a = 'Hi Alpha,\n\nI am reading “First Paper” at https://one.example/a. Can you explain the result?\n\nThanks,\nOperator'
    b = 'Hi Beta,\n\nI am reading “Second Paper” at https://two.example/b. Can you explain the result?\n\nBest,\nOperator'
    assert outreach.features(a, ('Alpha', 'Beta'))[:2] == outreach.features(b, ('Alpha', 'Beta'))[:2]
    assert outreach.normalise('Alpha says hello', ('Alpha',)) == outreach.normalise('Beta says hello', ('Beta',))


@pytest.mark.parametrize('url', ['https://example.org/a?x=3&y=4', 'http://localhost:8080/a', 'https://doi.org/10.1000/abc', 'https://[::1]/'])
def test_valid_links(url):
    assert outreach.link_errors('See ' + url) == []


@pytest.mark.parametrize('url', ['https://', 'https:/bad', 'www.example.org/a', 'ftp://example.org', 'https://bad..host', 'https://host:99999'])
def test_invalid_links(url):
    assert outreach.link_errors('See ' + url)




def test_url_query_does_not_add_a_question(env):
    ident, _ = draft(env, 'Can this landmark work? See https://example.org/a?q=signal for the diagram.')
    assert cli(env[0], 'lint', 'test', ident)[0] == 0


def test_team_x_still_defaults_to_one_question(env):
    (env[0] / 'lanes/team').mkdir()
    (env[0] / 'lanes/team/OUTREACH.toml').write_text('question_limit = 2\nscience_checks = true\n')
    ident, _ = draft(env, 'Which marker? At what age?', to='@friend', channel='x_reply', lane_name='team')
    assert 'questions:' in cli(env[0], 'lint', 'team', ident)[1]


def test_unreadable_draft_fails_lint_without_advancing(env):
    ident, path = draft(env)
    row = outreach.current(env[1], rh)[ident]
    row['draft_path'] = str(env[0] / 'missing.txt')
    rh.append(env[1] / 'OUTREACH.jsonl', row)
    assert cli(env[0], 'lint', 'test', ident)[0] == 1
    assert outreach.current(env[1], rh)[ident]['status'] == 'drafted'


def test_malformed_sent_record_reports_outreach_instead_of_crashing(env):
    ident, _ = draft(env)
    row = outreach.current(env[1], rh)[ident]
    row['status'] = 'sent'
    rh.append(env[1] / 'OUTREACH.jsonl', row)
    errors = outreach.health(env[1], rh)
    assert any('without approval' in e for e in errors)
    assert any('follow-up date' in e for e in errors)


def test_empty_batch_and_traversal_refused(env):
    assert cli(env[0], 'lint', 'test', '--batch', 'missing')[0] == 2
    assert cli(env[0], 'status', '../test')[0] == 2
    assert cli(env[0], 'lint', 'test', 'id', '--batch', 'both')[0] == 2


def test_reply_summary_refuses_quoted_text(env):
    ident, _ = approve(env)
    assert cli(env[0], 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] == 0
    assert cli(env[0], 'reply', 'test', ident, '--summary', 'They said "yes"')[0] == 2
    assert outreach.current(env[1], rh)[ident]['status'] == 'sent'


def test_collision_ids_are_scoped_to_lane():
    now = dt.datetime.now(dt.timezone.utc)
    draft = dict(id='same-id', lane='a', to_key='Contact Alpha')
    sent = dict(draft, lane='b', sent={'utc': now.isoformat()})
    assert outreach.collisions(draft, [sent], now) == [sent]


def test_outreach_only_lane_skips_research_checks(tmp_path):
    lane = tmp_path / 'lanes' / 'post-history'
    lane.mkdir(parents=True)
    (lane / 'OUTREACH.jsonl').write_text('')
    assert rh.outreach_only(lane)
    result = rh.lint_result(lane)
    assert result['depth'] is None and not any(f['check'] in ('queue-depth', 'intake-freshness') for f in result['failures'])
    (lane / 'IDEAS.jsonl').write_text('')
    assert not rh.outreach_only(lane)


PT_GREETING = 'Olá Beta, tudo bem? Espero que o trabalho esteja a correr bem por aí.'
PT_SIGNOFF = 'Obrigado pelo teu tempo e um abraço, até breve.'
EN_SCIENCE = ('We measured a correlation of 0.68 between length and the mean score, so the '
              'ranking tracks length. The control run gives 0.11 on the same dataset.')
PT_SCIENCE = ('Medimos uma correlação de 0.68 entre o comprimento e a média, portanto a '
              'ordenação segue o comprimento. O controlo dá 0.11 com os mesmos dados.')


def with_language(env, name='Contact Beta', language='pt'):
    """Give one fixture contact a language, the way a private contacts file would."""
    rows = json.loads(outreach.CONTACTS.read_text())
    for row in rows:
        if row['name'] == name:
            row['language'] = language
    outreach.CONTACTS.write_text(json.dumps(rows))


def test_portuguese_recipient_fails_on_portuguese_science(env):
    root, lane = env
    with_language(env)
    ident, _ = draft(env, '\n\n'.join([PT_GREETING, PT_SCIENCE, PT_SIGNOFF]), to='Contact Beta')
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'language:' in out and 'paragraph 2' in out
    assert outreach.current(lane, rh)[ident]['status'] == 'drafted'


def test_portuguese_recipient_passes_when_the_shape_is_right(env):
    root, lane = env
    with_language(env)
    ident, _ = draft(env, '\n\n'.join([PT_GREETING, EN_SCIENCE, PT_SIGNOFF]), to='Contact Beta')
    assert cli(root, 'lint', 'test', ident)[0] == 0
    assert outreach.current(lane, rh)[ident]['lint']['warnings'] == []


def test_english_opening_fails_and_a_middle_english_line_only_warns(env):
    root, lane = env
    with_language(env)
    english_open = 'Hi Beta, I hope you are well and that the work is going along nicely there.'
    ident, _ = draft(env, '\n\n'.join([english_open, EN_SCIENCE, PT_SIGNOFF]), to='Contact Beta')
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'language:' in out and 'opening' in out

    aside = 'By the way, I hope the move went well and that you are settled in by now.'
    other, _ = draft(env, '\n\n'.join([PT_GREETING, aside, EN_SCIENCE, PT_SIGNOFF]), to='Contact Beta')
    rc, out, _ = cli(root, 'lint', 'test', other)
    assert rc == 0, 'a personal line in the middle is a warning, never a block'
    assert 'WARN: ' in out and 'European Portuguese' in out
    warnings = outreach.current(lane, rh)[other]['lint']['warnings']
    assert len(warnings) == 1 and 'paragraph 2' in warnings[0]


def test_english_recipient_keeps_the_old_behaviour(env):
    """An unset language means English: a Portuguese draft to Alpha is not this rule's business."""
    root, _ = env
    ident, _ = draft(env, '\n\n'.join([PT_GREETING, PT_SCIENCE, PT_SIGNOFF]), to='Contact Alpha')
    assert cli(root, 'lint', 'test', ident)[0] == 0


def test_a_bad_language_code_is_reported_not_ignored(env):
    root, _ = env
    with_language(env, language='Portuguese please')
    ident, _ = draft(env, '\n\n'.join([PT_GREETING, EN_SCIENCE, PT_SIGNOFF]), to='Contact Beta')
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'contact:' in out and 'language code' in out


def test_recipient_language_reaches_the_science_checker(env):
    root, _ = env
    with_language(env)
    (root / 'lanes/team').mkdir()
    (root / 'lanes/team/OUTREACH.toml').write_text('question_limit = 2\nscience_checks = true\n')
    ident, _ = draft(env, '\n\n'.join([PT_GREETING, EN_SCIENCE, PT_SIGNOFF, 'Is it useful or slop?']),
                     to='Contact Beta', lane_name='team')
    with patch.object(outreach, 'science_checks', return_value=[]) as check:
        assert cli(root, 'lint', 'team', ident)[0] == 0
    assert check.call_args.args[2] == 'pt'


def recheck_setup(env, name='alpha_A001', pod=False, rerun='match', verdict='SURVIVES',
                  incident='2026-11-05T04:58:00+00:00', require=False):
    """A claim directory and a re-check ledger, wired into the lane's OUTREACH.toml."""
    import csv
    root, lane = env
    claim = root / 'claims' / name
    claim.mkdir(parents=True)
    (claim / 'CLAIM.md').write_text('# invented claim\n')
    if pod:
        (claim / 'pod_run.sh').write_text('#!/bin/sh\n')
    recheck = root / 'recheck_1105'
    recheck.mkdir(parents=True, exist_ok=True)
    with (recheck / 'RECHECK.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=('id', 'rerun', 'verdict', 'utc'))
        writer.writeheader()
        writer.writerow(dict(id=name, rerun=rerun, verdict=verdict,
                             utc='2026-11-05T10:00:00+00:00'))
    (lane / 'OUTREACH.toml').write_text(
        'recheck_roots = ["{}"]\n'.format(recheck).replace('\\', '\\\\')
        + ('pod_incident_utc = "{}"\n'.format(incident) if incident else '')
        + ('require_claims = true\n' if require else ''))
    return claim


def test_lint_fails_a_result_email_whose_claim_was_never_independently_rechecked(env):
    """Gate 1 end to end: the claim is real, the re-check ledger does not name it."""
    root, _ = env
    recheck_setup(env, name='alpha_A001')
    other = root / 'claims' / 'alpha_A002'
    other.mkdir(parents=True)
    (other / 'CLAIM.md').write_text('# invented claim\n')
    ident, _ = draft(env, claim=str(other))
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'FAIL' in out
    assert 'evidence: RECHECK_MISSING claim alpha_A002' in out
    assert outreach.current(env[1], rh)[ident]['status'] == 'drafted'
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] != 0


def test_lint_passes_a_result_email_whose_claim_a_separate_model_rebuilt(env):
    """Gate 1 end to end, the passing case: the ledger says it was re-run and survived."""
    root, _ = env
    claim = recheck_setup(env, name='alpha_A001')
    ident, _ = draft(env, claim=str(claim))
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 0 and 'PASS' in out and 'evidence' not in out
    assert outreach.current(env[1], rh)[ident]['claims'] == [str(claim)]
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] == 0


def test_lint_fails_pod_touched_evidence_rechecked_before_the_host_incident(env):
    """Gate 2 end to end: evidence from a rented pod, re-checked the day before."""
    root, _ = env
    claim = recheck_setup(env, name='alpha_A003', pod=True,
                          incident='2026-11-05T20:00:00+00:00')
    ident, _ = draft(env, claim=str(claim))
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'produced on a pod' in out and 'pod_run.sh' in out
    assert 'before the host incident' in out and 're-run it somewhere trusted' in out


def test_lint_passes_pod_touched_evidence_rerun_after_the_host_incident(env):
    """Gate 2 end to end, the passing case: the re-run is dated after the incident."""
    root, _ = env
    claim = recheck_setup(env, name='alpha_A004', pod=True,
                          incident='2026-11-05T04:58:00+00:00')
    ident, _ = draft(env, claim=str(claim))
    assert cli(root, 'lint', 'test', ident)[0] == 0


def test_a_lane_can_require_claims_and_an_unconfigured_lane_is_unaffected(env):
    """The gates bind where a lane asks for them, and change nothing anywhere else."""
    root, lane = env
    recheck_setup(env, name='alpha_A005', require=True)
    bare, _ = draft(env)
    rc, out, _ = cli(root, 'lint', 'test', bare)
    assert rc == 1 and '--claim' in out and 'separate model' in out
    (lane / 'OUTREACH.toml').write_text('')
    assert cli(root, 'lint', 'test', bare)[0] == 0, 'no config, no gate'


def test_a_misconfigured_gate_refuses_rather_than_switching_itself_off(env):
    root, lane = env
    ident, _ = draft(env)
    for bad in ('recheck_roots = "one-string"\n', 'require_claims = "yes"\n',
                'pod_incident_utc = "last Tuesday"\n', 'require_claims = true\n'):
        (lane / 'OUTREACH.toml').write_text(bad)
        assert cli(root, 'lint', 'test', ident)[0] != 0, bad


def test_the_science_checker_is_handed_the_claims(env):
    root, _ = env
    claim = recheck_setup(env, name='alpha_A006')
    (root / 'lanes/test/OUTREACH.toml').write_text(
        (root / 'lanes/test/OUTREACH.toml').read_text() + 'science_checks = true\n')
    ident, _ = draft(env, claim=str(claim))
    with patch.object(outreach, 'science_checks', return_value=[]) as check:
        assert cli(root, 'lint', 'test', ident)[0] == 0
    assert check.call_args.args[3] == [str(claim)]


# The sentence this rule came from (Ricardo, 11-06): an email of 11-05 told a friend "The first
# two ran on a RunPod server that has since had a security incident." He asked what it meant,
# and Ricardo's read was "we shouldn't have said that. That was completely unnecessary to say."
OPS_EMAIL = ('A sine wave has one extra peak. The first two ran on a RunPod server that has '
             'since had a security incident, so I re-solved them on my own machine and the '
             'optima match.\n\nRegards,\nOperator')


def test_lint_fails_an_email_that_tells_a_friend_about_our_infrastructure(env):
    root, lane = env
    ident, _ = draft(env, OPS_EMAIL)
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 1 and 'ops: OPS_DETAIL: runpod' in out and 'security-incident' in out
    assert 're-checked on my own machine' in out, 'the fix belongs in the failure'
    assert outreach.current(lane, rh)[ident]['status'] == 'drafted'
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] != 0


def test_lint_passes_an_email_that_answers_what_the_friend_asked_about(env):
    """The friend asked what the sentence meant, so the reply has to be able to say the word."""
    root, lane = env
    ident, _ = draft(env, OPS_EMAIL, asked_about=['runpod', 'security-incident'])
    rc, out, _ = cli(root, 'lint', 'test', ident)
    assert rc == 0 and 'PASS' in out and 'WARN: ops: runpod' in out
    assert outreach.current(lane, rh)[ident]['asked_about'] == ['runpod', 'security-incident']
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] == 0


def test_asked_about_takes_only_the_known_terms_never_the_friends_words(env):
    root, _ = env
    path = root / 'typo.txt'
    path.write_text(OPS_EMAIL)
    for value in ('runpodd', 'que quer dizer isto'):
        assert cli(root, 'draft', 'test', '--to', 'Contact Alpha', '--channel', 'email',
                   '--purpose', 'Learn', '--file', path, '--asked-about', value)[0] == 2


def test_the_ops_rule_leaves_a_public_post_alone(env):
    """Ricardo names his own hosts and tools in public; this is about what a friend is told."""
    ident, _ = draft(env, 'Re-solved 20 instances off a RunPod box. Optima match.',
                     to='@scientist', channel='x_post')
    rc, out, _ = cli(env[0], 'lint', 'test', ident)
    assert rc == 0 and 'ops' not in out, out


def test_record_sent_lands_a_message_that_already_went_out_and_failed_todays_lint(env):
    """friends, 11-05: a personal reply went out before it was registered, and lint failed the
    already-sent text (three questions, one a rhetorical tag). approve refused, so sent refused,
    so the row had to be dropped -- and the friend's next reply had nothing to attach to.
    Refusing to record a message does not un-send it; it only puts a hole in the ledger.
    """
    root, lane = env
    ident, _ = draft(env, 'Did it work? Why not? Right?')
    assert cli(root, 'lint', 'test', ident)[0] == 1, 'the already-sent text fails lint'
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] != 0
    assert cli(root, 'sent', 'test', ident, '--message-id', 'm', '--via', 'api')[0] != 0
    earlier = '2026-11-05T22:44:00+00:00'
    rc, out, err = cli(root, 'record-sent', 'test', ident, '--message-id', 'abc',
                       '--thread-id', 'thr', '--via', 'api', '--utc', earlier,
                       '--reason', 'Ricardo replied from his phone before it was registered')
    assert rc == 0, err
    assert 'went out before it was recorded: questions:' in out
    row = outreach.current(lane, rh)[ident]
    assert row['status'] == 'sent' and row['sent']['utc'] == earlier
    assert row['sent']['message_id'] == 'abc' and row['sent']['thread_id'] == 'thr'
    # The findings are kept rather than dropped: the postmortem needs them.
    after = row['recorded_after_the_fact']
    assert after['lint_ok'] is False and any('questions:' in f for f in after['findings'])
    assert 'phone before it was registered' in after['reason']
    # The follow-up falls due from when it really left, and a reply can now attach to it.
    assert row['follow_up_due'] > earlier
    assert cli(root, 'reply', 'test', ident, '--summary', 'He answered the second question')[0] == 0


def test_a_recorded_send_is_bookkeeping_and_can_never_authorize_a_send(env):
    """The send hook matches bytes against an approved entry. A recorded row has no approval,
    so recording history cannot become a way around `rh outreach approve`.
    """
    root, lane = env
    ident, path = draft(env, 'Did it work? Why not? Right?')
    assert cli(root, 'record-sent', 'test', ident, '--message-id', 'abc', '--via', 'api',
               '--utc', '2026-11-05T22:44:00+00:00', '--reason', 'Sent from his phone')[0] == 0
    row = outreach.current(lane, rh)[ident]
    assert 'approval' not in row
    gate = Path(__file__).resolve().parents[2] / 'tools/email-voice-gate.py'
    spec = importlib.util.spec_from_file_location('gate_under_test', gate)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert not hook.approved_body({'body': path.read_text()}, root), 'recorded is not approved'
    # And it cannot be walked back into the sendable states either.
    assert cli(root, 'approve', 'test', ident, '--quote', 'Send it')[0] != 0
    assert cli(root, 'record-sent', 'test', ident, '--message-id', 'z', '--via', 'api',
               '--utc', '2026-11-05T22:44:00+00:00', '--reason', 'again')[0] != 0


def test_record_sent_refuses_a_future_time_and_an_approved_draft(env):
    root, _ = env
    ident, _ = draft(env, 'Did it work? Why not? Right?')
    assert cli(root, 'record-sent', 'test', ident, '--message-id', 'm', '--via', 'api',
               '--utc', '2099-01-01T00:00:00+00:00', '--reason', 'r')[0] != 0
    approved, _ = approve(env)
    rc, _, err = cli(root, 'record-sent', 'test', approved, '--message-id', 'm', '--via', 'api',
                     '--utc', '2026-11-05T22:44:00+00:00', '--reason', 'r')
    assert rc != 0 and 'record it with `sent`' in err


def test_the_standing_approval_token_cannot_approve_an_email(env):
    """11-07/08: Ricardo gave the lane sessions a standing authorization for repo text, PRs, repo
    settings and routine lane choices, and general asked for confirmation that this boundary had
    not moved with it. It had not, and it had no test, which is how a rule quietly stops being one
    at exactly the moment it starts carrying weight.

    The token approves public X posts and replies only. An email or a DM needs his own words, and
    "first emails to someone new under his name" is on the list the authorization explicitly keeps
    for him.
    """
    ident, _ = draft(env, channel='email')
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    rc, _, err = cli(env[0], 'approve', 'test', ident, '--quote', outreach.STANDING_APPROVAL)
    assert rc == 2, 'the standing token must not approve an email'
    assert "owner's own words" in err
    assert outreach.current(env[1], rh)[ident]['status'] == 'linted'
    # His actual words do approve it, so the refusal is about the token and not about emails.
    assert cli(env[0], 'approve', 'test', ident, '--quote', 'Yes, send that one')[0] == 0


def test_the_standing_approval_token_cannot_approve_a_dm_either(env):
    ident, _ = draft(env, to='@someone', channel='x_dm')
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    rc, _, err = cli(env[0], 'approve', 'test', ident, '--quote', outreach.STANDING_APPROVAL)
    assert rc == 2 and "owner's own words" in err


def test_the_standing_approval_token_does_approve_a_public_x_post(env):
    """The token exists for a reason; this pins which side of the line it is on, so a later change
    that narrowed or widened it would fail here rather than pass quietly."""
    ident, _ = draft(env, to='@someone', channel='x_post')
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    assert cli(env[0], 'approve', 'test', ident, '--quote', outreach.STANDING_APPROVAL)[0] == 0
    assert outreach.current(env[1], rh)[ident]['approval']['quote'] == outreach.STANDING_APPROVAL


def test_an_approval_with_no_quote_is_not_a_command_at_all(env):
    """--quote is required, so there is no path that records an approval without words in it."""
    ident, _ = draft(env)
    assert cli(env[0], 'lint', 'test', ident)[0] == 0
    with pytest.raises(SystemExit):
        cli(env[0], 'approve', 'test', ident)
