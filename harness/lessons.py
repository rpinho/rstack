"""Cross-lane lessons: append-only revisions serialized by the harness root lock."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import uuid

SOURCES = ('retro', 'close', 'referee', 'correction', 'backfill')
STATUSES = ('active', 'superseded', 'promoted')


def one_line(value, field):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '\n\r\0'):
        raise ValueError(field + ' must be nonempty one-line text')
    return ' '.join(value.split())


def tags(values):
    if isinstance(values, str):
        values = [values]
    return sorted({one_line(tag, 'tag').casefold() for value in (values or [])
                   for tag in value.split(',') if tag.strip()})


def terms(values):
    """Match explicit tags and words inside lane search phrases or domain tags."""
    normalized = tags(values)
    return set(normalized) | {word for value in normalized
                              for word in re.findall(r'[^\W_]+', value, flags=re.UNICODE)}


def lane_at(root, name):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name):
        raise ValueError('invalid lane name')
    lane = Path(root).expanduser().resolve() / 'lanes' / name
    if not lane.is_dir():
        raise ValueError('lane directory missing: ' + name)
    return lane


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('lesson utc must include timezone')
    return parsed.astimezone(dt.timezone.utc)


def validate(row):
    for field in ('id', 'utc', 'lane', 'source', 'lesson', 'evidence', 'applies_when', 'status'):
        one_line(row.get(field), field)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', row['lane']):
        raise ValueError('invalid lesson lane')
    if row['source'] not in SOURCES or row['status'] not in STATUSES:
        raise ValueError('invalid lesson source or status')
    if len(re.split(r'(?<=[.!?])\s+', row['lesson'])) > 2:
        raise ValueError('lesson must be at most 2 sentences')
    timestamp(row['utc'])
    if not isinstance(row.get('tags'), list) or row['tags'] != tags(row['tags']):
        raise ValueError('lesson tags must be normalized lowercase strings')
    if not isinstance(row.get('supersedes'), list) or any(not isinstance(x, str) or not x for x in row['supersedes']):
        raise ValueError('supersedes must be a list of lesson ids')
    if not isinstance(row.get('promoted_to'), str) or (row['status'] == 'promoted' and not row['promoted_to'].strip()):
        raise ValueError('promoted lessons require promoted_to')
    return row


def _current(root, rh):
    history = rh.rows(Path(root) / 'LESSONS.jsonl')
    for row in history:
        validate(row)
    return rh.latest(history)


def current(root, rh):
    root = Path(root).expanduser().resolve()
    if not (root / 'LESSONS.jsonl').exists():
        return {}  # An empty read (including a dry run) creates nothing.
    with rh.locked(root):
        return _current(root, rh)


def target_file(root, value, field):
    value = one_line(str(value), field)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(root) / path
    if not path.is_file():
        raise ValueError(field + ' must name an existing file: ' + value)
    return value


def make(lane, lesson, evidence, applies_when, values, source, rh):
    return validate(dict(id='L-' + uuid.uuid4().hex, utc=rh.now(), lane=lane, source=source,
                         tags=tags(values), lesson=one_line(lesson, 'lesson'),
                         evidence=one_line(str(evidence), 'evidence'),
                         applies_when=one_line(applies_when, 'applies_when'),
                         status='active', supersedes=[], promoted_to=''))


def _replacement(old, new, rh):
    if old['id'] == new['id'] or old['status'] == 'superseded' or new['status'] == 'superseded':
        raise ValueError('supersession needs distinct current lessons and a live replacement')
    old = dict(old, utc=rh.now(), status='superseded')
    new = dict(new, utc=rh.now(), supersedes=sorted(set(new['supersedes']) | {old['id']}))
    return old, new


def add(root, rh, *, lane, lesson, evidence, applies_when, values=(), source='retro', supersedes=(), promoted_to=''):
    root = Path(root).expanduser().resolve()
    row = make(lane, lesson, evidence, applies_when, values, source, rh)
    if not re.match(r'https?://\S+$', row['evidence']):
        target_file(root, row['evidence'].split('#', 1)[0], 'evidence')
    if promoted_to:
        row.update(status='promoted', promoted_to=target_file(root, promoted_to, 'promoted_to'))
    root.mkdir(parents=True, exist_ok=True)
    with rh.locked(root):
        existing = _current(root, rh)
        updates = []
        for key in dict.fromkeys(supersedes):
            if key not in existing:
                raise ValueError('unknown lesson id: ' + key)
            old, row = _replacement(existing[key], row, rh)
            updates.append(old)
        for update in updates + [row]:
            rh.append(root / 'LESSONS.jsonl', validate(update))
    return row


def supersede(root, key, replacement, rh):
    root = Path(root).expanduser().resolve()
    with rh.locked(root):
        existing = _current(root, rh)
        if key not in existing or replacement not in existing:
            raise ValueError('unknown lesson id')
        old, new = _replacement(existing[key], existing[replacement], rh)
        rh.append(root / 'LESSONS.jsonl', validate(old))
        rh.append(root / 'LESSONS.jsonl', validate(new))
    return new


def promote(root, key, path, rh):
    root = Path(root).expanduser().resolve()
    path = target_file(root, path, 'promoted_to')
    with rh.locked(root):
        existing = _current(root, rh)
        if key not in existing:
            raise ValueError('unknown lesson id: ' + key)
        if existing[key]['status'] == 'superseded':
            raise ValueError('cannot promote a superseded lesson')
        row = validate(dict(existing[key], status='promoted', promoted_to=path, utc=rh.now()))
        rh.append(root / 'LESSONS.jsonl', row)
    return row


def for_lane(lane, rh, idea=None, values=(), n=12):
    if n < 0:
        raise ValueError('n must be nonnegative')
    cfg = rh.lane_config(lane)
    context = tags(values) + [lane.name]
    for field in ('lesson_tags', 'tags', 'keywords', 'depth_tags'):
        context += tags(cfg.get(field, []))
    ideas = rh.latest(rh.rows(lane / 'IDEAS.jsonl'))
    if idea:
        matches = [r for key, r in ideas.items() if key.startswith(idea)]
        if len(matches) != 1:
            raise ValueError('idea id must match exactly one idea in this lane')
    else:
        matches = list(ideas.values())
    for row in matches:
        context += tags(row.get('data_tags', [])) + tags(row.get('tags', []))
    context = terms(context)
    candidates = [r for r in current(lane.parent.parent, rh).values() if r['status'] != 'superseded']
    # Cross-lane transfer first; within each group, relevance then recency.
    ranked = sorted(candidates, key=lambda r: (r['lane'] != lane.name,
                    sum(bool(context.intersection(terms([tag]))) for tag in r['tags']), timestamp(r['utc']), r['id']), reverse=True)
    # 11-11, friends: with more than n cross-lane lessons in the store, the lane's own never made the cut,
    # so a lesson friends had just paid for never reached its next jobs. Each group gets half the slots,
    # and either fills what the other leaves.
    cross = [r for r in ranked if r['lane'] != lane.name]
    own = [r for r in ranked if r['lane'] == lane.name]
    take_cross = min(len(cross), max(n - len(own), n - n // 2))
    take_own = min(len(own), n - take_cross)
    return cross[:take_cross] + own[:take_own]


def render(rows):
    return '\n'.join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + ('\n' if rows else '')


def snapshot(rows):
    return hashlib.sha256(render(rows).encode()).hexdigest()


def record_read(lane, rh):
    selected = for_lane(lane, rh)
    receipt = dict(utc=rh.now(), command='rh lessons for {} -n 12'.format(lane.name),
                   lesson_ids=[row['id'] for row in selected], lessons_sha256=snapshot(selected))
    with (lane / 'LESSONS_READ.json').open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    print(receipt['command'])
    print(render(selected), end='')
    if not selected:
        print('(no lessons yet)')
    return receipt


def close_options(args, required):
    lesson, reason = (args.lesson or '').strip(), (args.no_lesson or '').strip()
    if args.lesson is not None and not lesson:
        raise ValueError('--lesson must be nonempty')
    if args.no_lesson is not None and not reason:
        raise ValueError('--no-lesson needs a nonempty reason')
    if required and not (lesson or reason):
        raise ValueError('lessons_required: close needs --lesson TEXT or --no-lesson REASON')
    if args.lesson_tags and not lesson:
        raise ValueError('--lesson-tags requires --lesson')
    if lesson and len(re.split(r'(?<=[.!?])\s+', one_line(lesson, 'lesson'))) > 2:
        raise ValueError('lesson must be at most 2 sentences')
    return lesson, reason


def close_record(lane, row, args, rh):
    required = rh.lane_config(lane).get('lessons_required', False)
    lesson, reason = close_options(args, required)
    row.update(lessons_required_at_close=required, no_lesson_reason=reason)
    if lesson:
        result = add(lane.parent.parent, rh, lane=lane.name, lesson=lesson,
                     evidence=str(lane / 'IDEAS.jsonl'),
                     applies_when='Testing ideas with tags: ' + (', '.join(tags(args.lesson_tags or row.get('data_tags', []))) or lane.name),
                     values=args.lesson_tags or row.get('data_tags', []), source='close')
        row['lesson_ids'] = [result['id']]
    return row


def warnings(lane, rh):
    root = lane.parent.parent
    result, referenced = [], set()
    sweep_path = lane / 'SWEEP.toml'
    enabled = sweep_path.is_file() and rh.config(sweep_path).get('enabled', False)
    runs = rh.rows(lane / 'SWEEP_RUNS.jsonl')
    if enabled and runs and not runs[-1].get('lesson_ids'):
        result.append('lessons-unread: enabled lane last sweep receipt shows no lessons')
    active = [r for r in current(root, rh).values() if r['status'] == 'active']
    old = [r for r in active if timestamp(rh.now()) - timestamp(r['utc']) > dt.timedelta(days=90)]
    if not old:
        return result
    for other in sorted((root / 'lanes').iterdir()):
        if not other.is_dir():
            continue
        read = other / 'LESSONS_READ.json'
        if read.is_file():
            referenced.update(json.loads(read.read_text()).get('lesson_ids', []))
        for name in ('SWEEP_RUNS.jsonl', 'IDEAS.jsonl'):
            for row in rh.rows(other / name):
                referenced.update(row.get('lesson_ids', []))
    for row in old:
        if row['id'] not in referenced:
            result.append('lesson-stale: {} active over 90 days with no recorded reference'.format(row['id']))
    return result


def arguments(sub):
    actions = sub.add_parser('lessons', help='share evidence-backed lessons across lanes').add_subparsers(dest='action', required=True)
    add_parser = actions.add_parser('add')
    for field in ('lane', 'lesson', 'evidence', 'applies-when'):
        add_parser.add_argument('--' + field, required=True)
    add_parser.add_argument('--source', choices=SOURCES, default='retro')
    add_parser.add_argument('--tags', nargs='+', default=[])
    add_parser.add_argument('--supersedes', nargs='+', default=[])
    add_parser.add_argument('--promoted-to', default='', help='existing enforcing test, lint or rule file')
    listing = actions.add_parser('list')
    listing.add_argument('--lane')
    listing.add_argument('--status', choices=STATUSES)
    listing.add_argument('--tags', nargs='+', default=[])
    listing.add_argument('-n', type=int)
    relevant = actions.add_parser('for')
    relevant.add_argument('lane')
    relevant.add_argument('--idea')
    relevant.add_argument('--tags', nargs='+', default=[])
    relevant.add_argument('-n', type=int, default=12)
    replace = actions.add_parser('supersede')
    replace.add_argument('id')
    replace.add_argument('--by', required=True, help='replacement lesson id')
    promoted = actions.add_parser('promote')
    promoted.add_argument('id')
    promoted.add_argument('--to', required=True)


def main(root, args, rh):
    root = Path(root).expanduser().resolve()
    if args.action == 'add':
        row = add(root, rh, lane=args.lane, lesson=args.lesson, evidence=args.evidence,
                  applies_when=args.applies_when, values=args.tags, source=args.source,
                  supersedes=args.supersedes, promoted_to=args.promoted_to)
        print(row['id'])
    elif args.action == 'supersede':
        print(supersede(root, args.id, args.by, rh)['id'])
    elif args.action == 'promote':
        print(promote(root, args.id, args.to, rh)['id'])
    else:
        if args.action == 'for':
            selected = for_lane(lane_at(root, args.lane), rh, args.idea, args.tags, args.n)
        else:
            selected = sorted(current(root, rh).values(), key=lambda r: (timestamp(r['utc']), r['id']), reverse=True)
            selected = [r for r in selected if (not args.lane or r['lane'] == args.lane)
                        and (not args.status or r['status'] == args.status)
                        and (not args.tags or set(tags(args.tags)).intersection(r['tags']))]
            if args.n is not None:
                if args.n < 0:
                    raise ValueError('n must be nonnegative')
                selected = selected[:args.n]
        print(render(selected), end='')
    return 0
