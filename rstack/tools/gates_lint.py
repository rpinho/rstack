#!/usr/bin/env python3
"""gates-lint: every gate in the code has a class in rstack/gates.json (RULE #1, 11-20).

FAILs when:
  * a file under the scanned trees refuses something (deny JSON, a Stop block, REFUSED/refused, exit 2/75/78)
    and is neither a registered gate's file nor in `exempt` with a reason;
  * a gate name used at a call site (`_hookfail.run('NAME'`, `harness_blocks.gate('NAME'`, `_gate('NAME'`,
    `refuses NAME` in launch.sh, the round gate's names) is not in the registry;
  * an entry has no class, a class other than hard-line/fail-open, a hard line outside the six reasons
    (or `pending` without a recommendation), a hard line with no `fix`, or a file that does not exist;
  * a fail-open entry wired as a hook has no probe (tests/test_fail_open_gates.py feeds every probe).

  gates_lint.py [--repo DIR]     exit 0 PASS, 1 FAIL (one line per finding)
"""
import argparse
import json
from pathlib import Path
import re
import sys

HARD_LINES = ('money', 'credentials', 'send-as-ricardo', 'permanent-delete', 'egress', 'third-party-code')
SIGNATURE = re.compile(r"permissionDecision|['\"]deny['\"]|['\"]decision['\"]:\s*['\"]block|REFUSED|refused|"
                       r"refuses|sys\.exit\((?:2|75|78)\)|\bexit 7[58]\b|return (?:REFUSED|7[58])\b")
NAMES = (re.compile(r"_hookfail\.run\(\s*'([\w.-]+)'"), re.compile(r"harness_blocks\.gate\(\s*'([\w.-]+)'"),
         re.compile(r"\b_gate\(\s*'([a-z][\w.-]+)'"), re.compile(r"\brefuses (launch\.[\w-]+)"),
         re.compile(r"'(rounds\.[a-z-]+)'"))
TREES = ('rstack/hooks', 'rstack/tools', 'tools', 'harness', 'kb/.claude/hooks')
SKIP = ('/tests/', '/__pycache__/', '/vendor/', '/fixtures/', '/templates/', '/docs/', '/pod/')


def code_files(repo):
    for tree in TREES:
        for path in sorted((repo / tree).rglob('*')):
            rel = path.relative_to(repo).as_posix()
            if not path.is_file() or any(s in '/' + rel for s in SKIP) or path.name.startswith('test_'):
                continue
            if path.suffix in ('.py', '.sh') or (not path.suffix and path.read_bytes()[:2] == b'#!'):
                yield rel, path


def lint(repo):
    repo = Path(repo)
    problems = []
    try:
        reg = json.loads((repo / 'rstack/gates.json').read_text())
    except (OSError, ValueError) as exc:
        return ['rstack/gates.json unreadable: {}'.format(exc)]
    gates = reg.get('gates', [])
    exempt = reg.get('exempt', {})
    names, covered = set(), set()
    for row in gates:
        name = row.get('gate', '?')
        if name in names:
            problems.append('{}: registered twice'.format(name))
        names.add(name)
        cls = row.get('class')
        if cls not in ('hard-line', 'fail-open'):
            problems.append('{}: class must be hard-line or fail-open, got {!r}'.format(name, cls))
        if cls == 'hard-line':
            why = row.get('hard_line')
            if why == 'pending':
                if not row.get('pending'):
                    problems.append('{}: pending needs a recommendation for general'.format(name))
            elif why not in HARD_LINES:
                problems.append('{}: a hard line must be one of {} (or pending), got {!r}'.format(
                    name, ', '.join(HARD_LINES), why))
            if not row.get('fix'):
                problems.append('{}: a refusing gate must name its fix (`fix`)'.format(name))
        if cls == 'fail-open' and row.get('kind') == 'hook' and not row.get('probe') \
                and not all(f.startswith('~') for f in row.get('files', [])):
            problems.append('{}: a fail-open hook needs a probe'.format(name))
        for f in row.get('files', []):
            if f.startswith('~'):
                continue
            if not (repo / f).is_file():
                problems.append('{}: file {} does not exist'.format(name, f))
            covered.add(f)
    for f in exempt:
        if not (repo / f).is_file():
            problems.append('exempt file {} does not exist'.format(f))
    for rel, path in code_files(repo):
        text = path.read_text(errors='replace')
        if SIGNATURE.search(text) and rel not in covered and rel not in exempt:
            problems.append('{}: refuses something but has no class in rstack/gates.json '
                            '(register it, or exempt it with a reason)'.format(rel))
        for pattern in (NAMES if rel != 'rstack/tools/gates_lint.py' else ()):
            for used in pattern.findall(text):
                if used not in names and not used.startswith(('my-', 'probe')):
                    problems.append('{}: gate {!r} is used here but not registered'.format(rel, used))
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--repo', default=str(Path(__file__).resolve().parents[2]))
    a = p.parse_args(argv)
    problems = lint(a.repo)
    for line in problems:
        print('FAIL ' + line)
    print('gates-lint: {}'.format('PASS' if not problems else 'FAIL ({})'.format(len(problems))))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
