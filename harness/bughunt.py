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
import reciprocate
import bug_coverage
import bug_verdicts
import speedup

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
# Open work on speed in their repository: Ricardo 11-08, a lab already optimizing its own code is
# asked first, so we do not duplicate their person's work.
PERF = re.compile(r'\b(?:speed|fast(?:er)?|perf(?:ormance)?|optimi[sz]\w*|profil\w*|accelerat\w*|'
                  r'vectori[sz]\w*|parallel\w*|numba|cython|gpu|benchmark\w*)\b', re.I)


def kinds_of(row):
    """Every kind an email carries. One email can hold refereed bugs AND a verified speedup
    (11-08, a batched email to one person); stored 'code' is the pre-split name for code-bug."""
    found = row.get('kinds') or ([row['kind']] if row.get('kind') else [])
    return ['code-bug' if k == 'code' else k for k in found]


def kind_in(kind, kinds):
    """KIND is listed, or KINDS says 'code' (both code kinds; the name before 11-08)."""
    return bool(kind) and (kind in kinds or (kind.startswith('code') and 'code' in kinds))


def defaults():
    return dict(target_max_age_days=365, target_check_valid_days=7, target_required_kinds=[],
                emails_per_contact_per_day=0, extra_rechecks=2, required_questions=[],
                required_question_names=[], required_questions_kinds=[])


def usage_defaults():
    return dict(usage_min_outside_accounts=3, usage_min_stars=25, usage_min_downloads_month=100,
                usage_min_conda_downloads=1000, usage_window_days=1095)


def downloads(packages, fetch_json):
    """{'pypi:name': last-month downloads, ...} for the packages named; None where unreadable."""
    out = {}
    for spec in packages:
        index, _, name = spec.partition(':')
        try:
            if index == 'pypi':
                out[spec] = int(fetch_json('https://pypistats.org/api/packages/{}/recent'.format(name))['data']['last_month'])
            elif index == 'cran':
                out[spec] = int(fetch_json('https://cranlogs.r-pkg.org/downloads/total/last-month/' + name)[0]['downloads'])
            elif index in ('bioconda', 'conda-forge'):
                files = fetch_json('https://api.anaconda.org/package/{}/{}'.format(index, name)).get('files', [])
                out[spec] = sum(int(f.get('ndownloads', 0)) for f in files)
            else:
                out[spec] = None
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            out[spec] = None
    return out


def recent(item, since):
    """Created on or after SINCE (an item with no date counts)."""
    try:
        return dt.datetime.fromisoformat(item['created_at'].replace('Z', '+00:00')) >= since
    except (KeyError, AttributeError, TypeError, ValueError):
        return True


def usage(target, repo, get, packages=(), fetch_json=None, cfg=None, clock=None):
    """Does anyone outside the project use it? 11-08, the owner: "nobody cares about bugs in software
    that's really old and nobody uses." Recent commits are not users, and neither are old forks: only
    issues, pull requests and forks from the last usage_window_days count (a fork from years ago is
    not someone using it now; one project had 7 such accounts and an author saying nobody used it)."""
    cfg = dict(usage_defaults(), **(cfg or {}))
    since = (clock or dt.datetime.now(UTC)) - dt.timedelta(days=cfg['usage_window_days'])
    owner = target.split('/')[0]
    contributors = {c.get('login', '').casefold() for c in (get('repos/{}/contributors?per_page=100'.format(target)) or [])}
    insiders = contributors | {owner.casefold()}
    issues = get('repos/{}/issues?state=all&per_page=100'.format(target)) or []
    forks = get('repos/{}/forks?per_page=100'.format(target)) or []
    accounts = [(i.get('user', {}).get('login', '').casefold(), recent(i, since)) for i in issues] + \
               [(f.get('owner', {}).get('login', '').casefold(), recent(f, since)) for f in forks]
    accounts = [(a, new) for a, new in accounts if a and a not in insiders and not a.endswith('[bot]')]
    outside = {a for a, new in accounts if new}
    older = {a for a, _ in accounts} - outside
    stars = int(repo.get('stargazers_count') or 0)
    counts = downloads(packages, fetch_json or json_get) if packages else {}
    signals = []
    if len(outside) >= cfg['usage_min_outside_accounts']:
        signals.append('{} outside accounts opened issues or PRs or forked it in the last {} days'.format(
            len(outside), cfg['usage_window_days']))
    if stars >= cfg['usage_min_stars']:
        signals.append('{} stars'.format(stars))
    for spec, n in counts.items():
        floor = cfg['usage_min_conda_downloads'] if spec.split(':')[0] in ('bioconda', 'conda-forge') \
            else cfg['usage_min_downloads_month']
        if n is not None and n >= floor:
            signals.append('{} downloads ({})'.format(n, spec))
    return dict(verdict='PASS' if signals else 'FAIL', signals=signals, outside_accounts=len(outside),
                outside_accounts_older=len(older), stars=stars, forks=int(repo.get('forks_count') or 0), downloads=counts)


