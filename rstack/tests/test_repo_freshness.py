"""repo-freshness: every public repo is pushed or published, and each kind's drift is a problem (11-13 audit)."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from rstack_hookcall import TOOLS

ENV = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
           GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid', GIT_CONFIG_GLOBAL='/dev/null')


def load():
    loader = importlib.machinery.SourceFileLoader('repo_freshness', str(TOOLS / 'repo-freshness'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


rf = load()


def git(cwd, *a):
    return subprocess.run(['git', '-C', str(cwd), *a], check=True, capture_output=True, text=True, env=ENV).stdout


def commit(repo, path, text, msg='c'):
    f = Path(repo) / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    git(repo, 'add', path)
    git(repo, 'commit', '-qm', msg)


def public_clone(tmp_path, name):
    """A clone of a local bare repo whose origin then names the GitHub repo, keeping its tracking refs."""
    bare = tmp_path / 'remotes' / (name + '.git')
    git(tmp_path, 'init', '-q', '--bare', '-b', 'main', str(bare))
    seed = tmp_path / 'seed' / name
    git(tmp_path, 'clone', '-q', str(bare), str(seed))
    commit(seed, 'README.md', '# {}\n'.format(name))
    git(seed, 'push', '-q', 'origin', 'HEAD:main')
    clone = tmp_path / 'dev' / name
    git(tmp_path, 'clone', '-q', str(bare), str(clone))
    git(clone, 'remote', 'set-url', 'origin', 'git@github.com:example-owner/{}.git'.format(name))
    return clone


def blob(text):
    return subprocess.run(['git', 'hash-object', '--stdin'], input=text, capture_output=True, text=True).stdout.strip()


def fake_gh(tmp_path, repos, trees):
    data = tmp_path / 'gh.json'
    data.write_text(json.dumps({'repos': repos, 'trees': trees}))
    gh = tmp_path / 'fake-gh'
    gh.write_text('#!{}\nimport json, sys\nd = json.load(open({!r}))\na = sys.argv[1:]\n'
                  'if a[:2] == ["repo", "list"]:\n    print(json.dumps([r for r in d["repos"] if r["nameWithOwner"].split("/")[0] == a[2]]))\n'
                  'elif a[0] == "api":\n    k = a[1].split("/git/trees/")[0][len("repos/"):]\n'
                  '    if k not in d["trees"]: sys.exit(1)\n    print(json.dumps({{"tree": d["trees"][k]}}))\n'
                  'else: sys.exit(2)\n'.format(sys.executable, str(data)))
    gh.chmod(0o755)
    return str(gh)


def repo(name, archived=False):
    return {'nameWithOwner': 'example-owner/' + name, 'isArchived': archived, 'defaultBranchRef': {'name': 'main'}}


def world(tmp_path):
    clean = public_clone(tmp_path, 'clean')
    drifted = public_clone(tmp_path, 'drifted')
    (drifted / 'notes.txt').write_text('uncommitted\n')
    commit(drifted, 'a.txt', 'a\n')                                   # on main, on no remote: unpushed
    git(drifted, 'branch', '-q', 'side', 'HEAD')
    git(drifted, 'branch', '-q', '--set-upstream-to', 'origin/main', 'side')   # tracks public main, ahead by 1
    git(drifted, 'reset', '-q', '--hard', 'origin/main')
    git(drifted, 'checkout', '-q', '-b', 'work')
    commit(drifted, 'b.txt', 'b\n')                                   # checked-out branch with a local commit
    src = tmp_path / 'dev' / 'release-src'
    git(tmp_path, 'init', '-q', '-b', 'main', str(src))
    commit(src, 'README.md', 'release\n')
    commit(src, 'src/x.py', 'x = 1\n')
    commit(src, 'HANDOFF.md', 'private\n')
    commit(src, 'PUBLISH', 'remote git@github.com:example-owner/release.git\nREADME.md\nsrc/\nHANDOFF.md\n')
    agent = tmp_path / 'agent-files.gitignore'
    agent.write_text('HANDOFF.md\n')
    trees = {'example-owner/release': [{'path': 'README.md', 'type': 'blob', 'sha': blob('release\n')},
                                       {'path': 'src/x.py', 'type': 'blob', 'sha': blob('x = 0\n')}]}
    repos = [repo('clean'), repo('drifted'), repo('release'), repo('old-site'), repo('stray'),
             repo('frozen', archived=True)]
    cfg = {'owners': ['example-owner'], 'roots': [{'path': str(tmp_path / 'dev'), 'depth': 3}],
           'declared': {'example-owner/old-site': {'kind': 'frozen', 'why': 'kept for links'}},
           'agent_files': str(agent)}
    return cfg, fake_gh(tmp_path, repos, trees), dict(clean=clean, drifted=drifted, src=src)


def kinds(rows):
    return sorted({(k, os.path.basename(w.split()[0]) if '/' in w else w) for k, w, _ in rows})


@pytest.fixture(scope='module')
def shared(tmp_path_factory):
    """One world and one check for the tests that only read it (each world costs a few seconds of git)."""
    cfg, gh, paths = world(tmp_path_factory.mktemp('shared'))
    return rf.check(cfg, gh), paths


def test_inventory_classifies_every_public_repo_and_fails_on_the_one_with_no_way_in(shared):
    (lines, rows), _ = shared
    inv = {l.split('\t')[1]: l.split('\t')[0] for l in lines}
    assert inv == {'example-owner/clean': 'pushed', 'example-owner/drifted': 'pushed',
                   'example-owner/release': 'published', 'example-owner/old-site': 'declared:frozen',
                   'example-owner/stray': 'unknown', 'example-owner/frozen': 'archived'}
    assert [w for k, w, _ in rows if k == 'unknown'] == ['example-owner/stray']


def test_public_branch_safety_and_clone_freshness(shared):
    (_, rows), p = shared
    mine = {k: d for k, w, d in rows if w == 'example-owner/drifted'}
    assert sorted(mine) == ['private-commits']
    assert '{} side (1)'.format(p['drifted']) in mine['private-commits']
    assert ('no-upstream', 'local:' + str(p['drifted'])) in {(k, w) for k, w, _ in rows}
    assert not [r for r in rows if r[1] == 'example-owner/clean']


def test_many_clones_of_one_repo_are_one_row_per_kind():
    """11-13: 121 job rows flooded the conductor's prompt; one repo here has 51 worktrees."""
    st = dict(head='b')
    clones = [(rf.Host(''), '/w{}'.format(i), {}) for i in range(51)]
    states = [dict(st, common='/c{}'.format(i), track=[('side', i + 1)]) for i in range(51)]
    rows = rf.pushed_problems('o/r', 'main', clones, states)
    assert len(rows) == 1 and rows[0][2].startswith('51 local branch(es)')
    assert '/w50 side (51), /w49 side (50), /w48 side (49), ...' in rows[0][2]


