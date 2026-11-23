#!/usr/bin/env python3
"""Grade a returned delegated job at return, with no session in the loop.

general, 11-19: grading must not depend on anyone remembering. launch.sh calls this when a delegated job
ends. The grade comes from the job's own acceptance checks first:
  - the executor's exit code for this selection (0 needed),
  - REPORT.md opens with "Shipped:" and STATUS.md with "You asked:" (the hard-rule lines),
  - every "Check: COMMAND" line in the spec, run in the work dir with a time limit.
All pass: pass. No exit 0 or no Shipped line: fail. Shipped but a check failed: partial. When the spec has no
Check lines, the call needs judgment, so the lane's reviewing model (the leaderboard's review pick, from
another family than the producer, never delegated) reads the spec and REPORT.md and answers
PASS, PARTIAL or FAIL. If that cannot be had, the job stays "ungraded" (counted, outside the rate).
An agy run that hit its quota is "ungraded" with note "quota" before any of this: infrastructure, not the model.
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
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import worker_models as wm  # noqa: E402

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


def exit_code(log, selection_id):
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith('MODEL_OUTCOME '):
            try:
                row = json.loads(line.split(' ', 1)[1])
            except ValueError:
                continue
            if row.get('selection_id') == selection_id:
                return row.get('exit_code')
    return None


# RULE #1 (11-20): a run the harness refused never reached the model, so it is never pass, partial or fail.
# math_huntfree_1120 was graded 'fail' for the Codex wrapper's per-lane cap (exit 75). Exit 75 (tempfail) and
# 78 (config) are the wrapper's and the launcher's refusal codes; the patterns are their refusal lines.
HARNESS_EXITS = (75, 78)
HARNESS_LINES = re.compile(r'^(?:codex: REFUSED .*|codex-budget: REFUSED.*|launch\.sh (?:REFUSED|refused).*|'
                           r'launch-guard: REFUSED.*|\[[\w.-]+\] REFUSED \(.*|agent_executor refused: .*|'
                           r'npx: REFUSED .*|'
                           # 11-22: the executor CLI is not installed where the job ran (ddbench_scan_1122, agy on the M4)
                           r"FileNotFoundError: \[Errno 2\] No such file or directory: '(?:[^']*/)?(?:agy|codex|claude)'|"
                           r'(?:zsh|bash|sh): (?:\d+: )?command not found: (?:agy|codex|claude)|'
                           r'(?:zsh|bash|sh): (?:\d+: )?(?:agy|codex|claude): command not found)$', re.M)


def selection_text(log, selection_id):
    """The log between this selection's MODEL_SELECTION and its MODEL_OUTCOME (the attempt's own output)."""
    try:
        lines = Path(log).read_text(errors='replace').splitlines()
    except OSError:
        return ''
    inside, part = False, []
    for line in lines:
        if line.startswith(('MODEL_SELECTION ', 'MODEL_OUTCOME ')):
            try:
                mine = json.loads(line.split(' ', 1)[1]).get('selection_id') == selection_id
            except (ValueError, AttributeError):
                mine = False
            if mine and line.startswith('MODEL_SELECTION '):
                inside = True
            elif mine:
                break
            continue
        if inside:
            part.append(line)
    return '\n'.join(part)


def harness_refusal(log, receipt, rc):
    """'harness: <reason>' when the wrapper or the launcher refused this run, else None."""
    found = HARNESS_LINES.findall(selection_text(log, receipt.get('selection_id')))
    if found:
        return 'harness: ' + ' '.join(found[-1].split())[:300]
    if rc in HARNESS_EXITS:
        return 'harness: exit {} (a wrapper or launcher refusal code; the model did not run to completion)'.format(rc)
    return None


def run_checks(spec_text, workdir, host=''):
    """(command, passed) per Check: line. A --host job's outputs stay on the host (only STATUS.md, REPORT.md and
    a few small files come back), so its checks run there, in the same work dir, over ssh. 11-20: three jobs
    run on the m5 from the M4 shipped out.txt there and were graded fail by a reviewer reading the M4's copy."""
    import shlex
    results = []
    for command in CHECK.findall(spec_text or ''):
        try:
            if host:
                argv = shlex.split(os.environ.get('LAUNCH_SSH') or 'ssh') + [
                    '-o', 'BatchMode=yes', host, 'cd {} && {}'.format(shlex.quote(str(workdir)), command)]
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
              'PARTIAL (some of it) or FAIL (not usable), then one sentence why.\n\n--- SPEC ---\n{}\n\n'
              '--- REPORT.md ---\n{}\n').format(workdir, (spec_text or '')[:12000], report)
    executable = {'codex': os.environ.get('LAUNCH_CODEX', 'codex'), 'claude': os.environ.get('LAUNCH_CLAUDE', 'claude'),
                  'agy': os.environ.get('LAUNCH_AGY', 'agy')}[backend]
    with tempfile.TemporaryDirectory(prefix='rh-grade-') as box:
        out = Path(box) / 'grade.out'
        try:
            done = subprocess.run([sys.executable, str(HERE / 'agent_executor.py'), '--backend', backend,
                                   '--executable', executable, '--directory', str(workdir), '--model', model,
                                   '--effort', 'low', '--output', str(out), '--timeout-seconds', '900'],
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


def grade(receipt_path, log, workdir, spec, roles_file=None, no_checks=False, host=''):
    receipt = json.loads(Path(receipt_path).read_text())
    spec_text = Path(spec).read_text(errors='replace') if spec and Path(spec).is_file() else ''
    run_text = '' if no_checks else spec_text
    rc = exit_code(log, receipt.get('selection_id'))
    quota = wm.quota_failure(log, receipt)
    if quota:
        # Infrastructure, not the model: never pass, partial or fail, and nothing for the morning report to grade.
        row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(), source_kind='everyday',
                   job=receipt.get('job'), grade='ungraded', model=receipt.get('route_model') or receipt['model'],
                   producer=receipt.get('route_model') or receipt['model'], grader='quota', role=receipt.get('role'),
                   auto=True, note=quota[:500])
        wm.log_record(log, 'MODEL_GRADE', row)
        wm.log_record(Path(receipt_path).with_name('everyday-grades.jsonl'), '', row)
        return row
    refused = harness_refusal(log, receipt, rc)
    if refused:
        row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(), source_kind='everyday',
                   job=receipt.get('job'), grade='ungraded', model=receipt.get('route_model') or receipt['model'],
                   producer=receipt.get('route_model') or receipt['model'], grader='harness', role=receipt.get('role'),
                   auto=True, note=refused[:500])
        wm.log_record(log, 'MODEL_GRADE', row)
        wm.log_record(Path(receipt_path).with_name('everyday-grades.jsonl'), '', row)
        return row
    shipped = first_line(Path(workdir) / 'REPORT.md').startswith('Shipped:')
    restated = first_line(Path(workdir) / 'STATUS.md').startswith('You asked:')
    floor_note = effort_floor_note(receipt) if rc == 0 else ''
    checks = run_checks(run_text, workdir, host) if rc == 0 and shipped and not floor_note else []
    notes = ['exit {}'.format(rc), 'Shipped line ' + ('yes' if shipped else 'no'),
             'You asked line ' + ('yes' if restated else 'no')]
    notes += ['check {}: {}'.format('ok' if ok else 'FAILED', command[:80]) for command, ok in checks]
    grader = 'checks'
    if floor_note:
        result, grader, notes = 'partial', 'effort floor', [floor_note]
    elif rc != 0 or not shipped:
        result = 'fail'
    elif checks:
        result = 'pass' if all(ok for _, ok in checks) and restated else 'partial'
    else:
        result, grader, reason = review(receipt, spec_text, workdir, roles_file)
        notes.append(reason)
        result = result or 'ungraded'
    row = dict(id='grade-' + receipt['selection_id'], date=dt.date.today().isoformat(), source_kind='everyday',
               job=receipt.get('job'), grade=result, model=receipt.get('route_model') or receipt['model'],
               producer=receipt.get('route_model') or receipt['model'], grader=grader, role=receipt.get('role'),
               auto=True, note='; '.join(notes)[:500])
    wm.log_record(log, 'MODEL_GRADE', row)
    wm.log_record(Path(receipt_path).with_name('everyday-grades.jsonl'), '', row)
    if result == 'ungraded':
        wm.morning_report([(row['job'], receipt.get('lane'), row['model'])])
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
    a = p.parse_args(argv)
    try:
        receipt = json.loads(a.receipt.read_text())
        if receipt.get('source') != 'delegate' and not effort_floor_note(receipt):
            return 0
        if a.host and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}', a.host):
            raise ValueError('--host must be an ssh alias')
        row = grade(a.receipt, a.log, a.dir, a.spec, a.roles_file, a.no_checks, a.host)
        print('auto-graded {} {} (producer {}, grader {})'.format(row['job'], row['grade'], row['producer'],
                                                                  row['grader']))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print('auto_grade: ' + str(exc), file=sys.stderr)
        return 0   # never fails the job; --record-ungraded after it still records the return


if __name__ == '__main__':
    raise SystemExit(main())
