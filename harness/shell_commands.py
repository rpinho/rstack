"""Small shell command reader shared by the model and deletion hooks.

This identifies ordinary executable argv, not a general shell sandbox. Heredoc
bodies are text; an unfinished quote uses the model gate's conservative fallback.
"""
import re
import shlex


def shell_commands(command):
    """Command argv plus input from its immediate pipeline, without heredoc bodies."""
    lines, delimiter = [], None
    for line in command.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        lines.append(line)
        here = re.search(r'<<-?\s*[\"\x27]?(\w+)[\"\x27]?', line)
        if here:
            delimiter = here.group(1)
    lexer = shlex.shlex('\n'.join(lines), posix=True, punctuation_chars=';&|()\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        # An unfinished quote must still expose a pinned launch, not brick Bash.
        tokens = re.findall(r'[;&|()\n]+|[^\s;&|()]+', '\n'.join(lines))
    segment, piped = [], ''
    for token in tokens + [';']:
        if token and all(c in ';&|()\n' for c in token):
            if segment:
                yield segment, piped
            piped = ' '.join(segment[1:]) if token == '|' else ''
            segment = []
        else:
            segment.append(token)


def command_argv(args):
    i = 0
    while i < len(args) and (args[i] in ('env', 'command', 'exec', 'sudo')
                            or re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', args[i])):
        i += 1
    return args[i:]
