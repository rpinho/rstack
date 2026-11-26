"""lane-nudge decides from idle time, running state, cadence status and its own rate limit."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import json
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
nudge = SourceFileLoader('lane_nudge', str(REPO / 'harness/tools/lane-nudge/lane-nudge')).load_module()
NOW = 1_000_000.0


@pytest.mark.parametrize('state', ['retired', 'ended', 'held'])
def test_registry_skips_alias_without_a_skip_list_or_cadence_help(tmp_path, monkeypatch, capsys, state):
    lanes = tmp_path / 'lanes'
    lanes.mkdir()
    row = {'status': 'active' if state == 'ended' else state, 'why': 'finished challenge',
           'sessions': ['closedb']}
    if state == 'ended':
        row['end'] = str(date.today() - timedelta(days=1))
    (lanes / 'REGISTRY.json').write_text(json.dumps({'lanes': {'closed': row}}))
    monkeypatch.setattr(nudge.sys, 'argv', ['lane-nudge', '--lanes', str(lanes), '--skip', '',
                                         '--state', str(tmp_path / 'state'), '--log', str(tmp_path / 'log')])
    monkeypatch.setattr(nudge, 'cadence', lambda _: ({'closedb': {'status': 'OK'}}, None))
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('closedb', '%1', '/work')])
    def unexpected(*args, **kwargs):
        pytest.fail('inactive session reached transcript scan or tmux')
    monkeypatch.setattr(nudge, 'idle_minutes', unexpected)
    monkeypatch.setattr(nudge.subprocess, 'run', unexpected)
    nudge.main()
    assert 'closedb: skipped (closed: ' + state in capsys.readouterr().out
    assert 'finished challenge' in (tmp_path / 'log').read_text()


def test_retired_session_is_skipped_even_when_cadence_is_unavailable(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'lanes': {'closed': {'status': 'retired', 'sessions': ['closedb']}}}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(path))
    monkeypatch.setattr(nudge.sys, 'argv', ['lane-nudge', '--state', str(tmp_path), '--skip', '', '--dry'])
    monkeypatch.setattr(nudge, 'cadence', lambda _: (None, 'offline'))
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('closedb', '%1', '/work')])
    monkeypatch.setattr(nudge, 'idle_minutes', lambda *_: pytest.fail('retired lane scanned'))
    nudge.main()
    assert 'retired' in capsys.readouterr().out


def test_quiet_lane_with_nothing_running_is_nudged():
    assert nudge.decide(90, False, 'OK', 0, NOW) == 'quiet'


def test_cadence_behind_is_named():
    assert nudge.decide(61, False, 'STALLED', 0, NOW) == 'STALLED on cadence'


@pytest.fixture
def public_cadence_lane(tmp_path, monkeypatch):
    lane = tmp_path / 'open-source'
    lane.mkdir()
    (lane / 'CADENCE.toml').write_text(
        'deliverable = "Public contribution"\nowner_session = "open-source"\n'
        'every_hours = 26\nevidence_jsonl = "DELIVERIES.jsonl"\n'
        'timestamp_field = "finished"\nsuccess_field = "ok"\n')
    (lane / 'DELIVERIES.jsonl').write_text('{"finished":"2026-11-19T23:00:00Z","ok":true,"kind":"pr"}\n')
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('RH_GH', 'gh')   # the bare name these tests' fake subprocess.run expects
    return lane


@pytest.mark.parametrize('event_type,target,author,pr', [
    ('IssueCommentEvent', 'issue', 'fixture-user', True),  # review reply in the PR conversation
    ('IssueCommentEvent', 'issue', 'fixture-user', False),  # comment on our own issue
    ('PullRequestReviewCommentEvent', 'pull_request', 'fixture-user', True),  # inline reply
    ('PullRequestReviewEvent', 'pull_request', 'maintainer', True),
])
def test_only_recent_public_event_clears_cadence(
        public_cadence_lane, monkeypatch, event_type, target, author, pr):
    import cadence
    import rh

    subject = {'number': 2554, 'user': {'login': author}}
    if event_type == 'PullRequestReviewCommentEvent':
        subject = {'number': 2554, 'url': 'https://api.github.com/repos/example/project/pulls/2554'}
    if pr and target == 'issue':
        subject['pull_request'] = {'url': 'https://api.github.com/repos/example/project/pulls/2554'}
    own_reply = {
        'type': event_type, 'public': True, 'actor': {'login': 'Fixture-User'},
        'created_at': '2026-11-20T17:51:53Z',
        'payload': {'action': 'created', target: subject},
    }
    controls = [
        dict(own_reply, public=False),
        dict(own_reply, actor={'login': 'maintainer'}),
        dict(own_reply, payload={**own_reply['payload'], 'action': 'edited'}),
        dict(own_reply, type='IssueCommentEvent',
             payload={'action': 'created', 'issue': {'user': {'login': 'maintainer'}}}),
        dict(own_reply, created_at='2026-11-21T00:00:00Z'),
    ]
    pages = [controls, []]

    def gh(args, **kwargs):
        assert 0 < kwargs['timeout'] <= 15 and kwargs['check']
        if args == ['gh', 'api', '--hostname', 'github.com', 'user', '--jq', '.login']:
            return nudge.subprocess.CompletedProcess(args, 0, stdout='fixture-user\n')
        if args == ['gh', 'api', '--hostname', 'github.com',
                    'repos/example/project/pulls/2554', '--jq', '.user.login']:
            assert event_type == 'PullRequestReviewCommentEvent'
            return nudge.subprocess.CompletedProcess(args, 0, stdout=author + '\n')
        assert args == ['gh', 'api', '--hostname', 'github.com',
                        'users/fixture-user/events/public?per_page=100', '--paginate', '--slurp']
        return nudge.subprocess.CompletedProcess(args, 0, stdout=json.dumps(pages))

    monkeypatch.setattr(cadence.subprocess, 'run', gh)
    now = '2026-11-20T18:00:00Z'
    row = cadence.evaluate(public_cadence_lane, rh, now)
    assert row['status'] == 'WARN'
    pages[1].append(own_reply)
    row = cadence.evaluate(public_cadence_lane, rh, now)
    assert row['status'] == 'OK'
    assert row['last_delivery'] == '2026-11-20T17:51:53+00:00'
    assert nudge.decide(61, False, row['status'], 0, NOW) == 'quiet'


def test_github_read_error_warns_without_a_cadence_flag(public_cadence_lane, monkeypatch, capsys):
    import cadence
    import rh

    def offline(*args, **kwargs):
        raise nudge.subprocess.TimeoutExpired('gh', 15)

    monkeypatch.setattr(cadence.subprocess, 'run', offline)
    row = cadence.evaluate(public_cadence_lane, rh, '2026-11-20T18:00:00Z')
    assert row['status'] == 'UNKNOWN'
    assert nudge.decide(61, False, row['status'], 0, NOW) == 'quiet'
    assert 'could not read public GitHub activity (TimeoutExpired)' in capsys.readouterr().err
    ledger = public_cadence_lane.parent / 'harness-blocks.jsonl'
    entry = json.loads(ledger.read_text())
    assert (entry['gate'], entry['outcome']) == ('cadence.public-activity', 'warn')


def test_gh_off_the_path_is_found_at_a_usual_location(public_cadence_lane, monkeypatch, capsys, tmp_path):
    """The monitor job has a bare PATH: gh was a FileNotFoundError warning 144 times in 24 h."""
    import cadence
    import rh
    event = {'type': 'PullRequestReviewEvent', 'public': True, 'actor': {'login': 'fixture-user'},
             'created_at': '2026-11-20T17:51:53Z', 'payload': {'action': 'created'}}
    fake = tmp_path / 'bin' / 'gh'
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\ncase "$*" in\n  *"--jq .login"*) printf "fixture-user\\n";;\n'
                    "  *events/public*) printf '%s' '" + json.dumps([[event]]) + "';;\n"
                    '  *) exit 1;;\nesac\n')
    fake.chmod(0o755)
    monkeypatch.delenv('RH_GH')
    monkeypatch.setenv('PATH', str(tmp_path / 'nowhere'))
    monkeypatch.setattr(cadence, 'GH_FALLBACKS', ())
    assert cadence.gh_binary() == 'gh'   # nothing found: the old behaviour, not a crash
    monkeypatch.setattr(cadence, 'GH_FALLBACKS', (str(tmp_path / 'absent/gh'), str(fake)))
    assert cadence.gh_binary() == str(fake)
    row = cadence.evaluate(public_cadence_lane, rh, '2026-11-20T18:00:00Z')
    assert row['status'] == 'OK' and row['last_delivery'] == '2026-11-20T17:51:53+00:00'
    assert 'could not read' not in capsys.readouterr().err
    assert not (public_cadence_lane.parent / 'harness-blocks.jsonl').exists()
    monkeypatch.setenv('RH_GH', str(tmp_path / 'other-gh'))
    assert cadence.gh_binary() == str(tmp_path / 'other-gh')   # RH_GH wins


def test_a_missing_gh_warns_once_per_lane_per_day(public_cadence_lane, monkeypatch, capsys, tmp_path):
    import cadence
    import rh
    monkeypatch.delenv('RH_GH')
    monkeypatch.setenv('PATH', str(tmp_path / 'nowhere'))
    monkeypatch.setattr(cadence, 'GH_FALLBACKS', ())
    for _ in range(3):
        row = cadence.evaluate(public_cadence_lane, rh, '2026-11-20T18:00:00Z')
        assert row['status'] == 'UNKNOWN'
    assert capsys.readouterr().err.count('could not read public GitHub activity (FileNotFoundError)') == 1
    ledger = public_cadence_lane.parent / 'harness-blocks.jsonl'
    assert len(ledger.read_text().splitlines()) == 1
    state = json.loads((public_cadence_lane.parent / 'cadence-public-warned.json').read_text())
    assert list(state) == ['open-source|could not read public GitHub activity (FileNotFoundError)']
    state_file = public_cadence_lane.parent / 'cadence-public-warned.json'
    state_file.write_text(json.dumps({k: '2000-01-01' for k in state}))   # an old day: warns again
    cadence.evaluate(public_cadence_lane, rh, '2026-11-20T18:00:00Z')
    assert len(ledger.read_text().splitlines()) == 2


def test_unreadable_delivery_ledger_still_uses_public_activity(public_cadence_lane, monkeypatch, capsys):
    import cadence
    import rh

    def unreadable(*args):
        raise PermissionError

    monkeypatch.setattr(cadence, 'delivery_time', unreadable)
    delivery = cadence.stamp('2026-11-20T17:51:53Z')
    monkeypatch.setattr(cadence, 'github_delivery_time', lambda clock, since: delivery)
    row = cadence.evaluate(public_cadence_lane, rh, '2026-11-20T18:00:00Z')
    assert row['status'] == 'OK'
    assert row['last_delivery'] == delivery.isoformat()
    assert 'could not read the delivery ledger (PermissionError)' in capsys.readouterr().err


def test_running_work_or_recent_turn_is_left_alone():
    assert nudge.decide(500, True, 'STALLED', 0, NOW) is None
    assert nudge.decide(59, False, 'WARN', 0, NOW) is None


def test_rate_limited_per_lane():
    assert nudge.decide(500, False, 'WARN', NOW - 3600, NOW) is None
    assert nudge.decide(500, False, 'WARN', NOW - 7201, NOW) == 'WARN on cadence'


def test_exempt_and_unconfigured_never_nudged():
    assert nudge.decide(10_000, False, 'HELD', 0, NOW) is None     # paused by its owner (friends, 11-11)
    assert nudge.decide(10_000, False, 'EXEMPT', 0, NOW) is None
    assert nudge.decide(10_000, False, 'UNCONFIGURED', 0, NOW) is None


def test_running_pattern_matches_claude_code_status_lines():
    assert nudge.RUNNING.search('done 2:41 PM · 1 shell still running')
    assert nudge.RUNNING.search('Shimmying… (esc to interrupt)')
    assert not nudge.RUNNING.search('Worked for 3m 15s · done 10:47 AM')


def test_a_failed_cadence_read_is_loud_never_all_clear(tmp_path, capsys):
    """11-08: a bare `rh` missing from launchd's PATH failed every read for 8 h and every lane read as fine."""
    cad, error = nudge.cadence(str(tmp_path / 'no-such-rh'))
    assert cad is None and 'FileNotFoundError' in error
    fake = tmp_path / 'rh'
    fake.write_text('#!/bin/sh\necho "Traceback: boom" >&2\nexit 2\n')
    fake.chmod(0o755)
    assert nudge.cadence(str(fake)) == (None, 'exit 2, no JSON: Traceback: boom')
    behind = tmp_path / 'rh-behind'
    behind.write_text('#!/bin/sh\necho \'[{"owner_session": "a", "status": "STALLED"}]\'\nexit 1\n')
    behind.chmod(0o755)
    assert nudge.cadence(str(behind))[0]['a']['status'] == 'STALLED', 'exit 1 means a lane is behind, not a failed read'
    sent = tmp_path / 'sent.txt'
    alert = '/bin/sh -c \'echo "$0" >> {}\''.format(sent)
    for _ in range(3):
        nudge.report_failure(error, tmp_path, alert, dry=False)
    assert 'CADENCE READ FAILED' in capsys.readouterr().err
    assert sent.read_text().count('CADENCE READ FAILED') == 1, 'one push per failure streak'
    nudge.report_failure(None, tmp_path, alert, dry=False)
    assert 'recovered' in sent.read_text() and not (tmp_path / 'cadence-failed.json').exists()


