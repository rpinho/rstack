"""asks-waiting finds sessions stopped on a person (11-08..11: three lanes sat three days unnoticed)."""
import importlib.machinery
import importlib.util
import json
import os
import time
from datetime import date, timedelta

import pytest

from rstack_hookcall import TOOLS


def load():
    loader = importlib.machinery.SourceFileLoader('asks_waiting', str(TOOLS / 'asks-waiting'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


aw = load()


@pytest.mark.parametrize('state', ['retired', 'ended'])
def test_retired_alias_ask_stays_visible_under_retired(tmp_path, monkeypatch, state):
    monkeypatch.setenv('TMUX_BIN', str(tmp_path / 'no-tmux'))
    registry = tmp_path / 'registry.json'
    row = {'status': 'retired' if state == 'retired' else 'active', 'sessions': ['closedb'],
           'why': 'owner closed challenge'}
    if state == 'ended':
        row['end'] = str(date.today() - timedelta(days=1))
    registry.write_text(json.dumps({'lanes': {'closed': row}}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(registry))
    p = tmp_path / 'projects'
    transcript(p, 'closedb', [say('Should I submit?', 3600, cwd='/src/closedb')])
    rows = aw.scan_sessions(p, time.time())
    assert len(rows) == 1
    assert 'retired: closed: ' + state in rows[0] and 'Should I submit?' in rows[0]
    assert 'owner closed challenge' in rows[0]


def test_hook_reclassifies_old_host_lists_and_keeps_active_asks(tmp_path, monkeypatch, capsys):
    import io
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'lanes': {'closed': {'status': 'retired', 'sessions': ['closedb'],
                                                       'why': 'finished'}}}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(registry))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('CONDUCTOR_CWD_SUFFIX', '/conductor')
    d = tmp_path / 'asks-waiting'
    d.mkdir()
    (d / 'host.tsv').write_text('2h\tclosedb\tquestion\tShould I submit?\n'
                               '2h\tworking\tquestion\tMay I proceed?\n')
    monkeypatch.setattr(aw.sys, 'stdin', io.StringIO('{"cwd":"/src/conductor"}'))
    assert aw.hook() == 0
    active, retired = capsys.readouterr().out.split('[asks-waiting] retired')
    assert 'working' in active and 'closedb' not in active
    assert 'closedb' in retired and 'finished' in retired and 'Should I submit?' in retired


def stamp(ago):
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time() - ago))


