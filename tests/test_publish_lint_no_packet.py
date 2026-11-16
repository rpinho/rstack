"""11-16: a packet-less corollary or record-only PR passes the PR gate only with a matched science-publish
receipt AND a declaration; a body with a publish-lint receipt is always checked in full."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
import publish_lint  # noqa: E402

TARGET = 'https://github.com/owner/table#new'


def body_with(tmp_path, decl=None):
    body = tmp_path / 'pr-body.md'
    body.write_text('C8 follows from the published bounds in #205 and the 2025 paper.\n')
    if decl is not None:
        Path(str(body) + '.no-packet.json').write_text(json.dumps(decl))
    return body


GOOD = dict(kind='corollary', why='a three-line deduction from published results',
            references=['https://github.com/owner/table/pull/205', 'https://arxiv.org/abs/2501.00001'], target=TARGET)


def test_declared_corollary_with_matched_science_receipt_passes_and_is_logged(tmp_path):
    body = body_with(tmp_path, GOOD)
    assert publish_lint.publication_errors(str(body), TARGET, science_receipt_matched=True) == []
    log = Path(str(body) + '.no-packet.log').read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])['target'] == TARGET


def test_without_the_science_receipt_the_declaration_is_not_enough(tmp_path):
    body = body_with(tmp_path, GOOD)
    errors = publish_lint.publication_errors(str(body), TARGET)
    assert errors and 'publish-lint' in errors[0]
    assert not Path(str(body) + '.no-packet.log').exists()


def test_no_declaration_is_refused(tmp_path):
    body = body_with(tmp_path)
    errors = publish_lint.publication_errors(str(body), TARGET, science_receipt_matched=True)
    assert errors and 'no-packet.json' in errors[0]


def test_a_bad_declaration_is_refused(tmp_path):
    for bad in (dict(GOOD, kind='result'), dict(GOOD, why=''), dict(GOOD, references=[]),
                dict(GOOD, references=['not a url']), dict(GOOD, target='https://github.com/other/repo#new')):
        body = body_with(tmp_path, bad)
        assert publish_lint.publication_errors(str(body), TARGET, science_receipt_matched=True), bad


def test_a_body_with_a_publish_lint_receipt_is_always_checked_in_full(tmp_path):
    body = body_with(tmp_path, GOOD)
    publish_lint.receipt_path('.', str(body)).write_text(json.dumps({'utc': '2000-01-01T00:00:00+00:00'}))
    errors = publish_lint.publication_errors(str(body), TARGET, science_receipt_matched=True)
    assert errors and 'expired' in errors[0]          # the packet path ran; the declaration did not bypass it