def json_get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'research-harness bughunt', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def check_settings(cfg):
    for key, default in dict(defaults(), **speedup.defaults(), **reciprocate.defaults(), **usage_defaults()).items():
        cfg.setdefault(key, default)
        value = cfg[key]
        if type(default) is int and (type(value) is not int or value < 0):
            raise ValueError('OUTREACH ' + key + ' must be a whole number, 0 or more')
        if type(default) is float and (type(value) not in (int, float) or value < 0):
            raise ValueError('OUTREACH ' + key + ' must be a number, 0 or more')
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


def target_check(target, max_age_days=365, get=None, clock=None, packages=(), fetch_json=None, usage_cfg=None):
    """The verdict row for one target. Network only through `get` (default: github)."""
    get = get or github
    clock = clock or dt.datetime.now(UTC)
    target = normalise(target)
    row = dict(target=target, utc=clock.isoformat(), max_age_days=max_age_days)
    unknown = dict(verdict='FAIL', signals=[], reason='not checked')
    if DEPOSIT.match(target):
        return dict(row, verdict='FAIL', reasons=['a data deposit, not maintained code'], usage=unknown)
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+', target):
        return dict(row, verdict='FAIL', reasons=['only GitHub repositories can be checked'], usage=unknown)
    repo = get('repos/' + target)
    if repo is None:
        return dict(row, verdict='FAIL', reasons=['repository not found'], usage=unknown)
    branch = repo.get('default_branch') or 'main'
    commits = get('repos/{}/commits?sha={}&per_page=1'.format(target, branch)) or []
    last_commit = stamp(commits[0]['commit']['committer']['date']) if commits else None
    head = commits[0].get('sha') if commits else None
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
    pulls = get('repos/{}/pulls?state=open&per_page=100'.format(target)) or []
    branches = get('repos/{}/branches?per_page=100'.format(target)) or []
    optimizing = (['PR #{}: {}'.format(p.get('number'), p.get('title', '')) for p in pulls
                   if PERF.search(p.get('title') or '')] +
                  ['branch ' + b['name'] for b in branches if PERF.search(b.get('name', '').replace('-', ' ').replace('_', ' '))])
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
                   last_commit_sha=head, optimizing=optimizing,
                   last_release=last_release.date().isoformat() if last_release else None,
                   commits_last_365_days=len(year) if len(year) < 100 else '100+',
                   last_issue_or_pr=last_issue.date().isoformat() if last_issue else None,
                   age_days=age)
    return dict(row, verdict='FAIL' if reasons else 'PASS', reasons=reasons, numbers=numbers,
                usage=usage(target, repo, get, packages, fetch_json, usage_cfg, clock))


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


