"""Bug-hunt referee verdicts: one schema, refuted claims remembered, planted claims to test the referee.

Three upgrades adopted 11-08 from published skill sets, compared against our own referee step
(Cloudflare's security-audit-skill most of all):

1. NOT REPRODUCED meant two things: "the claim is wrong" and "I could not run it". It is split:
   REFUTED (with the reason) and BLOCKED (with the one fact that would settle it and how to check
   it). A BLOCKED item is never reported as a bug; it can be the plain question an email opens with.
   Every REFUTED claim is kept in the lane's REFUTED.jsonl under a fingerprint (repo, file,
   function), so a later round cannot claim it again unless the source changed or the new claim
   says how it differs.
2. One referee prompt (harness/templates/bug_referee.md) and one verdict file, verdict.json, checked
   against a strict schema. Malformed output is run again, never repaired. Each batch carries
   planted false claims the referee cannot tell apart; a referee that confirms one is rejected
   whole, and the catch rate is kept per referee in REFEREE.jsonl. (One of our referees passed 98%
   of 528 claims; this is how that shows up the same day.)
3. What was already hunted is in bug_coverage.py.

Commands:
    rh bughunt claims-check LANE CLAIMS.json         refuse claims refuted before
    rh bughunt referee-prompt LANE CLAIMS.json DIR   plant, shuffle, write DIR/claims.json + PROMPT.md
                                                     (needs the hunter's family: "hunter" in the file or --hunter-family)
    rh bughunt verdicts LANE DIR/verdict.json        validate, check the plants, record
        [--receipt FILE]                             the launcher's model receipt; found by job name under
                                                     RH_LAUNCH_RECEIPTS when not given
    rh bughunt referees LANE                         confirm rate and plant catch rate per referee

Claims file (from the hunter):
    {"target": "owner/repo", "commit": "<sha>", "hunter": {"model", "family"}, "claims": [{"id", "file", "function", "root_cause",
     "observed", "expected", optional "file_sha256", optional "differs_from": {"fingerprint", "why"}}]}
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import secrets

VERDICTS = ('CONFIRMED', 'CONFIRMED-MINOR', 'KNOWN', 'INTENDED', 'REFUTED', 'BLOCKED')
CONFIRMS = ('CONFIRMED', 'CONFIRMED-MINOR')
CLAIM_KEYS = {'id', 'file', 'function', 'root_cause', 'observed', 'expected', 'file_sha256', 'differs_from'}
VERDICT_REQUIRED = {'id', 'verdict', 'file', 'function', 'root_cause', 'effect'}
VERDICT_OPTIONAL = {'repro', 'reason', 'needs', 'check', 'file_sha256', 'maintainer', 'notes'}
TOP_REQUIRED = {'schema', 'batch', 'target', 'commit', 'referee', 'claims'}
SCHEMA = 'bug-verdicts/1'
TEMPLATE = Path(__file__).resolve().parent / 'templates' / 'bug_referee.md'
SHA = re.compile(r'^[0-9a-f]{7,40}$')
TARGET = re.compile(r'^[a-z0-9_.-]+/[a-z0-9_.-]+$')
# A referee from the hunter's own family shares its blind spots, so it does not count (11-09: a GPT-6 Codex
# hunter was refereed by GPT-6 and the verdicts were accepted). Family is compared by maker, so GPT-5 vs GPT-6
# or Opus vs Sonnet is still the same family.
MAKERS = (('openai', r'gpt|codex|openai|\bo[1-9]\b|chatgpt'), ('anthropic', r'claude|opus|sonnet|haiku|fable|anthropic'),
          ('google', r'gemini|gemma|google|palm'), ('deepseek', r'deepseek'), ('qwen', r'qwen|alibaba'),
          ('xai', r'grok|xai'), ('meta', r'llama|meta'), ('mistral', r'mistral|mixtral|codestral'),
          ('moonshot', r'kimi|moonshot'), ('zhipu', r'glm|zhipu'))


def maker(*names):
    """The model maker named by any of NAMES, else the first name, normalised."""
    text = ' '.join(str(n or '') for n in names).casefold()
    for name, pattern in MAKERS:
        if re.search(pattern, text):
            return name
    return re.sub(r'[^a-z0-9]+', '', str(names[0] if names else '').casefold())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fingerprint(target, file, function):
    """Where the claim is: repo, file, function. Wording of the root cause varies between rounds;
    the place does not, so a new claim at a refuted place has to say how it differs."""
    key = '|'.join([target.strip().casefold(), Path(file.strip()).as_posix().lstrip('./').casefold(),
                    function.strip().casefold().rstrip('()')])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def text_field(value, words=1):
    return isinstance(value, str) and len(value.split()) >= words


def validate_claims(doc):
    errors = []
    if not isinstance(doc, dict):
        return ['claims file is not a JSON object']
    if not TARGET.match(str(doc.get('target', '')).casefold()):
        errors.append('target must be owner/repo')
    if not SHA.match(str(doc.get('commit', ''))):
        errors.append('commit must be a git sha')
    claims = doc.get('claims')
    if not isinstance(claims, list) or not claims:
        return errors + ['claims must be a nonempty list']
    seen = set()
    for i, c in enumerate(claims):
        where = 'claim {}'.format(c.get('id', i) if isinstance(c, dict) else i)
        if not isinstance(c, dict):
            errors.append(where + ': not an object')
            continue
        for key in ('id', 'file', 'function'):
            if not text_field(c.get(key)):
                errors.append('{}: {} is required'.format(where, key))
        if not text_field(c.get('root_cause'), 3):
            errors.append(where + ': root_cause needs a sentence')
        extra = set(c) - CLAIM_KEYS
        if extra:
            errors.append('{}: unknown fields {}'.format(where, ', '.join(sorted(extra))))
        if c.get('id') in seen:
            errors.append(where + ': duplicate id')
        seen.add(c.get('id'))
    return errors


def validate(doc):
    """Schema errors for a referee's verdict.json; [] when it is well formed."""
    if not isinstance(doc, dict):
        return ['verdict.json is not a JSON object']
    errors = []
    missing, extra = TOP_REQUIRED - set(doc), set(doc) - TOP_REQUIRED
    if missing:
        errors.append('missing fields: ' + ', '.join(sorted(missing)))
    if extra:
        errors.append('unknown fields: ' + ', '.join(sorted(extra)))
    if doc.get('schema') != SCHEMA:
        errors.append('schema must be "{}"'.format(SCHEMA))
    if not TARGET.match(str(doc.get('target', '')).casefold()):
        errors.append('target must be owner/repo')
    if not SHA.match(str(doc.get('commit', ''))):
        errors.append('commit must be a git sha')
    referee = doc.get('referee')
    if not (isinstance(referee, dict) and text_field(referee.get('model')) and text_field(referee.get('family'))):
        errors.append('referee needs model and family')
    claims = doc.get('claims')
    if not isinstance(claims, list) or not claims:
        return errors + ['claims must be a nonempty list']
    for i, c in enumerate(claims):
        where = 'claim {}'.format(c.get('id', i) if isinstance(c, dict) else i)
        if not isinstance(c, dict):
            errors.append(where + ': not an object')
            continue
        missing, extra = VERDICT_REQUIRED - set(c), set(c) - VERDICT_REQUIRED - VERDICT_OPTIONAL
        if missing:
            errors.append('{}: missing {}'.format(where, ', '.join(sorted(missing))))
        if extra:
            errors.append('{}: unknown fields {}'.format(where, ', '.join(sorted(extra))))
        verdict = c.get('verdict')
        if verdict == 'NOT REPRODUCED':
            errors.append(where + ': NOT REPRODUCED is split: REFUTED (with reason) or BLOCKED (with needs and check)')
        elif verdict not in VERDICTS:
            errors.append('{}: verdict must be one of {}'.format(where, ', '.join(VERDICTS)))
        if verdict in CONFIRMS and not text_field(c.get('repro')):
            errors.append(where + ': a confirmed claim needs the referee\'s own repro path')
        if verdict == 'REFUTED' and not text_field(c.get('reason'), 3):
            errors.append(where + ': REFUTED needs the reason')
        if verdict == 'BLOCKED' and not (text_field(c.get('needs'), 3) and text_field(c.get('check'), 3)):
            errors.append(where + ': BLOCKED needs the one fact (needs) and how to check it (check)')
        if c.get('file_sha256') is not None and not re.fullmatch(r'[0-9a-f]{64}', str(c['file_sha256'])):
            errors.append(where + ': file_sha256 must be a sha256')
    return errors


