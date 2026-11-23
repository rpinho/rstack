"""Claude weekly ceiling, burn-rate pacing, Sonnet default and per-lane shares, applied at launch (11-20).

Ricardo, 11-20: "Claude must never reach 100%; Sonnet is the default; MecCog is not that important."
General's orchestration runs on Claude, so at 100% he loses it even when Codex has room. These rules are
code, applied by worker_models.select() to every Claude pick, and the receipt says which one fired.

  ceiling   weekly >= RH_CLAUDE_CEILING_PERCENT (80): Claude is refused, the job takes a fallback route
            (Codex default for the role, else agy's Claude). Warning from RH_CLAUDE_WARN_PERCENT (70).
  pacing    weekly + burn %/h x hours to reset > 80: Opus is moved to Sonnet; at >= RH_CLAUDE_PACE_OFF_PERCENT
            (100: on course to hit the wall) the job leaves Claude. Burn is the slope of
            usage/claude-history.jsonl (written by claude-usage) over the last 6 h, else this week's average.
  Sonnet   preferred Claude model for mechanical/batch/cheap picks only; judgment roles keep the leaderboard's pick.
  shares    ~/.config/rstack/claude-shares.json: {"LANE": {"max_week_percent": N, "models": ["sonnet"]}, "default": {...}}.

Lane attribution (limits): the usage endpoint reports one weekly figure and no breakdown. A lane's share is
its fraction of weighted tokens in Claude Code transcripts (~/.claude/projects/*/**.jsonl, since the week
began) times the weekly percent. Weight = input + output + cache writes + 0.1 x cache reads, times 5 for
Opus and 1 for Sonnet (a price ratio, not the account's real accounting). A transcript belongs to a lane when
its project directory name ends in the lane name or contains "lanes-<lane>", so interactive sessions in a
lane's worktree count too; a session in a directory without the lane's name does not, and is unattributed.
Chat and desktop use leaves no transcript, so the lane figures understate the total and the weekly figure
stays the hard bound.
"""
import json
import os
from pathlib import Path
import re
import time
try:
    import settings  # noqa: F401  11-22: loads the harness env file, so the Agent hook sees the selector's knobs
except ImportError:
    pass

CEILING = 80.0
WARN = 70.0
PACE_OFF = 100.0
SONNET = 'claude-sonnet-5-5'
LOW_JUDGMENT = ('mechanical', 'batch', 'cheap')   # roles where Sonnet is the preferred Claude model
WEEK_H = 168.0


def load_allowance():
    """Load the same usage reader from a checkout or the installed harness."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    here = Path(__file__).resolve().parent
    for tool in (here / 'rstack/tools/allowance', here.parent / 'rstack/tools/allowance'):
        if tool.is_file():
            spec = spec_from_loader('allowance', SourceFileLoader('allowance', str(tool)))
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    return None


def _f(name, default):
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


# 11-22 (Ricardo: "You have 5 hours to spend the money."): in the last hours before the weekly reset the
# ceiling rises to 95% and pacing is off on its own; the last 5% stays general's. Unused allowance is lost at
# the reset, so holding it back then only gets in the way (RULE #1). RH_CLAUDE_SPEND_DOWN_HOURS sets the window.
SPEND_DOWN_H = 6.0
SPEND_DOWN_CEILING = 95.0


def ceiling_knob(now=None):
    """RH_CLAUDE_CEILING_PERCENT, or the default once RH_CLAUDE_CEILING_UNTIL (ISO UTC) has passed, so a one-off
    raise ends on its own (11-22, Ricardo at 95% with 2 h to the reset: "honestly, you could spend it")."""
    until = os.environ.get('RH_CLAUDE_CEILING_UNTIL', '').strip()
    if until:
        try:
            import datetime as _dt
            if (time.time() if now is None else now) >= _dt.datetime.fromisoformat(until.replace('Z', '+00:00')).timestamp():
                return CEILING
        except ValueError:
            return CEILING
    return _f('RH_CLAUDE_CEILING_PERCENT', CEILING)


def spend_down(weekly, now=None):
    """True in the last RH_CLAUDE_SPEND_DOWN_HOURS hours before the weekly reset `weekly` names."""
    try:
        left = (float(weekly['resets_at']) - (time.time() if now is None else now)) / 3600
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= left <= _f('RH_CLAUDE_SPEND_DOWN_HOURS', SPEND_DOWN_H)


def enabled():
    return os.environ.get('RH_CLAUDE_CAP', '1') != '0'


def is_opus(model):
    return 'opus' in (model or '')


# ---- burn rate -------------------------------------------------------------------------------------------

def _usage_dir(allowance):
    fn = getattr(allowance, 'usage_dir', None)
    return fn() if fn else Path(os.environ.get('RSTACK_STATE_DIR') or Path.home() / '.local/state/rstack') / 'usage'


def history_path(allowance):
    return _usage_dir(allowance) / 'claude-history.jsonl'


def burn_rate(allowance, now, weekly, hours_left, window_h=6.0):
    """(percent per hour, basis). The slope of the last window_h of readings since any reset; with fewer than
    two readings an hour apart, this week's average so far."""
    rows = []
    try:
        for line in history_path(allowance).read_text().splitlines()[-2000:]:
            try:
                r = json.loads(line)
                at, pct = float(r['at']), float(r['weekly_percent'])
            except (ValueError, KeyError, TypeError):
                continue
            if now - window_h * 3600 <= at <= now + 300:
                rows.append((at, pct))
    except OSError:
        pass
    rows.sort()
    for i in range(len(rows) - 1, 0, -1):        # keep only the run since the last reset (a drop)
        if rows[i][1] < rows[i - 1][1] - 0.5:
            rows = rows[i:]
            break
    if len(rows) >= 2 and rows[-1][0] - rows[0][0] >= 3600:
        span = (rows[-1][0] - rows[0][0]) / 3600
        return max(0.0, (rows[-1][1] - rows[0][1]) / span), 'last {:.1f} h of readings'.format(span)
    elapsed = min(WEEK_H, max(1.0, WEEK_H - hours_left))
    return max(0.0, weekly / elapsed), 'week average over {:.0f} h'.format(elapsed)