def test_published_compares_the_export_not_the_private_history(tmp_path):
    """The agent working file is dropped like publish-public drops it; the edited src/x.py is drift."""
    cfg, gh, p = world(tmp_path)
    _, rows = rf.check(cfg, gh)
    pub = [d for k, w, d in rows if k == 'unpublished']
    assert len(pub) == 1 and 'change 1 file(s) and remove 0' in pub[0] and 'src/x.py' in pub[0]
    assert 'HANDOFF' not in pub[0]
    # the source being far ahead of the public repo is not drift: make the export match and add private commits
    trees = json.loads((tmp_path / 'gh.json').read_text())
    trees['trees']['example-owner/release'][1]['sha'] = blob('x = 1\n')
    (tmp_path / 'gh.json').write_text(json.dumps(trees))
    commit(p['src'], 'private/log.txt', 'not whitelisted\n')
    _, rows = rf.check(cfg, gh)
    assert not [r for r in rows if r[0] == 'unpublished']
    assert not [r for r in rows if r[1] == 'example-owner/release']  # its own unpushed history is not drift


def test_stale_readme_blocks_are_a_problem(tmp_path):
    cfg, gh, p = world(tmp_path)
    clean = p['clean']
    (clean / 'R.jsonl').write_text('{"new": true}\n{"new": true}\n')
    (clean / 'readme-blocks.json').write_text(json.dumps({'blocks': {'n': {'source': 'jsonl', 'path': 'R.jsonl'}}}))
    commit(clean, 'README.md', 'n = <!-- auto:n -->1<!-- /auto -->\n')
    git(clean, 'add', 'R.jsonl', 'readme-blocks.json')
    git(clean, 'commit', '-qm', 'blocks')
    git(clean, 'update-ref', 'refs/remotes/origin/main', 'HEAD')      # as if pushed
    cfg['readme_blocks'] = '{} {}'.format(sys.executable, TOOLS / 'readme-blocks')
    _, rows = rf.check(cfg, gh)
    assert [d for k, w, d in rows if k == 'readme' and str(clean) in w] == ['auto-blocks differ from a fresh render: n']
    commit(clean, 'README.md', 'n = <!-- auto:n -->2<!-- /auto -->\n')
    git(clean, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    _, rows = rf.check(cfg, gh)
    assert not [r for r in rows if r[0] == 'readme']


def test_installed_retro_and_backup_checks(tmp_path):
    cfg, gh, paths = world(tmp_path)
    live, src = tmp_path / 'bin', tmp_path / 'repo-tools'
    live.mkdir()
    src.mkdir()
    git(src, 'init', '-q')
    for n, a, b in (('same', 'x', 'x'), ('edited', 'x', 'y'), ('edited-in-checkout', 'x', 'x')):
        (live / n).write_text(a)
        (src / n).write_text(b)
    (src / 'only-in-repo').write_text('z')
    git(src, 'add', '.')
    git(src, 'commit', '-qm', 'tools')
    (src / 'edited-in-checkout').write_text('uncommitted')          # not what was installed: compare HEAD
    now = time.time()
    day = 86400
    results = tmp_path / 'RESULTS.jsonl'
    iso = lambda t: time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(t))
    results.write_text(''.join(json.dumps({'utc': iso(now - d * day)}) + '\n' for d in (20, 10, 1)))
    retro = tmp_path / 'RETRO.md'
    retro.write_text('retro\n')
    os.utime(retro, (now - 15 * day,) * 2)
    fresh = tmp_path / 'FRESH.md'
    fresh.write_text('retro\n')
    os.utime(fresh, (now - 5 * day,) * 2)
    cfg.update(installed=[{'live': str(live), 'repo': str(src), 'names': ['same', 'edited', 'edited-in-checkout', 'only-in-repo', 'not-installed']}],
               retros=[{'lane': 'stale', 'retro': str(retro), 'results': str(results)},
                       {'lane': 'fresh', 'retro': str(fresh), 'results': str(results)},
                       {'lane': 'missing', 'retro': str(tmp_path / 'NONE.md'), 'results': str(results)},
                       {'lane': 'unreadable', 'retro': str(retro), 'results': str(tmp_path / 'gone.jsonl')}],
               backups=[{'name': 'kb', 'match': 'no-such-backup-command-7f3a'},
                        {'name': 'fresh-snapshot', 'repo': str(paths['clean'])}])
    _, rows = rf.check(cfg, gh)
    assert sorted(os.path.basename(w) for k, w, _ in rows if k == 'installed') == ['edited', 'not-installed', 'only-in-repo']
    retros = {w: d for k, w, d in rows if k == 'retro'}
    assert set(retros) == {'stale', 'missing', 'unreadable'}          # fresh: its newer result is 1 day old
    assert '2 newer result(s), the oldest 10 days' in retros['stale'] and 'no retro' in retros['missing']
    assert [w for k, w, _ in rows if k == 'backup'] == ['kb']


