"""readme-blocks: README numbers come from their source, and a stale one fails (11-13: 8 stale READMEs)."""
import json
import os
import subprocess
import sys

from rstack_hookcall import TOOLS

TOOL = TOOLS / 'readme-blocks'
README = ('# Demo\n\nWe found <!-- auto:holds -->0<!-- /auto --> new results.\n\n'
          'Latest:\n<!-- auto:latest -->\nnone yet\n<!-- /auto -->\n\n'
          'Merged PRs: <!-- auto:merged -->?<!-- /auto -->\n')


def setup(tmp_path, rows=None):
    lane = tmp_path / 'lanes/demo'
    lane.mkdir(parents=True)
    rows = rows if rows is not None else [
        dict(utc='2026-01-01T00:00:00+00:00', new=True, referee='HOLDS', what='bound A'),
        dict(utc='2026-01-02T00:00:00+00:00', new=False, referee='NONE', what='rerun B'),
        dict(utc='2026-01-03T00:00:00+00:00', new=True, referee='HOLDS', what='bound C')]
    (lane / 'RESULTS.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (tmp_path / 'README.md').write_text(README)
    (tmp_path / 'readme-blocks.json').write_text(json.dumps({'blocks': {
        'holds': {'source': 'jsonl', 'path': 'lanes/demo/RESULTS.jsonl', 'where': {'new': True, 'referee': 'HOLDS'}},
        'latest': {'source': 'jsonl', 'path': 'lanes/demo/RESULTS.jsonl', 'where': {'new': True},
                   'latest': 'what', 'format': '{value} ({utc})'},
        'merged': {'source': 'gh-prs', 'author': 'some-author', 'repo': 'example/demo', 'state': 'merged'}}}))
    gh = tmp_path / 'fake-gh'
    gh.write_text('#!/bin/sh\necho "$@" >> "{}"\necho 7\n'.format(tmp_path / 'gh-calls'))
    gh.chmod(0o755)
    return dict(os.environ, READMEBLOCKS_GH=str(gh))


def run(tmp_path, env, *args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=env, cwd=str(tmp_path))


def test_check_names_each_stale_block_and_changes_nothing(tmp_path):
    env = setup(tmp_path)
    r = run(tmp_path, env, 'check', 'README.md')
    assert r.returncode == 1
    assert all('block "{}"'.format(n) in r.stdout for n in ('holds', 'latest', 'merged'))
    assert (tmp_path / 'README.md').read_text() == README


def test_render_writes_the_numbers_from_their_sources_then_check_passes(tmp_path):
    env = setup(tmp_path)
    assert run(tmp_path, env, 'render', 'README.md').returncode == 0
    text = (tmp_path / 'README.md').read_text()
    assert 'We found <!-- auto:holds -->2<!-- /auto --> new results.' in text
    assert '<!-- auto:latest -->\nbound C (2026-01-03T00:00:00+00:00)\n<!-- /auto -->' in text
    assert 'Merged PRs: <!-- auto:merged -->7<!-- /auto -->' in text
    q = (tmp_path / 'gh-calls').read_text()
    assert 'is:merged' in q and 'author:some-author' in q and 'repo:example/demo' in q
    assert run(tmp_path, env, 'check', 'README.md').returncode == 0


def test_an_unreadable_source_fails_closed_and_render_leaves_that_block(tmp_path):
    env = setup(tmp_path)
    run(tmp_path, env, 'render', 'README.md')
    rendered = (tmp_path / 'README.md').read_text()
    (tmp_path / 'lanes/demo/RESULTS.jsonl').unlink()
    r = run(tmp_path, env, 'check', 'README.md')
    assert r.returncode == 2 and 'cannot read' in r.stderr
    r = run(tmp_path, env, 'render', 'README.md')
    assert r.returncode == 2 and (tmp_path / 'README.md').read_text() == rendered
    env['READMEBLOCKS_GH'] = '/bin/false'
    assert run(tmp_path, env, 'check', 'README.md').returncode == 2


def test_a_block_with_no_config_entry_or_no_close_is_an_error(tmp_path):
    env = setup(tmp_path)
    (tmp_path / 'README.md').write_text('x <!-- auto:nobody -->1<!-- /auto -->\n')
    r = run(tmp_path, env, 'check', 'README.md')
    assert r.returncode == 2 and 'no entry' in r.stderr
    (tmp_path / 'README.md').write_text('x <!-- auto:holds -->1\n')
    assert run(tmp_path, env, 'check', 'README.md').returncode == 2


def test_with_row_counts_a_row_not_yet_in_the_ledger(tmp_path):
    env = setup(tmp_path)
    run(tmp_path, env, 'render', 'README.md')
    ledger = tmp_path / 'lanes/demo/RESULTS.jsonl'
    row = json.dumps(dict(utc='2026-02-01T00:00:00+00:00', new=True, referee='HOLDS', what='bound D'))
    r = run(tmp_path, env, 'render', 'README.md', '--stdout', '--with-row', '{}={}'.format(ledger, row))
    assert '<!-- auto:holds -->3<!-- /auto -->' in r.stdout and 'bound D' in r.stdout
    assert run(tmp_path, env, 'check', 'README.md', '--with-row', '{}={}'.format(ledger, row)).returncode == 1
    assert '<!-- auto:holds -->2<!-- /auto -->' in (tmp_path / 'README.md').read_text()


def test_a_command_source_and_an_explicit_config(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/R.md').write_text('v<!-- auto:v -->old<!-- /auto -->\n')
    cfg = tmp_path / 'blocks.json'
    cfg.write_text(json.dumps({'blocks': {'v': {'source': 'command', 'run': 'echo 1.2.3'}}}))
    r = run(tmp_path, dict(os.environ), 'render', 'docs/R.md', '--config', str(cfg))
    assert r.returncode == 0 and (tmp_path / 'docs/R.md').read_text() == 'v<!-- auto:v -->1.2.3<!-- /auto -->\n'
    cfg.write_text(json.dumps({'blocks': {'v': {'source': 'command', 'run': 'exit 3'}}}))
    assert run(tmp_path, dict(os.environ), 'check', 'docs/R.md', '--config', str(cfg)).returncode == 2