def _row(kind, ts, **extra):
    import json
    return json.dumps(dict(type=kind, timestamp=ts, message={'role': kind, 'content': 'x'}, **extra))


def test_idle_is_measured_from_the_last_real_turn_not_the_file_mtime(tmp_path):
    """11-08 to 11-11: idle compaction rewrote every lane transcript about hourly, mtime never aged past
    60 minutes, and no lane was nudged for three days. Compaction rows and the untimestamped metadata a
    session rewrites while idle must not count as activity."""
    import json
    import os
    from datetime import datetime
    projects = tmp_path / 'projects'
    pane = '/Users/x/.worktrees/kb/math'
    d = projects / '-Users-x--worktrees-kb-math'
    d.mkdir(parents=True)
    f = d / 's.jsonl'
    rows = [
        _row('user', '2026-11-08T19:00:00.000Z'),
        _row('assistant', '2026-11-08T19:21:00.000Z'),
        json.dumps(dict(type='system', subtype='compact_boundary', timestamp='2026-11-09T22:50:39.000Z')),
        _row('user', '2026-11-09T22:50:39.000Z', isCompactSummary=True),
        _row('user', '2026-11-09T22:50:40.000Z', isMeta=True),
        json.dumps(dict(type='last-prompt', lastPrompt='x')),
        json.dumps(dict(type='bridge-session', lastSequenceNum=9)),
    ]
    f.write_text('\n'.join(rows) + '\n')
    now = datetime.fromisoformat('2026-11-11T11:21:00+00:00').timestamp()
    os.utime(f, (now - 30, now - 30))        # the file looks fresh: the old check saw 0 min idle
    idle = nudge.idle_minutes(pane, projects, now)
    assert idle == int((now - datetime.fromisoformat('2026-11-08T19:21:00+00:00').timestamp()) / 60)
    assert nudge.decide(idle, False, 'STALLED', 0, now) == 'STALLED on cadence'
    with open(f, 'a') as fh:                  # a peer message or task notification is a real turn
        fh.write(_row('user', '2026-11-11T11:00:00.000Z') + '\n')
    assert nudge.idle_minutes(pane, projects, now) == 21


