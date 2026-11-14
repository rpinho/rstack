#!/usr/bin/env python3
"""state-lint: an open state.md item must not open with a status its own later text overturns.

WHY. state.md items are append-only in practice: when a status changes, the update is added at
the END of the bullet and the bold opening is left as it was. A grep lands on the opening, so one
answer quoted three dead statuses at once ("blocked on endorsement" for a paper endorsed and
submitted further along in the same bullet, "drafted, unsubmitted" for one already submitted).
The opening is what gets read, so the opening must carry the current status.

RULE. For an open item (`- [ ]`) or a plain sub-bullet (never `- [x]`), take its opening (the
first bold span, else the first 200 characters). If the opening states an unresolved status
(blocked, drafted, unsubmitted, opened, awaiting, pending, on hold...) and the REST of the same
item later records the resolving event (SUBMITTED, MERGED, ENDORSED, PUBLISHED, ACCEPTED,
UNBLOCKED, APPROVED, in capitals, the way status changes are written), the item is stale: rewrite
the opening, or prefix it "SUPERSEDED (<date>): <current status>.", or tick it `[x]`.

The same thing tracked in two items counts too: an identifier in a stale opening that ANOTHER item
records as resolved. Built-in identifiers are pull requests (`/pull/N`, and `#N` on a line that
says PR). Add your own (manuscript numbers, ticket ids) in a file named by --ids or
$KB_STATE_LINT_IDS, one `label<TAB>regex` per line with one capture group for the id.

USAGE
  python3 scripts/state-lint.py               # every open item in state.md (exit 1 on any)
  python3 scripts/state-lint.py --staged      # only items whose line is added in the staged diff
                                              # (the pre-commit mode: you touched it, fix its opening)
"""
import argparse
import os
import re
import subprocess
import sys

STATE = 'state.md'
OPEN_STATUS = re.compile(
    r'\b(blocked|drafted|draft (?:done|ready|saved)|unsubmitted|not submitted|not yet submitted|'
    r'pr opened|opened|awaiting|waiting (?:on|for)|pending|on hold)\b', re.I)
# Capitals only, so prose like "once it is submitted" does not count.
RESOLVED = re.compile(r'\b(SUBMITTED|RESUBMITTED|MERGED|ENDORSED|PUBLISHED|ACCEPTED|UNBLOCKED|APPROVED)\b')
OVERTURNS = {
    'blocked': {'ENDORSED', 'UNBLOCKED', 'SUBMITTED', 'RESUBMITTED', 'MERGED', 'PUBLISHED'},
    'drafted': {'SUBMITTED', 'RESUBMITTED', 'PUBLISHED'},
    'draft': {'SUBMITTED', 'RESUBMITTED', 'PUBLISHED'},
    'unsubmitted': {'SUBMITTED', 'RESUBMITTED'},
    'not submitted': {'SUBMITTED', 'RESUBMITTED'},
    'not yet submitted': {'SUBMITTED', 'RESUBMITTED'},
    'pr opened': {'MERGED'},
    'opened': {'MERGED'},
    'awaiting': {'ACCEPTED', 'PUBLISHED', 'APPROVED', 'MERGED', 'ENDORSED'},
    'waiting': {'ACCEPTED', 'PUBLISHED', 'APPROVED', 'MERGED', 'ENDORSED'},
    'pending': {'ACCEPTED', 'PUBLISHED', 'APPROVED', 'MERGED', 'ENDORSED'},
    'on hold': {'PUBLISHED', 'ACCEPTED'},
}
SUPERSEDED = re.compile(r'SUPERSEDED', re.I)
ITEM = re.compile(r'^(\s*)- (?!\[x\])(?:\[ \] )?(.*)$')


def opening(text):
    m = re.match(r'\s*(\*\*.*?\*\*)', text)
    return m.group(1) if m else text[:200]


def status_key(word):
    key = word.lower()
    return 'draft' if key.startswith('draft ') else 'waiting' if key.startswith('waiting') else key


def load_ids(path):
    """[(label, compiled)] from a `label<TAB>regex` file; [] when no file is named."""
    if not path:
        return []
    out = []
    with open(path, encoding='utf-8') as fh:   # a named file that cannot be read is an error
        for n, line in enumerate(fh, 1):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            label, sep, rx = line.rstrip('\n').partition('\t')
            if not sep:
                raise SystemExit('state-lint: {}:{}: expected label<TAB>regex'.format(path, n))
            out.append((label.strip(), re.compile(rx.strip())))
    return out


def ids_in(text, extra=()):
    keys = {'pr' + x for x in re.findall(r'/pull/(\d+)', text)}
    if re.search(r'\bPRs?\b', text):
        keys |= {'pr' + x for x in re.findall(r'#(\d{2,5})\b', text)}
    for label, rx in extra:
        keys |= {label + ':' + x for x in rx.findall(text)}
    return keys


def check(lines, only=None, extra=()):
    problems = []
    for n, line in enumerate(lines, 1):
        if only is not None and n not in only:
            continue
        m = ITEM.match(line)
        if not m:
            continue
        body = m.group(2)
        head = opening(body)
        if SUPERSEDED.search(head):
            continue
        rest = body[body.find(head) + len(head):]
        for o in OPEN_STATUS.finditer(head):
            hit = next((r.group(1) for r in RESOLVED.finditer(rest)
                        if r.group(1) in OVERTURNS.get(status_key(o.group(1)), ())), None)
            if hit:
                problems.append((n, o.group(1), hit, head[:140]))
                break
    return problems + check_elsewhere(lines, only, extra)


def check_elsewhere(lines, only=None, extra=()):
    resolved = {}
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith('- '):
            for k in ids_in(line, extra):
                for r in RESOLVED.finditer(line):
                    resolved.setdefault(k, set()).add((n, r.group(1)))
    problems = []
    for n, line in enumerate(lines, 1):
        if only is not None and n not in only:
            continue
        m = ITEM.match(line)
        if not m:
            continue
        head = opening(m.group(2))
        o = OPEN_STATUS.search(head)
        if SUPERSEDED.search(head) or not o:
            continue
        for k in ids_in(head, extra):
            hit = next(((ln, w) for ln, w in sorted(resolved.get(k, ()))
                        if ln != n and w in OVERTURNS.get(status_key(o.group(1)), ())), None)
            if hit:
                problems.append((n, o.group(1), '{} (state.md:{})'.format(hit[1], hit[0]), head[:140]))
                break
    return problems


def staged_lines():
    out = subprocess.run(['git', 'diff', '--cached', '-U0', '--', STATE], capture_output=True, text=True).stdout
    nums = set()
    for h in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', out, re.M):
        start, count = int(h.group(1)), int(h.group(2) or 1)
        nums.update(range(start, start + count))
    return nums


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--staged', action='store_true')
    ap.add_argument('--ids', default=os.environ.get('KB_STATE_LINT_IDS'))
    args = ap.parse_args(argv)
    extra = load_ids(args.ids)
    if args.staged:
        text = subprocess.run(['git', 'show', ':' + STATE], capture_output=True, text=True).stdout
        only = staged_lines()
    else:
        with open(STATE, encoding='utf-8') as fh:
            text = fh.read()
        only = None
    problems = check(text.split('\n'), only, extra)
    for n, was, now, head in problems:
        where = 'another item' if 'state.md:' in now else 'the same item later'
        print('state.md:{}: opens "{}" but {} says {}: {}'.format(n, was, where, now, head))
    if problems:
        print('{} stale opening(s). Rewrite the opening to the current status, or prefix it with '
              '"SUPERSEDED (<date>): <current status>." (tick [x] if the loop is closed).'.format(len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
