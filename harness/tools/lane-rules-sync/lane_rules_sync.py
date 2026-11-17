#!/usr/bin/env python3
"""lane-rules-sync: put the shared lane rules into every lane's RULES.md, from one source.

Each lane used to hand-write its own RULES.md. The 11-04 hard rule reached the harness README and
the Codex front file but none of the lane rules, and an 11-05 fix pasted into one lane's file made
the drift worse. That is the same failure as a hand-installed release copy: one source of truth,
or every copy ages differently.

harness/LANE_RULES_COMMON.md is the source. This writes it into each lanes/*/RULES.md between its
markers, leaves the rest of the file alone, and is safe to re-run. --check changes nothing and
exits 2 when any lane is out of date, so a scheduled job can notice instead of a person.
"""
import argparse, difflib, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lane_paths import lane_dirs

START = '<!-- lane-rules-common:'
END = '<!-- /lane-rules-common -->'
BLOCK = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)


def source(repo):
    return (Path(repo) / 'harness/LANE_RULES_COMMON.md').read_text().strip()


def apply(text, common):
    """Replace the marked block, or insert it under the file's first heading."""
    if BLOCK.search(text):
        return BLOCK.sub(lambda _: common, text, count=1)
    lines = text.splitlines(keepends=True)
    at = 1 if lines and lines[0].startswith('#') else 0
    return ''.join(lines[:at]) + ('\n' if at else '') + common + '\n\n' + ''.join(lines[at:])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', default='~/.local/share/research-harness', help='deployed harness root')
    p.add_argument('--repo', default=str(Path(__file__).resolve().parents[3]), help='source repo')
    p.add_argument('--check', action='store_true', help='report drift, change nothing; exit 2 if any')
    a = p.parse_args(argv)
    common = source(a.repo)
    root = Path(os.path.expanduser(a.root))
    stale = 0
    for lane in lane_dirs(root):
        rules = lane / 'RULES.md'
        existed = rules.is_file()
        # A lane with no rules file gets no rules at all, which is the drift this tool exists to stop.
        old = rules.read_text() if existed else '# ' + lane.name + ' lane rules\n'
        new = apply(old, common)
        if existed and old == new:
            print('ok      ' + lane.name)
            continue
        stale += 1
        if a.check:
            print(('MISSING ' if not existed else 'STALE   ') + lane.name)
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                       'current', 'expected', n=0))
        else:
            if existed:
                lane.joinpath('RULES.md.bak-lane-rules-sync').write_text(old)
            rules.write_text(new)
            print(('created ' if not existed else 'updated ') + lane.name)
    if not stale:
        print('all lanes carry the current shared rules')
    return 2 if (stale and a.check) else 0


if __name__ == '__main__':
    raise SystemExit(main())
