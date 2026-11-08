"""Bug-hunt lane rules, as checks that refuse (docs/outreach.md, "Bug-hunt lane").

A lane that hunts bugs in other people's research code and writes to them about it has failure
modes prose never stopped: a report on a repository nobody has touched in years, three emails to
one person in a day, a second email to an address that already bounced, a result sent to a
demanding reader on one re-check, a message that forgets the one question we want answered.
Each is a lint finding here, with a code, read by `rh outreach lint` for every email draft.

    rh bughunt target-check LANE OWNER/REPO     read GitHub, store PASS/FAIL with the numbers
    rh bughunt targets LANE                     the stored verdicts, newest first

Target check (GitHub REST API; GH_TOKEN or GITHUB_TOKEN if set, else `gh auth token`, else
anonymous): archived, last commit on the default branch, last release or tag, commits in the last
365 days, last issue or pull-request activity, and an "unmaintained" notice in the README. PASS
needs: not archived, no such notice, and a commit or release within `target_max_age_days`
(OUTREACH.toml, default 365). A paper alone never passes. A data deposit (Zenodo, Mendeley Data,
figshare, OSF, Dryad) is not maintained code and fails. Verdicts go to the lane's TARGETS.jsonl.
"""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request

import contacts_ledger

UTC = dt.timezone.utc
API = 'https://api.github.com/'
GITHUB = re.compile(r'^(?:https?://(?:www\.)?github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)'
                    r'(?:\.git)?(?:/.*)?$')
DEPOSIT = re.compile(r'^https?://(?:www\.)?(?:zenodo\.org|data\.mendeley\.com|figshare\.com|'
                     r'[\w.-]*\.figshare\.com|osf\.io|datadryad\.org)/', re.I)
UNMAINTAINED = re.compile(
    r'\b(?:unmaintained|no longer (?:maintained|supported|under (?:active )?development)|'
    r'not (?:actively )?maintained|this (?:repo|repository|project|package|code) is '
    r'(?:deprecated|archived|abandoned))\b', re.I)
MERGE_MARK = '<<<MERGED DRAFT: edit these into one email, then delete this line>>>'
PASSING = re.compile(r'(?<!NOT )\b(?:CONFIRMED(?:-MINOR)?|PASS(?:ED)?|REPRODUCED)\b')
VERDICT_FILES = ('VERDICT.md', 'VERDICTS.md', 'RECHECK.csv', 'verdict.json')


def defaults():
    return dict(target_max_age_days=365, target_check_valid_days=7, target_required_kinds=[],
                emails_per_contact_per_day=0, extra_rechecks=2, required_questions=[],
                required_question_names=[], required_questions_kinds=[])


def check_settings(cfg):
    for key, default in defaults().items():
        cfg.setdefault(key, default)
        value = cfg[key]
        if type(default) is int and (type(value) is not int or value < 0):
            raise ValueError('OUTREACH ' + key + ' must be a whole number, 0 or more')
        if type(default) is list and (type(value) is not list):
            raise ValueError('OUTREACH ' + key + ' must be a list')
    sets = cfg['required_questions']
    if any(type(s) is not list or not s or any(type(w) is not str or not w.strip() for w in s)
           for s in sets):
        raise ValueError('OUTREACH required_questions must be a list of keyword lists')
    names = cfg['required_question_names']
    if names and len(names) != len(sets):
        raise ValueError('OUTREACH required_question_names needs one name per required_questions entry')
    cfg['required_question_names'] = names or ['question {}'.format(i + 1) for i in range(len(sets))]
    return cfg


def normalise(target):
    """'owner/repo' for a GitHub target, else the URL as given."""
    target = target.strip()
    if DEPOSIT.match(target):
        return target
    m = GITHUB.match(target)
    if m and (target.count('/') == 1 or 'github.com' in target):
        return '{}/{}'.format(m[1], m[2]).casefold()
    return target


# ---- reading GitHub -----------------------------------------------------------------------

def token():
    for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
        if os.environ.get(name):
            return os.environ[name]
    gh = os.environ.get('RH_GH') or shutil.which('gh')
    if gh:
        try:
            out = subprocess.run([gh, 'auth', 'token'], capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def github(path, _token=[]):
    """GET a GitHub API path; JSON, or None for a 404/409 (no such thing, empty repository)."""
    if not _token:
        _token.append(token())
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'research-harness bughunt'}
    if _token[0]:
        headers['Authorization'] = 'Bearer ' + _token[0]
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers),
                                    timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        if error.code in (404, 409):
            return None
        raise


def stamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def target_check(target, max_age_days=365, get=None, clock=None):
    """The verdict row for one target. Network only through `get` (default: github)."""
    get = get or github
    clock = clock or dt.datetime.now(UTC)
    target = normalise(target)
    row = dict(target=target, utc=clock.isoformat(), max_age_days=max_age_days)
    if DEPOSIT.match(target):
        return dict(row, verdict='FAIL', reasons=['a data deposit, not maintained code'])
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+', target):
        return dict(row, verdict='FAIL', reasons=['only GitHub repositories can be checked'])
    repo = get('repos/' + target)
    if repo is None:
        return dict(row, verdict='FAIL', reasons=['repository not found'])
    branch = repo.get('default_branch') or 'main'
    commits = get('repos/{}/commits?sha={}&per_page=1'.format(target, branch)) or []
    last_commit = stamp(commits[0]['commit']['committer']['date']) if commits else None
    releases = get('repos/{}/releases?per_page=1'.format(target)) or []
    last_release = stamp(releases[0].get('published_at')) if releases else None
    if not last_release:
        tags = get('repos/{}/tags?per_page=1'.format(target)) or []
        if tags:
            tagged = get('repos/{}/commits/{}'.format(target, tags[0]['commit']['sha'])) or {}
            last_release = stamp(((tagged.get('commit') or {}).get('committer') or {}).get('date'))
    since = (clock - dt.timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%SZ')
    year = get('repos/{}/commits?sha={}&since={}&per_page=100'.format(target, branch, since)) or []
    issues = get('repos/{}/issues?state=all&sort=updated&direction=desc&per_page=1'.format(target)) or []
    last_issue = stamp(issues[0].get('updated_at')) if issues else None
    readme = get('repos/{}/readme'.format(target)) or {}
    try:
        text = base64.b64decode(readme.get('content', '')).decode('utf-8', errors='replace')
    except (ValueError, TypeError):
        text = ''
    notice = UNMAINTAINED.search(text)
    dated = [t for t in (last_commit, last_release) if t]
    newest = max(dated) if dated else None
    age = (clock - newest).days if newest else None
    reasons = []
    if repo.get('archived'):
        reasons.append('archived')
    if notice:
        reasons.append('README says "{}"'.format(notice.group()))
    if age is None:
        reasons.append('no commit or release found')
    elif age > max_age_days:
        reasons.append('last commit or release {} days ago (limit {})'.format(age, max_age_days))
    numbers = dict(archived=bool(repo.get('archived')),
                   last_commit=last_commit.date().isoformat() if last_commit else None,
                   last_release=last_release.date().isoformat() if last_release else None,
                   commits_last_365_days=len(year) if len(year) < 100 else '100+',
                   last_issue_or_pr=last_issue.date().isoformat() if last_issue else None,
                   age_days=age)
    return dict(row, verdict='FAIL' if reasons else 'PASS', reasons=reasons, numbers=numbers)


def verdicts(lane, rh):
    return rh.rows(lane / 'TARGETS.jsonl') if (lane / 'TARGETS.jsonl').exists() else []


def latest_verdict(lane, rh, target):
    rows = [r for r in verdicts(lane, rh) if r.get('target') == normalise(target)]
    return max(rows, key=lambda r: r['utc']) if rows else None


# ---- the lint findings --------------------------------------------------------------------

def sent_at(row):
    for key in ('sent', 'gate_attempt'):
        if (row.get(key) or {}).get('utc'):
            return stamp(row[key]['utc'])
    return None


def passing_verdict(directory):
    """The verdict file in DIRECTORY that records at least one confirmed result, or None."""
    for name in VERDICT_FILES:
        path = Path(directory) / name
        try:
            if path.is_file() and PASSING.search(path.read_text(errors='replace')):
                return path
        except OSError:
            continue
    return None


def asks(text, keywords):
    """A question in TEXT (a sentence ending in '?') that carries one of KEYWORDS."""
    for sentence in re.findall(r'[^.!?\n]*\?', text):
        low = sentence.casefold()
        if any(re.search(r'(?<!\w)' + re.escape(k.casefold()) + r'(?!\w)', low) for k in keywords):
            return True
    return False


def findings(row, text, cfg, lane, rh, everyone, clock):
    """(failures, warnings) for an email draft. Codes lead each message."""
    failures, warnings = [], []
    root = lane.parent.parent
    kind = row.get('kind')
    if MERGE_MARK in text:
        failures.append('MERGE_UNEDITED: a batched draft still has its merge marker; make it one '
                        'email and delete the marker line')
    # 1. Target recency and activity.
    targets = row.get('targets', [])
    if kind in cfg['target_required_kinds'] and not targets:
        failures.append('TARGET_MISSING: a {} email names the code it is about with --target '
                        'OWNER/REPO'.format(kind))
    for target in targets:
        verdict = latest_verdict(lane, rh, target)
        problem = None
        if not verdict:
            problem = 'TARGET_UNCHECKED: {} has no target-check; run rh bughunt target-check {} {}'.format(
                target, lane.name, target)
        elif verdict['verdict'] != 'PASS':
            problem = 'TARGET_FAILED: {} failed its check on {}: {}'.format(
                target, verdict['utc'][:10], '; '.join(verdict.get('reasons', [])))
        elif clock - stamp(verdict['utc']) > dt.timedelta(days=cfg['target_check_valid_days']):
            problem = 'TARGET_STALE: {} last passed on {}, more than {} days ago; check it again'.format(
                target, verdict['utc'][:10], cfg['target_check_valid_days'])
        if problem and row.get('target_override'):
            warnings.append(problem + ' (overridden: {})'.format(row['target_override']))
        elif problem:
            failures.append(problem)
    # 2. One email per person per day, batched.
    limit = cfg['emails_per_contact_per_day']
    same = [o for o in everyone if o.get('channel') == 'email' and o.get('to_key') == row.get('to_key')
            and (o['lane'], o['id']) != (row['lane'], row['id'])]
    recent = [o for o in same if sent_at(o) and clock - sent_at(o) < dt.timedelta(hours=24)]
    if limit and len(recent) >= limit:
        failures.append('DAILY_LIMIT: {} email(s) to this contact in the last 24 h ({}); the next '
                        'one may go from {}'.format(len(recent), ', '.join(o['id'] for o in recent),
                                                    (min(sent_at(o) for o in recent) +
                                                     dt.timedelta(hours=24)).strftime('%Y-%m-%d %H:%MZ')))
    waiting = [o for o in same if o.get('status') in ('drafted', 'linted', 'approved')]
    if limit and waiting:
        warnings.append('{} other unsent email(s) to this contact ({}); merge them with rh outreach '
                        'batch {} {!r}'.format(len(waiting), ', '.join(o['id'] for o in waiting),
                                               lane.name, row.get('to_key')))
    # 3. The address. 4. Scrutiny. 5. Required questions: these read the contact.
    try:
        contact = contacts_ledger.merged(root, row['to_key'])
    except (OSError, ValueError, KeyError) as error:
        warnings.append('contact checks skipped: {}'.format(error))
        contact = None
    if contact is not None:
        book = contact.get('addresses', [])
        if book and not contacts_ledger.live_addresses(contact):
            failures.append('ADDRESS_DEAD: every address on record for this contact bounced; run '
                            'rh outreach contact find {!r}'.format(contact['name']))
        elif contact.get('needs_find'):
            warnings.append('an address bounced; a find is queued for this contact')
        if contact.get('scrutiny') == 'extra':
            good = {str(Path(d).resolve()) for d in row.get('rechecks', []) if passing_verdict(d)}
            if len(good) < cfg['extra_rechecks']:
                failures.append('SECOND_RECHECK_MISSING: an extra-scrutiny contact needs {} '
                                'independent re-checks with a confirmed verdict (--recheck DIR); '
                                'found {}'.format(cfg['extra_rechecks'], len(good)))
            review = row.get('text_review') or {}
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if review.get('verdict') != 'pass' or review.get('sha256') != digest:
                failures.append('TEXT_REVIEW_MISSING: an extra-scrutiny contact needs a passing '
                                'review of this exact text (rh outreach review)')
    if kind in cfg['required_questions_kinds']:
        answered = (contact or {}).get('answered', {})
        for name, keywords in zip(cfg['required_question_names'], cfg['required_questions']):
            if asks(text, keywords):
                continue
            if name in answered:
                warnings.append('{!r} not asked: already answered ({})'.format(name, answered[name]))
            else:
                failures.append('QUESTION_MISSING: a {} email asks {!r}'.format(kind, name))
    return failures, warnings


# ---- CLI ----------------------------------------------------------------------------------

def arguments(sub):
    parser = sub.add_parser('bughunt', help='bug-hunt lane: target recency and activity checks')
    actions = parser.add_subparsers(dest='action', required=True)
    p = actions.add_parser('target-check', help='read GitHub and store a PASS/FAIL verdict')
    p.add_argument('lane')
    p.add_argument('target', help='OWNER/REPO or its GitHub URL')
    p.add_argument('--json', action='store_true')
    p = actions.add_parser('targets', help='stored verdicts, newest first')
    p.add_argument('lane')
    p.add_argument('--json', action='store_true')


def main(root, args, rh, get=None):
    import outreach
    root = Path(root).expanduser().resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.lane):
        raise ValueError('invalid lane name')
    lane = root / 'lanes' / args.lane
    if not lane.is_dir():
        raise ValueError('lane directory missing')
    cfg = outreach.settings(lane, rh)
    if args.action == 'target-check':
        row = target_check(args.target, cfg['target_max_age_days'], get)
        with rh.locked(lane):
            rh.append(lane / 'TARGETS.jsonl', row)
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            print('{} {}{}'.format(row['verdict'], row['target'],
                                   (': ' + '; '.join(row['reasons'])) if row['reasons'] else ''))
            for key, value in (row.get('numbers') or {}).items():
                print('  {}: {}'.format(key, value))
        return 0 if row['verdict'] == 'PASS' else 1
    rows = sorted(verdicts(lane, rh), key=lambda r: r['utc'], reverse=True)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print('{} {} {} {}'.format(r['utc'][:16], r['verdict'], r['target'], '; '.join(r.get('reasons', []))))
    return 0