def transcript(projects, name, rows):
    d = projects / ('-src-' + name)
    d.mkdir(parents=True)
    (d / 's.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


def say(text, ago, cwd='/src/lane'):
    return dict(type='assistant', timestamp=stamp(ago), cwd=cwd,
                message=dict(role='assistant', content=[dict(type='text', text=text)]))


def test_finds_questions_and_pending_prompts_but_not_answered_or_busy(tmp_path, monkeypatch):
    monkeypatch.setenv('TMUX_BIN', str(tmp_path / 'no-tmux'))      # no tmux here: every session counts
    p = tmp_path / 'projects'
    transcript(p, 'asker', [say('Done the round. Should I start the next one?', 3600)])
    transcript(p, 'answered', [say('Should I?', 7200), dict(type='user', timestamp=stamp(7000),
                               message=dict(role='user', content='yes'))])
    transcript(p, 'stuck', [dict(type='assistant', timestamp=stamp(3600), message=dict(role='assistant', content=[
        dict(type='tool_use', id='t1', name='Bash', input={'command': 'rm x'})]))])
    transcript(p, 'fresh', [say('Should I go on?', 60)])
    transcript(p, 'statement', [say('Shipped 3 fixes.', 3600)])
    transcript(p, 'conductor', [say('Want me to merge it?', 3600, cwd='/home/u/conductor')])
    rows = aw.scan_sessions(p, time.time(), conductor='/home/u/conductor')
    labels = sorted(r.split('\t')[1] + ':' + r.split('\t')[2].split()[0] for r in rows)
    assert labels == ['-src-stuck:tool', 'lane:question']


def test_the_hook_prints_only_in_the_conductor(tmp_path, monkeypatch):
    import subprocess, sys
    state = tmp_path / 'state'
    (state / 'asks-waiting').mkdir(parents=True)
    (state / 'asks-waiting' / 'm5.tsv').write_text('2.0h\tplanets\tquestion\tShould I?\n')
    env = dict(os.environ, RSTACK_STATE_DIR=str(state), CONDUCTOR_CWD_SUFFIX='/home/u/conductor')
    run = lambda cwd: subprocess.run([sys.executable, str(TOOLS / 'asks-waiting'), '--hook'], env=env,
                                     input=json.dumps({'cwd': cwd}), capture_output=True, text=True).stdout
    assert 'm5: 2.0h | planets | question' in run('/home/u/conductor')
    assert run('/home/u/lane') == ''


def test_prs_are_scanned_at_most_every_half_hour_and_a_failure_keeps_the_last_list(tmp_path, monkeypatch):
    """11-12: a PR search every 5 minutes hit GitHub's rate limit on the shared token."""
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    calls = []
    good = lambda now: calls.append(now) or ['9h\tteorth/x\t2 open PR(s) idle 7-9h\toldest #1']
    bad = lambda now: calls.append(now) or ['?\tgh\tPR scan failed\tHTTP 403: API rate limit exceeded']
    t = 1_000_000.0
    assert aw.cached_prs(t, good)[0].startswith('9h')
    assert aw.cached_prs(t + 600, bad)[0].startswith('9h') and len(calls) == 1        # cached: no new search
    stale = aw.cached_prs(t + 3600, bad)
    assert len(calls) == 2 and stale[0].startswith('9h') and 'refresh failed' in stale[0]


def test_a_report_saying_nothing_needs_you_is_not_a_question(tmp_path, monkeypatch):
    """planets, 11-12: "Event-watch is armed. Nothing needs you." was listed as a question."""
    monkeypatch.setenv('TMUX_BIN', str(tmp_path / 'no-tmux'))
    p = tmp_path / 'projects'
    transcript(p, 'report', [say('Round started. Event-watch is armed. Nothing needs you.', 3600)])
    transcript(p, 'asks', [say('Round done. Nothing else needs you, but should I start the next one?', 3600, cwd='/src/b')])
    rows = aw.scan_sessions(p, time.time())
    assert [r.split('\t')[1] for r in rows] == ['b']


def test_a_line_separator_inside_a_record_does_not_hide_its_tool_result(tmp_path, monkeypatch):
    """11-12: the digest session read as stuck on a prompt for hours. Its transcript held a U+2028
    inside a tool result; splitlines() cut that record in two, the result was dropped, and the tool
    call looked unanswered. Transcripts are split on newlines only."""
    monkeypatch.setenv('TMUX_BIN', str(tmp_path / 'no-tmux'))
    p = tmp_path / 'projects'
    use = dict(type='assistant', timestamp=stamp(7200), cwd='/src/digest', message=dict(role='assistant', content=[
        dict(type='tool_use', id='t1', name='Bash', input={'command': 'ls'})]))
    result = dict(type='user', timestamp=stamp(7100), cwd='/src/digest', message=dict(role='user', content=[
        dict(type='tool_result', tool_use_id='t1', content='line one line two')]))
    d = p / '-src-digest'
    d.mkdir(parents=True)
    (d / 's.jsonl').write_text(json.dumps(use) + '\n' + json.dumps(result, ensure_ascii=False) + '\n'
                               + json.dumps(say('Done; event-watch armed.', 7000, cwd='/src/digest')) + '\n')
    assert aw.scan_sessions(p, time.time()) == []


def test_an_unchanged_ungraded_list_is_not_a_stopped_scan(tmp_path, monkeypatch, capsys):
    """11-27: mac-ungraded.tsv changes only when a job is recorded or graded; 1168 min old was a false alarm."""
    import io
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'lanes': {}}))
    monkeypatch.setenv('RH_LANE_REGISTRY', str(registry))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path))
    monkeypatch.setenv('CONDUCTOR_CWD_SUFFIX', '/conductor')
    d = tmp_path / 'asks-waiting'
    d.mkdir()
    old = time.time() - 3 * 3600
    for name in ('mac-ungraded.tsv', 'm5-jobs.tsv'):
        (d / name).write_text('')
        os.utime(d / name, (old, old))
    monkeypatch.setattr(aw.sys, 'stdin', io.StringIO('{"cwd":"/src/conductor"}'))
    aw.hook()
    out = capsys.readouterr().out
    assert 'mac-ungraded: list is' not in out
    assert 'm5-jobs: list is' in out and 'scan may have stopped' in out
