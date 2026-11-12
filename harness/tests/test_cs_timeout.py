"""cs.py never waits forever on Claude Science (planets, 11-11 on the m5: ask and reply hung three
times, once for 12 h, with no frame created, and an immediate retry went through in seconds)."""
import io
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
    """A daemon stub that, per request, hangs (None: the opener times out) or answers with a body.
    Records each request's method, path and the timeout it was opened with."""
    seen = []

    def start(answers):
        answers = list(answers)

        def open_(req, timeout=None):
            seen.append((req.get_method(), req.full_url.split('127.0.0.1', 1)[1], timeout))
            answer = answers.pop(0)
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


def test_every_request_is_opened_with_a_timeout(daemon):
    seen = daemon(['{"ok": 1}'])
    assert cs.call('/api/me') == (200, '{"ok": 1}')
    assert seen == [('GET', '/api/me', 7.0)]


def test_a_get_that_hangs_is_retried_and_then_answers(daemon):
    seen = daemon([None, '{"status": "idle"}'])
    assert cs.call('/api/frames/f1') == (200, '{"status": "idle"}')
    assert [s[:2] for s in seen] == [('GET', '/api/frames/f1')] * 2


def test_a_get_that_never_answers_raises_instead_of_hanging(daemon):
    seen = daemon([None, None, None])
    with pytest.raises(cs.CSTimeout):
        cs.call('/api/me')
    assert len(seen) == 3


def test_an_ask_that_hangs_is_sent_once_more(daemon, capsys):
    seen = daemon([None, '{"root_frame_id": "F2"}'])
    assert cs.post({'input_data': {'request': 'x'}}) == {'root_frame_id': 'F2'}
    assert [s[:2] for s in seen] == [('POST', '/api/request')] * 2
    assert 'sending once more' in capsys.readouterr().err


def test_an_ask_that_hangs_twice_exits_with_a_reason(daemon):
    seen = daemon([None, None])
    with pytest.raises(SystemExit) as e:
        cs.post({'input_data': {'request': 'x'}})
    assert 'did not answer twice' in str(e.value) and len(seen) == 2
