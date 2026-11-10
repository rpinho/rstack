"""Verification evidence for result/close rows. Standard library; no lane writes.

Receipts attest recorded executions, not authorship or the adequacy of a theorem
statement. See ../docs/verification.md for the schema and trust boundary.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile


LEVELS = ('L0', 'L1', 'L2', 'L3')
RULE_FROM = '2026-11-03T18:06:17+00:00'
STANDARD_AXIOMS = {'propext', 'Classical.choice', 'Quot.sound'}
EVIDENCE_FIELDS = {
    'verification', 'finite_component', 'verification_scope', 'finite_evidence',
    'producer_author', 'checker_author', 'certificate', 'checker',
    'checker_max_seconds', 'expected_output_sha256', 'run_receipt',
    'run_receipt_sha256', 'lean_project', 'build_receipt',
    'build_receipt_sha256', 'axioms_receipt', 'main_theorems',
}
FORBIDDEN = re.compile(r'(?<![\w\u0080-\uffff])(sorryAx|sorry|admit)(?![\w\u0080-\uffff])')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(value, base):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing file/path')
    path = Path(value).expanduser()
    return (Path(base) / path).resolve()


def hashed_file(value, digest, base, label):
    path = resolve(value, base)
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest) or sha256(path) != digest:
        raise ValueError(label + ': SHA256 hash mismatch or missing hash')
    return path


def object_json(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError('receipt/evidence must be a JSON object')
    return data


def command_words(command):
    if isinstance(command, str):
        command = shlex.split(command)
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ValueError('checker must be a command string or argv list')
    return command


def source_files(project):
    """Project sources, including local subprojects; cached dependencies excluded."""
    files = []
    for directory, dirs, names in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in {'.lake', '.git', '__pycache__'})
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise ValueError('source directory symlinks are unsupported')
        for name in sorted(names):
            if name.endswith('.lean') or name in {'lean-toolchain', 'lake-manifest.json', 'lakefile.toml'}:
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError('source symlinks are unsupported: ' + str(path))
                files.append(path)
    return sorted(files)


def source_hash(project):
    """SHA256 of sorted relative-name, NUL, file SHA256, newline records."""
    project = Path(project).resolve()
    records = ''.join(p.relative_to(project).as_posix() + '\0' + sha256(p) + '\n'
                      for p in source_files(project))
    return hashlib.sha256(records.encode()).hexdigest()


def _run_checker(argv, base, seconds):
    # Shell-free, bounded wall time, and temporary outputs. Kill descendants on
    # timeout too; a child holding stdout must not keep lint alive indefinitely.
    with tempfile.TemporaryDirectory(prefix='rh-checker-') as scratch, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        env = dict(os.environ, TMPDIR=scratch, PYTHONDONTWRITEBYTECODE='1')
        if sys.platform == 'darwin':
            # Read-only evidence replay: checkers can only write scratch files;
            # neither lane data nor external results can be changed by lint.
            profile = '(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (subpath ' + json.dumps(scratch) + '))'
            argv = ['/usr/bin/sandbox-exec', '-p', profile] + argv
        child = subprocess.Popen(argv, cwd=base, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
        try:
            code = child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise ValueError('L1 checker timed out')
        if code != 0:
            raise ValueError('L1 checker exited ' + str(code))
        stdout.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stdout.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def _l1(evidence, base, rerun):
    producer, author = evidence.get('producer_author'), evidence.get('checker_author')
    if not all(isinstance(x, str) and x.strip() for x in (producer, author)):
        raise ValueError('L1 requires producer_author and checker_author (model or party)')
    normalize = lambda x: ' '.join(x.casefold().split())
    if normalize(producer) == normalize(author):
        raise ValueError('L1 checker_author must differ from producer_author')
    certificate = resolve(evidence.get('certificate'), base)
    argv = command_words(evidence.get('checker'))
    seconds = evidence.get('checker_max_seconds')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('L1 checker_max_seconds must be a positive finite number')
    receipt = object_json(hashed_file(evidence.get('run_receipt'), evidence.get('run_receipt_sha256'), base, 'run receipt'))
    expected = evidence.get('expected_output_sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('L1 requires expected_output_sha256')
    if receipt.get('command') != argv or type(receipt.get('exit_code')) is not int or receipt['exit_code'] != 0:
        raise ValueError('L1 run receipt requires matching command and exit_code 0')
    if receipt.get('producer_author') != producer or receipt.get('checker_author') != author:
        raise ValueError('L1 run receipt author provenance mismatch')
    if receipt.get('certificate_sha256') != sha256(certificate) or receipt.get('output_sha256') != expected:
        raise ValueError('L1 certificate/output hash mismatch')
    # A slow run must remain tied to the checker implementation, not just argv.
    sources = receipt.get('checker_sources_sha256')
    if not isinstance(sources, dict) or not sources:
        raise ValueError('L1 receipt requires checker_sources_sha256')
    for name, digest in sources.items():
        hashed_file(name, digest, base, 'checker source')
    output = hashed_file(receipt.get('output'), expected, base, 'checker output')
    if FORBIDDEN.search(output.read_text(errors='replace')):
        raise ValueError('L1 checker output contains forbidden placeholder')
    if rerun and seconds <= 120 and _run_checker(argv, base, seconds) != expected:
        raise ValueError('L1 replay output hash mismatch')


def _axiom_declarations(text):
    """Canonical AXIOMS.md table: | `Fully.Qualified.name` | exact citation |."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    declared = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if not line.lstrip().startswith('|'):
            continue
        if len(cells) != 2:
            raise ValueError('AXIOMS.md: use exactly two columns (Axiom, Citation)')
        name = cells[0].strip('` ')
        if name.casefold() in {'axiom', 'name', 'non-standard axiom'} or re.fullmatch(r'[-: ]+', name):
            continue
        if not re.fullmatch(r'[\w.\u0080-\uffff]+', name):
            raise ValueError('AXIOMS.md: invalid axiom table row')
        citation = cells[1]
        if len(citation) < 12 or not re.search(r'https?://|doi:|arxiv:|ISBN', citation, re.I):
            raise ValueError('AXIOMS.md: axiom ' + name + ' needs an exact citation (URL/DOI/arXiv/ISBN and locator)')
        if not re.search(r'#|\b(?:theorem|thm|lemma|prop(?:osition)?|section|eq(?:uation)?|page|chapter)\b|§', citation, re.I):
            raise ValueError('AXIOMS.md: citation needs a theorem/section/page locator: ' + name)
        declared[name] = citation
    empty = bool(re.search(r'non-standard axiom list:\s*(?:\*\*)?empty\b', text, re.I))
    if empty and declared:
        raise ValueError('AXIOMS.md: empty list contradicts declared axioms')
    if not empty and not declared:
        raise ValueError('AXIOMS.md must declare its non-standard axiom list (table or empty)')
    return declared


