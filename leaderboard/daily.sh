#!/bin/zsh
# Generate one snapshot; publish changed snapshots from an isolated main worktree.
set -euo pipefail
HERE=${0:A:h}
REPO=${HERE:h}
PYTHON=${PYTHON:-python3}
dry_run=false
scratch=''
while (( $# )); do
  case "$1" in
    --dry-run) dry_run=true; shift ;;
    --scratch-dir) scratch=${2:?--scratch-dir needs a path}; shift 2 ;;
    *) print -u2 -- "unknown argument: $1"; exit 2 ;;
  esac
done
: ${RH_LAUNCH_RECEIPTS:?configure RH_LAUNCH_RECEIPTS}
if [[ -z ${RH_EVIDENCE_ROOT:-}${MODEL_OUTCOMES_ROOT:-}${MODEL_UPSTREAM_ROOT:-} ]]; then
  print -u2 -- 'configure RH_EVIDENCE_ROOT, MODEL_OUTCOMES_ROOT or MODEL_UPSTREAM_ROOT'
  exit 2
fi
if $dry_run; then
  if [[ -n $scratch ]]; then
    mkdir -p -- "$scratch"
  else
    scratch=$(mktemp -d "${TMPDIR:-/tmp}/model-scorer.XXXXXXXX")
  fi
  # Capture inputs before redirecting all output paths. Never append to the real ledger.
  source_ledger=${MODEL_LEDGER:-${MODEL_STATE:-.runtime/leaderboard}/evaluations.jsonl}
  if [[ -e $scratch/evaluations.jsonl || -e $scratch/roles.json || -e $scratch/LEADERBOARD.md ]]; then
    print -u2 -- 'scratch directory already contains scoring outputs; choose a new directory'
    exit 2
  fi
  [[ ! -f $source_ledger ]] || cp -- "$source_ledger" "$scratch/evaluations.jsonl"
  export MODEL_STATE=$scratch MODEL_LEDGER=$scratch/evaluations.jsonl RH_ROLES_FILE=$scratch/roles.json
  target=$scratch/LEADERBOARD.md
else
  : ${MODEL_LEDGER:?configure MODEL_LEDGER}
  : ${RH_ROLES_FILE:?configure RH_ROLES_FILE}
  : ${MODEL_STATE:?configure MODEL_STATE}
  mkdir -p -- "$MODEL_STATE"
  target=$MODEL_STATE/LEADERBOARD.md
  # Returned delegated jobs ungraded for 24 h are recorded "ungraded" and listed for the morning report.
  "$PYTHON" "$REPO/harness/worker_models.py" --sweep-ungraded "$RH_LAUNCH_RECEIPTS" || true
  # RULE #1 (11-20): yesterday's harness blocks. A block later rerun, overridden or retracted is a harness
  # bug; general gets the count and the top three blockers (tell-general fyi). Never fails the tick.
  "$PYTHON" "$REPO/harness/harness_blocks.py" report --tell ${=RH_BLOCKS_PEER_ARGS:-} || true
fi
"$PYTHON" "$HERE/model-roles.py" ingest
"$PYTHON" "$HERE/model-roles.py" recompute
"$PYTHON" "$HERE/model-roles.py" public --output "$target"
"$PYTHON" "$REPO/rstack/tools/egress-gate" scan "$target"
if $dry_run; then
  print -- "Dry run: $scratch (no commits or pushes)"
  exit 0
fi
# Fetch and branch before touching the repository page. The controller tree is never committed.
remote=${MODEL_SCORER_REMOTE:-origin}
branch=${MODEL_SCORER_BRANCH:-main}
git -C "$REPO" fetch "$remote" "$branch"
base=$(git -C "$REPO" rev-parse FETCH_HEAD)
landing=$MODEL_STATE/landing
# A detached worktree avoids changing a main branch checked out in another tree.
if [[ -e $landing ]]; then
  if [[ $(git -C "$landing" rev-parse --path-format=absolute --git-common-dir) != $(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir) ]]; then
    print -u2 -- 'landing directory belongs to a different repository'
    exit 2
  fi
  if [[ -n $(git -C "$landing" status --porcelain) ]]; then
    print -u2 -- 'landing worktree has uncommitted changes'
    exit 2
  fi
  git -C "$landing" checkout --detach "$base"
else
  git -C "$REPO" worktree add --detach "$landing" "$base"
fi
# Include rows landed since this controller checkout, including older dates.
"$PYTHON" "$HERE/model-roles.py" public --snapshot "$landing/LEADERBOARD.md" --output "$target"
"$PYTHON" "$REPO/rstack/tools/egress-gate" scan "$target"
if cmp -s -- "$target" "$landing/LEADERBOARD.md"; then
  print -- 'Leaderboard unchanged; no commit or push'
  exit 0
fi
cp -- "$target" "$landing/LEADERBOARD.md"
"$PYTHON" "$REPO/rstack/tools/egress-gate" scan "$landing/LEADERBOARD.md"
git -C "$landing" add -- LEADERBOARD.md
git -C "$landing" commit -m 'Refresh model outcome leaderboard'
git -C "$landing" push "$remote" "HEAD:refs/heads/$branch"
print -- "Published leaderboard; landing worktree at $landing"