def test_last_turn_reads_past_a_tail_window_with_no_turn(tmp_path):
    import json
    f = tmp_path / 't.jsonl'
    filler = json.dumps(dict(type='file-history-snapshot', snapshot='y' * 500))
    f.write_text(_row('assistant', '2026-11-10T00:00:00Z') + '\n' + '\n'.join([filler] * 50) + '\n')
    assert nudge.last_turn(f, chunk=1024) is not None
    g = tmp_path / 'none.jsonl'
    g.write_text(filler + '\n')
    assert nudge.last_turn(g, chunk=64) is None


def test_the_nudge_names_the_newest_unrun_digest_idea():
    row = {'digest': {'newest_unrun': {'id': 'abc123', 'claim': 'Run one round as teams of ten agents.'}}}
    assert 'abc123 (Run one round as teams of ten agents.)' in nudge.pickup(row)
    assert nudge.pickup({'digest': None}) == '' and nudge.pickup({}) == '' and nudge.pickup(None) == ''


def test_a_line_separator_inside_the_last_turn_does_not_hide_it(tmp_path):
    import json
    f = tmp_path / 't.jsonl'
    turn = dict(type='assistant', timestamp='2026-11-12T10:00:00Z', message={'role': 'assistant', 'content': 'a b'})
    f.write_text(json.dumps(turn, ensure_ascii=False) + '\n')
    assert nudge.last_turn(f) is not None


