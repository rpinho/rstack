#!/usr/bin/env python3
"""Run one bounded setup across toy + two past-competition mock holdouts."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import platform
import importlib.metadata
import resource
import signal
import shutil
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO/'harness')]
from bench.cases import (CASES, SETUPS, VERSION, CPU_SECONDS, PROCESS_SECONDS,
                         MODEL_SECONDS, FAMILIES, freeze_spec, stub_plan, validate_plan)
from bench.setup_data import file_sha, prepare, write_json


def bounded(command, log, *, timeout, prompt=None, cpu=None, cwd=None):
    """Own the process group, bound CPU when requested, and terminate descendants on failure."""
    def limits():
        if cpu is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    start = time.monotonic()
    with Path(log).open('x') as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
            preexec_fn=limits if cpu is not None else None, text=True)
        try:
            process.communicate(prompt, timeout=timeout)
            if process.returncode:
                raise RuntimeError('process exited {}; see {}'.format(process.returncode, Path(log).name))
        finally:
            # A failed launcher may leave children. End the entire owned group, even if its leader exited.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    return time.monotonic()-start


def usage_from_log(path):
    """Use exact provider usage; never price subscription tokens or apportion a shared prompt."""
    turns = []
    for line in Path(path).read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get('item', {})
        if isinstance(item, dict) and item.get('type') not in (None, 'agent_message', 'reasoning', 'error'):
            raise ValueError('model used a tool; scorecard refused')
        if event.get('type') == 'turn.completed':
            turns.append(event.get('usage'))
    if len(turns) == 1 and isinstance(turns[0], dict):
        usage = turns[0]
        keys = ('input_tokens', 'cached_input_tokens', 'output_tokens')
        if all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys):
            return dict(tokens={k: usage[k] for k in keys}, usd=None,
                        usd_reason='Codex CLI usage events do not report billed dollars; no inferred price.',
                        source='Codex turn.completed usage', log_sha256=file_sha(path))
    return dict(tokens=None, usd=None, tokens_reason='No unique complete usage event in backend log.',
                usd_reason='Backend did not report billed dollars.', log_sha256=file_sha(path))


def schema(cases):
    recipe = dict(type='object', additionalProperties=False,
        properties=dict(family=dict(type='string', enum=list(FAMILIES)),
                        strength=dict(type='string', enum=['small', 'medium'])),
        required=['family', 'strength'])
    return dict(type='object', additionalProperties=False, required=['sequence', 'recipes'],
        properties=dict(sequence=dict(type='array', items=dict(type='integer'), minItems=10, maxItems=10),
            recipes=dict(type='object', additionalProperties=False,
                properties={case: dict(type='array', items=recipe, minItems=3, maxItems=3)
                            for case in cases if case != 'toy'},
                required=[case for case in cases if case != 'toy'])))


def installed_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def generate_plan(args, cases, artifacts):
    if args.backend == 'stub':
        plan = stub_plan(cases)
        write_json(artifacts/'plan.json', plan)
        return plan, dict(tokens=None, usd=0., tokens_reason='Local stub; no model request.',
                          source='stub'), 0.
    # Use the repository's backend command builder; keep all changes within bench/.
    from agent_executor import command
    workspace = artifacts/'model-workspace'
    workspace.mkdir()
    output = artifacts/'model-response.json'
    schema_path = artifacts/'output-schema.json'
    write_json(schema_path, schema(cases))
    cmd = command('codex', 'codex', args.model, 'low', workspace, output)
    cmd[cmd.index('workspace-write')] = 'read-only'
    cmd[-1:-1] = ['--json', '--ephemeral', '--output-schema', str(schema_path),
        '-c', 'web_search="disabled"', '-c', 'mcp_servers={}']
    for feature in ('shell_tool', 'apps', 'plugins', 'multi_agent', 'code_mode_host',
                    'browser_use', 'computer_use', 'image_generation', 'view_image'):
        cmd[-1:-1] = ['--disable', feature]
    prompt = (
        'Return only the JSON matching the supplied schema. Do not call any tools, browse, '
        'read files, spawn agents or contact anyone. This is one cheap regression scorecard, '
        'not an open-ended research sweep. The toy is the exact squares of integers 0 through 9. '
        'For each regression case return exactly one recipe from each family: ridge, extra_trees, '
        'hist_gradient_boosting. Choose strength small or medium to balance score with CPU. '
        'All fits are implemented by trusted local code; do not write code. Small/medium use '
        'Ridge alpha 1/10; ExtraTrees 24/48 trees with max depth 6/10; histogram boosting 24/48 '
        'fixed iterations with 7/15 leaves. At most 1600 feature groups per case. '
        'Each candidate gets one development fit and two fresh bootstrap-fit seeds. '
        'The independent selector runs only after you exit. No hidden targets or scores are given. '
        'Case metadata: ' + json.dumps({case: dict(metric=CASES[case]['metric'],
            target=CASES[case]['target'], competition=CASES[case]['competition'])
            for case in cases if case != 'toy'}, sort_keys=True))
    (artifacts/'prompt.txt').write_text(prompt+'\n')
    elapsed = bounded(cmd, artifacts/'backend.jsonl', timeout=MODEL_SECONDS, prompt=prompt, cwd=workspace)
    write_json(artifacts/'backend-timing.json', dict(wall_time_seconds=elapsed))
    usage = usage_from_log(artifacts/'backend.jsonl')
    plan = validate_plan(json.loads(output.read_text()), cases)
    write_json(artifacts/'plan.json', plan)
    return plan, usage, elapsed


def recover_plan(args, cases, artifacts, manifests):
    """Recover a completed response after a local parser failure, without calling a backend."""
    original = json.loads(args.resume_result.read_text())
    if (original.get('status') != 'failed' or original.get('backend') != 'codex' or
            original.get('setup') != args.setup or original.get('model') != args.model or
            original.get('benchmark_version') != VERSION):
        raise ValueError('recovery requires a failed Codex result for the same setup/model/version')
    matches = [p.parent for p in args.runtime.glob('*/freeze.json')
               if file_sha(p) == original.get('freeze_sha256') and (p.parent/'backend.jsonl').exists()
               and file_sha(p.parent/'backend.jsonl') == original.get('usage', {}).get('log_sha256')]
    if len(matches) != 1:
        raise ValueError('recovery requires one original freeze/backend log matching the failed result')
    source, = matches
    freeze = json.loads((source/'freeze.json').read_text())
    if freeze['manifests'] != manifests or {row['case'] for row in original['cases']} != set(cases):
        raise ValueError('recovery data/cases changed')
    if any(source.glob('*/sealed-scoring.jsonl')) or any(source.glob('*/toy-receipt.json')):
        raise ValueError('recovery refused: original run already evaluated a case')
    usage = usage_from_log(source/'backend.jsonl')
    if usage.get('tokens') is None:
        raise ValueError('recovery requires one completed model turn with exact usage')
    plan = validate_plan(json.loads((source/'model-response.json').read_text()), cases)
    # A recovery is single-use; do not erase this marker or any previous evidence.
    write_json(source/'recovered.json', dict(result_sha256=file_sha(args.resume_result)))
    for name in ('backend.jsonl', 'model-response.json', 'prompt.txt'):
        shutil.copyfile(source/name, artifacts/name)
    write_json(artifacts/'plan.json', plan)
    timing = source/'backend-timing.json'
    model_wall = json.loads(timing.read_text())['wall_time_seconds'] if timing.exists() else None
    recovery = dict(result_sha256=file_sha(args.resume_result), freeze_sha256=original['freeze_sha256'],
        original_started_utc=original['started_utc'], original_wall_time_seconds=original['wall_time_seconds'],
        reason=original.get('error'), new_model_requests=0,
        timing_note='Wall time sums original execution and local recovery; intervening development time is excluded.')
    return plan, usage, model_wall, recovery


def compare(current, previous):
    """Only operational regressions are flags. Score changes are displayed, never ranked."""
    flags = []
    for row in current['cases']:
        if row['status'] != 'ok':
            flags.append(dict(kind='breakage', case=row['case'], detail=row.get('error')))
    if previous:
        old_tokens, new_tokens = previous.get('usage', {}).get('tokens'), current.get('usage', {}).get('tokens')
        if old_tokens and new_tokens:
            old = old_tokens['input_tokens'] + old_tokens['output_tokens']
            new = new_tokens['input_tokens'] + new_tokens['output_tokens']
            if old > 0 and new > 2*old:
                flags.append(dict(kind='token_jump', ratio=new/old, threshold='>2x'))
        old, new = previous['wall_time_seconds'], current['wall_time_seconds']
        if old > 0 and new > 2*old:
            flags.append(dict(kind='wall_time_jump', ratio=new/old, threshold='>2x'))
        for row in current['cases']:
            old_row = next((r for r in previous['cases'] if r['case'] == row['case']), None)
            if old_row and old_row.get('status') == 'ok' and row.get('status') != 'ok':
                flags.append(dict(kind='new_failure', case=row['case']))
    return flags


def run(args):
    start = time.monotonic()
    cases = args.cases.split(',')
    if len(cases) != len(set(cases)) or any(c not in ['toy']+list(CASES) for c in cases):
        raise ValueError('cases must be distinct names from toy,concrete,crab')
    if args.backend not in ('stub', 'codex'):
        raise ValueError('only stub and codex backends are supported; no backend substitution')
    if args.resume_result and args.backend != 'codex':
        raise ValueError('response recovery must retain the codex backend identity')
    if args.backend == 'codex' and not args.allow_paid and not args.resume_result:
        raise ValueError('Codex requires --allow-paid; the default invocation never silently spends')
    previous = json.loads(args.compare_to.read_text()) if args.compare_to else None
    if previous is not None and (previous.get('schema_version') != 1 or
            previous.get('benchmark_version') != VERSION or
            {row['case'] for row in previous.get('cases', [])} != set(cases)):
        raise ValueError('--compare-to must use the same benchmark version and cases')
    args.runtime.mkdir(parents=True, exist_ok=True)
    with (args.runtime/'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another benchmark run owns the lock; stop this duplicate')
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S.%fZ')
        artifacts = args.runtime/(args.setup+'-'+stamp+'-'+uuid.uuid4().hex[:6])
        artifacts.mkdir()
        result = dict(schema_version=1, benchmark_version=VERSION, setup=args.setup,
            backend=args.backend, model=args.model if args.backend == 'codex' else 'stub',
            started_utc=stamp, cases=[], usage=dict(tokens=None, usd=None,
            tokens_reason='Backend not reached.', usd_reason='Backend not reached.'),
            shared_model_wall_time_seconds=0., notes=[
                'One model invocation shared across cases; per-case tokens/dollars cannot be attributed.',
                'Per-case wall time includes local fitting/selection; total also includes preparation/model time.',
                'Final hidden scores are local mock holdouts, not Kaggle private leaderboard scores.',
                'One run per setup is a regression observation; run-to-run noise is real.'])
        result['environment'] = dict(python=platform.python_version(), system=platform.system(),
            machine=platform.machine(), cpu_count=os.cpu_count(),
            packages={name: installed_version(name) for name in ('numpy', 'scikit-learn')})
        try:
            manifests = {}
            for case in cases:
                if case != 'toy':
                    args.data_root.mkdir(parents=True, exist_ok=True)
                    with (args.data_root/'setup.lock').open('a') as data_lock:
                        fcntl.flock(data_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        manifests[case] = prepare(case, args.data_root)
            code_paths = list((REPO/'bench').glob('*.py')) + list((REPO/'selection/selection_gate').glob('*.py'))
            code_paths += [REPO/name for name in ('harness/agent_executor.py', 'harness/sweep.py', 'examples/toy_demo.py')]
            source_hashes = {str(path.relative_to(REPO)): file_sha(path) for path in sorted(code_paths)}
            freeze = dict(benchmark_version=VERSION, source_hashes=source_hashes,
                cases={c: freeze_spec(c) for c in cases if c != 'toy'}, manifests=manifests,
                setup=args.setup, backend=args.backend, model=result['model'])
            write_json(artifacts/'freeze.json', freeze)
            result['freeze_sha256'] = file_sha(artifacts/'freeze.json')
            result['source_hashes'] = source_hashes
            result['data_manifest_sha256'] = {case: file_sha(args.data_root/case/'manifest.json') for case in manifests}
            result['partitions'] = {case: m['partitions'] for case, m in manifests.items()}
            if previous is not None and previous.get('data_manifest_sha256') != result['data_manifest_sha256']:
                raise ValueError('--compare-to uses a different frozen data manifest')
            if args.backend == 'codex' and not args.resume_result:
                paid_path = args.runtime/'paid-attempts.jsonl'
                attempts = [json.loads(line) for line in paid_path.read_text().splitlines()] if paid_path.exists() else []
                if len(attempts) >= 2 or any(a['setup'] == args.setup for a in attempts):
                    raise ValueError('paid comparison already attempted; no automatic retries or extra Codex calls')
                # Reserve before Popen, including failed attempts. A crash cannot restore spend allowance.
                with paid_path.open('a') as ledger:
                    ledger.write(json.dumps(dict(setup=args.setup, at=stamp, model=args.model))+'\n')
                    ledger.flush()
                    os.fsync(ledger.fileno())
            if args.resume_result:
                plan, result['usage'], result['shared_model_wall_time_seconds'], result['recovery'] = recover_plan(args, cases, artifacts, manifests)
                if result['shared_model_wall_time_seconds'] is None:
                    result['shared_model_wall_time_reason'] = 'Original response timing was not separately captured; original total is in recovery metadata.'
            else:
                plan, result['usage'], result['shared_model_wall_time_seconds'] = generate_plan(args, cases, artifacts)
            result['plan'] = plan
            result['plan_sha256'] = file_sha(artifacts/'plan.json')
            for case in cases:
                case_start = time.monotonic()
                cpu_start = resource.getrusage(resource.RUSAGE_CHILDREN)
                row = dict(case=case, status='failed', n_submissions=0, local_validation_score=None,
                    hidden_test_score=None, tokens=None, usd=None,
                    cost_reason='One shared backend invocation; exact per-case allocation is unavailable.')
                output = artifacts/case
                try:
                    command = [sys.executable, str(REPO/'bench/worker.py'), '--case', case,
                               '--setup', args.setup, '--plan', str(artifacts/'plan.json'), '--output', str(output)]
                    if case != 'toy':
                        command += ['--data', str(args.data_root/case)]
                    bounded(command, artifacts/(case+'-worker.log'), timeout=PROCESS_SECONDS, cpu=CPU_SECONDS)
                    if case != 'toy':
                        row['predictions_frozen_sha256'] = file_sha(output/'predictions.json')
                        bounded([sys.executable, str(REPO/'bench/selector.py'), '--case', case,
                            '--setup', args.setup, '--data', str(args.data_root/case), '--output', str(output),
                            '--predictions-sha256', row['predictions_frozen_sha256']],
                            artifacts/(case+'-selector.log'), timeout=60, cpu=30)
                    row.update(json.loads((output/'result.json').read_text()), status='ok')
                except Exception as exc:
                    row['error'] = type(exc).__name__+': '+str(exc)
                row['wall_time_seconds'] = time.monotonic()-case_start
                cpu_end = resource.getrusage(resource.RUSAGE_CHILDREN)
                row['cpu_time_seconds'] = cpu_end.ru_utime+cpu_end.ru_stime-cpu_start.ru_utime-cpu_start.ru_stime
                result['cases'].append(row)
        except Exception as exc:
            result['error'] = type(exc).__name__+': '+str(exc)
            for case in cases:
                result['cases'].append(dict(case=case, status='failed', error=result['error'], n_submissions=0,
                    local_validation_score=None, hidden_test_score=None, tokens=None, usd=None,
                    cost_reason='Run failed before per-case evaluation.', wall_time_seconds=0.))
            backend_log = artifacts/'backend.jsonl'
            if backend_log.exists():
                try:
                    result['usage'] = usage_from_log(backend_log)
                except ValueError:
                    result['usage']['log_sha256'] = file_sha(backend_log)
        result['wall_time_seconds'] = time.monotonic()-start
        if result.get('recovery'):
            result['recovery']['local_wall_time_seconds'] = result['wall_time_seconds']
            result['wall_time_seconds'] += result['recovery']['original_wall_time_seconds']
        result['status'] = 'ok' if all(c['status'] == 'ok' for c in result['cases']) else 'failed'
        result['flags'] = compare(result, previous)
        args.results.mkdir(parents=True, exist_ok=True)
        destination = args.results/(args.setup+'-'+stamp+'.json')
        write_json(destination, result)
        print(destination)
        print(json.dumps(dict(status=result['status'], wall_time_seconds=result['wall_time_seconds'], flags=result['flags'])))
        return 0 if result['status'] == 'ok' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', choices=SETUPS, required=True)
    parser.add_argument('--backend', choices=['codex', 'stub'], default=os.environ.get('AGENT_BACKEND', 'codex'))
    parser.add_argument('--model', default='gpt-6.2-sol')
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--cases', default='toy,concrete,crab')
    parser.add_argument('--data-root', type=Path, default=REPO/'bench/data')
    parser.add_argument('--runtime', type=Path, default=REPO/'bench/.runtime')
    parser.add_argument('--results', type=Path, default=REPO/'bench/results')
    parser.add_argument('--compare-to', type=Path)
    parser.add_argument('--resume-result', type=Path,
                        help='reuse a completed response from a failed result in this runtime; never call the model')
    args = parser.parse_args(argv)
    for key in ('data_root', 'runtime', 'results'):
        setattr(args, key, getattr(args, key).expanduser().resolve())
    try:
        return run(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
