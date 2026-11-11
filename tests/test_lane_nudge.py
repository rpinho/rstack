"""lane-nudge decides from idle time, running state, cadence status and its own rate limit."""
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
nudge = SourceFileLoader('lane_nudge', str(REPO / 'harness/tools/lane-nudge/lane-nudge')).load_module()
NOW = 1_000_000.0


def test_quiet_lane_with_nothing_running_is_nudged():
    assert nudge.decide(90, False, 'OK', 0, NOW) == 'quiet'


def test_cadence_behind_is_named():
    assert nudge.decide(61, False, 'STALLED', 0, NOW) == 'STALLED on cadence'


def test_running_work_or_recent_turn_is_left_alone():
    assert nudge.decide(500, True, 'STALLED', 0, NOW) is None
    assert nudge.decide(59, False, 'WARN', 0, NOW) is None


def test_rate_limited_per_lane():
    assert nudge.decide(500, False, 'WARN', NOW - 3600, NOW) is None
    assert nudge.decide(500, False, 'WARN', NOW - 7201, NOW) == 'WARN on cadence'


def test_exempt_and_unconfigured_never_nudged():
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
