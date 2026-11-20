"""Lane lifecycle data shared by schedulers, launchers and the conductor.

An absent default registry preserves unregistered lanes. A configured but missing
registry, malformed entry or ambiguous session is an error, never an active lane.
The end date is inclusive: a lane ends on the following day (local calendar date).
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys


def _date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('expected YYYY-MM-DD, got {!r}'.format(value))
    return date.fromisoformat(value)


class LaneRegistry:
    def __init__(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('lanes'), dict):
            raise ValueError('registry must contain a lanes object')
        self.lanes = data['lanes']
        self.sessions = {}
        for lane, row in self.lanes.items():
            if not isinstance(lane, str) or not lane or not isinstance(row, dict):
                raise ValueError('invalid lane entry')
            if row.get('status') not in ('active', 'retired', 'held'):
                raise ValueError('invalid status for lane ' + lane)
            for field in ('since', 'end'):
                if field in row:
                    _date(row[field])
            if not isinstance(row.get('why', ''), str):
                raise ValueError('why must be text for lane ' + lane)
            if 'x' in row and not isinstance(row['x'], bool):
                raise ValueError('x must be boolean for lane ' + lane)
            sessions = row.get('sessions', [])
            if not isinstance(sessions, list) or any(not isinstance(s, str) or not s for s in sessions):
                raise ValueError('sessions must be a list of names for lane ' + lane)
            aliases = row.get('aliases', [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) or not a for a in aliases):
                raise ValueError('aliases must be a list of names for lane ' + lane)
            for session in [lane] + sessions + aliases:
                if session in self.sessions and self.sessions[session] != lane:
                    raise ValueError('ambiguous session ' + session)
                self.sessions[session] = lane
        # Job-name prefixes that are not sessions (11-18: nightly-<date> is the digest lane's job,
        # bio's hunt_* and ref_* are open-source's). Checked after every lane's sessions are known.
        self.job_prefixes = {}
        for lane, row in self.lanes.items():
            prefixes = row.get('job_prefixes', [])
            if not isinstance(prefixes, list) or any(not isinstance(p, str) or not p for p in prefixes):
                raise ValueError('job_prefixes must be a list of names for lane ' + lane)
            for prefix in prefixes:
                owner = self.job_prefixes.get(prefix, self.sessions.get(prefix, lane))
                if owner != lane:
                    raise ValueError('ambiguous job prefix ' + prefix)
                self.job_prefixes[prefix] = lane

    def lane_of_session(self, name):
        if name in self.sessions:
            return self.sessions[name]
        for prefix in ('claude-', 'codex-'):
            if name.startswith(prefix) and name[len(prefix):] in self.sessions:
                return self.sessions[name[len(prefix):]]
        return name

    def registered_lane_of_job(self, name):
        """Longest registered lane, session, alias or job prefix; None when the registry has no match."""
        name = Path(name).name
        names = dict(self.job_prefixes, **self.sessions)
        for prefix in sorted(names, key=len, reverse=True):
            if name == prefix or name.startswith((prefix + '_', prefix + '-')):
                return names[prefix]
        return None

    def lane_of_job(self, name):
        """Longest registered lane/session/job prefix; retain the launcher's legacy fallback."""
        name = Path(name).name
        lane = self.registered_lane_of_job(name)
        if lane:
            return lane
        # This hyphen is part of the lane name, even without a local registry.
        if name == 'open-source' or name.startswith(('open-source_', 'open-source-')):
            return 'open-source'
        return re.split('[-_]', name, maxsplit=1)[0]

    def status(self, lane, today=None):
        row = self.lanes.get(self.lane_of_session(lane), {})
        if row.get('end') and _date(today or date.today()) > _date(row['end']):
            return 'ended'
        return row.get('status', 'active')

    def reason(self, lane, today=None):
        lane = self.lane_of_session(lane)
        row = self.lanes.get(lane, {})
        state = self.status(lane, today)
        detail = ('end ' + row['end']) if state == 'ended' else ('since ' + row['since'] if row.get('since') else '')
        return '{}: {}{}{}'.format(lane, state, ' (' + detail + ')' if detail else '',
                                  ': ' + row['why'] if row.get('why') else '')

    def retired_reason(self, *names):
        """Reason for filing an ask/report under retired, including ended lanes."""
        for name in names:
            if name and self.status(name) in ('retired', 'ended'):
                return self.reason(name)
        return None

    def x_refusal(self, lane, lanes_root):
        """An explicit X prohibition wins, including over x:true and owner:general.

        Prefer the registry's boolean x field. Also honor plain no-X rules in
        legacy RULES.md files until their policy has been encoded in the registry.
        """
        canonical = self.lane_of_session(lane)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', canonical):
            raise ValueError('invalid X lane tag')
        if self.lanes.get(canonical, {}).get('x') is False:
            return canonical + ': registry x=false'
        aliases = [name for name, target in self.sessions.items() if target == canonical]
        for name in sorted(set([canonical, lane] + aliases)):
            # Registry session names are not filesystem paths.
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                continue
            path = Path(lanes_root) / name / 'RULES.md'
            try:
                rules = path.read_text()
            except FileNotFoundError:
                continue
            text = re.sub(r'[*_`]', '', rules)
            text = re.sub(r'\n(?!\s*(?:\n|[-#]))', ' ', text)
            # Operative clauses, not incidental mentions of X in a long rule file.
            clauses = re.split(r'[.!?;\n]+', text)
            for clause in clauses:
                denied = (
                    re.search(r'\bx\s*[:=]\s*false\b', clause, re.I)
                    or re.search(r'\b(?:no|never|do not|don.t|must not|cannot|may not)\b.{0,120}'
                                 r'\b(?:post|publish|share|disclose|tweet)\w*\b.{0,100}'
                                 r'\b(?:X|Twitter)\b', clause, re.I)
                    or re.search(r'\b(?:results?|lane|work)\b.{0,100}'
                                 r'\b(?:stay|stays|keep|kept|remain|remains)\b.{0,40}'
                                 r'\boff\s+(?:X|Twitter)\b', clause, re.I)
                    or re.search(r'\bno\s+(?:X|Twitter)\s+(?:posts?|posting|results?)\b', clause, re.I))
                if denied:
                    return canonical + ': ' + str(path) + ': ' + clause.strip()
        return None