def test_a_result_newer_than_the_last_turn_wakes_a_lane_even_with_its_watcher_running():
    """11-12: math's review finished at 16:18Z and the lane sat until 21:05Z. Its watcher shell was
    running (watching the wrong files), and a running shell made the pane look busy, so it was never
    nudged. A result newer than the last turn overrides that, once per file."""
    why = nudge.decide(20, True, 'OK', NOW - 600, NOW, unread='/jobs/math_rev/astra.md')
    assert why and 'astra.md' in why
    assert nudge.decide(20, True, 'OK', NOW - 600, NOW, unread='/jobs/math_rev/astra.md',
                        last_output='/jobs/math_rev/astra.md') is None          # already told about this one
    assert nudge.decide(20, True, 'HELD', 0, NOW, unread='/jobs/x/astra.md') is None   # a paused lane stays paused
    assert nudge.decide(20, True, 'OK', 0, NOW) is None                        # no result: a watcher is busy


def test_unread_output_is_the_newest_settled_result_after_the_last_turn(tmp_path):
    import os
    now = 1_000_000.0
    def make(name, age):
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('x')
        os.utime(f, (now - age, now - age))
        return str(f)
    make('math_a/astra.md', 7200)            # before the last turn: already seen
    want = make('math_b/astra.md', 3000)     # after the last turn, settled
    make('math_c/astra.md', 60)              # still being written
    make('friends_d/astra.md', 3000)         # another lane
    globs = [str(tmp_path / '{lane}_*/astra.md')]
    assert nudge.unread_output(globs, 'math', last_turn=now - 5000, now=now) == want
    assert nudge.unread_output(globs, 'math', last_turn=now - 100, now=now) is None


def test_a_lane_blocked_on_the_owner_is_not_nudged_but_a_result_still_wakes_it(tmp_path):
    """friends, 11-13: blocked on seven owner-only decisions with every job done, and nudged three times in
    a night to keep working on something else."""
    import os
    lane = tmp_path / 'friends'
    lane.mkdir()
    assert nudge.blocked_on(lane, NOW) is None
    (lane / 'BLOCKED').write_text('7 decisions sent to general 05:30 (ricardo channel)\n')
    os.utime(lane / 'BLOCKED', (NOW - 3600, NOW - 3600))
    reason = nudge.blocked_on(lane, NOW)
    assert reason.startswith('7 decisions')
    assert nudge.decide(500, False, 'STALLED', 0, NOW, blocked=reason) is None
    assert nudge.decide(500, False, 'OK', 0, NOW, unread='/jobs/x.last.md', blocked=reason)   # a result still wakes it
    os.utime(lane / 'BLOCKED', (NOW - 13 * 3600, NOW - 13 * 3600))
    assert nudge.blocked_on(lane, NOW) is None                                             # lapses: cannot silence forever


QUIET_NOW = 1795262400.0  # 2026-11-21T12:00Z
FUTURE_QUIET = 'until 2026-11-23T03:00Z by general: Claude conservation\n'


@pytest.fixture
def quiet_lane(tmp_path, monkeypatch):
    lanes = tmp_path / 'lanes'
    lane = lanes / 'games'
    lane.mkdir(parents=True)
    monkeypatch.delenv('RH_LANE_REGISTRY', raising=False)
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.delenv('RSTACK_ABLATE', raising=False)
    monkeypatch.setattr(nudge.sys, 'argv', ['lane-nudge', '--lanes', str(lanes), '--skip', '',
                                           '--state', str(tmp_path / 'state'), '--log', str(tmp_path / 'log'),
                                           '--outputs', str(tmp_path / '{lane}_*.last.md')])
    monkeypatch.setattr(nudge, 'cadence', lambda _: ({'games': {'status': 'STALLED'}}, None))
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('games', '%1', '/work')])
    monkeypatch.setattr(nudge, 'idle_minutes', lambda *_: 120)
    monkeypatch.setattr(nudge, 'time', SimpleNamespace(time=lambda: QUIET_NOW, sleep=lambda *_: None,
                                                       strftime=nudge.time.strftime))
    sends = []

    def tmux(args, **kwargs):
        if args[1] == 'send-keys':
            sends.append(args[-1])
        return SimpleNamespace(stdout='')

    monkeypatch.setattr(nudge.subprocess, 'run', tmux)
    return lane / 'QUIET', sends


