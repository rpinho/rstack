"""net-deletion: a week that removed code is NET-NEGATIVE, a week that added it is NET-POSITIVE."""
import json
import os
from pathlib import Path
import subprocess
import sys

from rstack_hookcall import TOOLS

TOOL = TOOLS / 'net-deletion'


def git(*args, cwd):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                   cwd=str(cwd), check=True, capture_output=True)


def make_repo(tmp_path):
    repo = tmp_path / 'repo'
    (repo / 'rstack/hooks').mkdir(parents=True)
    (repo / 'tests').mkdir()
    (repo / 'docs').mkdir()
    (repo / 'rstack/hooks/a-guard.py').write_text('x = 1\n' * 50)
    (repo / 'rstack/hooks/b-guard.py').write_text('y = 1\n' * 50)
    (repo / 'rstack/hooks/README.md').write_text('# not a hook\n')
    (repo / 'tests/test_a.py').write_text('z = 1\n' * 500)     # tests and docs are not counted
    (repo / 'docs/tool.py').write_text('d = 1\n' * 500)
    (repo / 'rstack/gates.json').write_text(json.dumps({'gates': [{'gate': 'a-guard.py'}, {'gate': 'b-guard.py'}]}))
    git('init', '-q', cwd=repo)
    git('add', '-A', cwd=repo)
    git('commit', '-qm', 'init', cwd=repo)
    return repo


def run(repo, state, date, *extra):
    env = dict(os.environ, RSTACK_STATE_DIR=str(state))
    done = subprocess.run([sys.executable, str(TOOL), '--repo', str(repo), '--date', date, *extra],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_the_first_run_records_a_baseline_and_gives_no_verdict(tmp_path):
    repo = make_repo(tmp_path)
    out = run(repo, tmp_path / 'state', '2026-11-14')
    assert 'baseline recorded (100 lines, 2 hooks, 0 skills, 0 memory files, 2 gates)' in out
    assert 'NET-' not in out
    # a snapshot from yesterday is not seven days old: still no verdict
    assert 'NET-' not in run(repo, tmp_path / 'state', '2026-11-15')


def test_a_deletion_week_is_net_negative(tmp_path):
    repo, state = make_repo(tmp_path), tmp_path / 'state'
    run(repo, state, '2026-11-14')
    git('rm', '-q', 'rstack/hooks/b-guard.py', cwd=repo)
    (repo / 'rstack/gates.json').write_text(json.dumps({'gates': [{'gate': 'a-guard.py'}]}))
    (repo / 'rstack/hooks/a-guard.py').write_text('x = 1\n' * 40)
    out = run(repo, state, '2026-11-21')
    assert 'lines +0/-60' in out and 'hooks +0/-1' in out and 'gates +0/-1' in out, out
    assert out.endswith('NET-NEGATIVE'), out
    rows = [json.loads(l) for l in (state / 'net-deletion.jsonl').read_text().splitlines()]
    assert [r['date'] for r in rows] == ['2026-11-14', '2026-11-21']


def test_an_addition_week_is_net_positive(tmp_path):
    repo, state = make_repo(tmp_path), tmp_path / 'state'
    run(repo, state, '2026-11-14')
    (repo / 'rstack/hooks/c-guard.py').write_text('w = 1\n' * 30)
    (repo / 'rstack/gates.json').write_text(json.dumps({'gates': [{'gate': 'a-guard.py'}, {'gate': 'b-guard.py'},
                                                                   {'gate': 'c-guard.py'}]}))
    git('add', '-A', cwd=repo)
    out = run(repo, state, '2026-11-21')
    assert 'lines +30/-0' in out and 'hooks +1/-0' in out and 'gates +1/-0' in out, out
    assert out.endswith('NET-POSITIVE'), out


def test_skills_memory_and_wired_hooks_are_counted(tmp_path):
    repo, state = make_repo(tmp_path), tmp_path / 'state'
    skills, memory = tmp_path / 'skills', tmp_path / 'memory'
    (skills / 's1').mkdir(parents=True)
    (skills / 's1/SKILL.md').write_text('skill')
    memory.mkdir()
    (memory / 'MEMORY.md').write_text('- index\n')
    (memory / 'fact.md').write_text('fact')
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({'hooks': {'PreToolUse': [{'hooks': [
        {'type': 'command', 'command': 'python3 ~/x/rstack/hooks/a-guard.py'},      # already a file here
        {'type': 'command', 'command': 'python3 ~/.claude/hooks/installed-only.py'}]}]}}))
    args = ('--skills', str(skills), '--memory', str(memory), '--settings', str(settings))
    run(repo, state, '2026-11-14', *args)
    (skills / 's1/SKILL.md').unlink()
    out = run(repo, state, '2026-11-21', *args)
    assert 'skills +0/-1' in out and 'memory +0/-0' in out and 'hooks +0/-0' in out, out
    first = json.loads((state / 'net-deletion.jsonl').read_text().splitlines()[0])
    assert first['hooks'] == ['a-guard.py', 'b-guard.py', 'installed-only.py']
    assert len(first['memory']) == 1 and len(first['skills']) == 1


def test_tell_sends_the_one_line_through_tell_general(tmp_path):
    repo, state = make_repo(tmp_path), tmp_path / 'state'
    told = tmp_path / 'told'
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    tg = bindir / 'tell-general'
    tg.write_text('#!{}\nimport sys\nopen({!r}, "a").write(" ".join(sys.argv[1:]))\n'.format(sys.executable, str(told)))
    tg.chmod(0o755)
    env = dict(os.environ, RSTACK_STATE_DIR=str(state), PATH=str(bindir) + os.pathsep + os.environ['PATH'])
    done = subprocess.run([sys.executable, str(TOOL), '--repo', str(repo), '--date', '2026-11-14', '--tell'],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and told.read_text() == '--from net-deletion fyi ' + done.stdout.strip()
    env['PATH'] = '/usr/bin:/bin'    # tell-general not on PATH: still exits 0, says so
    done = subprocess.run([sys.executable, str(TOOL), '--repo', str(repo), '--date', '2026-11-15', '--tell'],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and 'tell-general is not on PATH' in done.stderr
