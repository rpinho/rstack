#!/usr/bin/env python3
"""log_result: record a lane result in its RESULTS.jsonl ledger, the yield that lane-yield counts.

A lane exists to find something new. Every result that leaves a lane (a filed PR, a submitted note, a
leaderboard entry, an email to a researcher) gets one line, NEW yes or no, with its evidence link and
the referee verdict. lane-yield counts new=true lines with a HOLDS verdict.

    log_result.py --ledger ~/.local/share/research-harness/lanes/math/RESULTS.jsonl \\
        --new yes --kind value --what "C38 bound 0.25 -> 0.2524" --link https://github.com/... --referee HOLDS
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
# result_lint sits beside this tool's directory in BOTH layouts: harness/tools in the
# repo, tools/ in the install. Before 11-06 this was parents[3]/'tools'/'result-lint',
# which only resolved in the repo, so ~/.local/bin/lane-yield had to symlink to the
# working tree and the installed copy could not even import. A yield test that fails
# to start is a dry lane spinning instead of being told to change direction.
LINT = HERE.parents[1]
sys.path.insert(0, str(LINT))

KINDS = ('rerun', 'value', 'question', 'conjecture', 'note', 'other')
sys.path.insert(0, str(HERE.parents[2]))
try:
    import verdict_rubric
except ImportError:                  # installed layouts that do not ship the harness package
    verdict_rubric = None
try:
    import result_gates
except ImportError:
    result_gates = None
URL = re.compile(r'(?:https?://|doi:|10\.\d{4,9}/)', re.I)


def new_errors(kind, link):
    """Why this `--new yes` row is not admissible, or [] when it is.

    `new_yes` is the number the whole yield test turns on, and it was writeable by assertion:
    any `--new yes --referee HOLDS` was accepted with no evidence check, and `--kind rerun`
    counted as new (the friends ledger has one such row). A reproduction is not a new result --
    LANE_RULES_COMMON.md says so and the referee cannot see this ledger -- so the ledger now
    asks for the same evidence a claim would need.
    """
    if kind == 'rerun':
        return ['a rerun is not new: reproducing a result is not finding one (--kind rerun '
                'cannot be --new yes)']
    target = Path(link).expanduser()
    if target.is_dir():
        try:
            from result_lint import lint
        except ImportError:
            # Fail loudly rather than let an unimportable linter wave the row through.
            return ['result-lint is not importable, so this claim dir cannot be checked; '
                    'expected it under ' + str(LINT)]
        return ['claim dir fails result-lint: ' + e for e in lint(target, new_only=True)]
    if URL.match(link.strip()):
        return []
    return ['--new yes needs evidence: a claim directory that passes result-lint, or a PR, '
            'DOI or other https link. Got neither.']


def resolve_ledger(value, create=False):
    """(path, error). 11-15, virtual-embryo: `--ledger virtual-embryo` appended to ./virtual-embryo in the
    session cwd, printed the row and exited 0; seven results sat in stray files for a week and lane-yield
    never saw them. A bare lane name now means that lane's RESULTS.jsonl, and a path must be an existing
    .jsonl ledger (a new one only with --new-ledger)."""
    raw = str(value)
    if '/' not in raw and not raw.endswith('.jsonl'):
        root = Path(os.environ.get('RH_ROOT') or '~/.local/share/research-harness').expanduser()
        lane_dir = root / 'lanes' / raw
        if not lane_dir.is_dir():
            return None, 'no lane named {!r} under {} (pass a lane name or a RESULTS.jsonl path)'.format(raw, root / 'lanes')
        return lane_dir / 'RESULTS.jsonl', None
    path = Path(raw).expanduser()
    if path.suffix != '.jsonl':
        return None, '--ledger {!r} is not a .jsonl ledger'.format(raw)
    if not path.is_file() and not create and not (path.name == 'RESULTS.jsonl' and path.parent.is_dir()):
        return None, '--ledger {} does not exist; pass the lane name, or --new-ledger to start one'.format(path)
    return path, None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--ledger', required=True)
    p.add_argument('--new', required=True, choices=('yes', 'no'))
    p.add_argument('--kind', required=True, choices=KINDS)
    p.add_argument('--what', required=True)
    p.add_argument('--link', required=True, help='evidence: PR, DOI, claim dir or sent-mail id')
    p.add_argument('--referee', required=True, help='HOLDS, FAILS or NONE')
    p.add_argument('--utc', help='ISO time of the result (default now)')
    p.add_argument('--novelty', help='new-science, repro, bug or tightening (read from CLAIM.md when the link is a claim dir)')
    p.add_argument('--paper-date', help='YYYY-MM-DD of the source paper (read from CLAIM.md "Paper date:" when omitted)')
    p.add_argument('--verdict', help='the referee verdict text, or a file holding it; a passing '
                                     'verdict on a new result must answer the three rubric questions')
    p.add_argument('--new-ledger', action='store_true', help='allow --ledger to name a ledger that does not exist yet')
    a = p.parse_args(argv)
    ledger, err = resolve_ledger(a.ledger, a.new_ledger)
    if err:
        print('log_result: refused: ' + err, file=sys.stderr)
        return 2
    a.ledger = str(ledger)
    novelty, paper_date = a.novelty, a.paper_date
    link_dir = Path(a.link).expanduser()
    if result_gates is not None and link_dir.is_dir():
        found = result_gates.claim_fields(link_dir)
        novelty, paper_date = novelty or found[0], paper_date or found[1]
    if a.new == 'yes':
        errors = new_errors(a.kind, a.link)
        # 11-11, friends: a lane with RESULT_GATES.json counts only the novelty and paper window it names.
        if result_gates is not None:
            try:
                gates = result_gates.load(Path(a.ledger).expanduser().parent)
            except (OSError, ValueError) as exc:
                gates, errors = None, errors + ['RESULT_GATES.json unreadable: {}'.format(exc)]
            errors += result_gates.errors(gates, novelty, paper_date)
        # 11-06, BioBasicsBench failure modes: a referee pass only counts when the verdict says
        # what it checked. Scoped to --new yes AND a passing verdict, which is the row that leads
        # to something being sent; NONE and FAILS rows are untouched, so no lane's ordinary
        # logging changes.
        if verdict_rubric is not None and verdict_rubric.passing(a.referee):
            text = a.verdict or ''
            if text:
                candidate = Path(text).expanduser()
                try:
                    if candidate.is_file():
                        text = candidate.read_text(errors='replace')
                except OSError:
                    pass
            errors += verdict_rubric.findings(text or a.referee, a.referee)[0]
            if errors and not a.verdict:
                errors.append('pass the verdict with --verdict "<text>" or --verdict <file>. '
                              'The block to fill in:\n' + verdict_rubric.template())
        if errors:
            for e in errors:
                print('REFUSED: ' + e, file=sys.stderr)
            return 2
    row = dict(utc=a.utc or datetime.now(timezone.utc).isoformat(timespec='seconds'), new=a.new == 'yes',
               kind=a.kind, what=a.what, link=a.link, referee=a.referee)
    if a.verdict:
        row['verdict'] = a.verdict
    if novelty:
        row['novelty'] = novelty
    if paper_date:
        row['paper_date'] = paper_date
    path = Path(a.ledger).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(row) + '\n')
    print(json.dumps(row))
    print('log_result: logged to ' + str(path.resolve()), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