def test_future_quiet_skips_idle_nudges_and_logs_once_per_run(quiet_lane, tmp_path, monkeypatch):
    marker, sends = quiet_lane
    marker.write_text(FUTURE_QUIET)
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('games', '%1', '/work'), ('games', '%2', '/work')])
    for _ in range(2):
        nudge.main()
    assert not sends
    lines = (tmp_path / 'log').read_text().splitlines()
    assert len(lines) == 2 and all('QUIET' in line and 'idle nudge skipped' in line for line in lines)
    assert not (tmp_path / 'harness-blocks.jsonl').exists()


@pytest.mark.parametrize('first_line, reason', [
    ('until 2026-11-20T03:00Z by general: Claude conservation\n', 'marker expired'),
    ('until next Monday by general: Claude conservation\n', 'expected until'),
    (None, 'could not read marker'),
])
def test_invalid_quiet_nudges_and_warns_once_per_utc_day(quiet_lane, tmp_path, monkeypatch, first_line, reason):
    marker, sends = quiet_lane
    if first_line is None:
        marker.mkdir()  # opening a directory as a file fails even under elevated privileges
    else:
        marker.write_text(first_line + FUTURE_QUIET)  # a valid second line cannot activate QUIET

    nudge.main()
    assert len(sends) == 2 and 'STALLED on cadence' in sends[0] and sends[1] == 'Enter'
    nudge.main()
    ledger = tmp_path / 'harness-blocks.jsonl'
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == 1
    assert (rows[0]['gate'], rows[0]['class'], rows[0]['outcome'], rows[0]['lane']) == (
        'lane-nudge.quiet', 'fail-open', 'warn', 'games')
    assert reason in rows[0]['reason']
    monkeypatch.setattr(nudge.time, 'time', lambda: QUIET_NOW + 86400)
    nudge.main()
    assert len(ledger.read_text().splitlines()) == 2
    assert marker.exists()


def test_a_fresh_job_output_still_wakes_a_quiet_lane(quiet_lane, tmp_path):
    marker, sends = quiet_lane
    marker.write_text(FUTURE_QUIET)
    result = tmp_path / 'games_round.last.md'
    result.write_text('Finished')
    os.utime(result, (QUIET_NOW - 1800, QUIET_NOW - 1800))
    nudge.main()
    nudge.main()
    assert len(sends) == 2 and nudge.RESULT_MSG.format(lane='games', path=result) == sends[0]
    assert sends[1] == 'Enter'


# ---- 11-23: the weekly-reset wake ------------------------------------------------------------------------------

RESET = 1_800_000_000.0     # a reset on the minute


def reset_args(tmp_path, usage, **kw):
    a = dict(usage=str(usage), reset_skip='', tmux='tmux', prefix='claude-', log=str(tmp_path / 'log'), dry=False)
    a.update(kw)
    return SimpleNamespace(**a)


def write_usage(usage, *resets):
    from datetime import datetime, timezone
    usage.mkdir(parents=True, exist_ok=True)
    iso = [datetime.fromtimestamp(t, timezone.utc).isoformat() for t in resets]
    (usage / 'claude.json').write_text(json.dumps({'weekly_percent': 5.0, 'resets_at': iso[-1]}))
    (usage / 'claude-history.jsonl').write_text(''.join(json.dumps({'resets_at': r}) + '\n' for r in iso[:-1]))


def test_the_reset_that_just_passed_is_known_from_the_next_one_alone(tmp_path):
    write_usage(tmp_path / 'u', RESET + 7 * 86400 - 0.4)              # claude-usage already moved on, jittered
    assert nudge.reset_due(nudge.usage_resets(tmp_path / 'u'), 0, RESET + 600) == RESET
    assert nudge.reset_due({RESET}, 0, RESET + 60) is None              # not before reset + 5 min
    assert nudge.reset_due({RESET}, RESET, RESET + 600) is None         # announced once
    assert nudge.reset_due({RESET}, 0, RESET + 13 * 3600) is None       # 13 h late: not announced


def test_after_the_reset_every_idle_session_is_woken_once_conductor_included(tmp_path, monkeypatch):
    usage, state = tmp_path / 'u', tmp_path / 'state'
    state.mkdir()
    write_usage(usage, RESET, RESET + 7 * 86400)
    registry = SimpleNamespace(lane_of_session=lambda s: s, status=lambda l: 'retired' if l == 'old' else 'active')
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('general', '%1', '/'), ('math', '%2', '/'), ('old', '%3', '/'),
                                                    ('busy', '%4', '/')])
    typed = []

    def run(cmd, **kw):
        if cmd[1] == 'capture-pane':
            return SimpleNamespace(stdout='esc to interrupt' if cmd[4] == '%4' else '> ')
        if '-l' in cmd:
            typed.append((cmd[3], cmd[-1]))
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(nudge.subprocess, 'run', run)
    monkeypatch.setattr(nudge.time, 'sleep', lambda _: None)
    a = reset_args(tmp_path, usage)
    nudge.reset_wake(a, registry, state, RESET - 3600)                  # first run: records, wakes nobody
    assert typed == [] and json.loads((state / 'weekly-reset.json').read_text())['done'] == RESET - 7 * 86400
    nudge.reset_wake(a, registry, state, RESET + 120)                   # too early
    assert typed == []
    nudge.reset_wake(a, registry, state, RESET + 400)
    assert [p for p, _ in typed] == ['%1', '%2'] and 'weekly limit reset' in typed[0][1]
    nudge.reset_wake(a, registry, state, RESET + 2000)                  # once per reset
    assert len(typed) == 2


