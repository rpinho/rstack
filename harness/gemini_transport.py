"""Process-local Codex Responses transport for Google's Chat Completions API.

Codex 0.167 only speaks Responses; Google AI Studio's OpenAI endpoint does not.
No credentials, prompts or completions are logged here. No upstream retries.
"""
from contextlib import contextmanager
import hmac
import datetime as dt
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import threading
import urllib.error
import urllib.request
import uuid

BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'


def redact(text):
    key = os.environ.get('GEMINI_API_KEY', '')
    if key:
        text = text.replace(key, '[REDACTED]')
    return re.sub(r'AIza[\w-]+|(?i:Bearer)\s+[^\s"<>]+', '[REDACTED]', text)


def flat_tools(tools, prefix=''):
    for tool in tools:
        if tool.get('type') == 'namespace':
            yield from flat_tools(tool.get('tools', []), prefix + tool['name'] + '.')
        elif tool.get('type') in ('function', 'custom'):
            yield dict(tool, name=prefix + tool['name'])
        elif tool.get('type') != 'web_search':
            raise ValueError('unsupported Responses tool type: ' + str(tool.get('type')))


def content_parts(content):
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        kind = part.get('type')
        if kind in ('input_text', 'output_text', 'text'):
            parts.append(dict(type='text', text=part.get('text', '')))
        elif kind == 'input_image':
            url = part['image_url']
            parts.append(dict(type='image_url', image_url=url if isinstance(url, dict) else dict(url=url)))
        else:
            raise ValueError('unsupported Responses content type: ' + str(kind))
    if all(p['type'] == 'text' for p in parts):
        return '\n'.join(p['text'] for p in parts)
    return parts


def chat_request(body, saved_calls=None):
    """Translate stateless Responses history, including function and custom tools."""
    messages = []
    if body.get('instructions'):
        messages.append(dict(role='system', content=body['instructions']))
    items = body.get('input', [])
    if isinstance(items, str):
        items = [dict(role='user', content=items)]
    for item in items:
        kind = item.get('type', 'message')
        if kind == 'message':
            content = content_parts(item.get('content', ''))
            role = item['role']
            messages.append(dict(role='system' if role == 'developer' else role, content=content))
        elif kind in ('function_call', 'custom_tool_call'):
            arguments = (item.get('arguments', '{}') if kind == 'function_call'
                         else json.dumps(dict(input=item['input'])))
            call = dict(id=item['call_id'], type='function',
                        function=dict(name=(item.get('namespace', '') + '.' if item.get('namespace') else '') + item['name'], arguments=arguments))
            if saved_calls and item['call_id'] in saved_calls:
                call = saved_calls[item['call_id']]
            if messages and messages[-1]['role'] == 'assistant' and messages[-1].get('tool_calls'):
                messages[-1]['tool_calls'].append(call)
            else:
                messages.append(dict(role='assistant', content=None, tool_calls=[call]))
        elif kind in ('function_call_output', 'custom_tool_call_output'):
            output = content_parts(item.get('output', ''))
            if isinstance(output, str):
                messages.append(dict(role='tool', tool_call_id=item['call_id'], content=output))
            else:
                messages.append(dict(role='tool', tool_call_id=item['call_id'],
                    content='\n'.join(p['text'] for p in output if p['type'] == 'text')))
                messages.append(dict(role='user', content=[p for p in output if p['type'] == 'image_url']))
        elif kind != 'reasoning':
            raise ValueError('unsupported Responses input type: ' + kind)
    result = dict(model=body['model'].removeprefix('google/'), messages=messages, stream=False)
    custom = set()
    tools = []
    for tool in flat_tools(body.get('tools', [])):
        kind = tool.get('type')
        if kind == 'function':
            function = {k: tool[k] for k in ('name', 'description', 'parameters') if k in tool}
        elif kind == 'custom':
            custom.add(tool['name'])
            function = dict(name=tool['name'], description=tool.get('description', ''),
                            parameters=dict(type='object', properties=dict(input=dict(type='string')),
                                            required=['input']))
        else:
            raise ValueError('unsupported Responses tool type: ' + str(kind))
        tools.append(dict(type='function', function=function))
    if tools:
        result['tools'] = tools
    if body.get('reasoning', {}).get('effort'):
        result['reasoning_effort'] = body['reasoning']['effort']
    if body.get('max_output_tokens'):
        result['max_completion_tokens'] = body['max_output_tokens']
    return result, custom


