"""Synchronize release paths using the deploy application's own retention CLI."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile

from protected_paths import default_registry, protected_paths


def absolute(path):
    return Path(os.path.abspath(Path(path).expanduser()))


def release_entry(path, root):
    """Only this deployment's release subtree is owned by sync."""
    try:
        return len(absolute(path).relative_to(root / 'releases').parts) >= 2
    except ValueError:
        return False


def deploy_paths(root, retention_script=None, node='node'):
    root = absolute(root)
    # Import the actual function: the module's direct-entry guard fails through
    # the installed bin/current symlink. Do not copy its retention policy.
    script = absolute(retention_script) if retention_script else root / 'bin/release-retention.mjs'
    if not (root / 'deploy.json').is_file() or not script.is_file():
        raise ValueError('deploy.json and the deploy retention module are required')
    code = ("import {pathToFileURL} from 'node:url'; "
            "const {releaseProtection} = await import(pathToFileURL(process.argv[2]).href); "
            "console.log(JSON.stringify(releaseProtection(process.argv[1])));")
    # argv[1] is ROOT rather than the module, so importing a regular file cannot
    # accidentally trigger that module's standalone CLI either.
    result = subprocess.run([node, '--max-old-space-size=128', '--input-type=module',
                             '-e', code, str(root), str(script)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('deploy retention failed: ' + result.stderr.strip())
    data = json.loads(result.stdout)
    paths = data.get('paths') if isinstance(data, dict) else None
    if not isinstance(paths, list) or any(
            not isinstance(p, str) or not Path(p).is_absolute()
            or not release_entry(p, root) or len(Path(p).relative_to(root / 'releases').parts) != 2
            or str(absolute(p)) != p for p in paths):
        raise ValueError('invalid deploy protected paths')
    return set(paths)


def live_paths(root):
    """Read actual pointers independently of the retention result, including broken links."""
    paths = set()
    live = root / 'live'
    if live.exists():
        for link in live.iterdir():
            if link.is_symlink():
                target = absolute(link.parent / os.readlink(link))
                paths.update((str(target), str(link.resolve())))
    current = live / 'current.json'
    if current.exists():
        data = json.loads(current.read_text())
        if not isinstance(data, dict):
            raise ValueError('invalid live/current.json')
        for app, version in data.items():
            if app == 'updatedAt':
                continue
            if (not isinstance(version, str) or not version or '/' in version
                    or version in {'.', '..'} or '/' in app or app in {'.', '..'}):
                raise ValueError('invalid live/current.json release')
            paths.add(str(root / 'releases' / app / version))
    return paths


def documents(registry):
    """Validate with the disposal reader, then retain each source's non-release data."""
    protected_paths(registry, required=registry.exists())
    docs = {}

    def read(file):
        # Follow symlinks for writing too, preserving source/registry aliases.
        file = file.resolve()
        if file in docs:
            return
        data = json.loads(file.read_text()) if file.exists() else {'paths': []}
        docs[file] = data
        for source in data.get('sources', []):
            read(Path(source))

    read(registry)
    return docs


def plan(root, registry=None, retention_script=None, node='node'):
    root, registry = absolute(root), absolute(registry or default_registry())
    desired = deploy_paths(root, retention_script, node)
    live = live_paths(root)
    if live - desired:
        raise ValueError('refusing to drop/omit a currently live release: ' + ', '.join(sorted(live - desired)))
    docs = documents(registry)
    previous = {p for data in docs.values() for p in data.get('paths', []) if release_entry(p, root)}
    updated = {}
    for file, data in docs.items():
        paths = [p for p in data.get('paths', []) if not release_entry(p, root)
                 or (file != registry.resolve() and p in desired)]
        if file == registry.resolve():
            paths += sorted(desired)
        updated[file] = dict(data, paths=paths) if paths != data.get('paths', []) else data
    return dict(root=root, registry=registry.resolve(), desired=desired, live=live,
                docs=docs, updated=updated, add=sorted(desired - previous), remove=sorted(previous - desired))


def atomic_json(file, data):
    file.parent.mkdir(parents=True, exist_ok=True)
    mode = file.stat().st_mode & 0o777 if file.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix=file.name + '.', dir=file.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), mode)
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, file)
    finally:
        if os.path.exists(name):
            os.unlink(name)  # Only our own temporary file.


@contextmanager
def registry_lock(registry):
    registry = absolute(registry).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with open(str(registry) + '.sync.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def apply_plan(change):
    root, registry = change['root'], change['registry']
    # Add desired protections first. Source cleanup can then only leave excess
    # protection if interrupted, never a gap for the new live release.
    files = [registry] + [f for f in change['docs'] if f != registry]
    log = registry.with_name('release-protect-sync.jsonl')
    for file in files:
        before, after = change['docs'][file], change['updated'][file]
        if before == after:
            continue
        if live_paths(root) != change['live']:
            raise ValueError('live pointers changed during sync; retry under the deploy live lock')
        actual = json.loads(file.read_text()) if file.exists() else {'paths': []}
        if actual != before:
            raise ValueError('protected-path document changed during sync; retry')
        old, new = set(before.get('paths', [])), set(after.get('paths', []))
        # Log the intended file update before the atomic replacement, so a crash
        # cannot remove protection without leaving a record of the operation.
        with log.open('a') as stream:
            stream.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
                document=str(file), add=sorted(new - old), remove=sorted(old - new))) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        atomic_json(file, after)


def sync(root, registry=None, *, dry_run=False, retention_script=None, node='node'):
    def run():
        change = plan(root, registry, retention_script, node)
        diff = {key: change[key] for key in ('add', 'remove')}
        diff['documents'] = [dict(path=str(file),
            add=sorted(set(change['updated'][file].get('paths', [])) - set(data.get('paths', []))),
            remove=sorted(set(data.get('paths', [])) - set(change['updated'][file].get('paths', []))))
            for file, data in change['docs'].items() if data != change['updated'][file]]
        print(json.dumps(diff, indent=2))
        if not dry_run:
            apply_plan(change)
        return change
    if dry_run:
        return run()
    with registry_lock(registry or default_registry()):
        return run()


def health_problems(entries, now, state_file, *, write=True):
    """Alert after continuously observed drift >1h; equality resets its timer."""
    if not entries:
        return []
    state_file = Path(state_file)
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('invalid release-protection timer state')
    active, rows = {}, []
    for entry in entries:
        root = str(absolute(entry['deploy_root']))
        registry = str(absolute(entry.get('registry') or default_registry()))
        key = root + '\n' + registry
        try:
            change = plan(root, registry, entry.get('retention_script'), entry.get('node', 'node'))
            if not change['add'] and not change['remove']:
                continue
            detail = '{} missing, {} stale'.format(len(change['add']), len(change['remove']))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            # Unreadable sources are a problem, never an all-clear.
            detail = 'comparison unavailable: ' + str(exc)
        since = state.get(key, now)
        if isinstance(since, bool) or not isinstance(since, (int, float)) or not 0 <= since <= now:
            since = now
        active[key] = since
        if now - since > 3600:
            rows.append(('release-protection', root, 'drift for {:.0f} min: {}'.format((now - since) / 60, detail)))
    if write and active != state:
        atomic_json(state_file, active)
    return rows