def test_a_run_writes_the_list_alerts_once_and_only_dry_exits_nonzero(tmp_path):
    cfg, gh, _ = world(tmp_path)
    conf = tmp_path / 'rf.json'
    conf.write_text(json.dumps(cfg))
    sent, state = tmp_path / 'sent.txt', tmp_path / 'state'
    env = dict(ENV, RSTACK_STATE_DIR=str(state), REPO_FRESHNESS_GH=gh)
    alert = "/bin/sh -c 'echo \"$0\" >> {}'".format(sent)
    run = lambda *a: subprocess.run([sys.executable, str(TOOLS / 'repo-freshness'), '--config', str(conf), *a],
                                    env=env, capture_output=True, text=True)
    r = run('--dry')
    assert r.returncode == 1 and 'example-owner/stray' in r.stdout and not state.exists()
    assert run('--alert', alert).returncode == 0 and run('--alert', alert).returncode == 0
    assert sent.read_text().count('repo-freshness:') == 1
    listed = list((state / 'asks-waiting').glob('*-repos.tsv'))[0].read_text()
    assert 'example-owner/stray' in listed and listed.startswith('repo\t')


def test_a_broken_config_or_unreadable_github_is_a_problem_not_an_all_clear(tmp_path):
    conf = tmp_path / 'rf.json'
    conf.write_text('{broken')
    r = subprocess.run([sys.executable, str(TOOLS / 'repo-freshness'), '--config', str(conf), '--dry'],
                       capture_output=True, text=True)
    assert r.returncode == 1 and 'unreadable' in r.stdout
    cfg, _, _ = world(tmp_path)
    _, rows = rf.check(cfg, '/bin/false')
    assert rows and rows[-1][0] == 'inventory'
    r = subprocess.run([sys.executable, str(TOOLS / 'repo-freshness'), '--config', str(tmp_path / 'none.json')],
                       capture_output=True, text=True)
    assert r.returncode == 2 and 'nothing was checked' in r.stderr