def test_missing_usage_wakes_nobody_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(nudge, 'panes', lambda *_: pytest.fail('no reset known, no panes read'))
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'weekly-reset.json').write_text(json.dumps({'done': 0}))
    nudge.reset_wake(reset_args(tmp_path, tmp_path / 'nothing'), None, state, RESET)


# ---- 11-24: DRIVER_STATUS.md primary driver routing and fallback -----------------------------------------------

def _driver_env(tmp_path, monkeypatch, status_text, status_age=600, agy_live=True, agy_tail='? for shortcuts',
                claude_idle=120, include_claude=True, status_in_state=False):
    lanes = tmp_path / 'lanes'
    lane = lanes / 'math'
    lane.mkdir(parents=True)
    state = tmp_path / 'state'
    state.mkdir()
    marker = (tmp_path / 'math' / 'DRIVER_STATUS.md') if status_in_state else (lane / 'DRIVER_STATUS.md')
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(status_text)
    os.utime(marker, (NOW - status_age, NOW - status_age))
    monkeypatch.delenv('RH_LANE_REGISTRY', raising=False)
    monkeypatch.setattr(nudge.sys, 'argv', ['lane-nudge', '--lanes', str(lanes), '--skip', '',
                                           '--state', str(state), '--log', str(tmp_path / 'log'),
                                           '--outputs', str(tmp_path / '{lane}_*.last.md')])
    monkeypatch.setattr(nudge, 'cadence', lambda _: ({'math': {'status': 'OK'}}, None))
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('math', '%claude', '/work')] if include_claude else [])
    monkeypatch.setattr(nudge, 'idle_minutes', lambda *_: claude_idle)
    monkeypatch.setattr(nudge, 'time', SimpleNamespace(time=lambda: NOW, sleep=lambda *_: None,
                                                       strftime=nudge.time.strftime))
    sent = []

    def run(cmd, **kw):
        if cmd[1] == 'list-panes':
            return SimpleNamespace(returncode=0 if agy_live else 1, stdout='%agy\n' if agy_live else '')
        if cmd[1] == 'capture-pane':
            return SimpleNamespace(returncode=0, stdout=agy_tail if cmd[4] == '%agy' else '> ')
        if cmd[1] == 'send-keys' and '-l' in cmd:
            sent.append((cmd[3], cmd[-1]))
        return SimpleNamespace(returncode=0, stdout='')

    monkeypatch.setattr(nudge.subprocess, 'run', run)
    return sent, tmp_path


def test_live_driver_handles_results_and_idle_without_waking_claude_fallback(tmp_path, monkeypatch):
    # Output older than DRIVER_STATUS.md mtime (already handled by agy-math): wakes nobody.
    sent, root = _driver_env(tmp_path, monkeypatch, 'Driver: agy-math (Neon), active.\nNeon quota refusals: 0\n',
                             status_age=600)
    old_out = root / 'math_old.last.md'
    old_out.write_text('done')
    os.utime(old_out, (NOW - 1800, NOW - 1800))
    nudge.main()
    assert sent == []

    # Fresh settled output newer than DRIVER_STATUS.md mtime: wakes agy-math, never claude-math.
    os.utime(root / 'lanes/math/DRIVER_STATUS.md', (NOW - 3600, NOW - 3600))
    new_out = root / 'math_new.last.md'
    new_out.write_text('done')
    os.utime(new_out, (NOW - 1200, NOW - 1200))
    nudge.main()
    assert len(sent) == 1 and sent[0][0] == '%agy' and str(new_out) in sent[0][1]


def test_live_driver_busy_indicators_skip_idle_nudge(tmp_path, monkeypatch):
    for tail in ('esc to cancel  auto', '? for shortcuts  1 task(s) /tasks'):
        sent, _ = _driver_env(tmp_path / tail[:3], monkeypatch, 'Driver: agy-math\n',
                              status_age=7200, agy_tail=tail)
        nudge.main()
        assert sent == []


@pytest.mark.parametrize('status_text,agy_live', [
    ('Driver: agy-math (Neon)\n', False),
    ('Driver: agy-math\nStopped: agy hit quota limit, standing down.\n', True),
    ('Driver: agy-math\nPaused on rate limit (429).\n', True),
])
def test_claude_fallback_wakes_only_when_driver_missing_or_quota_stopped(tmp_path, monkeypatch, status_text, agy_live):
    # 11-26: a quota-stopped live driver is first restarted on Claude through agy; this stub's pane never comes
    # back on it, so the respawn fails and the fallback wakes.
    sent, _ = _driver_env(tmp_path, monkeypatch, status_text, status_age=600, agy_live=agy_live, claude_idle=120)
    nudge.main()
    assert len(sent) == 1 and sent[0][0] == '%claude'


def test_standalone_driver_and_state_dir_driver_status_work(tmp_path, monkeypatch):
    sent, _ = _driver_env(tmp_path / 'a', monkeypatch, 'Updated: (driver: agy-math / Neon)\n',
                          status_age=7200, include_claude=False)
    nudge.main()
    assert len(sent) == 1 and sent[0][0] == '%agy'

    sent2, _ = _driver_env(tmp_path / 'b', monkeypatch, 'Driver: agy-math (Neon)\n',
                           status_age=7200, status_in_state=True)
    nudge.main()
    assert len(sent2) == 1 and sent2[0][0] == '%agy'


