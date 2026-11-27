#!/usr/bin/env python3
"""Grade an executor attempt using the original job directory and checks.

launch.sh calls this when an attempt ends. The grade comes from the job's own acceptance checks first:
  - the executor's exit code for this selection (0 needed),
  - REPORT.md opens with "Shipped:" and STATUS.md with "You asked:" (the hard-rule lines),
  - every "Check: COMMAND" line in the spec, run in the work dir with a time limit.
All pass: pass. No exit 0 or no Shipped line: fail. Shipped but a check failed: partial. When the spec has no
Check lines, the call needs judgment, so the lane's reviewing model (the leaderboard's review pick, from
another family than the producer, never delegated) reads the spec and REPORT.md and answers
PASS, PARTIAL or FAIL. If that cannot be had, the job gets "void: <reason>" (counted, outside the rate).
An executor run that hit its quota is "void: quota" before any of this: infrastructure, not the model.
An effort-floor continuation that also quits early with no result is partial, including on a non-delegated route.
The row records the producer model and the grader (checks, or the reviewing model).

  auto_grade.py --receipt JOB.log.selection.json --log JOB.log --dir WORKDIR --spec JOB.md
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from shell_commands import command_argv, shell_commands  # noqa: E402
import worker_models as wm
import run_records
import score_verdicts
from model_slugs import canon  # noqa: E402

CHECK = re.compile(r'^[ \t]*[-*]?[ \t]*check:[ \t]*(\S.*)$', re.I | re.M)
VERDICT = re.compile(r'\b(PASS|PARTIAL|FAIL)\b')
CHECK_SECONDS = 600


def first_line(path):
    try:
        for line in Path(path).read_text(errors='replace').splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                return line.strip()
    except OSError:
        pass
    return ''


def exit_code(log, selection_id, run_id=None):
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith(('MODEL_OUTCOME ', 'MODEL_ATTEMPT_OUTCOME ')):
            try:
                row = json.loads(line.split(' ', 1)[1])
            except ValueError:
                continue
            if row.get('selection_id') == selection_id and (not run_id or row.get('run_id') == run_id):
                return row.get('exit_code')
    return None


# RULE #1 (11-20): a run the harness refused never reached the model, so it is never pass, partial or fail.
# math_huntfree_1120 was graded 'fail' for a refusal (exit 75). Exit 75 (tempfail) and 78 (config) are the
# launcher's refusal codes; the patterns are their refusal lines.
HARNESS_EXITS = (75, 78)
HARNESS_LINES = re.compile(r'^(?:launch\.sh (?:REFUSED|refused).*|'
                           r'launch-guard: REFUSED.*|\[[\w.-]+\] REFUSED \(.*|agent_executor refused: .*|'
                           # 11-22: the executor CLI is not installed where the job ran (ddbench_scan_1122, agy on the M4)
                           r"FileNotFoundError: \[Errno 2\] No such file or directory: '(?:[^']*/)?(?:agy|codex|claude)'|"
                           r'(?:zsh|bash|sh): (?:\d+: )?command not found: (?:agy|codex|claude)|'
                           r'(?:zsh|bash|sh): (?:\d+: )?(?:agy|codex|claude): command not found)$', re.M)


def selection_text(log, selection_id, run_id=None):
    """The log between this selection's MODEL_SELECTION and its MODEL_OUTCOME (the attempt's own output)."""
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return ''
    inside, part = False, []
    for line in lines:
        if line.startswith(('MODEL_SELECTION ', 'MODEL_ATTEMPT ', 'MODEL_OUTCOME ', 'MODEL_ATTEMPT_OUTCOME ')):
            try:
                row = json.loads(line.split(' ', 1)[1])
                mine = row.get('selection_id') == selection_id
            except (ValueError, AttributeError):
                mine = False
            if mine and line.startswith('MODEL_SELECTION '):
                inside = not run_id
            elif mine and row.get('run_id') == run_id:
                if line.startswith(('MODEL_OUTCOME ', 'MODEL_ATTEMPT_OUTCOME ')):
                    break
                inside, part = True, []
            continue
        if inside:
            part.append(line)
    return '\n'.join(part)


def harness_refusal(log, receipt, rc):
    """'harness: <reason>' when the wrapper or the launcher refused this run, else None."""
    found = HARNESS_LINES.findall(selection_text(log, receipt.get('selection_id'), receipt.get('run_id')))
    if found:
        return 'harness: ' + ' '.join(found[-1].split())[:300]
    if rc in HARNESS_EXITS:
        return 'harness: exit {} (a wrapper or launcher refusal code; the model did not run to completion)'.format(rc)
    return None


# Literal paths in acceptance checks. File-test operands can also be extensionless.
FILE_WORD = re.compile(r'(?:[~/]|\.{1,2}/|[^ /]+/|[^/]*\.[A-Za-z][A-Za-z0-9_-]*\Z)')
FILE_INPUTS = {'cat', 'cmp', 'diff', 'head', 'tail', 'wc', 'shasum', 'sha256sum'}
FILE_TESTS = {'-e', '-f', '-d', '-s', '-r', '-w', '-x', '-h', '-L', '-nt', '-ot', '-ef'}


def required_files(spec_text):
    paths = dict.fromkeys(('STATUS.md', 'REPORT.md'))
    for command in CHECK.findall(spec_text):
        for raw, _ in shell_commands(command):
            argv = command_argv(raw)
            if not argv:
                continue
            head = Path(argv[0]).name
            operands = argv if argv[0].startswith(('./', '../', '/')) else argv[1:]
            previous = ''
            for word in operands:
                token = word.strip('`[],;').split('::', 1)[0]
                if token.startswith('$PWD/'):
                    token = token[len('$PWD/'):]
                path_test = head in ('test', '[', '[[') and previous in FILE_TESTS
                named_path = FILE_WORD.fullmatch(token) or (
                    FILE_WORD.match(token) and ('/' in token or token.startswith('~')))
                if (token and not token.startswith(('-', '>')) and not any(c in token for c in '$*?<>|')
                        and '://' not in token and (path_test or previous == '<' or named_path
                                                       or (head in FILE_INPUTS and not token.isdigit()))):
                    paths[token] = None
                previous = word
    return list(paths)


def ssh_command(host, command):
    return shlex.split(os.environ.get('LAUNCH_SSH') or 'ssh') + [
        '-o', 'BatchMode=yes', host, command]


def inspect_workdir(workdir, files, host=''):
    if not host:
        missing = [name for name in files if not (
            (workdir / Path(name).expanduser()).is_file() if name in ('STATUS.md', 'REPORT.md')
            else (workdir / Path(name).expanduser()).exists())]
        return missing, first_line(workdir / 'STATUS.md'), first_line(workdir / 'REPORT.md')

    def check(name):
        # Permit the remote shell to expand its own home, without evaluating other substitutions.
        path = ('"$HOME"/' + shlex.quote(name[2:])) if name.startswith('~/') else shlex.quote(name)
        predicate = '-f' if name in ('STATUS.md', 'REPORT.md') else '-e'
        return 'test {} {} || printf "missing %s\\n" {}'.format(predicate, path, shlex.quote(name))

    commands = [check(name) for name in files]
    for field, name in [('status', 'STATUS.md'), ('report', 'REPORT.md')]:
        commands.append("awk -v tag='{} ' '/^[[:space:]]*($|#)/ {{next}} {{print tag $0; exit}}' "
                        "{} 2>/dev/null || :".format(field, name))
    try:
        result = subprocess.run(ssh_command(host, 'cd {} && {{ {}; }}'.format(
            shlex.quote(str(workdir)), '; '.join(commands))), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ['directory unavailable'], '', ''
    if result.returncode:
        return ['directory unavailable'], '', ''
    missing, headers = [], {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(' ')
        if key == 'missing':
            missing.append(value)
        else:
            headers[key] = value.strip()
    return missing, headers.get('status', ''), headers.get('report', '')


def run_checks(spec_text, workdir, host=''):
    """(command, passed) per Check: line. A --host job's outputs stay on the host (only STATUS.md, REPORT.md and
    a few small files come back), so its checks run there, in the same work dir, over ssh. 11-20: three jobs
    run on the m5 from the M4 shipped out.txt there and were graded fail by a reviewer reading the M4's copy."""
    results = []
    for command in CHECK.findall(spec_text or ''):
        try:
            if host:
                argv = ssh_command(host, 'cd {} && {}'.format(shlex.quote(str(workdir)), command))
                done = subprocess.run(argv, capture_output=True, timeout=CHECK_SECONDS)
            else:
                done = subprocess.run(command, shell=True, cwd=workdir, capture_output=True, timeout=CHECK_SECONDS)
            results.append((command, done.returncode == 0))
        except subprocess.TimeoutExpired:
            results.append((command, False))
    return results


