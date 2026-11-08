"""fleet-context-watch: ask at the threshold, compact after a SAVED reply, never miss a buried one."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools/fleet-context-watch'
loader = importlib.machinery.SourceFileLoader('fleet_context_watch', str(TOOL))
spec = importlib.util.spec_from_loader('fleet_context_watch', loader)
fcw = importlib.util.module_from_spec(spec)
loader.exec_module(fcw)

T0 = 1_800_000_000.0   # the request
CFG = fcw.settings({})


def iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def turn(t, text, tokens=520_000):
    return json.dumps(dict(type='assistant', timestamp=iso(t), message=dict(
        usage=dict(input_tokens=10, cache_read_input_tokens=tokens - 10, cache_creation_input_tokens=0),
        content=[dict(type='text', text=text)])))


def transcript(tmp_path, *turns, name='t.jsonl'):
    p = tmp_path / name
    p.write_text('\n'.join(turns) + '\n')
    return p


def test_a_saved_reply_buried_by_a_later_reply_still_compacts(tmp_path):
    """The 11-08 bug: SAVED, then something woke the session and a newer reply buried it."""
    f = transcript(tmp_path, turn(T0 - 600, 'working'), turn(T0 + 30, 'SAVED /state/handoff.md'),
                   turn(T0 + 300, 'A monitor fired; the job is still running.'))
    size, saved = fcw.read_transcript(f)
    assert size == 520_000 and saved[0] == 'SAVED /state/handoff.md'
    action, state = fcw.decide({'stage': 'asked', 'at': T0}, size, saved, quiet=600, now=T0 + 900, cfg=CFG)
    assert action == 'compact' and state['path'] == '/state/handoff.md'


def test_a_saved_reply_from_before_the_request_does_not_count():
    action, _ = fcw.decide({'stage': 'asked', 'at': T0}, 520_000, ('SAVED /old.md', T0 - 3600),
                           quiet=600, now=T0 + 900, cfg=CFG)
    assert action is None


def test_it_waits_for_the_session_to_go_quiet():
    action, _ = fcw.decide({'stage': 'asked', 'at': T0}, 520_000, ('SAVED /s.md', T0 + 30),
                           quiet=30, now=T0 + 60, cfg=CFG)
    assert action is None


@pytest.mark.parametrize('state, size, now, expect', [
    ({}, 520_000, T0, 'ask'),                                            # over the threshold
    ({}, 450_000, T0, None),                                             # under it
    ({'stage': 'asked', 'at': T0}, 520_000, T0 + 600, None),             # asked, no SAVED yet
    ({'stage': 'asked', 'at': T0}, 520_000, T0 + 7300, 'ask'),           # no SAVED in two hours: ask again
    ({'stage': 'compacted', 'at': T0}, 520_000, T0 + 600, None),         # just compacted: leave it
    ({'stage': 'compacted', 'at': T0}, 520_000, T0 + 7300, 'ask'),       # still big hours later
    ({'stage': 'compacted', 'at': T0}, 120_000, T0 + 600, 'reset'),      # it worked
])
def test_the_stages(state, size, now, expect):
    assert fcw.decide(state, size, ('', 0.0), quiet=600, now=now, cfg=CFG)[0] == expect


@pytest.fixture
def fleet(tmp_path):
    """A fake tmux with two sessions (one on the skip list) and their transcripts."""
    work = tmp_path / 'work'
    work.mkdir()
    projects = tmp_path / 'projects'
    folder = projects / str(work).replace('/', '-').replace('.', '-')
    folder.mkdir(parents=True)
    keys = tmp_path / 'keys.log'
    tmux = tmp_path / 'tmux'
    tmux.write_text('#!/bin/sh\nif [ "$1" = list-panes ]; then\n'
                    'printf "claude-a\\t%%1\\t{w}\\nclaude-skip\\t%%2\\t{w}\\nother\\t%%3\\t{w}\\n"\n'
                    'else echo "$@" >> {k}; fi\n'.format(w=work, k=keys))
    tmux.chmod(0o755)
    env = dict(FLEET_TMUX=str(tmux), FLEET_PROJECTS=str(projects), FLEET_STATE=str(tmp_path / 'state'),
               FLEET_SKIP='claude-skip')
    return folder, keys, fcw.settings(env)


def test_end_to_end_ask_then_compact_through_tmux(fleet, monkeypatch):
    folder, keys, cfg = fleet
    monkeypatch.setattr(fcw.time, 'sleep', lambda s: None)
    f = transcript(folder, turn(T0 - 600, 'working'))
    os.utime(f, (T0 - 600, T0 - 600))
    fcw.main([], cfg, now=T0)
    typed = keys.read_text()
    assert 'Context check: you are at 520k tokens' in typed and typed.count('-t %1') == 2
    assert '%2' not in typed and '%3' not in typed, 'the skip list and other sessions are never touched'
    f.write_text(f.read_text() + turn(T0 + 30, 'SAVED /state/h.md') + '\n' + turn(T0 + 200, 'still going') + '\n')
    os.utime(f, (T0 + 200, T0 + 200))
    fcw.main([], cfg, now=T0 + 900)
    assert '/compact Full saved state is in /state/h.md' in keys.read_text()
    assert 'compact' in (cfg['state'] / 'watch.log').read_text()


def test_dry_run_types_nothing(fleet):
    folder, keys, cfg = fleet
    f = transcript(folder, turn(T0 - 600, 'working'))
    os.utime(f, (T0 - 600, T0 - 600))
    fcw.main(['--dry'], cfg, now=T0)
    assert not keys.exists() and not (cfg['state'] / 'claude-a.json').exists()
