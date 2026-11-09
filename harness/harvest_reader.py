"""Read-only pod reader. Executed in memory by python3 -B, never installed on pods."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import subprocess
import sys

MAX_BYTES = 200_000_000
DEPENDENCY_DIRS = frozenset(('.lake', '.elan', '.cache'))
# Always pruned, before listing or hashing: installed environments and bytecode, rebuilt from the
# project's own lock files. On 11-03 the listing walked every file of every pod workspace's .venv
# (scipy's test .wav files logged one by one as skipped media) into a 22 MB controller log. A .git
# is not here: it can hold commits made on the pod and nowhere else.
ENVIRONMENT_DIRS = frozenset(('.venv', 'venv', 'site-packages', '__pycache__', 'node_modules'))
# 11-03: no '.ts' (TypeScript), and no host mimetypes guess (a pod's /etc/mime.types called a Snakemake
# .smk file video/x-smacker and the harvest skipped it). Extensions here are unambiguous; MPEG-TS is caught by magic.
MEDIA = frozenset('.mp3 .mp4 .m4a .m4v .wav .wave .avi .mov .mkv .webm .flac .ogg .oga .ogv .opus .aac .aiff .aif .wma .wmv .mpeg .mpg .3gp .mts .m2ts .mid .midi .amr .au'.split())


def valid(path):
    return (isinstance(path, str) and path.startswith('/workspace/')
            and str(PurePosixPath(path)) == path and '..' not in path.split('/')
            and not any(ord(c) < 32 for c in path))


def path_exclusions(roots, declarations):
    """Resolve explicit root-relative exclusions without filesystem inference."""
    if not isinstance(declarations, list):
        raise ValueError('harvest_exclude_paths must be a list')
    resolved = []
    for entry in declarations:
        if not isinstance(entry, dict):
            raise ValueError('harvest_exclude_paths entries must be objects')
        path = entry.get('path')
        if (not isinstance(path, str) or not path or path == '.'
                or PurePosixPath(path).is_absolute() or str(PurePosixPath(path)) != path
                or '..' in path.split('/') or any(c in path for c in '*?[]\\')
                or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            raise ValueError('harvest_exclude_paths path must be normalized, relative, without .. or globs')
        root = entry.get('root', roots[0] if len(roots) == 1 else None)
        if root not in roots:
            raise ValueError('harvest_exclude_paths root must select one declared results root')
        for key in ('reason', 'regenerate', 'approved_by', 'utc'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError('harvest_exclude_paths requires non-empty ' + key)
        try:
            utc = dt.datetime.fromisoformat(entry['utc'].replace('Z', '+00:00'))
            if utc.utcoffset() != dt.timedelta(0):
                raise ValueError('not UTC')
        except ValueError:
            raise ValueError('harvest_exclude_paths utc must be an ISO-8601 UTC timestamp') from None
        source = root + '/' + path
        if any(source == other['source'] or source.startswith(other['source'] + '/')
               or other['source'].startswith(source + '/') for other in resolved):
            raise ValueError('harvest_exclude_paths must not duplicate or overlap')
        resolved.append(dict(entry, root=root, source=source))
    return resolved


def excluded_path(path, exclusions):
    return next((entry for entry in exclusions
                 if path == entry['source'] or path.startswith(entry['source'] + '/')), None)


def exclusion_counts(path):
    """Count regular files using metadata only; never follow links or open payload."""
    try:
        fd = opened(path, directory=True)
    except FileNotFoundError:
        return dict(files=0, bytes=0, present=False)
    files = size = 0
    def failed(error):
        raise error
    try:
        for _, _, names, directory_fd in os.fwalk('.', dir_fd=fd, follow_symlinks=False, onerror=failed):
            for name in names:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    files += 1
                    size += info.st_size
    finally:
        os.close(fd)
    return dict(files=files, bytes=size, present=True)


def opened(path, directory=False):
    """No symlinks in any component; O_NONBLOCK prevents FIFO hangs."""
    if not valid(path):
        raise ValueError('path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        pieces = path.strip('/').split('/')
        for i, piece in enumerate(pieces):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if i < len(pieces) - 1 or directory:
                flags |= os.O_DIRECTORY
            nxt = os.open(piece, flags, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def media(path, head):
    return (PurePosixPath(path).suffix.lower() in MEDIA
            or len(head) >= 377 and head[0] == head[188] == head[376] == 0x47
            or head.startswith((b'fLaC', b'OggS', b'ID3', b'\x1aE\xdf\xa3'))
            or head[:4] == b'RIFF' and head[8:12] in (b'WAVE', b'AVI ')
            or head[4:8] == b'ftyp')


def inspect(path):
    fd = opened(path)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode):
            return dict(path=path, skip='special')
        if before.st_size > MAX_BYTES:
            return dict(path=path, skip='over_200_MB', size=before.st_size)
        head = f.read(512)
        if media(path, head):
            return dict(path=path, skip='media', size=before.st_size)
        digest = hashlib.sha256(head)
        size = len(head)
        while True:
            block = f.read(262144)
            if not block:
                break
            size += len(block)
            if size > MAX_BYTES:
                raise ValueError('growing')
            digest.update(block)
        after = os.fstat(f.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != after.st_size:
            raise ValueError('changed')
        return dict(path=path, size=size, sha256=digest.hexdigest())


def manifest(roots, excluded_dirs=(), excluded_paths=()):
    exclusions = path_exclusions(roots, list(excluded_paths))
    for root in roots:
        try:
            fd = opened(root, directory=True)
            os.close(fd)
            for entry in exclusions:
                if entry['root'] == root:
                    try:
                        yield dict(path=entry['source'], skip='excluded_path', **exclusion_counts(entry['source']))
                    except (OSError, ValueError):
                        yield dict(path=entry['source'], error='exclusion_count_failed')
            # fwalk with follow_symlinks=False; inspect also guards every parent.
            def failed(error):
                raise error
            for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
                for name in sorted(dirs + files):
                    path = directory + '/' + name
                    if excluded_path(path, exclusions):
                        if name in dirs:
                            dirs.remove(name)
                        continue
                    if not valid(path):
                        if name in dirs:
                            dirs.remove(name)
                        yield dict(path=path, skip='invalid_remote_path')
                        continue
                    try:
                        info = os.lstat(path)
                    except OSError:
                        yield dict(path=path, skip='unreadable_file', detail='lstat_failed')
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        if name in dirs:
                            dirs.remove(name)
                        yield dict(path=path, skip='symlink')
                    elif name in dirs and (name in excluded_dirs or name in ENVIRONMENT_DIRS):
                        dirs.remove(name)
                        yield dict(path=path, skip='excluded_dependency_directory')
                    elif name in files:
                        try:
                            yield inspect(path)
                        except OSError:
                            yield dict(path=path, skip='unreadable_file', detail='inspect_failed')
                        except ValueError as error:
                            reason = 'invalid_remote_path' if str(error) == 'path' else 'changed_during_harvest'
                            yield dict(path=path, skip=reason, detail='inspect_failed')
        except (OSError, ValueError):
            yield dict(path=root, error='results_path_unavailable')


def deadline_seconds():
    """Only sleep processes, never start-command credentials or environment."""
    try:
        out = subprocess.run(['ps', '-C', 'sleep', '-o', 'etimes=,ppid=,args='],
                             capture_output=True, text=True, timeout=5).stdout
        remaining = []
        for line in out.splitlines():
            m = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+(?:/\S*/)?sleep\s+(\d+)\s*', line)
            if m and int(m[2]) != 1 and int(m[3]) >= 3600:
                left = int(m[3]) - int(m[1])
                if left > 0:
                    remaining.append(left)
        return min(remaining) if remaining else None
    except (OSError, subprocess.SubprocessError):
        return None


def serve(token, roots, excluded_dirs=(), excluded_paths=()):
    exclusions = path_exclusions(roots, list(excluded_paths))
    def emit(row):
        print('\n' + token + base64.b64encode(json.dumps(row).encode()).decode(), flush=True)
    emit(dict(ready=True))
    pending = []
    for line in sys.stdin:
        operation = None
        detail = None
        try:
            encoded = line.strip()
            if encoded.startswith('+'):
                pending.append(encoded[1:])
                if sum(map(len, pending)) > 65536:
                    raise ValueError('request limit')
                emit(dict(request_chunk=True))
                continue
            if encoded == '.':
                encoded = ''.join(pending)
                pending = []
            request = json.loads(base64.b64decode(encoded))
            operation = request.get('op')
            if request['op'] in ('manifest', 'next'):
                first = request['op'] == 'manifest'
                if first:
                    inventory = iter(manifest(roots, excluded_dirs, excluded_paths))
                exhausted = False
                for _ in range(16):
                    try:
                        emit(next(inventory))
                    except StopIteration:
                        exhausted = True
                        break
                response = dict(end=True, more=not exhausted)
                if first:
                    response['deadline_seconds'] = deadline_seconds()
                emit(response)
            elif request['op'] == 'get':
                path = request['path']
                if not any(path.startswith(root + '/') for root in roots):
                    raise ValueError('outside roots')
                if excluded_path(path, exclusions):
                    raise ValueError('excluded path')
                detail = 'inspect_failed'
                expected = inspect(path)
                if expected != dict(path=path, size=request['size'], sha256=request['sha256']):
                    detail = 'manifest_hash_changed'
                    raise ValueError('changed')
                detail = 'stream_hash_changed'
                with os.fdopen(opened(path), 'rb') as f:
                    digest, size = hashlib.sha256(), 0
                    while True:
                        block = f.read(49152)
                        if not block:
                            break
                        size += len(block)
                        if size > MAX_BYTES:
                            raise ValueError('size')
                        digest.update(block)
                        emit(dict(data=base64.b64encode(block).decode()))
                    if size != expected['size'] or digest.hexdigest() != expected['sha256']:
                        raise ValueError('changed')
                emit(dict(end=True, size=size, sha256=digest.hexdigest()))
            elif request['op'] == 'quit':
                return
            else:
                raise ValueError('operation')
        except (OSError, ValueError, KeyError, TypeError) as error:
            response = dict(end=True, error='remote_read_failed')
            # Protocol/root errors remain fatal. Only failures while reading a
            # declared file are safe, explicitly recorded exclusions.
            if operation == 'get' and detail:
                if isinstance(error, OSError):
                    response.update(skip='unreadable_file', detail=detail)
                elif isinstance(error, ValueError) and str(error) in ('changed', 'growing', 'size', 'path'):
                    response.update(skip='invalid_remote_path' if str(error) == 'path' else 'changed_during_harvest', detail=detail)
            emit(response)
