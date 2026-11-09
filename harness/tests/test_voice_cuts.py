"""Paper-cut (11-08): a draft in the author's name is built from their own messages. Synthetic banks only."""
import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice_cuts
from test_outreach import cli, draft, env  # noqa: F401

EN = ["i don't think that was deprecated yet",
      "does it work with older files, or only the new format?",
      "thanks, that makes sense",
      "probably, but I'm not sure it matters for small runs"]
PT = ["acho que não vale a pena mudar isso agora",
      "obrigado, faz sentido"]


@pytest.fixture
def banks(tmp_path, monkeypatch):
    for name, lines in (('en', EN), ('pt', PT)):
        (tmp_path / (name + '.jsonl')).write_text(''.join(json.dumps({'text': t}) + '\n' for t in lines))
    spec = tmp_path / 'banks.json'
    spec.write_text(json.dumps({'v2': {'path': 'en.jsonl', 'lang': 'en'}, 'pt': {'path': 'pt.jsonl', 'lang': 'pt'}}))
    monkeypatch.setenv('RH_VOICE_BANKS', str(spec))
    return voice_cuts.load_banks()


def codes(fails):
    return [f.split(':')[0] for f in fails]


def test_a_draft_cut_from_the_bank_passes(banks):
    fails, stats = voice_cuts.check('Does it work with older plots, or only the new format?', 'v2:2', 'older plots', banks)
    assert fails == [] and stats['word_cover'] == 1.0


def test_a_composed_draft_fails(banks):
    assert codes(voice_cuts.check('Fascinating work, I wonder how this generalizes.', None, '', banks)[0]) == ['VOICE_CUTS_MISSING']
    fails, _ = voice_cuts.check('Fascinating work, I wonder how this generalizes to other settings.', 'v2:2', '', banks)
    assert 'VOICE_CUTS_WORDS' in codes(fails) and 'VOICE_CUTS_PAIRS' in codes(fails)


def test_the_words_of_the_message_answered_are_subject_swaps(banks):
    draft = 'Does zarr shard tiling handle sparse stores, or only the new format?'
    assert voice_cuts.check(draft, 'v2:2', '', banks)[0]
    assert voice_cuts.check(draft, 'v2:2', 'zarr shard tiling can handle sparse stores now', banks)[0] == []


def test_no_translating_english_into_portuguese(banks):
    fails, _ = voice_cuts.check('Obrigado, faz sentido.', 'v2:3', '', banks)
    assert 'VOICE_CUTS_LANGUAGE' in codes(fails)
    assert voice_cuts.check('Obrigado, faz sentido.', 'pt:2', '', banks)[0] == []


def test_links_and_handles_are_not_scored(banks):
    """11-09: a link self-reply cut from a short line failed on com, github, https."""
    for draft in ('Thanks, that makes sense: https://github.com/example/tool',
                  'thanks, that makes sense github.com/example/tool/pull/3',
                  '@someone thanks, that makes sense www.example.org'):
        assert voice_cuts.check(draft, 'v2:3', '', banks) == ([], dict(lang='en', cuts=1, word_cover=1.0, pair_cover=1.0))
    # Composed words beside a link are still scored, and the link's parts are not listed as missing.
    fails, _ = voice_cuts.check('Fascinating new tool here: https://github.com/example/tool', 'v2:3', '', banks)
    words = [f for f in fails if f.startswith('VOICE_CUTS_WORDS')]
    assert words and 'fascinating' in words[0] and 'github' not in words[0] and 'https' not in words[0]


def test_bad_cuts_are_named(banks):
    fails, _ = voice_cuts.check('thanks, that makes sense', 'v2:99\nxx:1\nnonsense', '', banks)
    assert codes(fails).count('VOICE_CUTS_BAD') == 3


def test_greeting_and_signoff_are_not_counted(banks):
    draft = 'Hi Dana,\n\nthanks, that makes sense\n\nBest,\nSam\n'
    assert voice_cuts.check(draft, 'v2:3', '', banks, signature_names=['Sam'])[0] == []


def test_a_pass_is_recorded_by_its_normalized_text(banks, tmp_path):
    draft = tmp_path / 'reply.txt'
    draft.write_text('thanks, that makes sense\n')
    (tmp_path / 'reply.txt.cuts').write_text('v2:3\n')
    assert voice_cuts.main([str(draft)]) == 0
    assert voice_cuts.passed('thanks,   that makes sense\n\n> their old text')
    assert not voice_cuts.passed('thanks, that makes no sense')
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    assert not voice_cuts.passed('thanks, that makes sense', clock=later)


def test_outreach_lint_requires_the_cuts_when_banks_are_configured(env, banks):
    ident, path = draft(env, 'Does it work with older files, or only the new format?', to='@someone', channel='x_reply')
    assert 'VOICE_CUTS_MISSING' in cli(env[0], 'lint', 'test', ident)[1]
    Path(str(path) + '.cuts').write_text('v2:2\n')
    rc, out, _ = cli(env[0], 'lint', 'test', ident)
    assert 'VOICE_CUTS' not in out and 'cuts: 1 lines' in out


def test_a_lane_can_turn_it_off_or_require_it(env, banks, monkeypatch):
    root, lane = env
    ident, _ = draft(env, 'A composed reply with nothing cut.', to='@someone', channel='x_reply')
    (lane / 'OUTREACH.toml').write_text('voice_cuts = "off"\n')
    assert 'VOICE_CUTS' not in cli(root, 'lint', 'test', ident)[1]
    (lane / 'OUTREACH.toml').write_text('voice_cuts = "on"\n')
    monkeypatch.delenv('RH_VOICE_BANKS')
    assert 'VOICE_BANKS_MISSING' in cli(root, 'lint', 'test', ident)[1]
    (lane / 'OUTREACH.toml').write_text('voice_cuts = "sometimes"\n')
    rc, out, err = cli(root, 'lint', 'test', ident)
    assert rc != 0 and 'voice_cuts' in (out + err)


def test_rh_runs_it(banks, tmp_path):
    import rh
    draft = tmp_path / 'r.txt'
    draft.write_text('thanks, that makes sense')
    (tmp_path / 'r.txt.cuts').write_text('v2:3')
    assert rh.main(['voice-cuts', str(draft)]) == 0
