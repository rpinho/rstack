#!/usr/bin/env python3
"""agy quota windows: when each (model, tier) is blocked until, read from the executor's quota log.

11-20 (harness-m5): the picker kept delegating to gemini-4-argon-medium after agy answered "Individual quota
reached ... Resets in 152h14m46s", so every job it got failed at once, and agy's claude-opus-5-5-high hit its
5-hour window the same way. Each row agent_executor appends to $RSTACK_STATE_DIR/agy-quota.jsonl carries the
reset agy names; blocked_until = utc + that reset. The picker skips a (model, tier) until then, and a job that
hit the quota is graded "ungraded" (note "quota"): the quota is infrastructure, not the model's work.

  agy_quota.py                 list what is blocked now
  agy_quota.py --import FILE   append rows from another machine's agy-quota.jsonl or a job log (AGY_QUOTA lines)
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

TIERS = ('low', 'medium', 'high', 'xhigh', 'max')
RESET = re.compile(r'resets?\s+in\s+((?:\d+\s*[dhms]\s*)+)', re.I)
UNIT = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
# agy publishes no numbers (11-19): a 5-hour refresh and a weekly cap. A reset within 5 h is the 5-hour window.
FIVE_HOURS = 5 * 3600
MARK = 'AGY_QUOTA '


def state_file():
    base = Path(os.environ.get('RSTACK_STATE_DIR') or
                Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rstack').expanduser()
    return base / 'agy-quota.jsonl'


def reset_seconds(text):
    """Seconds until the reset agy names ("Resets in 152h14m46s"), or None when it names none."""
    found = RESET.search(text or '')
    if not found:
        return None
    return sum(int(n) * UNIT[u.lower()] for n, u in re.findall(r'(\d+)\s*([dhms])', found.group(1), re.I))


def window(seconds):
    """'5h' or 'weekly', by how far away the reset is; None when unknown."""
    if seconds is None:
        return None
    return '5h' if seconds <= FIVE_HOURS else 'weekly'


def tier_of(model, effort=None):
    """The tier agy runs a model at: its name's suffix (gemini-4-argon-medium), else the --effort given."""
    return next((t for t in TIERS if str(model).endswith('-' + t)), None) or (effort if effort in TIERS else None)


def _utc(text):
    try:
        when = dt.datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)


def annotate(row):
    """The row with blocked_until and window filled in from its error text, when agy named a reset."""
    seconds = reset_seconds(row.get('error'))
    at = _utc(row.get('utc'))
    if seconds is not None and at and not row.get('blocked_until'):
        row['blocked_until'] = (at + dt.timedelta(seconds=seconds)).isoformat(timespec='seconds')
    if seconds is not None and not row.get('window'):
        row['window'] = window(seconds)
    return row


def rows(path=None):
    try:
        lines = Path(path or state_file()).read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('model'):
            out.append(annotate(row))
    return out


def blocked(now=None, path=None):
    """{(model, tier): row} for every (model, tier) whose latest logged reset has not passed."""
    now = now or dt.datetime.now(dt.timezone.utc)
    latest = {}
    for row in rows(path):
        until = _utc(row.get('blocked_until') or '')
        if not until:
            continue
        key = (row['model'], row.get('tier') or tier_of(row['model']))
        if key not in latest or until > _utc(latest[key]['blocked_until']):
            latest[key] = row
    return {k: r for k, r in latest.items() if _utc(r['blocked_until']) > now}


def blocked_until(model, effort=None, now=None, path=None, table=None):
    """The row blocking this model on agy now, or None. A row with no tier blocks every tier of the model."""
    table = blocked(now, path) if table is None else table
    tier = tier_of(model, effort)
    return table.get((model, tier)) or table.get((model, None))


def skip_note(model, row):
    return 'skipped {}: agy quota until {} ({} window)'.format(
        model, _utc(row['blocked_until']).strftime('%Y-%m-%d %H:%M UTC'), row.get('window') or 'unknown')


def hit(text):
    """The AGY_QUOTA rows the executor printed into a job log, newest last."""
    found = []
    for line in (text or '').splitlines():
        if line.startswith(MARK):
            try:
                row = json.loads(line[len(MARK):])
            except ValueError:
                continue
            if isinstance(row, dict):
                found.append(row)
    return found


def record(row, path=None):
    """Append the row unless the same (utc, model, job) is already there. True when written."""
    path = Path(path or state_file())
    key = (row.get('utc'), row.get('model'), row.get('job'))
    if any((r.get('utc'), r.get('model'), r.get('job')) == key for r in rows(path)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        stream.write(json.dumps(annotate(dict(row)), sort_keys=True) + '\n')
    return True


def import_rows(source, path=None):
    """Rows from another machine's quota log or from a job log's AGY_QUOTA lines; returns how many were new.
    11-20: a --host job runs agy on the host, so the host logs the quota while the controller picks."""
    text = Path(source).read_text(errors='replace')
    found = hit(text)
    if not found:
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('model') and row.get('error'):
                found.append(row)
    return sum(record(row, path) for row in found)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--import', dest='source', type=Path, help='append rows from this quota log or job log')
    a = p.parse_args(argv)
    if a.source:
        print('imported {} agy quota rows from {}'.format(import_rows(a.source), a.source))
    table = blocked()
    for (model, tier), row in sorted(table.items()):
        print('{} ({}): {}'.format(model, tier, skip_note(model, row)))
    if not table:
        print('no agy model is blocked now')
    return 0


if __name__ == '__main__':
    sys.exit(main())
