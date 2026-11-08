"""Onboarding tracks (Ricardo, 11-08): beginners get a tutorial, not the whole stack.

The beginner page may point at advanced-only material only with "later" in the same paragraph,
the README's first screen points newcomers at /onboard, each track but the last ends with the
checks that move someone up, and the onboard skill asks the placement question.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LINT = ROOT / 'rstack/tools/onboarding_lint.py'
sys.path.insert(0, str(LINT.parent))
import onboarding_lint


def test_the_repo_passes():
    run = subprocess.run([sys.executable, str(LINT), str(ROOT)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


def tree(tmp_path, beginner, readme='Type `/onboard` to start.\n'):
    (tmp_path / 'docs/onboarding').mkdir(parents=True)
    (tmp_path / 'harness').mkdir()
    (tmp_path / 'harness/README.md').write_text('the harness\n')
    shutil.copy(ROOT / 'docs/onboarding/tracks.json', tmp_path / 'docs/onboarding/tracks.json')
    (tmp_path / 'docs/onboarding/beginner.md').write_text(beginner)
    (tmp_path / 'README.md').write_text(readme)
    return tmp_path


def test_a_beginner_page_linking_into_the_harness_fails(tmp_path):
    found = onboarding_lint.findings(tree(tmp_path, 'Read [the harness](../../harness/README.md) next.\n'))
    assert found and 'advanced-only harness/README.md' in found[0]


def test_the_same_link_marked_later_passes(tmp_path):
    assert not onboarding_lint.findings(tree(tmp_path, 'Later, once this works: [the harness](../../harness/README.md).\n'))


def test_later_in_another_paragraph_does_not_count(tmp_path):
    text = 'You can read more later.\n\nRead [the harness](../../harness/README.md).\n'
    assert onboarding_lint.findings(tree(tmp_path, text))


def test_external_and_beginner_links_are_fine(tmp_path):
    text = 'See [Claude Code](https://claude.com/claude-code) and [next](intermediate.md).\n'
    assert not onboarding_lint.findings(tree(tmp_path, text))


def test_a_readme_that_stops_pointing_at_onboard_fails(tmp_path):
    found = onboarding_lint.findings(tree(tmp_path, 'Hello.\n', readme='# Something else\n'))
    assert any('/onboard' in f for f in found)


def test_each_track_but_the_last_ends_with_the_checks_that_move_you_up():
    for name in ('beginner', 'intermediate'):
        text = (ROOT / 'docs/onboarding' / (name + '.md')).read_text()
        assert '## Ready for the next one?' in text, name
    assert 'Ready for the next one?' not in (ROOT / 'docs/onboarding/advanced.md').read_text()


def test_the_onboard_skill_asks_the_placement_question_and_points_at_real_tracks():
    skill = (ROOT / '.claude/skills/onboard/SKILL.md').read_text()
    assert 'beginner, intermediate, or advanced' in skill
    for name in ('beginner', 'intermediate', 'advanced'):
        assert (ROOT / 'docs/onboarding' / (name + '.md')).is_file()
        assert 'docs/onboarding/{}.md'.format(name) in skill


def test_every_image_the_tracks_show_exists():
    import re
    for page in (ROOT / 'docs/onboarding').glob('*.md'):
        for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', page.read_text()):
            assert (page.parent / target).resolve().is_file(), (page.name, target)
