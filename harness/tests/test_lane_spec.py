"""The lane's target is compared to the challenge, not to the lane.

11-07, c5 postmortem 3 ("the wrong target"). c5 ran 115 rounds against HLA-A*02:01 with a signal
peptide while the challenge target is HLA-A*11:01, mature chain. The lane captured the challenge
page verbatim on 10-27 and the capture was still in the repo, unread, through every one of those
rounds. Every harness check was green because every harness check compared the lane to itself.

The first test here is that failure, with the real strings, against a capture that says A*11:01.
It must refuse. The rest are the ways the refusal can be dodged: an unpinned capture, a capture
that changed under the lane, a length that does not match, a ranking condition nobody answered,
and no SPEC.json at all.
"""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import spec

# The real sequences, from adaptyv-c4/scripts/c5_target.py. Shortened here only where the test
# does not depend on the full chain.
RIGHT = ('GSHSMRYFYTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEGPEYWDQETRNVKAQSQTDRVDLG')
WRONG = ('MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEG')
G12D = 'VVVGADGVGK'


def capture(tmp_path, body=None):
    text = body if body is not None else (
        'pMHC challenge\nAllele A*11:01\nHeavy chain (mature):\n' + RIGHT + '\n'
        'Peptide: ' + G12D + '\nBinder length 10 to 250 aa.\nTrack 1: 40 slots.\n'
        'Ranked on mutation specificity, peptide-dependence and affinity.\n')
    path = tmp_path / 'challenge_verbatim.txt'
    path.write_text(text)
    return path


def write(lane, **over):
    path = capture(lane) if 'capture' not in over else over.pop('capture')
    doc = dict(schema=1, challenge='pMHC', capture=str(path),
               capture_sha256=spec.digest(path),
               verbatim={'heavy_chain': RIGHT, 'peptide': G12D, 'allele': 'A*11:01'},
               lengths={'heavy_chain': len(RIGHT), 'peptide': 10},
               size_cap={'min_len': 10, 'max_len': 250, 'track1_slots': 40},
               ranking=[{'condition': 'mutation specificity', 'scored': True},
                        {'condition': 'peptide-dependence', 'scored': True},
                        {'condition': 'affinity', 'scored': True}])
    doc.update(over)
    (lane / 'SPEC.json').write_text(json.dumps(doc))
    return doc


def test_the_wrong_target_is_refused_by_name(tmp_path):
    """The 10-27 failure. The lane declares A*02:01 with its leader; the capture says A*11:01."""
    write(tmp_path, verbatim={'heavy_chain': WRONG, 'peptide': G12D, 'allele': 'A*11:01'},
          lengths={'heavy_chain': len(WRONG), 'peptide': 10})
    errors = spec.verify(tmp_path)
    assert any(e.startswith('WRONG_TARGET') and 'heavy_chain' in e for e in errors), errors


def test_the_right_target_passes(tmp_path):
    write(tmp_path)
    assert spec.verify(tmp_path) == []


def test_a_leader_peptide_shows_up_as_a_length(tmp_path):
    """Even if a string is somewhere in the page, the declared length has to match it. A leading
    MAVMAPRTLL... is how the wrong chain looked right at a glance."""
    body = ('Allele A*11:01\n' + WRONG + '\n' + RIGHT + '\nPeptide: ' + G12D +
            '\n10 to 250 aa, 40 slots\n')
    path = capture(tmp_path, body)
    write(tmp_path, capture=path, capture_sha256=spec.digest(path),
          verbatim={'heavy_chain': WRONG, 'peptide': G12D, 'allele': 'A*11:01'},
          lengths={'heavy_chain': 281, 'peptide': 10})
    errors = spec.verify(tmp_path)
    assert any(e.startswith('WRONG_LENGTH') for e in errors), errors


def test_an_unpinned_capture_proves_nothing(tmp_path):
    write(tmp_path, capture_sha256='')
    assert any('not pinned' in e for e in spec.verify(tmp_path))


def test_a_capture_that_changed_needs_a_person(tmp_path):
    """A capture edited after it was pinned invalidates every round scored against it, which is
    the one failure that cannot be fixed by rerunning."""
    write(tmp_path)
    (tmp_path / 'challenge_verbatim.txt').write_text('a different page entirely\n')
    errors = spec.verify(tmp_path)
    assert any('CHANGED' in e for e in errors), errors
    assert any('needs a person' in e for e in errors), errors


def test_a_missing_capture_is_not_an_excuse(tmp_path):
    write(tmp_path)
    (tmp_path / 'challenge_verbatim.txt').unlink()
    assert any('capture is missing' in e for e in spec.verify(tmp_path))


def test_a_ranking_condition_with_no_answer_is_refused(tmp_path):
    """peptide-dependence is in the challenge's ranking and was nearly dropped. A condition that
    is neither scored nor excused is the one that disappears."""
    write(tmp_path, ranking=[{'condition': 'mutation specificity', 'scored': True},
                             {'condition': 'peptide-dependence'},
                             {'condition': 'affinity', 'excused': 'ranked only among selective '
                                                                  'hits; none yet'}])
    errors = spec.verify(tmp_path)
    assert any('neither scored nor excused' in e and 'peptide-dependence' in e for e in errors)
    # An excused condition with a reason is fine: the point is that it was answered.
    assert not any('affinity' in e for e in errors), errors


def test_a_condition_cannot_be_both(tmp_path):
    write(tmp_path, ranking=[{'condition': 'affinity', 'scored': True, 'excused': 'also this'}])
    assert any('both scored and excused' in e for e in spec.verify(tmp_path))


