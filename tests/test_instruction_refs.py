"""Instruction files name only paths, links, rh commands and options that exist.

An agent follows its instruction file over the code (SmartScope's study of 40 projects: a stale
CLAUDE.md/AGENTS.md instruction was followed about 90% of the time, the code 4%). Ours drifted the
same way: a hook guarded a path deleted months earlier, and a skill kept a limit after the code moved.
"""
import importlib.machinery
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / 'rstack/tools/instruction-refs'
loader = importlib.machinery.SourceFileLoader('instruction_refs', str(TOOL))
spec = importlib.util.spec_from_loader('instruction_refs', loader)
refs = importlib.util.module_from_spec(spec)
loader.exec_module(refs)

INSTRUCTION_FILES = ['AGENTS.md', 'CLAUDE.md', 'README.md', 'docs', '.claude/skills', 'rstack']


def test_the_repos_instruction_files_name_nothing_stale():
    found = refs.findings([REPO / p for p in INSTRUCTION_FILES], REPO)
    assert found == [], '\n'.join(found)


def test_each_kind_of_stale_reference_is_caught(tmp_path):
    page = tmp_path / 'SKILL.md'
    page.write_text('See [the guide](missing.md) and `harness/gone.py`.\n'
                    'Run `rh lanez new X`, then `rh outreach dispatch LANE ID`, then `rh lint LANE --frobnicate`.\n'
                    'Fine: `harness/rh.py`, `rh outreach draft LANE --incoming FILE`, `rh ideas promote L ID --board B`, '
                    '`docs/<page>.md`.\n')
    found = refs.findings([page], REPO)
    text = '\n'.join(found)
    assert 'missing.md' in text and 'harness/gone.py' in text
    assert "no subcommand 'lanez'" in text and "no action 'dispatch'" in text and '--frobnicate' in text
    assert len(found) == 5, text


def test_a_skill_names_its_own_files_relative_to_itself(tmp_path):
    skill = tmp_path / 'skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'scripts/check.py').write_text('')
    (skill / 'SKILL.md').write_text('Run `scripts/check.py`.\n')
    assert refs.findings([skill], REPO) == []
