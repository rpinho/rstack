#!/bin/zsh
# Synchronous job runner: role selection, exit receipts and bounded capacity retries.
# usage: launch.sh JOB WORKDIR [--role ROLE] [--model MODEL --model-override REASON] [--host HOST]
setopt pipefail
(( $# >= 2 )) || { print -u2 -- 'usage: launch.sh JOB WORKDIR'; exit 2; }
self=${0:A}
job=$1; dir=$2; shift 2
LAUNCH_ROLE=${LAUNCH_ROLE:-batch}; LAUNCH_MODEL=${LAUNCH_MODEL:-}; LAUNCH_MODEL_OVERRIDE=${LAUNCH_MODEL_OVERRIDE:-}
LAUNCH_EFFORT=${LAUNCH_EFFORT:-high}
# --host runs the executor on another machine (Ricardo, 11-07: "move the science runs to the m5").
# Only that one step crosses the network. Admission, the spec word cap, the job registry, model
# selection, the prompt and the log all stay on the controller, so there is still one source for
# them and the host needs no lane state. The 16 GB controller ran out of memory under local
# rounds on 11-01 and Claude Code killed the background shells; the heavy work belongs elsewhere.
LAUNCH_HOST=${LAUNCH_HOST:-}
# A paid round is admitted by the round ledger, not by the lane's own judgement (Ricardo, 11-07,
# after c5 repeated the 11-06 failure: 66 rounds with the same generator, params and scorer).
# Set LAUNCH_ROUND to put the job through harness/tools/rounds.py; the rest describe the round.
LAUNCH_ROUND=${LAUNCH_ROUND:-}; LAUNCH_FAMILY=${LAUNCH_FAMILY:-}
LAUNCH_GENERATOR=${LAUNCH_GENERATOR:-}; LAUNCH_PARAMS=${LAUNCH_PARAMS:-}
LAUNCH_SCORER=${LAUNCH_SCORER:-}; LAUNCH_HYPOTHESIS=${LAUNCH_HYPOTHESIS:-}
LAUNCH_NEW_EVIDENCE=${LAUNCH_NEW_EVIDENCE:-}
backend=${AGENT_BACKEND:-codex}
[[ $backend == (codex|claude) ]] || { print -u2 -- 'AGENT_BACKEND must be codex or claude'; exit 2; }
[[ $LAUNCH_EFFORT == (low|medium|high|xhigh) ]] || { print -u2 -- 'bad LAUNCH_EFFORT'; exit 2; }
while (( $# )); do
  case $1 in
    --role) (( $# >= 2 )) || exit 2; LAUNCH_ROLE=$2; shift 2;;
    --model) (( $# >= 2 )) || exit 2; LAUNCH_MODEL=$2; shift 2;;
    --model-override) (( $# >= 2 )) || exit 2; LAUNCH_MODEL_OVERRIDE=$2; shift 2;;
    --host) (( $# >= 2 )) || exit 2; LAUNCH_HOST=$2; shift 2;;
    *) print -u2 -- "launch.sh: unknown argument $1"; exit 2;;
  esac
done
# An ssh alias, never a flag or a command: the host goes into an ssh argv and a remote shell line.
if [[ -n $LAUNCH_HOST ]] && ! [[ $LAUNCH_HOST =~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$' ]]; then
  print -u2 -- "launch.sh: --host must be an ssh alias, got '$LAUNCH_HOST'"; exit 2
fi
# Admission happens before registration, logs, model selection or the executor.
if [[ -n $LAUNCH_IDEA ]]; then
  idea_args=(ideas show "$LAUNCH_IDEA")
  [[ -z $LAUNCH_IDEA_ROOT ]] || idea_args=(--root "$LAUNCH_IDEA_ROOT" "${idea_args[@]}")
  idea_json=$(rh "${idea_args[@]}")
  idea_rc=$?
  if (( idea_rc != 0 )) || ! print -r -- "$idea_json" | python3 -I -c '
import json, sys
try:
    idea = json.load(sys.stdin)
    ok = (isinstance(idea, dict) and idea.get("status") == "testing"
          and isinstance(idea.get("id"), str) and idea["id"].startswith(sys.argv[1]))
except (ValueError, TypeError):
    ok = False
sys.exit(0 if ok else 1)
' "$LAUNCH_IDEA"; then
    print -u2 -- "launch.sh REFUSED $job: idea $LAUNCH_IDEA is not promoted (status testing). Run rh ideas promote first."
    exit 78
  fi
fi
[[ $dir = /* ]] || dir=${LAUNCH_WORK_ROOT:-$PWD}/$dir
cd "$dir" || exit 1
# The load is read on the machine that will do the work. 11-08, math and planets within the hour:
# this read the CONTROLLER's loadavg even for a --host job, refused two math rounds at "load 77"
# while the host sat at 1.5, and both lanes got past it with FORCE_LAUNCH=1, which also turns off
# the disk floor and the memory floor. A --host job's local cost is one ssh. Unreadable is a
# refusal, like every other host precondition: falling back to this machine's number is the bug.
# 1-minute load, from sysctl on a Mac and /proc/loadavg elsewhere; the field differs, so it is
# asked for by name rather than parsed out of one format.
remote_loadavg='if l=$(sysctl -n vm.loadavg 2>/dev/null); then echo $l | awk "{print \$2}"; else awk "{print \$1}" /proc/loadavg; fi'
if [[ -n $LAUNCH_HOST ]]; then
  load=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes -o ConnectTimeout=20 "$LAUNCH_HOST" \
         "$remote_loadavg" 2>/dev/null | awk 'NF{print int($1); exit}')
  load_where=$LAUNCH_HOST
  if [[ $load != <-> ]]; then
    print -u2 -- "launch.sh refused: cannot read the load on $LAUNCH_HOST. The executor runs there, so that is the load that decides, and a precondition this machine cannot measure is a refusal rather than a fallback to its own number."
    exit 75
  fi
else
  load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print int($2)}')
  load_where='this machine'
fi
if [[ $load == <-> ]] && (( load > ${LAUNCH_MAX_LOAD:-30} )) && [[ -z $FORCE_LAUNCH ]]; then
  print -u2 -- "launch.sh refused: load $load on $load_where"; exit 75
fi
artifacts=${LAUNCH_ARTIFACT_DIR:-$PWD/.runtime/jobs}
# Sweep passes a relative spec path; standalone jobs use the configured artifacts dir.
if [[ $job == */* ]]; then
  spec=${self:h}/$job.md; spec=${spec:A}
else
  spec=$artifacts/$job.md
fi
[[ -f $spec ]] || { print -u2 -- "missing spec: $spec"; exit 2; }
log=${spec:r}.log
# HARD RULE (Ricardo, 11-04): the goal must not turn into process. A spec over the cap needs
# SPEC_OVER_CAP="<reason>". The count is the job-specific part only (spec_words.py): the sweep
# embeds the lane's whole RULES.md and INTAKE.toml in its generated specs, which on 11-06 put
# c5's 472-word ask at 3,047 words and refused every job the sweep generated. Shared blocks
# added to the prompt below this line are never counted.
words=$(python3 "${self:h:h}/harness/tools/spec_words.py" "$spec") || exit 2
cap=${LAUNCH_SPEC_WORD_CAP:-1000}
if [[ -z $LAUNCH_RESUME ]] && (( words > cap )); then
  if [[ -z $SPEC_OVER_CAP ]]; then
    print -u2 -- "launch.sh REFUSED $job: spec is $words job-specific words, over the $cap cap (the goal is turning into process; set SPEC_OVER_CAP=reason)"
    print -- "exit 2 spec-over-cap $words words $(date)" >> "$log"
    exit 2
  fi
  print -- "spec over cap allowed ($words words): $SPEC_OVER_CAP $(date)" >> "$log"
fi
# The lane a job belongs to is its name up to the first separator (friends_new_x -> friends),
# overridable with LAUNCH_LANE. Derived here rather than further down because the round gate needs
# it, and the gate has to refuse before the registry write, the log and any spend.
lane=${LAUNCH_LANE:-${${job:t}%%[-_]*}}
lane_dir=${LAUNCH_LANE_ROOT:-${LAUNCH_IDEA_ROOT:-$PWD/.runtime}}/lanes/$lane
# rounds.py has held this rule since the first c5 postmortem on 11-06: no repeat of a method that
# just produced a dry streak, no reopening a closed dead end, no round 1 without reading the KB.
# Nothing ever called it and no lane had written a single row, so every check read an empty ledger
# and passed. Calling `start` here is what makes the write unavoidable: it gates and opens the
# round in one command, and it refuses a fingerprint seen in the recent rounds, so relabelling the
# same knobs as a new family does not get through.
if [[ -n $LAUNCH_ROUND ]]; then
  round_args=(--lane "$lane_dir" start --round "$LAUNCH_ROUND" --family "${LAUNCH_FAMILY:-$lane}"
              --generator "$LAUNCH_GENERATOR" --params "$LAUNCH_PARAMS" --scorer "$LAUNCH_SCORER")
  [[ -z $LAUNCH_HYPOTHESIS ]] || round_args+=(--hypothesis "$LAUNCH_HYPOTHESIS")
  [[ -z $LAUNCH_NEW_EVIDENCE ]] || round_args+=(--new-evidence "$LAUNCH_NEW_EVIDENCE")
  if ! python3 "${self:h:h}/harness/tools/rounds.py" "${round_args[@]}" >> "$log.round" 2>&1; then
    print -u2 -- "launch.sh REFUSED $job: the round gate refused this round"
    tail -20 "$log.round" >&2
    print -- "exit 78 round-gate-refused $(date)" >> "$log"
    exit 78
  fi
fi
reg=${LAUNCH_STATE:-$PWD/.runtime/job-registry}
mkdir -p "$reg"
registry_name=${job//[^A-Za-z0-9_.-]/_}
# host= is what lets a stop reach the machine the executor is actually on. Without it,
# 11-07: a --host job was stopped here, the local tmux session died and the log said
# "exit stopped", while codex kept running on the host as an orphan nobody was watching.
remote_marks=${LAUNCH_REMOTE_JOBS:-.local/state/research-harness/remote-jobs}
print -l "dir=$dir" "pid=$$" ${LAUNCH_HOST:+"host=$LAUNCH_HOST"} ${LAUNCH_HOST:+"remote_marks=$remote_marks"} > "$reg/$registry_name.job"
finished() {
  [[ ! -f $reg/$registry_name.job ]] || mv "$reg/$registry_name.job" "$reg/$registry_name.finished"
}
trap finished EXIT
stopped() { print -- "exit stopped by signal $(date)" >> "$log"; exit 143; }
trap stopped TERM HUP
if [[ $backend == codex ]]; then
  cx=${LAUNCH_CODEX:-codex}
else
  cx=${LAUNCH_CLAUDE:-claude}
fi
selector=${LAUNCH_SELECTOR:-${self:h:h}/harness/worker_models.py}
# lane and lane_dir are derived above, with the round gate that needs them. A missing GOAL.md or
# an unavailable `rh` is not fatal: a job that cannot read its goal still runs, and the gap shows
# up in the prompt's absence rather than as a dead lane.
lessons=$(rh --root "${LAUNCH_LANE_ROOT:-${LAUNCH_IDEA_ROOT:-$PWD/.runtime}}" lessons for "$lane" -n "${LAUNCH_LESSONS:-12}" 2>/dev/null)
start=1; [[ -n $LAUNCH_RESUME ]] && start=2
for (( i = start; i <= 5; i++ )); do
  m=$(python3 "$selector" --role "$LAUNCH_ROLE" --executor "$backend" --model "$LAUNCH_MODEL" --model-override "$LAUNCH_MODEL_OVERRIDE" --log "$log" --receipt "$log.selection.json") || { print -- "exit 2 model-selection-refused $(date)" >> "$log"; exit 2; }
  # Shared context every job gets, injected here and never counted against the word cap above:
  # the job rules (prior art first), the lane's goal in the owner's words, and the lessons the
  # lane has already paid for. Before 11-06 only `rh ideas promote` enforced prior art and only
  # sweep prompts carried lessons, so 31 of the last 60 specs never mentioned either.
  { [[ ! -f ${self:h}/RULES.md ]] || { cat "${self:h}/RULES.md"; printf '\n---\n\n'; }
    [[ ! -f $lane_dir/GOAL.md ]] || { printf -- '--- LANE GOAL (%s, the owner'\''s words; agents never edit it) ---\n' "$lane"; cat "$lane_dir/GOAL.md"; printf '\n---\n\n'; }
    [[ -z $lessons ]] || { printf -- '--- LESSONS THIS LANE ALREADY PAID FOR ---\n%s\n---\n\n' "$lessons"; }
    cat "$spec"; (( i > 1 )) && printf '\n\nRESUME (attempt %d): read STATUS.md, REPORT.md and existing files; continue completed work.\n' $i; } > "$log.prompt"
  print -- "=== attempt $i model $m${LAUNCH_HOST:+ host $LAUNCH_HOST} $(date)" >> "$log"
  attempt_log="$log.attempt-$i"
  out=${spec:r}.last.md
  if [[ -z $LAUNCH_HOST ]]; then
    nice -n 10 python3 "${self:h:h}/harness/agent_executor.py" --backend "$backend" \
      --executable "$cx" --directory "$dir" --model "$m" --effort "$LAUNCH_EFFORT" \
      --output "$out" --budget "${LAUNCH_CLAUDE_BUDGET:-1.00}" \
      < "$log.prompt" > "$attempt_log" 2>&1
    rc=$?
  else
    # A remote run uses the SAME absolute paths on both machines, and refuses when the work dir
    # is not there, rather than falling back to the remote $HOME and writing results nowhere.
    # No path is silently rewritten: both machines are /Users/ricardo, and a host whose layout
    # differs is a separate change, not a guess made here.
    # $HOME in the default is expanded by the remote shell, so no host path enters the repo.
    # A --host job runs the executor on the other machine, so it runs THAT machine's harness.
    # 11-07: the m5's installed copy was at 906efdc while this one was at ff47140, and the commit
    # between them touching agent_executor.py was the codex sandbox fix. What is compared is what
    # executes: each machine's installed harness receipt, not a git checkout (the m5's checkout was
    # older still than what it was running). Unreadable is a refusal, like every other host check.
    hr=${LAUNCH_HARNESS_ROOT:-$HOME/.local/share/research-harness}/.harness-sync.json
    if [[ -f $hr ]]; then
      mine=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("commit",""))' "$hr" 2>/dev/null)
      theirs=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes "$LAUNCH_HOST" "cat ${(q)hr}" 2>/dev/null \
               | python3 -c 'import json,sys; print(json.load(sys.stdin).get("commit",""))' 2>/dev/null)
      if [[ -n $mine && $mine != $theirs ]]; then
        print -u2 -- "launch.sh --host $LAUNCH_HOST: it runs harness ${theirs:-unreadable} and this machine runs ${mine[1,12]}. The executor runs THERE, so this job would run code this machine has already changed. Fix with: harness-sync --host $LAUNCH_HOST"
        print -- "exit 2 harness-drift $LAUNCH_HOST ${theirs:-unreadable} vs ${mine[1,12]} $(date)" >> "$log"
        exit 2
      fi
    fi
    rexec=${LAUNCH_REMOTE_EXECUTOR:-'$HOME/.local/share/research-harness/agent_executor.py'}
    if ! [[ $rexec =~ '^[$A-Za-z0-9_/.~{}-]+$' ]]; then
      print -u2 -- "launch.sh: LAUNCH_REMOTE_EXECUTOR must be a plain path"; exit 2
    fi
    # POSIX `echo`, not zsh's `print`: the remote shell is whatever the host's login shell is.
    missing="launch.sh --host $LAUNCH_HOST: no work dir $dir there"
    # The executor writes --output, and for a sweep worker that path is inside the attempt
    # directory the controller just created HERE: work/runs/<timestamp>-<hex>/. It does not exist
    # on the host, so the executor's first write would fail with nothing run. The work dir itself
    # is still a refusal, never created: that guard is what keeps a job out of the remote $HOME.
    nodir="launch.sh --host $LAUNCH_HOST: cannot create ${out:h} there"
    # The remote shell records its own pid immediately before exec, so the file holds the
    # EXECUTOR's pid and not a wrapper's. remote-stop reads it to end a --host job for real.
    # A marks path is taken as absolute when it starts with /, otherwise it is under the remote
    # $HOME, which the remote shell expands: no host path is baked into the repo.
    # $HOME has to reach the REMOTE shell unquoted so it expands THERE. Quoting the whole string,
    # as this did when it shipped on 11-07, escapes the dollar: the remote shell then creates a
    # directory literally named '$HOME' under the work dir and writes the marker inside it, so
    # remote-stop finds no pid file and the executor survives a job-stop. friends found it within
    # the hour. Only the relative part is quoted; an absolute path is quoted whole.
    if [[ $remote_marks == /* ]]; then rmarks=${(q)remote_marks}
    else rmarks='$HOME/'${(q)remote_marks}
    fi
    remote="cd ${(q)dir} 2>/dev/null || { echo ${(q)missing} >&2; exit 2; }
mkdir -p ${(q)${out:h}} 2>/dev/null || { echo ${(q)nodir} >&2; exit 2; }
mkdir -p $rmarks 2>/dev/null || true
echo \$\$ > $rmarks/${(q)${job:t}}.pid 2>/dev/null || true
exec nice -n 10 python3 $rexec --backend ${(q)backend} --executable ${(q)cx} --directory ${(q)dir} --model ${(q)m} --effort ${(q)LAUNCH_EFFORT} --output ${(q)out} --budget ${(q)${LAUNCH_CLAUDE_BUDGET:-1.00}}"
    ${=${LAUNCH_SSH:-ssh}} "$LAUNCH_HOST" "$remote" < "$log.prompt" > "$attempt_log" 2>&1
    rc=$?
    # Status has to keep working from the controller: the heavy outputs stay on the host and
    # only these few small bookkeeping files come back, so STATUS.md, REPORT.md, the receipts
    # and event-watch read exactly as they did when the job ran here.
    #
    # *.report.md and prior-art-*.json are a sweep worker's whole deliverable: the controller
    # reads <stage>.report.md to admit ideas and to record reads and kills, and it reads
    # prior-art-<ID>.json to admit each idea at all, then stores that path in the ledger. Without
    # both in this list, moving a lane to a host would have run all three stages, cost real money,
    # and then failed every one of them for a missing report or an unverifiable receipt, so the
    # lane would have looked broken rather than misconfigured.
    # When the work dir IS the lane, RESULTS.jsonl there is the lane's append-only ledger and this
    # machine is its only authority (math, 11-07: "never two live ledgers"). Pulling it would
    # overwrite rows written here with the host's copy, so it is excluded and a divergence is
    # reported instead of merged. For a job whose work dir is its own directory, RESULTS.jsonl is
    # that job's output and still comes home.
    ledger=()
    [[ ${dir:A:h:t} != lanes ]] || ledger=(--exclude='/RESULTS.jsonl')  # the work dir IS a lane
    rsync -a --timeout=120 --max-size="${LAUNCH_PULL_MAX_SIZE:-4m}" -e "${LAUNCH_SSH:-ssh}" \
      "${ledger[@]}" \
      --include='*/' --include='STATUS.md' --include='REPORT.md' --include='PLAN.md' \
      --include='RESULTS.jsonl' --include='*.selection.json' --include='*.report.md' \
      --include='prior-art-*.json' \
      --include="${out:t}" \
      --exclude='*' "$LAUNCH_HOST:$dir/" "$dir/" >> "$log.pull" 2>&1 ||
      print -- "pull from $LAUNCH_HOST failed rc $? (outputs are on the host) $(date)" >> "$log"
    # Say so when the host wrote the ledger anyway. Silence here would mean rows exist on a
    # machine nobody reads, which is how a result gets lost rather than merged wrongly.
    if (( $#ledger )); then
      ours=$(shasum -a 256 "$dir/RESULTS.jsonl" 2>/dev/null | cut -d' ' -f1)
      theirs=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes "$LAUNCH_HOST" \
        "shasum -a 256 ${(q)dir}/RESULTS.jsonl 2>/dev/null | cut -d' ' -f1" 2>/dev/null)
      if [[ -n $theirs && $theirs != $ours ]]; then
        msg="ledger diverged: RESULTS.jsonl on $LAUNCH_HOST differs from this machine's for lane $lane. This machine stays authoritative; the host copy was NOT merged and is still there."
        print -- "LEDGER DIVERGED $LAUNCH_HOST $(date)" >> "$log"
        print -- "$msg" >> "$log"
        [[ -z ${LAUNCH_NOTIFY_COMMAND:-} ]] || "${LAUNCH_NOTIFY_COMMAND}" "$msg" >/dev/null 2>&1 || true
      fi
    fi
  fi
  cat "$attempt_log" >> "$log"
  print -- "exit $rc $(date)" >> "$log"
  python3 "$selector" --log "$log" --receipt "$log.selection.json" --outcome "$rc" || exit 2
  (( rc != 0 && i < 5 )) || break
  [[ $backend == codex ]] || break  # A Claude retry must not reset its spend cap.
  tail -40 "$attempt_log" | grep -q 'at capacity' || break
  sleep $(( ${LAUNCH_RETRY_SECONDS:-300} * i ))
done

# HARD RULE check (AGENTS.md): did the job restate the ask, and does it say what shipped? AGENTS.md
# has claimed since 11-04 that the launcher lints every job for these two lines into a job-yield
# ledger, and that was true only of the host's own copy of this script, not of this one. A rule a
# repository documents and does not run is the same failure as a rule nothing calls.
# This runs after the loop, so a --host job has already had its STATUS.md and REPORT.md pulled back
# and reads exactly like a local one.
first_line() { grep -v -E '^[[:space:]]*(#.*)?$' "$1" 2>/dev/null | head -1; }
asked=$(first_line "$dir/STATUS.md"); shipped=$(first_line "$dir/REPORT.md")
ok_ask=0; [[ $asked == You\ asked:* ]] && ok_ask=1
ok_ship=0; [[ $shipped == Shipped:* ]] && ok_ship=1
print -- "lint restate-ask=$ok_ask shipped-line=$ok_ship $(date)" >> "$log"
yield=${LAUNCH_YIELD_LEDGER:-$PWD/.runtime/job-yield.jsonl}
mkdir -p "${yield:h}" 2>/dev/null
python3 -I -c 'import json, sys, time
print(json.dumps(dict(utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), job=sys.argv[1],
                      rc=sys.argv[2], restated=sys.argv[3] == "1", shipped=sys.argv[4][:300])))' \
  "$job" "$rc" "$ok_ask" "$shipped" >> "$yield" 2>/dev/null
# The notification is optional and never fatal: a missing notifier must not turn a finished job
# into a failed one.
if (( ! ok_ask || ! ok_ship )) && [[ -n ${LAUNCH_NOTIFY_COMMAND:-} ]]; then
  ${=LAUNCH_NOTIFY_COMMAND} "job $job ended without the hard-rule lines (You asked: $ok_ask, Shipped: $ok_ship)" >/dev/null 2>&1 || true
fi
exit "$rc"
