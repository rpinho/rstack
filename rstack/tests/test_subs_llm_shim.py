"""subs-llm-shim: an OpenAI-shaped request becomes one subscription CLI call. Stub CLIs only, no sockets."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / 'rstack/tools/subs-llm-shim'
spec = spec_from_loader('subs_llm_shim', SourceFileLoader('subs_llm_shim', str(TOOL)))
shim = module_from_spec(spec)
spec.loader.exec_module(shim)


def stub(path, body):
    path.write_text('#!' + sys.executable + '\n' + body)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def args(tmp_path):
    seen = tmp_path / 'seen.json'
    claude = stub(tmp_path / 'claude', (
        'import json, sys\n'
        'json.dump({"argv": sys.argv[1:], "prompt": sys.stdin.read()}, open(%r, "w"))\n'
        'print(json.dumps({"type": "result", "subtype": "success", "is_error": False,\n'
        '  "result": "```json\\n{\\"ok\\": true}\\n```",\n'
        '  "usage": {"input_tokens": 7, "cache_read_input_tokens": 3, "output_tokens": 5}}))\n') % str(seen))
    agy = stub(tmp_path / 'agy', (
        'import sys\n'
        'sys.stderr.write("Authentication required. Please visit the URL to log in:\\n")\n'
        'print(\'{"status":"ERROR","response":"","error":"authentication failed or timed out"}\')\n'
        'sys.exit(1)\n'))
    a = shim.parser().parse_args(['--claude', claude, '--agy', agy, '--codex', str(tmp_path / 'absent-codex')])
    a.seen = seen
    return a


def test_a_chat_completion_is_one_claude_call_and_json_comes_back_unfenced(args):
    body = shim.completion({'model': 'openai/claude-sonnet-5-5', 'response_format': {'type': 'json_object'},
                            'messages': [{'role': 'system', 'content': 'Be terse.'},
                                         {'role': 'user', 'content': 'Say ok.'}]}, args)
    assert body['choices'][0]['message']['content'] == '{"ok": true}'
    assert body['usage'] == {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}
    call = json.loads(args.seen.read_text())
    assert call['argv'][call['argv'].index('--model') + 1] == 'claude-sonnet-5-5'
    assert call['argv'][call['argv'].index('--tools') + 1] == ''
    assert '[SYSTEM]\nBe terse.' in call['prompt'] and 'JSON object' in call['prompt']


def test_a_signed_out_agy_says_it_needs_ricardos_sign_in(args):
    with pytest.raises(shim.CallError) as err:
        shim.completion({'model': 'gemini-3-pro', 'messages': [{'role': 'user', 'content': 'hi'}]}, args)
    assert err.value.status == 503
    assert "agy needs Ricardo's one-time interactive sign-in" in str(err.value)


def test_the_backend_comes_from_the_model_name_and_a_missing_cli_is_an_error_not_a_fallback(args):
    assert [shim.backend_for(m, 'claude') for m in ('claude-opus-5-5', 'gpt-6.2-sol', 'gemini-x', 'other')] == \
        ['claude', 'codex', 'agy', 'claude']
    with pytest.raises(shim.CallError) as err:
        shim.completion({'model': 'gpt-6.2-sol', 'messages': [{'role': 'user', 'content': 'hi'}]}, args)
    assert err.value.status == 502
