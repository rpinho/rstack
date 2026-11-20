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


def test_a_line_he_dictated_or_approved_is_added_and_can_be_cut_from(tmp_path):
    """11-12: the gate made general drop a line Ricardo had already approved in chat. His own words
    go into a bank (append-only, with a source) and a draft cut from that line passes."""
    spec = tmp_path / 'banks.json'
    spec.write_text(json.dumps({'dicten': {'path': 'dict_en.jsonl', 'lang': 'en'}}))
    banks = voice_cuts.load_banks(spec)
    line = 'We moved to Florida for the kids and I still work on the research side'
    assert voice_cuts.add_line('dicten', line, 'chat with general 2026-11-12', banks) == 'dicten:1'
    assert voice_cuts.add_line('dicten', line, 'chat again 2026-11-12', banks) == 'dicten:1'   # no duplicate
    rows = [json.loads(l) for l in (tmp_path / 'dict_en.jsonl').read_text().splitlines()]
    assert len(rows) == 1 and rows[0]['source'] == 'chat with general 2026-11-12'
    for bad in (('nope', line, 'chat 2026-11-12'), ('dicten', line, 'chat'),
                ('dicten', 'Estamos na Florida por causa dos miudos e da escola', 'chat 2026-11-12')):
        with pytest.raises(ValueError):
            voice_cuts.add_line(*bad, banks)
    draft = tmp_path / 'reply.txt'
    draft.write_text(line + '\n')
    (tmp_path / 'reply.txt.cuts').write_text('dicten:1\nWE-OK: family, the kids and I\n')
    fails, _ = voice_cuts.check(draft.read_text(), voice_cuts.cuts_for(draft), '', banks)
    assert fails == []


def test_names_and_addresses_are_facts_not_phrasing():
    banks = {'corpus': (None, 'en')}
    import voice_cuts as vc
    orig = vc.bank_line
    vc.bank_line = lambda b, n, i: ({1: 'Sorry my bad.', 2: 'thank you.', 3: "It's just that it's at the end."}[i], None)
    try:
        ok, _ = vc.check("Sorry my bad, it's at 646 Virginia St #202, Dunedin, FL 34698. Thank you",
                         'corpus:1\ncorpus:2\ncorpus:3', banks=banks)
        bad, _ = vc.check('we would greatly appreciate a quick update on the overall timeline for this request',
                          'corpus:1\ncorpus:2', banks=banks)
    finally:
        vc.bank_line = orig
    assert not [f for f in ok if f.startswith('VOICE_CUTS_WORDS')]
    assert [f for f in bad if f.startswith('VOICE_CUTS_WORDS')]


# 11-19 (Ricardo: "We don't say 'we'. We always say 'I'."): a maintainer read the plural ask as a company.
OLD_ASK = "Thanks! We would be glad to help in any way we can. What would be helpful for you? What's a hard problem?"
NEW_ASK = "Thanks! I'd be glad to help in any way I can. What would be helpful for you? What's a hard problem?"


@pytest.fixture
def dicten(tmp_path, monkeypatch):
    """A synthetic dictation bank with the real line numbers: 105-107 the ask, 106 retired for 113."""
    lines = ['filler line {}'.format(n) for n in range(1, 113)] + ["I'd be glad to help in any way I can."]
    lines[104] = 'Hey, I understand this is not helpful. What would be helpful?'
    lines[105] = 'We would be glad to help in any way we can.'
    lines[106] = "What would be helpful for you? What's a hard problem?"
    lines[110] = 'We moved to Florida for the kids and we like it here.'
    (tmp_path / 'dict_en.jsonl').write_text(''.join(json.dumps({'text': t}) + '\n' for t in lines))
    (tmp_path / 'dict_pt.jsonl').write_text(json.dumps({'text': 'obrigado, faz sentido e acho que vale a pena'}) + '\n')
    spec = tmp_path / 'voice-banks.json'
    spec.write_text(json.dumps({'dicten': {'path': 'dict_en.jsonl', 'lang': 'en'},
                                'dictpt': {'path': 'dict_pt.jsonl', 'lang': 'pt'}}))
    (tmp_path / 'voice-retired.json').write_text(json.dumps(
        {'dicten:106': {'reason': 'we, not I (2026-11-19)', 'use': 'dicten:113'}}))
    monkeypatch.setenv('RH_VOICE_BANKS', str(spec))
    monkeypatch.setenv('RH_VOICE_CUTS_STATE', str(tmp_path / 'state'))
    return voice_cuts.load_banks()


