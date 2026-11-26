"""tell-session against a fake tmux on PATH that records calls and plays back canned panes."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'rstack/tools/tell-session'
loader = importlib.machinery.SourceFileLoader('tell_session', str(TOOL))
spec = importlib.util.spec_from_loader('tell_session', loader)
ts = importlib.util.module_from_spec(spec)
loader.exec_module(ts)

STUB = '''#!{py}
import json, os, sys
d = os.environ['FAKE_TMUX_DIR']
with open(os.path.join(d, 'calls.jsonl'), 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'capture-pane':
    screens = json.load(open(os.path.join(d, 'screens.json')))
    n_path = os.path.join(d, 'n')
    n = int(open(n_path).read()) if os.path.exists(n_path) else 0
    open(n_path, 'w').write(str(n + 1))
    sys.stdout.write(screens[min(n, len(screens) - 1)])
'''

TEXT = 'Harness check: a job result for lane math landed, read it now'
IDLE = 'some reply\n╭────────╮\n│ >      │\n╰────────╯\n  ? for shortcuts\n'
STUCK = 'some reply\n╭────────╮\n│ > ' + TEXT[:40] + ' │\n╰────────╯\n'


@pytest.fixture
def fake(tmp_path, monkeypatch):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    stub = bindir / 'tmux'
    stub.write_text(STUB.format(py=sys.executable))
    stub.chmod(0o755)
    monkeypatch.setenv('HOME', str(tmp_path))  # no ~/.local/bin/tmux: the stub on PATH is used
    monkeypatch.setenv('PATH', f'{bindir}{os.pathsep}{os.environ["PATH"]}')
    monkeypatch.setenv('FAKE_TMUX_DIR', str(tmp_path))

    def play(*screens):
        (tmp_path / 'screens.json').write_text(json.dumps(list(screens)))
        return lambda: [json.loads(ln) for ln in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    return play


def tell(target='claude-general', text=TEXT):
    return ts.tell(target, text, sleep=lambda _: None)


def sends(calls):
    return [c for c in calls if c[0] == 'send-keys']


def test_text_and_enter_go_as_separate_calls_and_a_cleared_box_confirms(fake):
    calls = fake(IDLE, STUCK, IDLE)
    code, msg = tell()
    assert code == 0, msg
    assert sends(calls()) == [['send-keys', '-t', '=claude-general:', '-l', '--', TEXT],
                              ['send-keys', '-t', '=claude-general:', 'Enter']]


def test_cli_confirms_and_exits_zero(fake):
    fake(IDLE)
    r = subprocess.run([sys.executable, str(TOOL), '%3', TEXT], capture_output=True, text=True)
    assert r.returncode == 0 and 'submitted to %3' in r.stdout


def test_stuck_text_gets_one_more_enter(fake):
    calls = fake(IDLE, *[STUCK] * 8, IDLE)
    code, msg = tell()
    assert code == 0, msg
    assert [c[-1] for c in sends(calls())] == [TEXT, 'Enter', 'Enter']


def test_newly_working_session_counts_as_submitted(fake):
    fake(IDLE, STUCK + '✻ Thinking… (esc to interrupt)\n')
    assert tell()[0] == 0


@pytest.mark.parametrize('screen', [
    'How was this session?\n[0] Skip  [1] Bad  [2] Good\n',
    'Resume previous chat?\n  c continue   n start fresh\n',
    'Do you want to proceed?\n❯ 1. Yes\n  2. No\n',
    'Overwrite file? (y/n)\n',
])
def test_one_key_menu_is_refused_and_nothing_is_typed(fake, screen):
    calls = fake(screen)
    code, msg = tell()
    assert code == 2 and 'nothing sent' in msg
    assert sends(calls()) == []


def test_text_that_never_leaves_the_box_exits_nonzero_with_the_pane(fake):
    calls = fake(IDLE, STUCK)
    code, msg = tell()
    assert code == 1 and TEXT[:40] in msg
    assert [c[-1] for c in sends(calls())] == [TEXT, 'Enter', 'Enter']


def test_missing_session_is_an_error_not_a_send():
    code, msg = ts.tell('nope', TEXT, run=lambda *a, **k: subprocess.CompletedProcess(a, 1, '', ''),
                        sleep=lambda _: None)
    assert code == 2 and 'nothing sent' in msg
