#!/usr/bin/python3
"""launchd entrypoint: skip absent lanes, continue after individual failures."""
import settings  # loads the host env file before RH_ROOT is read
from pathlib import Path
import os
import subprocess
import sys
from lane_paths import lane_dirs, resolve_lane

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('RH_ROOT', str(CODE))).expanduser()



def lanes():
    """RH_INTAKE_LANES (comma-separated, run in that order) pins the set; otherwise every
    lane that declares an INTAKE.toml, alphabetically. Outreach-only lanes have none."""
    pinned = [n.strip() for n in os.environ.get('RH_INTAKE_LANES', '').split(',') if n.strip()]
    names = []
    if pinned:
        for name in pinned:
            path = ROOT / 'lanes' / name
            if path.is_symlink() or path.is_dir():
                try:
                    names.append(resolve_lane(ROOT, name))
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
    else:
        names = [lane.name for lane in lane_dirs(ROOT)]
    return [n for n in dict.fromkeys(names) if (ROOT / 'lanes' / n / 'INTAKE.toml').is_file()]


def main():
    failed = False
    for lane in lanes():
        result = subprocess.run(['/usr/bin/nice', '-n', '19', sys.executable,
                                 str(CODE / 'rh.py'), '--root', str(ROOT), 'intake', lane, '--live'])
        failed |= result.returncode != 0
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
