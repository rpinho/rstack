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


def test_pushed_drift_dirty_unpushed_and_private_commits(shared):
    (_, rows), p = shared
    mine = {k: d for k, w, d in rows if w == 'example-owner/drifted'}
    assert sorted(mine) == ['dirty', 'private-commits', 'unpushed']
    assert '{} side (1)'.format(p['drifted']) in mine['private-commits']
    assert '{} work (1)'.format(p['drifted']) in mine['unpushed']
    assert not [r for r in rows if r[1] == 'example-owner/clean']


def test_many_clones_of_one_repo_are_one_row_per_kind():
    """11-13: 121 job rows flooded the conductor's prompt; one repo here has 51 worktrees."""
    st = dict(dirty=2, common='/c', head='b', unpushed=0, track=[])
    clones = [(rf.Host(''), '/w{}'.format(i), {}) for i in range(51)]
    rows = rf.pushed_problems('o/r', 'main', clones, [dict(st, dirty=i + 1) for i in range(51)])
    assert len(rows) == 1 and rows[0][2].startswith('51 clone(s)') and '/w50 (51), /w49 (50), /w48 (49), ...' in rows[0][2]


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
    cfg, gh, _ = world(tmp_path)
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
               backups=[{'name': 'kb', 'match': 'no-such-backup-command-7f3a'}])
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
