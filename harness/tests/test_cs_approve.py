"""What cs.py approves by itself, and with which scope.

11-07, math: a Claude Science network approval sent with scope 'conversation' returns 200
"accepted" and changes nothing, so the session parks forever (C47 session 6660b62e sat on
annals.math.princeton.edu until it was resolved by hand). A 200 that does nothing is the worst
kind of answer, so cs.py sends the scope the API requires rather than relaying one that will be
silently dropped.

The other half of these tests is the line that must NOT move: network, spend and credential
requests wait for a person. cs.py approves local compute, and read-only host reads under an
explicit CS_AUTO_READ allowlist, and nothing else.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cs


def req(kind, **extra):
    row = dict(requestId='r-' + kind, kind=kind, tool_id='t-' + kind, tool=kind)
    row.update(extra)
    return row


@pytest.fixture
def api(monkeypatch):
    """A daemon stub: records the resolve-input payload, and CLEARS what it granted.

    Clearing matters. approve() now reads the requests back and refuses to report success for one
    that is still pending, so a stub that never clears would fail every test for the right reason
    and teach nothing. A stub that cannot succeed is as useless as one that cannot fail.
    """
    sent = {}
    granted = set()

    def call(path, data=None, form=False):
        if path.endswith('/resolve-input'):
            sent['payload'] = data
            granted.update(r['requestId'] for r in data['responses'])
            return 200, '{"status": "accepted"}'
        raise AssertionError('unexpected call: ' + path)

    def queue(rows):
        monkeypatch.setattr(cs, 'pending',
                            lambda fid: [r for r in rows if r['requestId'] not in granted])

    monkeypatch.setattr(cs, 'call', call)
    sent['queue'] = queue
    sent['granted'] = granted
    return sent


def test_a_network_approval_is_sent_with_the_scope_the_api_requires(api, monkeypatch):
    """The 11-07 bug. If a network request ever reaches resolve-input, 'conversation' is a no-op."""
    monkeypatch.setattr(cs, 'AUTO_APPROVE', {'local_exec', 'network'})
    api['queue']([req('network', target='annals.math.princeton.edu')])
    cs.approve('f1', scope='conversation')
    response = api['payload']['responses'][0]
    assert response['scope'] == 'always', 'conversation returns 200 and changes nothing'
    assert response['action'] == 'allow' and response['approved'] is True


def test_other_kinds_keep_the_scope_they_were_given(api, monkeypatch):
    api['queue']([req('local_exec', code='print(1)')])
    cs.approve('f1', scope='conversation')
    assert api['payload']['responses'][0]['scope'] == 'conversation'
    api['granted'].clear()
    cs.approve('f1', scope='always')
    assert api['payload']['responses'][0]['scope'] == 'always'


def test_network_is_not_approved_by_this_tool_at_all(monkeypatch):
    """The line that must not move. Network, spend and credential requests wait for a person; this
    is the Spend rule, not an oversight, and a lane asking for it to be automatic does not change
    it. The scope fix above is about what happens when a PERSON allows one."""
    monkeypatch.setattr(cs, 'pending', lambda fid: [req('network', target='example.org')])
    monkeypatch.setattr(cs, 'call', lambda *a, **k: pytest.fail('approved a network request'))
    ok, held = cs.approve('f1')
    assert ok == []
    assert [r['kind'] for r in held] == ['network']


def test_local_compute_is_the_only_automatic_kind(monkeypatch):
    assert cs.AUTO_APPROVE == {'local_exec'}
    assert 'network' in cs.SCOPE_ALWAYS


def test_a_usage_checkpoint_at_a_boundary_still_waits(monkeypatch):
    """Approaching a limit cannot bill; reaching it draws credits, so that one is a person's."""
    monkeypatch.setattr(cs, 'pending', lambda fid: [req('usage_checkpoint', boundary='overage')])
    monkeypatch.setattr(cs, 'call', lambda *a, **k: pytest.fail('approved an overage checkpoint'))
    ok, held = cs.approve('f1')
    assert ok == [] and held and held[0]['boundary'] == 'overage'


def test_a_read_only_host_request_needs_the_explicit_allowlist(monkeypatch, tmp_path):
    inside = tmp_path / 'papers'
    inside.mkdir()
    monkeypatch.setattr(cs, 'AUTO_READ', (str(tmp_path) + '/',))
    sent = {}
    granted = set()

    def call(path, data=None, form=False):
        sent['d'] = data
        granted.update(r['requestId'] for r in data['responses'])
        return 200, '{}'

    rows = [req('host', requested_mode='ro', target=str(inside))]
    monkeypatch.setattr(cs, 'call', call)
    monkeypatch.setattr(cs, 'pending',
                        lambda fid: [r for r in rows if r['requestId'] not in granted])
    ok, _ = cs.approve('f1')
    assert [r['kind'] for r in ok] == ['host']
    assert sent['d']['responses'][0]['mode'] == 'ro'
    # Outside the allowlist it waits, and a write mode always waits.
    monkeypatch.setattr(cs, 'pending', lambda fid: [req('host', requested_mode='ro', target='/etc')])
    monkeypatch.setattr(cs, 'call', lambda *a, **k: pytest.fail('read outside the allowlist'))
    assert cs.approve('f1')[0] == []
    monkeypatch.setattr(cs, 'pending',
                        lambda fid: [req('host', requested_mode='rw', target=str(inside))])
    assert cs.approve('f1')[0] == []


def test_a_200_that_changed_nothing_is_a_loud_failure(monkeypatch, capsys):
    """11-07, twice in one evening: math's network approval and planets' host prompts both came
    back "accepted" and changed nothing, and the session then sat pending with nothing saying why.
    Whatever the cause, reporting success for a request nobody granted is the failure direction
    that wastes a whole session, so the requests are read back."""
    row = req('local_exec', code='print(1)')
    monkeypatch.setattr(cs, 'pending', lambda fid: [row])      # never clears: the daemon ignored it
    monkeypatch.setattr(cs, 'call', lambda *a, **k: (200, '{"status": "accepted"}'))
    with pytest.raises(SystemExit) as e:
        cs.approve('f1', scope='conversation')
    message = str(e.value)
    assert 'returned 200 and changed nothing' in message
    assert 'local_exec' in message and "'conversation'" in message
    assert 'Nothing was approved' in message
