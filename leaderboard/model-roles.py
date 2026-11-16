#!/usr/bin/env python3
"""Local outcome ledger, conservative role ranking and a minimal Markdown export.

No archive, account or transcript discovery. `ingest` reads explicitly configured
idea histories, review receipts and draft outcomes. Public export selects model,
role, score and date fields.
"""
import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('MODEL_STATE', str(Path('.runtime/leaderboard')))).expanduser()
LEDGER = Path(os.environ.get('MODEL_LEDGER', str(STATE / 'evaluations.jsonl'))).expanduser()
ROLES_FILE = Path(os.environ.get('RH_ROLES_FILE', str(Path('.runtime/roles.json')))).expanduser()
RH_LANES = Path(os.environ.get('RH_EVIDENCE_ROOT', str(STATE / 'no-evidence-root'))) / 'lanes'
MIN_N, MIN_DAYS, SEED_RATE, LIFT_N, SETTLE_DAYS, Z = 5, 2, 0.75, 20, 14, 1.96
MIN_LABS = {'ideation': 2}
OVERRIDES = {}  # Set via a private MODEL_OVERRIDES config file; never included in export.
if os.environ.get('MODEL_OVERRIDES'):
    OVERRIDES = json.loads(Path(os.environ['MODEL_OVERRIDES']).read_text())
NOT_NEW = re.compile(r'already known|not new|prior art|duplicate', re.I)
CLOSE_FAULTS_PROPOSAL = {'prior-art', 'duplicate', 'rule-blocked'}
CLOSE_NEUTRAL = {'bar-failed', 'infeasible', 'superseded', 'other'}
RULE_BLOCKED = re.compile(r'rule-blocked|prohibited|not allowed|forbidden|holdout violat', re.I)

MODELS = {'anthropic/claude-opus-5.5': ('claude', 'claude-opus-5-5'),
 'anthropic/claude-fable-5.1': ('claude', 'claude-fable-5-1'),
 'anthropic/claude-fable-5.2': ('claude', 'claude-fable-5-2'),
 'anthropic/claude-sonnet-5.5': ('claude', 'claude-sonnet-5-5'),
 'anthropic/claude-haiku-5.5': ('claude', 'claude-haiku-5-5'),
 'anthropic/claude-opus-4.6': ('claude', 'claude-opus-4-6'),
 'openai/gpt-6.1-sol': ('codex', 'gpt-6.1-sol'),
 'openai/gpt-6-astra': ('codex', 'gpt-6-astra'),
 'openai/gpt-6.1-terra': ('codex', 'gpt-6.1-terra'),
 'openai/gpt-6-luna': ('codex', 'gpt-6-luna'),
 'openai/gpt-5.6-sol': ('codex', 'gpt-5.6-sol'),
 'deepseek/deepseek-v4.1-flash-1017': ('openrouter', 'deepseek/deepseek-v4.1-flash-1017'),
 'z-ai/glm-5.3-flash': ('openrouter', 'z-ai/glm-5.3-flash'),
 'moonshotai/kimi-k3.1-pro': ('openrouter', 'moonshotai/kimi-k3.1-pro'),
 'x-ai/grok-4.6': ('openrouter', 'x-ai/grok-4.6'),
 'google/gemini-4-argon': ('gemini', 'google/gemini-4-argon'),
 'google/gemini-4-carbon': ('gemini', 'google/gemini-4-carbon'),
 'google/gemini-4-hydrogen': ('gemini', 'google/gemini-4-hydrogen')}

ALIASES = [('opus[- ]?5[.-]5', 'anthropic/claude-opus-5.5'),
 ('fable[- ]?5[.-]1|fable-5-1', 'anthropic/claude-fable-5.1'),
 ('sonnet[- ]?5[.-]5', 'anthropic/claude-sonnet-5.5'),
 ('haiku[- ]?5[.-]5', 'anthropic/claude-haiku-5.5'),
 ('opus[- ]?4[.-]6', 'anthropic/claude-opus-4.6'),
 ('5\\.6-sol', 'openai/gpt-5.6-sol'),
 ('6\\.1-sol|^sol\\b', 'openai/gpt-6.1-sol'),
 ('astra', 'openai/gpt-6-astra'),
 ('terra', 'openai/gpt-6.1-terra'),
 ('luna', 'openai/gpt-6-luna'),
 ('deepseek', 'deepseek/deepseek-v4.1-flash-1017'),
 ('glm', 'z-ai/glm-5.3-flash'),
 ('kimi', 'moonshotai/kimi-k3.1-pro'),
 ('grok[- ]?4\\.6', 'x-ai/grok-4.6'),
 ('argon', 'google/gemini-4-argon'),
 ('carbon', 'google/gemini-4-carbon'),
 ('hydrogen', 'google/gemini-4-hydrogen')]

