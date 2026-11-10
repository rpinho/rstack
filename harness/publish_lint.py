"""Publication checks and short-lived, content-bound receipts. Standard library only.

Never executes packet code. Git object reads use the pinned tree. See
docs/publish-checks.md for the manifests and the limits of static checks.
"""
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote

import settings

CHECKS = ('claims', 'credit', 'paths', 'selfref', 'voice', 'rigor', 'replay')
VERSION = 2  # 11-04: blocking vs advisory findings; only blocking ones gate
TTL = 3600
# Voice linter for the owner's prose (reads text on stdin, nonzero exit = finding).
XLINT = settings.path('RH_XLINT', Path('.runtime/xlint.py'))
# 11-04: Python 3.9 (the rh interpreter) lacks sys.stdlib_module_names; embed the 3.12 list.
STDLIB_312 = ['abc', 'aifc', 'antigravity', 'argparse', 'array', 'ast', 'asyncio', 'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'bisect', 'builtins', 'bz2', 'cProfile', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser', 'contextlib', 'contextvars', 'copy', 'copyreg', 'crypt', 'csv', 'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'doctest', 'email', 'encodings', 'ensurepip', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'fractions', 'ftplib', 'functools', 'gc', 'genericpath', 'getopt', 'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder', 'msilib', 'msvcrt', 'multiprocessing', 'netrc', 'nis', 'nntplib', 'nt', 'ntpath', 'nturl2path', 'numbers', 'opcode', 'operator', 'optparse', 'os', 'ossaudiodev', 'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc', 'pydoc_data', 'pyexpat', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal', 'site', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'sre_compile', 'sre_constants', 'sre_parse', 'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess', 'sunau', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile', 'termios', 'textwrap', 'this', 'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize', 'tomllib', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib', 'zoneinfo']
KNOWN_IMPORTS = set(STDLIB_312) | set(getattr(sys, 'stdlib_module_names', ())) | set(sys.builtin_module_names) | {
    'argparse', 'array', 'ast', 'bisect', 'collections', 'concurrent', 'contextlib', 'copy',
    'csv', 'dataclasses', 'datetime', 'decimal', 'enum', 'fractions', 'functools', 'gzip',
    'hashlib', 'heapq', 'io', 'itertools', 'json', 'math', 'multiprocessing', 'operator',
    'os', 'pathlib', 'pickle', 'random', 're', 'shlex', 'shutil', 'statistics', 'struct',
    'subprocess', 'sys', 'tempfile', 'time', 'typing', 'unittest', 'urllib', 'warnings',
    'zlib', 'flint', 'sympy', 'mpmath', 'numpy', 'scipy', 'gmpy2', 'sage', 'sageall',
}
BOUND = re.compile(r'≤|≥|<=|>=|<|>|\\(?:leq?|geq?|lt|gt)\b|\b(?:upper[- ]bound|lower[- ]bound|bound|certified|certifies|proves|rigorous)\b', re.I)
# Folders holding verbatim copies of earlier rounds' inputs; only digest-sealed files qualify.
ARCHIVE_DIRS = {'frozen', 'historical', 'baseline', 'inputs', 'inherited'}
NEWRESULT = re.compile(r'\b(?:new|improv\w*|this (?:PR|submission|packet|candidate|note|work)|our|we|here|I|prove[sd]?|show[sn]?|establish\w*)\b', re.I)
PRIORCTX = re.compile(r"\b(?:previous(?:ly)?|earlier|prior|cite[sd]?|was|originally|reported|claimed|recorded|table)\b|\b[A-Z][a-z]+'s\b|#\d+", re.I)
VERIFIED = re.compile(r'\b(?:verified|certified|certifies|proves|rigorous)\b', re.I)
NUMBER = re.compile(r'(?<![\w#])[-+]?(?:\d[\d,]*\s*/\s*\d[\d,]*|(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?:\s*\^\s*[-+]?\d+)?)(?![\w])')
SCRIPT = re.compile(r'(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.(?:py|sage|sh|cpp|cc|c|jl|wl)\b')
FILE = re.compile(r'(?<![\w/])(?:\.{1,2}/|[\w@+-]+/)*[\w@+.-]+\.(?:md|markdown|tex|pdf|json|jsonl|py|sage|sh|cpp|cc|c|h|hpp|jl|wl|txt|csv|tsv|gz|xz|npz|npy|pkl|yaml|yml|toml|lean|log)\b', re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def json_object(data, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(label + ': duplicate JSON key ' + repr(key))
            result[key] = value
        return result
    def constant(value):
        raise ValueError(label + ': invalid JSON number ' + value)
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object')
    return value


def tree_evidence(snapshot, value, commit):
    tree = json_object(snapshot.read(value), value) if isinstance(value, str) else value
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit) or not isinstance(tree, dict) or tree.get('commit') != commit or tree.get('truncated') is not False:
        raise ValueError('tree evidence must be complete and match pinned commit')
    rows = tree.get('tree')
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('path'), str) for r in rows):
        raise ValueError('invalid tree evidence entries')
    return {r['path'] for r in rows if r.get('type') in ('blob', 'tree') and r.get('mode') not in ('120000', '160000')}


def normalized(text):
    return ' '.join(text.split())


def identity(text):
    return re.sub(r'[^\w]', '', text.casefold()) if isinstance(text, str) else ''


def safe_path(name):
    if not isinstance(name, str) or not name.strip() or '\\' in name or '\x00' in name:
        raise ValueError('invalid relative path: ' + repr(name))
    p = PurePosixPath(name)
    if p.is_absolute():
        raise ValueError('absolute path: ' + repr(name))
    parts = []
    for part in p.parts:
        if part == '..':
            if not parts:
                raise ValueError('path escapes repository: ' + repr(name))
            parts.pop()
        elif part != '.':
            parts.append(part)
    return '/'.join(parts)


