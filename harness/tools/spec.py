#!/usr/bin/env python3
"""What the lane is being scored on, pinned to a capture of the challenge, asserted before a round.

Why (2026-11-07, c5 postmortem 3, "the wrong target"). c5 ran 115 rounds against HLA-A*02:01 with
a signal peptide. The challenge target is HLA-A*11:01, mature chain. The lane HAD the right
information: it captured the challenge page verbatim on 10-27, and the capture was still sitting in
the repo while every round used a different sequence. Nothing ever compared the lane's input to the
challenge. Every check we had compared us to ourselves, which is why all of them stayed green.

So a lane declares its target in `SPEC.json`, and `rounds.py start` asserts it before the round:

  * the capture is pinned by sha256, and a capture whose hash does not match is a refusal, because
    an unpinned file proves nothing about what the challenge said;
  * every string the lane is scored against must appear in that capture BYTE FOR BYTE, which is
    the check that would have caught 10-27;
  * declared lengths must match the strings, which catches a leader peptide or a trailing residue;
  * the size cap must be declared and must appear in the capture;
  * every ranking condition is either scored or explicitly excused with a reason, so a condition
    cannot be quietly dropped the way peptide-dependence nearly was.

`diff` is the other half: the capture is a point in time, and a target can change upstream. It
re-reads the live page and reports any scored string that is no longer there. That is the one step
with network, deliberately separate from everything a worker runs, the same split inputs.py uses.

A lane with no external challenge says so (`"challenge": null` with a reason) and still declares
its ranking conditions. The declaration is the thing that was missing; "this lane has no page to
check" is a fine answer, and an empty SPEC.json is not.

    spec.py --lane L check     # what rounds.py start runs; no network
    spec.py --lane L pin       # record the capture's current sha256 into SPEC.json
    spec.py --lane L diff      # re-read the live page and compare; this one uses the network
    spec.py --lane L show
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

SPEC = 'SPEC.json'
TIMEOUT = 60
MAX_BYTES = 32 * 1024 * 1024
AGENT = 'research-harness-spec/1'


def load(lane):
    """The lane's SPEC.json, or None when there is none. Raises ValueError on unreadable JSON."""
    path = Path(lane) / SPEC
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise ValueError('{} is not valid JSON: {}'.format(path, exc))
    if not isinstance(data, dict):
        raise ValueError('{} must be a JSON object'.format(path))
    return data


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def capture_path(lane, spec):
    """The capture, resolved against the lane when the spec gives a relative path."""
    raw = str(spec.get('capture', '') or '').strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (Path(lane) / path)


def ranking_errors(spec):
    """Every ranking condition is scored, or excused by name with a reason. Never neither."""
    errors = []
    conditions = spec.get('ranking')
    if not isinstance(conditions, list) or not conditions:
        return ['SPEC ranking must be a non-empty list of the conditions this lane is ranked on. '
                'c5 nearly dropped peptide-dependence by never writing it down.']
    for n, item in enumerate(conditions, 1):
        if not isinstance(item, dict) or not str(item.get('condition', '')).strip():
            errors.append('SPEC ranking[{}] needs a "condition" naming what is ranked'.format(n))
            continue
        name = str(item['condition']).strip()
        scored = item.get('scored') is True
        excused = str(item.get('excused', '') or '').strip()
        if scored and excused:
            errors.append('SPEC ranking "{}" is both scored and excused; it is one or the other'
                          .format(name))
        elif not scored and not excused:
            errors.append('SPEC ranking "{}" is neither scored nor excused. Either score it, or '
                          'say why not: "excused": "<reason>". A condition with no answer is the '
                          'one that gets dropped.'.format(name))
    return errors