def ledger(lane, name):
    path = Path(lane) / name
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def append(lane, name, row):
    with open(Path(lane) / name, 'a') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')


def refuted_before(lane, target, claim):
    """The earlier refutation this claim repeats, or None. Passes when the source changed
    (both carry file_sha256 and they differ) or the claim names that refutation and says why it differs."""
    fp = fingerprint(target, claim.get('file', ''), claim.get('function', ''))
    differs = claim.get('differs_from') or {}
    for row in reversed(ledger(lane, 'REFUTED.jsonl')):
        if row.get('fingerprint') != fp:
            continue
        if claim.get('file_sha256') and row.get('file_sha256') and claim['file_sha256'] != row['file_sha256']:
            continue
        if differs.get('fingerprint') == fp and text_field(differs.get('why'), 5):
            continue
        return row
    return None


def claims_check(lane, doc):
    """Failure strings for a hunter's claims file: schema errors, then REFUTED_BEFORE."""
    errors = ['CLAIMS_MALFORMED: ' + e for e in validate_claims(doc)]
    if errors:
        return errors
    out = []
    for c in doc['claims']:
        row = refuted_before(lane, doc['target'], c)
        if row:
            out.append('REFUTED_BEFORE: {} ({}:{}) was refuted on {} by {}: "{}". Drop it, or give '
                       'differs_from {{"fingerprint": "{}", "why": ...}} saying what is different'.format(
                           c['id'], c['file'], c['function'], row.get('utc', '?')[:10], row.get('referee', '?'),
                           row.get('reason', ''), row['fingerprint']))
    return out


