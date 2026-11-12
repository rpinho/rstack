"""Paper-cut voice check: a draft passes only if it is built from the author's own messages.

The owner, 11-08, after a reply was composed freely and then "checked" against the voice rules:
"Does it tell you to do newspaper clipping?" The writing guide had said paper-cut for two weeks and
was skipped, so it is a check now. A draft lists the bank lines it was cut from, one per line, in
DRAFT.cuts beside it:

    pt:412
    v2:88      # comments are fine

and passes when every cited line exists, the draft's language matches a cited bank's language (no
translating the author's English into Portuguese), and at least `voice_cuts_min_words` (0.70) of its
words and `voice_cuts_min_pairs` (0.40) of its word pairs come from the cited lines. Words that occur
in the message being answered don't count against it: those are the subject swaps. Greeting and
sign-off lines are left out, and so are links and @handles: they name a thing, like a subject word,
and are not phrasing (a link self-reply cut from "Oh, it's here." failed on com, github, https, 11-09).

The banks are private and never in this repo. `RH_VOICE_BANKS` names a JSON file mapping each bank
name to its JSONL file (one {"text": ...} per line) and its language:

    {"v2": {"path": "voice_v2/phrases.jsonl", "lang": "en"}, "pt": {"path": "pt.jsonl", "lang": "pt"}}

Relative paths are read from the JSON file's directory. With no banks configured the check is off.

A pass is recorded in `RH_VOICE_CUTS_STATE` (pass.json, the latest, and passes.jsonl) with a hash of
the normalized text, so a send gate can ask whether exactly this text passed.

    rh voice-cuts DRAFT [--incoming THEIR_MESSAGE]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import settings  # noqa: F401  (loads the host env file, where RH_VOICE_BANKS is set)

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)
PT = set('não nao que de é e o a os as um uma para com também tambem está esta acho mas eu tu te teu tua isso '
         'isto já ja muito mais se quiseres fazer foi vai ser estou estás tens obrigado abraço beijinhos então'.split())
EN = set("the and is are i you it that to of in for with but not this was have just think it's i'm don't "
         "what so on at be my your".split())
GREETING = re.compile(r"^\s*(ol[aá]|oi|hey|hi|hello|dear|querid[oa]|caro|cara)\b[^.!?]{0,40}[,!]?\s*$", re.I)
SIGNOFF = re.compile(r"^\s*(abra[cç]o|abra[cç]os|beijinhos?|beijos?|um abra[cç]o|best|cheers|thanks|thank you|"
                     r"obrigad[oa]|best wishes|all the best|take care)[\s,.!]*$", re.I)
CUT = re.compile(r'^(\w+):(\d+)$')
# A link (with a scheme, www., or a domain followed by a path) or an @handle.
REF = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)+/\S*|(?<![\w@])@\w+", re.I)
QUOTE_START = re.compile(r'^\s*(on .+ wrote:|em .+ escreveu:|-----original message-----)', re.I)


def defaults():
    return dict(voice_cuts_min_words=0.70, voice_cuts_min_pairs=0.40)


def banks_file():
    value = os.environ.get('RH_VOICE_BANKS', '')
    return Path(value).expanduser() if value else None


def load_banks(path=None):
    """{name: (Path, lang)} from the banks file, or {} when none is configured."""
    path = Path(path).expanduser() if path else banks_file()
    if not path:
        return {}
    spec = json.loads(path.read_text())
    out = {}
    for name, entry in spec.items():
        bank = Path(entry['path']).expanduser()
        out[name] = (bank if bank.is_absolute() else path.parent / bank, entry.get('lang', 'en'))
    return out


def state_dir():
    return Path(os.environ.get('RH_VOICE_CUTS_STATE', '.runtime/voice-cuts')).expanduser()


def words(text):
    return [w.lower() for w in WORD.findall(text)]


def language(text):
    ws = words(text)
    return 'pt' if sum(w in PT for w in ws) > sum(w in EN for w in ws) else 'en'


def own_text(text):
    """The draft without quoted history."""
    lines = []
    for line in text.replace('\r', '').splitlines():
        if QUOTE_START.match(line):
            break
        if not line.lstrip().startswith('>'):
            lines.append(line)
    return '\n'.join(lines)


def body(text, signature_names=()):
    lines = [l for l in own_text(text).splitlines() if l.strip()]
    if lines and GREETING.match(lines[0]):
        lines = lines[1:]
    names = {n.casefold() for n in signature_names}
    kept = '\n'.join(l for l in lines if not SIGNOFF.match(l) and l.strip(' ,.!').casefold() not in names)
    return REF.sub(' ', kept)


def text_sha(text):
    """Hash of the text as a reader sees it: no quoted history, whitespace collapsed."""
    return hashlib.sha256(' '.join(own_text(text).split()).encode('utf-8')).hexdigest()


def bank_line(banks, name, n):
    path = banks[name][0]
    try:
        with open(path) as fh:
            for i, line in enumerate(fh, 1):
                if i == n:
                    try:
                        return json.loads(line).get('text', ''), None
                    except ValueError:
                        return None, '{}:{} is not a JSON line'.format(name, n)
    except OSError:
        return None, 'bank {} is not readable'.format(name)
    return None, '{}:{} is past the end of the bank'.format(name, n)


def check(draft, cuts, incoming='', banks=None, cfg=None, signature_names=()):
    """(failures, stats). DRAFT and CUTS are text; CUTS is None when there is no .cuts file."""
    cfg = dict(defaults(), **(cfg or {}))
    banks = load_banks() if banks is None else banks
    if cuts is None:
        return ['VOICE_CUTS_MISSING: no .cuts file, so the draft was composed, not cut. Build it from the '
                "author's own messages and list the bank lines in DRAFT.cuts"], {}
    fails, cited, langs = [], [], set()
    for raw in cuts.splitlines():
        raw = raw.split('#', 1)[0].strip()
        if not raw:
            continue
        m = CUT.match(raw)
        if not m or m.group(1) not in banks:
            fails.append('VOICE_CUTS_BAD: "{}" (use BANK:LINE; banks: {})'.format(raw, ', '.join(sorted(banks))))
            continue
        text, err = bank_line(banks, m.group(1), int(m.group(2)))
        if err:
            fails.append('VOICE_CUTS_BAD: ' + err)
            continue
        cited.append(text)
        langs.add(banks[m.group(1)][1])
    if not cited:
        return fails + ['VOICE_CUTS_MISSING: no usable cuts listed'], {}
    mine = body(draft, signature_names)
    want = language(mine)
    if want not in langs:
        fails.append("VOICE_CUTS_LANGUAGE: the draft is {} but every cut is from a {} bank; cut from the author's "
                     "own {} messages, don't translate".format(want.upper(), '/'.join(sorted(langs)).upper(),
                                                                want.upper()))
    swap = set(words(incoming))
    src = [words(t) for t in cited]
    src_words = {w for s in src for w in s}
    src_pairs = {p for s in src for p in zip(s, s[1:])}
    ws = words(mine)
    counted = [w for w in ws if w not in swap]
    pairs = [p for p in zip(ws, ws[1:]) if not (p[0] in swap and p[1] in swap)]
    wcov = sum(w in src_words for w in counted) / max(1, len(counted))
    pcov = sum(p in src_pairs for p in pairs) / max(1, len(pairs))
    stats = dict(lang=want, cuts=len(cited), word_cover=round(wcov, 2), pair_cover=round(pcov, 2))
    if wcov < cfg['voice_cuts_min_words']:
        missing = sorted({w for w in counted if w not in src_words})[:15]
        fails.append('VOICE_CUTS_WORDS: {:.0%} of the words come from the cited messages (need {:.0%}); not from '
                     'them: {}'.format(wcov, cfg['voice_cuts_min_words'], ', '.join(missing)))
    if pcov < cfg['voice_cuts_min_pairs']:
        fails.append('VOICE_CUTS_PAIRS: {:.0%} of the word pairs come from the cited messages (need {:.0%}): the '
                     'phrasing is new, not cut'.format(pcov, cfg['voice_cuts_min_pairs']))
    return fails, stats


def cuts_for(draft_path):
    path = Path(str(draft_path) + '.cuts')
    return path.read_text() if path.is_file() else None


def record_pass(draft_path, text, stats, state=None):
    state = Path(state) if state else state_dir()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    row = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), draft=str(draft_path),
               draft_sha=hashlib.sha256(text.encode()).hexdigest()[:12], text_sha=text_sha(text), **stats)
    (state / 'pass.json').write_text(json.dumps(row))
    with open(state / 'passes.jsonl', 'a') as fh:
        fh.write(json.dumps(row) + '\n')
    return row


def passed(text, within=dt.timedelta(hours=24), state=None, clock=None):
    """True when exactly this text (normalized) passed within WITHIN."""
    state = Path(state) if state else state_dir()
    clock = clock or dt.datetime.now(dt.timezone.utc)
    want = text_sha(text)
    try:
        lines = (state / 'passes.jsonl').read_text().splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        try:
            row = json.loads(line)
            if row.get('text_sha') == want and clock - dt.datetime.fromisoformat(row['utc']) <= within:
                return True
        except (ValueError, KeyError, TypeError):
            continue
    return False


def add_line(bank, text, source, banks=None, clock=None):
    """Append a line the author dictated or approved, verbatim, to a bank. Returns BANK:LINE.

    11-12: the gate made general drop a line Ricardo had already approved in chat ("You already had the
    line before. I had already approved"). Blocking free composition is the point; blocking his own words
    is not, so what he dictates or approves becomes a bank line that drafts can cut from. Append-only,
    and the source (where and when he said it) is required, so a bank line always traces to him."""
    banks = load_banks() if banks is None else banks
    if bank not in banks:
        raise ValueError('no bank {} (banks: {})'.format(bank, ', '.join(sorted(banks)) or 'none configured'))
    text, source = ' '.join(str(text).split()), ' '.join(str(source).split())
    if not text:
        raise ValueError('the line is empty')
    if len(source.split()) < 2:
        raise ValueError('--source must say where and when he said it, e.g. "chat with general 2026-11-12"')
    path, lang = banks[bank]
    if language(text) != lang:
        raise ValueError('the line reads as {} but bank {} is {}'.format(language(text), bank, lang))
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text().split('\n') if path.exists() else []
    for n, line in enumerate(existing, 1):
        try:
            if ' '.join(json.loads(line).get('text', '').split()) == text:
                return '{}:{}'.format(bank, n)          # already there: same citation, nothing appended
        except ValueError:
            continue
    rows = [l for l in existing if l.strip()]
    row = dict(text=text, source=source,
               added_utc=(clock or dt.datetime.now(dt.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    with open(path, 'a') as fh:
        if existing and existing[-1].strip():
            fh.write('\n')
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    return '{}:{}'.format(bank, len(rows) + 1)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['add']:
        ap = argparse.ArgumentParser(prog='voice-cuts add', description=add_line.__doc__)
        ap.add_argument('text', help='the line, exactly as he said or approved it')
        ap.add_argument('--bank', required=True, help='e.g. dicten or dictpt')
        ap.add_argument('--source', required=True, help='where and when he said it')
        ap.add_argument('--banks', type=Path, help='banks JSON (default: $RH_VOICE_BANKS)')
        a = ap.parse_args(argv[1:])
        try:
            print(add_line(a.bank, a.text, a.source, load_banks(a.banks)))
        except ValueError as exc:
            print('FAIL: ' + str(exc))
            return 1
        return 0
    ap = argparse.ArgumentParser(prog='rh voice-cuts', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('draft', type=Path)
    ap.add_argument('--incoming', type=Path, help='the message being answered (its words are subject swaps)')
    ap.add_argument('--banks', type=Path, help='banks JSON (default: $RH_VOICE_BANKS)')
    a = ap.parse_args(argv)
    banks = load_banks(a.banks)
    if not banks:
        print('FAIL: VOICE_BANKS_MISSING: no banks configured (RH_VOICE_BANKS)')
        return 1
    text = a.draft.read_text()
    names = [n.strip() for n in os.environ.get('RH_SIGNATURE_NAMES', '').split(',') if n.strip()]
    fails, stats = check(text, cuts_for(a.draft), a.incoming.read_text() if a.incoming else '', banks,
                         signature_names=names)
    if stats:
        print('cuts: ' + json.dumps(stats))
    for f in fails:
        print('FAIL: ' + f)
    if fails:
        return 1
    record_pass(a.draft, text, stats)
    print('PASS: cut from {} of the author\'s messages'.format(stats['cuts']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