def _lean(evidence, base, level):
    project = resolve(evidence.get('lean_project'), base)
    toolchain = (project / 'lean-toolchain').read_text().strip()
    if not re.fullmatch(r'leanprover/lean4:(?:v\d+\.\d+\.\d+(?:-[\w.-]+)?|[0-9a-f]{40})', toolchain):
        raise ValueError('lean-toolchain must pin a Lean release or commit')
    manifest = object_json(project / 'lake-manifest.json')
    packages = manifest.get('packages')
    if not isinstance(packages, list):
        raise ValueError('lake-manifest.json requires pinned packages')
    for package in packages:
        if not isinstance(package, dict) or package.get('type') != 'git' or not re.fullmatch(r'[0-9a-f]{40}', str(package.get('rev', ''))):
            raise ValueError('lake-manifest.json dependencies must be pinned git commits')
    if not any(p.suffix == '.lean' for p in source_files(project)):
        raise ValueError('Lean project has no sources')
    receipt = object_json(hashed_file(evidence.get('build_receipt'), evidence.get('build_receipt_sha256'), base, 'build receipt'))
    if receipt.get('command') != ['lake', 'build'] or type(receipt.get('exit_code')) is not int or receipt['exit_code'] != 0:
        raise ValueError('lake build receipt requires command [lake, build] and exit_code 0')
    if receipt.get('source_sha256') != source_hash(project):
        raise ValueError('lake build source hash mismatch')
    build = hashed_file(receipt.get('output'), receipt.get('output_sha256'), base, 'lake build output').read_text()
    if not re.search(r'Build completed successfully', build):
        raise ValueError('lake build output lacks success marker')
    if any(int(code) != 0 for code in re.findall(r'\bEXIT_CODE=(-?\d+)\b', build)):
        raise ValueError('lake build output records a nonzero exit code')
    axioms_path = hashed_file(evidence.get('axioms_receipt'), receipt.get('axioms_sha256'), base, 'axioms receipt')
    axioms = axioms_path.read_text()
    doc = hashed_file(str(project / 'AXIOMS.md'), receipt.get('axioms_md_sha256'), base, 'AXIOMS.md').read_text()
    declared = _axiom_declarations(doc)
    texts = [(str(p.relative_to(project)), p.read_text()) for p in source_files(project) if p.suffix == '.lean']
    texts += [('build receipt', build), ('axioms receipt', axioms), ('receipt metadata', json.dumps(receipt))]
    for name, text in texts:
        match = FORBIDDEN.search(text)
        if match:
            raise ValueError(name + ': forbidden ' + match.group())
    native = any(re.search(r'\bnative_decide\b|\bLean\.ofReduceBool\b', text) for _, text in texts)
    if native:
        lines = [line for line in doc.splitlines() if re.search(r'\bnative_decide\b', line)]
        if not any(len(re.sub(r'[`*]', '', line).strip()) > 40 and
                   re.search(r'trust|compil|kernel|evaluat|reduc', line, re.I) and
                   not re.search(r'\b(?:no|not|never|without|unused)\b', line, re.I) for line in lines):
            raise ValueError('native_decide requires an explanatory trust-boundary line in AXIOMS.md')
    found = {}
    # Include audit output printed during the build, so a separately trimmed
    # axioms receipt cannot conceal an inherited premise visible in that build.
    for match in re.finditer(r"'([^']+)' depends on axioms:\s*\[([^\]]*)\]", axioms + '\n' + build):
        name, values = match.groups()
        values = {x.strip() for x in values.split(',') if x.strip()}
        if name in found and values != found[name]:
            raise ValueError('conflicting axiom receipts for ' + name)
        found[name] = values
    for name in re.findall(r"'([^']+)' does not depend on any axioms", axioms + '\n' + build):
        if name in found and found[name]:
            raise ValueError('conflicting axiom receipts for ' + name)
        found[name] = set()
    mains = evidence.get('main_theorems')
    recorded = set(re.findall(r"'([^']+)' (?:depends on axioms:|does not depend on any axioms)", axioms))
    if not isinstance(mains, list) or not mains or not all(isinstance(n, str) and n in found and n in recorded for n in mains):
        raise ValueError('axioms_receipt must contain #print axioms output for each main_theorems entry')
    audit_requests = set(re.findall(r'^\s*#print\s+axioms\s+([\w.]+)', '\n'.join(t for _, t in texts[:-3]), re.M))
    if not set(mains) <= audit_requests:
        raise ValueError('main_theorems must have #print axioms requests in the hashed sources')
    nonstandard = set().union(*found.values()) - STANDARD_AXIOMS
    # Even unused explicit axioms must be disclosed, using their qualified name
    # from the table (or their literal name when outside a namespace).
    for _, text in texts[:-3]:
        for name in re.findall(r'^\s*(?:private\s+|protected\s+)?axiom\s+([\w.]+)', text, re.M):
            matches = {n for n in declared if n == name or n.endswith('.' + name)}
            if not matches and name not in STANDARD_AXIOMS:
                raise ValueError('unlisted source axiom: ' + name)
            nonstandard.update(matches)
    if nonstandard - declared.keys():
        raise ValueError('unlisted non-standard axiom(s): ' + ', '.join(sorted(nonstandard - declared.keys())))
    if level == 'L3' and (nonstandard or declared):
        raise ValueError('L3 requires an empty non-standard axiom list')