def plants_for(claims, n, rng):
    """False claims made from the real ones, indistinguishable in form:
    - observed and expected swapped (running the code shows the claimed output is not what it does);
    - one claim's root cause placed at another claim's function (the cited code doesn't say it)."""
    out = []
    usable = [c for c in claims if c.get('observed') and c.get('expected') and c['observed'] != c['expected']]
    rng.shuffle(usable)
    for c in usable:
        out.append(dict(c, observed=c['expected'], expected=c['observed']))
    if len(claims) >= 2:
        a, b = rng.sample(claims, 2)
        if (a['file'], a['function']) != (b['file'], b['function']):
            out.append(dict(b, file=a['file'], function=a['function']))
    rng.shuffle(out)
    for p in out:
        p.pop('file_sha256', None)
        p.pop('differs_from', None)
    return out[:n]


def referee_prompt(lane, doc, workdir, plants=(), n_plants=1, rng=None, extra='', hunter_family=None):
    """Write WORKDIR/claims.json (real and planted, shuffled, renumbered) and WORKDIR/PROMPT.md.
    The key (which ids are planted) and the hunter's family go to the lane's PLANTS.jsonl, never to WORKDIR."""
    rng = rng or random.Random(secrets.randbits(64))
    hunter = doc.get('hunter') if isinstance(doc.get('hunter'), dict) else {}
    family = hunter_family or hunter.get('family')
    if not text_field(family):
        raise ValueError('HUNTER_UNDECLARED: say which model family found these claims ("hunter": {"model", '
                         '"family"} in the claims file, or --hunter-family), so a same-family referee is refused')
    refused = claims_check(lane, doc)
    if refused:
        raise ValueError('; '.join(refused))
    real = [dict(c) for c in doc['claims']]
    planted = [dict(p) for p in plants] + plants_for(real, n_plants, rng)
    if not planted:
        raise ValueError('PLANT_IMPOSSIBLE: no false claim can be made from these claims; give observed and '
                         'expected for each, or pass --plants FILE with false claims written for this target')
    batch = secrets.token_hex(6)
    mixed = [('real', c) for c in real] + [('planted', p) for p in planted]
    rng.shuffle(mixed)
    out, key = [], []
    for i, (kind, c) in enumerate(mixed, 1):
        ident = 'C{:02d}'.format(i)
        key.append(dict(id=ident, planted=kind == 'planted', original=c.get('id')))
        c = {k: v for k, v in c.items() if k in CLAIM_KEYS - {'differs_from'}}
        out.append(dict(c, id=ident))
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / 'claims.json').write_text(json.dumps(dict(target=doc['target'], commit=doc['commit'], claims=out), indent=2))
    prompt = TEMPLATE.read_text().format(target=doc['target'], commit=doc['commit'], batch=batch,
                                         workdir=workdir, claims=workdir / 'claims.json', schema=SCHEMA,
                                         verdicts=', '.join(VERDICTS), extra=extra)
    (workdir / 'PROMPT.md').write_text(prompt)
    append(lane, 'PLANTS.jsonl', dict(batch=batch, utc=now(), target=doc['target'], commit=doc['commit'],
                                      workdir=str(workdir), key=key, hunter_family=family,
                                      hunter_model=hunter.get('model'), hunter_maker=maker(family, hunter.get('model'))))
    return batch, len(real), len(planted)


