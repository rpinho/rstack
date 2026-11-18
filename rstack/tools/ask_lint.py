#!/usr/bin/env python3
"""Refuse mechanical work addressed to the owner.

lint(text, reason_tag=None) returns refusal messages, or [] to allow. A reason
must be one of HIS_ONLY; inline [his-only: class] tags work too. Tags declare why
the owner is needed; this text lint cannot verify that declaration.
"""
import argparse
import re
import sys

HIS_ONLY = ('auth', 'money', 'delete', 'attest', 'first-email', 'terms', 'judgment')
TAG = re.compile(r'\[his-only:\s*([^\]]+)\]', re.I)

# Imperatives, polite questions, and explicit second-person requests. Requiring
# an address avoids treating "I uploaded it" or "the upload failed" as asks.
ADDRESS = (
    r'(?:^|[.!?;:\n]\s*|,\s*|\b(?:and\s+then|and|then)\s+)'
    r'[\s>*#\-\d.)]*(?:\[[ xX]\]\s*)?'
    r'(?:Ricardo[, :]+\s*)?'
    r'(?:(?:please|kindly|just)\s+)?'
    r'(?:(?:(?:can|could|would|will)\s+you|'
    r'you\s+(?:(?:need|have)\s+to|should|must|can)|'
    r'you(?:\x27ll|’ll)|you|I\s+need\s+you\s+to)\s+)?'
    r'(?:(?:please|kindly|just)\s+)?'
)

# Keep each action separate: test cases exercise every entry in this table.
MECHANICAL = (
    ('upload', r'upload\b'),
    ('paste', r'paste\b'),
    ('click', r'click\b'),
    ('press', r'press\b'),
    ('fill in', r'fill\s+(?:in|out)\b'),
    ('copy to', r'copy\b[^\n.!?;]*?\b(?:to|into)\b'),
    ('type', r'type\b'),
    ('attach', r'attach\b'),
    ('run', r'run\b'),
    ('open', r'open\b'),
    ('submit at', r'submit\b'),
    ('enter', r'enter\b'),
    ('follow link', r'follow\b[^\n.!?;]*?\blink\b'),
)
ACTIONS = tuple((name, re.compile(ADDRESS + r'(?P<step>' + pattern + r'[^\n.!?;]*)', re.I))
                for name, pattern in MECHANICAL)
LOGIN_LINK = re.compile(
    r'\b(?:magic[ -]link|(?:log[ -]?in|sign[ -]?in|authentication|auth)[ -]link)\b|'
    r'\blink\b.*\b(?:log\s*in|sign\s*in|authenticate)\b', re.I)


def lint(text, reason_tag=None):
    """Return 'do it yourself: <step>' for each unexcused owner action.

    Direct his-only verbs (sign in, log in, approve, read and OK, decide, pay)
    are allowed. They do not excuse a separate upload/paste/etc. A mechanical
    login-link instruction is allowed only with an explicit auth reason.
    """
    tags = [m.group(1).strip().lower() for m in TAG.finditer(text)]
    if reason_tag is not None:
        tags.append(reason_tag.strip().lower())
    invalid = [tag for tag in tags if tag not in HIS_ONLY]
    if invalid:
        raise ValueError('unknown his-only class: ' + ', '.join(invalid))
    clean = TAG.sub('', text)
    found = []
    for _, pattern in ACTIONS:
        for match in pattern.finditer(clean):
            # Coordination keeps its explicit subject: "I will read and upload"
            # is our work. "I will read, then you upload" still addresses him.
            clause = re.split(r'[.!?;\n]', clean[:match.start()])[-1].strip()
            address = clean[match.start():match.start('step')]
            if (re.match(r'(?:I|we)\b', clause, re.I)
                    and not re.search(r'\b(?:you|Ricardo)\b', address, re.I)):
                continue
            step = match.group('step').strip(' \t,')
            # Clicking/following a login link is authentication, never a generic
            # mechanical exception under judgment, money, etc.
            allowed = 'auth' in tags if LOGIN_LINK.search(step) else bool(tags)
            if not allowed:
                found.append((match.start('step'), 'do it yourself: ' + step))
    return [message for _, message in sorted(set(found))]


def lint_review_item(item, reason_tag=None):
    """Review-add's visible owner asks: title, note and checkbox labels.

    A --his-only reason applies to this item. Inline reasons stay local to their
    field so a tagged checkbox cannot excuse an unrelated mechanical note.
    """
    if reason_tag is None:
        reason_tag = item.get('his_only')
    texts = [item.get('title', ''), item.get('note', '')]
    texts.extend(check.get('label', '') for check in item.get('checks', []))
    return [message for text in texts for message in lint(text, reason_tag)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--his-only', choices=HIS_ONLY)
    parser.add_argument('text', nargs='?', help='text to lint; defaults to stdin')
    args = parser.parse_args(argv)
    try:
        messages = lint(args.text if args.text is not None else sys.stdin.read(), args.his_only)
    except ValueError as exc:
        parser.error(str(exc))
    for message in messages:
        print(message, file=sys.stderr)
    return 2 if messages else 0


if __name__ == '__main__':
    sys.exit(main())