def response_events(chat, custom=()):
    """Synthesize the Responses events Codex consumes, preserving calls and usage."""
    finish = chat['choices'][0].get('finish_reason')
    if finish and finish not in ('stop', 'tool_calls'):
        raise ValueError('Google completion did not finish: ' + finish)
    rid = 'resp_' + uuid.uuid4().hex
    message = chat['choices'][0]['message']
    output = []
    if message.get('content'):
        output.append(dict(id='msg_' + uuid.uuid4().hex, type='message', status='completed',
                           role='assistant', content=[dict(type='output_text', text=message['content'], annotations=[])]))
    for call in message.get('tool_calls', []):
        fn = call['function']
        item = dict(id='fc_' + uuid.uuid4().hex, call_id=call['id'], name=fn['name'], status='completed')
        if fn['name'] in custom:
            item.update(type='custom_tool_call', input=json.loads(fn['arguments'])['input'])
        else:
            item.update(type='function_call', arguments=fn['arguments'])
        output.append(item)
    usage = chat.get('usage', {})
    response = dict(id=rid, object='response', status='completed', output=output,
                    usage=dict(input_tokens=usage.get('prompt_tokens', 0),
                               output_tokens=usage.get('completion_tokens', 0),
                               total_tokens=usage.get('total_tokens', 0),
                               input_tokens_details=dict(cached_tokens=usage.get('prompt_tokens_details', {}).get('cached_tokens', 0))))
    yield dict(type='response.created', response=dict(id=rid, object='response', status='in_progress', output=[]))
    for index, item in enumerate(output):
        yield dict(type='response.output_item.added', output_index=index, item=item)
        yield dict(type='response.output_item.done', output_index=index, item=item)
    yield dict(type='response.completed', response=response)


@contextmanager
def bridge(base_url=BASE_URL):
    """Bind only loopback, require the environment key in a header, close on exit."""
    saved_calls = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            expected = 'Bearer ' + os.environ['GEMINI_API_KEY']
            if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                self.send_error(401, 'missing provider authorization')
                return
            if self.path != '/responses':
                self.send_error(404)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                request, custom = chat_request(body, saved_calls)
                upstream = urllib.request.Request(base_url.rstrip('/') + '/chat/completions',
                    data=json.dumps(request).encode(), headers={
                        'Authorization': expected, 'Content-Type': 'application/json'})
                with urllib.request.urlopen(upstream, timeout=float(os.environ.get('GEMINI_REQUEST_TIMEOUT_SECONDS', '180'))) as reply:
                    chat = json.load(reply)
                for call in chat['choices'][0]['message'].get('tool_calls', []):
                    # Codex drops provider-specific fields; keep Google's opaque thought
                    # signatures in memory and replay the exact call on the next turn.
                    saved_calls[call['id']] = call
                print('GEMINI_USAGE ' + json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                    usage=chat.get('usage', {}))), file=sys.stderr, flush=True)
                events = list(response_events(chat, custom))
            except urllib.error.HTTPError as exc:
                text = redact(exc.read().decode('utf-8', 'replace'))
                print('GEMINI_ERROR ' + json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                    status=exc.code, error=text)), file=sys.stderr, flush=True)
                self.send_response(exc.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(text.encode())
                return
            except Exception as exc:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(dict(error=dict(message=redact(str(exc))))).encode())
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            for seq, event in enumerate(events):
                event['sequence_number'] = seq
                self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