# ---- lane shares -----------------------------------------------------------------------------------------

def shares_path():
    return Path(os.environ.get('RSTACK_CLAUDE_SHARES') or Path.home() / '.config/rstack/claude-shares.json')


def share_for(lane):
    """(key, {'max_week_percent', 'models'}) for the lane: exact name, else the longest key it starts with,
    else "default"; (None, None) when no file or no entry."""
    try:
        cfg = json.loads(shares_path().read_text())
    except (OSError, ValueError):
        return None, None
    if not isinstance(cfg, dict):
        return None, None
    keys = [k for k in cfg if k != 'default' and lane and (lane == k or lane.startswith(k))]
    key = max(keys, key=len) if keys else ('default' if isinstance(cfg.get('default'), dict) else None)
    return (key, cfg[key]) if key else (None, None)


def _norm(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def _weight(usage, model):
    try:
        w = (usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
             + usage.get('cache_creation_input_tokens', 0) + 0.1 * usage.get('cache_read_input_tokens', 0))
    except TypeError:
        return 0.0
    return w * (5.0 if 'opus' in (model or '') else 0.3 if 'haiku' in (model or '') else 1.0)


def lane_weights(since, projects=None):
    """({project dir name: weighted tokens since `since`}) from Claude Code transcripts."""
    root = Path(projects or os.environ.get('RH_CLAUDE_PROJECTS') or Path.home() / '.claude/projects')
    out = {}
    if not root.is_dir():
        return out
    for proj in root.iterdir():
        if not proj.is_dir():
            continue
        seen = {}
        for f in proj.rglob('*.jsonl'):
            try:
                if f.stat().st_mtime < since:
                    continue
                for line in f.open('r', errors='replace'):
                    if '"usage"' not in line:
                        continue
                    try:
                        r = json.loads(line)
                        m = r.get('message') or {}
                        ts = r.get('timestamp') or ''
                        usage = m.get('usage')
                        if not isinstance(usage, dict):
                            continue
                        from datetime import datetime
                        if datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp() < since:
                            continue
                        seen[m.get('id') or r.get('uuid') or id(r)] = _weight(usage, m.get('model'))
                    except (ValueError, AttributeError, TypeError):
                        continue
            except OSError:
                continue
        if seen:
            out[proj.name] = sum(seen.values())
    return out


def lane_percent(lane, weekly, since, now, allowance=None, projects=None):
    """(lane % of the weekly limit, note). Cached 10 min beside the usage file."""
    cache = None
    if allowance is not None:
        cache = _usage_dir(allowance) / 'claude-lanes-cache.json'
        try:
            c = json.loads(cache.read_text())
            if now - c['at'] < 600 and abs(c['since'] - since) < 60 and projects is None:
                weights = c['weights']
            else:
                raise KeyError
        except (OSError, ValueError, KeyError, TypeError):
            weights = None
    else:
        weights = None
    if weights is None:
        weights = lane_weights(since, projects)
        if cache is not None and projects is None:
            try:
                cache.write_text(json.dumps(dict(at=now, since=since, weights=weights)))
            except OSError:
                pass
    norm = _norm(lane)
    total = sum(weights.values())
    mine = sum(w for name, w in weights.items()
               if _norm(name).endswith('-' + norm) or ('-lanes-' + norm + '-') in (_norm(name) + '-'))
    if not total:
        return 0.0, 'no transcripts since the week began'
    pct = weekly * mine / total
    return pct, '{:.1f}% of {:g}% weekly (token-weighted transcripts, interactive worktree sessions included)'.format(pct, weekly)


# ---- the decision ----------------------------------------------------------------------------------------

def decide(model, lane, role, sonnet_ok, allowance, now=None, pinned=False, projects=None):
    """What a Claude pick may do. Returns dict(model, leave, notes, warning, opus_reason):
    leave is a reason string when Claude must be left for a fallback route, else ''.
    pressure describes account usage independently of lane shares. Pacing includes used, rate and hours."""
    now = time.time() if now is None else now
    notes, leave, warning = [], '', ''
    out = dict(model=model, leave='', notes=notes, warning='', pressure='normal')
    if not enabled():
        return out
    ceiling, warn, pace_off = ceiling_knob(now), _f('RH_CLAUDE_WARN_PERCENT', WARN), \
        _f('RH_CLAUDE_PACE_OFF_PERCENT', PACE_OFF)
    # Within the leaderboard's Claude picks, Sonnet is preferred for low-judgment roles only; judgment roles keep
    # the leaderboard's pick (an explicit --model or spec pin is the operator's own choice).
    if is_opus(model) and role in LOW_JUDGMENT and sonnet_ok and not pinned:
        out['model'] = model = SONNET
        notes.append('claude Sonnet 5.5 preferred for the {} role'.format(role))
    weekly = allowance.claude_weekly(now) if allowance else None
    if not weekly:
        out['pressure'] = 'unknown'
        notes.append('claude usage unknown: ceiling, pacing and shares not applied')
        return out
    used = float(weekly['weekly_used_percent'])
    resets = weekly.get('resets_at')
    hours = max((float(resets) - now) / 3600, 1.0) if resets else WEEK_H
    pacing = True
    if spend_down(weekly, now):
        ceiling, pacing = max(ceiling, SPEND_DOWN_CEILING), False
        notes.append('claude spend-down: {:.1f} h to the weekly reset, ceiling {:g}% and pacing off'.format(
            (float(resets) - now) / 3600, ceiling))
    if used >= ceiling:
        out['pressure'] = 'ceiling'
        out['leave'] = 'claude weekly at {:.0f}% >= {:g}% ceiling (the last {:g}% is general\'s)'.format(used, ceiling, 100 - ceiling)
        return out
    if used >= warn:
        out['warning'] = 'claude weekly at {:.0f}%: warning from {:g}%, ceiling {:g}%'.format(used, warn, ceiling)
    rate, basis = burn_rate(allowance, now, used, hours)
    projected = used + rate * hours
    if projected > ceiling and pacing:
        out.update(pressure='pacing', used=used, rate=rate, hours=hours)
        line = 'claude pacing: {:.0f}% + {:.1f}%/h ({}) x {:.0f} h to reset projects {:.0f}% > {:g}%'.format(
            used, rate, basis, hours, projected, ceiling)
        if projected >= pace_off:
            out['pressure'] = 'pace-off'
            out['leave'] = line + '; on course for the wall, job leaves Claude'
            return out
        if is_opus(model) and sonnet_ok and not pinned:
            out['model'] = model = SONNET
            notes.append(line + '; Opus downshifted to Sonnet 5.5')
        else:
            notes.append(line + '; already Sonnet')
    # per-lane share
    key, share = share_for(lane)
    if share:
        allowed = share.get('models')
        if allowed and not any(a in model for a in allowed) and sonnet_ok and any(a == 'sonnet' for a in allowed):
            out['model'] = model = SONNET
            notes.append('lane {} share allows {}: moved to Sonnet 5.5'.format(lane, '/'.join(allowed)))
        cap = share.get('max_week_percent')
        if isinstance(cap, (int, float)):
            since = float(resets) - WEEK_H * 3600 if resets else now - WEEK_H * 3600
            pct, note = lane_percent(lane, used, since, now, allowance, projects)
            if pct >= cap:
                out['leave'] = 'lane {} used {} >= its {:g}% share ({})'.format(lane, note, cap, key)
                # 11-22 (general): a 0% share is a Claude hold; its fallback leaves Claude altogether (agy Gemini).
                out['hold'] = cap <= 0
                return out
            notes.append('lane {} share: {} of {:g}% cap ({})'.format(lane, note, cap, key))
    return out