def launch_receipt(path, receipt=None):
    """(receipt dict, its path) for the referee run that wrote PATH, or (None, None).

    A referee's own "referee" field is a self-report: on 11-09 Gemini 4 Argon run through Codex wrote
    {"model": "gpt-5.4", "family": "openai"}, repeating Codex's base prompt. The launcher's selection
    receipt (launch.sh writes JOB.log.selection.json) names the model it actually ran, so the family
    check uses that. Found by the verdict's directory name under RH_LAUNCH_RECEIPTS when not given."""
    if receipt:
        candidates = [Path(receipt).expanduser()]
    elif os.environ.get('RH_LAUNCH_RECEIPTS'):
        job = Path(path).resolve().parent.name
        candidates = [Path(os.environ['RH_LAUNCH_RECEIPTS']).expanduser() / (job + '.log.selection.json')]
    else:
        return None, None
    for c in candidates:
        try:
            doc = json.loads(c.read_text())
        except (OSError, ValueError):
            if receipt:
                raise ValueError('VERDICT_RECEIPT_UNREADABLE: ' + str(c))
            continue
        if isinstance(doc, dict) and text_field(doc.get('canonical') or doc.get('model')):
            return doc, c
        if receipt:
            raise ValueError('VERDICT_RECEIPT_UNREADABLE: no model in ' + str(c))
    return None, None


