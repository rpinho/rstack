"""Shared pieces of the KB send gates: their config, pass stamps and outreach approvals.

The gates hold no names, addresses, paths or phrase lists of their own. Everything that is yours
comes from one JSON file, so the hooks can be copied anywhere without carrying anyone's context:

    $KB_GATES_CONFIG, else ${XDG_CONFIG_HOME:-~/.config}/kb/gates.json

`gates.example.json` beside this file lists every key with a generic default. No file means the
defaults. A file that exists but cannot be read or parsed is an error, and each gate's triage then
decides: a call that could be a send is refused, never let through on a broken config.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re


def config_path():
    explicit = os.environ.get('KB_GATES_CONFIG')
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base).expanduser() / 'kb' / 'gates.json'


def config(section):
    """One gate's settings (a dict). Missing file: {}. Unreadable or malformed: raises."""
    path = config_path()
    if not path.exists() and not os.environ.get('KB_GATES_CONFIG'):
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))   # an explicit path that is missing raises
    if not isinstance(data, dict):
        raise ValueError('gates config is not an object')
    common = {k: v for k, v in data.items() if not isinstance(v, dict)}
    own = data.get(section) or {}
    if not isinstance(own, dict):
        raise ValueError('gates config section {} is not an object'.format(section))
    return dict(common, **own)


def path_of(value, default=None):
    value = value or default
    return Path(os.path.expandvars(str(value))).expanduser() if value else None


def words_rx(words):
    """A case-insensitive, word-bounded alternation of plain phrases from config."""
    if not words:
        return None
    if isinstance(words, str) or not all(isinstance(w, str) for w in words):
        raise TypeError('a phrase list must be a list of strings')
    return re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b', re.I)


def parse_utc(value):
    t = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def fresh_stamp(path, minutes, clock=None):
    """True when PATH is a JSON object whose `utc` is within MINUTES. Missing or unreadable: False."""
    if not path:
        return False
    clock = clock or dt.datetime.now(dt.timezone.utc)
    try:
        return clock - parse_utc(json.loads(Path(path).read_text())['utc']) <= dt.timedelta(minutes=minutes)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def recent_approval(root, minutes, clock=None):
    """True when an `rh outreach approve` under ROOT/lanes/*/OUTREACH.jsonl is within MINUTES.

    A cold message has no incoming text to lint; an approval with the approver's own quote is the
    same proof that a person read the exact text. A ledger that will not parse is skipped."""
    if not root:
        return False
    clock = clock or dt.datetime.now(dt.timezone.utc)
    for ledger in Path(root).glob('lanes/*/OUTREACH.jsonl'):
        try:
            latest = {}
            for line in ledger.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    latest[row['id']] = row
            for row in latest.values():
                ap = row.get('approval') or {}
                if row.get('status') == 'approved' and ap.get('quote') and ap.get('utc'):
                    if clock - parse_utc(ap['utc']) <= dt.timedelta(minutes=minutes):
                        return True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return False


def computer_actions(event):
    """The computer-use actions in a browser call: the call itself, or each one inside a batch."""
    tool = str(event.get('tool_name') or '')
    inp = event.get('tool_input') or {}
    if not isinstance(inp, dict):
        raise TypeError('tool_input')
    if tool.endswith('__computer'):
        return [inp]
    actions = inp.get('actions') or []
    if not isinstance(actions, list):
        raise TypeError('actions')
    return [a.get('input') or {} for a in actions if isinstance(a, dict) and a.get('name') == 'computer']


def browser_triage(raw, event):
    """Crash-proof, raw text only: could this be a click, a key press, or a batch holding one?"""
    low = raw.lower()
    if 'browser_batch' in low or 'actions' in low or 'click' in low or 'key' in low:
        return True
    return '__computer' not in low          # cannot tell which tool or action it is: treat as guarded


def load_wrapper():
    """Import the fail-safe wrapper that sits beside these hooks (a copy of rstack/hooks/_hookfail.py)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _hookfail
    return _hookfail


def no_wrapper(name, triage, what):
    """The wrapper itself would not load: still refuse a possible send, judged from the raw text."""
    import sys
    raw = sys.stdin.read()
    if triage(raw, None):
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
            'permissionDecisionReason': name + ': _hookfail.py would not load, so this ' + what +
            ' is refused rather than allowed. Repair .claude/hooks/_hookfail.py.'}}))
    else:
        print('[{}] _hookfail.py would not load; not a {}, allowed.'.format(name, what), file=sys.stderr)
    return 0