def test_publish_globs_match_publish_public():
    rx = rf.glob_rx
    assert rx('docs/').match('docs/a/b.md') and rx('*.py').match('x.py') and not rx('*.py').match('a/x.py')
    assert rx('results/**/*.log').match('results/a/b/c.log') and rx('**/x').match('x')
    assert rf.repo_id('https://github.com/Example/Repo.git') == rf.repo_id('git@github.com:example/repo') \
        == 'github.com/example/repo'


@pytest.fixture
def clone_pair(tmp_path):
    """An ordinary private clone and a writer to its local bare remote; no network needed."""
    bare, seed, checkout = tmp_path / 'remote.git', tmp_path / 'seed', tmp_path / 'dev' / 'checkout'
    git(tmp_path, 'init', '-q', '--bare', '-b', 'main', str(bare))
    git(tmp_path, 'clone', '-q', str(bare), str(seed))
    commit(seed, 'data.txt', 'initial\n')
    commit(seed, '.gitignore', 'ignored/\n')
    git(seed, 'push', '-q', 'origin', 'main')
    git(tmp_path, 'clone', '-q', str(bare), str(checkout))
    return checkout, seed, bare


def clone_config(checkout, **extra):
    return dict({'roots': [{'path': str(checkout.parent), 'depth': 3}]}, **extra)


def test_private_clone_behind_is_detected_after_fetch(clone_pair):
    checkout, seed, _ = clone_pair
    commit(seed, 'data.txt', 'remote is ahead\n')
    git(seed, 'push', '-q', 'origin', 'main')
    assert rf.check(clone_config(checkout))[1] == []  # cached upstream is still equal
    _, rows = rf.check(clone_config(checkout, fetch=True))
    assert rows == [('behind', 'local:' + str(checkout), 'behind 1')]
    assert git(checkout, 'show', 'HEAD:data.txt') == 'initial\n'  # fetch did not pull


