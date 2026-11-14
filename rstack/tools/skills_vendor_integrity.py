"""Shared, standard-library integrity checks. Never import installed skill code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re


MARKER = '.skills-vendor.json'


def vendor_hash(data):
    return hashlib.sha256(data).hexdigest()


def vendor_canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def vendor_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('invalid relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or value == '.':
        raise ValueError('unsafe relative path: ' + value)
    return path


def vendor_expected(manifest):
    if not isinstance(manifest, dict) or not isinstance(manifest.get('acceptance'), dict):
        raise ValueError('malformed manifest')
    if manifest.get('version') != 1 or manifest['acceptance'].get('state') != 'accepted':
        raise ValueError('manifest is not accepted')
    for key in ('commit', 'tree'):
        if not re.fullmatch('[0-9a-f]{40}', manifest.get(key, '')):
            raise ValueError('manifest needs a full ' + key)
    if not isinstance(manifest.get('repo'), str) or not manifest['repo']:
        raise ValueError('manifest needs a repository')
    expected = {}

    def add(target, source, digest):
        vendor_relative(target)
        vendor_relative(source)
        if target == MARKER or target in expected or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('duplicate, reserved or invalid manifest entry: ' + target)
        if any(target.startswith(p + '/') or p.startswith(target + '/') for p in expected):
            raise ValueError('manifest file/directory collision: ' + target)
        expected[target] = (source, digest)

    license = manifest['license']
    if license['spdx'] != 'MIT':
        raise ValueError('unsupported license')
    add('LICENSE', license['path'], license['sha256'])
    names = set()
    for skill in manifest['skills']:
        name = skill['name']
        if not re.fullmatch('[a-z0-9][a-z0-9_-]*', name) or name in names:
            raise ValueError('invalid or duplicate skill name')
        names.add(name)
        source = str(vendor_relative(skill['source']))
        if not skill['files'] or not any(f['path'] == 'SKILL.md' for f in skill['files']):
            raise ValueError('skill has no SKILL.md: ' + name)
        for entry in skill['files']:
            path = str(vendor_relative(entry['path']))
            add(name + '/' + path, source + '/' + path, entry['sha256'])
    return expected


def vendor_inventory(root):
    """Reject links (including parent links), special files and unreadable subtrees."""
    root = Path(root).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError('pack root is not a real directory')
    found = set()

    def fail(exc):
        raise exc

    for current, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in dirs + files:
            path = Path(current) / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError('link or special file: ' + str(path.relative_to(root)))
        found.update((Path(current) / f).relative_to(root).as_posix() for f in files)
    return found


def vendor_check(dest, manifest=None):
    dest = Path(dest)
    actual = vendor_inventory(dest)
    marker = json.loads((dest / MARKER).read_text(encoding='utf-8'))
    recorded = marker['manifest']
    if marker['manifest_sha256'] != vendor_hash(vendor_canonical(recorded)):
        raise ValueError('marker manifest digest mismatch')
    if manifest is not None and recorded != manifest:
        raise ValueError('installed manifest differs from supplied manifest')
    expected = vendor_expected(recorded)
    if actual != set(expected) | {MARKER}:
        raise ValueError('file set mismatch; missing={} extra={}'.format(
            sorted(set(expected) - actual), sorted(actual - set(expected) - {MARKER})))
    for target, (_, digest) in expected.items():
        if vendor_hash((dest / target).read_bytes()) != digest:
            raise ValueError('sha256 mismatch: ' + target)
    return recorded
