"""voice-lint: measure your own writing, then refuse drafts that don't sound like you."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
loader = importlib.machinery.SourceFileLoader('voice_lint', str(TOOLS / 'voice-lint'))
spec = importlib.util.spec_from_loader('voice_lint', loader)
vl = importlib.util.module_from_spec(spec)
loader.exec_module(vl)


def lint(text, *args, slop='Great question\nre: \\bdelve\\b\n', tmp=None):
    path = tmp / 'slop.txt'
    path.write_text(slop)
    return subprocess.run([sys.executable, str(TOOLS / 'voice-lint'), '--slop', str(path), *args],
                          input=text, capture_output=True, text=True)


def test_measure_profiles_your_own_writing():
    profile = vl.measure(["I think it's fine. Probably ships today.", 'ok, merging now', 'Done!'])
    assert profile['messages'] == 3 and profile['sentences'] == 4
    assert profile['contractions'] == round(1 / 3, 3) and profile['lowercase_start'] == round(1 / 3, 3)
    assert profile['exclamation'] == round(1 / 3, 3) and profile['hedges'] == {'i think': 1, 'probably': 1}
    assert profile['words_per_sentence']['median'] == 3   # 4, 3, 3 and 1 words


def test_a_slop_phrase_fails(tmp_path):
    run = lint('Great question! Here is the answer.', tmp=tmp_path)
    assert run.returncode == 1 and 'FAIL: slop: Great question' in run.stdout


def test_a_regex_entry_matches_words_not_substrings(tmp_path):
    assert lint("Let's delve into it.", tmp=tmp_path).returncode == 1
    assert lint('The delved-for result held.', tmp=tmp_path).returncode == 0


def test_an_em_dash_fails_unless_allowed(tmp_path):
    text = 'It held — mostly.'
    assert 'em dash' in lint(text, tmp=tmp_path).stdout
    assert lint(text, '--allow-em-dash', tmp=tmp_path).returncode == 0


def test_too_many_exclamations_fail(tmp_path):
    assert lint('Yes! Yes!', tmp=tmp_path).returncode == 1
    assert lint('Yes! Yes!', '--max-exclamations', '2', tmp=tmp_path).returncode == 0


def test_a_plain_draft_passes_and_the_harness_reply_flag_is_ignored(tmp_path):
    run = lint('The bound holds. I checked it twice.', '--reply', tmp=tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'PASS'


def test_the_example_slop_list_loads():
    rules = vl.load_slop(TOOLS / 'slop.example.txt')
    assert rules and any(label.startswith('re:') for label, _ in rules)
    assert vl.check('I hope this finds you well.', rules)
