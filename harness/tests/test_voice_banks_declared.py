"""A voice bank is citable as soon as it is declared in RH_VOICE_BANKS. Synthetic banks only.

11-18: the dictation bank was documented and filled, but missing from the host's banks file, so a draft
citing the author's approved lines failed VOICE_CUTS_BAD."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice_cuts


def test_a_bank_is_citable_only_once_it_is_declared(tmp_path, monkeypatch, capsys):
    (tmp_path / 'en.jsonl').write_text(json.dumps({'text': 'thanks, that makes sense'}) + '\n')
    (tmp_path / 'dict.jsonl').write_text(json.dumps({'text': 'I think one agent searches and the other one referees it.',
                                                     'source': 'chat 2026-11-18'}) + '\n')
    spec = tmp_path / 'banks.json'
    spec.write_text(json.dumps({'v2': {'path': 'en.jsonl', 'lang': 'en'}}))
    monkeypatch.setenv('RH_VOICE_BANKS', str(spec))
    monkeypatch.setenv('RH_VOICE_CUTS_STATE', str(tmp_path / 'state'))
    draft = tmp_path / 'p.md'
    draft.write_text('I think one agent searches and the other one referees it.\n')
    (tmp_path / 'p.md.cuts').write_text('dicten:1\n')

    assert voice_cuts.main([str(draft)]) == 1
    assert 'VOICE_CUTS_BAD: "dicten:1"' in capsys.readouterr().out

    spec.write_text(json.dumps({'v2': {'path': 'en.jsonl', 'lang': 'en'},
                                'dicten': {'path': 'dict.jsonl', 'lang': 'en'}}))
    assert voice_cuts.main([str(draft)]) == 0
    assert 'PASS' in capsys.readouterr().out