SEED = {'taste': ['anthropic/claude-opus-5.5', 'anthropic/claude-fable-5.2'],
 'review': ['anthropic/claude-opus-5.5',
            'openai/gpt-6-astra',
            'anthropic/claude-fable-5.2',
            'openai/gpt-6.1-sol'],
 'mechanical': ['openai/gpt-6.1-sol', 'deepseek/deepseek-v4.1-flash-1017'],
 'builder': ['anthropic/claude-opus-5.5', 'openai/gpt-6.1-sol'],
 'cheap': ['deepseek/deepseek-v4.1-flash-1017', 'z-ai/glm-5.3-flash'],
 'biology': ['moonshotai/kimi-k3.1-pro'],
 'batch': ['openai/gpt-6.1-sol', 'deepseek/deepseek-v4.1-flash-1017'],
 'writing': ['anthropic/claude-opus-5.5'],
 'ideation': ['anthropic/claude-opus-5.5', 'openai/gpt-6-astra', 'moonshotai/kimi-k3.1-pro']}

FIELD_ROLE = {'scientific-verification': 'mechanical',
 'independent-review': 'review',
 'causal-diagnosis': 'builder',
 'cross-layer-debugging': 'builder',
 'system-recovery': 'builder',
 'recovery-tooling': 'builder',
 'scientific-pipeline': 'builder',
 'prioritization': 'taste',
 'scientific-interpretation': 'taste'}

SEED['design'] = list(SEED['taste'])
SEED['judge'] = list(SEED['review'])
ROLES = tuple(SEED)
# Listed challengers enter after the existing seeds at the usual unscored rate.
# They must earn promotion under the same five-outcomes-on-two-days rule.
CANDIDATES = {role: ['google/gemini-4-carbon', 'google/gemini-4-hydrogen']
              for role in ('review', 'judge', 'ideation', 'design', 'mechanical', 'batch')}


def close_faults_proposal(row, prose):
    """True = this close counts against the proposer, False = counts neither way, from close_kind if present.

    Falls back to the prose match for rows closed before rh had the field.
    """
    kind = str(row.get("close_kind") or "").strip().lower()
    if kind in CLOSE_FAULTS_PROPOSAL:
        return True
    if kind in CLOSE_NEUTRAL:
        return False
    return bool(prose)


