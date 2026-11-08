#!/usr/bin/env python3
"""result-lint: the gate a claim must pass before anyone spends a referee on it.

A claim directory holds CLAIM.md (or RESULT.md). The lint enforces three rules (see docs/normal-first.md):

1. NEW yes/no first. The first non-empty line is `NEW: yes` or `NEW: no`. A `yes` needs a `Printed:` line
   (the number or open question as printed, with a DOI/arXiv/URL to the source) and an `Ours:` line.
2. Normal first ("Please let's do normal things unless they don't work"). A `Standard method:` line, and a
   `Deviations:` line that is `none` or says where the standard method failed (`standard failed: ...`).
3. Baselines before predictive claims. If the claim reports a predictive metric, BASELINES.json must give the
   trivial, simple and method scores on the same split, and its `sbs` must match harness/tools/sbs.py.
4. Scooped and scale. A `yes` needs a `Cited by:` line from the forward-citation check (tools/cited-by): the
   citing-paper count, the paper's year and the closest citing paper or `none`. Old, well-cited papers are where
   someone else got there first. And a `Kind:` line from a fixed scale, so nobody has to guess how big it is:
   rerun (better settings or restarts of the paper's own method), value (a printed number improved or proved
   optimal), question (a question the paper states, settled), conjecture (a stated conjecture proved or refuted),
   note (a new result that builds on the source: a new question, new data or a new method, written up as NOTE.md).
5. A note is a small paper. `Kind: note` replaces `Printed:` with `Builds on:` (the source, with its link) and
   needs a NOTE.md next to the claim, plus a `Prior art:` line saying what the closest published work does.

Exit 0 = PASS, 1 = FAIL (reasons printed), 2 = usage error. `--new-only` also fails a well-formed `NEW: no`,
so a loop can skip refereeing claims that say they found nothing new.
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sbs'))
from sbs import sbs  # noqa: E402

METRIC = re.compile(r'\b(AUROC|AUPRC|ROC[- ]AUC|AUC|accuracy|balanced accuracy|F1|RMSE|MAE|MSE|R\^?2|R²|'
                    r'Spearman|Pearson|correlation|mAP|log[- ]loss|top-\d)\b', re.I)
LOWER = re.compile(r'\b(RMSE|MAE|MSE|log[- ]loss|error|loss)\b', re.I)
KINDS = ('rerun', 'value', 'question', 'conjecture', 'note')
CITED = re.compile(r'\b\d+\b.*\b(19|20)\d{2}\b.*closest\s*:\s*\S', re.I)
SOURCE = re.compile(r'(doi\.org/|\b10\.\d{4,9}/|arxiv\.org/|arXiv:?\s*\d{4}\.\d{4,5}|https?://)', re.I)


def field(text, name):
    m = re.search(rf'^\s*[-*]?\s*\**{name}\**\s*:\s*(.+)$', text, re.I | re.M)
    return m.group(1).strip() if m else None


def lint(d, new_only=False):
    d = Path(d)
    doc = next((d / n for n in ('CLAIM.md', 'RESULT.md') if (d / n).is_file()), None)
    if doc is None:
        return ['no CLAIM.md or RESULT.md']
    text = doc.read_text(errors='replace')
    errs = []
    first = next((l.strip().strip('*#').strip() for l in text.splitlines() if l.strip()), '')
    m = re.fullmatch(r'NEW\s*:\s*(yes|no)\b.*', first, re.I)
    if not m:
        errs.append('first line must be "NEW: yes" or "NEW: no" (did you find something new?)')
        new = None
    else:
        new = m.group(1).lower() == 'yes'
    kind = (field(text, 'Kind') or '').split()
    is_note = bool(kind) and kind[0].lower().strip('.,;:') == 'note'
    if new:
        printed, ours = field(text, 'Printed'), field(text, 'Ours')
        if is_note:
            base = field(text, 'Builds on')
            if not base or not SOURCE.search(base):
                errs.append('Kind: note needs a "Builds on:" line with the source paper and its DOI/arXiv/URL')
            if not (d / 'NOTE.md').is_file():
                errs.append('Kind: note needs NOTE.md (the short paper) next to CLAIM.md')
            if not field(text, 'Prior art'):
                errs.append('Kind: note needs a "Prior art:" line: what the closest published work does')
        elif not printed or not SOURCE.search(printed):
            errs.append('NEW: yes needs a "Printed:" line with the printed number or open question and its DOI/arXiv/URL')
        if not ours:
            errs.append('NEW: yes needs an "Ours:" line')
        cited, kind = field(text, 'Cited by'), field(text, 'Kind')
        if not cited or not CITED.search(cited) or '<title' in cited:
            errs.append('NEW: yes needs "Cited by: N papers since YEAR (source, date); closest: <title or none>" '
                        'from tools/cited-by/cited_by.py')
        if not kind or kind.split()[0].lower().strip('.,;:') not in KINDS:
            errs.append(f'NEW: yes needs "Kind:" one of {", ".join(KINDS)}')
    if new is False and new_only:
        errs.append('NEW: no (nothing new, so nothing to referee)')
    std, dev = field(text, 'Standard method'), field(text, 'Deviations')
    if not std:
        errs.append('needs a "Standard method:" line (normal first)')
    if not dev or not (re.fullmatch(r'none\.?', dev, re.I) or re.search(r'standard failed', dev, re.I)):
        errs.append('needs "Deviations: none" or each deviation with "standard failed: <where>"')
    if METRIC.search(text):
        b = d / 'BASELINES.json'
        if not b.is_file():
            errs.append('predictive metric found: needs BASELINES.json (trivial, simple, method, sbs) from harness/tools/sbs.py')
        else:
            try:
                rows = json.loads(b.read_text())
                rows = baseline_rows(rows)
                if not rows:
                    raise ValueError('no baseline rows')
                for r in rows:
                    v = sbs(r['trivial'], r['simple'], r['method'], r.get('higher_is_better', True))
                    if abs(v - float(r['sbs'])) > 1e-6:
                        errs.append(f'BASELINES.json sbs {r["sbs"]} does not match recomputed {v:.6f}')
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
                errs.append(f'BASELINES.json unreadable or incomplete: {e}')
        if not re.search(r'\bSBS\b', text):
            errs.append('predictive metric found: state the SBS in the claim text')
    return errs



def baseline_rows(data):
    """Flatten BASELINES.json: one sbs.py record, a list of them, or a dict of
    named records (one per metric). A named record may hold sbs.py's JSON in
    its "stdout" field, as written by a job that saved the command and output."""
    if isinstance(data, list):
        return [r for x in data for r in baseline_rows(x)]
    if not isinstance(data, dict):
        return []
    if 'trivial' in data:
        return [data]
    if isinstance(data.get('stdout'), str):
        try:
            return baseline_rows(json.loads(data['stdout']))
        except json.JSONDecodeError:
            return []
    return [r for v in data.values() if isinstance(v, (dict, list)) for r in baseline_rows(v)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dirs', nargs='+')
    p.add_argument('--new-only', action='store_true')
    p.add_argument('-q', '--quiet', action='store_true')
    a = p.parse_args(argv)
    bad = 0
    for d in a.dirs:
        errs = lint(d, a.new_only)
        bad += bool(errs)
        if not a.quiet:
            print(f'{"FAIL" if errs else "PASS"} {d}' + ''.join(f'\n  - {e}' for e in errs))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
