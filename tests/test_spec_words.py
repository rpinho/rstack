"""The goal-drift word cap counts the ask, not what the harness injected around it."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sw', ROOT / 'harness/tools/spec_words.py')
sw = importlib.util.module_from_spec(spec); spec.loader.exec_module(sw)

ASK = 'Find a better bound for C44 than the printed one, or say plainly that you did not.'


def generated(policy_words=2000, lessons_words=500):
    """A spec shaped like the sweep's own output: the ask, then injected shared blocks."""
    return '\n'.join([
        '# Harness outside search: c5 / search / 2026-11-06',
        '',
        ASK,
        '',
        '## Shared lessons',
        ' '.join(['lesson'] * lessons_words),
        '',
        '## Working directory',
        'Run here.',
        '',
        '--- BEGIN VERBATIM LANE POLICY: /x/lanes/c5/RULES.md ---',
        ' '.join(['rule'] * policy_words),
        '--- END VERBATIM LANE POLICY ---',
        '',
        '--- BEGIN VERBATIM LANE POLICY: /x/lanes/c5/INTAKE.toml ---',
        ' '.join(['config'] * policy_words),
        '--- END VERBATIM LANE POLICY ---',
    ])


def test_injected_blocks_do_not_count_against_the_cap(tmp_path):
    """c5's 0-search spec was 3,047 words, of which 472 were the ask. The cap refused it and
    the lane's generated jobs could not run at all.
    """
    p = tmp_path / 'spec.md'
    p.write_text(generated())
    assert len(p.read_text().split()) > 4000, 'the whole file is far over any cap'
    assert sw.count(p) < 100, 'the ask is small'
    # The ask itself survives, so the cap still measures something real.
    kept = sw.job_specific(p.read_text())
    assert ASK in kept and 'Run here.' in kept
    assert 'rule' not in kept and 'config' not in kept and 'lesson' not in kept


def test_a_long_ask_is_still_refused(tmp_path):
    """The cap is a hard rule; this must not become a way around it."""
    p = tmp_path / 'spec.md'
    p.write_text(ASK + '\n' + ' '.join(['ceremony'] * 1200) + '\n' + generated())
    assert sw.count(p) > 1000


def test_unbalanced_markers_count_everything(tmp_path):
    """Fail closed: a malformed spec gets the strict budget, never an unlimited one."""
    p = tmp_path / 'spec.md'
    p.write_text('\n'.join([ASK, '--- BEGIN VERBATIM LANE POLICY: /x ---',
                            ' '.join(['rule'] * 2000)]))
    assert sw.count(p) > 1000


def test_the_lessons_block_ends_at_the_next_heading(tmp_path):
    p = tmp_path / 'spec.md'
    p.write_text('\n'.join(['## Shared lessons', 'dropped dropped', '# Real heading', 'kept kept']))
    kept = sw.job_specific(p.read_text())
    assert 'kept kept' in kept and 'dropped' not in kept


def test_a_plain_spec_is_counted_whole(tmp_path):
    """A hand-written spec has no injected blocks, so nothing changes for it."""
    p = tmp_path / 'spec.md'
    p.write_text(ASK)
    assert sw.count(p) == len(ASK.split())


def test_a_generated_worklist_of_ids_is_not_process(tmp_path):
    """friends 0-read was refused at 1,172 words, 771 of them one line of 762 queue ids.

    The cap exists so the goal cannot turn into process. The list of rows to work on IS the goal,
    so counting it refuses a lane for having a long queue, which is backwards.
    """
    ids = ', '.join('"%032x"' % i for i in range(300))
    spec = tmp_path / 'read.md'
    spec.write_text('Read and judge every listed queue id.\n'
                    'Required queue ids (all unmarked rows since stage start): [%s]\n' % ids)
    assert sw.count(spec) == 7


def test_prose_in_brackets_cannot_buy_room(tmp_path):
    """The exclusion must not become a way to smuggle rules past the cap."""
    spec = tmp_path / 'read.md'
    spec.write_text('Rules: ["always do the thing", "never do the other thing"]\n')
    assert sw.count(spec) > 7, 'strings with spaces are prose, not ids'
    spec.write_text('Note: [not json at all\n')
    assert sw.count(spec) == 5
    spec.write_text('Single: ["0123456789abcdef"]\n')
    assert sw.count(spec) == 2, 'a one-item list is not a worklist'


def test_the_repair_pass_failure_list_is_harness_output_not_the_ask():
    """planets, 11-08: the repair spec was the first pass plus the compiler's failures, and the
    failures pushed it over the cap, so no repair pass could run on a lane near the limit."""
    ask = ' '.join(['word'] * 50)
    failures = '\n'.join('ideas without a result: ' + 'x' * 32 + ' and more words here' for _ in range(40))
    spec_text = (ask + '\nONE REPAIR PASS. Correct the compiler failures below without relaxing policy.\n'
                 '--- BEGIN HARNESS COMPILER FAILURES ---\n' + failures + '\n--- END HARNESS COMPILER FAILURES ---\n')
    assert len(sw.job_specific(spec_text).split()) < 70
    unbalanced = spec_text.replace('--- END HARNESS COMPILER FAILURES ---\n', '')
    assert len(sw.job_specific(unbalanced).split()) > 200, 'unbalanced markers count everything'