def canon(s):
    s = (s or "").lower().strip()
    if s in MODELS:
        return s
    for canonical, (_, native) in MODELS.items():
        if s == native:
            return canonical
    # Versioned native names and canonical provider IDs register their own routes.
    # A bare family name is deliberately insufficient to identify a model version.
    if re.fullmatch(r'claude-[a-z]+-\d+(?:[.-]\d+)+', s):
        canonical = 'anthropic/' + re.sub(r'-(\d+)-(\d+)$', r'-\1.\2', s)
    elif re.fullmatch(r'gpt-\d+(?:\.\d+)?-[a-z0-9.-]+', s):
        canonical = 'openai/' + s
    elif re.fullmatch(r'[a-z][a-z0-9-]*/[a-z][a-z0-9_.-]*', s):
        canonical = s
    else:
        for pat, c in ALIASES:
            if re.search(pat, s):
                return c
        return None
    provider, name = canonical.split('/', 1)
    cli = {'anthropic': 'claude', 'openai': 'codex'}.get(provider, 'openrouter')
    native = re.sub(r'(\d+)\.(\d+)', r'\1-\2', name) if provider == 'anthropic' else name if provider == 'openai' else canonical
    MODELS[canonical] = (cli, native)
    return canonical


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_ts(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def days_old(ts):
    t = parse_ts(ts)
    return (now() - t).days if t else 0


def jsonl(path):
    out = []
    try:
        for line in open(path):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def obs(source, item, model, role, outcome, date, evidence, note):
    """One resolved outcome, in the ledger's own format (scripts/model-eval.py validates it)."""
    key = "|".join((source, item, model, role))
    case = f"{source}:{item}"
    if len(case) > 120:
        case = case[:103] + "-" + hashlib.sha1(case.encode()).hexdigest()[:16]
    return {"id": "auto-" + hashlib.sha1(key.encode()).hexdigest()[:12], "case": case,
            "date": date[:10], "model": model, "effort": "as run", "route": MODELS[model][0], "role": "harness",
            "task_family": f"auto-{role}", "layer": "model", "score": 4 if outcome == "held" else 0,
            "cost_usd": None, "evidence": [str(e) for e in evidence], "note": note,
            "pick_role": role, "source": source, "outcome": outcome}


def from_rh():
    """rh taste calls (promote/close with decided_by), judged by what later happened to the idea."""
    out, pending, unattributed = [], 0, 0
    for path in sorted(RH_LANES.glob("*/IDEAS.jsonl")):
        rows = jsonl(path)
        by_id = collections.defaultdict(list)
        for r in rows:
            by_id[r.get("id")].append(r)
        for r in rows:
            who = r.get("decided_by") or ""
            if not who or r.get("mechanical") or "mechanical" in who or r.get("event") not in ("close", "promote"):
                continue
            model = canon(who)
            if not model:
                unattributed += 1
                continue
            when = r.get("revised") or r.get("created") or ""
            later = [x for x in by_id[r.get("id")] if (x.get("revised") or x.get("created") or "") > when]
            outcome = None
            if r["event"] == "close":
                if any(x.get("status") in ("new", "testing", "shipped") for x in later):
                    outcome = "overturned"
                elif days_old(when) >= SETTLE_DAYS:
                    outcome = "held"
            else:
                end = next((x for x in later if x.get("status") in ("shipped", "closed")), None)
                why = (end or {}).get("closed_reason") or ""
                if end is None:
                    outcome = None
                elif end["status"] == "shipped":
                    outcome = "held"
                elif close_faults_proposal(end, NOT_NEW.search(why)):
                    outcome = "overturned"
            if outcome is None:
                pending += 1
                continue
            out.append(obs("rh", f"{path.parent.name}/{r['id']}/{r['event']}", model, "taste", outcome, when,
                           [str(path)], f"rh {r['event']} by {who}; {outcome} by the idea's later history"))
    return out, pending, unattributed


def linked_outcomes():
    spec = importlib.util.spec_from_file_location('outcome_adapters', HERE / 'outcome_adapters.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect(
        os.environ.get('RH_EVIDENCE_ROOT'), os.environ['RH_LAUNCH_RECEIPTS'], canon, obs,
        os.environ.get('MODEL_OUTCOMES_ROOT'), os.environ.get('MODEL_UPSTREAM_ROOT'),
        os.environ.get('MODEL_LAUNCH_ROOT'), os.environ.get('MODEL_TRANSCRIPTS_ROOT'))


def ingest(write=True):
    existing = {r["id"]: r for r in validate(LEDGER.read_text())} if LEDGER.exists() else {}
    latest = {}                                  # case-key -> newest active auto row
    for r in existing.values():
        if r.get("source"):
            latest[(r["case"], r["model"], r.get("pick_role"))] = r
    new, stats = [], {}
    adapters = ADAPTERS
    if os.environ.get('RH_LAUNCH_RECEIPTS'):
        receipt_rows, receipt_stats = linked_outcomes()
        adapters = {}  # This mode admits only outcomes joined to launch receipts.
        for kind, counts in receipt_stats.items():
            if kind.startswith('_'):
                continue
            matching = [r for r in receipt_rows if r['source_kind'] == kind]
            adapters['receipt-' + kind] = lambda r=matching, c=counts: (r, c['pending'], c['unlinked'])
    for name, fn in adapters.items():
        rows, pending, unattributed = fn()
        stats[name] = {"resolved": len(rows), "pending": pending, "unattributed": unattributed, "unlinked": unattributed}
        if os.environ.get('RH_LAUNCH_RECEIPTS'):
            stats[name]['link_kinds'] = dict(collections.Counter(r['link_kind'] for r in rows))
        for r in rows:
            prev = latest.get((r["case"], r["model"], r["pick_role"]))
            if prev and prev["outcome"] == r["outcome"]:
                continue
            if prev:                              # outcome flipped: supersede, never edit
                r["id"] = r["id"] + "-" + hashlib.sha1((prev["id"] + r["outcome"]).encode()).hexdigest()[:8]
                if r["id"] in existing:
                    continue
                r["supersedes"] = prev["id"]
            new.append(r)
            latest[(r["case"], r["model"], r["pick_role"])] = r
    if write and new:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new)
        validate((LEDGER.read_text() if LEDGER.exists() else '') + text)        # the ledger's own validator, before anything is written
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(text)
    return new, stats


