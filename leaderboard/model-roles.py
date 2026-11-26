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
# Ricardo's own rank (taste + cost), copied from the KB leaderboard page "11-26 CURRENT RANK"; never computed from
# pass rates. A family rank covers every effort tier of that model; Neon's #1 is the high tier only.
OWNER_RANK = {'anthropic/claude-opus-5.5': 1, 'google/gemini-4-neon-high': 1, 'anthropic/claude-fable-5.2': 2,
              'openai/gpt-6.2-astra': 3, 'openai/gpt-6.2-sol': 4, 'anthropic/claude-sonnet-5.5': '5-6',
              **{f'google/gemini-4-{m}-{t}': 7 for m in ('argon', 'hydrogen') for t in ('low', 'medium', 'high')}}
MIN_LABS = {'ideation': 2}
OVERRIDES = {}  # Set via a private MODEL_OVERRIDES config file; never included in export.
if os.environ.get('MODEL_OVERRIDES'):
    OVERRIDES = json.loads(Path(os.environ['MODEL_OVERRIDES']).read_text())
NOT_NEW = re.compile(r'already known|not new|prior art|duplicate', re.I)
CLOSE_FAULTS_PROPOSAL = {'prior-art', 'duplicate', 'rule-blocked'}
CLOSE_NEUTRAL = {'bar-failed', 'infeasible', 'superseded', 'other'}
RULE_BLOCKED = re.compile(r'rule-blocked|prohibited|not allowed|forbidden|holdout violat', re.I)

# One resolver for every score writer and reader.
sys.path.insert(0, str(HERE.parent / 'harness'))
from model_slugs import MODELS, ALIASES, canon
import score_verdicts

# 11-19 Ricardo: "No pay-as-you-go. Do NOT top up OpenRouter." Every seed is a subscription route
# (claude -p, codex exec, agy); the OpenRouter seeds (DeepSeek, GLM, Kimi) are history-only below.
SEED = {'taste': ['anthropic/claude-opus-5.5', 'anthropic/claude-fable-5.2'],
 'review': ['anthropic/claude-opus-5.5',
            'openai/gpt-6.2-astra',
            'anthropic/claude-fable-5.2',
            'openai/gpt-6.2-sol'],
 'mechanical': ['openai/gpt-6.2-sol', 'anthropic/claude-sonnet-5.5'],
 'builder': ['anthropic/claude-opus-5.5', 'openai/gpt-6.2-sol'],
 'cheap': ['openai/gpt-6-luna', 'anthropic/claude-haiku-5.5'],
 'biology': ['anthropic/claude-opus-5.5', 'openai/gpt-6.2-astra'],
 'batch': ['openai/gpt-6.2-sol', 'anthropic/claude-sonnet-5.5'],
 'writing': ['anthropic/claude-opus-5.5'],
 'ideation': ['anthropic/claude-opus-5.5', 'openai/gpt-6.2-astra']}

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
# Google API routes and observations remain readable for historical tables only.
# Owner, 2026-11-18: "Spending OpenRouter money on Google is a waste".
# 11-19: Google on the agy subscription is not metered, so its Flash tiers enter as candidates: after every
# seed, with no evidence, and moved only by the same Wilson rule as any other model. No winner is picked here.
AGY_FLASH = ['google/gemini-3.8-flash-high', 'google/gemini-3.8-flash-medium']
# 11-20 (Ricardo: "yes, of course"): Neon is the main Gemini, so it is the candidate for judgment roles, at
# medium; Hydrogen is the cheap, fast one, for batch and mechanical work, at low or medium. Argon (the older main
# model, ~3.5x Sol's cost per task, weekly quota exhausted) is out of every pool, and Carbon (Ultra only) stays
# out. This changes who is a candidate, never the rank: ranks still come only from graded everyday work.
# 11-23 (Ricardo: "just do median for all of them, and for Neon and Hydrogen, we should try high"): no Gemini tier
# below medium is a candidate or keeps a rank; Neon and Hydrogen run at high as well as medium, each its own row.
# Argon-medium has a route again but no rank: the selector draws it for a small share of delegated work.
AGY_NEON = ['google/gemini-4-neon-high', 'google/gemini-4-neon-medium']
AGY_HYDROGEN = ['google/gemini-4-hydrogen-high', 'google/gemini-4-hydrogen-medium']
GEMINI_BELOW_FLOOR = ('google/gemini-3.8-flash-low', 'google/gemini-4-neon-low', 'google/gemini-4-hydrogen-low',
                      'google/gemini-4-argon-low', 'google/gemini-4-carbon-low')
