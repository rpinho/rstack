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
