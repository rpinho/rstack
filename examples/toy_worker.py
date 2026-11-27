#!/usr/bin/env python3
"""One paid worker, followed by local exact verification and selection receipts."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'harness'), str(REPO/'selection'), str(REPO/'examples')]
import sweep
import toy_demo
from selection_gate import decide, write_receipt, verify_receipt


def launch(command, env, timeout=180):
    """A timed-out tutorial must not leave a billable descendant running."""
    proc = subprocess.Popen(command, env=env, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # The launcher may exit before a descendant; clean the entire owned group.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return 124


def verify(root, backend):
    lane = root/'lanes/toy'
    sequence = lane/'runs/sequence.json'
    expected = [i*i for i in range(10)]
    if json.loads(sequence.read_text()) != expected:
        raise ValueError('worker sequence differs from the exact verifier')
    paths = {stage: lane/('reports/'+stage+'.md') for stage in ('search', 'read', 'kill')}
    errors = sweep.check(paths, [], {'boards': ['TOY']}, known_ids=set())
    if errors:
        raise ValueError('; '.join(errors))
    log = (root/'jobs/toy-worker.log').read_text()
    events = [json.loads(line.split(' ', 1)[1]) for line in log.splitlines()
              if line.startswith('MODEL_OUTCOME ')]
    if len(events) != 1 or events[0]['exit_code'] != 0 or events[0]['executor'] != backend:
        raise ValueError('expected exactly one successful backend outcome')
    # Two identical exact-verifier repeats exercise the API, not statistical validation.
    decision = decide([dict(name='squares', sealed_scores=[1., 1.])], 0., 1)
    receipt = root/'receipts/selection.json'
    write_receipt(receipt, decision, hashlib.sha256(sequence.read_bytes()).hexdigest(), 'toy-worker', 'TOY')
    verify_receipt(receipt, sequence)
    result = dict(backend=backend, model=events[0]['model'], exit_code=0,
                  sequence_sha256=hashlib.sha256(sequence.read_bytes()).hexdigest(),
                  reports=list(paths), selection=decision['selected'],
                  statistical_holdout=False, verified_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    (root/'receipts/toy.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, sort_keys=True))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args(argv)
    backend = os.environ.get('AGENT_BACKEND', 'codex')
    if backend not in ('codex', 'claude'):
        p.error('AGENT_BACKEND must be codex or claude')
    root = a.root.resolve()
    if root.exists():
        p.error('choose a fresh root for each paid run')
    if toy_demo.main(['--root', str(root)]):
        return 1
    lane = root/'lanes/toy'
    for folder in ('runs', 'reports'):
        (lane/folder).mkdir(exist_ok=True)
    jobs = root/'jobs'; jobs.mkdir()
    model = 'gpt-6.2-sol' if backend == 'codex' else 'claude-haiku-5-5'
    roles = root/'roles.json'
    roles.write_text(json.dumps(dict(roles={'toy': [model]}, routes={model: {'canonical': model, 'cli': backend}})))
    (jobs/'toy-worker.md').write_text('''Use only this synthetic lane. Do not browse, contact anyone, spawn workers, or publish.
Read RULES.md. Write exactly four files using your file tools:
runs/sequence.json: a JSON array of squares for integers 0 through 9, in order.
reports/search.md: exactly "IDEA TOY-1: enumerate squares\\nDONE\\n".
reports/read.md: exactly "No queued external ideas.\\nDONE\\n".
reports/kill.md: exactly "RESULT TOY-1: SURVIVED 10/10 squares match the exact arithmetic pass line\\nDONE\\n".
The notation \\n means a real newline. The independent host verifier will check the files.
No statistical holdout is claimed: this is an exact arithmetic installation test.
Finish with a short receipt. Use no other tools or files.
''')
    env = dict(os.environ, RH_ROLES_FILE=str(roles), LAUNCH_ARTIFACT_DIR=str(jobs),
               LAUNCH_STATE=str(root/'registry'), LAUNCH_ROLE='toy', LAUNCH_EFFORT='low',
               AGENT_BACKEND=backend)
    # Ambient role/model overrides cannot alter the documented toy command.
    for key in ('LAUNCH_MODEL', 'LAUNCH_MODEL_OVERRIDE', 'LAUNCH_RESUME', 'LAUNCH_IDEA', 'LAUNCH_IDEA_ROOT'):
        env.pop(key, None)
    code = launch(['zsh', str(REPO/'tools/launch.sh'), 'toy-worker', str(lane)], env)
    if code:
        print((jobs/'toy-worker.log').read_text(), file=sys.stderr)
        return code
    verify(root, backend)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