def wilson_low(k, n):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + Z * Z / n
    return (p + Z * Z / (2 * n) - Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))) / d


def evidence():
    rows = validate(LEDGER.read_text()) if LEDGER.exists() else []
    retired = {r["supersedes"] for r in rows if r.get("supersedes")}
    ev = collections.defaultdict(lambda: collections.defaultdict(lambda: {"n": 0, "k": 0, "days": set()}))
    for r in rows:
        if r["id"] in retired:
            continue
        model = canon(r.get("model"))
        if not model:
            continue
        if r.get("pick_role") == "corrections":
            continue                              # reported as a rate, never ranked; see CORRECTIONS_CAVEAT
        if r.get("pick_role"):
            role, ok = r["pick_role"], r.get("outcome") == "held"
        elif r.get("task_family") in FIELD_ROLE and r.get("score") in (0, 1, 3, 4):
            role, ok = FIELD_ROLE[r["task_family"]], r["score"] >= 3
        else:
            continue
        e = ev[role][model]
        e["n"] += 1
        e["k"] += ok
        e["days"].add(r.get("date", "")[:10])
    return ev


def lab(model):
    return str(model).split("/")[0]


def spread_labs(order, min_labs):
    """Pull models forward so the first `min_labs` picks come from distinct labs, keeping the rest in place.

    A caller that takes the top 2 or 3 of a role should get that many perspectives, not two runs of the same
    model family. Everything below the constraint keeps its evidence order, and a list that cannot satisfy it
    (only one lab available) is returned untouched rather than padded.
    """
    if min_labs <= 1 or len(order) < 2:
        return order
    out, rest = [], list(order)
    while rest and len(out) < min_labs:
        seen = {lab(m) for m in out}
        pick = next((m for m in rest if lab(m) not in seen), None)
        if pick is None:
            break
        out.append(pick)
        rest.remove(pick)
    return out + rest


def rank(role, ev):
    e = ev.get(role, {})
    def eligible(m):
        return e.get(m, {}).get("n", 0) >= MIN_N and len(e[m]["days"]) >= MIN_DAYS
    def rate(m):
        return e[m]["k"] / e[m]["n"] if eligible(m) else SEED_RATE
    def low(m):
        return wilson_low(e[m]["k"], e[m]["n"]) if eligible(m) else -1
    pool = list(SEED[role]) + CANDIDATES.get(role, [])
    order = pool + sorted((m for m in e if m not in pool), key=low, reverse=True)
    for _ in range(len(order) ** 2):              # stable bubble: pass only on evidence
        swapped = False
        for i in range(len(order) - 1):
            a, b = order[i], order[i + 1]
            if eligible(b) and low(b) > rate(a):
                order[i], order[i + 1] = b, a
                swapped = True
        if not swapped:
            break
    order = spread_labs(order, MIN_LABS.get(role, 1))
    flags = []
    ov = OVERRIDES.get(role)
    if ov:
        for m in ov["exclude"]:
            second = order[1] if len(order) > 1 else None
            if (m in e and e[m]["n"] >= LIFT_N and second and second != m
                    and wilson_low(e[m]["k"], e[m]["n"]) >= rate(second)):
                flags.append(f"{m} exclusion LIFTED by evidence (n={e[m]['n']}); override dated {ov['date']}")
            elif m in order:
                order.remove(m)
    return order, flags

REVIEW_ROOT = Path(os.environ['MODEL_REVIEW_ROOT']).expanduser() if os.environ.get('MODEL_REVIEW_ROOT') else None
DRAFTS_LOG = Path(os.environ['MODEL_DRAFTS_LOG']).expanduser() if os.environ.get('MODEL_DRAFTS_LOG') else None
SENT_AS_DRAFTED = 'sent_as_drafted'


