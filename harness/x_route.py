"""Route order for X actions, and the ledger every attempt is written to (11-19).

Ricardo, 11-19: "Why are you replying using Chrome instead of Grokbot?" and then "Are you sure about
these? How can we make them use it?" Grok Bot's X connector can post and reply but has no like or
follow tool (its 101 tool names were read from the app, 11-19). So each action kind has one first
route, a second where one exists, and the browser last:

  reply, post   grok (grok-post)            then browser
  like, follow  api  (xurl, posting account) then browser

Every attempt, success or failure, is one JSON line in the route ledger. A browser submit is
allowed only for a kind with no first route, or after a failed first-route attempt for the same
target in the last BROWSER_WINDOW minutes (x-submit-gate reads this). No network here.
"""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re

# 11-27 (Ricardo: "we're getting in the way of ourselves"): the API refuses likes and follows for this account
# (403, unsupported authentication), so they go straight to the browser; X_ROUTE_API_ENGAGE=1 restores the API first.
ROUTES = {'reply': ('grok',), 'post': ('grok', 'api')}
if os.environ.get('X_ROUTE_API_ENGAGE') == '1':
    ROUTES.update(like=('api',), follow=('api',))
BROWSER_WINDOW = 15


def ledger_path():
    root = os.environ.get('RSTACK_STATE_DIR') or str(
        Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack')
    return Path(os.environ.get('X_ROUTE_LEDGER') or Path(root).expanduser() / 'x-route.jsonl').expanduser()


def target_key(kind, target):
    """A post ID for reply/like/post, a lowercased handle for follow; '' when it cannot be read."""
    text = str(target or '').strip()
    if kind == 'follow':
        m = re.fullmatch(r'(?:https?://(?:www\.)?(?:x|twitter)\.com/)?@?([A-Za-z0-9_]{1,15})/?', text)
        return m[1].casefold() if m else ''
    m = re.search(r'(?:/status/)(\d{5,25})', text) or re.fullmatch(r'(\d{5,25})', text)
    return m[1] if m else ('new' if kind == 'post' and text in ('', 'post', 'new') else '')


def log(kind, target, route, ok, detail='', **extra):
    row = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), kind=kind,
               target=target_key(kind, target), route=route, ok=bool(ok), detail=str(detail)[-400:], **extra)
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    return row


def rows(path=None):
    path = path or ledger_path()
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def browser_allowed(kind, target, now=None, path=None):
    """(allowed, reason). The browser is last: only with no first route, or after a logged failure."""
    if kind not in ROUTES:
        return True, 'no grok or api route for ' + kind
    key = target_key(kind, target)
    if not key:
        return False, 'name the target (post URL or ID, or @handle) so the route ledger can be checked'
    now = now or dt.datetime.now(dt.timezone.utc)
    for row in reversed(rows(path)):
        if row.get('kind') != kind or row.get('target') != key or row.get('route') == 'browser':
            continue
        try:
            stamp = dt.datetime.fromisoformat(str(row['utc']).replace('Z', '+00:00'))
        except (KeyError, ValueError):
            continue
        if now - stamp > dt.timedelta(minutes=BROWSER_WINDOW):
            break
        if row.get('ok'):
            return False, '{} already done through {} at {}'.format(kind, row.get('route'), row['utc'])
        if row.get('uncertain'):
            return False, '{} through {} may have gone out unverified; never retry it'.format(kind, row.get('route'))
        return True, '{} failed at {}: {}'.format(row.get('route'), row['utc'], row.get('detail', ''))
    return False, ('{} has a {} route and no failed attempt for {} in the last {} min; run x-route {} first'
                   .format(kind, ' then '.join(ROUTES[kind]), key, BROWSER_WINDOW, kind))
