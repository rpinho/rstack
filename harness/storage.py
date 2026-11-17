"""Reversible disposal for alerts and superseded snapshots. No destructive fallback."""
import os
from pathlib import Path
import subprocess
import settings
from protected_paths import assert_disposable

# A flat 30 seconds was too thin a ceiling. On a quiet machine this is a rename and the
# size does not matter: 58,464 entries moved in 0.44 s when measured. But six disposals of
# one friends/fz67 snapshot hit the 30 s timeout on 11-04, on a volume at 92% capacity with
# tens of GB already in the Trash, and each killed move left the snapshot on disk and the
# harvest that had copied and verified it recorded as a failure. The condition is not
# reproduced, so the ceiling now simply scales with the tree rather than pretending to know
# the cost per file. It bounds a hang, not a wait, so it is generous; counting stops once
# the ceiling is reached, because a larger tree gets the ceiling either way.
TIMEOUT_FLOOR = 60
TIMEOUT_PER_ENTRY = 0.2
TIMEOUT_CEILING = 1800
COUNT_LIMIT = int((TIMEOUT_CEILING - TIMEOUT_FLOOR) / TIMEOUT_PER_ENTRY)


def entries(path):
    """How many items a Trash move has to move, counted no further than it matters."""
    total = 1
    for _, dirs, files in os.walk(str(path), followlinks=False):
        total += len(dirs) + len(files)
        if total >= COUNT_LIMIT:
            return COUNT_LIMIT
    return total


def timeout(path):
    return min(TIMEOUT_CEILING, TIMEOUT_FLOOR + TIMEOUT_PER_ENTRY * entries(path))


def trash(path):
    path = Path(path).absolute()
    assert_disposable([path])
    if path.exists() or path.is_symlink():
        subprocess.run([*settings.command('RH_TRASH_COMMAND', '/usr/bin/trash'), str(path)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout(path))
