"""cs.py never waits forever on Claude Science (planets, 11-11 on the m5: ask and reply hung three
times, once for 12 h, with no frame created, and an immediate retry went through in seconds), and a
retry never starts a second session for a request that did land."""
import io
import json
from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cs


class Reply(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def daemon(monkeypatch):
    """A daemon stub. `answers` maps a path prefix to a list of replies, one per request: None hangs
    (the opener times out), a str is the body. Records (method, path, timeout) for each request."""
    seen = []

    def start(answers):
        def open_(req, timeout=None):
            path = req.full_url.split('127.0.0.1', 1)[1]
            seen.append((req.get_method(), path, timeout))
            key = next(k for k in answers if path.startswith(k))
            answer = answers[key].pop(0)
            if answer is None:
                raise socket.timeout('timed out')
            return Reply(answer.encode())
        monkeypatch.setattr(cs.opener, 'open', open_)
        return seen
    monkeypatch.setattr(cs, 'REQUEST_TIMEOUT', 7.0)
    monkeypatch.setattr(cs, 'save', lambda: None)
    monkeypatch.setattr(cs, 'origin', lambda: 'http://127.0.0.1')
    monkeypatch.setattr(cs, 'base', lambda: 'http://127.0.0.1')
    return start


def frames(*rows, messages=None):
    messages = messages or {}
    return json.dumps([dict(id=i, root_frame_id=root, parent_frame_id=parent, status='running',
                            message_count=messages.get(i, 2), created_at='2026-11-12T00:00:0{}Z'.format(n))
                       for n, (i, root, parent) in enumerate(rows)])


ASK = {'project_id': 'p1', 'input_data': {'request': 'x'}}
OLD = ('F1', 'F1', None)


def test_every_request_is_opened_with_a_timeout(daemon):
    seen = daemon({'/api/me': ['{"ok": 1}']})
    assert cs.call('/api/me') == (200, '{"ok": 1}')
    assert seen == [('GET', '/api/me', 7.0)]


def test_a_get_that_hangs_is_retried_and_then_answers(daemon):
    seen = daemon({'/api/frames/f1': [None, '{"status": "idle"}']})
    assert cs.call('/api/frames/f1') == (200, '{"status": "idle"}')
    assert [s[:2] for s in seen] == [('GET', '/api/frames/f1')] * 2


def test_a_get_that_never_answers_raises_instead_of_hanging(daemon):
    seen = daemon({'/api/me': [None, None, None]})
    with pytest.raises(cs.CSTimeout):
        cs.call('/api/me')
    assert len(seen) == 3


def test_an_ask_that_hung_without_a_frame_is_sent_once_more(daemon, capsys):
    seen = daemon({'/api/frames?': [frames(OLD), frames(OLD)], '/api/request': [None, '{"root_frame_id": "F2"}']})
    assert cs.post(ASK, sleep=lambda s: None) == {'root_frame_id': 'F2'}
    assert [s[:2] for s in seen if s[0] == 'POST'] == [('POST', '/api/request')] * 2
    assert 'no frame was created; sending once more' in capsys.readouterr().err


def test_an_ask_that_timed_out_but_landed_is_not_sent_again(daemon, capsys):
    seen = daemon({'/api/frames?': [frames(OLD), frames(OLD, ('F2', 'F2', None))], '/api/request': [None]})
    assert cs.post(ASK, sleep=lambda s: None) == {'root_frame_id': 'F2', 'frame_id': 'F2', 'status': 'running'}
    assert sum(1 for s in seen if s[0] == 'POST') == 1
    assert 'frame F2 was created; not resending' in capsys.readouterr().err


def test_a_reply_that_landed_shows_as_more_messages_in_its_conversation(daemon, capsys):
    """The live listing shows root frames only (11-12), so a landed reply is a message-count rise."""
    reply = dict(ASK, root_frame_id='F1')
    seen = daemon({'/api/frames?': [frames(OLD), frames(OLD, messages={'F1': 3})], '/api/request': [None]})
    assert cs.post(reply, sleep=lambda s: None)['frame_id'] == 'F1'
    assert sum(1 for s in seen if s[0] == 'POST') == 1
    reply_seen = daemon({'/api/frames?': [frames(OLD), frames(OLD)], '/api/request': [None, '{"status": "ok"}']})
    assert cs.post(reply, sleep=lambda s: None) == {'status': 'ok'}       # no new message: resent once


def test_a_reply_that_landed_is_found_in_its_own_conversation(daemon):
    reply = dict(ASK, root_frame_id='F1')
    daemon({'/api/frames?': [frames(OLD), frames(OLD, ('X9', 'OTHER', None), ('R2', 'F1', 'F1'))],
            '/api/request': [None]})
    assert cs.post(reply, sleep=lambda s: None)['frame_id'] == 'R2'


def test_a_timeout_with_unreadable_frames_stops_instead_of_resending_blind(daemon):
    seen = daemon({'/api/frames?': [frames(OLD), None, None, None], '/api/request': [None]})
    with pytest.raises(SystemExit) as e:
        cs.post(ASK, sleep=lambda s: None)
    assert 'not resending blind' in str(e.value)
    assert sum(1 for s in seen if s[0] == 'POST') == 1


def test_an_ask_that_hangs_twice_exits_with_a_reason(daemon):
    seen = daemon({'/api/frames?': [frames(OLD), frames(OLD)], '/api/request': [None, None]})
    with pytest.raises(SystemExit) as e:
        cs.post(ASK, sleep=lambda s: None)
    assert 'did not answer twice' in str(e.value)
    assert sum(1 for s in seen if s[0] == 'POST') == 2
