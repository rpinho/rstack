"""launch-guard: queued jobs hold no slot; the queue drains first come, first served (11-28 math deadlock)."""
import json
import os
from pathlib import Path
import subprocess
import sys

TOOL = Path(__file__).resolve().parents[1] / 'tools/launch-guard'
FAKE = '''
import json, os, sys
args = sys.argv[1:]
state = json.load(open(os.environ['STATE']))
if args[0] == 'display-message':
    print(os.environ['ME'])
elif args[0] == 'list-panes':
    print(''.join('{}\\t0\\tcodex\\t\\t\\tlaunch.sh\\n'.format(s) for s in state['sessions']), end='')
elif args[0] == 'list-sessions':
    print(''.join('{}\\t{}\\n'.format(s, state['marks'].get(s, '')) for s in state['sessions']), end='')
elif args[0] == 'set-option':
    target = args[args.index('-t') + 1].lstrip('=')
    if '-u' in args:
        state['marks'].pop(target, None)
    elif args[-2] == '@launch_queued':
        state['marks'][target] = args[-1]
    json.dump(state, open(os.environ['STATE'], 'w'))
'''


def guard(tmp_path, me):
    tmux = tmp_path / 'tmux'
    if not tmux.exists():
        tmux.write_text('#!' + sys.executable + '\n' + FAKE)
        tmux.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LAUNCH_', 'TMUX'))}
    env.update(LAUNCH_TMUX=str(tmux), TMUX='fixture', TMUX_PANE='%1', ME=me, STATE=str(tmp_path / 'state.json'))
    done = subprocess.run([sys.executable, str(TOOL), '--job', me[4:], '--lane', 'math', '--backend', 'codex'],
                          env=env, capture_output=True, text=True, timeout=20)
    return done.returncode


def test_four_launched_together_with_one_running_start_three_and_queue_one(tmp_path):
    state = tmp_path / 'state.json'
    queued = ['job-math_opx_{}_1128'.format(x) for x in 'ABCD']
    # Everyone arrived at once and saw the others' sessions: the 11-28 deadlock state, all four marked queued.
    state.write_text(json.dumps({'sessions': ['job-planets_tnodes_1127'] + queued,
                                 'marks': {name: str(100 + i) for i, name in enumerate(queued)}}))
    assert [guard(tmp_path, name) for name in queued] == [0, 0, 0, 75]
    marks = json.loads(state.read_text())['marks']
    assert list(marks) == ['job-math_opx_D_1128'] and marks['job-math_opx_D_1128'] == '103'   # D keeps its place


def test_a_new_arrival_queues_behind_earlier_waiters_not_ahead(tmp_path):
    state = tmp_path / 'state.json'
    running = ['job-r{}'.format(i) for i in range(3)]
    state.write_text(json.dumps({'sessions': running + ['job-early', 'job-new'], 'marks': {'job-early': '100'}}))
    assert guard(tmp_path, 'job-new') == 75          # 3 running + 1 queued ahead of it = cap 4
    assert float(json.loads(state.read_text())['marks']['job-new']) > 100
    assert guard(tmp_path, 'job-early') == 0         # the earlier waiter sees only the 3 running