GEMINI4_DROPPED = ('google/gemini-4-argon', 'google/gemini-4-argon-medium') + GEMINI_BELOW_FLOOR
HYDROGEN_ROLES = ('batch', 'mechanical', 'cheap')
AGY_GEMINI4 = AGY_NEON + AGY_HYDROGEN
AGY_CANDIDATES = AGY_FLASH + AGY_GEMINI4
CANDIDATES = {role: AGY_FLASH + (AGY_HYDROGEN if role in HYDROGEN_ROLES else AGY_NEON)
              for role in ROLES if role != 'writing'}
# Owner, 2026-11-18: "Astra 6.2 should replace Astra on the leaderboard. Sol 6.2 should/could replace Sol 6.1."
# 11-19 (general): a superseded version is history, not a fallback: shown with its own everyday record, never
# routed, and its successor earns its own n from zero.
SUPERSEDED = {'openai/gpt-6-astra': 'openai/gpt-6.2-astra', 'openai/gpt-6.1-sol': 'openai/gpt-6.2-sol'}
# Ricardo, 11-19: "I think 6.2 should inherit the scores of 6.1 in the rank until we get a larger sample size."
# Explicit successor -> predecessor pairs, never inferred from names. A successor ranks on its predecessor's
# everyday record until its own graded n reaches the predecessor's n; then on its own. Its own outcomes count the
# whole time. Same lab only: a pair across labs is refused when this module loads.
INHERITS = {'openai/gpt-6.2-sol': 'openai/gpt-6.1-sol', 'openai/gpt-6.2-astra': 'openai/gpt-6-astra'}


def check_inherits(pairs):
    for new, old in pairs.items():
        if new.split('/')[0] != old.split('/')[0]:
            raise ValueError('inheritance across families refused: {} <- {}'.format(new, old))


check_inherits(INHERITS)


def effective(m, e):
    """(n, k, inherited_from) the rank uses for m in one role's everyday evidence."""
    own = e.get(m) or {'n': 0, 'k': 0}
    old = INHERITS.get(canon(m) or m)
    if old and old.split('/')[0] == str(canon(m) or m).split('/')[0]:
        prev = e.get(old) or {'n': 0, 'k': 0}
        if own['n'] < prev['n']:
            return prev['n'], prev['k'], old
    return own['n'], own['k'], None


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
    model = canon(model) or model
    key = "|".join((source, item, model, role))
    case = f"{source}:{item}"
    if len(case) > 120:
        case = case[:103] + "-" + hashlib.sha1(case.encode()).hexdigest()[:16]
    return {"id": "auto-" + hashlib.sha1(key.encode()).hexdigest()[:12], "case": case,
            "date": date[:10], "model": model, "effort": "as run", "route": MODELS[model][0], "role": "harness",
            "task_family": f"auto-{role}", "layer": "model", "score": {"held": 4, "pass": 4, "partial": 2, "overturned": 0, "fail": 0}.get(outcome),
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
            if prev and score_verdicts.migrate(prev["outcome"], prev) == score_verdicts.migrate(r["outcome"], r):
                continue
            if prev:                              # outcome flipped: supersede, never edit
                r["id"] = r["id"] + "-" + hashlib.sha1((prev["id"] + r["outcome"]).encode()).hexdigest()[:8]
                if r["id"] in existing:
                    continue
                r["supersedes"] = prev["id"]
            new.append(r)
            latest[(r["case"], r["model"], r["pick_role"])] = r
    for row in new:
        row['model'] = canon(row['model']) or row['model']
        row['outcome'] = score_verdicts.observation(row['outcome'], row)
        score_verdicts.validate(row['outcome'])
    if write and new:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new)
        validate((LEDGER.read_text() if LEDGER.exists() else '') + text)        # the ledger's own validator, before anything is written
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(text)
    return new, stats