def from_ideation():
    """Credit the proposed_by model for reaching testing; a fair kill is neutral."""
    out, pending, unattributed = [], 0, 0
    for path in sorted(RH_LANES.glob("*/IDEAS.jsonl")):
        rows = jsonl(path)
        by_id = collections.defaultdict(list)
        for r in rows:
            by_id[r.get("id")].append(r)
        for r in rows:
            if r.get("event") not in (None, "add", "import") or not r.get("claim"):
                continue
            model = canon(r.get("proposed_by") or r.get("proposer_model") or "")
            if not model:
                unattributed += 1
                continue
            when = r.get("created") or ""
            history = by_id[r.get("id")]
            tested = any(x.get("status") in ("testing", "shipped") for x in history)
            latest = max(history, key=lambda x: x.get("revised") or x.get("created") or "")
            why = latest.get("closed_reason") or ""
            if tested:
                outcome = "held"
            elif latest.get("status") == "closed" and close_faults_proposal(
                    latest, NOT_NEW.search(why) or RULE_BLOCKED.search(why)):
                outcome = "overturned"
            else:
                pending += 1          # still new, or killed at its bar: neither is evidence about the proposal
                continue
            out.append(obs("ideation", f"{path.parent.name}/{r['id']}", model, "ideation", outcome, when,
                           [str(path)],
                           f"idea {outcome} at prior art and review (reached testing: {tested})"))
    return out, pending, unattributed



def from_reviews():
    """*.reviews.json: a FLAG that led to a new version held; a PASS on that same version missed it."""
    out, pending, unattributed = [], 0, 0
    files = sorted(REVIEW_ROOT.rglob('*.reviews.json')) if REVIEW_ROOT else []
    docs = [(f, json.load(open(f))) for f in files]
    by_doc = collections.defaultdict(list)
    for f, d in docs:
        # some receipts carry no date; fall back to the file's own mtime rather than writing an empty date
        date = d.get("date") or dt.date.fromtimestamp(os.path.getmtime(f)).isoformat()
        by_doc[d.get("file") or f].append((date, d.get("sha256"), f, d))
    for doc, versions in by_doc.items():
        versions.sort(key=lambda v: v[0])
        for i, (date, sha, f, d) in enumerate(versions):
            revs = [r for r in d.get("reviews", []) if isinstance(r, dict)]
            flagged = [r for r in revs if str(r.get("verdict", "")).upper() not in ("PASS", "")]
            newer = any(v[1] != sha for v in versions[i + 1:])
            for r in revs:
                model = canon(r.get("model") or r.get("reviewer"))
                if not model:
                    unattributed += 1
                    continue
                passed = str(r.get("verdict", "")).upper() == "PASS"
                if flagged and newer:
                    outcome = "overturned" if passed else "held"
                elif not flagged and not newer and days_old(date) >= SETTLE_DAYS:
                    outcome = "held"
                else:
                    pending += 1
                    continue
                out.append(obs("review", f"{Path(doc).name}@{(sha or '')[:8]}", model, "review", outcome, date,
                               [f], f"{r.get('verdict')}; {len(flagged)} flagged; newer version: {newer}"))
    return out, pending, unattributed



def from_drafts():
    """Score explicit draft outcomes. Recipient fields are deliberately never read."""
    out, pending, unattributed = [], 0, 0
    for row in (jsonl(DRAFTS_LOG) if DRAFTS_LOG else []):
        model, outcome = canon(row.get("model")), str(row.get("outcome") or "")
        utc, sha = row.get("utc") or "", str(row.get("draft_sha") or "")[:16]
        if not model:
            unattributed += 1
            continue
        if outcome not in (SENT_AS_DRAFTED, "rewritten", "dropped") or not sha or not parse_ts(utc):
            pending += 1
            continue
        channel = re.sub(r"[^a-z0-9_-]", "", str(row.get("channel") or "msg").lower())[:16]
        out.append(obs("message-draft", f"{channel}/{sha}", model, "writing",
                       "held" if outcome == SENT_AS_DRAFTED else "overturned", utc, [str(DRAFTS_LOG)],
                       f"{channel} draft {outcome}"))
    return out, pending, unattributed



ADAPTERS = {'rh': from_rh, 'ideation': from_ideation, 'review': from_reviews, 'message-draft': from_drafts}