def passing_verdict(directory, lane=None):
    """The verdict file in DIRECTORY that records at least one confirmed result, or None.
    A verdict.json (bug_verdicts.py) counts only when it was recorded and accepted in LANE."""
    structured = Path(directory) / 'verdict.json'
    if lane is not None and structured.is_file():
        try:
            return structured if bug_verdicts.accepted(structured, lane) and bug_verdicts.confirmed(structured) else None
        except (OSError, ValueError, KeyError):
            return None
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
    kinds = kinds_of(row)
    label = '+'.join(kinds) or 'unlabelled'
    if MERGE_MARK in text:
        failures.append('MERGE_UNEDITED: a batched draft still has its merge marker; make it one '
                        'email and delete the marker line')
    # 1. Target recency and activity.
    targets = row.get('targets', [])
    if any(kind_in(k, cfg['target_required_kinds']) for k in kinds) and not targets:
        failures.append('TARGET_MISSING: a {} email names the code it is about with --target '
                        'OWNER/REPO'.format(label))
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
        # Users: 11-08. Recent and active is not enough; somebody outside the project uses it.
        if not problem and any(k.startswith('code') for k in kinds):
            used = verdict.get('usage') or {}
            if used.get('verdict') != 'PASS':
                unused = ('TARGET_UNUSED: {} shows no users outside the project ({}); lead with something they '
                          'care about now, or --users-override with their words that it is in their current '
                          'pipeline'.format(target, used.get('reason') or 'outside accounts {}, stars {}'.format(
                              used.get('outside_accounts', '?'), used.get('stars', '?'))))
                if row.get('users_override'):
                    warnings.append(unused + ' (overridden: {})'.format(row['users_override']))
                else:
                    failures.append(unused)
        if problem and row.get('target_override'):
            warnings.append(problem + ' (overridden: {})'.format(row['target_override']))
        elif problem:
            failures.append(problem)
    # 2. One email per person per day, batched.
    limit = cfg['emails_per_contact_per_day']
    same = [o for o in everyone if o.get('channel') == 'email' and o.get('to_key') == row.get('to_key')
            and (o['lane'], o['id']) != (row['lane'], row['id'])]
    # A bounced email never reached them, so it is not contact (friends, 11-08: a bounced opener held the
    # next email to the same person on DAILY_LIMIT).
    recent = [o for o in same if sent_at(o) and o.get('status') != 'bounced'
              and clock - sent_at(o) < dt.timedelta(hours=24)]
    if limit and len(recent) >= limit and row.get('requested'):
        # 11-08: a send the recipient explicitly asked for is a reply, not outreach.
        warnings.append('DAILY_LIMIT not applied: they asked for this ({})'.format(row['requested']))
    elif limit and len(recent) >= limit:
        failures.append('DAILY_LIMIT: {} email(s) to this contact in the last 24 h ({}); the next '
                        'one may go from {}'.format(len(recent), ', '.join(o['id'] for o in recent),
                                                    (min(sent_at(o) for o in recent) +
                                                     dt.timedelta(hours=24)).strftime('%Y-%m-%d %H:%MZ')))
    waiting = [o for o in same if o.get('status') in ('drafted', 'linted', 'approved')]
    if limit and waiting:
        warnings.append('{} other unsent email(s) to this contact ({}); merge them with rh outreach '
                        'batch {} {!r}'.format(len(waiting), ', '.join(o['id'] for o in waiting),
                                               lane.name, row.get('to_key')))
    # Speedups: verified, current, on their latest commit, not duplicating their own work.
    speed_count = 0
    if 'code-speedup' in kinds:
        found, notes, speed_count = speedup.findings(row, None, lane, rh, latest_verdict, cfg['extra_rechecks'])
        failures += found
        warnings += notes
    # 3. The address. 4. Scrutiny. 5. Required questions: these read the contact.
    try:
        contact = contacts_ledger.merged(root, row['to_key'])
    except (OSError, ValueError, KeyError) as error:
        warnings.append('contact checks skipped: {}'.format(error))
        contact = None
    # Structured referee verdicts (bug_verdicts.py, 11-08): a verdict.json counts only once recorded and
    # accepted (plants caught), and a bug one referee refuted cannot go out on another's confirm alone.
    if any(k in ('code-bug', 'code') for k in kinds):
        refuted = bug_verdicts.ledger(lane, 'REFUTED.jsonl')
        for directory in row.get('rechecks', []):
            structured = Path(directory) / 'verdict.json'
            if not structured.is_file():
                continue
            if not bug_verdicts.accepted(structured, lane):
                failures.append('VERDICT_UNRECORDED: {} is not a recorded, accepted referee verdict; run rh bughunt '
                                'verdicts {} {}'.format(structured, lane.name, structured))
                continue
            doc = json.loads(structured.read_text())
            for c in bug_verdicts.confirmed(structured):
                fp = bug_verdicts.fingerprint(doc['target'], c['file'], c['function'])
                clash = [r for r in refuted if r['fingerprint'] == fp and r.get('batch') != doc['batch'] and
                         not (r.get('file_sha256') and c.get('file_sha256') and r['file_sha256'] != c['file_sha256'])]
                if clash:
                    failures.append('BUG_REFUTED_BEFORE: {} {}:{} was refuted by {} on {} ("{}"); the referees '
                                    'disagree, so a third one decides'.format(
                                        c['id'], c['file'], c['function'], clash[-1].get('referee'),
                                        clash[-1].get('utc', '')[:10], clash[-1].get('reason', '')))
        for target in row.get('targets', []):
            st = bug_coverage.status(lane, normalise(target))
            if not st['rounds']:
                warnings.append('COVERAGE_UNRECORDED: no hunt round on {} is recorded (rh bughunt coverage {} record '
                                'FILE)'.format(target, lane.name))
            elif not st['done']:
                warnings.append('COVERAGE_ONE_PASS: {} has {} hunt round(s) at {} and is not done; one pass finds '
                                'about half of what repeated passes do'.format(target, st['rounds'], (st['commit'] or '')[:10]))
    if contact is not None:
        book = contact.get('addresses', [])
        if book and not contacts_ledger.live_addresses(contact):
            failures.append('ADDRESS_DEAD: every address on record for this contact bounced; run '
                            'rh outreach contact find {!r}'.format(contact['name']))
        elif contact.get('needs_find'):
            warnings.append('an address bounced; a find is queued for this contact')
        found, notes = contacts_ledger.engagement_findings(contact, text)
        failures += found
        warnings += notes
        if contact.get('scrutiny') == 'extra':
            needs = []
            if 'code-speedup' in kinds:
                # The re-check of a speedup is a second, separate run of the benchmark and the
                # equality check on the same patch: another --speedup directory that passed.
                needs.append((speed_count, 'verified runs of the same patch (--speedup DIR)'))
            if set(kinds) - {'code-speedup'} or not kinds:
                needs.append((len({str(Path(d).resolve()) for d in row.get('rechecks', []) if passing_verdict(d, lane)}),
                              're-checks with a confirmed verdict (--recheck DIR)'))
            for count, what in needs:
                if count < cfg['extra_rechecks']:
                    failures.append('SECOND_RECHECK_MISSING: an extra-scrutiny contact needs {} '
                                    'independent {}; found {}'.format(cfg['extra_rechecks'], what, count))
            review = row.get('text_review') or {}
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if review.get('verdict') != 'pass' or review.get('sha256') != digest:
                failures.append('TEXT_REVIEW_MISSING: an extra-scrutiny contact needs a passing '
                                'review of this exact text (rh outreach review)')
    if any(kind_in(k, cfg['required_questions_kinds']) for k in kinds):
        answered = (contact or {}).get('answered', {})
        for name, keywords in zip(cfg['required_question_names'], cfg['required_questions']):
            if asks(text, keywords):
                continue
            if name in answered:
                warnings.append('{!r} not asked: already answered ({})'.format(name, answered[name]))
            else:
                failures.append('QUESTION_MISSING: a {} email asks {!r}'.format(label, name))
    return failures, warnings