def validate_row(row, base, required=False, rerun=True):
    """Return evidence failures. Legacy untagged rows remain valid by default."""
    try:
        if not isinstance(row, dict):
            raise ValueError('verification row must be an object')
        tagged = any(k in row for k in ('verification', 'finite_component'))
        if required or tagged:
            if row.get('verification') not in LEVELS:
                raise ValueError('verification must be L0|L1|L2|L3')
            if row.get('finite_component') not in LEVELS + ('none',):
                raise ValueError('finite_component must be L0|L1|L2|L3|none')
        for component, level in (('verification', row.get('verification')), ('finite_component', row.get('finite_component'))):
            if level not in ('L1', 'L2', 'L3'):
                continue
            evidence = row
            if component == 'finite_component' and 'finite_evidence' in row:
                evidence = row['finite_evidence']
                if not isinstance(evidence, dict):
                    raise ValueError('finite_evidence must be an object')
            scope = evidence.get('verification_scope')
            if not isinstance(scope, str) or not scope.strip() or '\n' in scope:
                raise ValueError('verification_scope must name the exact certified/proved statement in one line')
            if level == 'L1':
                _l1(evidence, base, rerun)
            else:
                _lean(evidence, base, level)
        return []
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return ['verification: ' + str(exc)]


def new_close(row):
    if row.get('event') != 'close' and row.get('status') != 'closed':
        return False
    # A sweep read mark copies the closed row with a new `revised`; it is not a close. 11-10: math's
    # four 10-31/11-01 closes failed lint as new because their 11-03 read marks came after the
    # cutoff. The close itself was judged on its own row, under its own date.
    if row.get('event') == 'read':
        return False
    # A close written while the lane was not opted in remains historical when
    # the owner enables the rule later. External appenders have the cutoff.
    if row.get('verification_required_at_close') is False:
        return False
    if row.get('verification_policy_version') == 1:
        return True
    try:
        when = dt.datetime.fromisoformat((row.get('revised') or row.get('created', '')).replace('Z', '+00:00'))
        return when >= dt.datetime.fromisoformat(RULE_FROM)
    except (ValueError, TypeError, AttributeError):
        # Missing or malformed timestamps cannot grandfather an external close.
        return True