def record(lane, path, receipt=None):
    """Validate a verdict.json, check its plants, and record it. Returns (ok, messages)."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return False, ['VERDICT_MALFORMED: unreadable JSON ({}); run the referee again, never repair it'.format(
            type(exc).__name__)]
    errors = validate(doc)
    if errors:
        return False, ['VERDICT_MALFORMED: ' + e for e in errors] + ['run the referee again; never repair its output']
    keys = [r for r in ledger(lane, 'PLANTS.jsonl') if r.get('batch') == doc['batch']]
    if not keys:
        return False, ['VERDICT_UNPLANTED: batch {} has no planted claims on record; referee prompts come from '
                       'rh bughunt referee-prompt'.format(doc['batch'])]
    key = {k['id']: k for k in keys[-1]['key']}
    by_id = {c['id']: c for c in doc['claims']}
    msgs = []
    missing = sorted(set(key) - set(by_id))
    if missing:
        msgs.append('VERDICT_INCOMPLETE: no verdict for {}'.format(', '.join(missing)))
    planted = [i for i, k in key.items() if k['planted']]
    fooled = [i for i in planted if (by_id.get(i) or {}).get('verdict') in CONFIRMS]
    caught = [i for i in planted if (by_id.get(i) or {}).get('verdict') in ('REFUTED', 'BLOCKED')]
    counts = {v: sum(c['verdict'] == v for c in doc['claims'] if not key.get(c['id'], {}).get('planted')) for v in VERDICTS}
    referee = '{} ({})'.format(doc['referee']['model'], doc['referee']['family'])
    said = maker(doc['referee']['family'], doc['referee']['model'])
    notes = []   # where the referee's family came from; printed after the verdict's own messages
    try:
        rec, rec_path = launch_receipt(path, receipt)
    except ValueError as exc:
        return False, [str(exc)]
    if rec:
        ran = rec.get('canonical') or rec.get('model')
        referee_maker = maker(ran)
        if referee_maker != said:
            notes.append('REFEREE_SELF_REPORT_WRONG: verdict.json says {}; the launch receipt {} says {}; the '
                        'receipt is used'.format(referee, rec_path.name, ran))
        referee = '{} ({})'.format(ran, referee_maker)
    else:
        referee_maker = said
    hunter_maker = keys[-1].get('hunter_maker')
    if hunter_maker and not rec:
        notes.append('REFEREE_FAMILY_SELF_REPORTED: no launch receipt, so the family check used verdict.json\'s own '
                    '"referee" field (pass --receipt JOB.log.selection.json)')
    same = bool(hunter_maker) and referee_maker == hunter_maker
    if same:
        msgs.append('REFEREE_SAME_FAMILY: the hunter was {} and the referee is {}; nothing in this file counts. '
                    'Run a referee from another family'.format(keys[-1].get('hunter_family'), referee))
    elif not hunter_maker:
        msgs.append('REFEREE_FAMILY_UNCHECKED: batch {} predates the hunter-family record'.format(doc['batch']))
    ok = not missing and not fooled and not same
    append(lane, 'REFEREE.jsonl', dict(utc=now(), batch=doc['batch'], target=doc['target'], referee=referee,
                                       file=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                       planted=len(planted), caught=len(caught), fooled=len(fooled), counts=counts,
                                       same_family=same, family_source='receipt' if rec else 'self-report',
                                       accepted=ok))
    if fooled:
        msgs.append('REFEREE_FOOLED: the referee confirmed planted false claim(s) {}; nothing in this file counts. '
                    'Run a different referee'.format(', '.join(fooled)))
    if not ok:
        return False, msgs + notes
    for c in doc['claims']:
        if key.get(c['id'], {}).get('planted'):
            continue
        row = dict(utc=now(), batch=doc['batch'], target=doc['target'], commit=doc['commit'], referee=referee,
                   fingerprint=fingerprint(doc['target'], c['file'], c['function']), file=c['file'],
                   function=c['function'], root_cause=c['root_cause'], file_sha256=c.get('file_sha256'))
        if c['verdict'] == 'REFUTED':
            append(lane, 'REFUTED.jsonl', dict(row, reason=c['reason']))
        elif c['verdict'] == 'BLOCKED':
            append(lane, 'BLOCKED.jsonl', dict(row, needs=c['needs'], check=c['check']))
    msgs += notes
    msgs.append('recorded: {} real claims ({}), {} of {} planted caught'.format(
        sum(counts.values()), ', '.join('{} {}'.format(n, v) for v, n in counts.items() if n), len(caught), len(planted)))
    return True, msgs


def accepted(path, lane=None):
    """True when PATH (a verdict.json) is valid and was recorded as accepted, unchanged since."""
    path = Path(path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if validate(json.loads(path.read_text())):
            return False
    except (OSError, ValueError):
        return False
    lanes = [Path(lane)] if lane else []
    return any(r.get('sha256') == digest and r.get('accepted') for l in lanes for r in ledger(l, 'REFEREE.jsonl'))


def confirmed(path):
    """The confirmed claims in an accepted verdict.json."""
    return [c for c in json.loads(Path(path).read_text())['claims'] if c['verdict'] in CONFIRMS]


def referees(lane, min_claims=20, max_confirm=0.9):
    """Per referee: claims judged, confirm rate, plants caught. A warning line for a referee that
    confirms nearly everything or was fooled by a plant."""
    stats = {}
    for r in ledger(lane, 'REFEREE.jsonl'):
        s = stats.setdefault(r['referee'], dict(claims=0, confirmed=0, planted=0, caught=0, fooled=0, batches=0))
        counts = r.get('counts') or {}
        s['batches'] += 1
        s['claims'] += sum(counts.values())
        s['confirmed'] += sum(counts.get(v, 0) for v in CONFIRMS)
        for k in ('planted', 'caught', 'fooled'):
            s[k] += r.get(k, 0)
    lines = []
    for name, s in sorted(stats.items()):
        rate = s['confirmed'] / s['claims'] if s['claims'] else 0
        flag = ''
        if s['fooled']:
            flag = '  WARN: fooled by {} planted claim(s)'.format(s['fooled'])
        elif s['claims'] >= min_claims and rate > max_confirm:
            flag = '  WARN: confirms {:.0%} of what it sees'.format(rate)
        lines.append('{}: {} batches, {} claims, {:.0%} confirmed, plants caught {}/{}{}'.format(
            name, s['batches'], s['claims'], rate, s['caught'], s['planted'], flag))
    return lines
