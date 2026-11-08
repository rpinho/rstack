#!/usr/bin/env python3
"""Local X posting gate shared by xr and the PreToolUse hook. No X API calls here.

Only xr's wrapper entry point launches xurl after checking. Hook parsing never
runs commands. Tests replace xurl with a local executable in an isolated PATH.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

import outreach
import settings

ROOT = Path(__file__).resolve().parent
HELP = ('Run: rh outreach draft LANE --to @HANDLE --channel CHANNEL '
        '--purpose "what to share" --file FILE '
        '(CHANNEL=x_post for originals; CHANNEL=x_reply with --in-reply-to URL for replies; '
        'x_post with --self-reply-to ID for link self-replies); '
        'rh outreach lint LANE ID; '
        'rh outreach approve LANE ID --quote standing-approval-10-30. '
        'After posting: rh outreach sent LANE ID --message-id POST_ID --via api (or --via browser).')


def root_path():
    return settings.path('RH_OUTREACH_ROOT', settings.path('RH_ROOT', ROOT))


def mode():
    # Invalid values fail closed, rather than accidentally disabling enforcement.
    return os.environ.get('RH_X_GATE', 'warn')


def option(words, *names):
    found = []
    for i, word in enumerate(words):
        for name in names:
            if word == name:
                found.append(words[i + 1] if i + 1 < len(words) else '')
            elif word.startswith(name + '='):
                found.append(word[len(name) + 1:])
            elif len(name) == 2 and word.startswith(name) and len(word) > 2:
                found.append(word[2:])
    return found


def is_tweet_post(words):
    methods = option(words, '-X', '--request', '--method')
    if not any(m.upper() == 'POST' for m in methods):
        return False
    for word in words:
        endpoint = urlsplit(word) if word.startswith(('https://', 'http://')) else None
        if endpoint:
            if endpoint.hostname in ('api.x.com', 'api.twitter.com') and endpoint.path.rstrip('/') == '/2/tweets':
                return True
        elif word.split('?', 1)[0].rstrip('/') == '/2/tweets':
            return True
    return False


def payload_of(words, cwd, stdin=None, shell=False):
    values = option(words, '-d', '--data', '--json', '--data-file')
    if len(values) != 1:
        raise ValueError('provide exactly one JSON payload using -d/--data (inline or @FILE)')
    raw = values[0]
    if shell and ('$' in raw or '`' in raw):
        raise ValueError('dynamic shell payload cannot be validated; use a literal JSON file with -d @FILE')
    file_option = bool(option(words, '--data-file'))
    if raw == '-' or raw == '@-':
        if stdin is None:
            raise ValueError('piped payload cannot be inspected by PreToolUse; use -d @FILE or xr')
        raw = stdin
    elif raw.startswith('@') or file_option:
        path = Path(raw[1:] if raw.startswith('@') else raw).expanduser()
        raw = (Path(cwd) / path).read_text()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get('text'), str) or not payload['text'].strip():
        raise ValueError('tweet payload requires nonempty text')
    reply = payload.get('reply', {})
    if not isinstance(reply, dict):
        raise ValueError('invalid reply payload')
    if reply and not str(reply.get('in_reply_to_tweet_id', '')).isdecimal():
        raise ValueError('invalid in_reply_to_tweet_id')
    return payload


class Ledger:
    """The small, read-only subset of rh needed to avoid importing network modules."""
    @staticmethod
    def rows(path):
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if any(not isinstance(r, dict) for r in rows):
            raise ValueError('invalid ledger row')
        return rows

    @staticmethod
    def latest(rows):
        return {r['id']: r for r in rows}

    @staticmethod
    def config(path):
        import toml_subset
        return toml_subset.config(path)

    @staticmethod
    def append(path, row):
        with path.open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


def candidates(root, payload=None, browser=False, clock=None, blocked=None):
    """Approved rows this post may claim. A row that matches but fails a reach check now (a
    reply too soon after the last one) goes to `blocked`, so the refusal can say why."""
    clock = clock or dt.datetime.now(outreach.UTC)
    everyone = list(outreach.all_rows(root, Ledger))
    digest = hashlib.sha256(payload['text'].encode('utf-8')).hexdigest() if payload else None
    target = str(payload.get('reply', {}).get('in_reply_to_tweet_id', '')) if payload else None
    for row in everyone:
        approval = row.get('approval') or {}
        if row.get('status') != 'approved' or row.get('channel') not in outreach.X_PUBLIC:
            continue
        if browser and row['channel'] != 'x_reply':
            continue
        if not row.get('lint', {}).get('ok') or not approval.get('quote'):
            continue
        try:
            text = outreach.body(row)
            actual = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if actual != approval.get('sha256') or actual != row['lint'].get('sha256'):
                continue
            if digest and digest != actual:
                continue
            if target is not None and (outreach.reply_target(row) or '') != target:
                continue
            if browser and not dt.timedelta(0) <= clock - outreach.time_of(approval['utc']) <= dt.timedelta(minutes=20):
                continue
            # A successful precheck is a single-use posting intent. This also prevents
            # two concurrent hook calls from borrowing one approved browser reply.
            if row.get('gate_attempt'):
                continue
            cfg = outreach.settings(root / 'lanes' / row['lane'], Ledger)
            failures, _ = outreach.x_checks(row, text, everyone, clock, cfg=cfg, posting=True)
            if failures:
                if blocked is not None:
                    blocked.extend(failures)
                continue
            yield row
        except (OSError, ValueError, KeyError, TypeError):
            continue


def log_block(path_name, reason, payload=None):
    path = settings.path('RH_X_GATE_LOG', Path('.runtime/x-gate.jsonl'))
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(utc=dt.datetime.now(outreach.UTC).isoformat(), mode=mode(), path=path_name,
               would_block=True, reason=reason)
    if payload and isinstance(payload.get('text'), str):
        row['sha256'] = hashlib.sha256(payload['text'].encode('utf-8')).hexdigest()
    # No text, auth tokens, command lines, response bodies, or secrets in this log.
    with path.open('a') as stream:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(row) + '\n')
    return reason + '. ' + HELP


def check(root, path_name, payload=None, browser=False, claim=True):
    if not (root / 'lanes').is_dir():
        return None, log_block(path_name, 'outreach ledger root is unavailable', payload)
    with outreach.send_lock(root, 'sent'):
        blocked = []
        matches = list(candidates(root, payload, browser, blocked=blocked))
        if not matches:
            reason = ('no unused approved x_reply from the last 20 minutes (including current reach checks)'
                      if browser else 'no unused approved x_* row matching exact text, reply target and current reach checks')
            if blocked:
                reason += ': ' + blocked[0]
            return None, log_block(path_name, reason, payload)
        row = matches[0]
        if claim:
            lane = root / 'lanes' / row['lane']
            # Root lock is held before lane lock everywhere in this job.
            import fcntl
            with (lane / '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                row = dict(row, gate_attempt=dict(utc=dt.datetime.now(outreach.UTC).isoformat(), path=path_name))
                outreach.record(lane, row, Ledger)
        return row, None


def bash_tweets(command, segments, cwd, depth=0):
    """Inspect literal shell wrappers too, without evaluating any command."""
    if depth > 8:
        raise ValueError('shell nesting is too deep to validate')
    for words in segments(command):
        words = list(words)
        while words:
            if re.match(r'^\w+=', words[0]):
                words.pop(0)
                continue
            wrapper = Path(words[0]).name
            if wrapper not in ('env', 'command', 'exec', 'sudo'):
                break
            words.pop(0)
            while words and words[0].startswith('-'):
                flag = words.pop(0)
                if flag == '--':
                    break
                if flag in ('-u', '--unset', '-g', '--group', '--user', '-a') and words:
                    words.pop(0)
                elif flag in ('-C', '--chdir') and words:
                    cwd = str((Path(cwd) / Path(words.pop(0)).expanduser()).resolve())
        if not words:
            continue
        executable = Path(words[0]).name
        if executable == 'cd' and len(words) == 2:
            cwd = str((Path(cwd) / Path(words[1]).expanduser()).resolve())
            continue
        if executable in ('bash', 'zsh', 'sh', 'dash', 'ksh'):
            for i, word in enumerate(words[1:], 1):
                if word.startswith('-') and not word.startswith('--') and 'c' in word and i + 1 < len(words):
                    yield from bash_tweets(words[i + 1], segments, cwd, depth + 1)
                    break
        elif executable == 'xurl' and is_tweet_post(words[1:]):
            yield words[1:], cwd


def hook_decision(event, segments):
    """Return hook output, or None. Reuses science hook's shell tokenizer."""
    name, inp = event.get('tool_name', ''), event.get('tool_input') or {}
    attempts = []
    cwd = event.get('cwd') or str(Path.cwd())
    if name == 'Bash':
        for words, command_cwd in bash_tweets(inp.get('command', ''), segments, cwd):
            try:
                attempts.append((payload_of(words, command_cwd, shell=True), False, None))
            except (OSError, ValueError, TypeError):
                attempts.append((None, False, 'cannot extract a literal JSON tweet payload'))
    elif name.endswith('__computer') or name.endswith('__browser_batch'):
        items = [inp] if name.endswith('__computer') else [a.get('input', {}) for a in inp.get('actions', []) if a.get('name', '').endswith('computer')]
        for item in items:
            summary = item.get('action_summary', '')
            if item.get('action') not in ('left_click', 'click'):
                continue
            if (re.search(r'\b(post|send|submit|publish)(?:s|ing|ed)?\b', summary, re.I) and
                re.search(r'\b(reply|replies|respond|response)\b', summary, re.I) and
                re.search(r'\bX\b|twitter|x\.com', summary, re.I)):
                attempts.append((None, True, None))
    messages = []
    for payload, browser, error in attempts:
        path_name = 'browser' if browser else 'bash-xurl'
        try:
            if error:
                message = log_block(path_name, error, payload)
            else:
                _, message = check(root_path(), path_name, payload, browser)
        except Exception:
            message = log_block(path_name, 'X gate could not validate local ledger or rules', payload)
        if message:
            messages.append(message)
    if messages:
        reason = 'X reach gate: ' + ' '.join(messages)
        if mode() == 'warn':
            return {'systemMessage': 'WARNING: ' + reason}
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    return None


