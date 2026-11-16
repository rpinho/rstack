"""Exercise real HTTP boundaries locally; never use a real credential or API."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
from agent_executor import command
from gemini_transport import bridge, chat_request, response_events


def test_gemini_provider_argv_contains_only_environment_key_name(monkeypatch):
    monkeypatch.setenv('LAUNCH_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-secret-never-in-argv')
    argv = command('codex', 'codex', 'google/gemini-4-carbon', 'low', '/w', '/o')
    assert 'model_provider="gemini"' in argv
    assert 'model_providers.gemini.env_key="GEMINI_API_KEY"' in argv
    assert 'model_providers.gemini.wire_api="responses"' in argv
    assert 'model_providers.gemini.request_max_retries=0' in argv
    assert 'fixture-secret-never-in-argv' not in str(argv)


def test_chat_history_and_tool_results_preserve_call_identity():
    body = dict(model='google/gemini-4-argon', instructions='rules', tools=[
        dict(type='function', name='shell', parameters=dict(type='object')),
        dict(type='custom', name='apply_patch')], input=[
        dict(role='developer', content=[dict(type='input_text', text='context')]),
        dict(type='function_call', call_id='a', name='shell', arguments='{"cmd":"ls"}'),
        dict(type='function_call_output', call_id='a', output='file'),
        dict(type='custom_tool_call', call_id='b', name='apply_patch', input='patch'),
        dict(type='custom_tool_call_output', call_id='b', output='done')])
    chat, custom = chat_request(body)
    assert chat['model'] == 'gemini-4-argon'
    assert chat['messages'][1] == dict(role='system', content='context')
    assert chat['messages'][3] == dict(role='tool', tool_call_id='a', content='file')
    events = list(response_events(dict(choices=[dict(message=dict(tool_calls=[dict(
        id='b', function=dict(name='apply_patch', arguments='{"input":"patch"}'))]))],
        usage=dict(prompt_tokens=20, completion_tokens=4, total_tokens=24)), custom))
    item = events[-1]['response']['output'][0]
    assert item['type'] == 'custom_tool_call' and item['call_id'] == 'b' and item['input'] == 'patch'
    assert events[-1]['response']['usage']['total_tokens'] == 24


def test_namespaced_tools_and_signed_calls_survive_codex_history():
    signed = dict(id='signed', type='function', function=dict(name='local.run', arguments='{}'),
                  extra_content=dict(google=dict(thought_signature='opaque-signed-state')))
    body = dict(model='google/gemini-4-hydrogen', reasoning=dict(effort='medium'), tools=[
        dict(type='namespace', name='local', tools=[dict(type='function', name='run',
             parameters=dict(type='object'))]), dict(type='web_search')], input=[
        dict(type='function_call', call_id='signed', name='run', namespace='local', arguments='{}'),
        dict(type='function_call_output', call_id='signed', output='result')])
    chat, _ = chat_request(body, {'signed': signed})
    assert chat['messages'][0]['tool_calls'] == [signed]
    assert chat['tools'][0]['function']['name'] == 'local.run'
    assert len(chat['tools']) == 1 and chat['reasoning_effort'] == 'medium'


def test_view_image_output_reaches_google_as_an_image():
    chat, _ = chat_request(dict(model='google/gemini-4-hydrogen', input=[
        dict(type='function_call_output', call_id='image', output=[
            dict(type='input_text', text='page one'),
            dict(type='input_image', image_url='data:image/png;base64,fixture')])]))
    assert chat['messages'][0] == dict(role='tool', tool_call_id='image', content='page one')
    assert chat['messages'][1]['content'] == [dict(type='image_url',
        image_url=dict(url='data:image/png;base64,fixture'))]


def _http_fixture(status):
    secret = 'fixture-provider-key-never-log'
    os.environ['GEMINI_API_KEY'] = secret
    seen = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            seen.append((self.path, self.headers.get('Authorization'), body))
            self.send_response(status)
            self.end_headers()
            if status == 429:
                self.wfile.write(json.dumps(dict(error=dict(message='quota ' + secret))).encode())
            else:
                self.wfile.write(json.dumps(dict(choices=[dict(message=dict(content='OK'))],
                    usage=dict(prompt_tokens=10, completion_tokens=1, total_tokens=11))).encode())
    server = HTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with bridge('http://127.0.0.1:' + str(server.server_port)) as url:
            req = urllib.request.Request(url + '/responses', data=json.dumps(dict(
                model='google/gemini-4-carbon', input='OK')).encode(),
                headers={'Authorization': 'Bearer ' + secret})
            try:
                with urllib.request.urlopen(req) as reply:
                    text = reply.read().decode()
                assert status == 200 and 'response.completed' in text
            except urllib.error.HTTPError as exc:
                text = exc.read().decode()
                assert exc.code == status == 429 and 'quota' in text and '[REDACTED]' in text
            assert secret not in text
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert len(seen) == 1
    assert seen[0][0] == '/chat/completions' and seen[0][1] == 'Bearer ' + secret
    assert secret not in seen[0][0] and secret.encode() not in seen[0][2]


@pytest.mark.parametrize('status', [200, 429])
def test_bridge_header_only_auth_no_retries_and_redacted_errors(status):
    # The parent suite blocks all TCP. This child exercises only two ephemeral
    # loopback sockets; its upstream is fixed locally, with a synthetic key.
    script = 'import runpy; runpy.run_path(' + repr(__file__) + ')["_http_fixture"](' + str(status) + ')'
    proc = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize('role', ['batch', 'review', 'judge', 'ideation'])
def test_launcher_gemini_exploration_keeps_key_out_of_receipts(tmp_path, role):
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / 'home'
    key = home / '.config/gemini/api_key'
    key.parent.mkdir(parents=True)
    secret = 'fixture-secret-header-only'
    key.write_text(secret)
    jobs = tmp_path / 'jobs'
    jobs.mkdir()
    (jobs / 'fixture.md').write_text('Offline synthetic fixture. No model pin.\n')
    model = 'google/gemini-4-hydrogen'
    roles = tmp_path / 'roles.json'
    roles.write_text(json.dumps(dict(roles={role: [model]}, routes={
        model: dict(cli='gemini', canonical=model)})))
    fake = tmp_path / 'fake-codex'
    fake.write_text('#!' + sys.executable + '\nimport os,sys,json\n'
        'assert os.environ["GEMINI_API_KEY"] == ' + repr(secret) + '\n'
        'assert os.environ["GEMINI_API_KEY"] not in str(sys.argv)\n'
        'assert \'model_provider="gemini"\' in sys.argv\n'
        'print("fixture: 429 quota at capacity")\nsys.exit(1)\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LAUNCH_', 'AGENT_', 'RH_'))}
    env.update(HOME=str(home), AGENT_BACKEND='codex', LAUNCH_CODEX=str(fake),
        LAUNCH_ARTIFACT_DIR=str(jobs), LAUNCH_STATE=str(tmp_path / 'registry'),
        RH_ROLES_FILE=str(roles), FORCE_LAUNCH='1')
    proc = subprocess.run(['zsh', str(repo / 'tools/launch.sh'), 'fixture', str(tmp_path),
        '--role', role, '--made-by', 'openai/fixture', '--explore', model],
        env=env, capture_output=True, text=True, timeout=20)
    assert proc.returncode == 1, proc.stderr
    log = (jobs / 'fixture.log').read_text()
    assert log.count('=== attempt') == 1
    receipt = json.loads((jobs / 'fixture.log.selection.json').read_text())
    assert receipt['executor'] == 'gemini' and receipt['source'] == 'explore'
    assert secret not in log + proc.stdout + proc.stderr
    for path in jobs.iterdir():
        assert secret not in path.read_text()