def validate(text):
    spec = importlib.util.spec_from_file_location('model_eval', HERE / 'model-eval.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'ledger.jsonl'
        path.write_text(text)
        return module.load_rows(path)


def write_roles(data, path=ROLES_FILE):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def recompute(write=True):
    ev = evidence()
    if os.environ.get('RH_LAUNCH_RECEIPTS'):
        _, source_stats = linked_outcomes()
        for entry in source_stats.get('_entries', []):
            if entry['role'] in ROLES:
                ev[entry['role']][entry['model']]  # Enter an observed role before it is scored.
    out = {'schema': 1, 'updated': now().isoformat(timespec='seconds'), 'roles': {},
           'routes': {native: {'cli': cli, 'canonical': canonical}
                      for canonical, (cli, native) in MODELS.items()}, 'evidence': {},
           'overrides': OVERRIDES, 'min_labs': MIN_LABS}
    for role in ROLES:
        order, _ = rank(role, ev)
        out['roles'][role] = [MODELS[m][1] for m in order]
        out['evidence'][role] = {MODELS[m][1]: {'n': v['n'], 'rate': round(v['k']/v['n'], 3),
                      'low': round(wilson_low(v['k'], v['n']), 3), 'days': len(v['days']), 'scored': m in SEED[role] or (v['n'] >= MIN_N and len(v['days']) >= MIN_DAYS)}
                      for m, v in ev.get(role, {}).items() if v['n']}
    if write:
        write_roles(out)
    return out


def safe_cell(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_.:-]*', value):
        raise ValueError('invalid public model or role')
    return value


def score(value):
    if value is None:
        return '-'
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('invalid public score')
    return str(round(value, 3))


def snapshot_rows(path):
    """Read only the two public table schemas; never copy arbitrary page prose."""
    tables = {6: [], 4: []}
    if not path or not Path(path).is_file():
        return tables
    for line in Path(path).read_text().splitlines():
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if not line.startswith('| ') or len(cells) not in tables or cells[0] == 'Role':
            continue
        role, model = cells[:2]
        safe_cell(role); safe_cell(model)
        if role not in ROLES or not canon(model):
            raise ValueError('unknown public role or model in snapshot')
        dt.date.fromisoformat(cells[-1])
        if len(cells) == 6:
            if cells[2] != '-' and (not cells[2].isdigit() or int(cells[2]) < 1):
                raise ValueError('invalid routing position in snapshot')
            for value in cells[3:5]:
                if value != '-':
                    score(float(value))
        elif not re.fullmatch(r'[0-4](?:, [0-4])*', cells[2]):
            raise ValueError('invalid observation scores in snapshot')
        tables[len(cells)].append('| ' + ' | '.join(cells) + ' |')
    return tables


def public(data, path, observations=(), previous=None):
    """Allowlist fields. Unranked observations use '-' in the routing order column."""
    date = dt.datetime.fromisoformat(data['updated'].replace('Z', '+00:00')).date().isoformat()
    old = snapshot_rows(previous if previous is not None else path)
    lines = ['# Model leaderboard', '',
             'A dated routing snapshot from selected local harness outcomes. Scores are held-outcome rates and 95% Wilson lower bounds. A dash means unscored; starting orders include operator seed choices. This is not a universal benchmark.', '',
             '| Role | Model | Routing order | Held score | Wilson lower score | Date |',
             '|---|---|---:|---:|---:|---|']
    # A rerun on the same day replaces that day's routing rows; older days are kept (merge, never erase).
    lines.extend(l for l in old[6] if not l.rstrip().endswith(f'| {date} |'))
    for role, ranked in data['roles'].items():
        safe_cell(role)
        if role not in ROLES:
            raise ValueError('unknown public role')
        role_scores = data.get('evidence', {}).get(role, {})
        for model in list(ranked) + sorted(set(role_scores) - set(ranked)):
            safe_cell(model)
            if model not in {native for _, native in MODELS.values()}:
                raise ValueError('unknown public model')
            observation = role_scores.get(model, {})
            if observation.get('scored') is False:
                observation = {}
            order = str(ranked.index(model) + 1) if model in ranked else '-'
            line = f"| {role} | {model} | {order} | {score(observation.get('rate'))} | {score(observation.get('low'))} | {date} |"
            if line not in lines:
                lines.append(line)
    groups = collections.defaultdict(list)
    for observation in observations:
        canonical = canon(observation.get('model'))
        role = observation.get('pick_role') or FIELD_ROLE.get(observation.get('task_family'))
        value = observation.get('score')
        if canonical not in MODELS or role not in ROLES or value is None:
            continue
        if type(value) is not int or value not in range(5):
            raise ValueError('invalid observation score')
        day = dt.date.fromisoformat(observation['date'][:10]).isoformat()
        groups[(role, MODELS[canonical][1], day)].append(value)
    if groups or old[4]:
        lines += ['', '## Recorded observation scores', '',
                  'Selected local labels on a 0–4 scale, including proxy and operational outcomes. Repeated scores are retained; no task identifiers or text are exported. These labels are not matched benchmark trials.', '',
                  '| Role | Model | Scores | Date |', '|---|---|---|---|']
        # Recomputed (role, model, day) cells replace their earlier copy instead of sitting beside it.
        fresh = {(f'| {r} | {m} |', day) for r, m, day in groups}
        lines.extend(l for l in old[4] if not any(l.startswith(k) and l.rstrip().endswith(f'| {v} |')
                                                  for k, v in fresh))
        for (role, model, day), values in sorted(groups.items()):
            line = f"| {role} | {model} | {', '.join(map(str, sorted(values)))} | {day} |"
            if line not in lines:
                lines.append(line)
    lines += ['', 'Ranking method and limits: [leaderboard/README.md](leaderboard/README.md).', '']
    Path(path).write_text('\n'.join(lines))
    return Path(path)


def bootstrap(path):
    """Recover routes from the single public snapshot. No private ledger is shipped."""
    roles = collections.defaultdict(list)
    dates, snapshots = [], collections.defaultdict(dict)
    for line in Path(path).read_text().splitlines():
        if not line.startswith('| '):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 6 or cells[0] == 'Role':
            continue
        role, model, position, _, _, date = cells
        safe_cell(role); safe_cell(model)
        if role not in ROLES:
            raise ValueError('unknown role')
        if model.startswith('claude-') or model.startswith('gpt-') or '/' in model:
            canon(model)
        dt.date.fromisoformat(date)
        dates.append(date)
        snapshots[(role, date)][model] = position
    for role in {r for r, _ in snapshots}:
        latest = max(date for r, date in snapshots if r == role)
        for model, position in snapshots[(role, latest)].items():
            if position != '-':
                roles[role].append((int(position), model))
    if not roles:
        raise ValueError('snapshot has no routing roles')
    routes = {native: {'cli': cli, 'canonical': canonical}
              for canonical, (cli, native) in MODELS.items()}
    for rows in roles.values():
        if sorted(p for p, _ in rows) != list(range(1, len(rows) + 1)) or any(m not in routes for _, m in rows):
            raise ValueError('invalid routing order or unknown route')
    return {'schema': 1, 'updated': max(dates) + 'T00:00:00+00:00',
            'roles': {r: [m for _, m in sorted(rows)] for r, rows in roles.items()},
            'routes': routes, 'evidence': {}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('bootstrap', 'ingest', 'recompute', 'daily', 'status', 'public'))
    parser.add_argument('--snapshot', type=Path, default=HERE.parent / 'LEADERBOARD.md')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'bootstrap':
            data = bootstrap(args.snapshot)
            write_roles(data, args.output or ROLES_FILE)
        elif args.command in ('ingest', 'daily'):
            if not any(os.environ.get(key) for key in ('RH_EVIDENCE_ROOT', 'MODEL_REVIEW_ROOT', 'MODEL_DRAFTS_LOG', 'MODEL_OUTCOMES_ROOT', 'MODEL_UPSTREAM_ROOT')):
                raise ValueError('ingest requires explicit RH_EVIDENCE_ROOT, MODEL_REVIEW_ROOT, MODEL_DRAFTS_LOG, MODEL_OUTCOMES_ROOT or MODEL_UPSTREAM_ROOT')
            _, stats = ingest()
            print(json.dumps(stats))
            if args.command == 'daily':
                recompute()
        elif args.command == 'recompute':
            recompute()
        elif args.command == 'public':
            data = json.loads(ROLES_FILE.read_text())
            for route in data.get('routes', {}).values():
                canon(route.get('canonical'))
            observations = validate(LEDGER.read_text()) if LEDGER.exists() else []
            print(public(data, args.output or args.snapshot, observations, previous=args.snapshot))
        else:
            print(json.dumps(recompute(write=False), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
