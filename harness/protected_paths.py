"""Refuse disposal of registered paths, their contents and their ancestors.

A private JSON document has {"paths": [...], "sources": [absolute JSON paths]}.
Sources are reread on each disposal so a release switch updates protection without
reinstalling tools. No application-specific paths or identities live in source.
"""
import json
import os
from pathlib import Path


def default_registry():
    return Path(os.environ.get('RSTACK_PROTECTED_PATHS',
                Path.home() / '.local/state/rstack/protected-paths.json'))


def protected_paths(registry=None, *, required=False, seen=None):
    registry = Path(registry or default_registry()).expanduser().absolute()
    seen = set() if seen is None else seen
    if registry in seen:
        raise ValueError('protected-path source cycle')
    seen = seen | {registry}
    if not registry.exists() and not required:
        return set()
    data = json.loads(registry.read_text())
    if not isinstance(data, dict) or set(data) - {'paths', 'sources', 'schema'}:
        raise ValueError('invalid protected-path document')
    paths, sources = data.get('paths', []), data.get('sources', [])
    if not isinstance(paths, list) or not isinstance(sources, list):
        raise ValueError('protected paths and sources must be arrays')
    if any(not isinstance(p, str) or not Path(p).is_absolute() for p in paths + sources):
        raise ValueError('protected paths and sources must be absolute')
    out = {registry, registry.resolve()} if paths or sources else set()
    for p in paths:
        out.update((Path(p).absolute(), Path(p).resolve()))
    for source in sources:
        out.update(protected_paths(source, required=True, seen=seen))
    return out


def assert_disposable(paths, registry=None, *, required=False):
    protected = protected_paths(registry, required=required)
    for raw in paths:
        for candidate in {Path(raw).expanduser().absolute(), Path(raw).expanduser().resolve()}:
            for keep in protected:
                if candidate == keep or candidate in keep.parents or keep in candidate.parents:
                    raise ValueError('cleanup refused: path overlaps a protected release')


def assert_shell_disposable(command, registry=None):
    """Cover ordinary explicit trash/rm commands at the existing shell hook boundary."""
    import glob
    import shlex
    protected = protected_paths(registry)
    if not protected:
        return
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|')
    lexer.whitespace_split = True
    segments, current = [], []
    for token in lexer:
        if token and all(c in ';&|' for c in token):
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    for segment in segments:
        start = next((i for i, t in enumerate(segment) if Path(t).name in
                      {'trash', 'rm', 'rmdir', 'unlink'}), None)
        if start is None:
            continue
        for token in segment[start + 1:]:
            if token.startswith('-'):
                continue
            expanded = os.path.expandvars(os.path.expanduser(token))
            if '$' in expanded or '`' in expanded:
                raise ValueError('cleanup refused: cannot resolve a deletion operand with protected releases registered')
            candidates = glob.glob(expanded) if glob.has_magic(expanded) else [expanded]
            if not candidates:
                candidates = [expanded.split('*', 1)[0].split('?', 1)[0].split('[', 1)[0]]
            assert_disposable(candidates, registry)