def test_an_empty_ranking_is_refused(tmp_path):
    for value in ([], 'affinity', None):
        write(tmp_path, ranking=value)
        assert any('non-empty list' in e for e in spec.verify(tmp_path)), value


def test_a_size_cap_that_is_not_in_the_capture_is_refused(tmp_path):
    """Weak on its own, and it still catches a capture that is not the page the cap came from."""
    write(tmp_path, size_cap={'max_len': 9999})
    assert any('does not appear anywhere in the capture' in e for e in spec.verify(tmp_path))
    write(tmp_path, size_cap={})
    assert any('size_cap must be a non-empty object' in e for e in spec.verify(tmp_path))


def test_no_spec_at_all_is_the_refusal_that_matters(tmp_path):
    """Applies to every lane. An assertion a lane can skip by not writing the file is not one."""
    errors = spec.verify(tmp_path)
    assert len(errors) == 1 and errors[0].startswith('NO_SPEC')
    assert '115 rounds' in errors[0]


def test_unreadable_json_is_not_silently_an_absent_spec(tmp_path):
    (tmp_path / 'SPEC.json').write_text('{not json')
    errors = spec.verify(tmp_path)
    assert len(errors) == 1 and 'unreadable' in errors[0]


def test_a_lane_with_no_challenge_says_so_and_still_declares_its_ranking(tmp_path):
    """math and planets have no challenge page. "Nothing to pin" is a fine answer; silence is not."""
    (tmp_path / 'SPEC.json').write_text(json.dumps(dict(
        schema=1, challenge=None,
        no_challenge_reason='open problem from the literature; the bar is a published constant, '
                            'not a page that can change',
        ranking=[{'condition': 'beats the published constant', 'scored': True}])))
    assert spec.verify(tmp_path) == []
    # Without the reason it is just an empty declaration.
    (tmp_path / 'SPEC.json').write_text(json.dumps(dict(
        schema=1, challenge=None,
        ranking=[{'condition': 'beats the published constant', 'scored': True}])))
    assert any('gives no reason' in e for e in spec.verify(tmp_path))


def test_the_schema_is_asserted(tmp_path):
    write(tmp_path, schema=2)
    assert any('schema must be 1' in e for e in spec.verify(tmp_path))


def test_pin_records_the_current_hash_and_says_when_it_moved(tmp_path, capsys):
    write(tmp_path, capture_sha256='0' * 64)
    assert spec.main(['--lane', str(tmp_path), 'pin']) == 0
    out = capsys.readouterr().out
    assert 'WAS' in out and 'The capture changed since it was last pinned' in out
    assert spec.verify(tmp_path) == []


def test_check_exits_non_zero_on_a_wrong_target(tmp_path, capsys):
    write(tmp_path, verbatim={'heavy_chain': WRONG}, lengths={})
    assert spec.main(['--lane', str(tmp_path), 'check']) == 2
    assert 'WRONG_TARGET' in capsys.readouterr().err


# --- the live page, the other half ---------------------------------------------------------

def test_diff_names_what_left_the_page(tmp_path, monkeypatch):
    """The capture is a point in time. A target that moves upstream has to be caught, not assumed
    away, which is the scheduled half of this."""
    write(tmp_path, capture_url='https://example.org/challenge')
    monkeypatch.setattr(spec, 'fetch', lambda url, max_bytes=None:
                        'the page now says A*02:01 and nothing else')
    gone, note = spec.diff(tmp_path)
    assert gone == ['allele', 'heavy_chain', 'peptide']
    assert 'https://example.org/challenge' in note
    assert spec.main(['--lane', str(tmp_path), 'diff']) == 2


def test_diff_passes_when_the_page_still_says_it(tmp_path, monkeypatch):
    write(tmp_path, capture_url='https://example.org/challenge')
    monkeypatch.setattr(spec, 'fetch', lambda url, max_bytes=None:
                        'A*11:01 ' + RIGHT + ' ' + G12D)
    assert spec.diff(tmp_path)[0] == []
    assert spec.main(['--lane', str(tmp_path), 'diff']) == 0


def test_diff_without_a_url_refuses_rather_than_reporting_nothing_wrong(tmp_path):
    write(tmp_path)
    with pytest.raises(ValueError) as e:
        spec.diff(tmp_path)
    assert 'capture_url' in str(e.value)
    assert spec.main(['--lane', str(tmp_path), 'diff']) == 2


def test_fetch_refuses_a_non_http_url(tmp_path):
    with pytest.raises(ValueError):
        spec.fetch('file:///etc/passwd')


# --- the round gate ------------------------------------------------------------------------

def test_the_round_gate_refuses_a_lane_whose_target_is_wrong(tmp_path):
    """This is the point of the whole file: `rounds.py start` cannot open a round against a target
    the challenge does not state, however healthy the lane's own ledgers look."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import rounds
    write(tmp_path, verbatim={'heavy_chain': WRONG}, lengths={})
    (tmp_path / 'KB_CONSULTS.jsonl').write_text(json.dumps(
        dict(utc='2026-11-07T00:00:00Z', note='consulted')) + '\n')
    errors, _ = rounds.gate(tmp_path, 'minibinder')
    assert any(e.startswith('WRONG_TARGET') for e in errors), errors


def test_the_round_gate_is_quiet_when_the_spec_holds(tmp_path):
    import rounds
    write(tmp_path)
    (tmp_path / 'KB_CONSULTS.jsonl').write_text(json.dumps(
        dict(utc='2026-11-07T00:00:00Z', note='consulted')) + '\n')
    errors, _ = rounds.gate(tmp_path, 'minibinder')
    assert not [e for e in errors if 'SPEC' in e or 'TARGET' in e], errors