def test_reset_wake_skips_claude_fallback_when_driver_is_live(tmp_path, monkeypatch):
    usage, state, lanes = tmp_path / 'u', tmp_path / 'state', tmp_path / 'lanes'
    state.mkdir()
    (lanes / 'math').mkdir(parents=True)
    (lanes / 'math/DRIVER_STATUS.md').write_text('Driver: agy-math (Neon)\n')
    write_usage(usage, RESET, RESET + 7 * 86400)
    registry = SimpleNamespace(lane_of_session=lambda s: s, status=lambda l: 'active')
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('general', '%1', '/'), ('math', '%2', '/')])
    typed = []

    def run(cmd, **kw):
        if cmd[1] == 'list-panes':
            return SimpleNamespace(returncode=0, stdout='%agy\n')
        if cmd[1] == 'capture-pane':
            return SimpleNamespace(returncode=0, stdout='> ')
        if '-l' in cmd:
            typed.append(cmd[3])
        return SimpleNamespace(returncode=0, stdout='')

    monkeypatch.setattr(nudge.subprocess, 'run', run)
    monkeypatch.setattr(nudge.time, 'sleep', lambda _: None)
    (state / 'weekly-reset.json').write_text(json.dumps({'done': RESET - 7 * 86400}))
    nudge.reset_wake(reset_args(tmp_path, usage, lanes=str(lanes)), registry, state, RESET + 400)
    assert typed == ['%1']


def test_nameless_driver_status_defaults_to_agy_lane_and_wakes_it_not_claude(tmp_path, monkeypatch):
    # 11-25: agy-math rewrote DRIVER_STATUS.md without naming agy-math, so lane-nudge woke claude-math.
    seen_targets = []
    sent, _ = _driver_env(tmp_path, monkeypatch, 'Running: sweep 1 on m5.\nNext: check results.\n',
                          status_age=7200, agy_live=True, claude_idle=120)
    orig_run = nudge.subprocess.run

    def spy(cmd, **kw):
        if cmd[1] == 'list-panes':
            seen_targets.append(cmd[3])
        return orig_run(cmd, **kw)

    monkeypatch.setattr(nudge.subprocess, 'run', spy)
    nudge.main()
    assert set(seen_targets) == {'=agy-math'}
    assert len(sent) == 1 and sent[0][0] == '%agy'


# ---- 11-26: a Gemini quota stop moves the agy driver onto Claude through agy, and back after the reset ----------

QUOTA_SCREEN = ('  Started the sweep.\n'
                '⚠ Individual quota reached. Please upgrade your subscription to increase your\n'
                'limits. Resets in 2h0m0s.\nError ID: fixture\n' + '─' * 40 + '\n>\n' + '─' * 40 + '\n'
                '? for shortcuts                       auto · {model} · high\n')
IDLE_SCREEN = '  ok\n' + '─' * 40 + '\n>\n' + '─' * 40 + '\n? for shortcuts            auto · {model} · high\n'
SHOWN = {'gemini-4-neon': 'Gemini 4 Neon', 'claude-opus-5-5-high': 'Claude Opus 5.5'}


def _agy_env(tmp_path, monkeypatch, screen, model='gemini-4-neon', respawn_ok=True, comes_up_on=None):
    lanes = tmp_path / 'lanes'
    (lanes / 'math').mkdir(parents=True)
    state = tmp_path / 'state'
    state.mkdir()
    (lanes / 'math/DRIVER_STATUS.md').write_text('Driver: agy-math\n')
    os.utime(lanes / 'math/DRIVER_STATUS.md', (NOW - 600, NOW - 600))
    monkeypatch.delenv('RH_LANE_REGISTRY', raising=False)
    monkeypatch.setenv('RH_MODEL_RUNS_LOG', str(tmp_path / 'model-runs.jsonl'))
    monkeypatch.setattr(nudge.sys, 'argv', ['lane-nudge', '--lanes', str(lanes), '--skip', '', '--state', str(state),
                                           '--log', str(tmp_path / 'log'), '--agy', '/bin/agy'])
    monkeypatch.setattr(nudge, 'cadence', lambda _: ({'math': {'status': 'OK'}}, None))
    monkeypatch.setattr(nudge, 'panes', lambda *_: [('math', '%claude', '/work')])
    monkeypatch.setattr(nudge, 'idle_minutes', lambda *_: 120)
    clock = SimpleNamespace(now=NOW)
    monkeypatch.setattr(nudge, 'time', SimpleNamespace(time=lambda: clock.now, sleep=lambda *_: None,
                                                       strftime=nudge.time.strftime))
    pane = {'model': model, 'screen': screen.format(model=SHOWN[model]), 'start': f'agy --model {model} --effort high'}
    log = SimpleNamespace(respawns=[], sent=[])

    def run(cmd, **kw):
        out = ''
        if cmd[1] == 'list-panes':
            out = '%agy\n'
        elif cmd[1] == 'display-message':
            out = '{}\t/work/math\t4242\n'.format(pane['start'])
        elif cmd[1] == 'capture-pane':
            out = pane['screen'] if cmd[4] == '%agy' else '> '
        elif cmd[0].endswith('lsof'):
            out = 'p4242\nn/x/conversations/0a1b2c3d-0000-4000-8000-000000000001.db\n'
        elif cmd[1] == 'respawn-pane':
            log.respawns.append(cmd[-1])
            if not respawn_ok:
                return SimpleNamespace(returncode=1, stdout='')
            new = comes_up_on or cmd[-1].split('--model ')[1].split()[0]
            pane.update(model=new, start=cmd[-1], screen=IDLE_SCREEN.format(model=SHOWN.get(new, new)))
        elif cmd[1] == 'send-keys' and '-l' in cmd:
            log.sent.append((cmd[3], cmd[-1]))
        return SimpleNamespace(returncode=0, stdout=out)

    monkeypatch.setattr(nudge.subprocess, 'run', run)
    monkeypatch.setattr(nudge, 'tell_session', lambda: None)
    return log, pane, clock, state


