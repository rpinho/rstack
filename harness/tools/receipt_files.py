"""The evidence files the pulled-back prior-art receipts name, for launch.sh to pull back as well.

    receipt_files.py WORKDIR   prints one path per line, relative to WORKDIR

A sweep worker on a host copies the X capture it cites (the intake capture, or X_SEARCHES.jsonl
for a dated none-row) into its run directory and binds capture_path and capture_sha256 to that
copy. The controller then hashes the file at capture_path. The pull list brought back the receipt
but not the copy, so on 11-09 a planets receipt that was correct on the m5 failed here with
"evidence file must exist" (sweep f54183c7). The receipt is the authority on which files it needs,
so this reads them out of it rather than guessing file names. Only paths inside WORKDIR are
listed: a receipt cannot make the pull reach anywhere else on the host. Unreadable receipts are
skipped; the controller's own receipt check reports them.
"""
import json
import os
from pathlib import Path
import sys


def files(workdir):
    root = Path(os.path.abspath(workdir))
    out = []
    for receipt in sorted(root.rglob('prior-art-*.json')):
        try:
            data = json.loads(receipt.read_text())
            path = data['sources']['x']['capture_path']
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if not isinstance(path, str) or not os.path.isabs(path):
            continue
        rel = os.path.relpath(os.path.normpath(path), root)
        # The lane's own ledger never comes home by any route (see launch.sh).
        if rel in ('.', 'RESULTS.jsonl') or rel.startswith('..') or rel in out:
            continue
        out.append(rel)
    return out


if __name__ == '__main__':
    print('\n'.join(files(sys.argv[1])))