def git(root, *args):
    # No lazy network fetches from a hook. Acquiring missing objects is a separate
    # explicit preparation step; a partial/missing object fails closed here.
    result = subprocess.run(['git', '-c', 'protocol.allow=never', '-C', str(root), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('git ' + args[0] + ': ' + result.stderr.decode(errors='replace').strip()[:400])
    return result.stdout


class Snapshot:
    """Read blobs, never check out files or execute repository code."""
    def __init__(self, packet, commit=None, repo_root=None, prefix=None):
        self.packet = Path(packet).expanduser().resolve()
        self.root = Path(repo_root).expanduser().resolve() if repo_root else Path(git(self.packet, 'rev-parse', '--show-toplevel').decode().strip())
        relative = self.packet.relative_to(self.root).as_posix() if not prefix else prefix
        self.prefix = safe_path(relative)
        self.prefix = self.prefix.strip('/')
        self.commit = git(self.root, 'rev-parse', '--verify', (commit or 'HEAD') + '^{commit}').decode().strip()
        rows = git(self.root, 'ls-tree', '-rz', '--full-tree', self.commit).split(b'\0')
        self.entries = {}
        for row in rows:
            if row:
                info, name = row.split(b'\t', 1)
                mode, kind, oid = info.decode().split()
                self.entries[name.decode()] = (mode, kind, oid)
        self.cache = {}

    def name(self, path):
        return safe_path((self.prefix + '/' if self.prefix else '') + path)

    def exists(self, name):
        name = safe_path(name).rstrip('/')
        if not name:
            return True
        entry = self.entries.get(name)
        # Symlinks and gitlinks cannot stand in for a pinned certificate or script.
        return bool(entry and entry[0] in ('100644', '100755')) or any(p.startswith(name + '/') for p in self.entries)

    def read_repo(self, name):
        name = safe_path(name)
        if name not in self.entries or self.entries[name][0] not in ('100644', '100755'):
            raise ValueError('not a regular pinned file: ' + name)
        if name not in self.cache:
            self.cache[name] = git(self.root, 'cat-file', 'blob', self.entries[name][2])
        return self.cache[name]

    def read(self, path):
        return self.read_repo(self.name(path))

    def text(self, path):
        return self.read(path).decode('utf-8', errors='replace')

    def files(self):
        prefix = self.prefix + '/' if self.prefix else ''
        return [p[len(prefix):] for p, entry in self.entries.items()
                if p.startswith(prefix) and entry[0] in ('100644', '100755')]

    def resolve(self, name, document=None, fallback=True):
        candidates = []
        in_doc = bool(document and document != 'PR body' and not document.startswith('PR comment'))
        if in_doc:
            candidates.append(self.name(str(PurePosixPath(document).parent / name)))
            if not fallback:
                # Astra 11-04 r2 #7: an explicit link renders relative to its own
                # document; no root or basename fallback.
                return candidates[0]
        for candidate in ((self.prefix + '/' if self.prefix else '') + name, name):
            try:
                candidates.append(safe_path(candidate))
            except ValueError:
                pass
        if not candidates:
            raise ValueError('path escapes repository: ' + repr(name))
        if fallback and in_doc:
            # 11-04: a prose citation (never an explicit link) may be written
            # relative to an ancestor folder of the citing document (nearest first),
            # or name a basename that is unique within the citing document's subtree.
            parts = PurePosixPath(document).parts[:-1]
            for i in range(len(parts) - 1, 0, -1):
                try:
                    cand = self.name('/'.join(parts[:i]) + '/' + name)
                except ValueError:
                    continue
                if self.exists(cand):
                    candidates.append(cand)
                    break
            if '/' not in name and parts:
                sub = self.name('/'.join(parts)) + '/'
                local = sorted(p for p in self.entries if p.startswith(sub) and PurePosixPath(p).name == name)
                if len(local) == 1:
                    candidates.append(local[0])
        if '/' not in name and fallback:
            prefix = self.prefix + '/' if self.prefix else ''
            matches = sorted(p for p in self.entries if p.startswith(prefix) and PurePosixPath(p).name == name)
            # 11-04: a basename with several byte-identical copies (same blob) is
            # unambiguous; frozen packets keep identical copies of shared inputs.
            if len(matches) == 1 or matches and len({self.entries[m][2] for m in matches}) == 1:
                candidates.append(matches[0])
        return next((p for p in candidates if self.exists(p)), candidates[0])

    def fingerprint(self):
        prefix = self.prefix + '/' if self.prefix else ''
        return sha(canonical({p: e for p, e in self.entries.items() if p.startswith(prefix)}))


def prose(text):
    text = re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$', lambda m: '\n' * m[0].count('\n'), text)
    text = re.sub(r'(?m)^(?: {4}|\t).*$', '', text)
    return text


def sentences(text):
    # Keep soft-wrapped sentences together, decimal points and file names intact.
    # Bound displays may be indented or fenced. They still need labels; only
    # voice checking drops code blocks.
    text = re.sub(r'(?m)^[ \t]*(?:```|~~~)[^\n]*$', '', text)
    units, pending, first = [], [], 1
    for line_no, line in enumerate(text.splitlines(), 1):
        separate = bool(re.match(r'^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)', line))
        if not line.strip() or separate:
            if pending:
                units.append((first, ' '.join(pending)))
                pending = []
        if line.strip():
            if not pending:
                first = line_no
            pending.append(line.strip())
            if line.lstrip().startswith('|'):
                units.append((first, ' '.join(pending)))
                pending = []
    if pending:
        units.append((first, ' '.join(pending)))
    for line_no, line in units:
        for item in re.split(r'(?<=[.!?])\s+(?=[A-Z])', line):
            if item.strip():
                yield line_no, item.strip()


def without_links(text):
    text = re.sub(r'https?://[^\s)>\]]+', '', text)
    text = re.sub(r'\b(?:PR\s*)?#\d+\b', '', text)
    return text


def math_text(text):
    text = text.replace('−', '-')
    text = re.sub(r'\\(?:d?frac)\{([-+]?\d[\d,]*)\}\{(\d[\d,]*)\}', r'\1/\2', text)
    return re.sub(r'\^\{([-+]?\d+)\}', r'^\1', text)


def numbers(text, declared=()):
    text = without_links(text)
    text = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)', '', text)
    text = FILE.sub('', text)
    text = math_text(text).replace(',', '')
    found = []
    # Prefer a registered complete expression (1/2 + 2^-4096) over its numeric
    # pieces. Literal boundaries prevent a 0.25 entry from covering 0.25001.
    for value in sorted(declared, key=len, reverse=True):
        # 11-04: a sentence-final full stop ends the value; '.' + digit still extends it.
        pattern = r'(?<![\w.])' + r'\s*'.join(re.escape(c) for c in value) + r'(?!\w|\.\d)'
        def replace(match):
            found.append(value)
            return ' ' * len(match[0])
        text = re.sub(pattern, replace, text)
    return found + [m.group().replace(',', '').replace(' ', '') for m in NUMBER.finditer(text)]


def arithmetic(snapshot, producer, seen=None):
    """Conservative source audit, including local Python imports. No execution."""
    seen = set() if seen is None else seen
    path = snapshot.resolve(producer)
    if path in seen:
        return set()
    seen.add(path)
    source = snapshot.read_repo(path).decode(errors='replace')
    features = set()
    clean = source
    if path.endswith('.py'):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            raise ValueError('cannot statically inspect ' + producer)
        clean = ast.unparse(tree) if hasattr(ast, 'unparse') else source
        if any(isinstance(n, ast.Constant) and isinstance(n.value, float) for n in ast.walk(tree)):
            features.add('float')
        if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) for n in ast.walk(tree)):
            features.add('division')
        api_aliases = {}
        for node in ast.walk(tree):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in ('arb', 'acb', 'RealIntervalField', 'RealBallField', 'iv', 'Fraction', 'Rational', 'fmpq', 'fmpz', 'mpq', 'mpz'):
                        api_aliases[alias.asname or alias.name] = alias.name
            for module in modules:
                found_local = False
                base = PurePosixPath(path).parent
                if isinstance(node, ast.ImportFrom) and node.level:
                    for _ in range(node.level - 1):
                        base = base.parent
                bases = [base] if isinstance(node, ast.ImportFrom) and node.level else [base, PurePosixPath(snapshot.prefix or '.'), PurePosixPath('.')]
                modules_to_check = [module]
                if isinstance(node, ast.ImportFrom):
                    modules_to_check += [(module + '.' if module else '') + a.name for a in node.names if a.name != '*']
                for parent in bases:
                    for mod in modules_to_check:
                        stem = parent / mod.replace('.', '/')
                        for candidate in (str(stem) + '.py', str(stem / '__init__.py')):
                            local = safe_path(candidate)
                            if local in snapshot.entries:
                                found_local = True
                                rel = os.path.relpath(local, snapshot.prefix or '.').replace(os.sep, '/')
                                features |= arithmetic(snapshot, rel, seen)
                if not found_local and (not module or module.split('.')[0] not in KNOWN_IMPORTS):
                    raise ValueError('unresolved producer import ' + repr(module) + ' in ' + producer)
        assignments = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.setdefault(target.id, []).append(node.value)

        def number_type(node, depth=0):
            if depth > 12:
                return 'unknown'
            if isinstance(node, ast.Constant):
                return 'float' if isinstance(node.value, float) else 'integer' if type(node.value) is int else 'unknown'
            if isinstance(node, ast.Name):
                values = assignments.get(node.id, [])
                return number_type(values[0], depth + 1) if len(values) == 1 else 'unknown'
            if isinstance(node, ast.UnaryOp):
                return number_type(node.operand, depth + 1)
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func).split('.')[-1]
                name = api_aliases.get(name, name)
                if name in ('Fraction', 'Rational', 'fmpq', 'fmpz', 'mpq', 'mpz'):
                    return 'exact'
                if name in ('arb', 'acb', 'RealIntervalField', 'RealBallField'):
                    return 'interval'
                return 'integer' if name == 'int' else 'float' if name == 'float' else 'unknown'
            if isinstance(node, ast.BinOp):
                left, right = number_type(node.left, depth + 1), number_type(node.right, depth + 1)
                if 'float' in (left, right):
                    return 'float'
                if 'unknown' in (left, right):
                    return 'unknown'
                if isinstance(node.op, ast.Pow) and left == right == 'integer' and isinstance(node.right, ast.UnaryOp) and isinstance(node.right.op, ast.USub):
                    return 'float'
                if isinstance(node.op, ast.Div) and left == right == 'integer':
                    return 'float'
                return 'interval' if 'interval' in (left, right) else 'exact' if 'exact' in (left, right) else 'integer'
            return 'unknown'

        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                inferred = number_type(node)
                if inferred == 'float':
                    features.add('float')
                elif isinstance(node.op, ast.Div) and inferred == 'unknown':
                    features.add('unresolved-division')
    # Strip comments and strings before looking for arithmetic APIs: a comment saying
    # 'Arb' must not turn a float checker into an interval checker.
        calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
        calls = [api_aliases.get(c.split('.')[0], c.split('.')[0]) + ('.' + c.split('.', 1)[1] if '.' in c else '') for c in calls]
        if any(c in ('eval', 'exec', '__import__', 'importlib.import_module') for c in calls):
            raise ValueError('dynamic code/imports require manual review: ' + producer)
        tokens = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        tokens += [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
        tokens += [a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names]
        tokens += [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        clean = ' '.join(tokens)
    else:
        if not path.endswith(('.c', '.cc', '.cpp', '.h', '.hpp')):
            raise ValueError('unsupported arithmetic source audit: ' + producer + '; point to a Python or C/C++ checker')
        clean = re.sub(r'/\*.*?\*/|//[^\n]*|#[^\n]*', '', clean, flags=re.S)
        clean = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', clean)
        if re.search(r'\b\d+\.\d*|\.\d+\b|\b\d+[eE][-+]?\d+', clean):
            features.add('float')
    interval_api = bool(re.search(r'\b(?:arb|acb|RealIntervalField|RealBallField|interval|iv)\b', clean))
    if path.endswith('.py'):
        interval_api = any(re.search(r'(?:^|\.)(?:arb|acb|RealIntervalField|RealBallField|interval)$|(?:^|\.)iv\.', c) for c in calls)
    else:
        interval_api |= bool(re.search(r'\b(?:arb|acb|mpfi)_\w+\s*\(', clean))
    if interval_api:
        features.add('interval')
    if re.search(r'\b(?:Fraction|fractions|Rational|fmpq|fmpz|mpq|mpz|mpq_class|mpz_class|mpq_t|mpz_t|QQ|ZZ)\b', clean):
        features.add('exact')
    if re.search(r'\b(?:numpy|scipy|math|double|float|float64|mpmath)\b', clean):
        features.add('float')
    # Integer-only Python, without true division, is exact arithmetic too.
    if path.endswith('.py') and not features.intersection({'float', 'division'}):
        features.add('exact')
    return features


class Linter:
    def __init__(self, snapshot, body=None, metadata=None, comments=None):
        self.s = snapshot
        self.body_path = Path(body).expanduser().resolve() if body else None
        self.body = self.body_path.read_text() if body else ''
        self.extra = {}
        if self.body_path:
            self.extra[str(self.body_path)] = sha(self.body_path.read_bytes())
        self.errors = {key: [] for key in CHECKS}
        self.advisory = {key: [] for key in CHECKS}
        self.meta = metadata if metadata is not None else self.load('PUBLISH.json', 'paths', required=True)
        self.claim_data = self.load('CLAIMS.json', 'claims', required=True, advisory=True)
        self.claims = self.claim_data.get('claims', [])
        if self.s.name('CLAIMS.json') in self.s.entries and 'claims' not in self.claim_data:
            self.fail('claims', 'CLAIMS.json requires a claims list (use [] for a packet without numeric claims)', advisory=True)
        if not isinstance(self.claims, list):
            self.fail('claims', 'CLAIMS.json: claims must be a list', advisory=True)
            self.claims = []
        self.documents = {}
        proof_inputs = self.meta.get('replay_inputs', {})
        proof_inputs = proof_inputs if isinstance(proof_inputs, dict) else {}
        for name in self.s.files():
            base = PurePosixPath(name).name.lower()
            if base.startswith('readme') and base.endswith(('.md', '.txt', '.rst')) or ('proof' in base and base.endswith(('.md', '.tex', '.txt'))):
                self.documents[name] = self.s.text(name)
            elif base.endswith('.pdf') and ('proof' in base or proof_inputs.get(name) == 'proof'):
                try:
                    parsed = subprocess.run(['pdftotext', '-', '-'], input=self.s.read(name), capture_output=True, timeout=30)
                    if parsed.returncode or not parsed.stdout.strip():
                        raise ValueError('PDF text extraction failed or produced no text')
                    self.documents[name] = parsed.stdout.decode('utf-8', errors='replace')
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    self.fail('rigor', 'cannot inspect PDF proof; pdftotext is required: ' + str(exc), name, advisory=True)
        # A packet often keeps its proof in a sibling folder (e.g. C82). Follow
        # local proof citations, retaining repository-relative context.
        pending = list(self.documents)
        while pending:
            document = pending.pop()
            for cited in FILE.findall(without_links(self.documents[document])):
                if 'proof' not in PurePosixPath(cited).name.casefold() or not cited.endswith(('.md', '.tex', '.txt')):
                    continue
                try:
                    resolved = self.s.resolve(cited, document)
                    relative = os.path.relpath(resolved, self.s.prefix or '.').replace(os.sep, '/')
                    if relative not in self.documents and self.s.exists(resolved):
                        self.documents[relative] = self.s.read_repo(resolved).decode(errors='replace')
                        pending.append(relative)
                except ValueError:
                    pass
        if self.body_path:
            self.documents['PR body'] = self.body
        self.comments = []
        for p in comments or []:
            path = Path(p).expanduser().resolve()
            data = path.read_bytes()
            self.extra[str(path)] = sha(data)
            self.comments.append((str(path), data.decode()))

    def load(self, path, check, required=False, advisory=False):
        if self.s.name(path) not in self.s.entries:
            if required:
                self.fail(check, path + ' missing at pinned commit', advisory=advisory)
            return {}
        try:
            return json_object(self.s.read(path), path)
        except (ValueError, OSError) as exc:
            self.fail(check, path + ': ' + str(exc), advisory=advisory)
            return {}

    def fail(self, check, message, document=None, line=None, advisory=False):
        # 11-04 (the owner's rule: tests never block publishing). BLOCKING
        # findings are those that would make a public statement false or unfair;
        # ADVISORY findings are paperwork/completeness, recorded in the receipt and
        # fixed later, never gating.
        item = {'message': message}
        if document:
            item['file'] = document
        if line is not None:
            item['line'] = line
        target = self.advisory if advisory else self.errors
        if item not in target[check]:
            target[check].append(item)

    def producer(self, row, check):
        script = row.get('producer')
        arith = row.get('arithmetic')
        if arith not in ('exact', 'interval', 'float') or not isinstance(script, str) or not SCRIPT.fullmatch(script):
            raise ValueError('producer script and arithmetic=exact|interval|float required')
        features = arithmetic(self.s, script)
        if arith == 'interval' and 'interval' not in features:
            raise ValueError(repr(script) + ' has no interval arithmetic API (features: ' + ', '.join(sorted(features)) + ')')
        if arith == 'exact' and ('exact' not in features or features.intersection({'float', 'unresolved-division'})):
            raise ValueError(repr(script) + ' is not an exact-only producer (features: ' + ', '.join(sorted(features)) + ')')
        return script, arith

    def check_claims(self):
        indexed = {}
        for row in self.claims:
            try:
                if not isinstance(row, dict):
                    raise ValueError('claim must be an object')
                value = row['value']
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('value must be a nonempty string')
                key = math_text(value).replace(',', '').replace(' ', '')
                if not NUMBER.search(key):
                    raise ValueError('value must contain a numeric value or expression')
                if key in indexed:
                    raise ValueError('duplicate value ' + repr(value))
                if row.get('kind') not in ('rigorous', 'estimate', 'cited'):
                    raise ValueError('kind must be rigorous|estimate|cited')
                if row['kind'] == 'cited':
                    # Someone else's public value (a table row, another PR, a paper).
                    # It needs a real source (a URL or a pinned packet file), not one
                    # of our producers, and is never new. An invalid cited row is NOT
                    # registered, so its value still counts as unregistered.
                    source = row.get('source')
                    if row.get('new_bound'):
                        self.fail('claims', 'CLAIMS.json ' + repr(row) + ': a cited value cannot be a new bound')
                        continue
                    if not isinstance(source, str) or not (re.match(r'https?://\S+$', source) or (source.startswith('sources/') and self.s.exists(self.s.resolve(source)))):
                        raise ValueError('cited value needs a URL or a pinned sources/ evidence file as source')
                    indexed[key] = row
                    continue
                if row['kind'] == 'rigorous' and row.get('arithmetic') == 'float':
                    # Self-declared estimate labelled rigorous: false statement, BLOCKING.
                    self.fail('claims', 'CLAIMS.json ' + repr(row) + ': float-only producer ' + repr(row.get('producer')) + ' cannot produce a rigorous claim')
                    continue
                if row.get('arithmetic') not in ('exact', 'interval', 'float') or not isinstance(row.get('producer'), str):
                    raise ValueError('producer script and arithmetic=exact|interval|float required')
                indexed[key] = row
            except (KeyError, ValueError, OSError) as exc:
                # Schema findings are paperwork: ADVISORY (the row is not registered).
                self.fail('claims', 'CLAIMS.json ' + repr(row) + ': ' + str(exc), advisory=True)
                continue
            if row.get('kind') != 'cited':
                try:
                    self.producer(row, 'claims')
                except (KeyError, ValueError, OSError) as exc:
                    # Heuristic source audit: ADVISORY; the registration stands.
                    self.fail('claims', 'CLAIMS.json ' + repr(row) + ': ' + str(exc), advisory=True)
        for name, text in self.documents.items():
            if name != 'PR body' and not PurePosixPath(name).name.lower().startswith('readme'):
                continue
            parts = list(sentences(text))
            bound_context = {line for line, sentence in parts if BOUND.search(without_links(sentence))}
            for line, sentence in parts:
                bound = bool(BOUND.search(without_links(sentence)))
                vals = numbers(sentence, indexed)
                plain = math_text(without_links(sentence)).replace(',', '')
                for val in vals:
                    row = indexed.get(val)
                    if (bound or line in bound_context) and not row:
                        # BLOCKING for an unregistered value that a bound sentence
                        # asserts: any decimal/fraction/scientific value, and an integer
                        # that a comparison actually asserts ("<= 0", "bound is 2").
                        # Other integers (years, spans, counts) and paragraph-context
                        # numbers are ADVISORY. Scanner artifacts (software versions such
                        # as 'Python 3.10', ellipsis fragments such as '.5999' from
                        # 'k=1,...,5999') are context.
                        # Astra 11-04 r2 #5: an artifact exemption applies only when EVERY
                        # occurrence of the value in the sentence is that artifact.
                        # Astra 11-04 r3 #4: classify each occurrence span on its own.
                        md = re.sub(r'[*_`]', '', plain)
                        spans = [m.start() for m in re.finditer(r'(?<![\w])' + re.escape(val) + r'(?![\w]|\.\d)', md)]
                        def is_artifact(i):
                            before = md[max(0, i - 24):i]
                            if val.startswith('.'):
                                return before.endswith('..') or before.endswith('…')
                            return bool(re.search(r'(?i)(?:python|version|gcc|clang|flint|arb|c\+\+|\bv)\s*(?:>=|≥)?\s*$', before))
                        artifact = bool(spans) and all(is_artifact(i) for i in spans)
                        # Astra 11-04 r3 #5: Markdown emphasis removed; an integer next to
                        # "bound" (either side, no other number between) is asserted.
                        asserted_integer = bool(re.search(r'(?i)(?:≤|≥|<=|>=|<|>|\\(?:leq?|geq?|lt|gt)\b|\bat\s+(?:least|most)|\b(?:bound|constant|value)\b[^.;\d]{0,32}?)\s*\$?\s*' + re.escape(val) + r'(?![\d.]\d)', md)) \
                            or bool(re.search(r'(?<![\w.])' + re.escape(val) + r'(?![\d.]\d)[^.;\d]{0,32}?\bbound\b', md, re.I))
                        blocking = bound and not artifact and (bool(re.search(r'[./eE]', val)) or asserted_integer)
                        self.fail('claims', 'unlabeled bound number ' + repr(val) + '; add CLAIMS.json entry and prose label/producer', name, line, advisory=not blocking)
                    if not row:
                        continue
                    kind, script = row.get('kind', ''), row.get('producer', '')
                    if kind == 'cited':
                        # r5 #1: a model/software version is context only when EVERY
                        # occurrence of the value in the sentence is such a version.
                        mdc = re.sub(r'[*_`]', '', plain)
                        occ_c = [m.start() for m in re.finditer(r'(?<![\w.])' + re.escape(val) + r'(?![\w]|\.\d)', mdc)]
                        if occ_c and all(re.search(r'(?i)(?:python|version|opus|sonnet|haiku|fable|gpt-?|claude|codex|\bv)\s*$', mdc[max(0, i - 16):i]) for i in occ_c):
                            continue
                    if kind == 'cited':
                        # Astra 11-04 r2 #3: a citation cannot carry this submission's
                        # own new or improved result.
                        # r3 #2: the new-result cue may sit anywhere in the paragraph; a
                        # sentence that frames the value as earlier/cited work is fine.
                        paragraph = ' '.join(t for l2, t in parts if l2 == line)
                        if bound and NEWRESULT.search(paragraph) and not PRIORCTX.search(sentence):
                            self.fail('claims', 'cited value ' + repr(val) + ' asserted as this submission\'s new result: ' + sentence, name, line)
                        continue
                    if kind not in ('rigorous', 'estimate') or not re.search(r'\b' + kind + r'\b', sentence, re.I) or not script or script not in sentence:
                        self.fail('claims', repr(val) + ' needs its ' + repr(kind) + ' label and producer ' + repr(script) + ' in the same sentence', name, line, advisory=True)
                    if bound and (kind != 'rigorous' or row.get('arithmetic') == 'float'):
                        # 11-04: a registered estimate explicitly marked as approximate is
                        # not presented as a bound (ADVISORY), unless the sentence also
                        # asserts rigor (verified/certified/proves/rigorous) or holds a
                        # rigorous value (#301): then BLOCKING.
                        marked = bool(re.search(r'\b(?:approximately|approx\.?|about|roughly|estimated?|numerical(?:ly)?)\b|≈|~', sentence, re.I)) \
                            and not VERIFIED.search(sentence) \
                            and not any(indexed.get(v, {}).get('kind') == 'rigorous' for v in vals)
                        self.fail('claims', repr(val) + ' from ' + repr(script) + ' is an estimate in a bound sentence: ' + sentence, name, line, advisory=marked)

    def sealed(self, name):
        # True when some SHA256SUMS in an enclosing packet folder lists this file.
        parts = PurePosixPath(name).parts
        for i in range(len(parts) - 1, -1, -1):
            folder = '/'.join(parts[:i])
            sums = (folder + '/' if folder else '') + 'SHA256SUMS'
            if self.s.name(sums) not in self.s.entries:
                continue
            rel = '/'.join(parts[i:])
            listed = {}
            for l in self.s.text(sums).splitlines():
                bits = l.split(None, 1)
                if len(bits) == 2:
                    f = bits[1].strip().lstrip('*')
                    listed[f[2:] if f.startswith('./') else f] = bits[0].lower()
            # Astra 11-04 r2 #8: the listed digest must be the file's actual digest.
            if rel in listed and listed[rel] == sha(self.s.read(name)):
                return True
        return False

    def check_paths(self):
        for name, text in self.documents.items():
            for line, sentence in enumerate(prose(text).splitlines(), 1):
                plain = without_links(re.sub(r'(?<!!)\[[^\]]*\]\([^)]+\)', '', sentence))
                paths = set(FILE.findall(plain))
                # Astra 11-04 #7: an explicit Markdown link must reach its actual
                # destination; basename fallbacks apply only to prose citations.
                links = set(re.findall(r"""(?<!!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)""", sentence))
                links |= set(re.findall(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', sentence))  # r3 #7 reference definitions
                links |= set(re.findall(r'''<(?:a|img)\s[^>]*?(?:href|src)\s*=\s*["']([^"']+)["']''', sentence, re.I))  # r5 #5 HTML
                paths.update(links)
                for candidate in re.findall(r'`((?:[\w.-]+/)+[\w./-]*|(?:LICENSE|COPYING|Makefile))`', sentence):
                    # Inline rational expressions and short symbolic quotients are
                    # mathematics, not directory citations.
                    if candidate.endswith('/') or '.' in candidate or candidate in ('LICENSE', 'COPYING', 'Makefile') or all(len(c) > 2 and not c.isdigit() for c in candidate.split('/')):
                        paths.add(candidate)
                for path in paths:
                    if re.match(r'^(?:https?:|mailto:|#)', path):
                        continue
                    is_link = path in links
                    path = path.split('#')[0].rstrip('.,:;')
                    if not path:
                        continue
                    # 11-04: sealed historical copies (frozen/, historical/) are
                    # archived verbatim; their internal references are ADVISORY, since
                    # rewriting them would break their seals and replay input hashes.
                    # Astra 11-04 #4: only a prose citation inside a document that is
                    # actually sealed (listed in a SHA256SUMS) under frozen/ or
                    # historical/ qualifies; links and unsealed files stay BLOCKING.
                    archived = (not is_link and name != 'PR body' and any(q in ARCHIVE_DIRS or q.startswith('frozen') for q in PurePosixPath(name).parts[:-1])
                                and self.sealed(name))
                    try:
                        resolved = self.s.resolve(path, name, fallback=not is_link)
                        if not self.s.exists(resolved):
                            publication = set()
                            if name == 'PR body' and self.meta.get('publication_tree'):
                                publication = tree_evidence(self.s, self.meta['publication_tree'], self.meta.get('publication_commit'))
                            if not is_link and '/' not in path and len([q for q in publication if PurePosixPath(q).name == path]) == 1:
                                continue  # 11-04: unique basename in the pinned target tree
                            if path not in publication:
                                self.fail('paths', repr(path) + ' missing at ' + self.s.commit, name, line, advisory=archived)
                    except ValueError as exc:
                        self.fail('paths', str(exc), name, line, advisory=archived)
        # GitHub blob/tree links name files in other repositories. They must use
        # full commit pins and have locally cached tree evidence, never a live HEAD.
        evidence = self.meta.get('linked_trees', {})
        for name, text in self.documents.items():
            for match in re.finditer(r'https://github\.com/([^/]+/[^/]+)/(blob|tree)/([^/\s)]+)(?:/([^\s)<>\]]*))?', text):
                repo, kind, commit, path = match.groups()
                commit = commit.rstrip('.,;')
                path = unquote((path or '').split('#')[0].rstrip('.,;'))
                if not re.fullmatch(r'[a-f0-9]{40}', commit):
                    self.fail('paths', 'unpinned GitHub citation ' + repr(match.group()), name)
                    continue
                if not path:
                    continue
                # Own-repository paths can be checked directly if this is the same tree.
                if commit == self.s.commit and self.s.exists(path):
                    continue
                key = repo + '@' + commit
                cached = evidence.get(key)
                if not isinstance(cached, (str, dict)):
                    self.fail('paths', 'missing linked-tree evidence for ' + key + ':' + path, name)
                    continue
                try:
                    items = tree_evidence(self.s, cached, commit)
                    if path not in items:
                        raise ValueError('cited path missing')
                except (KeyError, ValueError) as exc:
                    self.fail('paths', key + ':' + path + ': ' + str(exc), name)

    def check_credit(self):
        data = self.load('CREDITS.json', 'credit', advisory=True)
        rows = data.get('credits', [])
        has_credit = any(re.search(r'\b(?:credits?|attribution|builds? (?:directly )?on|author|byline)\b', t, re.I) for t in self.documents.values())
        if has_credit and not data:
            self.fail('credit', 'CREDITS.json missing: credited names require PR, packet and source-author/byline evidence', advisory=True)
        if not isinstance(rows, list):
            self.fail('credit', 'CREDITS.json credits must be a list', advisory=True)
            rows = []  # Astra 11-04 #6: keep running the attribution checks
        mapped_prs = set()
        pr_names = {}
        packet_names = set()
        for row in rows:
            names = [row.get(k) for k in ('pr_name', 'packet_name', 'source_name')] if isinstance(row, dict) else []
            try:
                if len(names) != 3 or any(not isinstance(n, str) or not n.strip() for n in names):
                    raise ValueError('three nonempty verbatim names required')
                pr_name, packet_name, source_name = names
                packet_names.add(packet_name)
                missing_in_body = bool(self.body_path) and pr_name not in self.body
                packet = row['packet_file']
                if packet_name not in self.s.text(packet):
                    raise ValueError('packet name not found in ' + packet)
                source = json_object(self.s.read(row['source_pr']), 'source PR evidence')
                if type(source.get('number')) is not int:
                    raise ValueError('source PR snapshot requires its numeric PR number')
                # Astra 11-04 r4 #4: evidence that names a repository must name the
                # target repository's PR.
                repo = str(self.meta.get('target', '')).split('#')[0]
                if source.get('url') is not None and source.get('url') != 'https://github.com/' + repo + '/pull/' + str(source['number']):
                    raise ValueError('source PR snapshot is for another repository/PR: ' + repr(source.get('url')))
                author = source.get('author', source.get('user', {}))
                if not isinstance(author, dict):
                    raise ValueError('credited PR author must be an object')
                authors = {author.get('name'), author.get('login')}
                # 11-04: a row for the submitter's own PR (evidence author login ==
                # PUBLISH.json submitter) is self-reference, not credit to someone
                # else, and may live in packet text only.
                own = bool(self.meta.get('submitter')) and author.get('login') == self.meta.get('submitter')
                if missing_in_body and not own:
                    raise ValueError('PR name not found in PR body')
                byline = row.get('byline')
                if byline:
                    source_body = re.sub(r'[*_`]', '', source.get('body', ''))
                    if byline != source_name or not re.search(r'(?im)^\s*(?:by|author|byline)\s*:?\s*' + re.escape(byline) + r'\s*[.]?\s*$', source_body):
                        raise ValueError('byline not present verbatim in credited PR body')
                    authors.add(byline)
                # 11-05 (#299, CS): the credited PR's OWN diff credits its author by name
                # when the GitHub profile name is empty. r6-tight: only an added line of the
                # form "by [NAME](https://github.com/LOGIN..." with LOGIN the PR author's
                # login, and no negation on that line.
                diff = source.get('diff')
                login = author.get('login')
                if isinstance(diff, str) and isinstance(login, str) and login and source_name not in authors:
                    for l in diff.splitlines():
                        if not l.startswith('+') or l.startswith('+++'):
                            continue
                        line = re.sub(r'[*_`]', '', l[1:])
                        if re.search(r"(?i)\b(?:not|never|no)\b|n't\b", line):
                            continue
                        if re.search(r'\bby\s+\[' + re.escape(source_name) + r'\]\(https://github\.com/' + re.escape(login) + r'(?:[/)])', line, re.I):
                            authors.add(source_name)
                            break
                if source_name not in authors:
                    raise ValueError('source name not in credited PR author/byline/own-diff credit: ' + repr(sorted(str(a) for a in authors if a)))
                if pr_name != packet_name or packet_name != source_name:
                    raise ValueError('attribution mismatch')
                # Astra 11-04 r2 #6: only fully validated evidence maps a credited PR.
                mapped_prs.add(str(source['number']))
                pr_names.setdefault(str(source['number']), set()).add(pr_name)
            except (KeyError, ValueError, TypeError) as exc:
                # A name that is not the credited author's, or not what the PR/packet
                # says, is wrong credit: BLOCKING. Malformed rows are paperwork.
                schema = isinstance(exc, (KeyError, TypeError)) or str(exc).startswith('three nonempty')
                self.fail('credit', 'PR / packet / source names ' + ' / '.join(repr(n) for n in names) + ': ' + str(exc), advisory=schema)
        # An empty table cannot waive visible attribution; it is recorded (ADVISORY),
        # since paper/repository credits have no PR-author evidence to map.
        if has_credit and data and not rows:
            self.fail('credit', 'CREDITS.json is empty although the publication contains attribution', advisory=True)
        # Credit to another PR always needs that PR's own author evidence (BLOCKING,
        # even with no CREDITS.json): this is how a wrong name (#299/#274) is caught.
        # Astra 11-04 r4 #3: every published document, not only the PR body; sealed
        # archive copies (frozen/, historical/) are recorded as ADVISORY.
        credit_docs = [('PR body', self.body)] + [(d, t) for d, t in self.documents.items() if d != 'PR body']
        # 11-05 r6-tight: an evidenced credit name with an initial ("V. Patankar") is
        # not split by the sentence splitter; nothing else changes sentence boundaries.
        initialled = sorted({n for ns in pr_names.values() for n in ns if re.search(r'\b[A-Z]\.\s', n)}, key=len, reverse=True)
        def guarded(text):
            for n in initialled:
                text = text.replace(n, re.sub(r'\.\s+', '.\u2060', n))
            return text
        for doc, doc_text in credit_docs:
            archived = False  # r5 #4: wrong credit is unfair anywhere; no archive exemption
            for _, sentence in sentences(guarded(doc_text)):
                sentence = sentence.replace('\u2060', ' ')
                if re.search(r'\b(?:credits?|attribution|builds? (?:directly )?on|author|byline)\b', sentence, re.I):
                    refs = set(re.findall(r'(?:#|/pull/)(\d+)\b', sentence))
                    for number in sorted(refs - mapped_prs):
                        self.fail('credit', 'credited PR #' + number + ' has no name/evidence row: ' + sentence, doc, advisory=archived)
                    # Astra 11-04 r3 #6: the name credited with #N must be in this sentence.
                    for number in sorted(refs & mapped_prs):
                        if not any(n in sentence for n in pr_names.get(number, ())):
                            self.fail('credit', 'credited PR #' + number + ' is not attributed to its evidenced name ' + repr(sorted(pr_names.get(number, ()))) + ': ' + sentence, doc, advisory=archived)
        for name in self.s.files():
            if 'credit' not in PurePosixPath(name).name.casefold() or not name.endswith('.md'):
                continue
            for match in re.finditer(r'(?im)^\s*(?:[-*]\s*)?(?:(?:original|credited|baseline)\s+)?(?:author|byline|credit)\s*:\s*(.+?)\s*$', self.s.text(name)):
                quoted = match[1].strip('*` ')
                if quoted not in packet_names:
                    self.fail('credit', 'unmapped packet name ' + repr(quoted) + '; mapped names ' + repr(sorted(packet_names)), name, advisory=True)

    def check_selfref(self):
        target = self.meta.get('target', '')
        number = self.meta.get('pr_number') or (target.split('#')[-1] if '#' in target else None)
        if number is None:
            return
        if not str(number).isdigit():
            self.fail('selfref', 'pr_number must be numeric')
            return
        if '#' in target and str(number) != target.split('#')[-1]:
            self.fail('selfref', 'pr_number disagrees with target')
            return
        pattern = re.compile(r'(?<!\w)#' + str(number) + r'\b|github\.com/' + re.escape(target.split('#')[0]) + r'/pull/' + str(number) + r'\b')
        for name, text in self.documents.items():
            for line, sentence in sentences(text):
                # A comment on this PR and an explicit description of this PR are
                # legitimate self links. Catch a dependency/history relationship
                # that presents this PR as a separate source.
                candidate = re.sub(r'https://github\.com/[^\s)]+/pull/\d+#(?:issuecomment|discussion_r)-?\d+', '', sentence)
                explicit = re.search(r'\b(?:this|existing|current|our)(?:\s+\w+){0,3}\s+PR\s*\(?#' + str(number) + r'\b', candidate, re.I)
                relation = re.search(r'\b(?:builds? on|on top of|replaces?|preceding|prior|earlier|from|above|threshold in|round\s*\d+)\b', candidate, re.I)
                if pattern.search(candidate) and relation and not explicit:
                    self.fail('selfref', 'reference to this PR as a separate PR: ' + sentence, name, line)

    def check_voice(self):
        documents = [('PR body', self.body)] if self.body_path else []
        documents += [('PR comment ' + name, text) for name, text in self.comments]
        for name, text in self.documents.items():
            if name != 'PR body' and PurePosixPath(name).name.lower().startswith('readme'):
                first = [p for p in prose(text).split('\n\n') if re.search(r'\b(?:I|my|me|we|our|us)\b', p)]
                if first:
                    documents.append((name, '\n\n'.join(first)))
        for name, text in documents:
            clean = prose(text)
            # 11-04: the required attribution footer is not the owner's prose; strip it before xlint.
            clean = re.sub(r'(?m)^\s*\U0001F916\s*Generated with \[Claude Code\]\([^)]*\)\s*$', '', clean)
            clean = re.sub(r'(?m)^\s*https://claude\.ai/code/session_\S+\s*$', '', clean)
            clean = re.sub(r'(?m)^\s*#+\s+', '', clean)
            clean = re.sub(r'#(?=\d+\b)', 'PR ', clean)  # PR references are not hashtags.
            clean = re.sub(r'https?://\S+', '', clean)
            try:
                result = subprocess.run([sys.executable, str(XLINT)], input=clean, capture_output=True, text=True, timeout=15)
                if result.returncode:
                    self.fail('voice', 'xlint: ' + (result.stdout + result.stderr).strip(), name)
                if re.search(r'\bgood one to have on the record\b|\bload[- ]bearing\b', clean, re.I):
                    self.fail('voice', 'banned phrase in the owner\'s prose', name)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.fail('voice', 'cannot run xlint: ' + str(exc), name)

    def check_rigor(self):
        data = self.load('RIGOR.json', 'rigor', advisory=True)
        steps = data.get('steps', [])
        if not isinstance(steps, list):
            self.fail('rigor', 'RIGOR.json steps must be a list', advisory=True)
            steps = []
        valid = []
        float_steps = False
        for row in steps:
            try:
                document = row['document']
                statement = row['statement']
                if document not in self.documents or not statement or normalized(statement) not in normalized(self.documents[document]):
                    raise ValueError('step must quote an actual proof/publication statement')
                if row.get('arithmetic') == 'float':
                    # Self-declared float step: calling it verified is a false
                    # statement (BLOCKING), and it downgrades dependent claims.
                    float_steps = True
                    if 'numerical evidence' not in statement.casefold() or VERIFIED.search(statement):
                        self.fail('rigor', 'RIGOR.json ' + repr(row) + ': float-only step must say numerical evidence and cannot say verified/certified/proves/rigorous')
                        continue
                script, arith = self.producer(row, 'rigor')
                valid.append(row)
            except (KeyError, ValueError, TypeError) as exc:
                self.fail('rigor', 'RIGOR.json ' + repr(row) + ': ' + str(exc), advisory=True)
        for document, text in self.documents.items():
            for line, sentence in sentences(text):
                if not VERIFIED.search(sentence):
                    continue
                covered = [r for r in valid if r['document'] == document and normalized(sentence) in normalized(r['statement']) and r['arithmetic'] in ('exact', 'interval')]
                if covered:
                    continue
                scripts = SCRIPT.findall(sentence)
                checked = False
                mixed = False
                for script in scripts:
                    try:
                        features = arithmetic(self.s, script)
                        checked |= 'interval' in features or ('exact' in features and not features.intersection({'float', 'unresolved-division'}))
                        # Exact/interval code with some float or unresolved division is
                        # the heuristic's ambiguous case (diagnostic doubles): ADVISORY.
                        mixed |= bool(features.intersection({'exact', 'interval'}))
                    except ValueError:
                        pass
                if not checked and mixed:
                    self.fail('rigor', 'verified step names a mixed exact/float producer (heuristic): ' + sentence, document, line, advisory=True)
                elif not checked:
                    # Naming a script that is not exact/interval as the verifier is an
                    # estimate labelled rigorous: BLOCKING. A verified-sounding sentence
                    # with no script (analytic prose, negations, filenames) is ADVISORY.
                    self.fail('rigor', 'verified step lacks a mapped exact/interval producer: ' + sentence, document, line, advisory=not scripts)
        if float_steps:
            if any(r.get('kind') == 'rigorous' for r in self.claims if isinstance(r, dict)):
                self.fail('rigor', 'float-only proof step downgrades the packet: all dependent claims must be estimates')
            for document, text in self.documents.items():
                if document == 'PR body' or PurePosixPath(document).name.lower().startswith('readme'):
                    if any(BOUND.search(s) and numbers(s) for _, s in sentences(text)):
                        self.fail('rigor', 'float-only proof step requires numerical evidence claim text, without numeric bound assertions', document)

    def unchanged_update(self, new_claims):
        target = self.meta.get('target', '')
        m = re.fullmatch(r'teorth/[\w.-]+#(\d+)', target if isinstance(target, str) else '')
        snap = self.meta.get('live_body')
        if not m or not isinstance(snap, str):
            return False, ''
        try:
            live = json_object(self.s.read(snap), snap)
        except (ValueError, OSError):
            return False, ''
        if live.get('number') != int(m[1]) or not isinstance(live.get('body'), str) or not new_claims:
            return False, ''
        # Astra 11-04 r2 #2: bind the snapshot to the target repository, an OPEN PR
        # and freshness (fetched_utc within 24 h of this lint).
        repo = target.split('#')[0]
        if live.get('url') != 'https://github.com/' + repo + '/pull/' + m[1] or live.get('state') != 'OPEN':
            return False, ''
        try:
            fetched = dt.datetime.fromisoformat(str(live.get('fetched_utc')).replace('Z', '+00:00'))
            age = (dt.datetime.now(dt.timezone.utc) - fetched).total_seconds()
        except (ValueError, TypeError):
            return False, ''
        if fetched.tzinfo is None or not 0 <= age < 86400:
            return False, ''
        # Astra 11-04 r2 #1: compare ASSERTED bounds, not mere numeric presence: a value
        # counts only from a live bound sentence that is not a previous/withdrawn/
        # cited/estimate statement.
        cited = {math_text(r['value']).replace(',', '').replace(' ', '') for r in self.claims if isinstance(r, dict) and r.get('kind') == 'cited' and isinstance(r.get('value'), str)}
        def directions(sentence, v):
            # Astra 11-04 r5 #3: per-value directions = bound words in the sentence
            # plus the comparison adjacent to the value ("C >= v" lower, "v < X" lower,
            # "C <= v" upper, "v > X" upper).
            txt = math_text(without_links(sentence)).replace(',', '')
            out = set()
            out |= {w.lower() for w in re.findall(r'(?i)\b(upper|lower)[- ]bounds?\b', txt)}
            ve = r'(?<![\w.])' + r'\s*'.join(re.escape(c) for c in v) + r'(?![\w]|\.\d)'
            # 11-05: when the other operand is a bare number, "C <= v < 1.99", the
            # comparison is not a bound on C. r6-tight: a number joined to more terms
            # by an arithmetic operator ("1 * C") is not a bare number.
            numeric = re.compile(r'[-+]?[\d.,/]+[*\\]*\$?')
            arith = '*/×·+-−^'
            for m in re.finditer(r'(\S*?)\s*(>=|≥|\\geq?|>|<=|≤|\\leq?|<)\s*\$?\s*' + ve, txt):
                bare = numeric.fullmatch(m.group(1).strip('$')) and not txt[:m.start(1)].rstrip().endswith(tuple(arith))
                if not bare:
                    out.add('lower' if m.group(2) in ('>=', '≥', '>', '\\ge', '\\geq') else 'upper')
            for m in re.finditer(ve + r'\s*\$?\s*(>=|≥|\\geq?|>|<=|≤|\\leq?|<)\s*(\S*)', txt):
                op = m.group(2).strip('$').rstrip('.,;)')
                rest = txt[m.end(2):].lstrip()
                bare = numeric.fullmatch(op) and not (rest[:1] and rest[0] in arith)
                if not bare:
                    out.add('upper' if m.group(1) in ('>=', '≥', '>', '\\ge', '\\geq') else 'lower')
            return out
        def asserted(text, idx):
            # Astra 11-04 r3 #1: (value, direction) pairs from sentences that assert a
            # bound as this PR's own result: not cited/attributed, negated, estimated
            # or framed as previous/withdrawn.
            out = set()
            for _, sentence in sentences(text):
                if not BOUND.search(without_links(sentence)):
                    continue
                if re.search(r"(?i)\b(?:previous|previously|earlier|prior|withdrawn|replac\w*|superseded|estimated?|numerical|approximately|was|cite[sd]?|reported|claimed|not|no|never|fails?)\b|n't\b|≈|\b[A-Z][a-z]+'s\b|\bof [A-Z][a-z]+", sentence):
                    continue
                out |= {(v, d) for v in numbers(sentence, idx) if v not in cited for d in (directions(sentence, v) or {'none'})}
            return out
        index = {math_text(r['value']).replace(',', '').replace(' ', ''): r for r in new_claims if isinstance(r.get('value'), str)}
        live_pairs = asserted(live['body'], index)
        body_pairs = asserted(self.body, index) if self.body_path else set()
        live_vals = {v for v, _ in live_pairs}
        if not set(index) <= live_vals or not set(index) <= {v for v, _ in body_pairs}:
            return False, ''
        live_dirs = {}
        for v, d in live_pairs:
            live_dirs.setdefault(v, set()).add(d)
        # 11-05: a value the live body prints only without a direction (a code block
        # "v = 1.99... < X") may take a direction the live body asserts for the PR's
        # new values. r6-tight: never when the live body gives v an explicit direction.
        live_union = {d for v, d in live_pairs if v in index and d != 'none'}
        def same(v, d):
            ds = live_dirs.get(v, set())
            return d in ds or (d == 'none' and bool(ds)) or (ds == {'none'} and d in live_union)
        if not all(same(v, d) for v, d in body_pairs if v in index):
            return False, ''
        # Every registered rigorous value that a bound sentence of the proposed body
        # asserts must already be asserted (same direction) in the live body.
        rigorous = {math_text(r['value']).replace(',', '').replace(' ', ''): r for r in self.claims
                    if isinstance(r, dict) and r.get('kind') == 'rigorous' and isinstance(r.get('value'), str)}
        live_r = asserted(live['body'], rigorous)
        for pr in asserted(self.body, rigorous):
            if pr[0] in rigorous and pr not in live_r:
                return False, ''
        # Astra 11-04 r4 #1: README/proof documents must not assert a new value, or a
        # new value in another direction, either.
        # Packet documents: every new value's directions (bound words or adjacent
        # comparisons) must already be live directions of that value.
        for document, text in self.documents.items():
            if document == 'PR body':
                continue
            for _, sentence in sentences(text):
                if re.search(r"(?i)\b(?:previous|previously|earlier|prior|withdrawn|replac\w*|superseded|estimated?|numerical|approximately|was|cite[sd]?|reported|claimed|not|no|never|fails?)\b|n't\b|≈|\b[A-Z][a-z]+'s\b|\bof [A-Z][a-z]+", sentence):
                    continue
                for v in numbers(sentence, index):
                    if v in index and not all(same(v, d) for d in directions(sentence, v)):
                        return False, ''
        return True, 'update of open PR #' + m[1] + ' with its bound unchanged (' + ', '.join(sorted(index)) + ' in the live body ' + snap + ')'

    def check_replay(self):
        new = self.meta.get('new_bound')
        if type(new) is not bool:
            self.fail('replay', 'PUBLISH.json must explicitly declare new_bound=true|false')
            return
        # A missing classification is conservative; ordinary historical rows should
        # explicitly set new_bound:false in their individual CLAIMS entries.
        # Astra 11-04 r4 #2: anything but an explicit False counts as new.
        new_claims = [r for r in self.claims if isinstance(r, dict) and r.get('kind') == 'rigorous' and r.get('new_bound', True) is not False]
        if not new and new_claims:
            self.fail('replay', 'new rigorous CLAIMS entries contradict new_bound=false')
            return
        if not new:
            return
        # 11-04 (general): an update to an ALREADY-OPEN PR whose bound is unchanged,
        # fixing only wording, credit or links, makes the public text more correct:
        # replay is ADVISORY there. "Unchanged" = every new rigorous value appears in
        # the PR's current live body (a pinned `gh pr view N --json number,body`
        # snapshot named by PUBLISH.json live_body) and in the proposed body. A NEW
        # or CHANGED bound keeps replay BLOCKING.
        adv, why = self.unchanged_update(new_claims)
        if adv:
            self.fail('replay', 'replay not required to gate: ' + why, advisory=True)
        replay = self.load('REPLAY.json', 'replay', required=True, advisory=adv)
        if not replay:
            return
        try:
            if replay.get('status') != 'PASS':
                raise ValueError('replay status must be PASS')
            for key in ('author', 'model'):
                producer = self.meta.get('producer_' + key)
                checker = replay.get(key)
                if not identity(producer) or not identity(checker) or identity(producer) == identity(checker):
                    raise ValueError('replay ' + key + ' must differ from producer_' + key + ': ' + repr(checker) + ' / ' + repr(producer))
            if replay.get('read_producer_code') is not False or replay.get('ran_producer_code') is not False:
                raise ValueError('clean-room replay must attest read_producer_code=false and ran_producer_code=false')
            allowed = self.meta.get('replay_inputs')
            if not isinstance(allowed, dict) or not allowed or not {'proof', 'certificate'} <= set(allowed.values()) or not set(allowed.values()) <= {'proof', 'certificate'}:
                raise ValueError('replay_inputs must contain only proof/PDF and certificate inputs, with both roles')
            inputs = {}
            for path, role in allowed.items():
                if not isinstance(path, str) or path.endswith(('.py', '.sh', '.cpp', '.c', '.sage', '.jl', '.wl')) or role == 'proof' and not path.endswith(('.pdf', '.md', '.tex', '.txt')):
                    raise ValueError('producer code is not an allowed replay input: ' + repr(path))
                inputs[path] = sha(self.s.read(path))
            if replay.get('inputs') != inputs or replay.get('inputs_hash') != sha(canonical(inputs)):
                raise ValueError('replay inputs/hash differ from pinned proof and certificate')
            expected = [r['value'] for r in new_claims]
            values = replay.get('values', [replay.get('value')])
            if not expected or sorted(values) != sorted(expected):
                raise ValueError('replay value(s) must reproduce every new rigorous claim exactly: ' + repr(expected))
            for path_key, hash_key in (('checker', 'checker_sha256'), ('report', 'report_sha256')):
                path = replay.get(path_key)
                if not isinstance(path, str) or not self.s.read(path).strip() or replay.get(hash_key) != sha(self.s.read(path)):
                    raise ValueError('replay needs a nonempty hash-bound ' + path_key)
            if replay.get('arithmetic') not in ('exact', 'interval'):
                raise ValueError('a new bound needs an exact/interval clean-room checker')
            try:
                # 11-04: the heuristic exact/interval source audit is ADVISORY when the
                # checker has exact/interval code mixed with float or unresolved
                # division; a checker with no exact/interval code at all is BLOCKING
                # (Astra 11-04 #3).
                self.producer({'producer': replay['checker'], 'arithmetic': replay['arithmetic']}, 'replay')
                if 'float' in arithmetic(self.s, replay['checker']):
                    raise ValueError('clean-room checker uses float arithmetic')  # r3 #3, any mode
            except ValueError as exc:
                # Astra 11-04 r2 #4: token presence (an unused Fraction import) cannot
                # launder float arithmetic. Any float feature BLOCKS; only the
                # unresolvable-division heuristic is ADVISORY.
                try:
                    feats = arithmetic(self.s, replay['checker'])
                except ValueError:
                    feats = {'float'}
                if 'float' in feats or not feats.intersection({'exact', 'interval'}):
                    raise
                self.fail('replay', str(exc), advisory=True)
            dependencies = set()
            try:
                arithmetic(self.s, replay['checker'], dependencies)
            except ValueError as exc:
                # An import the audit cannot resolve is not packet code (packet code
                # resolves); record it (ADVISORY) and check what did resolve.
                self.fail('replay', 'checker import audit: ' + str(exc), advisory=True)
                dependencies.add(self.s.resolve(replay['checker']))
            checker_path = self.s.resolve(replay['checker'])
            if dependencies != {checker_path}:
                raise ValueError('clean-room checker imports packet code: ' + repr(sorted(dependencies - {checker_path})))
            checker = self.s.text(replay['checker'])
            if replay['checker'].endswith('.py'):
                parsed = ast.parse(checker)
                docstrings = {id(n.value) for n in ast.walk(parsed) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
                access_text = '\n'.join(n.value for n in ast.walk(parsed) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings)
            else:
                access_text = re.sub(r'/\*.*?\*/|//[^\n]*', '', checker, flags=re.S)
            if any(script in access_text for script in [r.get('producer', '') for r in self.claims if isinstance(r, dict)] if script):
                raise ValueError('replay checker references producer code')
        except (KeyError, ValueError, TypeError) as exc:
            self.fail('replay', str(exc), advisory=adv)

    def run(self):
        for key in CHECKS:
            try:
                getattr(self, 'check_' + key)()
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.fail(key, str(exc))
        target = self.meta.get('target', '')
        if not isinstance(target, str) or not re.fullmatch(r'teorth/[\w.-]+(?:#\d+)?', target):
            self.fail('paths', 'PUBLISH.json target must be teorth/REPO[#NUMBER]')
        return {'version': VERSION, 'status': 'FAIL' if any(self.errors.values()) else 'PASS',
                'packet': str(self.s.packet), 'repo_root': str(self.s.root), 'prefix': self.s.prefix,
                'commit': self.s.commit, 'target': target, 'tree_sha256': self.s.fingerprint(),
                'body': str(self.body_path) if self.body_path else None, 'external_sha256': self.extra,
                'checks': {k: {'status': 'FAIL' if v else 'PASS', 'failures': v, 'advisory': self.advisory[k]} for k, v in self.errors.items()},
                'advisory_count': sum(len(v) for v in self.advisory.values()),
                'metadata_sha256': sha(canonical(self.meta)),
                'pinned_files_sha256': {name: sha(data) for name, data in self.s.cache.items()},
                'linter_sha256': sha(Path(__file__).read_bytes()),
                'xlint_sha256': sha(XLINT.read_bytes()) if XLINT.is_file() else None}


def receipt_path(packet, body=None):
    return Path(str(Path(body).expanduser().resolve()) + '.publish-lint.json') if body else Path(packet).expanduser().resolve() / '.publish-lint.json'


def save_receipt(path, result):
    # Preserve every previous receipt, just as source backups are preserved.
    if path.exists():
        backup = Path(str(path) + '.bak-1104x')
        n = 1
        while backup.exists():
            backup = Path(str(path) + '.bak-1104x.' + str(n))
            n += 1
        backup.write_bytes(path.read_bytes())
    path.write_text(json.dumps(dict(result, utc=dt.datetime.now(dt.timezone.utc).isoformat()), indent=2) + '\n')


def validate_checkout(snapshot, pinned_files):
    s = snapshot
    if s.packet != s.root / s.prefix:
        raise ValueError('receipt packet must be the actual checkout directory')
    if git(s.root, 'rev-parse', 'HEAD').decode().strip() != s.commit:
        raise ValueError('publish-lint pinned commit is no longer checkout HEAD')
    for name in s.files():
        local = s.packet / name
        if not local.is_file() or local.is_symlink():
            raise ValueError('publish-lint working packet differs from pin: ' + name)
        oid = git(s.root, 'hash-object', '--no-filters', '--', str(local)).decode().strip()
        if oid != s.entries[s.name(name)][2]:
            raise ValueError('publish-lint working packet differs from pin: ' + name)
    for name, digest in pinned_files.items():
        local = s.root / safe_path(name)
        if local.is_symlink() or not local.is_file() or sha(local.read_bytes()) != digest or sha(s.read_repo(name)) != digest:
            raise ValueError('publish-lint cited dependency differs from pin: ' + name)
    untracked = git(s.root, 'ls-files', '--others', '--exclude-standard', '-z', '--', s.prefix or '.').decode().split('\0')
    for name in untracked:
        if name and '.bak-1104x' not in name and not name.endswith('.publish-lint.json'):
            raise ValueError('publish-lint untracked packet file: ' + name)


def publication_errors(body, target, now=None):
    """Read-only gate validation. No networking, packet execution or receipt issuing."""
    if '#' not in target:
        # gh pr create (edits carry #N): a NEW PR waits while a lane with this upstream has
        # max_open or more of ours open there (11-10: 18 open, none merged since 10-26).
        try:
            import upstream
            root = settings.path('RH_ROOT', Path(__file__).resolve().parent)
            waiting = upstream.new_pr_errors(root, target, now)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            waiting = ['upstream PR list unreadable ({}); a cap that cannot be read refuses'.format(exc)]
        if waiting:
            return ['open-PR cap: ' + e for e in waiting]
    try:
        path = receipt_path('.', body)
        receipt = json_object(path.read_bytes(), str(path))
        now = now or dt.datetime.now(dt.timezone.utc)
        when = dt.datetime.fromisoformat(receipt['utc'].replace('Z', '+00:00'))
        if when.tzinfo is None or not 0 <= (now - when).total_seconds() < TTL:
            raise ValueError('publish-lint receipt expired or future-dated')
        if receipt.get('version') != VERSION or receipt.get('status') != 'PASS' or set(receipt.get('checks', {})) != set(CHECKS) or any(r.get('status') != 'PASS' or r.get('failures') for r in receipt['checks'].values()):
            raise ValueError('publish-lint needs PASS (no blocking findings) on all seven checks')
        if receipt.get('target') != target or receipt.get('body') != str(Path(body).expanduser().resolve()):
            raise ValueError('publish-lint receipt target/body mismatch')
        for name, digest in receipt['external_sha256'].items():
            if sha(Path(name).read_bytes()) != digest:
                raise ValueError('publish-lint external bytes changed: ' + name)
        if str(Path(body).expanduser().resolve()) not in receipt['external_sha256']:
            raise ValueError('publish-lint receipt does not bind PR body')
        if receipt['linter_sha256'] != sha(Path(__file__).read_bytes()) or receipt['xlint_sha256'] != sha(XLINT.read_bytes()):
            raise ValueError('publish-lint/xlint changed; rerun lint')
        s = Snapshot(receipt['packet'], receipt['commit'], receipt['repo_root'], receipt['prefix'])
        if s.fingerprint() != receipt['tree_sha256']:
            raise ValueError('publish-lint packet tree changed')
        validate_checkout(s, receipt['pinned_files_sha256'])
        meta = json_object(s.read('PUBLISH.json'), 'PUBLISH.json')
        if sha(canonical(meta)) != receipt['metadata_sha256']:
            raise ValueError('publish-lint metadata changed')
        return []
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        return ['publish-lint: ' + str(exc) + '; run rh publish-lint PACKET --pr-body ' + str(body)]


def arguments(sub):
    p = sub.add_parser('publish-lint', help='check publication claims, credit, paths, voice, rigor and clean-room replay')
    p.add_argument('packet_dir', type=Path)
    p.add_argument('--pr-body', type=Path)
    p.add_argument('--comments', type=Path, action='append', default=[], help='local PR comment prose (repeatable)')
    p.add_argument('--commit', help='pinned commit (default HEAD)')
    p.add_argument('--repo-root', type=Path, help='Git object database for read-only audits, including bare repositories')
    p.add_argument('--prefix', help='packet path inside --repo-root')
    p.add_argument('--metadata', type=Path, help='audit-only PUBLISH.json override; requires --no-receipt')
    p.add_argument('--no-receipt', action='store_true', help='read-only audit; do not issue/replace a receipt')
    p.add_argument('--json', action='store_true', help='print machine-readable results')


def main(args):
    try:
        if args.metadata and not args.no_receipt:
            raise ValueError('--metadata is audit-only and requires --no-receipt')
        meta = json_object(args.metadata.read_bytes(), str(args.metadata)) if args.metadata else None
        s = Snapshot(args.packet_dir, args.commit, args.repo_root, args.prefix)
        result = Linter(s, args.pr_body, meta, args.comments).run()
        if not args.no_receipt:
            try:
                validate_checkout(s, result['pinned_files_sha256'])
            except ValueError as exc:
                result['status'] = result['checks']['paths']['status'] = 'FAIL'
                result['checks']['paths']['failures'].append({'message': str(exc)})
            save_receipt(receipt_path(args.packet_dir, args.pr_body), result)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for check, row in result['checks'].items():
                print(row['status'] + ' ' + check + ': ' + str(len(row['failures'])) + ' blocking finding(s), ' + str(len(row.get('advisory', []))) + ' advisory')
                for failure in row['failures']:
                    print('  ' + (failure.get('file', '') + ':' + str(failure.get('line', '')) + ': ' if failure.get('file') else '') + failure['message'])
            print(result['status'] + ': ' + str(args.packet_dir) + ' @ ' + s.commit)
        return 0 if result['status'] == 'PASS' else 1
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print('FAIL publish-lint: ' + str(exc), file=sys.stderr)
        return 1