def run(tmp_path, text, cuts, capsys):
    draft = tmp_path / 'ask.txt'
    draft.write_text(text + '\n')
    (tmp_path / 'ask.txt.cuts').write_text(cuts)
    rc = voice_cuts.main([str(draft)])
    return rc, capsys.readouterr().out


def test_the_old_plural_ask_fails_and_names_the_line_and_word(dicten, tmp_path, capsys):
    rc, out = run(tmp_path, 'Hi,\n' + OLD_ASK, 'dicten:105\ndicten:107\ndicten:113\n', capsys)
    assert rc == 1 and 'VOICE_PLURAL: line 2 "We", line 2 "we"' in out
    for word in ("we'd", "we're", "we've", "we'll", 'our', 'ours', 'us', 'OUR', 'We’ll'):
        fails = voice_cuts.plural_failures('That helps {} a lot.'.format(word))
        assert fails and '"{}"'.format(word) in fails[0]
    assert voice_cuts.plural_failures('They answered weekly, in their house, with jokes about fuses.') == []


def test_the_new_ask_passes(dicten, tmp_path, capsys):
    rc, out = run(tmp_path, NEW_ASK, 'dicten:105\ndicten:107\ndicten:113\n', capsys)
    assert rc == 0 and 'PASS' in out, out


def test_retired_dicten_106_fails(dicten, tmp_path, capsys):
    rc, out = run(tmp_path, NEW_ASK, 'dicten:106\ndicten:107\ndicten:113\n', capsys)
    assert rc == 1 and 'VOICE_CUTS_RETIRED: dicten:106 is retired' in out and 'dicten:113 instead' in out
    assert voice_cuts.load_retired() == {'dicten:106': {'reason': 'we, not I (2026-11-19)', 'use': 'dicten:113'}}


def test_a_we_ok_family_line_passes_and_xlint_honours_exactly_that_text(dicten, tmp_path, capsys):
    family = 'We moved to Florida for the kids and we like it here.'
    rc, out = run(tmp_path, family, 'dicten:111\n', capsys)
    assert rc == 1 and 'VOICE_PLURAL' in out
    assert voice_cuts.main(['plural', family]) == 1          # xlint's check: no WE-OK pass yet
    capsys.readouterr()
    rc, out = run(tmp_path, family, 'dicten:111\nWE-OK: family, the kids and I\n', capsys)
    assert rc == 0 and 'we_ok' in out, out
    assert voice_cuts.plural_lint(family) == [] and voice_cuts.main(['plural', family]) == 0
    assert voice_cuts.plural_lint('We moved to Florida for the kids.')   # a different text is not covered
    rc, out = run(tmp_path, family, 'dicten:111\nWE-OK:\n', capsys)
    assert rc == 1 and 'WE-OK needs a reason' in out


def test_a_portuguese_draft_passes(dicten, tmp_path, capsys):
    rc, out = run(tmp_path, 'Obrigado, faz sentido e acho que vale a pena.', 'dictpt:1\n', capsys)
    assert rc == 0, out
    assert voice_cuts.plural_failures('Obrigado, acho que vale a pena para nós e para a nossa casa.') == []


def test_us_the_country_passes():
    assert voice_cuts.plural_failures('I moved to the US in 2019 and I work on US data.') == []
    assert voice_cuts.plural_failures('Send it to us.')


def test_xlint_check_for_x_replies(dicten, capsys, monkeypatch):
    """xlint imports voice_cuts.plural_lint (`voice-cuts plural`, stdin as xlint reads it)."""
    import io
    monkeypatch.setattr('sys.stdin', io.StringIO('@someone ' + OLD_ASK))
    assert voice_cuts.main(['plural']) == 1 and 'VOICE_PLURAL' in capsys.readouterr().out
    monkeypatch.setattr('sys.stdin', io.StringIO('@someone ' + NEW_ASK))
    assert voice_cuts.main(['plural']) == 0


def test_outreach_lint_refuses_plural_even_with_cuts_off(env, banks, tmp_path):
    root, lane = env
    ident, path = draft(env, OLD_ASK, to='@someone', channel='x_reply')
    (lane / 'OUTREACH.toml').write_text('voice_cuts = "off"\n')
    assert 'VOICE_PLURAL' in cli(root, 'lint', 'test', ident)[1]
    ident, path = draft(env, NEW_ASK, to='@someone', channel='x_reply')
    assert 'VOICE_PLURAL' not in cli(root, 'lint', 'test', ident)[1]