def test_no_upstream_on_private_clone_and_intentional_detached_head(clone_pair):
    checkout, _, _ = clone_pair
    git(checkout, 'branch', '--unset-upstream')
    cfg = clone_config(checkout, detached=[{'path': str(checkout)}])
    assert rf.check(cfg)[1] == [('no-upstream', 'local:' + str(checkout), 'current branch has no upstream')]
    git(checkout, 'checkout', '-q', '--detach')
    assert rf.check(clone_config(checkout))[1][0][0] == 'no-upstream'
    assert rf.check(cfg)[1] == []
    cfg['detached'][0]['host'] = 'elsewhere'
    assert rf.check(cfg)[1][0][0] == 'no-upstream'


def test_dirty_old_vs_fresh_tracks_untracked_and_honors_gitignore(clone_pair):
    checkout, _, _ = clone_pair
    now = time.time()
    (checkout / 'data.txt').write_text('dirty\n')
    loose = checkout / 'loose file\nwith newline.txt'
    loose.write_text('untracked\n')
    ignored = checkout / 'ignored' / 'old.txt'
    ignored.parent.mkdir()
    ignored.write_text('ignored\n')
    os.utime(ignored, (now - 200 * 3600,) * 2)
    cfg = clone_config(checkout)
    assert rf.check(cfg, now=now)[1] == []
    os.utime(loose, (now - 49 * 3600,) * 2)
    assert rf.check(cfg, now=now)[1] == [
        ('dirty', 'local:' + str(checkout), 'dirty files 2 oldest 49.0h (limit 24h)')]
    assert rf.check(clone_config(checkout, dirty_max_hours=50), now=now)[1] == []
    os.utime(loose, (now,) * 2)
    os.utime(checkout / 'data.txt', (now - 25 * 3600,) * 2)
    assert 'dirty files 2 oldest 25.0h' in rf.check(cfg, now=now)[1][0][2]


def test_staged_rename_and_deleted_file_are_counted_once(clone_pair):
    checkout, _, _ = clone_pair
    now = time.time()
    git(checkout, 'mv', 'data.txt', 'renamed file.txt')
    os.utime(checkout / 'renamed file.txt', (now - 30 * 3600,) * 2)
    rows = rf.check(clone_config(checkout), now=now)[1]
    assert len(rows) == 1 and 'dirty files 1 oldest 30.0h' in rows[0][2]
    (checkout / '.gitignore').unlink()
    os.utime(checkout, (now - 40 * 3600,) * 2)
    rows = rf.check(clone_config(checkout), now=now)[1]
    assert len(rows) == 1 and 'dirty files 2 oldest 40.0h' in rows[0][2]


def test_unpushed_commits_are_aged_against_current_upstream(clone_pair, monkeypatch):
    checkout, _, _ = clone_pair
    now = int(time.time())
    monkeypatch.setitem(ENV, 'GIT_AUTHOR_DATE', '{} +0000'.format(now - 30 * 3600))
    monkeypatch.setitem(ENV, 'GIT_COMMITTER_DATE', '{} +0000'.format(now - 30 * 3600))
    commit(checkout, 'data.txt', 'old local commit\n')
    monkeypatch.setitem(ENV, 'GIT_AUTHOR_DATE', '{} +0000'.format(now))
    monkeypatch.setitem(ENV, 'GIT_COMMITTER_DATE', '{} +0000'.format(now))
    commit(checkout, 'data.txt', 'recent local commit\n')
    cfg = clone_config(checkout)
    assert rf.check(cfg, now=now)[1] == [
        ('unpushed', 'local:' + str(checkout), 'unpushed 2 oldest 30.0h (limit 24h)')]
    assert rf.check(clone_config(checkout, unpushed_max_hours=31), now=now)[1] == []
    # A commit on a different remote does not make it pushed to this branch's upstream.
    git(checkout, 'update-ref', 'refs/remotes/elsewhere/saved', 'HEAD')
    assert rf.check(cfg, now=now)[1][0][0] == 'unpushed'


