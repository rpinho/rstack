"""Shared receipt/promote/launch integration; every network operation is mocked."""
import io
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.error
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rh
import idea_policy

spec = importlib.util.spec_from_file_location('shared_receipt', ROOT / 'tools/prior_art_receipt.py')
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)
LAUNCH = Path(__file__).resolve().parents[2] / 'tools/launch.sh'


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected network/subprocess search')
    monkeypatch.setattr(receipt.urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(receipt, '_gh', forbidden)
    # The paper chain caches on disk and shares a quota between lanes through files. Point both
    # at this test's own directory: otherwise these tests would write to the real cache, and the
    # second test to ask for a query would pass on a cache hit instead of exercising the search.
    monkeypatch.setenv('RH_PAPER_CACHE', str(tmp_path / 'paper-cache'))
    monkeypatch.delenv('RH_PAPER_CONTACT', raising=False)


def response(data):
    return io.StringIO(json.dumps(data))


@pytest.mark.parametrize('code,retry_after', [(429, '37971'), (429, '0'), (503, '37971')])
def test_rate_limited_openalex_falls_through_to_the_next_source(monkeypatch, code, retry_after):
    # 11-07: Semantic Scholar, Europe PMC and arXiv now sit between OpenAlex and Crossref, so a
    # spent OpenAlex allowance costs one more request rather than the whole chain. The receipt
    # records which source answered, and nothing waits for a ten-hour quota reset.
    calls = []
    def urlopen(req, timeout):
        calls.append(req.full_url)
        if 'api.openalex.org' in req.full_url:
            raise urllib.error.HTTPError(req.full_url, code, 'limited', {'retry-after': retry_after}, None)
        assert 'api.semanticscholar.org' in req.full_url
        return response({'data': [{'paperId': 'p', 'externalIds': {'DOI': '10.1234/example'}},
                                  {'paperId': 'q', 'externalIds': {}}]})
    monkeypatch.setattr(receipt.urllib.request, 'urlopen', urlopen)
    sleep = Mock(side_effect=AssertionError('fallback must not wait for quota reset'))
    monkeypatch.setattr('time.sleep', sleep)
    assert receipt.papers('a harmless query', 2) == [
        'https://doi.org/10.1234/example', 'https://www.semanticscholar.org/paper/q']
    assert len(calls) == 2
    assert receipt.PAPER_SRC[0] == 'Semantic Scholar'
    assert f'OpenAlex: HTTP {code}' in receipt.PAPER_NOTE[0]
    sleep.assert_not_called()


def test_crossref_is_still_the_last_resort(monkeypatch):
    hosts = ['api.openalex.org', 'api.semanticscholar.org', 'ebi.ac.uk', 'export.arxiv.org']
    def urlopen(req, timeout):
        if any(h in req.full_url for h in hosts):
            raise urllib.error.HTTPError(req.full_url, 429, 'limited', {'retry-after': '600'}, None)
        assert 'api.crossref.org' in req.full_url
        return response({'message': {'items': [{'DOI': '10.1234/example'}, {'title': ['no DOI']}]}})
    monkeypatch.setattr(receipt.urllib.request, 'urlopen', urlopen)
    assert receipt.papers('a harmless query', 2) == ['https://doi.org/10.1234/example']
    assert receipt.PAPER_SRC[0] == 'Crossref'


def test_paper_failure_does_not_invent_results(monkeypatch):
    monkeypatch.setattr(receipt.urllib.request, 'urlopen', Mock(side_effect=urllib.error.HTTPError('url', 403, 'denied', {}, None)))
    with pytest.raises(urllib.error.HTTPError):
        receipt.papers('query')


def mock_searches(monkeypatch):
    def urlopen(req, timeout):
        url = req.full_url
        if 'api.openalex.org' in url:
            return response({'results': [{'doi': 'https://doi.org/10.1234/example'}]})
        assert 'huggingface.co/api/' in url
        return response([{'id': 'fixture/benchmark'}])
    monkeypatch.setattr(receipt.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(receipt, '_gh', lambda q, n: subprocess.CompletedProcess([], 0, 'https://github.com/fixture/repo\n', ''))


def capture(tmp_path, monkeypatch, key='topic'):
    monkeypatch.setattr(receipt, 'Q', tmp_path)
    cap = tmp_path / 'x_capture' / (key + '.jsonl')
    cap.parent.mkdir(exist_ok=True)
    cap.write_text(json.dumps({'query': 'recorded browser query', 'source_url': 'https://x.com/fixture/status/1',
                               'captured_at': '2026-01-01T00:00:00+00:00'}) + '\n')
    return cap


@pytest.mark.parametrize('paper_query', [None, 'specific paper query'])
def test_team_caller_cli_and_receipt_append(tmp_path, monkeypatch, paper_query):
    # promote_new.py supplies --paper-query conditionally; freeze_live.py always supplies it.
    mock_searches(monkeypatch)
    cap = capture(tmp_path, monkeypatch)
    md = tmp_path / 'prior art.md'
    md.write_text('# Existing notes\n\nKeep this narrative.\n')
    argv = ['topic', str(md), '--baseline', 'Method A, score 42', '--query', 'topic query']
    if paper_query is not None:
        argv += ['--paper-query', paper_query]
    assert receipt.main(argv) == 0
    assert receipt.main(argv) == 0  # replaces existing block without duplicating it
    assert md.read_text().count('```rh-prior-art') == 1
    assert 'Keep this narrative.' in md.read_text()
    assert idea_policy.prior_art(md)['baseline'] == 'Method A, score 42'
    data = json.loads(md.read_text().split('```rh-prior-art\n')[1].split('\n```')[0])
    assert data['sources']['papers']['query'] == (paper_query or 'topic query')
    frozen = Path(data['sources']['x']['capture_path'])
    assert frozen.read_bytes() == cap.read_bytes()
    cap.write_text('later browser capture\n')
    assert idea_policy.prior_art(md)  # immutable copy remains valid


def test_missing_x_is_explicit_and_still_blocks_promotion(tmp_path, monkeypatch):
    mock_searches(monkeypatch)
    monkeypatch.setattr(receipt, 'Q', tmp_path)
    md = tmp_path / 'prior.md'
    assert receipt.main(['theory-key', str(md), '--baseline', 'method 42', '--query', 'query']) == 0
    assert 'no capture for theory-key' in md.read_text()
    assert '"status": "skipped"' in md.read_text()
    assert not (tmp_path / 'x_capture').exists()
    with pytest.raises(ValueError, match='prior-art x:'):
        idea_policy.prior_art(md)


def test_failed_fetch_leaves_prior_art_unchanged(tmp_path, monkeypatch):
    md = tmp_path / 'prior.md'
    md.write_text('existing narrative')
    monkeypatch.setattr(receipt, 'Q', tmp_path)
    with pytest.raises(AssertionError, match='unexpected network'):
        receipt.main(['key', str(md), '--baseline', 'method 42', '--query', 'query'])
    assert md.read_text() == 'existing narrative'


def test_rh_receipt_is_thin_wrapper(tmp_path, monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 7))
    monkeypatch.setattr(rh.subprocess, 'run', run)
    assert rh.main(['prior-art', 'receipt', 'key', str(tmp_path/'pa.md'), '--baseline', 'method 42',
                    '--query', 'repo query', '--paper-query', 'paper query']) == 7
    assert run.call_args.args[0] == [sys.executable, str(ROOT/'tools/prior_art_receipt.py'),
                                     'key', str(tmp_path/'pa.md'), '--baseline', 'method 42',
                                     '--query', 'repo query', '--paper-query', 'paper query']


def test_promote_hint_is_exact_shell_command_and_does_not_promote(tmp_path, capsys):
    lane = tmp_path/'lanes/test'
    lane.mkdir(parents=True)
    (lane/'INTAKE.toml').write_text('keywords = []\n')
    row = rh.new_idea('internal', '', "query with 'quotes' and $(no-command)", 'fixture')
    rh.append(lane/'IDEAS.jsonl', row)
    md = tmp_path/'prior art.md'
    md.write_text('Narrative with no receipt')
    before = (lane/'IDEAS.jsonl').read_bytes()
    rc = rh.main(['--root', str(tmp_path), 'ideas', 'promote', 'test', row['id'], '--prior-art', str(md)])
    assert rc == 2
    err = capsys.readouterr().err
    command = next(line.removeprefix('Run: ') for line in err.splitlines() if line.startswith('Run: '))
    assert shlex.split(command) == ['rh', 'prior-art', 'receipt', row['id'], str(md), '--baseline',
                                      'BEST_PUBLIC_METHOD_AND_NUMBER', '--query', row['claim']]
    assert (lane/'IDEAS.jsonl').read_bytes() == before


def test_show_unique_id_and_ambiguous_prefix(tmp_path, capsys):
    for name, key, status in [('theory', 'abc-1', 'testing'), ('orbits', 'abc-2', 'new')]:
        lane = tmp_path/'lanes'/name
        lane.mkdir(parents=True)
        rh.append(lane/'IDEAS.jsonl', dict(id=key, status=status))
    assert rh.main(['--root', str(tmp_path), 'ideas', 'show', 'abc-1']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'testing' and shown['lane'] == 'theory'
    assert rh.main(['--root', str(tmp_path), 'ideas', 'show', 'abc-']) == 2
    assert '2 matches' in capsys.readouterr().err
    assert rh.main(['--root', str(tmp_path), 'ideas', 'show', 'missing']) == 2


@pytest.mark.parametrize('output,rc', [('{"id":"idea-1","status":"new"}', 0),
    ('{"id":"idea-1","status":"closed"}', 0), ('not JSON', 0), ('[]', 0),
    ('{"id":"other","status":"testing"}', 0), ('{"id":"idea-1","status":"testing"}', 2)])
def test_launch_refuses_unpromoted_before_any_launch_side_effect(tmp_path, output, rc):
    fake = tmp_path/'rh'
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_RH_ARGS"\n'
                    'printf "%s\\n" "$FAKE_RH_OUTPUT"\nexit "$FAKE_RH_RC"\n')
    fake.chmod(0o755)
    args_file = tmp_path/'args'
    env = dict(os.environ, PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],
               LAUNCH_IDEA='idea-1', LAUNCH_IDEA_ROOT=str(tmp_path/'isolated root'),
               FAKE_RH_ARGS=str(args_file), FAKE_RH_OUTPUT=output, FAKE_RH_RC=str(rc),
               LAUNCH_STATE=str(tmp_path/'jobs'))
    result = subprocess.run(['zsh', '-f', str(LAUNCH), 'test-job', str(tmp_path/'missing-dir')],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 78
    assert 'not promoted' in result.stderr
    assert args_file.read_text().splitlines() == ['--root', str(tmp_path/'isolated root'), 'ideas', 'show', 'idea-1']
    assert not (tmp_path/'jobs').exists()


@pytest.mark.parametrize('idea', ['', 'idea-1'])
def test_launch_without_opt_in_or_with_promoted_idea_continues(tmp_path, idea):
    fake = tmp_path/'rh'
    fake.write_text('#!/bin/sh\nprintf "%s\\n" called > "$FAKE_RH_ARGS"\n'
                    'printf \'%s\\n\' \'{"id":"idea-1","status":"testing"}\'\n')
    fake.chmod(0o755)
    args_file = tmp_path/'args'
    env = dict(os.environ, PATH=str(tmp_path)+os.pathsep+os.environ['PATH'], LAUNCH_IDEA=idea,
               LAUNCH_IDEA_ROOT='', FAKE_RH_ARGS=str(args_file))
    result = subprocess.run(['zsh', '-f', str(LAUNCH), 'test-job', str(tmp_path/'missing-dir')],
                            env=env, capture_output=True, text=True)
    # Deliberate nonexistent working directory stops safely after the optional check.
    assert result.returncode == 1 and 'REFUSED' not in result.stderr
    assert args_file.exists() == bool(idea)
