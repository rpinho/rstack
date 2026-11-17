"""Build a local field-retro scaffold and separate evidence/proposed-lesson files."""
import json
import math
from pathlib import Path
import re
import lessons
from lane_paths import resolve_lane

SECTIONS = (
    'What we tried',
    'What the results taught us about the problem and the field',
    "What's easy and what's hard",
    'What data is missing',
    'What would make it easier',
    "What's still open",
    'Credits and thanks, by name with links',
    'How hard open science with AI is in this field',
)


def arguments(sub):
    parser = sub.add_parser('retro', help='scaffold a local field retro; never publish or land lessons')
    parser.add_argument('lane')
    parser.add_argument('--out', type=Path)


def local_artifact(value, lane):
    """Read only explicit lane evidence paths; no directory crawl or network."""
    if not value or not isinstance(value, str) or re.match(r'https?://', value):
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = lane / path
    if not path.is_file():
        return dict(path=str(path), missing=True)
    if path.suffix == '.json':
        try:
            return dict(path=str(path), data=json.loads(path.read_text()))
        except ValueError:
            pass
    return dict(path=str(path), text=path.read_text(errors='replace'))


def collect(lane, rh):
    history = rh.rows(lane / 'IDEAS.jsonl')
    ideas = list(rh.latest(history).values())
    outreach = list(rh.latest(rh.rows(lane / 'OUTREACH.jsonl')).values())
    selected = lessons.for_lane(lane, rh)
    own = [r for r in lessons.current(lane.parent.parent, rh).values()
           if resolve_lane(lane.parent.parent, r['lane'], must_exist=False) == lane.name]
    lesson_rows = list({r['id']: r for r in selected + own}.values())
    artifacts = {}
    for row in ideas:
        for field in ('prior_art', 'result_path'):
            value = row.get(field)
            if value:
                artifacts[value] = local_artifact(value, lane)
        for record in row.get('selection_records', []):
            value = record.get('decision_path')
            if value:
                artifacts[value] = local_artifact(value, lane)
    return dict(lane=lane.name, generated=rh.now(), ideas=ideas, idea_history=history,
                selection= rh.rows(lane / 'SEALED_SCORING.jsonl'),
                optimism=rh.rows(lane / 'OPTIMISM.jsonl'),
                outreach_replies=[r for r in outreach if r.get('reply')],
                lessons=lesson_rows, artifacts=artifacts)


def proposals(lane, data, rh):
    result = []
    for idea in data['ideas']:
        reason = idea.get('closed_reason') or idea.get('no_test_reason')
        if idea.get('status') != 'closed' or not isinstance(reason, str) or not reason.strip():
            continue
        # These are attributed observations to review, never automatic rules.
        reason = ' '.join(reason.split())
        reason = re.split(r'(?<=[.!?])\s+', reason)[0].rstrip('.!?')
        claim = 'The recorded close reason for idea {} was: {}.'.format(idea['id'], reason)
        row = lessons.make(lane.name, claim, str(lane / 'IDEAS.jsonl') + '#' + idea['id'],
                           'Revisiting the method or evidence behind idea ' + idea['id'],
                           idea.get('data_tags', []), 'retro', rh)
        result.append(row)
    return result


def result_summary(data):
    """Only known numeric fields enter the scaffold; free text stays local."""
    numeric = ('score', 'metric_value', 'mean', 'sd', 'sem', 'floor', 'lower_bound',
               'expected', 'search_optimism', 'optimism_estimate')
    lines = []
    for index, idea in enumerate(data['ideas']):
        seen = set()
        paths = [idea.get('result_path')]
        paths += [r.get('decision_path') for r in idea.get('selection_records', [])]
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            payload = (data['artifacts'].get(path) or {}).get('data')
            if not isinstance(payload, dict):
                continue
            facts = ['{}={}'.format(key, payload[key]) for key in numeric
                     if type(payload.get(key)) in (float, int) and math.isfinite(payload[key])]
            if type(payload.get('accepted')) is bool:
                facts.append('selection accepted=' + str(payload['accepted']).lower())
            if facts:
                lines.append('- Idea {} evidence {}: {}.'.format(index + 1, len(seen), '; '.join(facts)))
    return '\n'.join(lines) or 'No structured numeric result summaries are recorded; inspect the local evidence packet.'