@pytest.mark.parametrize('hours,stale', [(72, True), (1, False)])
def test_backup_repo_age_without_match(tmp_path, monkeypatch, hours, stale):
    backup = tmp_path / 'backup'
    git(tmp_path, 'init', '-q', '-b', 'main', str(backup))
    now = int(time.time())
    for k in ('GIT_AUTHOR_DATE', 'GIT_COMMITTER_DATE'):
        monkeypatch.setitem(ENV, k, '{} +0000'.format(now - hours * 3600))
    commit(backup, 'snapshot.txt', 'snapshot\n')
    cfg = {'backups': [{'name': 'results', 'repo': str(backup)}]}
    rows = rf.check(cfg, now=now)[1]
    expected = [('backup', 'local:{} (results)'.format(backup), 'newest commit 72.0h old (limit 48h)')]
    assert rows == (expected if stale else [])
    cfg['backups'][0]['max_hours'] = 100
    assert rf.check(cfg, now=now)[1] == []


def test_backup_fetch_shared_with_clone_and_overlapping_roots(clone_pair, monkeypatch):
    checkout, seed, _ = clone_pair
    now = int(time.time())
    commit(seed, 'snapshot.txt', 'new backup\n')
    git(seed, 'push', '-q', 'origin', 'main')
    cfg = clone_config(checkout, fetch=True, backups=[{'name': 'results', 'repo': str(checkout), 'max_hours': 1}])
    cfg['roots'].append(dict(cfg['roots'][0]))
    calls, original = [], rf.Host.run
    def counted(self, argv, *args, **kwargs):
        if argv[:3] == ['python3', '-c', rf.FRESHNESS]:
            calls.append(argv[3:])
        return original(self, argv, *args, **kwargs)
    monkeypatch.setattr(rf.Host, 'run', counted)
    rows = rf.check(cfg, now=now)[1]
    assert calls == [[str(checkout), 'true']]
    assert rows == [('behind', 'local:' + str(checkout), 'behind 1')]


def test_fetch_failure_is_a_finding_and_does_not_hide_other_checks(clone_pair):
    checkout, _, bare = clone_pair
    git(checkout, 'remote', 'set-url', 'origin', str(bare.parent / 'missing.git'))
    git(checkout, 'branch', '--unset-upstream')
    rows = rf.check(clone_config(checkout, fetch=True))[1]
    assert [k for k, _, _ in rows] == ['fetch', 'no-upstream']
    assert rows[0][1] == 'local:' + str(checkout)
    assert 'fetch failed:' in rows[0][2] and 'missing.git' in rows[0][2]


def test_clone_scan_continues_when_public_inventory_fails(clone_pair):
    checkout, _, _ = clone_pair
    git(checkout, 'branch', '--unset-upstream')
    cfg = clone_config(checkout, owners=['example-owner'])
    rows = rf.check(cfg, gh='/bin/false')[1]
    assert {k for k, _, _ in rows} == {'inventory', 'no-upstream'}
    cfg['exclude'] = [str(checkout.parent / '*')]
    assert [k for k, _, _ in rf.check(cfg, gh='/bin/false')[1]] == ['inventory']