def wilson_high(k, n):
    return min(1.0, 1 - wilson_low(n - k, n)) if n else 1.0


def wilson_low(k, n):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + Z * Z / n
    return (p + Z * Z / (2 * n) - Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))) / d


# 11-19 Ricardo (laptop handoff): "rank by everyday work first". Everyday work is real tasks handed to workers,
# graded pass, partial or fail when they come back. The bench (reproductions with known answers, planted claims) is
# a second check on correctness and cost and never ranks: almost every model scores 100% on it.
BENCH_SOURCES = {'receipt-review'}          # planted-claim referee batches
GRADE = {'held': 1.0, 'pass': 1.0, 'partial': 0.5, 'overturned': 0.0, 'fail': 0.0}


def is_bench(r):
    return bool(r.get('bench')) or r.get('source') in BENCH_SOURCES or str(r.get('task_family', '')).startswith('bench')


def _grades_feed():
    """The grades-feed reader, or None when it cannot be loaded: the scorer then ranks on this machine's
    grades alone (RULE #1: never in its way)."""
    try:
        spec = importlib.util.spec_from_file_location('grades_feed', HERE / 'grades_feed.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as exc:
        print('grades-feed: not read ({})'.format(exc), file=sys.stderr)
        return None


FEED_SKIPPED = {}    # model ids in a grades feed that resolve to no known model: skipped, and reported


def evidence():
    """{role: {model: {n, k, days}}} from graded everyday work. k counts a partial as half."""
    return graded('everyday')


def bench_evidence():
    """The same shape from the bench, shown beside the ranking and never used for it."""
    return graded('bench')


def graded(kind):
    rows = validate(LEDGER.read_text()) if LEDGER.exists() else []
    retired = {r["supersedes"] for r in rows if r.get("supersedes")}
    ev = collections.defaultdict(lambda: collections.defaultdict(lambda: {"n": 0, "k": 0, "days": set()}))
    for r in rows:
        if r["id"] in retired or is_bench(r) != (kind == 'bench'):
            continue
        model = canon(r.get("model"))
        if not model:
            continue
        if r.get("pick_role") == "corrections":
            continue                              # reported as a rate, never ranked; see CORRECTIONS_CAVEAT
        if r.get("pick_role") and (r.get("outcome") == "ungraded" or r.get("outcome") == "harness_fail" or str(r.get("outcome", "")).startswith("void:")):
            # Returned but never graded within 24 h: counted, and kept out of the rate.
            ev[r["pick_role"]][model]["ungraded"] = ev[r["pick_role"]][model].get("ungraded", 0) + 1
            continue
        if r.get("pick_role"):
            if r.get("outcome") not in GRADE:
                continue
            role, ok = r["pick_role"], GRADE[r["outcome"]]
        elif r.get("task_family") in FIELD_ROLE and r.get("score") in (0, 1, 2, 3, 4):
            role, ok = FIELD_ROLE[r["task_family"]], (1.0 if r["score"] >= 3 else 0.5 if r["score"] == 2 else 0.0)
        else:
            continue
        e = ev[role][model]
        e["n"] += 1
        e["k"] += ok
        e["days"].add(r.get("date", "")[:10])
    # 11-22 (Ricardo: "We just combine them together."): another machine's grades-feed snapshot counts here
    # under the same rule (everyday and judge rows rank, bench rows only as bench, void and harness rows never),
    # with the per-machine split kept on each row.
    gf = _grades_feed()
    for row in (gf.snapshots() if gf else ()):
        row_kind, ok = gf.counts(row)
        if row_kind != kind:
            continue
        model = canon(row["model"])
        if not model:
            FEED_SKIPPED[row["model"]] = FEED_SKIPPED.get(row["model"], 0) + 1
            continue
        e = ev[gf.role_for(row)][model]
        e["n"] += 1
        e["k"] += ok
        e["days"].add(row["date"])
        split = e.setdefault("feed", {}).setdefault(row["machine"], {"n": 0, "k": 0.0})
        split["n"] += 1
        split["k"] += ok
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


# Executors that run on a subscription. 11-19: only these are served; OpenRouter and the Gemini API
# are pay-as-you-go, so their models stay readable for history and are never routed.
SUBSCRIPTION = ('claude', 'codex', 'agy')


def served_model(model):
    """Only subscription routes are served; metered ones (OpenRouter, Gemini API) are history-only,
    including newly observed model versions."""
    canonical = canon(model)
    return bool(canonical and MODELS[canonical][0] in SUBSCRIPTION)


def fallback_tail(order):
    """Superseded versions are not routed (general, 11-19: 6.1 was retired as a route on 11-18). Their everyday
    record stays visible as a historical row in LEADERBOARD.md, and the successor inherits none of it."""
    return [m for m in order if canon(m) not in SUPERSEDED]


def rank(role, ev, cost=None):
    """Models with MIN_N or more graded everyday tasks first, by Wilson lower bound; every other model after
    them in its seed/candidate order ("n<5"). The bench never enters: rank is called with everyday evidence.
    `cost` ({model: percent of a weekly plan per passed task}) only orders models whose everyday standing is
    exactly equal (same Wilson bound and rate); a model with no cost figure sorts after one that has it."""
    cost = cost or {}
    e = ev.get(role, {})
    def graded(m):
        return effective(m, e)[0] >= MIN_N
    def rate(m):
        n, k, _ = effective(m, e)
        return k / n if graded(m) else SEED_RATE
    def low(m):
        n, k, _ = effective(m, e)
        return wilson_low(k, n) if graded(m) else -1
    pool = list(SEED[role]) + CANDIDATES.get(role, [])
    order = [m for m in pool + sorted((m for m in e if m not in pool), key=low, reverse=True)
             if served_model(m) and m not in GEMINI4_DROPPED]
    data = sorted((m for m in order if graded(m)),
                  key=lambda m: (low(m), rate(m), -cost[m] if m in cost else -math.inf), reverse=True)
    order = data + [m for m in order if not graded(m)]
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
    return fallback_tail(order), flags

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
    FEED_SKIPPED.clear()
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
    bench = bench_evidence()
    cost = costs()
    out['bench'] = {}
    out['cost'] = {}
    out['ranking'] = 'everyday'
    out['owner_rank'] = dict(OWNER_RANK)
    for role in ROLES:
        order, _ = rank(role, ev, {m: v['per_pass'] for m, v in cost.get(role, {}).items() if v['per_pass'] is not None})
        out['roles'][role] = [MODELS[m][1] for m in order]
        # 'scored' is the n<5 rule: under MIN_N graded everyday tasks the model shows "n<5" and has no rate.
        out['evidence'][role] = {MODELS[m][1]: {'n': v['n'], 'rate': round(v['k']/v['n'], 3),
                      'low': round(wilson_low(v['k'], v['n']), 3), 'days': len(v['days']), 'scored': v['n'] >= MIN_N,
                      **({'feed': v['feed']} if v.get('feed') else {})}
                      for m, v in ev.get(role, {}).items() if v['n']}
        for m in order:
            n, k, old = effective(m, ev.get(role, {}))
            if old:
                own = ev.get(role, {}).get(m) or {'n': 0}
                row = out['evidence'][role].setdefault(MODELS[m][1], {'n': own['n'], 'rate': None, 'low': None,
                                                                         'days': 0, 'scored': False})
                row['inherited'] = {'from': MODELS[old][1], 'n': n, 'rate': round(k / n, 3)}
        for m, v in ev.get(role, {}).items():
            if v.get('ungraded'):
                out['evidence'][role].setdefault(MODELS[m][1], {'n': 0, 'rate': None, 'low': None, 'days': 0,
                                                               'scored': False})['ungraded'] = v['ungraded']
        out['cost'][role] = {MODELS[m][1]: {'n': v['n'], 'passes': v['passes'], 'pct_per_pass': v['per_pass']}
                             for m, v in cost.get(role, {}).items() if m in MODELS and v['per_pass'] is not None}
        out['bench'][role] = {MODELS[m][1]: {'n': v['n'], 'rate': round(v['k']/v['n'], 3),
                                             **({'feed': v['feed']} if v.get('feed') else {})}
                              for m, v in bench.get(role, {}).items() if v['n'] and m in MODELS}
    if FEED_SKIPPED:
        out['feed_skipped'] = dict(sorted(FEED_SKIPPED.items()))
        print('grades-feed: skipped unknown model ids: ' + ', '.join('{} ({})'.format(m, n) for m, n in out['feed_skipped'].items()),
              file=sys.stderr)
    if write:
        write_roles(out)
    return out


def job_cost_module():
    spec = importlib.util.spec_from_file_location('job_cost', HERE / 'job_cost.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def costs():
    """{role: {model: {'n', 'passes', 'pct', 'per_pass'}}}: cost per passed everyday task, display and tie-break
    only. Any missing source gives {} (shown as "-"); this never raises."""
    try:
        found = job_cost_module().per_pass(os.environ.get('RH_LAUNCH_RECEIPTS'), canon)
    except Exception:
        return {}
    out = collections.defaultdict(dict)
    for (role, model), v in found.items():
        out[role][model] = v
    return dict(out)


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
    tables = {8: [], 7: [], 6: [], 5: [], 4: []}
    if not path or not Path(path).is_file():
        return tables
    for line in Path(path).read_text().splitlines():
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if not line.startswith('| ') or len(cells) not in tables or cells[0] in ('Role', 'Model'):
            continue
        role, model = cells[:2]
        # Diagnostic calibration tables can also have six columns. Their first
        # column is Entry/a canonical model ID, not a routing role.
        if role == 'Entry' or role in MODELS or canon(role):
            continue
        safe_cell(role); safe_cell(model)
        if role not in ROLES or not canon(model):
            raise ValueError('unknown public role or model in snapshot')
        dt.date.fromisoformat(cells[-1])
        if len(cells) in (7, 8):
            if cells[2] != '-' and (not cells[2].isdigit() or int(cells[2]) < 1):
                raise ValueError('invalid routing position in snapshot')
            for value in (cells[3], cells[5]):
                if value not in ('-', 'n<5'):
                    score(float(value))
            if cells[4] != '-' and not cells[4].isdigit() and not re.fullmatch(
                    r'inherited from [A-Za-z0-9][A-Za-z0-9/_.:-]* \(n=\d+\); own n=\d+', cells[4]):
                raise ValueError('invalid everyday n in snapshot')
            if len(cells) == 8 and cells[6] != '-' and not re.fullmatch(r'\d+(?:\.\d+)?% wk', cells[6]):
                raise ValueError('invalid cost per pass in snapshot')
        elif len(cells) == 6:
            if cells[2] != '-' and (not cells[2].isdigit() or int(cells[2]) < 1):
                raise ValueError('invalid routing position in snapshot')
            for value in cells[3:5]:
                if value != '-':
                    score(float(value))
        elif len(cells) == 5:
            if cells[2] != '-' and (not cells[2].isdigit() or int(cells[2]) < 1):
                raise ValueError('invalid routing position in snapshot')
            if cells[3] != '-' and not re.fullmatch(r'\d+(?:\.\d+)?% wk', cells[3]):
                raise ValueError('invalid cost per pass in snapshot')
        elif not re.fullmatch(r'[0-4](?:, [0-4])*', cells[2]):
            raise ValueError('invalid observation scores in snapshot')
        tables[len(cells)].append('| ' + ' | '.join(cells) + ' |')
    return tables


def mini_only(observation):
    """The public table's view of a row: the grades-feed rows from another machine are taken out unless
    MODEL_PUBLIC_FEED=1 (11-22: they are graded work from another of the owner's machines; publishing their
    counts is his call). The routing order itself still counts them."""
    fed = observation.get('feed') or {}
    if not fed or os.environ.get('MODEL_PUBLIC_FEED') == '1':
        return observation, False
    n_all, rate = observation.get('n', 0), observation.get('rate') or 0
    fn = sum(int(f.get('n', 0)) for f in fed.values())
    fk = sum(float(f.get('k', 0)) for f in fed.values())
    n = max(n_all - fn, 0)
    return dict(observation, n=n, rate=round(min(max((rate * n_all - fk) / n, 0), 1), 3) if n else None), True


def feed_only(observation):
    """True when every graded row behind `observation` came from another machine's grades feed."""
    fed = sum(int(f.get('n', 0)) for f in (observation.get('feed') or {}).values())
    return fed > 0 and fed >= observation.get('n', 0)


def public_counts(pairs, historical, stamp, days):
    """Windowed observed work; aggregated routing evidence never supplies a grade."""
    import run_grades
    since = stamp - dt.timedelta(days=days)
    totals, roles = collections.defaultdict(lambda: [0, 0, 0.0]), collections.defaultdict(dict)
    dropped = collections.Counter()
    drivers = [0, 0]

    def admit(run, record, when, has_run):
        if not when or not since <= when <= stamp:
            return
        grade, ledger = (record[0], record[1]) if record else ({}, Path('.'))
        if run_grades.run_records.is_probe(run) or run_grades.run_records.is_probe(grade):
            dropped['probe'] += bool(record and record[2])
            return
        if is_bench(run) or is_bench(grade):
            dropped['bench'] += bool(record)
            return
        model = canon(run.get('model') or grade.get('model'))
        if not model:
            return
        native = MODELS[model][1]
        safe_cell(native)
        role = grade.get('role') or run.get('role') or 'batch'
        safe_cell(role)
        entry = roles[role].setdefault(native, [0, 0, 0.0])
        overall = totals[native]
        if has_run:
            entry[0] += 1
            overall[0] += 1
        driver = run.get('backend') == 'agy-driver'
        if driver:
            drivers[1] += 1
        reason = run_grades.exclusion_reason(run, grade, ledger) if record else ''
        if reason:
            dropped[reason] += 1
            return
        verdict = grade.get('grade')
        if verdict in GRADE:
            for cell in (entry, overall):
                cell[1] += 1
                cell[2] += GRADE[verdict]
            drivers[0] += int(driver)

    for run, record in pairs:
        admit(run, record, parse_ts(run.get('utc')), True)
    for record in historical:
        grade = record[0]
        admit({}, record, parse_ts(grade.get('utc') or grade.get('date')), False)
    return totals, roles, dropped, drivers


def owner_ranks(data, previous):
    """Owner taste/cost is copied, never inferred from evidence or routing positions."""
    ranks = {canon(m): str(v) for m, v in OWNER_RANK.items()}
    ranks.update({canon(m): str(v) for m, v in data.get('owner_rank', {}).items()})
    header = []
    if previous and Path(previous).is_file():
        for line in Path(previous).read_text().splitlines():
            if not line.startswith('| '):
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if 'Model' in cells:
                header = cells
                continue
            rank_col = next((i for i, c in enumerate(header) if c in ('Rank', 'Rank (Ricardo: taste + cost)')), None)
            if rank_col is not None and len(cells) == len(header):
                model = canon(cells[header.index('Model')])
                if model:
                    ranks[model] = cells[rank_col]
    for value in ranks.values():
        if not re.fullmatch(r'[#=~0-9 .–—-]+', value):
            raise ValueError('invalid owner rank')
    return ranks


def interval(cell):
    _, n, k = cell
    if not n:
        return '- (n=0)'
    return '{:.1f}% [{:.1f}%, {:.1f}%] (n={})'.format(
        100 * k / n, 100 * wilson_low(k, n), 100 * wilson_high(k, n), n)


def public(data, path, observations=(), previous=None, days=30):
    """Render observed work separately from the owner's rank and the unchanged routing snapshot."""
    import run_grades
    if type(days) is not int or days <= 0:
        raise ValueError('days must be a positive integer')
    stamp = now()
    date = dt.datetime.fromisoformat(data['updated'].replace('Z', '+00:00')).date().isoformat()
    previous = previous if previous is not None else path
    old = snapshot_rows(previous)
    ranks = owner_ranks(data, previous)
    pairs, historical = run_grades.table()
    totals, by_role, dropped, drivers = public_counts(pairs, historical, stamp, days)
    lines = ['# Model leaderboard', '',
             "Ricardo's own rank (2026-11-26): Gemini 4 Neon and Opus 5.5 tied #1.", '',
             'Everyday work over {} days: {} through {} (UTC). Runs is the recorded model total across roles, including ungraded work; n counts only pass, partial or fail (partial=half). Historical grades without run records count in n, so n can exceed Runs. Each rate shows a Wilson 95% interval. Within-role ranks use the Wilson lower bound and require n>=20; owner ranks retain taste + cost. Task mix, correlated jobs and subjective grades limit comparisons; these are descriptive intervals, not matched trials.'.format(
                 days, (stamp - dt.timedelta(days=days)).date().isoformat(), stamp.date().isoformat()), '',
             '| Model | Rank (Ricardo: taste + cost) | Runs | Overall passed (Wilson 95%) | Role | Role passed (Wilson 95%) | Within-role rank |',
             '|---|---:|---:|---|---|---|---|']
    for role, models in sorted(by_role.items()):
        ordered = sorted(models, key=lambda m: (-wilson_low(models[m][2], models[m][1]) if models[m][1] >= 20 else 1, m))
        eligible = [m for m in ordered if models[m][1] >= 20]
        lows = [wilson_low(models[m][2], models[m][1]) for m in eligible]
        for model in ordered:
            cell = models[model]
            rank = str(lows.index(wilson_low(cell[2], cell[1])) + 1) if cell[1] >= 20 else 'n<20, unranked'
            lines.append('| {} | {} | {} | {} | {} | {} | {} |'.format(
                model, ranks.get(canon(model), '-'), totals[model][0], interval(totals[model]), role, interval(cell), rank))
    why = ', '.join('{}={}'.format(reason, n) for reason, n in sorted(dropped.items()) if n) or 'none'
    lines += ['', 'Dropped {} grade rows: {}. Ungraded runs remain in Runs; probes and bench runs are omitted.'.format(sum(dropped.values()), why), '',
              'Driver-session work (most Gemini Neon use) is ungraded until driver outputs are scored; {}/{} driver outputs have a grade.'.format(*drivers), '']
    bench = []
    for role, models in sorted(data.get('bench', {}).items()):
        safe_cell(role)
        for model, row in sorted(models.items()):
            safe_cell(model)
            row, _ = mini_only(row)
            if row.get('n'):
                bench.append('{} / {} {} (n={})'.format(model, role, score(row.get('rate')), row['n']))
    lines += ['Everyday work ranks models, never synthetic. Bench (saturated): ' + ('; '.join(bench) if bench else 'no published observations') + '.', '',
              'Carbon (10-28) replaced Argon; model versions and effort tiers keep their own records.', '']
    # Preserve routing positions as routing positions, never as the owner or measured ranks.
    # Earlier scored snapshots remain in the source file; their scores are not reused as current evidence.
    routing = []
    for width in (8, 7, 6, 5):
        for line in old[width]:
            cells = [c.strip() for c in line.strip('|').split('|')]
            if cells[-1] != date:
                cost = cells[6] if width == 8 else cells[3] if width == 5 else '-'
                item = '| {} | {} | {} | {} | {} |'.format(cells[0], cells[1], cells[2], cost, cells[-1])
                if item not in routing:
                    routing.append(item)
    hidden_feed = False
    for role, order in data['roles'].items():
        safe_cell(role)
        if role not in ROLES:
            raise ValueError('unknown public role')
        # Validate aggregate inputs even though only raw joined grades enter the main table.
        for model, row in data.get('evidence', {}).get(role, {}).items():
            safe_cell(model)
            if model not in {native for _, native in MODELS.values()}:
                if feed_only(row):
                    hidden_feed = True
                    continue
                raise ValueError('unknown public model')
            score(row.get('rate'))
        for i, model in enumerate(order, 1):
            safe_cell(model)
            if model not in {native for _, native in MODELS.values()}:
                raise ValueError('unknown public model')
            value = data.get('cost', {}).get(role, {}).get(model, {}).get('pct_per_pass')
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError('invalid cost per pass')
            cost = '{:.2f}% wk'.format(value) if value is not None else '-'
            routing.append('| {} | {} | {} | {} | {} |'.format(role, model, i, cost, date))
    if routing:
        lines += ['<details>', '<summary>Routing snapshots (positions are routing preferences)</summary>', '',
                  '| Role | Model | Routing order | Cost per pass | Date |', '|---|---|---:|---:|---|', *routing, '', '</details>', '']
    if old[6]:
        lines += ['<details>', '<summary>Historical held-outcome scores (before 2026-11-19)</summary>', '',
                  '| Role | Model | Routing order | Held score | Wilson lower score | Date |',
                  '|---|---|---:|---:|---:|---|', *old[6], '', '</details>', '']
    if hidden_feed:
        lines += ['_The routing order also counts graded rows that are not published here._', '']
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
        lines += ['## Recorded observation scores', '',
                  'Historical 0–4 labels; these are not the pass rates above.', '',
                  '| Role | Model | Scores | Date |', '|---|---|---|---|']
        fresh = {(f'| {r} | {m} |', day) for r, m, day in groups}
        lines.extend(l for l in old[4] if not any(l.startswith(k) and l.rstrip().endswith(f'| {v} |') for k, v in fresh))
        for (role, model, day), values in sorted(groups.items()):
            lines.append('| {} | {} | {} | {} |'.format(role, model, ', '.join(map(str, sorted(values))), day))
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
        if len(cells) not in (5, 6, 7, 8) or cells[0] in ('Role', 'Model'):
            continue
        role, model, position, date = cells[0], cells[1], cells[2], cells[-1]
        if role == 'Entry' or role in MODELS or canon(role):
            continue
        safe_cell(role); safe_cell(model)
        if role not in ROLES:
            raise ValueError('unknown role')
        if model.startswith('claude-') or model.startswith('gpt-') or '/' in model:
            canon(model)
        dt.date.fromisoformat(date)
        dates.append(date)
        # The everyday table (7 columns 11-19, 8 with cost per pass from 11-20) is the routing; the older held-score table is history.
        snapshots[(role, len(cells), date)][model] = position
    for role in {r for r, _, _ in snapshots}:
        width = max((w for r, w, _ in snapshots if r == role), key=lambda w: (w == 5, w))
        latest = max(date for r, w, date in snapshots if r == role and w == width)
        for model, position in snapshots[(role, width, latest)].items():
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
            'roles': {r: [m for _, m in sorted(rows) if served_model(m)]
                      for r, rows in roles.items()},
            'routes': routes, 'evidence': {}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('bootstrap', 'ingest', 'recompute', 'daily', 'status', 'public'))
    parser.add_argument('--snapshot', type=Path, default=HERE.parent / 'LEADERBOARD.md')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--days', type=int, default=30, help='public work window in days (default: 30)')
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
            print(public(data, args.output or args.snapshot, observations, previous=args.snapshot, days=args.days))
        else:
            print(json.dumps(recompute(write=False), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