def verify(lane):
    """Errors that refuse a round. Empty means the lane's target matches its pinned capture.

    Missing SPEC.json is an error on purpose, for every lane and not only the one that failed.
    An assertion a lane can skip by not writing the file is not an assertion.
    """
    lane = Path(lane)
    try:
        spec = load(lane)
    except ValueError as exc:
        return ['SPEC unreadable: ' + str(exc)]
    if spec is None:
        return ['NO_SPEC: {} has no {}, so nothing has ever compared this lane\'s target to the '
                'challenge. That is the c5 failure: 115 rounds against the wrong allele with the '
                'right page captured in the repo. Write it (see harness/tools/spec.py) and pin the '
                'capture with `spec.py --lane {} pin`. A lane with no external challenge says '
                '"challenge": null with a reason and still declares its ranking conditions.'
                .format(lane, SPEC, lane)]
    errors = []
    if spec.get('schema') != 1:
        errors.append('SPEC schema must be 1, got {!r}'.format(spec.get('schema')))
    errors.extend(ranking_errors(spec))

    challenge = spec.get('challenge')
    if challenge is None:
        if not str(spec.get('no_challenge_reason', '') or '').strip():
            errors.append('SPEC says there is no challenge to check but gives no reason. '
                          '"no_challenge_reason": "<why this lane has no page or paper to pin>".')
        return errors
    if not str(challenge).strip():
        errors.append('SPEC challenge is empty; name it, or set it to null with a reason')

    # From here the lane claims an external target, so the capture decides everything.
    path = capture_path(lane, spec)
    pinned = str(spec.get('capture_sha256', '') or '').strip().lower()
    if path is None:
        return errors + ['SPEC gives no "capture": the verbatim challenge text this lane is scored '
                         'against. Without it there is nothing to compare the target to.']
    if not path.is_file():
        return errors + ['SPEC capture is missing: {}. The target cannot be checked against a file '
                         'that is not there.'.format(path)]
    if not pinned:
        return errors + ['SPEC capture is not pinned: no "capture_sha256". An unpinned capture '
                         'proves nothing about what the challenge said. Run `spec.py --lane {} '
                         'pin`.'.format(lane)]
    got = digest(path)
    if got != pinned:
        return errors + ['SPEC capture CHANGED: {}\n  pinned {}\n  now    {}\nEvery round scored '
                         'against it compared to something else. This needs a person: re-read the '
                         'page, decide whether the challenge changed or the file was edited, then '
                         'pin it again.'.format(path, pinned, got)]

    text = path.read_text(errors='replace')
    verbatim = spec.get('verbatim')
    if not isinstance(verbatim, dict) or not verbatim:
        errors.append('SPEC verbatim must be a non-empty object of name -> the exact string this '
                      'lane is scored against. This is the check that was missing on 10-27.')
        verbatim = {}
    for name, value in sorted(verbatim.items()):
        if not isinstance(value, str) or not value:
            errors.append('SPEC verbatim "{}" must be a non-empty string'.format(name))
        elif value not in text:
            errors.append('WRONG_TARGET: verbatim "{}" ({} chars) does NOT appear in the capture. '
                          'The lane is scored against something the challenge does not say. '
                          'First 40 chars: {!r}'.format(name, len(value), value[:40]))

    lengths = spec.get('lengths') or {}
    if not isinstance(lengths, dict):
        errors.append('SPEC lengths must be an object of name -> expected length')
    else:
        for name, want in sorted(lengths.items()):
            if name not in verbatim:
                errors.append('SPEC lengths names "{}", which is not in verbatim'.format(name))
            elif not isinstance(want, int) or want < 0:
                errors.append('SPEC lengths "{}" must be a non-negative integer'.format(name))
            elif len(verbatim[name]) != want:
                errors.append('WRONG_LENGTH: "{}" is {} long, the spec says {}. A leader peptide '
                              'or a trailing residue is exactly how c5 went wrong.'
                              .format(name, len(verbatim[name]), want))

    # The weak check, kept because what it catches is worth it: a cap that does not appear at all
    # means the capture is not the page this cap came from. A number that does appear proves
    # little, and this says so rather than implying otherwise.
    caps = spec.get('size_cap')
    if not isinstance(caps, dict) or not caps:
        errors.append('SPEC size_cap must be a non-empty object of the limits the submission has '
                      'to respect (lengths, slots, counts). A cap nobody wrote down is a cap '
                      'nobody checks.')
    else:
        for name, value in sorted(caps.items()):
            if str(value) not in text:
                errors.append('SPEC size_cap "{}" = {} does not appear anywhere in the capture. '
                              'Either the cap is wrong or the capture is not the page it came '
                              'from.'.format(name, value))
    return errors


