"""What was already hunted in a repository, so the next round covers new ground.

Cloudflare's security-audit-skill reports that one run found about half of what repeated runs found
in total, and that a repository was not done until a gap-fill pass stopped finding things. Ours
counted a repository as done after one pass. So each hunt round records its units (a module or file,
times a bug class) as covered, candidate (it found something) or deferred (not reached), in the
lane's COVERAGE.jsonl:

    {"target": "owner/repo", "commit": "<sha>", "round": "r2",
     "units": [{"unit": "src/fit.py", "bug_class": "off-by-one", "status": "covered"}, ...]}

`rh bughunt coverage LANE record FILE` refuses a round that covers nothing new at that commit
(COVERAGE_REPEAT); `rh bughunt coverage LANE show TARGET` lists what is covered, what is deferred
and whether the target is done: at least two rounds, the last of which found no new candidate.
"""
import datetime as dt
import json
from pathlib import Path
import re

STATUSES = ('covered', 'candidate', 'deferred')
SHA = re.compile(r'^[0-9a-f]{7,40}$')


def norm(value):
    return ' '.join(str(value).strip().casefold().split())


def rows(lane):
    path = Path(lane) / 'COVERAGE.jsonl'
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return ['coverage file is not a JSON object']
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+', str(doc.get('target', '')).casefold()):
        errors.append('target must be owner/repo')
    if not SHA.match(str(doc.get('commit', ''))):
        errors.append('commit must be a git sha')
    if not str(doc.get('round', '')).strip():
        errors.append('round is required')
    units = doc.get('units')
    if not isinstance(units, list) or not units:
        return errors + ['units must be a nonempty list']
    for i, u in enumerate(units):
        if not (isinstance(u, dict) and str(u.get('unit', '')).strip() and str(u.get('bug_class', '')).strip()):
            errors.append('unit {}: needs unit and bug_class'.format(i))
        elif u.get('status') not in STATUSES:
            errors.append('unit {}: status must be one of {}'.format(i, ', '.join(STATUSES)))
    return errors


def cells(history, target, commit=None, statuses=('covered', 'candidate')):
    return {(norm(u['unit']), norm(u['bug_class'])) for r in history
            if norm(r['target']) == norm(target) and (commit is None or r['commit'] == commit)
            for u in r['units'] if u['status'] in statuses}


def record(lane, doc):
    """(ok, messages). A round must cover at least one unit not covered before at that commit."""
    errors = validate(doc)
    if errors:
        return False, ['COVERAGE_MALFORMED: ' + e for e in errors]
    history = rows(lane)
    if any(norm(r['target']) == norm(doc['target']) and r['round'] == doc['round'] for r in history):
        return False, ['COVERAGE_MALFORMED: round {} is already recorded for {}'.format(doc['round'], doc['target'])]
    before = cells(history, doc['target'], doc['commit'])
    now = cells([doc], doc['target'], doc['commit'])
    new = now - before
    if before and not new:
        return False, ['COVERAGE_REPEAT: round {} covers only units already covered at {}; hunt the deferred '
                       'or never-listed units (rh bughunt coverage show)'.format(doc['round'], doc['commit'][:10])]
    found = cells([doc], doc['target'], doc['commit'], ('candidate',))
    row = dict(doc, utc=dt.datetime.now(dt.timezone.utc).isoformat(), new_units=len(new),
               new_candidates=len(found - cells(history, doc['target'], doc['commit'], ('candidate',))))
    with open(Path(lane) / 'COVERAGE.jsonl', 'a') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')
    return True, ['recorded round {}: {} new units, {} new candidates'.format(
        doc['round'], row['new_units'], row['new_candidates'])]


def status(lane, target):
    history = [r for r in rows(lane) if norm(r['target']) == norm(target)]
    if not history:
        return dict(rounds=0, done=False, covered=[], deferred=[], commit=None)
    commit = history[-1]['commit']
    at = [r for r in history if r['commit'] == commit]
    covered = cells(at, target, commit)
    deferred = cells(at, target, commit, ('deferred',)) - covered
    done = len(at) >= 2 and at[-1].get('new_candidates', 1) == 0 and not deferred
    return dict(rounds=len(at), done=done, covered=sorted(covered), deferred=sorted(deferred), commit=commit)
