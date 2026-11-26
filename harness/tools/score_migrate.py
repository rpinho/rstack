#!/usr/bin/env python3
"""Translate legacy scoring rows to sibling *.migrated.jsonl files; default is read-only."""
import argparse
from collections import Counter, defaultdict
import json
import os
import plistlib
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'harness'), str(REPO / 'leaderboard')]
import grade_ledgers
from model_slugs import canon, MODELS
import run_records
import score_verdicts


def paths():
    out = [run_records.runs_path(), run_records.grades_path(),
           *grade_ledgers.ledgers(os.environ.get('RH_LAUNCH_RECEIPTS'))]
    out.extend(r['grade_ledger'] for r in run_records.read_jsonl(run_records.runs_path()) if r.get('grade_ledger'))
    # Read only scoring path settings, never execute a personal env file.
    settings = dict(os.environ)
    try:
        for line in grade_ledgers._env_file().read_text().splitlines():
            key, sep, value = line.removeprefix('export ').partition('=')
            if sep and key.strip() in ('MODEL_LEDGER', 'MODEL_STATE'):
                settings.setdefault(key.strip(), value.strip().strip('\'"'))
    except OSError:
        pass
    installed = Path.home() / 'Library/LaunchAgents/com.ricardo.model-scorer.plist'
    try:
        environment = plistlib.loads(installed.read_bytes()).get('EnvironmentVariables', {})
        for key in ('MODEL_LEDGER', 'MODEL_STATE'):
            if environment.get(key):
                settings.setdefault(key, environment[key])
    except (OSError, ValueError):
        pass
    if settings.get('MODEL_LEDGER'):
        out.append(settings['MODEL_LEDGER'])
    elif settings.get('MODEL_STATE'):
        out.append(Path(settings['MODEL_STATE']) / 'evaluations.jsonl')
    return list(dict.fromkeys(Path(p).expanduser().resolve() for p in out))


def translate(row):
    result = dict(row)
    for key in ('model', 'producer'):
        if result.get(key):
            resolved = canon(result[key])
            if not resolved:
                raise ValueError('unknown model {!r}'.format(result[key]))
            result[key] = resolved
    for key in ('grade', 'outcome'):
        if key in result:
            result[key] = score_verdicts.migrate(result[key], result)
            if result[key] != row[key]:
                result.setdefault('legacy_' + key, row[key])
            score_verdicts.validate(result[key])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledgers', nargs='*', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--write', action='store_true', help='create new siblings exclusively; never overwrite')
    args = parser.parse_args(argv)
    if args.write and args.dry_run:
        parser.error('choose --write or --dry-run')
    counts, mappings, orphans, aliases = defaultdict(Counter), Counter(), [], set()
    for path in args.ledgers or paths():
        if not path.exists():
            print('absent:', path)
            continue
        rows = []
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                original = json.loads(line)
                if not isinstance(original, dict):
                    raise ValueError('expected an object')
                row = translate(original)
            except (ValueError, TypeError) as exc:
                orphans.append(f'{path}:{number}: {exc}')
                continue
            if original.get('model'):
                aliases.add((original['model'], row['model']))
                assert row['model'] in MODELS and canon(row['model']) == row['model']
            for field in ('grade', 'outcome'):
                if field in row:
                    mappings[(str(original[field]), row[field])] += 1
            counts[row.get('model', '<none>')][row.get('grade', row.get('outcome', 'run' if path.name.startswith('model-runs') else 'score_only'))] += 1
            rows.append(row)
        destination = path.with_name(path.stem + '.migrated' + path.suffix)
        print(f'{path}: rows={len(rows)} -> {destination}')
        if args.write:
            if orphans:
                raise ValueError('cannot migrate: fix malformed rows or unknown model keys first')
            with destination.open('x') as stream:
                for row in rows:
                    stream.write(json.dumps(row, sort_keys=True) + '\n')
    for (old, new), count in sorted(mappings.items()):
        print(f'map {old!r} -> {new!r}: {count}')
    for model, values in sorted(counts.items()):
        print(model, ' '.join(f'{key}={value}' for key, value in sorted(values.items())))
    print(f'aliases={len(aliases)} orphan_keys={len(orphans)}')
    for error in orphans:
        print(error)
    print('WRITE' if args.write else 'DRY RUN: no files written')
    return int(bool(orphans))


if __name__ == '__main__':
    raise SystemExit(main())