# ---- CLI ----------------------------------------------------------------------------------

def arguments(sub):
    parser = sub.add_parser('bughunt', help='bug-hunt lane: target recency and activity checks')
    actions = parser.add_subparsers(dest='action', required=True)
    p = actions.add_parser('target-check', help='read GitHub and store a PASS/FAIL verdict')
    p.add_argument('lane')
    p.add_argument('target', help='OWNER/REPO or its GitHub URL')
    p.add_argument('--package', action='append', default=[], metavar='INDEX:NAME',
                   help='a package to count downloads for: pypi:NAME, cran:NAME, bioconda:NAME, conda-forge:NAME')
    p.add_argument('--json', action='store_true')
    p = actions.add_parser('speedup-verify', help='apply a speedup patch to their commit, check equal outputs, benchmark')
    p.add_argument('lane')
    p.add_argument('dir', help='directory holding SPEEDUP.json')
    p = actions.add_parser('targets', help='stored verdicts, newest first')
    p.add_argument('lane')
    p.add_argument('--json', action='store_true')
    p = actions.add_parser('claims-check', help="refuse a hunter's claims that a referee refuted before")
    p.add_argument('lane')
    p.add_argument('claims', type=Path, help='claims.json from the hunter')
    p = actions.add_parser('referee-prompt', help='the standard referee prompt, with planted false claims mixed in')
    p.add_argument('lane')
    p.add_argument('claims', type=Path, help='claims.json from the hunter')
    p.add_argument('workdir', type=Path, help="the referee's working directory (gets claims.json and PROMPT.md)")
    p.add_argument('--plants', type=Path, help='a JSON list of false claims written for this target')
    p.add_argument('--plant', type=int, default=1, help='automatic plants to add (default 1)')
    p.add_argument('--extra', type=Path, help="a file of host notes appended to the prompt (toolchains, limits)")
    p.add_argument('--hunter-family', help="the hunter's model family, when the claims file has no \"hunter\"")
    p = actions.add_parser('verdicts', help="validate a referee's verdict.json, check its plants, record it")
    p.add_argument('lane')
    p.add_argument('file', type=Path)
    p.add_argument('--receipt', type=Path, help="the launcher's JOB.log.selection.json for this referee run")
    p = actions.add_parser('referees', help='confirm rate and plant catch rate per referee')
    p.add_argument('lane')
    p = actions.add_parser('coverage', help='what was already hunted in a repository')
    p.add_argument('lane')
    p.add_argument('what', choices=('record', 'show'))
    p.add_argument('arg', help='record: a coverage JSON file; show: OWNER/REPO')


