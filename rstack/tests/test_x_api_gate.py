"""The gate only executes admitted requests; every decision and outcome is accounted for."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

import pytest

from rstack_hookcall import HOOKS, TOOLS, allowed, blocked


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(TOOLS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


policy = load('xurl-policy')
reconcile = load('x-usage-reconcile')
FIXTURES = Path(__file__).parent / 'fixtures/x-api'


@pytest.fixture
def gate(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith(('XURL_', 'X_USAGE_')):
            monkeypatch.delenv(key)
    stub = tmp_path / 'real-xurl'
    stub.write_text('#!{}\nimport json, os, sys\n'
                    'with open(os.environ["STUB_CALLS"], "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                    'sys.stdout.write(os.environ.get("STUB_OUTPUT", \'{{"data":[{{}},{{}}]}}\\n\'))\n'
                    'sys.stderr.write(os.environ.get("STUB_ERROR", ""))\n'
                    'sys.exit(int(os.environ.get("STUB_RC", "0")))\n'.format(sys.executable))
    stub.chmod(0o755)
    cfg = tmp_path / 'policy.json'
    ledger = tmp_path / 'ledger.jsonl'
    data = {'owner_id': '00000', 'ledger_path': str(ledger), 'real_binary': str(stub),
            'sync_lock': str(tmp_path / 'lock')}
    cfg.write_text(json.dumps(data))
    monkeypatch.setenv('XURL_POLICY_CONFIG', str(cfg))
    monkeypatch.setenv('RSTACK_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('STUB_CALLS', str(tmp_path / 'calls'))
    return cfg, ledger, data


def invoke(*args):
    return subprocess.run([str(TOOLS / 'xurl'), *args], capture_output=True, text=True, timeout=20)


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize('args', [
    [], ['auth', 'status'], ['version'], ['--help'], ['help'], ['-h'],
    ['/2/users/00000/bookmarks?max_results=100'],
    ['https://api.twitter.com/2/users/00000/bookmarks'],
    ['-X', 'POST', '/2/tweets', '-d', '{"text":"fixture"}'],
    ['--method=POST', '/2/tweets'], ['-XDELETE', '/2/tweets/00001'],
    ['-X', 'POST', '/2/dm_conversations/00001/messages'],
    ['media', 'upload', 'fixture.png'], ['/2/usage'], ['/2/usage/tweets?days=7'],
    # 11-17: xr puts `-u ACCOUNT` first; x-post-ready's upload was refused as "expected one API endpoint".
    ['-u', 'fixture_acct', 'media', 'upload', '--category', 'tweet_image', '--media-type', 'image/png', 'fixture.png'],
    ['-u', 'fixture_acct', 'media', 'status', '00001'],
])
def test_allow_classes_execute_and_record_outcome(gate, args):
    result = invoke(*args)
    assert result.returncode == 0, result.stderr
    assert result.stdout == '{"data":[{},{}]}\n'
    decision, outcome = rows(gate[1])
    assert decision['decision'] == 'ALLOW'
    assert outcome['type'] == 'outcome' and outcome['call_id'] == decision['call_id']
    local = not args or args[0] in policy.LOCAL
    assert outcome['items_returned'] == (None if local else 2) and outcome['exit_code'] == 0
    assert outcome['http_outcome'] == ('local' if local else 'success')
    assert 'caller' in decision and 'cwd' in decision


@pytest.mark.parametrize('args', [
    ['/2/tweets/00001'], ['/2/users/00001'], ['/2/tweets/search/recent?query=fixture'],
    ['/2/users/00000/mentions'], ['-X', 'POST', '/2/users/00000/likes'],
    ['-X', 'POST', '/2/users/00000/following'], ['/2/users/00001/bookmarks'],
    ['/2/users/00000/tweets'], ['/2/tweets/counts/recent'], ['/2/lists/00001/tweets'],
    ['search', 'fixture'], ['/2/usage-not-a-real-endpoint'],
    ['/2/users/00000/bookmarks', '-d', '{}'], ['/2/usage/tweets', '--data={}'],
    ['/2/tweets', '-d{}'], ['-X', 'GET', '/2/users/00000/bookmarks', '--data', '{}'],
    ['-H', '/2/users/00000/bookmarks', '/2/tweets/00001'],
    ['/2/users/00000/bookmarks', '/2/tweets/00001'],
    ['-u', 'fixture_acct', '/2/tweets/00001'], ['-u', 'media', '/2/tweets/00001'],
])
def test_block_classes_never_execute_and_log_exit_86(gate, args):
    result = invoke(*args)
    assert result.returncode == 86, result.stderr
    assert [r['decision'] for r in rows(gate[1])] == ['BLOCK']
    assert not Path(os.environ['STUB_CALLS']).exists()


def test_missing_or_malformed_config_blocks_even_override(gate, monkeypatch):
    cfg, ledger, _ = gate
    monkeypatch.setenv('XURL_LEDGER', str(ledger))
    monkeypatch.setenv('XURL_ALLOW_REASON', 'fixture exception')
    monkeypatch.setenv('XURL_POLICY_CONFIG', str(cfg.with_name('missing.json')))
    assert invoke('/2/usage/tweets').returncode == 86
    cfg.write_text('not JSON')
    monkeypatch.setenv('XURL_POLICY_CONFIG', str(cfg))
    assert invoke('/2/users/00000/bookmarks').returncode == 86
    assert len(rows(ledger)) == 2 and all(r['decision'] == 'BLOCK' for r in rows(ledger))


def test_env_configuration_and_logged_override(gate, monkeypatch):
    cfg, ledger, data = gate
    monkeypatch.setenv('XURL_POLICY_CONFIG', str(cfg.with_name('missing.json')))
    for key, env in policy.ENV.items():
        if key in data:
            monkeypatch.setenv(env, data[key])
    monkeypatch.setenv('XURL_ALLOW_REASON', 'fixture one-off lookup')
    assert invoke('/2/tweets/00001').returncode == 0
    assert rows(ledger)[0]['why'] == 'override: fixture one-off lookup'


def test_http_error_output_and_exit_code_are_preserved(gate, monkeypatch):
    monkeypatch.setenv('STUB_RC', '1')
    monkeypatch.setenv('STUB_OUTPUT', '{"status":429,"title":"Too Many Requests"}\n')
    monkeypatch.setenv('STUB_ERROR', 'fixture stderr\n')
    result = invoke('/2/usage/tweets')
    assert result.returncode == 1 and result.stderr == 'fixture stderr\n'
    outcome = rows(gate[1])[1]
    assert outcome['http_status'] == 429 and outcome['http_outcome'] == 'error'
    assert outcome['items_returned'] is None


def test_local_command_with_no_config_and_policy_cli(gate, monkeypatch):
    cfg, ledger, data = gate
    monkeypatch.setenv('XURL_POLICY_CONFIG', str(cfg.with_name('missing.json')))
    monkeypatch.setenv('XURL_REAL_BINARY', data['real_binary'])
    monkeypatch.setenv('XURL_LEDGER', str(ledger))
    assert invoke('version').returncode == 0
    result = subprocess.run([str(TOOLS / 'xurl-policy'), '/2/tweets/00001'], capture_output=True, text=True)
    assert result.returncode == 86 and result.stdout == 'BLOCK\n'


def test_unwritable_ledger_refuses_before_binary(gate):
    cfg, ledger, data = gate
    data['ledger_path'] = str(cfg.parent)  # a directory, not a ledger
    cfg.write_text(json.dumps(data))
    assert invoke('/2/usage/tweets').returncode == 86
    assert not Path(os.environ['STUB_CALLS']).exists()


def test_auth_sync_pull_and_push_only_after_change(gate, monkeypatch):
    cfg, ledger, data = gate
    auth = cfg.with_name('auth')
    auth.write_text('old')
    sync = cfg.with_name('sync')
    sync.write_text('#!{}\nimport sys\nfrom pathlib import Path\n'
                    'with Path({!r}).open("a") as f: f.write(sys.argv[1]+"\\n")\n'.format(
                        sys.executable, str(cfg.with_name('sync-calls'))))
    sync.chmod(0o755)
    data.update(sync_command=[str(sync)], auth_file=str(auth))
    cfg.write_text(json.dumps(data))
    assert invoke('/2/usage/tweets').returncode == 0
    assert cfg.with_name('sync-calls').read_text() == 'pull\n'
    binary = Path(data['real_binary'])
    binary.write_text('#!{}\nfrom pathlib import Path\nPath({!r}).write_text("changed")\n'
                      'print(\'{{"data":[]}}\')\n'.format(sys.executable, str(auth)))
    assert invoke('/2/usage/tweets').returncode == 0
    assert cfg.with_name('sync-calls').read_text() == 'pull\npull\npush\n'


@pytest.mark.parametrize('cmd', ['xurl-bin /2/tweets/00001', 'curl https://api.x.com/2/tweets/00001',
    'python3 -c "import urllib.request; urllib.request.urlopen(\'https://api.twitter.com/2/users/me\')"',
    'grep api.x.com file; curl https://api.x.com/2/tweets/00001',
    'grep "$(xurl-bin /2/tweets/00001)" file'])
def test_hook_blocks_bypasses(cmd):
    blocked(HOOKS / 'x-api-bypass-guard', {'tool_name': 'Bash', 'tool_input': {'command': cmd}})


@pytest.mark.parametrize('cmd', ['grep api.x.com file', 'rg xurl-bin file', 'xurl /2/usage/tweets'])
def test_hook_allows_reads_and_gated_calls(cmd):
    allowed(HOOKS / 'x-api-bypass-guard', {'tool_name': 'Bash', 'tool_input': {'command': cmd}})


def test_hook_malformed_guarded_input_denied_and_wrap_checker_accepts(tmp_path):
    blocked(HOOKS / 'x-api-bypass-guard', '{"tool_input":"xurl-bin"')
    checker = load('hook-wrap-check')
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
        {'type': 'command', 'command': 'python3 {}'.format(HOOKS / 'x-api-bypass-guard')}]}]}}))
    assert [r['state'] for r in checker.check([str(settings)], [], {})] == ['ok']


def decision(date, call_id=None, **extra):
    return dict(utc=date + 'T00:00:00+00:00', decision='ALLOW', method='GET',
                path='/2/users/00000/bookmarks', call_id=call_id, **extra)


def test_reconcile_items_outcomes_fallback_block_and_free_calls(tmp_path):
    ledger = tmp_path / 'ledger'
    entries = [decision('2026-11-11', 'a'), decision('2026-11-11', 'b'),
        {'type': 'outcome', 'call_id': 'a', 'items_returned': 99, 'exit_code': 0},
        {'type': 'outcome', 'call_id': 'b', 'items_returned': 0, 'exit_code': 0},
        decision('2026-11-11'), dict(decision('2026-11-11'), decision='BLOCK'),
        dict(decision('2026-11-11'), why='local'),
        dict(decision('2026-11-11'), path='/2/usage/tweets'),
        decision('2026-11-12', items_returned=100),
        decision('2026-11-12', 'error'),
        {'type': 'outcome', 'call_id': 'error', 'items_returned': None, 'exit_code': 1}]
    ledger.write_text(''.join(json.dumps(row) + '\n' for row in entries))
    assert reconcile.ledger_days([ledger]) == {'2026-11-11': 100, '2026-11-12': 100}
    usage = reconcile.usage_days(json.loads((FIXTURES / 'usage.json').read_text()))
    bad = reconcile.failures(usage, reconcile.ledger_days([ledger]), 25, 20)
    assert [r['day'] for r in bad] == ['2026-11-12', '2026-11-13']


def test_reconcile_margin_boundaries_and_overview_shape():
    assert not reconcile.failures({'2026-11-11': 125}, {'2026-11-11': 100}, 25, 20)
    assert not reconcile.failures({'2026-11-11': 600}, {'2026-11-11': 500}, 25, 20)
    assert reconcile.failures({'2026-11-11': 601}, {'2026-11-11': 500}, 25, 20)
    overview = {'data': {'daily_project_usage': [{'date': '2026-11-11', 'usage': [
        {'tweets_consumed': 10}, {'tweets_consumed': 20}]}]}}
    assert reconcile.usage_days(overview) == {'2026-11-11': 30}
    for value in ({'data': {}}, {'data': {'daily_project_usage': {'usage': []}}}):
        with pytest.raises((ValueError, KeyError)):
            reconcile.usage_days(value)


def test_reconcile_calls_adjacent_gate_and_alerts_once_per_failing_day(gate, monkeypatch):
    cfg, ledger, data = gate
    ledger.write_text('')
    fixture = json.loads((FIXTURES / 'usage.json').read_text())
    monkeypatch.setenv('STUB_OUTPUT', json.dumps(fixture))
    alerts = []
    run = reconcile.subprocess.run
    def stub(argv, **kw):
        if argv[0] == 'tell-general':
            alerts.append(argv)
            return subprocess.CompletedProcess(argv, 0)
        assert argv[0] == str(TOOLS / 'xurl')
        assert argv[1:4] == ['--auth', 'app', '/2/usage/tweets?days=7&usage.fields=daily_project_usage']
        return run(argv, **kw)
    monkeypatch.setattr(reconcile.subprocess, 'run', stub)
    for _ in range(2):
        assert reconcile.main(['--ledger', str(ledger), '--alert']) == 1
    assert len(alerts) == 3 and all(a[:2] == ['tell-general', 'fyi'] for a in alerts)
    assert 'X=160 ledger=0' in alerts[1][2]


def test_reconcile_offline_pass_missing_ledger_and_invalid_json(gate, tmp_path):
    ledger = gate[1]
    ledger.write_text(''.join(json.dumps(decision(date, items_returned=count)) + '\n'
        for date, count in [('2026-11-11', 100), ('2026-11-12', 160), ('2026-11-13', 26)]))
    args = ['--usage-json', str(FIXTURES / 'usage.json'), '--ledger', str(ledger)]
    assert reconcile.main(args) == 0
    assert reconcile.main(args + ['--ledger', str(tmp_path / 'missing')]) == 1
    ledger.write_text('not JSON\n')
    assert reconcile.main(args) == 1


def test_installed_wrapper_with_symlinked_policy_refuses_self_execution(gate):
    cfg, ledger, data = gate
    wrapper = cfg.with_name('xurl')
    shutil.copy2(TOOLS / 'xurl', wrapper)
    cfg.with_name('xurl-policy').symlink_to(TOOLS / 'xurl-policy')
    data['real_binary'] = str(wrapper)
    cfg.write_text(json.dumps(data))
    result = subprocess.run([str(wrapper), '/2/usage/tweets'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 86 and 'refused execution' in result.stderr
    assert len(rows(ledger)) == 1