def wrapper(words):
    """Preserve xr account pinning and existing forbidden-operation policy."""
    command = ' '.join(words)
    if any(s in command for s in ('/blocking', '/muting', '/lists', 'delete', '/bookmarks')) or any(w in ('block', 'mute') for w in words) or any(m.upper() == 'DELETE' for m in option(words, '-X', '--request', '--method')):
        print('xr: blocked command', file=sys.stderr)
        return 2
    message, row, payload, piped = None, None, None, None
    if is_tweet_post(words):
        try:
            values = option(words, '-d', '--data', '--json', '--data-file')
            if any(v in ('-', '@-') for v in values):
                piped = sys.stdin.read()
            payload = payload_of(words, Path.cwd(), stdin=piped)
            row, message = check(root_path(), 'xr', payload)
        except Exception:
            message = log_block('xr', 'X gate could not extract payload or validate local ledger', payload)
        if message:
            print('xr: ' + ('WARNING: ' if mode() == 'warn' else 'REFUSED: ') + message, file=sys.stderr)
            if mode() != 'warn':
                return 2
    if payload is not None:
        forwarded = []
        skip = False
        names = ('-d', '--data', '--json', '--data-file')
        for word in words:
            if skip:
                skip = False
                continue
            if word in names:
                skip = True
                continue
            if any(word.startswith(n + '=') or (len(n) == 2 and word.startswith(n) and len(word) > 2) for n in names):
                continue
            forwarded.append(word)
        words = forwarded + ['--data', json.dumps(payload, ensure_ascii=False)]
        piped = None
    # xurl is invoked only here, after the gate. Unit and pipe tests supply a fake.
    # The posting account comes from RH_X_ACCOUNT; with none configured, nothing is posted.
    account = os.environ.get('RH_X_ACCOUNT', '').strip().lstrip('@')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', account):
        print('xr: REFUSED: set RH_X_ACCOUNT to the X account handle to post as', file=sys.stderr)
        return 2
    result = subprocess.run(['xurl', '-u', account, *words], input=piped, text=True, capture_output=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode == 0 and row:
        try:
            response = json.loads(result.stdout)
            ident = str(response['data']['id'])
            if not ident.isdecimal():
                raise ValueError('invalid response ID')
            root = root_path()
            with outreach.send_lock(root, 'sent'):
                lane = root / 'lanes' / row['lane']
                import fcntl
                with (lane / '.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    latest = outreach.current(lane, Ledger)[row['id']]
                    sent = dict(latest, status='sent', sent=dict(utc=dt.datetime.now(outreach.UTC).isoformat(), message_id=ident, via='api'))
                    outreach.record(lane, sent, Ledger)
        except (OSError, ValueError, KeyError, TypeError):
            print('xr: posting attempt retained; response receipt unavailable. Record rh outreach sent manually.', file=sys.stderr)
    return result.returncode


if __name__ == '__main__':
    sys.exit(wrapper(sys.argv[1:]))
