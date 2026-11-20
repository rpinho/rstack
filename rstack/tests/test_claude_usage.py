"""claude-usage: the scheduled Claude usage reader (11-20). Offline: the endpoint and Keychain are stubbed."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
from pathlib import Path
import urllib.error

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'claude-usage'
_spec = spec_from_loader('claude_usage', SourceFileLoader('claude_usage', str(TOOL)))
cu = module_from_spec(_spec)
_spec.loader.exec_module(cu)

BODY = {'five_hour': None,
        'seven_day': {'utilization': 24.0, 'resets_at': '2026-11-23T03:00:00.240302+00:00'}}
SECRET = 'placeholder-oauth-value'


def test_the_weekly_and_five_hour_windows_are_recorded_with_the_method():
    rec = cu.reading(BODY, 1795177822)
    assert rec['weekly_percent'] == 24.0 and rec['at'] == 1795177822
    assert rec['resets_at'].startswith('2026-11-23T03:00:00') and 'oauth/usage' in rec['source']
    assert 'five_hour_percent' not in rec   # the account reports no five-hour window right now
    rec = cu.reading(dict(BODY, five_hour={'utilization': 61, 'resets_at': '2026-11-20T17:00:00Z'}), 1)
    assert rec['five_hour_percent'] == 61.0 and rec['five_hour_resets_at'].startswith('2026-11-20T17:00:00')


def test_the_token_goes_in_a_header_and_never_into_an_error():
    seen = {}

    def opener(req, timeout):
        seen['auth'] = req.get_header('Authorization')
        return io.BytesIO(json.dumps(BODY).encode())
    assert cu.fetch(lambda: SECRET, opener)['seven_day']['utilization'] == 24.0
    assert seen['auth'] == 'Bearer ' + SECRET

    def refused(req, timeout):
        raise urllib.error.HTTPError(cu.URL, 401, 'Unauthorized', {}, None)
    rec, row = cu.run(now=1, fetcher=lambda: cu.fetch(lambda: SECRET, refused))
    assert rec is None and 'HTTP 401' in row and SECRET not in row


def test_a_failed_read_keeps_the_last_reading_writes_an_alert_row_and_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('RSTACK_HOST', 'm5')
    monkeypatch.setattr(cu, 'fetch', lambda: BODY)
    assert cu.main([]) == 0
    usage, alert = tmp_path / 'usage/claude.json', tmp_path / 'asks-waiting/m5-claude-usage.tsv'
    first = json.loads(usage.read_text())
    assert first['weekly_percent'] == 24.0 and alert.read_text() == ''

    def broken():
        raise cu.Failure('usage body has no seven_day.utilization (the endpoint may have changed)')
    monkeypatch.setattr(cu, 'fetch', broken)
    assert cu.main([]) == 1
    assert json.loads(usage.read_text()) == first     # never overwritten with a guess
    row = alert.read_text().split('\t')
    assert row[1] == 'claude-usage' and 'seven_day.utilization' in row[2] and 'unknown' in row[2]
    monkeypatch.setattr(cu, 'fetch', lambda: BODY)
    assert cu.main([]) == 0 and alert.read_text() == ''   # cleared once it reads again
