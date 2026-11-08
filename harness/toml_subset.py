"""The TOML subset the harness reads (stdlib only, no other harness imports).

Its own module so the X posting hook can read a lane's OUTREACH.toml without importing rh, which
pulls in the network modules. rh re-exports both names.
"""
import ast
import json


def config(path):
    """Use tomllib when available; 3.9 fallback accepts documented config subset.

    Strings, numbers, booleans, arrays and [[banned_patterns]] are supported.
    Unsupported syntax fails explicitly instead of silently changing rules.
    """
    try:
        import tomllib
    except ImportError:
        tomllib = None
    if tomllib:
        return tomllib.loads(path.read_text())
    result, current, pending = {}, None, ''
    current = result
    for line in path.read_text().splitlines():
        # Strip comments only outside quoted strings.
        quote, escaped, clean = '', False, ''
        for c in line:
            if escaped:
                escaped = False
            elif c == '\\' and quote == '"':
                escaped = True
            elif quote and c == quote:
                quote = ''
            elif not quote and c in "\"'":
                quote = c
            elif not quote and c == '#':
                break
            clean += c
        pending += clean.strip() + ' '
        s = pending.strip()
        if not s:
            pending = ''
            continue
        if s == '[[banned_patterns]]':
            current = {}
            result.setdefault('banned_patterns', []).append(current)
            pending = ''
            continue
        if '=' not in s:
            raise ValueError('unsupported INTAKE.toml syntax: ' + s)
        key, value = map(str.strip, s.split('=', 1))
        try:
            parsed = config_value(value)
        except (ValueError, SyntaxError):
            if value.startswith('[') and not value.endswith(']'):
                continue
            raise ValueError('unsupported INTAKE.toml value: ' + value)
        if key in current:
            raise ValueError('duplicate TOML key: ' + key)
        current[key] = parsed
        pending = ''
    if pending.strip():
        raise ValueError('unfinished INTAKE.toml value')
    return result


def config_value(value):
    if value in ('true', 'false'):
        return value == 'true'
    tree = ast.parse(value, mode='eval')

    def decode(node):
        if isinstance(node, ast.List):
            return [decode(item) for item in node.elts]
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                raw = ast.get_source_segment(value, node)
                if raw.startswith("'") and not raw.startswith("'" * 3):
                    # TOML literal strings preserve regex backslashes verbatim.
                    return raw[1:-1]
                if raw.startswith('"') and not raw.startswith('"' * 3):
                    return json.loads(raw)
            if type(node.value) in (int, float):
                return node.value
        raise ValueError('unsupported TOML value: ' + value)

    return decode(tree.body)
