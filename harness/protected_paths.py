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


def deletion_commands(command, _depth=0):
    """Yield executed cleanup argv, never words in echo arguments or heredocs."""
    import shlex
    import re
    from shell_commands import shell_commands

    if _depth > 16:
        raise ValueError('cleanup command nesting is too deep')
    for args, _ in shell_commands(command):
        while args and args[0] in {'do', 'then', 'else', 'if', 'while', 'until', '!', '{'}:
            args = args[1:]
        # Wrappers execute their following command; their option values do not.
        argv = args
        while argv:
            name = Path(argv[0]).name
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', argv[0]):
                argv = argv[1:]
            elif name in {'env', 'command', 'exec', 'sudo', 'nohup', 'xargs'}:
                value_options = {'env': {'-u', '--unset', '-C', '--chdir'},
                                 'sudo': {'-u', '-g', '-h', '-p', '-C', '-T', '-R', '-D'},
                                 'exec': {'-a'},
                                 'xargs': {'-E', '-I', '-J', '-L', '-n', '-P', '-s', '-a'}}.get(name, set())
                argv = argv[1:]
                while argv and argv[0].startswith('-'):
                    option = argv[0]
                    argv = argv[2:] if option in value_options else argv[1:]
                    if option == '--':
                        break
            else:
                break
        if not argv:
            continue
        name = Path(argv[0]).name
        script = None
        if name in {'sh', 'bash', 'zsh', 'dash', 'ksh'}:
            for i, arg in enumerate(argv[1:], 1):
                if arg.startswith('-') and not arg.startswith('--') and 'c' in arg:
                    script = argv[i + 1] if i + 1 < len(argv) else ''
                    break
        elif name == 'ssh':
            i = 1
            while i < len(argv) and argv[i].startswith('-'):
                i += 2 if argv[i] in {'-b', '-c', '-D', '-E', '-e', '-F', '-I', '-i', '-J',
                                     '-L', '-l', '-m', '-O', '-o', '-p', '-Q', '-R', '-S', '-W', '-w'} else 1
            script = ' '.join(argv[i + 1:])  # ssh hands the command to the remote shell
        elif name == 'eval':
            script = ' '.join(argv[1:])
        elif name == 'find':
            for i, arg in enumerate(argv):
                if arg in {'-exec', '-execdir', '-ok', '-okdir'}:
                    script = shlex.join(argv[i + 1:])
                    break
        if script is not None:
            yield from deletion_commands(script, _depth + 1)
        elif name in {'trash', 'rm', 'rmdir', 'unlink', 'osascript'}:
            yield argv
        elif name == 'mv' and len(argv) > 2:
            destination = Path(os.path.expandvars(os.path.expanduser(argv[-1])))
            if {'.Trash', '.Trashes', 'Trash'}.intersection(destination.parts):
                yield argv


def assert_shell_disposable(command, registry=None):
    """Check real cleanup operands using the model gate's shell reader/fallback."""
    import glob
    commands = [argv for argv in deletion_commands(command) if Path(argv[0]).name != 'osascript']
    if not commands or not protected_paths(registry):
        return
    for argv in commands:
        for token in argv[1:]:
            if token.startswith('-'):
                continue
            # The unfinished-quote fallback retains quote marks. Check that path
            # too, rather than letting an open quote hide a protected operand.
            for operand in {token, token.strip('\"\x27')}:
                expanded = os.path.expandvars(os.path.expanduser(operand))
                if '$' in expanded or '`' in expanded:
                    raise ValueError('cleanup refused: cannot resolve a deletion operand with protected releases registered')
                candidates = glob.glob(expanded) if glob.has_magic(expanded) else [expanded]
                if not candidates:
                    candidates = [expanded.split('*', 1)[0].split('?', 1)[0].split('[', 1)[0]]
                assert_disposable(candidates, registry)
