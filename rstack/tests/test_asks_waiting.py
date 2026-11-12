"""asks-waiting finds sessions stopped on a person (11-08..11: three lanes sat three days unnoticed)."""
import importlib.machinery
import importlib.util
import json
import os
import time

from rstack_hookcall import TOOLS


def load():
    loader = importlib.machinery.SourceFileLoader('asks_waiting', str(TOOLS / 'asks-waiting'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


aw = load()


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
