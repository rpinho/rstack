"""Contact protection uses synthetic fixtures only; no private inputs are loaded here."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from rstack_hookcall import TOOLS


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def sources(tmp_path):
    kb = tmp_path / 'wiki'
    (kb / 'health/records').mkdir(parents=True)
    (kb / 'people').mkdir()
    (kb / 'health/providers.md').write_text(
        '# Providers\nDoctor: Dr. Testname\nClinic: Example Clinic\n'
        'Portal: ExamplePortal\nDr. Li\nClinic: Clinic\nHealth\nHospital\n')
    (kb / 'health/records/visit.html').write_text(
        '<html><body><p>Ordering Provider: Recordname, MD</p>'
        '<p>Sample Eye Care</p><p>RecordChart - welcome</p>'
        '<script>Dr. Scriptname</script></body></html>')
    (kb / 'health/records/image.png').write_bytes(b'synthetic image')
    (kb / 'people/contact.md').write_text('Dr. Peoplename\n')
    contacts = tmp_path / 'contacts.json'
    contacts.write_text(json.dumps([
        dict(name='Dr. Jsonname', relationship='physician', org='Sample Medical Center'),
        dict(name='Friendname', relationship='friend', personal='Doctor: Dr. Othername'),
        dict(name='Regularname', relationship='friend', org='Example Software',
             channels={'profile': 'ExampleNetwork'}),
    ]))
    conf = tmp_path / 'egress'
    conf.mkdir()
    return kb, contacts, conf


def generate(sources, *args):
    kb, contacts, conf = sources
    return subprocess.run([sys.executable, str(TOOLS / 'egress-contacts'), str(conf / 'patterns.txt'),
                           '--kb', str(kb), '--contacts', str(contacts), *args],
                          text=True, capture_output=True, timeout=30)


def test_generator_extracts_private_rules_and_emits_only_counts(sources):
    kb, contacts, conf = sources
    old = '# existing\nemail\tsynthetic@example\\.invalid\ncontact\tManualname\n'
    (conf / 'patterns.txt').write_text(old)
    result = generate(sources)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['patterns'] >= 8
    assert summary['sources'][0]['files_read'] == 2
    assert summary['sources'][0]['files_skipped'] == 1
    assert summary['sources'][2]['records'] == 3
    assert summary['sources'][2]['medical_records'] == 1
    assert not any(n in result.stdout + result.stderr for n in ['Testname', 'Jsonname', 'ExamplePortal'])
    body = (conf / 'patterns.txt').read_text()
    assert body.startswith(old)
    assert (conf / 'patterns.txt').stat().st_mode & 0o777 == 0o600
    patterns = [re.compile(line.split('\t', 1)[1]) for line in body.splitlines() if line.startswith('contact\t')]
    matches = lambda text: any(rx.search(text) for rx in patterns)
    for name in ['TESTNAME', 'Example Clinic', 'exampleportal', 'Jsonname', 'Recordname',
                 'Peoplename', 'Othername', 'Sample Eye Care', 'Sample Medical Center', 'RecordChart']:
        assert matches(name), name
    for text in ['PreTestnameSuffix', 'ExamplePortalExtra', '_Testname', 'Friendname',
                 'Regularname', 'ExampleNetwork', 'Scriptname', 'Li', 'clinic health hospital provider portal']:
        assert not matches(text), text
    assert generate(sources).returncode == 0
    assert (conf / 'patterns.txt').read_text() == body  # regeneration doesn't append duplicates
    (kb / 'health/providers.md').write_text('Doctor: Dr. Replacementname\n')
    assert generate(sources).returncode == 0
    changed = (conf / 'patterns.txt').read_text()
    assert 'testname' not in changed and 'replacementname' in changed
    assert changed.startswith(old)


def test_generator_dry_run_and_input_errors_leave_patterns_untouched(sources):
    kb, contacts, conf = sources
    output = conf / 'patterns.txt'
    assert generate(sources, '--dry-run').returncode == 0
    assert not output.exists()
    output.write_text('# existing\n')
    contacts.write_text('{invalid private content Testname')
    result = generate(sources)
    assert result.returncode == 1 and 'Testname' not in result.stderr
    assert output.read_text() == '# existing\n'
    contacts.write_text('[]')
    output.write_text('# BEGIN egress-contacts\ncontact\tOldname\n')
    original = output.read_text()
    assert generate(sources).returncode == 1
    assert output.read_text() == original


def test_structured_contacts_and_literal_whole_word_patterns():
    mod = load('contacts_under_test', TOOLS / 'egress-contacts')
    names, records, medical = mod.contact_names({'contacts': {
        'Dr. Mapname': {'role': 'doctor', 'portal': 'ExamplePortal', 'aliases': ['Aliasname']},
        'Friendname': {'role': 'friend'},
    }})
    assert records == 2 and medical == 1
    assert {'mapname', 'aliasname', 'exampleportal'} <= names
    assert 'friendname' not in names
    rx = re.compile(mod.pattern("Example+ Portal"))
    assert rx.search('EXAMPLE+  PORTAL.')
    assert not rx.search('Exampleee Portal') and not rx.search('Example+ PortalExtra')
    names = set()
    for value in ['Dr. Li', 'A. B.', 'clinic', 'health', 'hospital', 'Medical Clinic']:
        mod.add(names, value)
    assert names == set()
    assert 'example clinic' in mod.text_names('EXAMPLE CLINIC')
    assert mod.text_names('The medical team will call.') == set()
    names, _, _ = mod.contact_names([dict(name='Friendname', relationship='friend',
                                         channels={'profile': 'ExampleNetwork'})])
    assert names == set()


def test_generated_contact_rules_keep_importer_apis(sources, monkeypatch):
    _, _, conf = sources
    assert generate(sources).returncode == 0
    (conf / 'agent-files.gitignore').write_text('# working files\nCLAUDE.md\n.claude/\n')
    (conf / 'allow.txt').write_text('/srv/backups/*\tcontact\tapproved/*\towner approved\n')
    monkeypatch.setenv('RSTACK_EGRESS_DIR', str(conf))
    gate = load('contact_gate_import', TOOLS / 'egress-gate')
    rules = gate.load_patterns()
    assert {label for label, _ in rules} == {'contact'}
    assert gate.hits_in('Dr. TESTNAME', rules) == [('contact', 'TESTNAME')]
    assert not gate.hits_in('PreTestnameSuffix', rules)
    assert gate.load_agent_files() == ['claude.md', '.claude/']
    assert gate.load_allow('/srv/backups/example') == [('contact', 'approved/*')]


@pytest.mark.parametrize('text,blocked', [
    ('Dr. TESTNAME', True), ('The ExamplePortal message', True),
    ('The example clinic visit', True), ('PreTestnameSuffix ExamplePortalExtra', False),
])
def test_pre_push_contact_rules(sources, tmp_path, text, blocked):
    _, _, conf = sources
    assert generate(sources).returncode == 0
    repo = tmp_path / 'repo'
    repo.mkdir()
    env = dict(os.environ, RSTACK_EGRESS_DIR=str(conf))
    # No network or push: exercise the real hook with a synthetic ref update.
    def git(*args):
        return subprocess.run(['git', '-c', 'user.name=Synthetic', '-c',
                               'user.email=synthetic@example.invalid', *args], cwd=repo,
                              env=env, text=True, capture_output=True, check=True).stdout.strip()
    git('init', '-q', '-b', 'main')
    (repo / 'note.txt').write_text(text + '\n')
    git('add', 'note.txt')
    git('commit', '-qm', 'Synthetic change')
    head = git('rev-parse', 'HEAD')
    result = subprocess.run([sys.executable, str(TOOLS / 'egress-gate'), 'pre-push', 'origin',
                             'https://example.invalid/synthetic.git'],
                            cwd=repo, env=env, text=True, capture_output=True, timeout=30,
                            input='refs/heads/main {} refs/heads/main {}\n'.format(head, '0' * 40))
    assert result.returncode == (2 if blocked else 0), result.stdout + result.stderr
    if blocked:
        assert '[contact]' in result.stdout
