#!/usr/bin/env bash
# test-hooks.sh: exercise every branch of .githooks/pre-commit and the guard-main-tree hook in a
# throwaway repo. Checks BOTH the blocked path and the override path. A hook you have not watched
# fire is just prose in a different file.
#
# usage: scripts/test-hooks.sh        (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/kb-hooktest.XXXXXX")"
pass=0; failn=0
ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
bad()  { failn=$((failn+1)); printf '  FAIL  %s\n' "$1"; }
expect() {  # expect <0|1> <label> <cmd...>
  local want="$1" label="$2"; shift 2
  if "$@" >/dev/null 2>&1; then got=0; else got=1; fi
  [ "$got" = "$want" ] && ok "$label" || bad "$label (wanted exit $want, got $got)"
}

M="$T/main"; mkdir -p "$M"; cd "$M" || exit 1
git init -q -b main
git config user.email test@example.invalid; git config user.name test; git config commit.gpgsign false
mkdir -p .githooks scripts raw/_index raw/sources wiki outbox .claude/hooks
cp "$SRC/.githooks/pre-commit" .githooks/; cp "$SRC/scripts/prep-lint.py" scripts/
for f in guard-main-tree.sh guard-main-tree.py _kbgate.py _hookfail.py; do cp "$SRC/.claude/hooks/$f" .claude/hooks/; done
printf '# State\n\n- [ ] Pay the tax installment plan, due 2026-12-01\n' > state.md
echo "a" > raw/sources/one.txt; echo "# p" > wiki/Page.md
git add -A && git commit -qm init
git config core.hooksPath .githooks
git worktree add -q "$T/wt" -b session

echo "pre-commit:"
cd "$M"; echo x >> wiki/Page.md; git add wiki/Page.md
expect 1 "1 blocks a commit in the main tree" git commit -qm t
expect 0 "1 override KB_ALLOW_MAIN_COMMIT=1" env KB_ALLOW_MAIN_COMMIT=1 git commit -qm t

cd "$T/wt"; mkdir -p raw/_index outbox   # empty dirs are not tracked
echo y >> wiki/Page.md; git add wiki/Page.md
expect 0 "1 allows a commit in a worktree" git commit -qm t

echo b >> raw/sources/one.txt; git add raw/sources/one.txt
expect 1 "2 blocks modifying a raw file" git commit -qm t
expect 0 "2 override KB_ALLOW_RAW_EDIT=1" env KB_ALLOW_RAW_EDIT=1 git commit -qm t

mkdir -p certs; echo k > certs/server.pem; git add certs/server.pem
expect 1 "3 blocks certs/server.pem (extension outside the segment group)" git commit -qm t
git rm -q --cached certs/server.pem; rm -rf certs
echo s > .env; git add -f .env
expect 1 "3 blocks .env" git commit -qm t
git rm -q --cached .env; rm -f .env

echo new > raw/sources/two.txt; git add raw/sources/two.txt
expect 1 "4 blocks a raw/ add without a day-ledger line" git commit -qm t
echo '{"type":"entry"}' >> raw/_index/day-ledger.jsonl; git add raw/_index/day-ledger.jsonl
expect 0 "4 allows it with the ledger staged" git commit -qm t
echo new3 > raw/sources/three.txt; git add raw/sources/three.txt
expect 0 "4 override KB_NO_LEDGER=1" env KB_NO_LEDGER=1 git commit -qm t

printf '<p>Taxes: nothing owed.</p>\n' > "outbox/Reference Sheet.html"; git add "outbox/Reference Sheet.html"
expect 1 "5 blocks a hand-over doc claiming absence of an open item" git commit -qm t
printf '<p>Taxes: nothing owed. <!-- verified: state.md 2026-01-01 --></p>\n' > "outbox/Reference Sheet.html"; git add "outbox/Reference Sheet.html"
expect 0 "5 allows a claim marked verified" git commit -qm t

for i in $(seq 1 45); do echo "$i" > "wiki/bulk-$i.md"; done; git add wiki/bulk-*.md
expect 1 "6 blocks a 45-file commit" git commit -qm t
expect 0 "6 override KB_BULK_OK=1" env KB_BULK_OK=1 git commit -qm t

echo "guard-main-tree:"
hook="$M/.claude/hooks/guard-main-tree.sh"
g() { printf '{"tool_input":{"file_path":"%s"}}' "$1" | CLAUDE_PROJECT_DIR="$2" bash "$hook"; }
expect 1 "blocks editing a tracked main-tree file"      g "$M/wiki/Page.md" "$M"
expect 1 "blocks creating a file in a tracked main area" g "$M/wiki/New Page.md" "$M"
expect 0 "allows editing the same file in a worktree"   g "$T/wt/wiki/Page.md" "$T/wt"
expect 0 "allows untracked scratch (outbox/) in main"   g "$M/outbox/note.md" "$M"
git -C "$M" worktree add -q "$M/.claude/worktrees/inner" -b inner
expect 0 "allows a worktree nested inside the main path" g "$M/.claude/worktrees/inner/wiki/Page.md" "$M/.claude/worktrees/inner"

cd /; printf '\n%s passed, %s failed (scratch: %s)\n' "$pass" "$failn" "$T"
[ "$failn" -eq 0 ]