def test_a_gemini_quota_pane_moves_to_claude_through_agy_and_wakes_no_fallback(tmp_path, monkeypatch):
    log, pane, clock, state = _agy_env(tmp_path, monkeypatch, QUOTA_SCREEN)
    nudge.main()
    assert len(log.respawns) == 1
    assert '--model claude-opus-5-5-high' in log.respawns[0]
    assert '--conversation 0a1b2c3d-0000-4000-8000-000000000001' in log.respawns[0]
    assert [p for p, _ in log.sent] == ['%agy'] and 'now on Claude Opus 5.5 through agy' in log.sent[0][1]
    saved = json.loads((state / 'agy-math.agy-switch.json').read_text())
    assert (saved['to'], saved['from'], saved['reset']) == ('claude-opus-5-5-high', 'gemini-4-neon', NOW + 7200)
    hit, = [json.loads(ln) for ln in (tmp_path / 'quota-hits.jsonl').read_text().splitlines()]
    assert (hit['model'], hit['lane']) == ('google/gemini-4-neon-high', 'math') and hit['reset_time']
    assert 'switching to claude-opus-5-5-high' in (tmp_path / 'log').read_text()
    nudge.main()                                     # on Claude now: no second respawn, the driver stays primary
    assert len(log.respawns) == 1


def test_a_pane_already_on_claude_is_not_respawned(tmp_path, monkeypatch):
    log, *_ = _agy_env(tmp_path, monkeypatch, IDLE_SCREEN, model='claude-opus-5-5-high')
    nudge.main()
    assert log.respawns == []
    log, *_ = _agy_env(tmp_path / 'b', monkeypatch, QUOTA_SCREEN, model='claude-opus-5-5-high')
    nudge.main()                                     # the Claude group is out too: the fallback is woken
    assert log.respawns == [] and [p for p, _ in log.sent] == ['%claude']


@pytest.mark.parametrize('respawn_ok,comes_up_on', [(False, None), (True, 'gemini-4-neon')])
def test_a_failed_respawn_wakes_the_claude_fallback(tmp_path, monkeypatch, respawn_ok, comes_up_on):
    log, *_ = _agy_env(tmp_path, monkeypatch, QUOTA_SCREEN, respawn_ok=respawn_ok, comes_up_on=comes_up_on)
    nudge.main()
    assert len(log.respawns) == 1 and [p for p, _ in log.sent] == ['%claude']
    assert 'failed; waking the Claude fallback' in (tmp_path / 'log').read_text()


def test_the_driver_switches_back_to_its_model_after_the_reset(tmp_path, monkeypatch):
    log, pane, clock, state = _agy_env(tmp_path, monkeypatch, QUOTA_SCREEN)
    nudge.main()
    pane['screen'] = QUOTA_SCREEN.format(model='Claude Opus 5.5').replace('Individual quota reached', 'Done')
    clock.now = NOW + 3600                           # before the reset: stays on Claude
    nudge.main()
    assert len(log.respawns) == 1
    clock.now = NOW + 7200 + 60
    nudge.main()
    assert len(log.respawns) == 2 and '--model gemini-4-neon --effort high' in log.respawns[1]
    assert 'back on gemini-4-neon' in log.sent[-1][1]
    assert json.loads((state / 'agy-math.agy-switch.json').read_text())['to'] is None
    nudge.main()                                     # the old quota line is gone from above the prompt: no flapping
    assert len(log.respawns) == 2


def test_the_quota_line_is_read_only_above_the_prompt():
    old = QUOTA_SCREEN.format(model='Gemini 4 Neon').replace('Error ID: fixture\n', 'Error ID: fixture\n  ok\n  a\n'
                                                              '  b\n  c\n  d\n  e\n  f\n')
    assert not nudge.AGY_QUOTA.search(nudge.above_prompt(old))
    assert nudge.AGY_QUOTA.search(nudge.above_prompt(QUOTA_SCREEN.format(model='Gemini 4 Neon')))
    assert not nudge.AGY_QUOTA.search('Weekly quota · Refreshes in 3d 3h 59m')
    assert nudge.shown_model('? for shortcuts   auto · Claude Opus 5.5 · high · 1 task(s)') == 'Claude Opus 5.5'


def test_the_conversation_comes_from_the_open_db_else_the_process_log(tmp_path, monkeypatch):
    log = tmp_path / 'log/cli-20261126_171828.log'
    log.parent.mkdir()
    log.write_text('conversation=11111111-0000-4000-8000-000000000000 listed\n'
                   'I1126 manager.go] cascade_id:22222222-0000-4000-8000-000000000000\n')
    outs = {'db': 'p1\nn/x/conversations/33333333-0000-4000-8000-000000000000.db\nn{}\n'.format(log),
            'log': 'p1\nn{}\nn/x/conversations\n'.format(log)}
    for kind, want in (('db', '33333333'), ('log', '22222222')):
        monkeypatch.setattr(nudge.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=outs[kind]))
        assert nudge.conversation_of('1').startswith(want)
    assert nudge.conversation_of('') is None