def load(lanes_root=None):
    """Read RH_LANE_REGISTRY, otherwise <lanes_root>/REGISTRY.json.

    Without a caller-supplied lanes root, use RH_ROOT/lanes or the installed
    research-harness lanes directory. Read afresh on each invocation.
    """
    configured = os.environ.get('RH_LANE_REGISTRY')
    root = Path(lanes_root).expanduser() if lanes_root is not None else Path(
        os.environ.get('RH_ROOT') or '~/.local/share/research-harness').expanduser() / 'lanes'
    path = Path(configured).expanduser() if configured else root / 'REGISTRY.json'
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        if configured:
            raise
        data = {'lanes': {}}
    return LaneRegistry(data)


def status(lane, today=None):
    return load().status(lane, today)


def lane_of_session(name):
    return load().lane_of_session(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--lanes-root')
    parser.add_argument('--job', required=True)
    parser.add_argument('--lane', default='')
    args = parser.parse_args(argv)
    import harness_blocks   # RULE #1: only rstack/gates.json decides whether this may stop a job
    try:
        registry = load(args.lanes_root)
        lane = registry.lane_of_session(args.lane) if args.lane else registry.lane_of_job(args.job)
        if registry.status(lane) in ('retired', 'ended', 'held'):
            if harness_blocks.gate('launch.lane-status', '{}: {}'.format(args.job, registry.reason(lane)),
                                   job=args.job, lane=lane):
                return 78
        print(lane)
        return 0
    except (OSError, ValueError) as exc:
        # An unreadable registry is a harness error, not a reason to stop the job: it runs under the
        # lane its own name gives (the launcher's legacy fallback), with a warning in the ledger.
        lane = args.lane or LaneRegistry({'lanes': {}}).lane_of_job(args.job)
        if harness_blocks.gate('launch.lane-registry', 'lane registry unreadable ({}); running {} as lane {}'.format(
                exc, args.job, lane), job=args.job, lane=lane):
            return 78
        print(lane)
        return 0


if __name__ == '__main__':
    sys.exit(main())