def test_alert_summary_daily_retry_and_first_five(tmp_path, monkeypatch):
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    sent = tmp_path / 'sent.txt'
    script = tmp_path / 'alert.py'
    script.write_text('import sys\nfrom pathlib import Path\n'
                      'with Path(sys.argv[1]).open("a") as f: f.write(sys.argv[2] + "\\n")\n')
    import shlex
    cmd = shlex.join([sys.executable, str(script), str(sent)])
    rows = [('behind', 'remote:/repo{}'.format(i), 'behind {}'.format(i + 1)) for i in range(7)]
    rows.append(('dirty', 'local:/other', 'dirty files 1 oldest 30h'))
    rf.alert_problems(rows, cmd, now=100000)
    rf.alert_problems(rows + [('no-upstream', 'local:/new', 'no upstream')], cmd, now=100001)
    rf.alert_problems(rows, cmd, now=100000 + 86400)
    lines = sent.read_text().splitlines()
    assert len(lines) == 2
    assert 'behind=7, dirty=1' in lines[0]
    assert '/repo4 ' in lines[0] and '/repo5 ' not in lines[0] and '/other ' not in lines[0]
    assert json.loads((tmp_path / 'state/repo-freshness/last-alert.json').read_text())['sent_at'] == 186400
    # A failed alert leaves the last success alone, so the next run can retry.
    rf.alert_problems(rows, '/bin/false', now=300000)
    rf.alert_problems(rows, cmd, now=300001)
    assert len(sent.read_text().splitlines()) == 3
    rf.alert_problems([], cmd, now=400000)
    assert len(sent.read_text().splitlines()) == 3


@pytest.mark.parametrize('command,seconds', [('fetch', 30), ('status', 120)])
def test_git_timeouts_keep_available_findings(clone_pair, monkeypatch, capsys, command, seconds):
    checkout, seed, _ = clone_pair
    commit(seed, 'data.txt', 'remote advance\n')
    git(seed, 'push', '-q', 'origin', 'main')
    original = subprocess.run
    def timeout_one(argv, **kwargs):
        if command in argv:
            assert kwargs['timeout'] == seconds
            raise subprocess.TimeoutExpired(argv, seconds)
        return original(argv, **kwargs)
    monkeypatch.setattr(subprocess, 'run', timeout_one)
    monkeypatch.setattr(sys, 'argv', ['collector', str(checkout), 'true'])
    exec(rf.FRESHNESS, {})
    st = json.loads(capsys.readouterr().out)
    rows = rf.clone_problems(rf.Host(''), str(checkout), st, {}, time.time())
    if command == 'fetch':
        assert rows == [('fetch', 'local:' + str(checkout), 'fetch failed: timed out after 30 s')]
    else:
        assert [r[0] for r in rows] == ['host', 'behind']
        assert st['latest'] is not None and 'timed out after 120 seconds' in rows[0][2]


def test_clone_only_scan_does_not_classify_publish_files(clone_pair):
    checkout, _, _ = clone_pair
    commit(checkout, 'PUBLISH', 'remote git@github.com:example-owner/release.git\ndata.txt\n')
    assert rf.check(clone_config(checkout))[1] == []


def test_invalid_nested_git_directory_does_not_check_parent_twice(clone_pair):
    checkout, _, _ = clone_pair
    nested = checkout / 'not-a-checkout'
    (nested / '.git').mkdir(parents=True)
    rows = rf.check(clone_config(checkout))[1]
    assert rows == [('host', 'local:' + str(nested), 'cannot read clone: not a checkout root; Git resolves to ' + str(checkout))]


def test_remote_clone_and_backup_findings_name_the_host(clone_pair, monkeypatch):
    checkout, _, _ = clone_pair
    git(checkout, 'branch', '--unset-upstream')
    original = rf.Host.run
    def local_transport(self, argv, *args, **kwargs):
        return original(rf.Host(''), argv, *args, **kwargs)
    monkeypatch.setattr(rf.Host, 'run', local_transport)
    cfg = {'roots': [{'path': str(checkout.parent), 'host': 'other-mac', 'depth': 3}],
           'backups': [{'name': 'results', 'repo': str(checkout), 'host': 'other-mac', 'max_hours': 48}]}
    now = time.time() + 72 * 3600
    rows = rf.check(cfg, now=now)[1]
    assert [r[0] for r in rows] == ['no-upstream', 'backup']
    assert all(r[1].startswith('other-mac:' + str(checkout)) for r in rows)
