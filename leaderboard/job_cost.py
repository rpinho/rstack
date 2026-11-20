"""Cost per PASSED everyday task, as a share of a plan's weekly allowance (11-20, general's decision).

Cost is never dollars (no pay-as-you-go). A job's cost is the weekly-percent delta of its executor over the
job's start/end window:
  claude  ~/.local/state/rstack/usage/claude-history.jsonl   (weekly_percent every 15 minutes)
  codex   ~/.local/state/rstack/codex-ledger/*.jsonl         (weekly_before / weekly_after snapshots of every call)
  agy     no source: the launch receipts carry no tokens and agy-quota.jsonl logs only quota errors, so agy
          jobs are never costed and show "-".
Window: the launch receipt's utc (start) to the job log's last write (end). Jobs on the same executor whose
windows overlap are "shared" (the receipts hold no tokens to split by) and stay out of the average. A reading
that is missing, stale (more than SLACK seconds from the window edge) or from another weekly window gives no
cost. Every failure here degrades to "no cost" and is never raised: the harness does not get in the way.

cost per passed task = total attributed cost / number of PASS grades, shown once a model has MIN_COSTED
graded everyday tasks with a cost. It never ranks: it breaks ties and informs routing, nothing else. Bench rows
never enter (only everyday-grades.jsonl is read).
"""
import collections
import datetime as dt
import json
import os
from pathlib import Path

MIN_COSTED = 5
SLACK = 1800          # seconds a reading may sit from the window edge
STATE = Path(os.environ.get('RSTACK_STATE', '~/.local/state/rstack')).expanduser()


def _ts(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError):
        return None


def _lines(path):
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        return
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row


def series(state=None):
    """{'claude': [(ts, percent, window)], 'codex': [...]} sorted by time; window names the weekly reset."""
    state = Path(state) if state else STATE
    out = {'claude': [], 'codex': []}
    for r in _lines(state / 'usage' / 'claude-history.jsonl'):
        t, p = _ts(r.get('at')), r.get('weekly_percent')
        if t is not None and isinstance(p, (int, float)):
            out['claude'].append((t, float(p), str(r.get('resets_at'))))
    seen = set()
    for path in sorted((state / 'codex-ledger').glob('*.jsonl')) if (state / 'codex-ledger').is_dir() else ():
        for r in _lines(path):
            for key in ('weekly_before', 'weekly_after'):
                w = r.get(key)
                if not isinstance(w, dict):
                    continue
                t, p = _ts(w.get('snapshot_at')), w.get('weekly_used_percent')
                if t is None or not isinstance(p, (int, float)):
                    continue
                item = (t, float(p), str(w.get('resets_at')))
                if item not in seen:
                    seen.add(item)
                    out['codex'].append(item)
    for rows in out.values():
        rows.sort()
    return out


def delta(rows, start, end):
    """Weekly percent used between start and end, or None when the readings cannot say."""
    before = [r for r in rows if r[0] <= start and start - r[0] <= SLACK]
    after = [r for r in rows if r[0] >= end and r[0] - end <= SLACK]
    if not before or not after:
        return None
    b, a = before[-1], after[0]
    if b[2] != a[2] or a[1] < b[1]:
        return None
    return a[1] - b[1]


def windows(receipts):
    """{job: (executor, start, end)} from launch receipts; end is the job log's last write."""
    out = {}
    root = Path(receipts) if receipts else None
    if not root or not root.is_dir():
        return out
    for path in root.glob('*.selection.json'):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        name = path.name
        for suffix in ('.log.selection.json', '.selection.json'):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        job = row.get('job') or name
        start = _ts(row.get('utc'))
        if start is None:
            continue
        end = None
        for candidate in (root / (name + '.log'), root / (name + '.last.md')):
            try:
                end = candidate.stat().st_mtime
                break
            except OSError:
                continue
        if end is not None and end >= start:
            out[job] = (row.get('executor'), start, end)
    return out


def grades(receipts):
    """{job: row} of the final everyday grade per job; retracted ids are dropped, ungraded rows ignored."""
    rows = list(_lines(Path(receipts) / 'everyday-grades.jsonl')) if receipts else []
    retracted = {r.get('id') for r in rows
                 if r.get('source_kind') == 'everyday' and str(r.get('grade')).lower() == 'retracted'}
    out = {}
    for r in rows:
        if r.get('source_kind') != 'everyday' or r.get('id') in retracted:
            continue
        if str(r.get('grade')).lower() in ('pass', 'partial', 'fail') and r.get('job'):
            out[r['job']] = r
    return out


def job_costs(receipts, state=None):
    """{job: percent | 'shared' | None} for every windowed job."""
    try:
        wins, data = windows(receipts), series(state)
    except Exception:           # never in the way
        return {}
    costs = {}
    for job, (executor, start, end) in wins.items():
        if any(o != job and e == executor and s <= end and start <= f for o, (e, s, f) in wins.items()):
            costs[job] = 'shared'
        elif executor in data:
            costs[job] = delta(data[executor], start, end)
        else:
            costs[job] = None
    return costs


def per_pass(receipts, canon, state=None):
    """{(role, canonical model): {'n': costed graded tasks, 'passes': n, 'pct': total, 'per_pass': x | None}}.

    per_pass is None until MIN_COSTED costed graded tasks exist and at least one passed."""
    try:
        costs, graded = job_costs(receipts, state), grades(receipts)
    except Exception:
        return {}
    acc = collections.defaultdict(lambda: {'n': 0, 'passes': 0, 'pct': 0.0})
    for job, g in graded.items():
        cost = costs.get(job)
        model = canon(g.get('model') or g.get('producer'))
        if not model or not g.get('role') or not isinstance(cost, (int, float)):
            continue
        a = acc[(g['role'], model)]
        a['n'] += 1
        a['pct'] += cost
        a['passes'] += str(g.get('grade')).lower() == 'pass'
    for a in acc.values():
        a['per_pass'] = round(a['pct'] / a['passes'], 3) if a['n'] >= MIN_COSTED and a['passes'] else None
    return dict(acc)
