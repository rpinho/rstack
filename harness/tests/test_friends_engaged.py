"""Friends work goes only to people who replied (Ricardo, 11-11): contacts matching and the sweep refusal.
All names are invented."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import contacts_ledger

ROWS = [dict(name='Ana Brandão', last_in='2026-10-29 14:01 LinkedIn'),
        dict(name='Tomas Quaresma', last_in='2026-11-07T20:03Z forwarded'),
        dict(name='Inês Varela', last_in='2026-11-06 12:26Z email'),
        dict(name='Varela Nogueira e Sá', last_in=''),
        dict(name='Olga Pinto', last_in=''),
        dict(name='Rita Lobo')]


def test_names_match_without_accents_or_middle_initials():
    assert contacts_ledger.find_person('Ana Brandao', ROWS)['name'] == 'Ana Brandão'
    assert contacts_ledger.find_person('Tomas J. Quaresma', ROWS)['name'] == 'Tomas Quaresma'
    assert contacts_ledger.find_person('Ines Varela', ROWS)['name'] == 'Inês Varela'
    assert contacts_ledger.find_person('Varela', ROWS) is None          # two people: never guess


def test_only_people_who_replied_pass(tmp_path, monkeypatch):
    monkeypatch.setenv('RH_CONTACT_UPDATES', str(tmp_path / 'updates.jsonl'))
    (tmp_path / 'updates.jsonl').write_text(json.dumps(dict(
        event='answered', name='Olga Pinto', utc='2026-11-09T12:13:12+00:00', question='uses AI')) + '\n')
    targets = ['Ana Brandao, Rita Lobo: open questions', 'Tomas J. Quaresma and Olga Pinto: routing',
               'Varela Nogueira e Sa: restriction constants', 'no person here']
    refused = contacts_ledger.not_engaged(tmp_path, targets, ROWS)
    assert refused == [('Rita Lobo', 'has not replied'), ('Varela Nogueira e Sa', 'has not replied'),
                       ('no person here', 'names nobody before a colon')]
