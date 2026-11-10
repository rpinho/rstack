"""What a lane's upstream has actually taken: merged PRs, not pushes or opened PRs.

Why (11-10). The math lane's results are PRs to a maintainer's repo. By 11-10 nothing had been
merged there since 10-26, for anyone; 18 of the 86 open PRs were ours and only 6 of ours had ever
merged, yet the lane's yield counted every refereed row as shipped and its reports said "live on
Tao's table". A push or an opened PR is activity. So, for a lane with UPSTREAM.json:

  * lane-yield counts a result only when its link is a merged PR (or a commit) in that repo;
  * `rh lanes upstream` shows open-unmerged N and the oldest one's age;
  * publish_lint refuses a NEW PR there while we have max_open or more open (stacked ones count;
    updating an existing PR is still allowed);
  * tell-general refuses a report that calls an unmerged PR "live".

lanes/LANE/UPSTREAM.json:  {"repo": "owner/name", "author": "github-login", "max_open": 10}

The PR list is fetched with `gh api` (refresh) and cached beside it as .upstream-prs.json. Readers
never touch the network (the publish hook may not); a cache older than MAX_AGE_H is a refusal for
the gate, not a guess.
"""
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess

CONFIG = 'UPSTREAM.json'
CACHE = '.upstream-prs.json'
MAX_AGE_H = 6
UTC = dt.timezone.utc


def now_utc():
    return dt.datetime.now(UTC)


def parse(stamp):
    return dt.datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).astimezone(UTC)


def config(lane):
    """The lane's upstream settings, or None when it has none."""
    path = Path(lane) / CONFIG
    if not path.is_file():
        return None
    cfg = json.loads(path.read_text())
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', str(cfg.get('repo', ''))):
        raise ValueError('{}: repo must be owner/name'.format(path))
    if not re.fullmatch(r'[A-Za-z0-9-]+', str(cfg.get('author', ''))):
        raise ValueError('{}: author must be a GitHub login'.format(path))
    cfg.setdefault('max_open', 10)
    if type(cfg['max_open']) is not int or cfg['max_open'] < 1:
        raise ValueError('{}: max_open must be a positive integer'.format(path))
    return cfg


def lanes_with_upstream(root):
    base = Path(root).expanduser() / 'lanes'
    return [p for p in sorted(base.iterdir()) if p.is_dir() and (p / CONFIG).is_file()] if base.is_dir() else []


