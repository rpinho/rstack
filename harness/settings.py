"""Environment configuration shared by standalone commands. No state is loaded here.

Host-specific values (paths, lane sets, notifier commands) live outside the repo in a
KEY=VALUE file: $RH_ENV_FILE, else $XDG_CONFIG_HOME/research-harness/env, else
~/.config/research-harness/env. It is read once at import, so every entry point (CLI,
launchd job, lane session) sees the same values. The real environment always wins.
"""
import os
from pathlib import Path
import re
import shlex


def env_file():
    explicit = os.environ.get('RH_ENV_FILE')
    if explicit:
        return Path(explicit).expanduser()
    config = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(config).expanduser() / 'research-harness/env'


def load_env_file(path=None):
    """Set unset variables from a KEY=VALUE file. Blank lines and # comments are ignored;
    values may be single- or double-quoted. Returns the keys it set."""
    path = Path(path) if path else env_file()
    try:
        text = path.read_text()
    except (FileNotFoundError, NotADirectoryError):
        return []
    loaded = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', key):
            raise ValueError('{}:{}: expected KEY=VALUE'.format(path, number))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


load_env_file()


def names(key):
    values = frozenset(filter(None, os.environ.get(key, '').split(',')))
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', v) for v in values):
        raise ValueError(key + ': expected comma-separated lane names')
    return values


def path(key, default):
    return Path(os.environ.get(key, str(default))).expanduser()


def command(key, default):
    args = shlex.split(os.environ.get(key, default))
    if not args:
        raise ValueError(key + ': command must not be empty')
    return args


def runpod_api_key():
    """The RunPod key from its file first (RH_RUNPOD_KEY_FILE, default ~/.config/runpod/api_key),
    then RUNPOD_API_KEY. A rotated key reaches every process through the file, while a process
    started earlier still carries the old value in its environment. Never log the result."""
    try:
        key = path('RH_RUNPOD_KEY_FILE', Path('~/.config/runpod/api_key')).read_text().strip()
    except OSError:
        key = ''
    return key or os.environ.get('RUNPOD_API_KEY', '').strip()

def lane_dir(value, root=None):
    """Resolve a --lane argument to a real lane directory, or raise ValueError.

    11-07, planets: `baseline.py --lane planets` run from the harness root took the bare name as a
    path, created ~/.local/share/research-harness/planets/BASELINES.jsonl beside the lanes
    directory, and ran the lane's commands with cwd "planets", which failed with
    FileNotFoundError. Four tools took --lane as a bare Path and all of them had the same trap, so
    the fix is one resolver rather than four.

    A bare name resolves under RH_ROOT/lanes. A path with a separator is taken as given. Either way
    the directory has to exist already: a tool that writes a lane's ledger must not be able to
    create a new directory by typo, which is what left a stray planets/ beside the lanes.

    Existence is the whole test. Requiring an IDEAS.jsonl as well was tempting and wrong: a lane
    created minutes ago has no ledger yet, and it would have refused every new lane and every test
    fixture. The failure being fixed is a path that did not exist, not a directory that is not
    furnished.
    """
    text = str(value).strip()
    if not text:
        raise ValueError('--lane is empty')
    base = Path(root).expanduser() if root else path('RH_ROOT', Path(__file__).resolve().parent)
    candidate = Path(text).expanduser()
    if os.sep in text or text.startswith('~') or candidate.is_absolute():
        lane = candidate
    else:
        lane = base / 'lanes' / text
    lane = lane.expanduser()
    if not lane.is_dir():
        raise ValueError('no lane directory at {} (a bare name resolves under {})'
                         .format(lane, base / 'lanes'))
    return lane
