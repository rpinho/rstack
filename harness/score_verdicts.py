"""Verdicts accepted by score writers; legacy translation is explicit and lossless."""
import re

ALLOWED = 'pass | partial | fail | harness_fail | void: <reason>'


def validate(value):
    if value in ('pass', 'partial', 'fail', 'harness_fail'):
        return value
    if isinstance(value, str) and re.fullmatch(r'void: [^\r\n]+', value) and value[6:].strip():
        return value
    raise ValueError('unknown verdict {!r}; allowed: {}'.format(value, ALLOWED))


def migrate(value, row=None):
    """Preserve every legacy row; ambiguous outcomes are void, never invented passes."""
    row = row or {}
    try:
        return validate(value)
    except ValueError:
        pass
    text = str(value or '').strip().lower()
    if text in ('held', 'holds', 'confirmed', 'caught'):
        return 'pass'
    if text in ('overturned', 'fails', 'missed', 'not held'):
        return 'fail'
    if text == 'retracted':
        return 'void: retracted'
    reason = str(row.get('reason') or row.get('note') or '').strip()
    if text.startswith('ungraded'):
        reason = text.partition(':')[2].strip() or reason
        if 'quota' in reason.lower() or row.get('grader') == 'quota':
            return 'void: quota'
        if (row.get('grader') == 'harness' or reason.startswith(('harness:', 'workdir incomplete:',
                                                               'review requires access'))):
            return 'harness_fail'
        return 'void: ' + (' '.join(reason.split()) or 'ungraded')
    return 'void: legacy ' + (' '.join(text.split()) or 'missing verdict')


def row(value):
    out = dict(value)
    for key in ('grade', 'outcome'):
        if key in out:
            out[key] = validate(out[key])
    return out


def observation(value, row=None):
    """Translate the adapters' finite historical vocabulary before strict writes."""
    if value in ('held', 'overturned', 'ungraded'):
        return migrate(value, row)
    return validate(value)