def apply_metadata(row, args, base, required=False):
    """Apply CLI metadata before append; never accept arbitrary row overrides."""
    explicit = args.verification is not None or args.finite_component is not None or args.verification_evidence is not None
    if explicit:
        for field in EVIDENCE_FIELDS:
            row.pop(field, None)  # A new attempt must not silently inherit receipts.
        if args.verification_evidence:
            path = args.verification_evidence.expanduser().resolve()
            evidence = object_json(path)
            unknown = evidence.keys() - EVIDENCE_FIELDS
            if unknown:
                raise ValueError('unknown verification evidence fields: ' + ', '.join(sorted(unknown)))
            row.update(evidence)
        if args.verification is not None:
            row['verification'] = args.verification
        if args.finite_component is not None:
            row['finite_component'] = args.finite_component
    elif args.action == 'result' or (args.action == 'close' and args.result_path and str(Path(args.result_path).expanduser().resolve()) != row.get('result_path')):
        for field in EVIDENCE_FIELDS:
            row.pop(field, None)
    errors = validate_row(row, base, required=required)
    if errors:
        raise ValueError('; '.join(errors))
    row['verification_policy_version'] = 1
    if args.action == 'close':
        row['verification_required_at_close'] = bool(required)


def verification_line(row):
    level, finite = row.get('verification', 'L0'), row.get('finite_component', 'none')
    if level not in LEVELS or finite not in LEVELS + ('none',):
        raise ValueError('invalid verification level')
    descriptions = {'L0': 'prose or AI review; no strict certificate claim',
                    'L1': 'exact finite certificate; differently authored checker',
                    'L2': 'Lean proof of the stated step; cited inherited axioms allowed',
                    'L3': 'Lean proof of the full scoped statement; standard axioms only'}
    scope = row.get('verification_scope', '')
    if '\n' in scope or '\r' in scope:
        raise ValueError('verification_scope must be one line')
    return 'Verification level: {} ({}{}); finite component: {}.'.format(
        level, descriptions[level], '; scope: ' + scope if scope else '', finite)


def publication_errors(file):
    """Check level claims against FILE.verification.json without running code.

    Any bare level token is treated as a claim, except explicitly labelled finite
    components. Conservative by design; quote discussions in separate documents.
    """
    path = Path(file)
    body = path.read_text()
    tokens = list(re.finditer(r'\b(?:L0|L1(?!-(?:same-agent|independence-unestablished|partial)\b)|L2|L3)\b', body, re.I))
    if not any(m.group().upper() != 'L0' for m in tokens):
        return []
    try:
        sidecar = object_json(str(path) + '.verification.json')
        if sidecar.get('sha256') != sha256(path):
            raise ValueError('publication verification sidecar body hash mismatch')
        row = sidecar.get('row')
        errors = validate_row(row, path.parent, required=True, rerun=False)
        if errors:
            return errors
        finite_spans = [m.span(1) for m in re.finditer(
            r'\bfinite(?:[ -]+(?:component|parts?|portion))?\s*(?:level)?\s*[:=]?\s*\**(L[0-3])\b', body, re.I)]
        for token in tokens:
            component = 'finite_component' if token.span() in finite_spans else 'verification'
            supported = row[component]
            if supported == 'none' or int(token.group()[1]) > int(supported[1]):
                raise ValueError('public ' + component + ' claim ' + token.group() + ' exceeds supported ' + supported)
        return []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return ['verification: ' + str(exc)]
