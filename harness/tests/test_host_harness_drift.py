"""A --host job runs the executor on the other machine, so it runs THAT machine's harness.

11-07, general: "the m5's harness checkout is 16 commits behind main, and nothing keeps it
current." The gap was real and sat in a different file than the report said. launch.sh runs
$HOME/.local/share/research-harness/agent_executor.py on the host, which is the host's INSTALLED
harness, not its git checkout. That day the m5's installed copy was at 906efdc while this machine
was at ff47140, and the single commit between them touching agent_executor.py was a73a033, the
codex sandbox fix. So --host jobs ran an executor that had already been fixed here.

The checkout mattered in the opposite direction: the m5's was at dee270d, OLDER than what it was
running, so having the host follow origin/main and install for itself would have installed older
code than it already had. That is why this compares installed receipts and why the controller
installs outward instead.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sweep

MINE = 'ff47140bb57e1c2d2427904a74cf3378232a53d9'
THEIRS = '906efdc0757a89c717ae6c5b703e758ced5da693'


@pytest.fixture
def root(tmp_path):
    (tmp_path / sweep.HARNESS_RECEIPT).write_text(json.dumps(dict(commit=MINE, ref='main')))
    return tmp_path


def stub_ssh(tmp_path, monkeypatch, body, name='fake-ssh'):
    s = tmp_path / name
    s.write_text('#!/bin/sh\n' + body + '\n')
    s.chmod(0o755)
    monkeypatch.setenv('LAUNCH_SSH', str(s))
    return s


def test_a_host_on_an_older_harness_is_refused_and_both_shas_are_named(root, tmp_path, monkeypatch):
    """The exact 11-07 state. This is the test that fails without the check."""
    stub_ssh(tmp_path, monkeypatch, "printf '%s' '{\"commit\": \"" + THEIRS + "\"}'")
    message = sweep.host_harness_mismatch('m5', root)
    assert message, 'a host on a different harness must be refused'
    assert THEIRS[:12] in message and MINE[:12] in message
    assert 'harness-sync --host m5' in message


def test_a_host_on_the_same_harness_runs(root, tmp_path, monkeypatch):
    stub_ssh(tmp_path, monkeypatch, "printf '%s' '{\"commit\": \"" + MINE + "\"}'")
    assert sweep.host_harness_mismatch('m5', root) == ''


@pytest.mark.parametrize('body', [
    'exit 255',                      # host unreachable
    'true',                          # no receipt
    "printf 'not json'",             # junk receipt
    "printf '{}'",                   # receipt with no commit
    "printf '[]'",                   # receipt that is not an object
])
def test_an_unreadable_host_harness_is_a_refusal_not_an_assumption(root, tmp_path, monkeypatch, body):
    """Same discipline as the disk floor and the work dir: a job that cannot be shown to be
    running the right code is not run."""
    stub_ssh(tmp_path, monkeypatch, body)
    message = sweep.host_harness_mismatch('m5', root)
    assert 'cannot read the installed harness on m5' in message


def test_a_tree_that_is_not_an_installed_harness_has_nothing_to_compare(tmp_path, monkeypatch):
    """The repo checkout and the test tree have no receipt; the check must not invent drift for
    them, or every developer run would refuse."""
    stub_ssh(tmp_path, monkeypatch, 'exit 255')
    assert sweep.host_harness_mismatch('m5', tmp_path) == ''


def test_the_sweep_refuses_before_it_refreshes_or_spends(root, tmp_path, monkeypatch):
    """Order matters: a lane refreshed onto a host running old code is still the wrong run."""
    launcher = tmp_path / 'launcher'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    spec = tmp_path / 'worker.md'
    spec.write_text('fixture')
    cfg = dict(launcher_path=launcher, cwd=str(tmp_path), cores=1, memory_gib=1,
               worker_timeout_minutes=1, host='m5', rules=[])
    monkeypatch.setattr(sweep, 'guard', lambda c: None)
    monkeypatch.setattr(sweep, 'host_harness_mismatch',
                        lambda host, *a, **k: 'm5 runs harness 906efdc and this machine runs ff47140')
    monkeypatch.setattr(sweep, 'host_sync',
                        lambda c, h: pytest.fail('refreshed the lane onto a drifted host'))
    monkeypatch.setattr(sweep.subprocess, 'Popen',
                        lambda *a, **k: pytest.fail('spent money on a drifted host'))
    with pytest.raises(ValueError) as e:
        sweep.run_worker(spec, cfg)
    assert '906efdc' in str(e.value) and 'ff47140' in str(e.value)


def test_a_local_run_never_asks_about_a_host(tmp_path, monkeypatch):
    launcher = tmp_path / 'launcher'
    launcher.write_text('#!/bin/sh\nexit 0\n')
    spec = tmp_path / 'worker.md'
    spec.write_text('fixture')
    cfg = dict(launcher_path=launcher, cwd=str(tmp_path), cores=1, memory_gib=1,
               worker_timeout_minutes=1, rules=[])
    monkeypatch.delenv('LAUNCH_HOST', raising=False)
    monkeypatch.setattr(sweep, 'guard', lambda c: None)
    monkeypatch.setattr(sweep, 'host_harness_mismatch',
                        lambda *a, **k: pytest.fail('asked about a host for a local run'))
    with monkeypatch.context() as m:
        m.setattr(sweep.subprocess, 'Popen', FakePopen)
        m.setattr(sweep.os, 'killpg', lambda *a: None)
        assert sweep.run_worker(spec, cfg) == 0


class FakePopen:
    def __init__(self, *a, **k):
        self.pid = 4242
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


# --- keeping the host current, from here -------------------------------------------------------

import importlib.machinery
import importlib.util

_loader = importlib.machinery.SourceFileLoader(
    'harness_sync_tool', str(ROOT / 'tools/harness-sync/harness_sync.py'))
_spec = importlib.util.spec_from_loader('harness_sync_tool', _loader)
hs = importlib.util.module_from_spec(_spec)
_loader.exec_module(hs)


def test_only_real_ssh_aliases_are_followed(monkeypatch):
    monkeypatch.setenv('RH_HARNESS_HOSTS', 'm5, laptop  mini2')
    assert hs.configured_hosts() == ['m5', 'laptop', 'mini2']
    monkeypatch.setenv('RH_HARNESS_HOSTS', '-oProxyCommand=id, m5;id, m5')
    assert hs.configured_hosts() == ['m5']
    monkeypatch.delenv('RH_HARNESS_HOSTS')
    assert hs.configured_hosts() == []


def test_a_host_that_cannot_be_reached_is_reported_and_not_fatal(monkeypatch, capsys):
    """The scheduled tick must not break because a second machine is asleep. The guarantee is the
    refusal at use time, not this."""
    monkeypatch.setenv('RH_HARNESS_HOSTS', 'm5')
    monkeypatch.setattr(hs, 'host_plan',
                        lambda *a, **k: (_ for _ in ()).throw(ValueError('m5 is asleep')))
    assert hs.follow_hosts(Path('/repo'), Path('/root'), 'main') == 1
    out = capsys.readouterr().out
    assert 'NOT brought to main' in out and 'm5 is asleep' in out
    assert 'will refuse until this is fixed' in out


def test_a_host_already_at_the_ref_is_left_alone(monkeypatch, capsys):
    monkeypatch.setenv('RH_HARNESS_HOSTS', 'm5')
    monkeypatch.setattr(hs, 'host_plan', lambda *a, **k: ({'sweep.py': ('100644', 'abc')}, []))
    monkeypatch.setattr(hs, 'install_host',
                        lambda *a, **k: pytest.fail('reinstalled a host that already matched'))
    assert hs.follow_hosts(Path('/repo'), Path('/root'), 'main') == 0
    assert 'already matches main' in capsys.readouterr().out


def test_the_host_install_verifies_on_the_host_before_writing_the_receipt(tmp_path, monkeypatch):
    """A receipt is a claim that the files arrived. rsync's exit status is not evidence of that,
    so the receipt is written only after the files are re-hashed on the host."""
    source = (ROOT / 'tools/harness-sync/harness_sync.py').read_text()
    verify = source.index('after = host_state(host, root, todo')
    receipt = source.index("receipt = dict(commit=commit, ref=ref,\n                   utc=")
    assert verify < receipt, 'the receipt must be written after the on-host verification'
    assert 'the receipt was \\n                         \'NOT written' in source or \
           'NOT written' in source


def test_installing_outward_from_a_drifted_controller_is_refused(tmp_path, monkeypatch, capsys):
    """Spreading this machine's drift to the host would be worse than leaving the host behind."""
    monkeypatch.setattr(hs, 'plan', lambda repo, root, ref: ({}, {}, [('behind', 'sweep.py')]))
    monkeypatch.setattr(hs, 'git', lambda *a, **k: b'f4c930e39481\n')
    monkeypatch.setattr(hs, 'host_plan',
                        lambda *a, **k: pytest.fail('looked at the host while this machine drifts'))
    rc = hs.main(['--host', 'm5', '--root', str(tmp_path), '--repo', str(tmp_path)])
    assert rc == 2
    assert 'this machine is not at main yet' in capsys.readouterr().out