def gh_pulls(repo):
    """Every PR of the repo, as dicts, from the GitHub API through an authenticated gh."""
    gh = shutil.which('gh') or '/opt/homebrew/bin/gh'
    out = subprocess.run([gh, 'api', '-X', 'GET', 'repos/{}/pulls'.format(repo), '-f', 'state=all',
                          '-f', 'per_page=100', '--paginate', '--jq',
                          '.[] | {number, state, merged_at, created_at, url: .html_url, '
                          'author: .user.login, base: .base.ref}'],
                         capture_output=True, text=True, timeout=120, check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def refresh(lane, fetch=gh_pulls, now=None):
    cfg = config(lane)
    if cfg is None:
        raise ValueError('{} has no {}'.format(lane, CONFIG))
    prs = fetch(cfg['repo'])
    data = dict(fetched=(now or now_utc()).isoformat(timespec='seconds'), repo=cfg['repo'], prs=prs)
    tmp = Path(lane) / (CACHE + '.tmp')
    tmp.write_text(json.dumps(data))
    tmp.replace(Path(lane) / CACHE)
    return data


def cached(lane):
    try:
        return json.loads((Path(lane) / CACHE).read_text())
    except (OSError, ValueError):
        return None


def age_hours(data, now=None):
    return ((now or now_utc()) - parse(data['fetched'])).total_seconds() / 3600


def summary(lane, now=None):
    """Our PRs there: open-unmerged count and the oldest one's age, merged count, last merge."""
    cfg, data = config(lane), cached(lane)
    if cfg is None or data is None:
        return None
    now = now or now_utc()
    ours = [p for p in data['prs'] if p.get('author', '').lower() == cfg['author'].lower()]
    open_ = sorted((p for p in ours if p['state'] == 'open'), key=lambda p: p['created_at'])
    merged = [p for p in ours if p.get('merged_at')]
    anyone = [p['merged_at'] for p in data['prs'] if p.get('merged_at')]
    return dict(repo=cfg['repo'], open_unmerged=len(open_),
                oldest_open_days=round((now - parse(open_[0]['created_at'])).total_seconds() / 86400, 1)
                if open_ else None,
                oldest_open=open_[0]['url'] if open_ else None, merged=len(merged),
                last_merge_ours=max((p['merged_at'] for p in merged), default=None),
                last_merge_anyone=max(anyone, default=None), max_open=cfg['max_open'],
                cache_age_h=round(age_hours(data, now), 1))


def line(s):
    return ('upstream {repo}: open-unmerged {n}{oldest}; merged {m} (last ours {lo}, last anyone {la}); '
            'list {age} h old').format(
        repo=s['repo'], n=s['open_unmerged'],
        oldest=', oldest {} d'.format(s['oldest_open_days']) if s['oldest_open_days'] is not None else '',
        m=s['merged'], lo=(s['last_merge_ours'] or 'never')[:10], la=(s['last_merge_anyone'] or 'never')[:10],
        age=s['cache_age_h'])


def taken(lane, link):
    """True when link is a merged PR, or a commit, in the lane's upstream repo."""
    cfg, data = config(lane), cached(lane)
    if cfg is None or data is None or not link:
        return False
    repo = re.escape(cfg['repo'])
    m = re.match(r'https://github\.com/' + repo + r'/pull/(\d+)', str(link), re.I)
    if m:
        return any(p['number'] == int(m.group(1)) and p.get('merged_at') for p in data['prs'])
    return bool(re.match(r'https://github\.com/' + repo + r'/commit/[0-9a-f]{7,40}', str(link), re.I))


def new_pr_errors(root, repo, now=None):
    """Why a NEW PR to repo must wait, or [] (no lane has that upstream, or we are under the cap)."""
    errors = []
    for lane in lanes_with_upstream(root):
        cfg = config(lane)
        if cfg['repo'].lower() != repo.lower():
            continue
        data = cached(lane)
        if data is None or age_hours(data, now) > MAX_AGE_H:
            errors.append('cannot confirm how many of our PRs are open in {}: the PR list is {}. '
                          'Refresh it with: rh lanes upstream --lane {} --refresh'.format(
                              repo, 'missing' if data is None else 'over {} h old'.format(MAX_AGE_H),
                              lane.name))
            continue
        s = summary(lane, now)
        if s['open_unmerged'] >= cfg['max_open']:
            errors.append('{n} of our PRs are open and unmerged in {repo} (oldest {d} d, last merge of ours '
                          '{lo}). No new PR while {cap} or more are open; stacked PRs count. Update an '
                          'existing PR instead, or wait for merges.'.format(
                              n=s['open_unmerged'], repo=repo, d=s['oldest_open_days'],
                              lo=(s['last_merge_ours'] or 'never')[:10], cap=cfg['max_open']))
    return errors


PR_REF = re.compile(r'github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(\d+)|(?<![\w/])#(\d+)\b', re.I)
TABLE = re.compile(r"\bon\s+Tao[\u2019']?s\s+(?:optimization\s+)?table\b", re.I)   # not "on the table"
FIX = 'say "PR updated, not merged"'
X_FIX = 'write "candidate bound for C22b (Tao\'s optimization table), PR open"'


def report_lint(text, root, fix=FIX):
    """Reasons a lane report misstates an unmerged PR as shipped; [] when it does not.

    "live" next to a PR that is not merged fails, and so does "on Tao's table" unless every PR it
    names is merged. It should say "PR updated, not merged". Only PRs in a lane's cached upstream
    list are judged, so other uses of "live" pass."""
    known = {}
    for lane in lanes_with_upstream(root):
        data = cached(lane)
        for p in (data or {}).get('prs', []):
            known[(data['repo'].lower(), p['number'])] = bool(p.get('merged_at'))
    repos = {r for r, _ in known}
    if not repos:
        return []
    errors = []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        refs = []
        for m in PR_REF.finditer(sentence):
            if m.group(1):
                key = (m.group(1).lower(), int(m.group(2)))
                if key in known:
                    refs.append(key)
            else:
                refs += [(r, int(m.group(3))) for r in repos if (r, int(m.group(3))) in known]
        unmerged = sorted({n for key, n in [(k, k[1]) for k in refs] if not known[key]})
        if TABLE.search(sentence) and (unmerged or not refs):
            errors.append('"on Tao\'s table" is only true once merged{}: {}'.format(
                ' (#{} not merged)'.format(', #'.join(map(str, unmerged))) if unmerged else
                ' (name the PR, and only if it merged)', fix))
        elif unmerged and re.search(r'\blive\b', sentence, re.I):
            errors.append('#{} {} not merged, so not live: {}'.format(
                ', #'.join(map(str, unmerged)), 'is' if len(unmerged) == 1 else 'are', fix))
    return errors