def review(receipt, spec_text, workdir, roles_file=None):
    """(verdict, grader model, reason) from the lane's reviewing model, or (None, model, why)."""
    pick = wm.select('review', 'codex', path=roles_file, made_by=receipt.get('route_model') or receipt['model'],
                     job=receipt.get('job', '') + '-grade', lane=receipt.get('lane', ''), pin='auto-grade at return')
    model, backend = pick.get('route_model') or pick['model'], pick['executor']
    report = ''
    try:
        report = (Path(workdir) / 'REPORT.md').read_text(errors='replace')[:12000]
    except OSError:
        pass
    prompt = ('You grade a finished job. Read its spec and its REPORT.md below, and check the work dir {} if you '
              'need to. Answer on the first line with exactly one word: PASS (it shipped what the spec asked), '
              'PARTIAL (some of it) or FAIL (not usable), then explain why. Include CONTROLS, CONTRADICTING, '
              'and LABELS with the file, command, count or line you checked for each.\n\n--- SPEC ---\n{}\n\n'
              '--- REPORT.md ---\n{}\n').format(workdir, (spec_text or '')[:12000], report)
    executable = {'codex': os.environ.get('LAUNCH_CODEX', 'codex'), 'claude': os.environ.get('LAUNCH_CLAUDE', 'claude'),
                  'agy': os.environ.get('LAUNCH_AGY', 'agy')}[backend]
    with tempfile.TemporaryDirectory(prefix='rh-grade-') as box:
        out = Path(box) / 'grade.out'
        try:
            done = subprocess.run([sys.executable, str(HERE / 'agent_executor.py'), '--backend', backend,
                                   '--executable', executable, '--directory', str(workdir), '--model', model,
                                   '--effort', 'low', '--output', str(out), '--timeout-seconds', '900'],
                                  env={**{k: v for k, v in os.environ.items() if not k.startswith('RH_LAUNCH_')},
                                       'RH_JOB': receipt.get('job', '') + '-grade', 'RSTACK_CALL_ROLE': 'review'},
                                  input=prompt, capture_output=True, text=True, timeout=1000)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, model, 'grader did not run: {}'.format(exc)
        text = out.read_text(errors='replace') if out.exists() else done.stdout
    try:
        data = json.loads(text)
        text = str(data.get('result') or data.get('response') or text) if isinstance(data, dict) else text
    except ValueError:
        pass
    found = VERDICT.search(text.strip().splitlines()[0] if text.strip() else '')
    if done.returncode or not found:
        return None, model, 'grader gave no verdict (exit {})'.format(done.returncode)
    return found.group(1).lower(), model, ' '.join(text.split())[:300]


