"""Read a user-supplied terms file. rstack ships no terms of its own.

Why there is no built-in list: a list of the words you do not want in a context is itself a
summary of what you are working on. Shipped in a public repository, or even as a fallback in a
script that gets copied around, it leaks the very thing it protects. So the tools that use one
(`relay`, `reload-lint.py`) read it from a file you supply with --terms or RSTACK_TERMS_FILE, and
with no file they do nothing and say so.

Format, one entry per line, `#` comments:

    projectcodename                          a term (case-insensitive; word-bounded at the ends
    internal-sku                             that are letters or digits)
    marker build id = \\bbuild-\\d{4}\\b       working detail that makes a nearby term a problem
    standalone ticket dump = \\bTKT-\\d{6}\\b   never right in a reloaded file, term or not

`relay` uses terms only. `reload-lint.py` uses all three (see its docstring for why a term alone
is not enough there).
"""
import os
from pathlib import Path
import re

ENV = 'RSTACK_TERMS_FILE'


class TermsUnreadable(Exception):
    """A terms file was configured but could not be read or parsed."""


class Terms:
    def __init__(self, terms=(), markers=(), standalone=(), source=None):
        self.terms = list(terms)            # [(name, compiled)]
        self.markers = list(markers)        # [(label, compiled)]
        self.standalone = list(standalone)  # [(label, compiled)]
        self.source = source

    def __bool__(self):
        return bool(self.terms or self.standalone)

    def term_hits(self, text):
        return sorted({name for name, rx in self.terms if rx.search(text)})

    def marker_hits(self, text):
        return [label for label, rx in self.markers if rx.search(text)]

    def standalone_hits(self, text):
        return [label for label, rx in self.standalone if rx.search(text)]


def compile_term(term):
    left = r'\b' if term[:1].isalnum() else ''
    right = r'\b' if term[-1:].isalnum() else ''
    return re.compile(left + re.escape(term) + right, re.I)


def _labelled(rest, kind, path, n):
    label, sep, rx = rest.partition(' = ')
    if not sep or not label.strip() or not rx.strip():
        raise TermsUnreadable('{}:{}: expected "{} LABEL = REGEX"'.format(path, n, kind))
    try:
        return label.strip(), re.compile(rx.strip(), re.I)
    except re.error:
        raise TermsUnreadable('{}:{}: bad regex'.format(path, n))


def configured_path(explicit=None):
    value = explicit or os.environ.get(ENV)
    return Path(value).expanduser() if value else None


def load(explicit=None):
    """Terms from the configured file; empty Terms if none is configured.

    Raises TermsUnreadable if a file is configured but missing or malformed: a configured filter
    that silently becomes no filter is the failure this module must not have.
    """
    path = configured_path(explicit)
    if path is None:
        return Terms()
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        raise TermsUnreadable('{}: cannot be read'.format(path))
    terms, markers, standalone = [], [], []
    for n, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith('#'):
            continue
        head, _, rest = entry.partition(' ')
        if head == 'marker':
            markers.append(_labelled(rest, 'marker', path, n))
        elif head == 'standalone':
            standalone.append(_labelled(rest, 'standalone', path, n))
        else:
            terms.append((entry, compile_term(entry)))
    return Terms(terms, markers, standalone, source=path)
