#!/usr/bin/env python3
"""Count the job-specific words in a spec, for the goal-drift word caps.

Why (2026-11-06): the cap exists so the goal cannot turn into process -- a spec that grows
layered rules is how the friends lane's goal drifted. It was counting the wrong words. The
sweep writes its generated specs with the lane's whole RULES.md and INTAKE.toml embedded
verbatim, plus a shared-lessons block, so c5's `0-search` spec came to 3,047 words of which
only 472 were the actual ask. launch.sh refused it at the 1,000-word cap, and the lane's
generated jobs could not run at all. Lane rules grow over time, so this gets worse on its own;
the no-ops rule added to LANE_RULES_COMMON.md earlier the same day put another ~130 words into
every lane's RULES.md and therefore into every generated spec.

So the cap measures what somebody actually asked for, and not what the harness injected around
it. Blocks that the harness itself wrote into the spec are excluded:

  --- BEGIN VERBATIM LANE POLICY: <path> ---  ...  --- END VERBATIM LANE POLICY ---
  ## Shared lessons                           ...  up to the next heading
  <label>: ["<id>", "<id>", ...]              a generated worklist of ids, on one line

That last one, added 2026-11-06 after the first fix did not go far enough: friends' `0-read` and
`1-read` were still refused at 1,172 and 1,199 words, and 771 of those were a single line listing
762 queue ids for the worker to read. The cap exists so the GOAL cannot turn into process. A list
of the rows to work on is the goal; counting it means a lane is refused for having a long queue,
which is the opposite of what the rule wants. Only a line whose value parses as a JSON array of
plain strings is excluded, so prose cannot hide inside the brackets to buy room.

Shared material added to the *prompt* rather than the spec -- the prior-art block, GOAL.md,
`rh lessons for LANE` -- is appended after this check runs and is never counted.

Unbalanced markers count everything, so a malformed spec gets the strict budget rather than an
unlimited one. These markers are written by the harness's own sweep; a hand-written spec that
pastes them in to buy itself room is circumventing a hard rule, which is not what this guards.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# The compiler-failures block is the sweep's own output on a repair pass (planets, 11-08: it pushed a
# 998-word first-pass spec to 1,094 and the repair pass was refused, so no repair could ever run).
BEGIN = re.compile(r'^---\s*BEGIN (?:VERBATIM LANE POLICY|HARNESS COMPILER FAILURES)\b.*---\s*$')
END = re.compile(r'^---\s*END (?:VERBATIM LANE POLICY|HARNESS COMPILER FAILURES)\s*---\s*$')
LESSONS = re.compile(r'^##\s+Shared lessons\s*$')
HEADING = re.compile(r'^#{1,6}\s+\S')
MANIFEST = re.compile(r'^[^:\[\]]{1,80}:\s*(\[.*\])\s*$')


def id_manifest(line):
    """Is this line a generated worklist, `label: ["id", "id", ...]`?

    Strict on purpose: the value has to parse as a JSON array of plain strings, each short and
    without spaces. That admits the sweep's queue-id lists and refuses a paragraph of rules
    wrapped in brackets to dodge the cap.
    """
    m = MANIFEST.match(line)
    if not m:
        return False
    try:
        value = json.loads(m.group(1))
    except ValueError:
        return False
    return (isinstance(value, list) and len(value) > 1
            and all(isinstance(v, str) and 0 < len(v) <= 64 and ' ' not in v for v in value))


def job_specific(text):
    """The spec text with harness-injected blocks removed."""
    if sum(bool(BEGIN.match(l)) for l in text.splitlines()) != \
       sum(bool(END.match(l)) for l in text.splitlines()):
        return text  # unbalanced: fail closed, count the whole file
    kept, in_policy, in_lessons = [], False, False
    for line in text.splitlines():
        if BEGIN.match(line):
            in_policy = True
            continue
        if END.match(line):
            in_policy = False
            continue
        if in_policy:
            continue
        if LESSONS.match(line):
            in_lessons = True
            continue
        if in_lessons:
            # The lessons block runs to the next heading of any level.
            if HEADING.match(line):
                in_lessons = False
            else:
                continue
        if id_manifest(line):
            continue
        kept.append(line)
    return '\n'.join(kept)


def count(path):
    text = Path(path).read_text(errors='replace')
    return len(job_specific(text).split())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('spec', type=Path)
    a = p.parse_args(argv)
    try:
        print(count(a.spec))
    except OSError as e:
        print('spec unreadable: {}'.format(e), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
