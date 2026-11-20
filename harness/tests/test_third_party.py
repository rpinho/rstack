"""Third-party code runs only from a pinned commit, with no network, writing only the job dir (11-20)."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import third_party as tp

needs_sandbox = pytest.mark.skipif(not Path(tp.SANDBOX).exists(), reason='macOS sandbox-exec only')

SCRIPT = '''import socket, sys
from pathlib import Path
what = sys.argv[1]
if what == 'write-inside':
    Path('out.txt').write_text('ok')
elif what == 'write-outside':
    Path(sys.argv[2]).write_text('escaped')
elif what == 'network':
    socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=3).close()
print('done', what)
'''


def repo(tmp_path):
    r = tmp_path / 'upstream'
    r.mkdir()
    (r / 'tool.py').write_text(SCRIPT)
    for args in (['init', '-q'], ['add', '.'], ['-c', 'user.email=t@example.com', '-c', 'user.name=t',
                                                'commit', '-qm', 'tool']):
        subprocess.run(['git', *args], cwd=r, check=True)
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=r, capture_output=True, text=True).stdout.strip()
    return 'file://' + str(r), sha


def job(tmp_path):
    j = tmp_path / 'job'
    j.mkdir()
    return j


@needs_sandbox
def test_a_pinned_run_passes_and_leaves_a_receipt(tmp_path):
    url, sha = repo(tmp_path)
    j = job(tmp_path)
    assert tp.run(j, url, sha, [sys.executable, 'tool.py', 'write-inside']) == 0
    out = j / tp.DIR / ('upstream-' + sha[:12]) / 'out.txt'
    assert out.read_text() == 'ok'
    row = json.loads((j / tp.RECEIPTS).read_text())
    assert row['commit'] == sha and row['rc'] == 0 and row['url'] == url
    assert tp.check(j) == []


@needs_sandbox
def test_a_write_outside_the_job_dir_fails(tmp_path):
    url, sha = repo(tmp_path)
    j = job(tmp_path)
    outside = tmp_path / 'outside.txt'
    assert tp.run(j, url, sha, [sys.executable, 'tool.py', 'write-outside', str(outside)]) != 0
    assert not outside.exists()


@needs_sandbox
def test_a_network_call_fails(tmp_path):
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    def serve():
        for _ in range(2):
            try:
                srv.accept()[0].close()
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    url, sha = repo(tmp_path)
    j = job(tmp_path)
    tool = j / 'control.py'
    tool.write_text(SCRIPT)
    # control: the same call works outside the sandbox, so the failure below is the sandbox
    assert subprocess.run([sys.executable, str(tool), 'network', str(port)]).returncode == 0
    assert tp.run(j, url, sha, [sys.executable, 'tool.py', 'network', str(port)]) != 0
    srv.close()


def test_an_unpinned_ref_or_a_missing_sandbox_is_refused(tmp_path):
    url, sha = repo(tmp_path)
    j = job(tmp_path)
    with pytest.raises(ValueError, match='UNPINNED'):
        tp.fetch(j, url, 'main')
    with pytest.raises(RuntimeError, match='NO_SANDBOX'):
        tp.run(j, url, sha, ['true'], sandbox='/nonexistent/sandbox-exec')
    assert not (j / tp.DIR).exists()


def test_check_flags_fetched_code_under_a_runnable_name_and_stray_checkouts(tmp_path):
    j = job(tmp_path)
    src = 'import os\nprint("their loop")\n'
    url = 'https://raw.githubusercontent.com/someone/repo/' + 'a' * 40 + '/experiments/loop.py'
    (j / 'sources.jsonl').write_text(json.dumps({'name': 'loop.py', 'url': url}) + '\n'
                                     + json.dumps({'name': 'README.md', 'url': url[:-7] + 'README.md'}) + '\n')
    (j / 'loop.py').write_text(src)
    (j / 'README.md').write_text('# docs are data')
    errs = tp.check(j)
    assert len(errs) == 1 and errs[0].startswith('FETCHED_CODE_RUNNABLE: loop.py')
    # kept as data it passes; a byte-for-byte copy under a code name does not
    (j / 'loop.py').rename(j / 'loop.py.txt')
    (j / 'sources.jsonl').write_text(json.dumps({'name': 'loop.py.txt', 'url': url}) + '\n')
    assert tp.check(j) == []
    (j / 'run_it.py').write_text(src)
    assert [e.split(':')[0] for e in tp.check(j)] == ['FETCHED_CODE_RUNNABLE']
    (j / 'run_it.py').unlink()
    # a hand clone, or a third_party folder nobody ran through the tool
    (j / 'clone' / '.git').mkdir(parents=True)
    (j / tp.DIR / 'repo-aaaaaaaaaaaa').mkdir(parents=True)
    kinds = sorted(e.split(':')[0] for e in tp.check(j))
    assert kinds == ['CHECKOUT_OUTSIDE_SANDBOX', 'THIRD_PARTY_UNRECEIPTED']


def test_the_sweep_check_fails_a_run_with_fetched_code_left_runnable(tmp_path):
    import sweep
    run = tmp_path / 'run'
    run.mkdir()
    for stage, text in (('search', 'NOTHING NEW\nDONE\n'), ('read', 'DONE\n'), ('kill', 'RESULT NONE\nDONE\n')):
        (run / (stage + '.report.md')).write_text(text)
    paths = {s: run / (s + '.report.md') for s in ('search', 'read', 'kill')}
    assert not any('THIRD' in e or 'FETCHED' in e for e in sweep.check(paths, []))
    url = 'https://raw.githubusercontent.com/someone/repo/' + 'b' * 40 + '/gridcegar.py'
    (run / 'sources.jsonl').write_text(json.dumps({'name': 'gridcegar.py', 'url': url}) + '\n')
    (run / 'gridcegar.py').write_text('print(1)\n')
    assert any(e.startswith('FETCHED_CODE_RUNNABLE: gridcegar.py') for e in sweep.check(paths, []))
