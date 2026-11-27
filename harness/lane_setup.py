"""Create isolated lanes with frozen v2 declarations; never invent research evidence."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import idea_policy
import selection_policy
import lessons

REPO = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def arguments(sub):
    lane = sub.add_parser('lane', help='create and inspect a lane before research begins')
    actions = lane.add_subparsers(dest='action', required=True)
    new = actions.add_parser('new', help='write a fresh lane and frozen v2 protocol; no evidence or workers')
    new.add_argument('name')
    for flag in ('problem', 'metric', 'dev-set', 'hidden-test', 'split-reason', 'sealed-set-id', 'submission-rules'):
        new.add_argument('--' + flag, required=True)
    new.add_argument('--split', required=True, choices=('group', 'time', 'source', 'random'))
    new.add_argument('--test-shares-units-statement', default='')
    deadline = new.add_mutually_exclusive_group(required=True)
    deadline.add_argument('--deadline', help='ISO UTC timestamp')
    deadline.add_argument('--deadline-days', type=int)
    new.add_argument('--submissions', required=True, type=int)
    new.add_argument('--sealed-budget', type=int, default=1, help='independent selector batches, distinct from upload count')
    new.add_argument('--test', default='paired exact-match accuracy on development folds held out by the declared split')
    new.add_argument('--bar', default='strictly beat the last-value baseline under the frozen v2 confidence and backtest checks')
    new.add_argument('--final-fit', choices=('fixed_steps', 'fold_ensemble'), default='fixed_steps')


PRIOR_ART = []


def prior_art():
    """The one prior-art search (tools/prior_art_receipt.py), loaded once."""
    if not PRIOR_ART:
        spec = importlib.util.spec_from_file_location('prior_art_receipt', Path(__file__).resolve().parent / 'tools/prior_art_receipt.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        PRIOR_ART.append(module)
    return PRIOR_ART[0]


def overlap(lane, problem):
    """11-19: before a lane starts, is anyone else already working on this problem? Write the answer to
    OVERLAP.json, outside the frozen files so it can be re-run. It records and never refuses."""
    if os.environ.get('RH_OVERLAP', '').lower() in ('0', 'off', 'no'):
        receipt = dict(schema=1, check='overlap', query=problem, status='skipped', reason='RH_OVERLAP=off', sources={})
    else:
        try:
            receipt = prior_art().overlap(problem)
        except Exception as exc:
            receipt = dict(schema=1, check='overlap', query=problem, status='unavailable',
                           reason=f'{type(exc).__name__}: {str(exc)[:200]}', sources={})
    receipt.setdefault('searched_at', dt.datetime.now(UTC).replace(microsecond=0).isoformat())
    (lane / 'OVERLAP.json').write_text(json.dumps(receipt, indent=1) + '\n')
    found = sum(len(v.get('hits', [])) for v in receipt['sources'].values())
    print('Overlap check: {} ({} hits) in {}'.format(receipt['status'], found, lane / 'OVERLAP.json'))
    return receipt


def stamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError('deadline must be an ISO UTC timestamp')
    return parsed


def create(root, args, rh):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.name):
        raise ValueError('invalid lane name')
    for field in ('problem', 'metric', 'dev_set', 'hidden_test', 'split_reason', 'sealed_set_id', 'submission_rules', 'test', 'bar'):
        value = getattr(args, field)
        if not isinstance(value, str) or not value.strip() or any(c in value for c in '\n\r\0'):
            raise ValueError(field + ' must be nonempty one-line text')
    if args.dev_set == args.hidden_test:
        raise ValueError('development and hidden test must be distinct')
    now = dt.datetime.now(UTC)
    if args.deadline_days is not None and args.deadline_days < 1:
        raise ValueError('deadline-days must be positive')
    deadline = stamp(args.deadline) if args.deadline else now + dt.timedelta(days=args.deadline_days)
    if deadline <= now:
        raise ValueError('deadline must be in the future')
    policy = dict(policy_version=2, split=args.split, split_reason=args.split_reason,
        preprocessing_inside_folds=True, augmentation_used=False, final_fit=args.final_fit,
        min_measurements=10, n_trials_total=0, trials=[], sealed_set_id=args.sealed_set_id,
        sealed_budget=args.sealed_budget, submissions=args.submissions, backtest_margin=0)
    if args.split == 'random':
        policy.update(test_shares_units=True, test_shares_units_statement=args.test_shares_units_statement)
    selection_policy.validate(policy)
    payload = dict(created=now.isoformat(), problem=args.problem, metric=args.metric, dev_set=args.dev_set,
        hidden_test=args.hidden_test, deadline=deadline.isoformat(), submissions=args.submissions,
        submission_rules=args.submission_rules, test=args.test, bar=args.bar,
        selection_board='independent-sealed-selector', worker_sealed_access=False,
        public_board_selection=False, selection_policy_sha256=digest(policy))
    record = dict(schema=1, created=now.isoformat(), frozen=payload, frozen_sha256=digest(payload))
    lane = root.expanduser().resolve() / 'lanes' / args.name
    lane.mkdir(parents=True, exist_ok=False)
    (lane / 'LANE.json').write_text(json.dumps(record, indent=2) + '\n')
    (lane / 'SELECTION.json').write_text(json.dumps(policy, indent=2) + '\n')
    intake = '''# Sources are unconfigured. Setup records no external reading or scores.
keywords = [%s]
arxiv_queries = []
biorxiv_pages = 0
community_urls = []
github_pr_repos = []
minimum_attempts = 2
lessons_required = false
claude_science_required = false
selection_min_measurements = 10
selection_sealed_budget = %d
selection_submissions = %d
''' % (json.dumps(args.problem), args.sealed_budget, args.submissions)
    (lane / 'INTAKE.toml').write_text(intake)
    sweep = (REPO / 'examples/toy-lane/SWEEP.toml').read_text()
    sweep = sweep.replace('enabled = true', 'enabled = true\nworkers_enabled = false', 1)
    sweep = sweep.replace('start_date = "2026-11-03"', 'start_date = ' + json.dumps(now.isoformat()))
    sweep = sweep.replace('search_targets = ["toy sequence generation"]', 'search_targets = [' + json.dumps(args.problem) + ']')
    sweep = sweep.replace('sources = ["https://example.org/synthetic-reference"]', 'sources = [' + json.dumps('operator-provided development data: ' + args.dev_set) + ']')
    sweep = sweep.replace('launcher = "../../tools/launch.sh"', 'launcher = ' + json.dumps(str(REPO / 'tools/launch.sh')))
    sweep = sweep.replace('boards = ["TOY"]', 'boards = ["DEV"]')
    sweep = sweep.replace('allowed_tests = ["enumerate a finite synthetic integer sequence"]', 'allowed_tests = [' + json.dumps(args.test) + ']')
    (lane / 'SWEEP.toml').write_text(sweep)
    (lane / 'CADENCE.toml').write_text('''deliverable = "verified development result"
every_hours = 24
warn_hours = 18
evidence_root = "."
evidence_globs = ["reports/*-verified.md"]
owner_session = "lane-agent"
''')
    # The rules every lane gets come from harness/LANE_RULES_COMMON.md, never from a copy here;
    # `lane-rules-sync` refreshes them in existing lanes. A new lane starts with the same block.
    try:
        common = (Path(__file__).resolve().parent / 'LANE_RULES_COMMON.md').read_text().strip() + '\n\n'
    except OSError:
        common = ''
    (lane / 'RULES.md').write_text(common + '''# Lane rules

Use development folds only. Never read or score hidden targets; an independent
selector owns the sealed set. Never select using a visible/public board.
LANE.json freezes the problem, metric, test and bar before results. SELECTION.json
freezes the v2 declarations. Describe assumptions honestly; no data was supplied.
No outreach without `rh outreach` approval. No submissions by sweep workers.
Keep workers bounded by SWEEP.toml. Send deletions to Trash.
''')
    problems = audit(lane, rh)
    if problems:
        raise ValueError('; '.join(problems))
    print('Created {}: frozen v2 declarations; workers disabled; no results or external reads claimed'.format(lane))
    print('Frozen declarations are immutable; changed assumptions require a new lane.')
    overlap(lane, args.problem)
    lessons.record_read(lane, rh)
    print('Next: rh --root {} lint {}'.format(root, args.name))
    return 0


def read(lane):
    return json.loads((lane / 'LANE.json').read_text()), json.loads((lane / 'SELECTION.json').read_text())


def audit(lane, rh):
    if not (lane / 'LANE.json').exists():
        return []  # existing lanes retain their original admission contract
    try:
        record, policy = read(lane)
        frozen = record['frozen']
        if record['schema'] != 1 or record['frozen_sha256'] != digest(frozen):
            raise ValueError('frozen lane declaration changed')
        if frozen['selection_policy_sha256'] != digest(policy):
            raise ValueError('frozen selection declaration changed; create a new lane for a new protocol')
        selection_policy.lane_policy(policy, rh.lane_config(lane))
        if frozen['submissions'] != policy['submissions']:
            raise ValueError('submission count must match frozen v2 policy')
        for key in ('problem', 'metric', 'dev_set', 'hidden_test', 'submission_rules', 'test', 'bar'):
            if not isinstance(frozen[key], str) or not frozen[key].strip():
                raise ValueError('missing frozen ' + key)
        if frozen['dev_set'] == frozen['hidden_test']:
            raise ValueError('development and hidden test must be distinct')
        if (frozen['worker_sealed_access'] is not False or frozen['public_board_selection'] is not False
                or frozen['selection_board'] != 'independent-sealed-selector'):
            raise ValueError('workers must not access sealed data or select on a visible board')
        if record['created'] != frozen['created']:
            raise ValueError('frozen lane creation time changed')
        created = stamp(record['created'])
        if stamp(frozen['deadline']) <= created:
            raise ValueError('deadline must follow lane creation')
        import cadence
        cadence.load(lane, rh)
        import sweep
        sweep.load(lane, rh)
        fast = idea_policy.checker(lane)
        for row in rh.rows(lane / 'IDEAS.jsonl'):
            # 11-27: a venue with a checker submits without a frozen selection. Only a leaderboard's
            # final pick (status shipped) still needs one, so the visible board never picks it.
            if fast and (fast != 'leaderboard' or row.get('status') == 'testing'):
                continue
            if row.get('status') in ('testing', 'shipped'):
                if row.get('policy_version') != 2:
                    raise ValueError('new lanes require v2 before an experiment')
                if row.get('selection_policy') != policy:
                    raise ValueError('idea selection policy differs from frozen lane declaration')
        return []
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return ['lane declaration invalid: ' + str(exc)]


def in_setup(lane, rh):
    if not (lane / 'LANE.json').exists():
        return False
    record, _ = read(lane)
    age = dt.datetime.now(UTC) - stamp(record['created'])
    if not dt.timedelta(0) <= age < dt.timedelta(hours=24):
        return False
    if rh.config(lane / 'SWEEP.toml').get('workers_enabled') is not False:
        return False
    return not any(rh.rows(lane / name) for name in
        ('IDEAS.jsonl', 'INTAKE_RUNS.jsonl', 'SWEEP_RUNS.jsonl', 'SEALED_SCORING.jsonl'))


def main(root, args, rh):
    return create(root, args, rh)
