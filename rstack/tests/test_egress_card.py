"""[card] stays on prose and skips numeric data (11-25). Synthetic fixtures only."""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

from rstack_hookcall import TOOLS

# Built by concatenation so this file itself carries no card-shaped run.
CARD = '4111 ' + '1111 ' * 2 + '1111'


def load_gate():
    loader = importlib.machinery.SourceFileLoader('card_gate', str(TOOLS / 'egress-gate'))
    spec = importlib.util.spec_from_loader('card_gate', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


gate = load_gate()


def cards(text, path):
    return [h for h in gate.hits_in(text, gate.SECRET_SHAPES, path) if h[0] == 'card']


@pytest.mark.parametrize('path', ['notes/STATUS.md', 'src/pay.py', 'mail.eml', 'README', 'logs.md'])
def test_card_in_prose_is_caught(path):
    assert cards(f'Card on file: {CARD} exp 12/30\n', path)


@pytest.mark.parametrize('path', [
    'erdos/293-k9-gaps/gaps.tsv', 'erdos/293-k9-gaps/logs/r3/summary.json', 'a/b.csv', 'x.jsonl',
    'proof/Main.lean', 'cert/run.lrat', 'big.json.gz', 'erdos/36/logs/run.txt', 'c/certificates/q.txt',
    'erdos/982/logs/r/out.log',
])
def test_numeric_data_and_proof_files_skip_card(path):
    assert not cards(f'{CARD}\n', path)


@pytest.mark.parametrize('text', [
    f'denominators: 2 3 {CARD} 7 11',          # whitespace integer list
    f'1/{CARD}',                                # fraction
    f'0.{CARD}',                                # decimal
    f'[{CARD}, 5]',                             # list in prose
])
def test_digit_run_inside_a_number_list_is_not_a_card(text):
    assert not cards(text, 'erdos/293-k9-gaps/STATUS.md')


def test_txt_outside_logs_is_still_prose():
    assert cards(f'{CARD}\n', 'notes/todo.txt')


def test_pre_push_blocks_md_card_and_passes_tsv(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    conf = tmp_path / 'egress'
    conf.mkdir()
    (conf / 'patterns.txt').write_text('# synthetic: built-in shapes only\n')
    env = dict(os.environ, RSTACK_EGRESS_DIR=str(conf))

    def git(*args):
        return subprocess.run(['git', '-c', 'user.name=Synthetic', '-c',
                               'user.email=synthetic@example.invalid', *args], cwd=repo,
                              env=env, text=True, capture_output=True, check=True).stdout.strip()

    def push():
        head = git('rev-parse', 'HEAD')
        return subprocess.run([sys.executable, str(TOOLS / 'egress-gate'), 'pre-push', 'origin',
                               'https://example.invalid/synthetic.git'],
                              cwd=repo, env=env, text=True, capture_output=True, timeout=30,
                              input='refs/heads/main {} refs/heads/main {}\n'.format(head, '0' * 40))

    git('init', '-q', '-b', 'main')
    (repo / 'gaps.tsv').write_text(f'{CARD}\t1\n')
    git('add', '.')
    git('commit', '-qm', 'data')
    ok = push()
    assert ok.returncode == 0, ok.stdout + ok.stderr
    (repo / 'NOTE.md').write_text(f'Card: {CARD}\n')
    git('add', '.')
    git('commit', '-qm', 'prose')
    bad = push()
    assert bad.returncode == 2, bad.stdout + bad.stderr
    assert '[card]' in bad.stdout