def verdict_commands(lane, args, rh):
    if args.action == 'referees':
        for line in bug_verdicts.referees(lane) or ['no referee batches recorded']:
            print(line)
        return 0
    if args.action == 'coverage':
        if args.what == 'record':
            with rh.locked(lane):
                ok, msgs = bug_coverage.record(lane, json.loads(Path(args.arg).read_text()))
            print('\n'.join(msgs))
            return 0 if ok else 1
        st = bug_coverage.status(lane, normalise(args.arg))
        print('{} rounds at {}; {}'.format(st['rounds'], (st['commit'] or '-')[:10], 'done' if st['done'] else
                                          'not done (two rounds, the last with no new candidate, nothing deferred)'))
        for unit, cls in st['covered']:
            print('  covered   {}  {}'.format(unit, cls))
        for unit, cls in st['deferred']:
            print('  deferred  {}  {}'.format(unit, cls))
        return 0
    if args.action == 'verdicts':
        with rh.locked(lane):
            ok, msgs = bug_verdicts.record(lane, args.file, receipt=args.receipt)
        print('\n'.join(msgs))
        return 0 if ok else 1
    doc = json.loads(args.claims.read_text())
    if args.action == 'claims-check':
        found = bug_verdicts.claims_check(lane, doc)
        print('\n'.join(found) if found else 'PASS: {} claims, none refuted before'.format(len(doc['claims'])))
        return 1 if found else 0
    plants = json.loads(args.plants.read_text()) if args.plants else []
    extra = args.extra.read_text() if args.extra else ''
    with rh.locked(lane):
        batch, real, planted = bug_verdicts.referee_prompt(lane, doc, args.workdir.expanduser().resolve(),
                                                           plants, args.plant, extra=extra,
                                                           hunter_family=args.hunter_family)
    print('batch {}: {} claims + {} planted in {}/claims.json; prompt {}/PROMPT.md'.format(
        batch, real, planted, args.workdir, args.workdir))
    return 0


def main(root, args, rh, get=None):
    import outreach
    root = Path(root).expanduser().resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.lane):
        raise ValueError('invalid lane name')
    lane = root / 'lanes' / args.lane
    if not lane.is_dir():
        raise ValueError('lane directory missing')
    cfg = outreach.settings(lane, rh)
    if args.action in ('claims-check', 'referee-prompt', 'verdicts', 'referees', 'coverage'):
        return verdict_commands(lane, args, rh)
    if args.action == 'speedup-verify':
        row = speedup.verify(args.dir, cfg)
        print('{} {} {}x ({} s -> {} s)'.format(row['verdict'], row['target'], row.get('speedup'),
                                             (row.get('median_seconds') or {}).get('before'),
                                             (row.get('median_seconds') or {}).get('after')))
        for code in row['codes']:
            print('  ' + code)
        return 0 if row['verdict'] == 'PASS' else 1
    if args.action == 'target-check':
        row = target_check(args.target, cfg['target_max_age_days'], get, packages=args.package, usage_cfg=cfg)
        with rh.locked(lane):
            rh.append(lane / 'TARGETS.jsonl', row)
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            # The headline is the whole verdict: friends read "PASS" on a target whose users line said FAIL.
            used = row.get('usage') or {}
            both = 'PASS' if row['verdict'] == 'PASS' and used.get('verdict') == 'PASS' else 'FAIL'
            print('{} {} (recency {}, users {}){}'.format(both, row['target'], row['verdict'], used.get('verdict'),
                                                        (': ' + '; '.join(row['reasons'])) if row['reasons'] else ''))
            print('  users: {} ({})'.format(used.get('verdict'), '; '.join(used.get('signals') or []) or
                                            'outside accounts {} recent, {} older; stars {}'.format(
                                                used.get('outside_accounts'), used.get('outside_accounts_older'),
                                                used.get('stars'))))
            for key, value in (row.get('numbers') or {}).items():
                print('  {}: {}'.format(key, value))
        return 0 if row['verdict'] == 'PASS' and (row.get('usage') or {}).get('verdict') == 'PASS' else 1
    rows = sorted(verdicts(lane, rh), key=lambda r: r['utc'], reverse=True)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print('{} {} {} {}'.format(r['utc'][:16], r['verdict'], r['target'], '; '.join(r.get('reasons', []))))
    return 0