def effort_floor_note(receipt):
    floor = receipt.get('effort_floor')
    if isinstance(floor, dict):
        quit_at = floor.get('quit_at_seconds')
        budget = floor.get('budget_seconds')
        if type(quit_at) is int and type(budget) is int and 0 <= quit_at < budget:
            return 'effort floor: quit at {:.2f}/{:.2f} min, no result'.format(quit_at / 60, budget / 60)
    return ''


def grade(receipt_path, log, workdir, spec, roles_file=None, no_checks=False, host='', retried=False):
    receipt = json.loads(Path(receipt_path).read_text())
    workdir = Path(workdir).absolute()
    spec_text = Path(spec).read_text(errors='replace') if spec and Path(spec).is_file() else ''
    model = receipt.get('route_model') or receipt['model']
    model = canon(model) or model
    run_id = receipt.get('run_id')
    rc = exit_code(log, receipt.get('selection_id'), run_id)
    if run_id:
        try:
            metrics = {'rc': rc}
            for line in Path(log).read_text(errors='replace').splitlines():
                if line.startswith('EXECUTOR_RUN '):
                    try:
                        summary = json.loads(line[len('EXECUTOR_RUN '):])
                        if summary.get('run_id') == run_id:
                            metrics = {key: summary[key] for key in ('closed_at', 'wall_seconds', 'tokens', 'cost_usd', 'rc')
                                       if key in summary}
                    except (ValueError, AttributeError):
                        continue
            run_records.close_run(run_id, **metrics)
        except OSError as exc:
            run_records.warn(exc)
    quota = wm.quota_failure(log, receipt)
    refused = harness_refusal(log, receipt, rc)
    missing = []
    if run_records.is_probe(receipt) or os.environ.get('RH_RUN_PURPOSE') == 'probe':
        result, grader, reason = 'void: probe', 'probe', 'probe'
    elif quota:
        result, grader, reason = 'ungraded', 'quota', quota
    elif refused:
        result, grader, reason = 'ungraded', 'harness', refused
    elif retried and rc == 0:
        result, grader, reason = 'ungraded', 'launcher', 'attempt continued before grading'
    else:
        missing, status, report = inspect_workdir(workdir, required_files(spec_text), host)
        shipped, restated = report.startswith('Shipped:'), status.startswith('You asked:')
        floor_note = effort_floor_note(receipt) if rc == 0 else ''
        grader = 'checks'
        unreachable = 'directory unavailable' in missing or (not host and not workdir.is_dir())
        if missing and unreachable:
            # The only harness gap: the files may exist where the job ran, but this grader cannot see them.
            result, grader, reason = 'ungraded', 'harness', 'workdir incomplete: ' + ', '.join(missing)
        elif missing and '/sweep-work/runs/' in str(Path(log).absolute()):
            # 11-27: a sweep stage writes its stage output, not STATUS.md/REPORT.md; the sweep reports it.
            result, grader, reason, missing = 'void: sweep stage', 'harness', 'sweep stage: graded by its sweep', []
        elif missing:
            # 11-27: the job's own dir, on the host it ran on, has no REPORT.md (or a checked file): the model did
            # not ship it. That is the model's result (fail, or partial via the failed check), not a harness gap.
            reason_missing, missing = ', '.join(missing), []
            if rc != 0 or not shipped:
                result, reason = 'fail', 'exit {}; not shipped: {}'.format(rc, reason_missing)
            else:
                result, reason = 'partial', 'Shipped, but missing: ' + reason_missing
        elif floor_note:
            result, grader, reason = 'partial', 'effort floor', floor_note
        elif rc != 0 or not shipped:
            result, reason = 'fail', 'exit {}; Shipped line {}'.format(rc, 'yes' if shipped else 'no')
        else:
            checks = [] if no_checks else run_checks(spec_text, workdir, host)
            if checks:
                result = 'pass' if restated and all(ok for _, ok in checks) else 'partial'
                notes = ['You asked line ' + ('yes' if restated else 'no')]
                notes.extend('check {}: {}'.format('ok' if ok else 'FAILED', command[:80]) for command, ok in checks)
                reason = '; '.join(notes)
            elif host:
                result, grader, reason = 'ungraded', 'harness', 'review requires access to the execution host'
            elif receipt.get('source') != 'delegate':
                result, reason = 'ungraded', 'no acceptance checks or downstream review'
            else:
                result, grader, reason = review(receipt, spec_text, workdir, roles_file)
                result = result or 'ungraded'
    result = score_verdicts.migrate(result, dict(reason='quota' if quota else reason, grader=grader))
    row = dict(id='grade-' + (run_id or receipt['selection_id']), date=dt.date.today().isoformat(),
               source_kind='everyday', job=receipt.get('job'), grade=result, model=model, producer=model,
               grader=grader, role=receipt.get('role'), auto=True, note=reason[:500],
               reason='quota' if quota else reason, grade_host=host or socket.gethostname(),
               grade_dir=str(workdir), missing_files=missing)
    if run_id:
        row['run_id'] = run_id
    wm.log_record(Path(receipt_path).with_name('everyday-grades.jsonl'), '', row)
    wm.log_record(log, 'MODEL_GRADE', row)
    if result.startswith('void:') and receipt.get('source') == 'delegate' and grader not in ('harness', 'quota', 'launcher', 'probe'):
        wm.morning_report([(row['job'], receipt.get('lane'), model)], reason=reason)
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--dir', type=Path, required=True)
    p.add_argument('--spec', type=Path)
    p.add_argument('--roles-file', type=Path)
    p.add_argument('--no-checks', action='store_true', help='skip Check: commands')
    p.add_argument('--host', default='', help='the work ran on this ssh host: run the Check: commands there')
    p.add_argument('--retried', action='store_true')
    a = p.parse_args(argv)
    try:
        if a.host and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}', a.host):
            raise ValueError('--host must be an ssh alias')
        row = grade(a.receipt, a.log, a.dir, a.spec, a.roles_file, a.no_checks, a.host, a.retried)
        print('auto-graded {} {} (producer {}, grader {})'.format(row['job'], row['grade'], row['producer'],
                                                                  row['grader']))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print('auto_grade: ' + str(exc), file=sys.stderr)
        return 0   # never fails the job; --record-ungraded after it still records the return


if __name__ == '__main__':
    raise SystemExit(main())
