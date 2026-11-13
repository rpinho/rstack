"""job-health: a failed scheduled job or a stale required output reaches a person (11-12, twice in a day)."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import time

from rstack_hookcall import TOOLS


def load():
    loader = importlib.machinery.SourceFileLoader('job_health', str(TOOLS / 'job-health'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


jh = load()
LISTING = ('PID\tStatus\tLabel\n'
           '-\t0\tcom.example.fine\n'
           '-\t78\tcom.example.preview\n'
           '412\t1\tcom.example.running-now\n'
           '-\t1\tcom.example.lane-yield\n'
           '-\t1\tcom.other.not-ours\n')


def test_a_failed_last_run_is_a_problem_unless_that_code_is_declared_fine():
    jobs = jh.launchd_jobs('com.example.', LISTING)
    rows = jh.exit_problems(jobs, {'com.example.lane-yield': {'codes': [1], 'why': 'its FAIL verdict'}})
    assert rows == [('exit', 'com.example.preview', 'last run exited 78')]


def test_a_missing_or_stale_required_output_is_a_problem(tmp_path):
    """The X case: the job kept running and exiting 0, but its bookmark list stopped being rebuilt."""
    now = time.time()
    fresh, old = tmp_path / 'fresh.md', tmp_path / 'BOOKMARKS_FRESH.md'
    fresh.write_text('x')
    old.write_text('x')
    os.utime(old, (now - 72 * 3600, now - 72 * 3600))
    rows = jh.fresh_problems([dict(path=str(fresh), max_hours=6), dict(path=str(old), max_hours=6, why='X rounds'),
                              dict(path=str(tmp_path / 'gone.md'), max_hours=6)], now)
    assert [(k, os.path.basename(w)) for k, w, _ in rows] == [('fresh', 'BOOKMARKS_FRESH.md'), ('fresh', 'gone.md')]
    assert '72.0 h old' in rows[0][2]


def test_a_new_problem_alerts_once_and_shows_until_it_clears(tmp_path, monkeypatch):
    state, sent = tmp_path / 'state', tmp_path / 'sent.txt'
    stale = tmp_path / 'out.md'
    stale.write_text('x')
    os.utime(stale, (time.time() - 10 * 3600,) * 2)
    reg = tmp_path / 'reg.json'
    reg.write_text(json.dumps({'fresh': [{'path': str(stale), 'max_hours': 6, 'why': 'test'}]}))
    alert = "/bin/sh -c 'echo \"$0\" >> {}'".format(sent)
    run = lambda: subprocess.run([sys.executable, str(TOOLS / 'job-health'), '--prefix', 'com.nothing-matches.',
                                  '--registry', str(reg), '--alert', alert],
                                 env=dict(os.environ, RSTACK_STATE_DIR=str(state)), capture_output=True, text=True)
    assert run().returncode == 0 and run().returncode == 0               # a run that reports is not a failed job
    assert sent.read_text().count('job-health:') == 1                     # once per new problem, not per run
    listed = list((state / 'asks-waiting').glob('*-jobs.tsv'))[0].read_text()
    assert 'out.md' in listed                                             # the conductor sees it every turn
    stale.touch()
    assert run().returncode == 0
    assert list((state / 'asks-waiting').glob('*-jobs.tsv'))[0].read_text() == ''
    assert 'RECOVERED' in (state / 'job-health' / 'log').read_text()


def test_an_unreadable_registry_is_a_problem_not_an_all_clear(tmp_path):
    reg = tmp_path / 'reg.json'
    reg.write_text('{broken')
    r = subprocess.run([sys.executable, str(TOOLS / 'job-health'), '--prefix', 'com.nothing-matches.',
                        '--registry', str(reg), '--dry'], capture_output=True, text=True)
    assert r.returncode == 1 and 'unreadable' in r.stdout


def test_freshness_is_only_checked_in_the_hours_its_producer_runs(tmp_path):
    """11-13: the bookmark list is rebuilt 08:15-20:15; at 04:00 it is 8 h old by design, not stale."""
    f = tmp_path / 'list.md'
    f.write_text('x')
    now = time.mktime((2026, 11, 13, 4, 0, 0, 0, 0, -1))
    os.utime(f, (now - 8 * 3600,) * 2)
    entry = dict(path=str(f), max_hours=6, check_hours=[9, 22])
    assert jh.fresh_problems([entry], now) == []
    noon = time.mktime((2026, 11, 13, 12, 0, 0, 0, 0, -1))
    os.utime(f, (noon - 8 * 3600,) * 2)
    assert len(jh.fresh_problems([entry], noon)) == 1
