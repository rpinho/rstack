"""Canonical lane names and enumeration; directory symlinks are aliases."""
from pathlib import Path
import re
import sys


def resolve_lane(root, name, *, must_exist=True):
    """Return the canonical name of an existing lane under root/lanes.

    Alias chains are allowed, but must end at a direct child of this lanes root.
    Broken links and loops are ordinary command errors, not tracebacks.
    must_exist=False also accepts historical labels whose directories are gone.
    """
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name):
        raise ValueError('invalid lane name')
    base = Path(root).expanduser() / 'lanes'
    lane = base / name
    if lane.is_symlink():
        try:
            target = lane.resolve(strict=True)
        except FileNotFoundError:
            raise ValueError('dangling lane alias: ' + str(lane)) from None
        except (OSError, RuntimeError) as exc:
            raise ValueError('invalid lane alias {}: {}'.format(lane, exc)) from None
        if target.parent != base.resolve() or not target.is_dir():
            raise ValueError('lane alias must target a lane directory in {}: {}'.format(base, lane))
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', target.name):
            raise ValueError('invalid lane name: ' + target.name)
        return target.name
    if must_exist and not lane.is_dir():
        raise ValueError('lane directory missing: ' + str(lane))
    return name


def lane_dirs(root):
    """Yield real lane directories once, sorted; report unusable aliases to stderr."""
    base = Path(root).expanduser() / 'lanes'
    if not base.is_dir():
        return
    for lane in sorted(base.iterdir()):
        if lane.is_symlink():
            try:
                resolve_lane(root, lane.name)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
        elif lane.is_dir():
            yield lane