def fetch(url, max_bytes=None):
    max_bytes = MAX_BYTES if max_bytes is None else max_bytes
    if not str(url).lower().startswith(('http://', 'https://')):
        raise ValueError('only http(s) URLs are read, got: ' + str(url)[:60])
    req = urllib.request.Request(url, headers={'User-Agent': AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if not str(r.geturl()).lower().startswith(('http://', 'https://')):
                raise ValueError('redirected off http(s)')
            body = r.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise ValueError('fetch failed: {}'.format(getattr(exc, 'reason', exc)))
    if len(body) > max_bytes:
        raise ValueError('page is larger than the {} byte cap'.format(max_bytes))
    if not body:
        raise ValueError('the URL returned an empty body')
    return body.decode('utf-8', errors='replace')


def diff(lane):
    """Compare the live page with the pinned capture. Returns (gone, note).

    A string the lane is scored against that is no longer on the page is the signal: the target
    changed upstream, or the capture was never of this page. Either way a person decides.
    """
    spec = load(lane)
    if spec is None:
        raise ValueError('no {} in {}'.format(SPEC, lane))
    url = str(spec.get('capture_url', '') or '').strip()
    if not url:
        raise ValueError('SPEC has no "capture_url", so the live page cannot be re-read')
    live = fetch(url)
    verbatim = spec.get('verbatim') or {}
    gone = sorted(name for name, value in verbatim.items()
                  if isinstance(value, str) and value and value not in live)
    return gone, '{} scored string(s) checked against {}'.format(len(verbatim), url)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--lane', required=True, type=Path)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('check', help='what rounds.py start runs; no network')
    sub.add_parser('pin', help="record the capture's current sha256 into SPEC.json")
    sub.add_parser('diff', help='re-read the live page and compare (uses the network)')
    sub.add_parser('show', help='print the spec')
    a = p.parse_args(argv)

    if a.action == 'show':
        try:
            spec = load(a.lane)
        except ValueError as exc:
            print('REFUSED: ' + str(exc), file=sys.stderr)
            return 2
        if spec is None:
            print('no {} in {}'.format(SPEC, a.lane), file=sys.stderr)
            return 2
        print(json.dumps(spec, indent=2, sort_keys=True))
        return 0

    if a.action == 'pin':
        try:
            spec = load(a.lane)
        except ValueError as exc:
            print('REFUSED: ' + str(exc), file=sys.stderr)
            return 2
        if spec is None:
            print('REFUSED: no {} in {} to pin'.format(SPEC, a.lane), file=sys.stderr)
            return 2
        path = capture_path(a.lane, spec)
        if path is None or not path.is_file():
            print('REFUSED: capture missing: {}'.format(path), file=sys.stderr)
            return 2
        got = digest(path)
        was = str(spec.get('capture_sha256', '') or '')
        spec['capture_sha256'] = got
        spec['pinned_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (Path(a.lane) / SPEC).write_text(json.dumps(spec, indent=2, sort_keys=True) + '\n')
        print('pinned {}\n  sha256 {}{}'.format(path, got,
              '' if not was or was == got else '\n  WAS    ' + was +
              '\n  The capture changed since it was last pinned. Say in the lane log what '
              'changed and why this is the right file now.'))
        return 0

    if a.action == 'diff':
        try:
            gone, note = diff(a.lane)
        except ValueError as exc:
            print('REFUSED: ' + str(exc), file=sys.stderr)
            return 2
        print(note)
        if gone:
            print('CHANGED UPSTREAM: {} no longer appear(s) on the live page: {}\nThe target may '
                  'have moved under this lane. Re-capture, diff the text, and pin again before '
                  'the next round.'.format(len(gone), ', '.join(gone)), file=sys.stderr)
            return 2
        print('every scored string is still on the live page')
        return 0

    errors = verify(a.lane)
    for e in errors:
        print('REFUSED: ' + e, file=sys.stderr)
    if errors:
        return 2
    print('SPEC ok: the target, its lengths, the size cap and every ranking condition match the '
          'pinned capture')
    return 0


if __name__ == '__main__':
    sys.exit(main())
