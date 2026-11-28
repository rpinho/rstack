"""x-campaign-canary: counts campaign replies on X itself and pages on a shortfall or an unreadable X (11-28)."""
import json
import os
from pathlib import Path
import subprocess
import sys

TOOL = Path(__file__).resolve().parents[1] / 'tools/x-campaign-canary'


def tweet(i, reply=True, url='https://github.com/rpinho/lean-golf', replies=1, likes=2):
    return {'id': str(i), 'text': 'try it https://t.co/x', 'public_metrics': {'reply_count': replies, 'like_count': likes},
            'referenced_tweets': [{'type': 'replied_to', 'id': '9'}] if reply else [],
            'entities': {'urls': [{'url': 'https://t.co/x', 'expanded_url': url}]}}


def env_for(tmp_path, tweets=None, fail=False, hour=None):
    xr = tmp_path / 'xr'
    if fail:
        xr.write_text('#!/bin/sh\necho "401 Unauthorized" >&2\nexit 1\n')
    else:
        (tmp_path / 'tl.json').write_text(json.dumps({'data': tweets or []}))
        xr.write_text('#!/bin/sh\ncat {}\n'.format(tmp_path / 'tl.json'))
    xr.chmod(0o755)
    route = tmp_path / 'x-route.json'
    route.write_text(json.dumps({'account_id': '123'}))
    sent = tmp_path / 'sent.txt'
    rec = tmp_path / 'rec'
    rec.write_text('#!/bin/sh\necho "$@" >> {}\n'.format(sent))
    rec.chmod(0o755)
    runs = tmp_path / 'runs.log'
    runs.write_text('ok\nINPUT-FAIL x-engage: bookmark_queue failed\n')
    env = dict(os.environ, X_CANARY_XR=str(xr), X_ROUTE_CONFIG=str(route), X_CANARY_NOTIFY=str(rec),
               X_CANARY_TELL=str(rec), X_CANARY_ERRORS=str(runs), X_CANARY_STATE=str(tmp_path / 'state'))
    return env, sent


def run(env, *args):
    return subprocess.run([sys.executable, str(TOOL), *args], env=env, capture_output=True, text=True, timeout=60)


def test_counts_only_replies_with_the_campaign_link_and_pages_on_a_shortfall(tmp_path):
    env, sent = env_for(tmp_path, [tweet(1), tweet(2), tweet(3, reply=False), tweet(4, url='https://example.org')])
    done = run(env, '--ramp', '0:5')
    assert done.returncode == 1 and '2 of 5 expected' in done.stdout
    assert 'blocked by: INPUT-FAIL x-engage: bookmark_queue failed' in done.stdout
    assert sent.read_text().count('2 of 5 expected') == 2          # the phone push and tell-general


def test_on_target_it_stays_quiet_until_the_summary_hour(tmp_path):
    env, sent = env_for(tmp_path, [tweet(i) for i in range(4)])
    done = run(env, '--ramp', '0:3', '--summary-hour', '99')
    assert done.returncode == 0 and 'OK: 4 of 3' in done.stdout and not sent.exists()
    hour = __import__('datetime').datetime.now().hour
    done = run(env, '--ramp', '0:3', '--summary-hour', str(hour))
    assert done.returncode == 0 and '4 live in the last 24 h' in done.stdout and '4 replies and 8 likes' in done.stdout
    assert sent.read_text().count('live in the last 24 h') == 1     # one OK push, no tell-general


def test_an_unreadable_x_is_a_failure_push_not_a_skip(tmp_path):
    env, sent = env_for(tmp_path, fail=True)
    done = run(env, '--ramp', '0:3')
    assert done.returncode == 1 and 'CANNOT READ X' in done.stdout and '401 Unauthorized' in done.stdout
    assert sent.read_text().count('CANNOT READ X') == 2
    row = json.loads((tmp_path / 'state/log.jsonl').read_text().splitlines()[-1])
    assert row['status'] == 'fail-read'
