"""worker_path: a lane's interpreter goes first on the worker's PATH, here and on the host.

11-10: math's kill test 60a6723f was BLOCKED on "No module named 'flint'". The m5 worker ran the system
python3; the lane's checkers need the shared venv, which has python-flint."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sweep


def test_no_worker_path_changes_nothing():
    assert sweep.worker_path_env({}, {'PATH': '/usr/bin'}) == {}
    assert sweep.worker_path_env({'worker_path': []}, {'PATH': '/usr/bin'}) == {}


def test_worker_path_goes_first_locally_and_on_the_host(tmp_path):
    venv = tmp_path / 'venv' / 'bin'
    venv.mkdir(parents=True)
    (venv / 'python3').write_text('#!/bin/sh\necho venv-python\n')
    (venv / 'python3').chmod(0o755)
    env = sweep.worker_path_env({'worker_path': [str(venv)]}, {'PATH': '/usr/bin:/bin'})
    assert env['PATH'].split(':')[0] == str(venv)
    assert env['LAUNCH_REMOTE_PATH'].split(':')[0] == str(venv)
    assert env['LAUNCH_REMOTE_PATH'].endswith('/usr/bin:/bin:/usr/sbin:/sbin')
    # The point of it: a bare `python3` in a worker's shell is the lane's interpreter.
    out = subprocess.run(['sh', '-c', 'python3'], env={'PATH': env['PATH']}, capture_output=True, text=True)
    assert out.stdout.strip() == 'venv-python'


def test_an_explicit_remote_path_is_kept_behind_the_lane_dirs():
    env = sweep.worker_path_env({'worker_path': ['/opt/v/bin']}, {'PATH': '/usr/bin', 'LAUNCH_REMOTE_PATH': '/x/bin'})
    assert env['LAUNCH_REMOTE_PATH'] == '/opt/v/bin:/x/bin'