def draft(lane, data, sources_name):
    ideas = data['ideas']
    closed = sum(r.get('status') == 'closed' for r in ideas)
    tested = sum(bool(r.get('attempt_records') or r.get('result_path')) for r in ideas)
    verification = {}
    for row in ideas:
        level = row.get('verification', 'unrecorded')
        verification[level] = verification.get(level, 0) + 1
    sections = {
        SECTIONS[0]: [
            '{} recorded ideas; {} with attempt/result evidence; {} closed.'.format(len(ideas), tested, closed),
            'Describe the scientific hypotheses, methods and baselines. Use the idea history and close reasons in the local source packet.',
            'Recorded idea IDs: ' + (', '.join(r['id'] for r in ideas) or 'none') + '.',
            'For each closed idea, review its recorded reason in the source packet and include only the scientific finding here.',
        ],
        SECTIONS[1]: [
            'Explain what the measurements support about the problem. Compare baselines, scores and selection outcomes in the source packet; separate observed results from explanations.',
            'Recorded whole-result verification levels: ' + (', '.join('{}={}'.format(k, v) for k, v in sorted(verification.items())) or 'none') + '.',
            result_summary(data),
            'State each claim at its evidenced scope. A finite component does not establish a universal conclusion.',
        ],
        SECTIONS[2]: ['Which parts of the scientific task were tractable? Which failed, and under which conditions? Cite the local results and prior-art receipts.'],
        SECTIONS[3]: ['Name the missing observations, controls, replicates or evaluation data. Distinguish absent data from failed methods.'],
        SECTIONS[4]: ['Describe concrete datasets, benchmarks or methods that would resolve the bottleneck.'],
        SECTIONS[5]: ['List unanswered scientific questions and a test that could distinguish the explanations.'],
        SECTIONS[6]: ['{} prior-art artifacts and {} substantive outreach replies are available in the local packet.'.format(sum(bool(r.get('prior_art')) for r in ideas), len(data['outreach_replies'])), 'Add real names with public links after checking the prior-art receipts and substantive outreach replies. Do not invent endorsements or credit.'],
        SECTIONS[7]: ['Describe the field-specific difficulty of making evidence reproducible with AI: data access, independent checks and the gap between a plausible claim and a supported result.'],
    }
    text = '# {}: field retrospective (local draft)\n\n'.format(lane.name)
    text += 'Unfinished draft for human review. Local evidence packet: [{}]({}).\n'.format(sources_name, sources_name)
    for heading in SECTIONS:
        text += '\n## ' + heading + '\n\n' + '\n\n'.join(sections[heading]) + '\n'
    return text


def main(root, args, rh):
    lane = lessons.lane_at(root, args.lane)
    out = args.out.expanduser().absolute() if args.out else lane / 'RETRO.draft.md'
    sources = out.with_suffix('.sources.json')
    proposed = out.with_suffix('.lessons.proposed.jsonl')
    paths = (out, sources, proposed)
    if len(set(paths)) != 3 or any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError('retro output exists; choose a fresh --out path to preserve the draft')
    data = collect(lane, rh)
    candidates = proposals(lane, data, rh)
    contents = (draft(lane, data, sources.name), json.dumps(data, indent=2, ensure_ascii=False) + '\n',
                lessons.render(candidates))
    out.parent.mkdir(parents=True, exist_ok=True)
    for path, text in zip(paths, contents):
        with path.open('x') as stream:
            stream.write(text)
    print('Local field draft: ' + str(out))
    print('Local evidence (includes private method notes): ' + str(sources))
    print('Proposed lessons ({}; review, then rh lessons add): {}'.format(len(candidates), proposed))
    print('Human reading and egress-gate PASS are required before any public release.')
    return 0
