"""rstack tools: each refuses what it should, allows what it should, and leaks nothing it guards."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from rstack_hookcall import TOOLS

# Placeholder vocabulary only. Real term lists never enter this repository.
TERM = 'projectcodename'


def run(argv, env=None, input=None, cwd=None):
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(('RSTACK_', 'CONDUCTOR_', 'EVENT_WATCH_', 'CLEAN_ROOM_'))}
    e.update(env or {})
    return subprocess.run(argv, env=e, input=input, text=True, capture_output=True,
                          cwd=str(cwd) if cwd else None, timeout=60)


def py(tool, *args, **kw):
    return run([sys.executable, str(TOOLS / tool), *args], **kw)


def git(*args, cwd):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
                   cwd=str(cwd), check=True, capture_output=True)


def terms_file(tmp_path, body=None):
    p = tmp_path / 'terms.txt'
    p.write_text(body if body is not None else
                 '# test terms\n{}\nmarker run id = \\brun-\\d{{3}}\\b\n'
                 'standalone ticket = \\bTKT-\\d{{6}}\\b\n'.format(TERM))
    return p


# ------------------------------------------------------------------------------- event-watch

@pytest.fixture
def watch(tmp_path):
    conf, state = tmp_path / 'conf', tmp_path / 'state'
    conf.mkdir()
    env = {'EVENT_WATCH_CONF': str(conf), 'EVENT_WATCH_STATE': str(state)}
    return conf, state, env


def test_event_watch_wakes_on_a_new_file_and_only_then(watch, tmp_path):
    conf, state, env = watch
    out = tmp_path / 'results'
    out.mkdir()
    (out / 'old.csv').write_text('x')
    (conf / 'job.conf').write_text('new {}/*.csv\n'.format(out))
    first = py('event-watch', 'scan', 'job', env=env)
    assert first.returncode == 0 and first.stdout == ''          # baseline, no event
    quiet = py('event-watch', 'wait', 'job', '--max-hours', '0', env=env)
    assert '"quiet"' in quiet.stdout                              # silence is said, not implied
    (out / 'new.csv').write_text('y')
    woke = py('event-watch', 'wait', 'job', '--max-hours', '0', env=env)
    events = [json.loads(l) for l in woke.stdout.splitlines()]
    assert [e['kind'] for e in events] == ['new'] and events[0]['path'].endswith('new.csv')
    again = py('event-watch', 'wait', 'job', '--max-hours', '0', env=env)
    assert '"quiet"' in again.stdout                              # the cursor moved


def test_event_watch_match_deadline_and_missing_job(watch, tmp_path):
    conf, state, env = watch
    log = tmp_path / 'run.log'
    log.write_text('starting\n')
    (conf / 'j.conf').write_text('match {} Traceback\ndeadline 2000-01-01T00:00\n'.format(log))
    py('event-watch', 'scan', 'j', env=env)
    with open(log, 'a') as f:
        f.write('Traceback (most recent call last)\n')
    woke = py('event-watch', 'wait', 'j', '--max-hours', '0', env=env)
    kinds = sorted(json.loads(l)['kind'] for l in woke.stdout.splitlines())
    assert kinds == ['deadline', 'match']
    assert py('event-watch', 'wait', 'nope', '--max-hours', '0', env=env).returncode == 2


def test_event_watch_notification_carries_no_log_content(watch, tmp_path):
    conf, state, env = watch
    log = tmp_path / 'run.log'
    log.write_text('')
    seen = tmp_path / 'notified.txt'
    notifier = tmp_path / 'notify'
    notifier.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$1" "$2" >> {}\n'.format(seen))
    notifier.chmod(0o755)
    (conf / 'p.conf').write_text('push on\nmatch {} ERROR\n'.format(log))
    env = dict(env, EVENT_WATCH_NOTIFY=str(notifier))
    py('event-watch', 'scan', 'p', env=env)
    log.write_text('ERROR the-private-detail\n')
    py('event-watch', 'scan', 'p', env=env)
    pushed = seen.read_text()
    assert 'match: run.log' in pushed
    assert 'private-detail' not in pushed


# ------------------------------------------------------------------------------------- relay

@pytest.fixture
def inbox(tmp_path):
    root = tmp_path / 'inbox'
    return root, {'CONDUCTOR_INBOX_DIR': str(root), 'CLAUDE_SESSION_NAME': 'worker-a'}


def rows(root):
    return [json.loads(l) for l in (root / 'inbox.jsonl').read_text().splitlines()]


def test_relay_without_terms_files_and_says_so(inbox):
    root, env = inbox
    r = py('relay', 'fyi', 'build', 'finished', env=env)
    assert r.returncode == 0 and 'nothing is quarantined' in r.stderr
    assert rows(root)[-1]['text'] == 'build finished' and not (root / 'wake').exists()
    py('relay', 'owner', 'needs a click', env=env)
    assert len(list((root / 'wake').iterdir())) == 1
    assert py('relay', 'gossip', 'x', env=env).returncode != 0     # unknown kind refused


def test_relay_quarantines_and_never_names_the_terms(inbox, tmp_path):
    root, env = inbox
    env = dict(env, RSTACK_TERMS_FILE=str(terms_file(tmp_path)))
    detail = 'results for {} are in run-104'.format(TERM)
    r = py('relay', 'break', detail, '--summary', 'run finished; needs a decision', env=env)
    row = rows(root)[-1]
    assert row['quarantine_match_count'] == 1
    assert TERM not in json.dumps(row), 'the row is re-read on every wake: no terms in it'
    assert TERM not in r.stdout + r.stderr
    assert row['text'].startswith('run finished; needs a decision')
    q = Path(row['quarantined'])
    assert q.read_text() == detail
    assert stat.S_IMODE(q.stat().st_mode) == 0o600
    assert len(list((root / 'wake').iterdir())) == 1               # the kind still wakes
    assert TERM not in (root / 'wake').iterdir().__next__().read_text()


def test_relay_withholds_a_summary_that_also_matches(inbox, tmp_path):
    root, env = inbox
    env = dict(env, RSTACK_TERMS_FILE=str(terms_file(tmp_path)))
    py('relay', 'fyi', TERM + ' detail', '--summary', 'about ' + TERM, env=env)
    row = rows(root)[-1]
    assert TERM not in json.dumps(row) and 'withheld too' in row['text']


def test_relay_unreadable_terms_quarantines_everything(inbox, tmp_path):
    root, env = inbox
    env = dict(env, RSTACK_TERMS_FILE=str(tmp_path / 'missing.txt'))
    r = py('relay', 'fyi', 'anything at all', env=env)
    assert r.returncode == 0 and 'cannot be read' in r.stderr
    row = rows(root)[-1]
    assert 'anything at all' not in row['text'] and Path(row['quarantined']).exists()


# ------------------------------------------------------------------------------- egress-gate

def fake_aws_key():
    return 'AK' + 'IA' + 'Z7' * 8                                  # assembled at run time


def egress(*args, env=None, **kw):
    return py('egress-gate', *args, env=env or {}, **kw)


def test_egress_gate_scan(tmp_path):
    clean = tmp_path / 'clean'
    clean.mkdir()
    (clean / 'README.md').write_text('nothing to see\n')
    r = egress('scan', str(clean), env={'HOME': str(tmp_path)})
    assert r.returncode == 0 and 'PASS' in r.stdout and 'built-in secret shapes only' in r.stdout

    dirty = tmp_path / 'dirty'
    dirty.mkdir()
    (dirty / 'config.py').write_text('KEY = "{}"\n'.format(fake_aws_key()))
    r = egress('scan', str(dirty), env={'HOME': str(tmp_path)})
    assert r.returncode == 2 and '[aws-key]' in r.stdout

    (clean / 'blob.jsonl').write_text('{"encrypted_content":"gAAAAA' + 'sk-' + 'A' * 60 + '"}\n')
    assert egress('scan', str(clean), env={'HOME': str(tmp_path)}).returncode == 0   # ciphertext masked


def test_egress_gate_user_patterns_terms_and_blind_refusal(tmp_path):
    conf = tmp_path / 'egress'
    conf.mkdir()
    env = {'RSTACK_EGRESS_DIR': str(conf)}
    target = tmp_path / 'out'
    target.mkdir()
    (target / 'notes.md').write_text('deployed to build-host-07 for {}\n'.format(TERM))
    r = egress('scan', str(target), env=env)
    assert r.returncode == 2 and 'refusing to pass blind' in r.stdout   # configured but missing
    (conf / 'patterns.txt').write_text('hostname\t\\bbuild-host-\\d+\\b\n')
    r = egress('scan', str(target), env=env)
    assert r.returncode == 2 and '[hostname]' in r.stdout and '[term]' not in r.stdout
    (conf / 'terms.txt').write_text(TERM + '\n')
    r = egress('scan', str(target), env=env)
    assert '[term]' in r.stdout
    assert egress('check-text', env=env, input='a harmless post').returncode == 0
    assert egress('check-text', env=env, input='hello ' + TERM).returncode == 2
    assert egress('self-test', env=env).returncode == 0
    assert egress(env=env).returncode == 1


def test_egress_gate_masks_only_the_ciphertext_field(tmp_path):
    """Provider-encrypted reasoning (a Fernet token under "encrypted_content") spells key prefixes by
    chance and is masked; the same text in any other field is still scanned."""
    out = tmp_path / 'out'
    out.mkdir()
    blob = 'gAAAAA' + 'Q' * 10 + '-sk-' + 'A' * 60
    (out / 'rollout.jsonl').write_text('{"encrypted_content":"' + blob + '"}\n')
    env = {'HOME': str(tmp_path)}
    assert egress('scan', str(out), env=env).returncode == 0
    (out / 'rollout.jsonl').write_text('{"text":"' + blob + '"}\n')
    r = egress('scan', str(out), env=env)
    assert r.returncode == 2 and '[api-key]' in r.stdout


def test_egress_gate_scan_honours_scoped_allow_rules(tmp_path):
    conf = tmp_path / 'egress'
    conf.mkdir()
    (conf / 'patterns.txt').write_text('# none\n')
    (conf / 'terms.txt').write_text(TERM + '\n')
    env = {'RSTACK_EGRESS_DIR': str(conf)}
    stage = tmp_path / 'stage'
    (stage / 'docs').mkdir(parents=True)
    (stage / 'docs' / 'about.md').write_text('the {} release\n'.format(TERM))
    (stage / 'other.md').write_text('also {}\n'.format(TERM))
    real = os.path.realpath(str(stage))

    # a rule scoped to the staging directory passes only the path it names
    (conf / 'allow.txt').write_text('{}\tterm\tdocs/*\tdecided public\n'.format(real))
    r = egress('scan', str(stage), env=env)
    assert r.returncode == 2 and 'other.md' in r.stdout and 'about.md' not in r.stdout
    (stage / 'other.md').write_text('nothing\n')
    r = egress('scan', str(stage), env=env)
    assert r.returncode == 0 and '1 signal(s) passed by scoped rules' in r.stdout

    # the rule is scoped: the same content in another directory still blocks
    elsewhere = tmp_path / 'elsewhere' / 'docs'
    elsewhere.mkdir(parents=True)
    (elsewhere / 'about.md').write_text('the {} release\n'.format(TERM))
    assert egress('scan', str(elsewhere.parent), env=env).returncode == 2
    # and a parent directory does not inherit the child's rule
    assert egress('scan', str(tmp_path), env=env).returncode == 2

    # inside a git work tree, the tree's own rules apply with paths relative to its top
    repo = tmp_path / 'repo'
    (repo / 'site').mkdir(parents=True)
    git('init', '-q', '-b', 'main', cwd=repo)
    (repo / 'site' / 'index.md').write_text('{} home\n'.format(TERM))
    assert egress('scan', str(repo / 'site'), env=env).returncode == 2
    (conf / 'allow.txt').write_text('*/repo\tterm\tsite/index.md\tdecided public\n')
    r = egress('scan', str(repo / 'site'), env=env)
    assert r.returncode == 0, r.stdout


def test_egress_gate_pre_push(tmp_path):
    conf = tmp_path / 'egress'
    conf.mkdir()
    (conf / 'patterns.txt').write_text('# none of mine\n')
    (conf / 'terms.txt').write_text(TERM + '\n')
    (conf / 'agent-files.gitignore').write_text('HANDOFF*.md\n')
    env = {'RSTACK_EGRESS_DIR': str(conf)}
    repo = tmp_path / 'repo'
    repo.mkdir()
    git('init', '-q', '-b', 'main', cwd=repo)
    (repo / 'a.txt').write_text('public\n')
    git('add', '.', cwd=repo)
    git('commit', '-qm', 'clean', cwd=repo)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(repo), capture_output=True,
                          text=True).stdout.strip()
    refs = 'refs/heads/main {} refs/heads/main {}\n'.format(head, '0' * 40)
    r = egress('pre-push', 'origin', 'https://example.invalid/r.git', env=env, input=refs, cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr

    (repo / 'HANDOFF.md').write_text('notes\n')
    (repo / 'b.txt').write_text('about ' + TERM + '\n')
    git('add', '.', cwd=repo)
    git('commit', '-qm', 'more', cwd=repo)
    new = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(repo), capture_output=True,
                         text=True).stdout.strip()
    refs = 'refs/heads/main {} refs/heads/main {}\n'.format(new, head)
    r = egress('pre-push', 'origin', 'https://example.invalid/r.git', env=env, input=refs, cwd=repo)
    assert r.returncode == 2 and '[agent-file]' in r.stdout and '[term]' in r.stdout

    (conf / 'allow.txt').write_text('*\tterm\tb.txt\tdecided public\n*\tagent-file\tHANDOFF.md\tok\n')
    r = egress('pre-push', 'origin', 'https://example.invalid/r.git', env=env, input=refs, cwd=repo)
    assert r.returncode == 0, r.stdout


# -------------------------------------------------------------------------------- clean-room

def fake_agent(tmp_path, name):
    p = tmp_path / 'bin' / name
    p.parent.mkdir(exist_ok=True)
    p.write_text('#!/bin/bash\nenv | sort\necho "ARGS=$*"\n')
    p.chmod(0o755)
    return p


def room_env(out):
    return dict(l.split('=', 1) for l in out.splitlines() if '=' in l)


def test_clean_room_codex_gets_an_empty_identity(tmp_path):
    home = tmp_path / 'home'
    (home / '.codex').mkdir(parents=True)
    (home / '.codex/auth.json').write_text('{}')
    bin_ = fake_agent(tmp_path, 'codex')
    r = run(['/bin/bash', str(TOOLS / 'clean-room'), '--', 'codex', 'exec', 'hi'],
            env={'HOME': str(home), 'CLEAN_ROOM_CODEX_BIN': str(bin_),
                 'CLEAN_ROOM_BASE': str(tmp_path / 'rooms'), 'PRIVATE_SESSION_VAR': 'leak'})
    assert r.returncode == 0, r.stderr
    e = room_env(r.stdout)
    assert 'PRIVATE_SESSION_VAR' not in e, 'the calling environment leaked into the room'
    assert e['HOME'].startswith(str(tmp_path / 'rooms')) and e['HOME'].endswith('/home')
    room = Path(e['CODEX_HOME'])
    assert (room / 'auth.json').is_symlink() and e['ARGS'] == 'exec hi'


def test_clean_room_claude_needs_a_token_and_excludes_ancestors(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    bin_ = fake_agent(tmp_path, 'claude')
    base = {'HOME': str(home), 'CLEAN_ROOM_CLAUDE_BIN': str(bin_),
            'CLEAN_ROOM_BASE': str(tmp_path / 'rooms')}
    r = run(['/bin/bash', str(TOOLS / 'clean-room'), '--', 'claude', '-p', 'x'], env=base)
    assert r.returncode == 2 and 'no Claude token' in r.stderr
    tok = tmp_path / 'tok'
    tok.write_text('tok-value')
    r = run(['/bin/bash', str(TOOLS / 'clean-room'), '--', 'claude', '-p', 'x'],
            env=dict(base, CLEAN_ROOM_CLAUDE_TOKEN_FILE=str(tok)))
    assert r.returncode == 0, r.stderr
    e = room_env(r.stdout)
    assert e['CLAUDE_CODE_OAUTH_TOKEN'] == 'tok-value'
    settings = json.loads((Path(e['CLAUDE_CONFIG_DIR']) / 'settings.json').read_text())
    assert str(home) + '/CLAUDE.md' in settings['claudeMdExcludes']
    assert 'tok-value' not in (Path(e['CLAUDE_CONFIG_DIR']) / 'settings.json').read_text()
    assert run(['/bin/bash', str(TOOLS / 'clean-room'), '--', 'vim'], env=base).returncode == 2


def test_clean_room_collect_drops_auth_and_runs_the_gate(tmp_path):
    root = tmp_path / 'room'
    (root / 'codex/sessions').mkdir(parents=True)
    (root / 'codex/sessions/run.jsonl').write_text('{"ok": true}\n')
    (root / 'codex/sessions/auth.json').write_text('{"secret": 1}')
    out = tmp_path / 'out'
    r = run(['/bin/bash', str(TOOLS / 'clean-room'), '--collect', str(root), str(out)],
            env={'HOME': str(tmp_path)})
    assert r.returncode == 0 and 'PASS' in r.stdout, r.stdout + r.stderr
    assert not list(out.rglob('auth.json'))


# ------------------------------------------------------------------------------- reload-lint

def lint(*args, env=None, cwd=None):
    return py('reload-lint.py', *args, env=env or {}, cwd=cwd)


def test_reload_lint_does_nothing_without_terms_and_says_so(tmp_path):
    f = tmp_path / 'CLAUDE.md'
    f.write_text('{} run-104\n'.format(TERM))
    r = lint('--files', str(f))
    assert r.returncode == 0 and 'nothing was checked' in r.stderr


def test_reload_lint_fires_on_co_occurrence_only(tmp_path):
    env = {'RSTACK_TERMS_FILE': str(terms_file(tmp_path))}
    f = tmp_path / 'index.md'
    f.write_text('the {} postmortem is in its repo\n'      # term alone: fine
                 'run-104 finished\n'                       # marker alone: fine
                 .format(TERM))
    assert lint('--files', str(f), env=env).returncode == 0
    f.write_text('{} results: run-104 best so far\n'.format(TERM))
    r = lint('--files', str(f), env=env)
    assert r.returncode == 1 and 'run id' in r.stderr and '1 configured term' in r.stderr
    assert TERM not in r.stderr, 'the lint output lands in the context it protects'
    assert 'best so far' not in r.stderr
    f.write_text('see TKT-123456\n')
    assert lint('--files', str(f), env=env).returncode == 1         # standalone


def test_reload_lint_refuses_on_an_unusable_terms_file(tmp_path):
    f = tmp_path / 'CLAUDE.md'
    f.write_text('fine\n')
    assert lint('--files', str(f), env={'RSTACK_TERMS_FILE': str(tmp_path / 'gone')}).returncode == 1
    bad = terms_file(tmp_path, 'marker no-equals-sign\n')
    assert lint('--files', str(f), '--terms', str(bad)).returncode == 1
    only_terms = terms_file(tmp_path, TERM + '\n')
    r = lint('--files', str(f), '--terms', str(only_terms))
    assert r.returncode == 0 and 'no markers' in r.stderr


def test_reload_lint_checks_staged_additions(tmp_path):
    env = {'RSTACK_TERMS_FILE': str(terms_file(tmp_path))}
    repo = tmp_path / 'repo'
    repo.mkdir()
    git('init', '-q', cwd=repo)
    (repo / 'AGENTS.md').write_text('old line {} run-104\n'.format(TERM))   # already committed
    git('add', '.', cwd=repo)
    git('commit', '-qm', 'x', cwd=repo)
    (repo / 'AGENTS.md').write_text('old line {} run-104\nnew harmless line\n'.format(TERM))
    git('add', '.', cwd=repo)
    assert lint(env=env, cwd=repo).returncode == 0                  # only additions are judged
    (repo / 'AGENTS.md').write_text('old line {} run-104\n{} run-105\n'.format(TERM, TERM))
    git('add', '.', cwd=repo)
    r = lint(env=env, cwd=repo)
    assert r.returncode == 1 and 'AGENTS.md:2' in r.stderr
    assert lint('--all', env=env, cwd=repo).returncode == 1


def test_no_tool_ships_a_term_list():
    for f in TOOLS.iterdir():
        if f.is_file():
            assert 'FALLBACK_TERMS' not in f.read_text(errors='replace'), f.name


def test_hook_audit_reports_a_guard_that_crashes(tmp_path):
    crash = tmp_path / 'crash.py'
    crash.write_text('import json, sys\nd = json.load(sys.stdin)\nprint(d["tool_input"]["command"])\n')
    refuse = tmp_path / 'refuse.py'
    refuse.write_text('import json, sys\nprint(json.dumps({"hookSpecificOutput": {"permissionDecision": "deny"}}))\n')
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({'hooks': {'PreToolUse': [
        {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': '{} {}'.format(sys.executable, crash)}]},
        {'matcher': 'mcp__x__send|Other', 'hooks': [{'type': 'command', 'command': '{} {}'.format(sys.executable, refuse)}]}],
        'PostToolUse': [{'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'false'}]}]}}))
    r = py('hook-audit', str(settings))
    assert r.returncode == 1
    assert 'CRASHES  [Bash]' in r.stdout and 'refuses  [mcp__x__send]' in r.stdout
    assert 'false' not in r.stdout, 'only PreToolUse guards run'
    rows = json.loads(py('hook-audit', str(settings), '--json').stdout)
    assert {r['result'] for r in rows if 'refuse' in r['command']} == {'refused'}


def test_event_watch_match_regex_is_the_rest_of_the_line(watch, tmp_path):
    """friends-nsplan, 11-11: `match F (exit [1-9]|refused)` was split at the space and failed to
    compile; the `\\s` workaround lost its backslash to shlex and matched the letter s."""
    conf, state, env = watch
    log = tmp_path / 'job log.txt'
    log.write_text('')
    (conf / 'j.conf').write_text('match "{}" (exit [1-9]|refused)\nmatch "{}" job\\sdone\n'.format(log, log))
    assert py('event-watch', 'scan', 'j', env=env).returncode == 0
    with open(log, 'a') as f:
        f.write('worker exit 3\nsss\njob done\n')
    woke = py('event-watch', 'wait', 'j', '--max-hours', '0', env=env)
    lines = sorted(json.loads(l)['line'] for l in woke.stdout.splitlines())
    assert lines == ['job done', 'worker exit 3'], woke.stdout + woke.stderr
