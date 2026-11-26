#!/bin/zsh
# Synchronous job runner: role selection, exit receipts and bounded capacity retries.
# usage: launch.sh JOB WORKDIR [--role ROLE] [--made-by MODEL] [--explore MODEL] [--model MODEL --model-override REASON] [--host HOST]
setopt pipefail
# 11-09 (planets on the m5): a non-login shell there has only the system PATH, the detached job inherits
# it, and the executor (codex in /opt/homebrew/bin) was "command not found" (exit 127).
# 11-12: moved to the FRONT, not just added when missing. ~/.local/bin holds the osascript shim that
# turns a Finder delete into a silent /usr/bin/trash; a math Codex job deleted through Finder (the
# owner heard it) because a PATH that already had ~/.local/bin behind /usr/bin was left alone.
for d in /opt/homebrew/bin $HOME/.local/bin; do [[ -d $d ]] && path=($d ${path:#$d}); done; export PATH
(( $# >= 2 )) || { print -u2 -- 'usage: launch.sh JOB WORKDIR'; exit 2; }
self=${0:A}
# The harness this file runs: ../harness in a checkout, .. in the installed root, where harness-sync puts
# this file at <root>/launcher/ (11-20: the lanes' launcher execs the installed copy, so every lane job
# runs committed code; the installed root had no launcher before).
if [[ -d ${self:h:h}/harness ]]; then H=${self:h:h}/harness; else H=${self:h:h}; fi
job=$1; dir=$2; shift 2
# RULE #1 (Ricardo, 11-20: "Make sure the harness is not getting in our way"). Every admission check in
# this file asks `refuses GATE REASON FIX` instead of exiting on its own. Only a gate that rstack/gates.json
# classes a hard line (or one it leaves to general, `pending`) refuses, naming the fix; every other check
# logs a warning to harness-blocks.jsonl and the job runs. A helper that cannot run is a warning too.
hblocks=${LAUNCH_HARNESS_BLOCKS:-$H/harness_blocks.py}
refuses() {
  python3 "$hblocks" gate --gate "$1" --reason "$2" --fix "${3:-}" --job "$job" --lane "${lane:-}"
  local rc=$?
  (( rc == 3 )) && return 0
  (( rc == 0 )) || print -u2 -- "[$1] harness_blocks unavailable (exit $rc): carrying on (RULE #1)"
  return 1
}
if [[ -x $HOME/.local/bin/osascript && $(whence -p osascript) != $HOME/.local/bin/osascript ]]; then
  if refuses launch.osascript-shim "osascript resolves to $(whence -p osascript), not the shim in ~/.local/bin, so a Finder delete in this job would play the trash sound" "put ~/.local/bin first on PATH"; then
    exit 78
  fi
fi
# Optional and never fatal: a missing notifier must not turn a job into a failed one.
notify() { [[ -z ${LAUNCH_NOTIFY_COMMAND:-} ]] || ${=LAUNCH_NOTIFY_COMMAND} "$1" >/dev/null 2>&1 || true; }
LAUNCH_ROLE=${LAUNCH_ROLE:-batch}; LAUNCH_MODEL=${LAUNCH_MODEL:-}; LAUNCH_MODEL_OVERRIDE=${LAUNCH_MODEL_OVERRIDE:-$MODEL_OVERRIDE_REASON}
LAUNCH_MADE_BY=${LAUNCH_MADE_BY:-}
LAUNCH_EXPLORE=${LAUNCH_EXPLORE:-}
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
# LAUNCH_BACKEND is the launcher's own name for AGENT_BACKEND (the name hosts that run this launcher
# directly already use). Either selects the backend; set to different values they refuse, since a
# job that might run on either CLI has no single spend cap or route to check.
if [[ -n $AGENT_BACKEND && -n $LAUNCH_BACKEND && $AGENT_BACKEND != $LAUNCH_BACKEND ]]; then
  print -u2 -- "launch.sh: AGENT_BACKEND=$AGENT_BACKEND and LAUNCH_BACKEND=$LAUNCH_BACKEND disagree"; exit 2
fi
backend=${AGENT_BACKEND:-${LAUNCH_BACKEND:-codex}}
[[ $backend == (codex|claude|agy) ]] || { print -u2 -- 'AGENT_BACKEND must be codex, claude or agy'; exit 2; }
# A Claude job is bounded by spend (LAUNCH_CLAUDE_BUDGET) and by the clock: that CLI has no
# --max-turns. LAUNCH_TIMEOUT_SECONDS is the clock (default 90 minutes; 0 means none) and
# LAUNCH_CLAUDE_TOOLS widens the executor's read/write/edit default for a job that runs its own code.
LAUNCH_TIMEOUT_SECONDS=${LAUNCH_TIMEOUT_SECONDS:-5400}
[[ $LAUNCH_TIMEOUT_SECONDS == <-> ]] || { print -u2 -- 'LAUNCH_TIMEOUT_SECONDS must be whole seconds'; exit 2; }
LAUNCH_CLAUDE_TOOLS=${LAUNCH_CLAUDE_TOOLS:-Read,Write,Edit}
[[ $LAUNCH_CLAUDE_TOOLS =~ '^[A-Za-z0-9_(),:*. -]+$' ]] || { print -u2 -- 'LAUNCH_CLAUDE_TOOLS must be a tool list'; exit 2; }
[[ $LAUNCH_EFFORT == (low|medium|high|xhigh) ]] || { print -u2 -- 'bad LAUNCH_EFFORT'; exit 2; }
while (( $# )); do
  case $1 in
    --role) (( $# >= 2 )) || exit 2; LAUNCH_ROLE=$2; shift 2;;
    --made-by) (( $# >= 2 )) || exit 2; LAUNCH_MADE_BY=$2; shift 2;;
    --model) (( $# >= 2 )) || exit 2; LAUNCH_MODEL=$2; shift 2;;
    --explore) (( $# >= 2 )) || exit 2; LAUNCH_EXPLORE=$2; shift 2;;
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
    if refuses launch.idea-promoted "idea $LAUNCH_IDEA is not promoted (status testing)" "rh ideas promote $LAUNCH_IDEA"; then
      exit 78
    fi
  fi
fi
[[ $dir = /* ]] || dir=${LAUNCH_WORK_ROOT:-$PWD}/$dir
cd "$dir" || exit 1
# Resolve aliases and hyphenated lane names before host checks or any job writes.
lane=$(python3 "$H/lane_registry.py" \
  --lanes-root "${LAUNCH_LANE_ROOT:-${LAUNCH_IDEA_ROOT:-${RH_ROOT:-$PWD/.runtime}}}/lanes" \
  --job "$job" --lane "${LAUNCH_LANE:-}") || exit 78
lane_dir=${LAUNCH_LANE_ROOT:-${LAUNCH_IDEA_ROOT:-${RH_ROOT:-$PWD/.runtime}}}/lanes/$lane
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
  if [[ $load != <-> ]] && refuses launch.load "cannot read the load on $LAUNCH_HOST, where the executor runs" "ssh $LAUNCH_HOST uptime"; then
    exit 75
  fi
else
  load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print int($2)}')
  load_where='this machine'
fi
if [[ $load == <-> ]] && (( load > ${LAUNCH_MAX_LOAD:-30} )) && [[ -z $FORCE_LAUNCH ]] &&
   refuses launch.load "load $load on $load_where (over ${LAUNCH_MAX_LOAD:-30})" "wait for the load to fall, or LAUNCH_MAX_LOAD=N"; then
  exit 75
fi
# 11-23 (general): the m5 fell to 142 MB free overnight and jobs, the grades mirror and job ledgers failed with
# ENOSPC. A new job starts only when the volume that holds its work dir on the run host has LAUNCH_DISK_FLOOR_GB
# (default 30) free. Nothing running is stopped (games, saves). Unreadable is a warning and the job runs.
disk_cmd="d=${(q)dir}; while [ ! -e \"\$d\" ]; do d=\$(dirname \"\$d\"); done; df -Pk \"\$d\" | awk 'NR==2{print \$4}'"
if [[ -n $LAUNCH_HOST ]]; then
  disk_free=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes -o ConnectTimeout=20 "$LAUNCH_HOST" "$disk_cmd" 2>/dev/null)
else
  disk_free=$(sh -c "$disk_cmd" 2>/dev/null)
fi
if [[ $disk_free == <-> ]]; then
  if (( disk_free < ${LAUNCH_DISK_FLOOR_GB:-30} * 1048576 )) && [[ -z $FORCE_LAUNCH ]] &&
     refuses launch.disk-floor "$(( disk_free / 1048576 )) GB free under $dir on ${LAUNCH_HOST:-this machine}, below the ${LAUNCH_DISK_FLOOR_GB:-30} GB floor" \
       "free space there first (venvs, clean clones and caches of finished jobs; unused colima images), or LAUNCH_DISK_FLOOR_GB=N"; then
    exit 75
  fi
else
  print -u2 -- "[launch.disk-floor] cannot read free disk under $dir on ${LAUNCH_HOST:-this machine}; running anyway (RULE #1)"
fi
artifacts=${LAUNCH_ARTIFACT_DIR:-$PWD/.runtime/jobs}
# Sweep passes a relative spec path; standalone jobs use the configured artifacts dir. An absolute
# job is the spec's own path without .md (the lanes' wrapper resolves a sweep's relative path to it).
if [[ $job == /* ]]; then
  spec=${job:A}.md
elif [[ $job == */* ]]; then
  spec=${self:h}/$job.md; spec=${spec:A}
else
  spec=$artifacts/$job.md
fi
[[ -f $spec ]] || { print -u2 -- "missing spec: $spec"; exit 2; }
# 11-10: the m5 froze overnight. Two math jobs used up its memory and swap, the kernel suspended
# every app until morning, and the m5 had no memory guard. So a --host job starts only where the
# guard is live (mem_guard.py --every writes a heartbeat each pass; over 60 s old is a refusal) and
# only with its measured peak declared in the spec, as a line "Peak RSS: N GB" (measure the heaviest
# step with /usr/bin/time -l). A peak over LAUNCH_MAX_PEAK_GB (8) belongs on a RunPod pod.
# FORCE_LAUNCH does not skip this: the guard is what lets anything run there unattended.
if [[ -n $LAUNCH_HOST ]]; then
  hbf=${LAUNCH_MEMGUARD_HEARTBEAT:-'$HOME/.local/state/mem-guard/heartbeat'}
  beat_age() {
    ${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes -o ConnectTimeout=20 "$LAUNCH_HOST" \
      "f=$hbf; [ -f \"\$f\" ] && echo \$(( \$(date +%s) - \$(stat -f %m \"\$f\" 2>/dev/null || stat -c %Y \"\$f\") ))" 2>/dev/null | awk 'NF{print int($1); exit}'
  }
  hb=$(beat_age)
  # 11-20 (general, RULE #1): a guard that is down is restarted, not a reason to refuse the job. The guard's
  # launch agent is kickstarted over ssh (-k also restarts one that hangs with a stale heartbeat), the
  # heartbeat is read again, and the job runs either way, warned if the guard still is not beating.
  if [[ $hb != <-> ]] || (( hb > 60 )); then
    was="heartbeat ${hb:+$hb s old}${hb:-missing}"
    kick=${LAUNCH_MEMGUARD_KICK:-"launchctl kickstart -k gui/\$(id -u)/${LAUNCH_MEMGUARD_LABEL:-com.ricardo.mem-guard}"}
    ${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes -o ConnectTimeout=20 "$LAUNCH_HOST" "$kick" >/dev/null 2>&1
    sleep ${LAUNCH_MEMGUARD_RECHECK_S:-10}
    hb=$(beat_age)
    if [[ $hb == <-> ]] && (( hb <= 60 )); then
      print -u2 -- "launch.sh: the memory guard on $LAUNCH_HOST was down ($was); kickstarted, it is beating again"
    elif refuses launch.host-memguard "the memory guard on $LAUNCH_HOST is not running ($was; still ${hb:+$hb s old}${hb:-missing} after a kickstart); running anyway" "ssh $LAUNCH_HOST launchctl kickstart -k gui/\$(id -u)/${LAUNCH_MEMGUARD_LABEL:-com.ricardo.mem-guard}"; then
      exit 75
    fi
  fi
  peak=$(grep -Eio -m1 '^[-* ]*peak rss: *[0-9]+(\.[0-9]+)? *GB' $spec 2>/dev/null | grep -Eo '[0-9]+(\.[0-9]+)?' | head -1)
  if [[ -z $peak ]] && refuses launch.host-peak-declared "a job for $LAUNCH_HOST declares no 'Peak RSS: N GB' line; the memory guard there still kills anything over its limit" "add 'Peak RSS: N GB' to $spec, measured with /usr/bin/time -l on the heaviest step"; then
    exit 78
  fi
  if [[ -n $peak ]] && (( peak > ${LAUNCH_MAX_PEAK_GB:-8} )) &&
     refuses launch.host-peak-cap "declared peak $peak GB is over ${LAUNCH_MAX_PEAK_GB:-8} GB for $LAUNCH_HOST" "run it on a RunPod pod (rh pod), or stream the data and measure again"; then
    exit 78
  fi
fi
log=${spec:r}.log
# HARD RULE (Ricardo, 11-04): the goal must not turn into process. A spec over the cap needs
# SPEC_OVER_CAP="<reason>". The count is the job-specific part only (spec_words.py): the sweep
# embeds the lane's whole RULES.md and INTAKE.toml in its generated specs, which on 11-06 put
# c5's 472-word ask at 3,047 words and refused every job the sweep generated. Shared blocks
# added to the prompt below this line are never counted.
words=$(python3 "$H/tools/spec_words.py" "$spec") || exit 2
cap=${LAUNCH_SPEC_WORD_CAP:-1000}
# LAUNCH_SPEC_CAP_SINCE (epoch seconds): specs last modified before it predate the rule and are exempt,
# so an old long spec can still be relaunched (the lanes' launcher has exempted pre-11-04 specs since 11-04).
zmodload -F zsh/stat b:zstat 2>/dev/null
spec_mtime=$(zstat +mtime -- "$spec" 2>/dev/null); [[ $spec_mtime == <-> ]] || spec_mtime=0
if [[ -z $LAUNCH_RESUME ]] && (( words > cap )) && (( spec_mtime >= ${LAUNCH_SPEC_CAP_SINCE:-0} )); then
  if [[ -z $SPEC_OVER_CAP ]]; then
    if refuses launch.spec-word-cap "spec is $words job-specific words, over the $cap cap" "SPEC_OVER_CAP=<reason>, or cut the spec"; then
      print -- "exit 2 spec-over-cap $words words $(date)" >> "$log"
      notify "launch refused $job: spec over $cap words ($words job-specific)"
      exit 2
    fi
    print -- "spec over cap ($words words, no SPEC_OVER_CAP): warned, not refused (RULE #1) $(date)" >> "$log"
  fi
  # Once per launch: a detached job's child runs this check again and says nothing.
  if [[ -z ${LAUNCH_DETACHED:-} ]]; then
    print -- "spec over cap allowed ($words words): $SPEC_OVER_CAP $(date)" >> "$log"
    notify "launch $job: spec over $cap words allowed: $SPEC_OVER_CAP"
  fi
fi
# The registry resolves lane and lane_dir above, before host checks and logs.
# 11-10: a lane-yield HOLD stops the lane's jobs here. Until now only friends' own loops read one,
# so a hold on any other lane was a file nobody checked. Only general removes it.
if [[ -f $lane_dir/HOLD ]] &&
   refuses launch.lane-hold "lane $lane is on hold: $(head -1 $lane_dir/HOLD)" "general removes $lane_dir/HOLD (tell-general decision)"; then
  exit 78
fi
# 11-20 (general, RULE #1): lane-yield's own hold is YIELD_HOLD, a report with a decision card to general, not a
# HOLD. The job runs and carries it in its prompt; general holds the lane by turning it into HOLD.
yield_hold=
if [[ -f $lane_dir/YIELD_HOLD ]]; then
  yield_hold=$(head -1 "$lane_dir/YIELD_HOLD")
  refuses lane-yield.hold "lane $lane: $yield_hold" "general decides: mv $lane_dir/YIELD_HOLD $lane_dir/HOLD to hold the lane, or remove it" && exit 78
fi
# LAUNCH_DETACH=tmux: the job never lives under the caller's process tree. 11-01: the 7:25 AM memory kill
# took out eight jobs inside Claude's process tree with no exit line, and nobody noticed for 13 hours. So
# a job started outside tmux, or from a claude-* session, moves itself into its own tmux session
# job-<job> (the name job-stop and job-watchdog use) and the caller waits for it and exits with its code.
# It sits after every admission check, so a refusal still reaches the caller, and before the round gate
# and the registry, so a round is opened once and the registered pid is the job's. Ported from the
# lanes' launcher (_codex/launch.sh), which now execs this file.
if [[ ${LAUNCH_DETACH:-} == tmux && -z ${LAUNCH_DETACHED:-} ]]; then
  tm=${LAUNCH_TMUX:-tmux}
  s=; [[ -n $TMUX ]] && s=$($tm display-message -p '#S' 2>/dev/null)
  if [[ -z $TMUX || $s == claude-* ]]; then
    name=job-${job//[.:]/_}
    already=0
    if $tm has-session -t "=$name" 2>/dev/null; then
      # Not a second copy, and not a refusal either (RULE #1): wait for the running one and return its code.
      refuses launch.duplicate-session "$job already running in $name; waiting for it instead of starting a second copy" "tmux attach -t $name" && exit 75
      already=1
    fi
    # The session gets the tmux server's environment, not this one, so what this job was given (flags
    # included, resolved above) is passed explicitly.
    export LAUNCH_ROLE LAUNCH_MODEL LAUNCH_MODEL_OVERRIDE LAUNCH_MADE_BY LAUNCH_EXPLORE LAUNCH_EFFORT LAUNCH_HOST \
           LAUNCH_TIMEOUT_SECONDS LAUNCH_CLAUDE_TOOLS LAUNCH_BACKEND=$backend LAUNCH_LANE=$lane
    envs=("PATH=$PATH")
    for k in ${(ok)parameters}; do
      [[ $k == (LAUNCH_*|RH_*|RSTACK_*|AGENT_BACKEND|SPEC_OVER_CAP|MODEL_OVERRIDE_REASON|PYTHONDONTWRITEBYTECODE|*_NUM_THREADS) ]] || continue
      [[ $k == (LAUNCH_DETACHED|FORCE_LAUNCH) || ${parameters[$k]} != *export* ]] && continue
      envs+=("$k=${(P)k}")
    done
    envs+=(LAUNCH_DETACHED=1 FORCE_LAUNCH=1)
    at=0; [[ -f $log ]] && at=$(wc -c < "$log")
    if (( ! already )); then
      $tm new-session -d -s "$name" -c "$dir" "env ${(j: :)${(q)envs[@]}} zsh ${(q)self} ${(q)job} ${(q)dir}" || exit 1
    fi
    while $tm has-session -t "=$name" 2>/dev/null; do sleep ${LAUNCH_DETACH_POLL:-15}; done
    # The exit line the job wrote (every launcher line ends with $(date)); only this run's part of the log.
    last=$(tail -c +$(( at + 1 )) "$log" 2>/dev/null | grep -E '^exit [^ ]+ .*(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ' | tail -1 | awk '{print $2}')
    [[ $last == <-> ]] && exit $last
    [[ $last == stopped ]] && exit 143
    print -u2 -- "launch.sh: $job ended without an exit line in $log"; exit 1
  fi
fi
# Check the full spec in the process that will run it, so a detached launch warns only once.
spec_warn=$(python3 "$H/tools/spec_words.py" --warn-process-listing --job="$job" --lane="$lane" "$spec" 2>/dev/null) ||
  spec_warn='[launch.spec-process-listing] WARNING (fail-open, the work continues): spec process-listing lint unavailable.'
if [[ -n $spec_warn ]]; then
  print -r -u2 -- "$spec_warn"
  print -r -- "$spec_warn" >> "$log"
fi
# rounds.py has held this rule since the first c5 postmortem on 11-06: no repeat of a method that
# just produced a dry streak, no reopening a closed dead end, no round 1 without reading the KB.
# Nothing ever called it and no lane had written a single row, so every check read an empty ledger
# and passed. Calling `start` here is what makes the write unavoidable: it gates and opens the
# round in one command, and it refuses a fingerprint seen in the recent rounds, so relabelling the
# same knobs as a new family does not get through.
round_warn=
if [[ -n $LAUNCH_ROUND ]]; then
  round_args=(--lane "$lane_dir" start --round "$LAUNCH_ROUND" --family "${LAUNCH_FAMILY:-$lane}"
              --generator "$LAUNCH_GENERATOR" --params "$LAUNCH_PARAMS" --scorer "$LAUNCH_SCORER")
  [[ -z $LAUNCH_HYPOTHESIS ]] || round_args+=(--hypothesis "$LAUNCH_HYPOTHESIS")
  [[ -z $LAUNCH_NEW_EVIDENCE ]] || round_args+=(--new-evidence "$LAUNCH_NEW_EVIDENCE")
  round_at=0; [[ -f $log.round ]] && round_at=$(wc -c < "$log.round")
  python3 "$H/tools/rounds.py" "${round_args[@]}" >> "$log.round" 2>&1
  round_rc=$?
  # rounds.py exits 2 only when a gate the registry lets refuse refused (its fail-open checks print a
  # warning and pass). Any other failure is the round gate's own error, which never stops a job (RULE #1).
  if (( round_rc == 2 )); then
    print -u2 -- "launch.sh REFUSED $job: the round gate refused this round"
    tail -20 "$log.round" >&2
    print -- "exit 78 round-gate-refused $(date)" >> "$log"
    notify "launch refused $job: the round gate refused round $LAUNCH_ROUND (see $log.round)"
    exit 78
  elif (( round_rc != 0 )); then
    refuses launch.round-gate-error "rounds.py failed (exit $round_rc) before deciding; the round runs unrecorded" "read $log.round" && exit 78
  fi
  # 11-20 (general): a repeat, a dry family, a dead end or a drifted baseline warns and the round runs. This
  # run's warnings (not the whole file's) go to stderr, the job log and, below, the prompt and the receipt.
  round_warn=$(tail -c +$(( round_at + 1 )) "$log.round" 2>/dev/null | grep -h 'WARNING (fail-open')
  if [[ -n $round_warn ]]; then
    print -r -- "$round_warn" >&2
    print -r -- "round gate warnings, round $LAUNCH_ROUND runs (RULE #1): $round_warn $(date)" >> "$log"
  fi
fi
# 11-20 (general): a bug-hunt round that covered nothing new is recorded with a warning (bughunt.coverage); the
# lane's next job reads it in its prompt.
cov_warn=
if [[ -f $lane_dir/COVERAGE.jsonl ]]; then
  cov_warn=$(tail -1 "$lane_dir/COVERAGE.jsonl" | python3 -c 'import json,sys
try: print(json.loads(sys.stdin.read()).get("coverage_repeat", ""))
except Exception: pass' 2>/dev/null)
fi
# Admitted. If this job was blocked in the last week, the block did not hold: the ledger records a rerun,
# which the daily report counts as a harness bug (RULE #1).
python3 "$hblocks" admitted --job "$job" --lane "$lane" >/dev/null 2>&1
reg=${LAUNCH_STATE:-$PWD/.runtime/job-registry}
mkdir -p "$reg"
registry_name=${job//[^A-Za-z0-9_.-]/_}
# job-watchdog resumes a registered JOB by name, from its log beside the specs. A job given as a path (a
# sweep worker) has no such log, so it registers one level down, where the watchdog does not look (the
# lanes' launcher wrote those entries outside the registry altogether).
if [[ $job == */* ]]; then registry_name=paths/$registry_name; mkdir -p "$reg/paths"; fi
# host= is what lets a stop reach the machine the executor is actually on. Without it,
# 11-07: a --host job was stopped here, the local tmux session died and the log said
# "exit stopped", while codex kept running on the host as an orphan nobody was watching.
remote_marks=${LAUNCH_REMOTE_JOBS:-.local/state/research-harness/remote-jobs}
# restarts= is job-watchdog's per-job restart cap and path= the PATH it resumes with.
print -l "dir=$dir" "pid=$$" "restarts=${LAUNCH_RESTARTS:-0}" "path=$PATH" ${LAUNCH_HOST:+"host=$LAUNCH_HOST"} ${LAUNCH_HOST:+"remote_marks=$remote_marks"} > "$reg/$registry_name.job"
finished() {
  [[ ! -f $reg/$registry_name.job ]] || mv "$reg/$registry_name.job" "$reg/$registry_name.finished"
}
trap finished EXIT
stopped() { print -- "exit stopped by signal $(date)" >> "$log"; exit 143; }
trap stopped TERM HUP
selector=${LAUNCH_SELECTOR:-$H/worker_models.py}
# lane and lane_dir are derived above, with the round gate that needs them. A missing GOAL.md or
# an unavailable `rh` is not fatal: a job that cannot read its goal still runs, and the gap shows
# up in the prompt's absence rather than as a dead lane.
lessons=$(rh --root "${LAUNCH_LANE_ROOT:-${LAUNCH_IDEA_ROOT:-${RH_ROOT:-$PWD/.runtime}}}" lessons for "$lane" -n "${LAUNCH_LESSONS:-12}" 2>/dev/null)
start=1; [[ -n $LAUNCH_RESUME ]] && start=2
effort_percent=0; effort_resumed=0; effort_started=
effort_helper=$H/tools/effort_floor.py
effort_warn() {
  print -r -- "[launch.effort-floor] WARNING: $1" >> "$log"
  refuses launch.effort-floor "$1" || true
}
effort_env=()
# 11-23 (general, disk): one package cache per host, shared by every job, instead of a copy in each job's work
# dir (21 GB of per-job .uv-cache dirs in the m5's ~/jobs). uv clones from its cache on APFS, so a job's venv
# costs almost nothing beyond it. The executor gets these; a workspace-write Codex sandbox may write them.
cache_env=("UV_CACHE_DIR=${RH_UV_CACHE_DIR:-$HOME/.cache/uv}" "PIP_CACHE_DIR=${RH_PIP_CACHE_DIR:-$HOME/.cache/pip}"
           "npm_config_cache=${RH_NPM_CACHE_DIR:-$HOME/.cache/npm}")
if grep -qE '(^|[^A-Za-z_])(UV_CACHE_DIR|PIP_CACHE_DIR|npm_config_cache)=["'"'"']?(\$PWD|\.\.?/|\.uv-cache|cache)' "$spec" 2>/dev/null; then
  refuses launch.job-cache "$spec points a package cache inside the job's work dir, so this job keeps its own copy of every package" \
    "drop that line from the spec (and the lane's template): the launcher sets the shared cache" || true
fi
if (( start == 1 )) && [[ ${RSTACK_ABLATE:-} != 1 ]]; then
  effort_line=$(grep '^Effort floor:' "$spec" 2>/dev/null)
  effort_rc=$?
  if (( effort_rc == 0 )); then
    if [[ $effort_line =~ '^Effort floor:[[:blank:]]*([1-9]|[1-8][0-9]|9[0-5])%[[:blank:]]*$' ]]; then
      if (( LAUNCH_TIMEOUT_SECONDS == 0 )); then
        effort_warn "Effort floor needs a positive LAUNCH_TIMEOUT_SECONDS"
      elif effort_offsets=$(python3 "$effort_helper" snapshot "$dir" "$lane_dir" 2>&1); then
        effort_percent=$match[1]
        effort_env=("RH_EFFORT_FLOOR_JOB=$job")
      else
        effort_warn "$effort_offsets"
      fi
    else
      effort_warn "expected one spec line 'Effort floor: N%' with N between 1 and 95"
    fi
  elif (( effort_rc != 1 )); then
    effort_warn "could not read the effort floor from $spec"
  fi
fi
resume_prompt() {
  printf '\n\nRESUME (attempt %d): read STATUS.md, REPORT.md and existing files; continue completed work.\n' "$1"
}
# 11-22 (general, RULE #1): ddbench_scan_1122 was delegated to agy on the M4, which has no agy. It died in 1 s
# and the auto-grade charged Hydrogen a FAIL. Unless RH_LAUNCHER_EXECUTORS names them, the selector is offered
# the executors the run host has (this Mac, or LAUNCH_HOST over ssh with the job's own PATH), plus the one the
# job asked for. A probe that finds nothing offers all three, as before.
if [[ -z ${RH_LAUNCHER_EXECUTORS:-} ]]; then
  if [[ -n $LAUNCH_HOST ]]; then
    probe="export PATH=${${LAUNCH_REMOTE_PATH:+${(q)LAUNCH_REMOTE_PATH}}:-\$HOME/.local/bin:/opt/homebrew/bin:\$PATH}; "'for b in codex claude agy; do command -v "$b" >/dev/null 2>&1 && echo "$b"; done'
    found=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes -o ConnectTimeout=20 "$LAUNCH_HOST" "$probe" 2>/dev/null)
  else
    found=$(for b in codex claude agy; do v=LAUNCH_${(U)b}; command -v "${(P)v:-$b}" >/dev/null 2>&1 && print -r -- $b; done)
  fi
  have=(${(f)found})
  if (( $#have )); then
    (( ${have[(Ie)$backend]} )) || have+=($backend)
    export RH_LAUNCHER_EXECUTORS=${(j:,:)have}
    [[ $RH_LAUNCHER_EXECUTORS == codex,claude,agy ]] ||
      print -- "executors on ${LAUNCH_HOST:-this host}: $RH_LAUNCHER_EXECUTORS (the others are not installed there) $(date)" >> "$log"
  fi
fi
# 11-22 (general): a relaunch with --model-override after an attempt of this job today is a person overruling
# the harness's routing. It is recorded, and the daily report counts it as a harness bug.
if [[ -n ${LAUNCH_MODEL_OVERRIDE:-} && -n $log.selection.json*(N.mh-24[1]) ]]; then
  python3 "$hblocks" mark --job "${job:t}" --lane "$lane" --outcome override --gate selector \
    --reason "relaunched with --model-override: $LAUNCH_MODEL_OVERRIDE" >/dev/null 2>&1 || true
fi
codex_closed=; agy_closed=
prepare_attempt() {
  # 11-24: set only when that provider failed this job on quota or a rate limit (below): the selector then leaves it out.
  if [[ -n $codex_closed ]]; then export RH_CODEX_CLOSED=$codex_closed; else unset RH_CODEX_CLOSED; fi
  if [[ -n $agy_closed ]]; then export RH_AGY_CLOSED=$agy_closed; else unset RH_AGY_CLOSED; fi
  sel_exec=$backend
  [[ ${LAUNCH_PROVIDER:-} == (openrouter|gemini) && $backend == codex ]] && sel_exec=$LAUNCH_PROVIDER
  # This launcher runs all three executors, so a delegate may be on any of them. A host without one of
  # the CLIs names the ones it has in RH_LAUNCHER_EXECUTORS.
  selection=$(RH_LAUNCHER_EXECUTORS=${RH_LAUNCHER_EXECUTORS:-codex,claude,agy} python3 "$selector" --role "$LAUNCH_ROLE" --executor "$sel_exec" --model "$LAUNCH_MODEL" --explore "$LAUNCH_EXPLORE" --model-override "$LAUNCH_MODEL_OVERRIDE" --made-by "$LAUNCH_MADE_BY" --job "$job" --lane "$lane" --workdir "$dir" --lane-dir "$lane_dir" --spec "$spec" --print-route --log "$log" --receipt "$log.selection.json")
  sel_rc=$?
  # RULE #1: the selector refusing a pinned model, an explore pick or a missing --made-by is rerouted to the
  # leaderboard's own pick for the role, with a warning. Exit 4 is its one hard line (a pay-as-you-go route:
  # money), already named with its fix on stderr; that, or a role with no route at all, still stops the job.
  if (( sel_rc != 0 && sel_rc != 4 )) && [[ -n $LAUNCH_MODEL$LAUNCH_EXPLORE$LAUNCH_MADE_BY ]] &&
     ! refuses launch.model-selection "the selector refused the pinned model/explore/made-by for $job (exit $sel_rc); rerouting to the leaderboard pick for role $LAUNCH_ROLE" "name the role, not a model (LEADERBOARD.md)"; then
    print -- "model selection rerouted to the leaderboard pick (exit $sel_rc on the pinned route) $(date)" >> "$log"
    LAUNCH_MODEL=; LAUNCH_EXPLORE=; LAUNCH_MODEL_OVERRIDE=
    selection=$(RH_LAUNCHER_EXECUTORS=${RH_LAUNCHER_EXECUTORS:-codex,claude,agy} python3 "$selector" --role "$LAUNCH_ROLE" --executor "$sel_exec" --model "" --explore "" --model-override "" --made-by "$LAUNCH_MADE_BY" --job "$job" --lane "$lane" --workdir "$dir" --lane-dir "$lane_dir" --spec "$spec" --print-route --log "$log" --receipt "$log.selection.json")
    sel_rc=$?
  fi
  (( sel_rc == 0 )) || { print -- "exit 2 model-selection-refused $(date)" >> "$log"; exit 2; }
  selected_route=("${(@f)selection}")
  m=$selected_route[1]; backend=$selected_route[2]
  RSTACK_CALL_ROLE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("call_role", ""))' \
    "$log.selection.json" 2>/dev/null)
  export RSTACK_CALL_ROLE
  # 11-20 (bio): a Codex referee that reruns a claim through third_party.py run died with exit 71,
  # because sandbox-exec cannot nest inside Codex's own sandbox. third_party.py is the sandbox there
  # (pinned commit, no network, writes only the run dir), so a referee or review spec that says
  # `Third-party: run` gets Codex's outer sandbox off, recorded in the log and the selection receipt.
  # An explicit LAUNCH_CODEX_SANDBOX always wins.
  if [[ $backend == codex && -z ${LAUNCH_CODEX_SANDBOX:-} &&
        ( $RSTACK_CALL_ROLE == (referee|review) || $LAUNCH_ROLE == (referee|review) ) ]] &&
     grep -Eiq '^[-* ]*third-party: *run([^a-z]|$)' "$spec" 2>/dev/null; then
    export LAUNCH_CODEX_SANDBOX=danger-full-access
    print -- "codex sandbox danger-full-access: the spec says Third-party: run (third_party.py sandboxes that code) $(date)" >> "$log"
    python3 -c 'import json,sys
p=sys.argv[1]; d=json.load(open(p)); d["codex_sandbox"]={"mode":"danger-full-access","why":"spec line Third-party: run"}
json.dump(d, open(p, "w"), indent=2)' "$log.selection.json" 2>/dev/null || true
  fi
  unset RH_CODEX_CLOSED RH_AGY_CLOSED   # the selection's input only; the job's own children choose for themselves
  # 11-20 (general): the round ran past its gate's warnings; the receipt says which, and flags a comparison
  # against a baseline that stopped reproducing.
  if [[ -n $round_warn ]]; then
    python3 -c 'import json,sys
p=sys.argv[1]; d=json.load(open(p)); w=[l.strip() for l in sys.argv[2].splitlines() if l.strip()]
d["round_warnings"]=w
drift=[l for l in w if l.startswith("[rounds.baseline-drift]")]
if drift: d["baseline_drift"]=drift[0]
json.dump(d, open(p, "w"), indent=2)' "$log.selection.json" "$round_warn" 2>/dev/null || true
  fi
  case $backend in
    codex) cx=${LAUNCH_CODEX:-codex};;
    openrouter|gemini) export LAUNCH_PROVIDER=$backend; backend=codex; cx=${LAUNCH_CODEX:-codex};;
    claude) cx=${LAUNCH_CLAUDE:-claude};;
    agy) cx=${LAUNCH_AGY:-agy};;
    *) print -u2 -- "launch.sh refused $job: unsupported executor route $backend"; exit 2;;
  esac
  # 11-19: a codex-sized job delegated or overflowed to claude or agy keeps the shell a codex job has.
  if [[ $sel_exec == codex && $backend == (claude|agy) && $LAUNCH_CLAUDE_TOOLS != *Bash* ]]; then
    LAUNCH_CLAUDE_TOOLS+=,Bash
    print -- "tools widened to $LAUNCH_CLAUDE_TOOLS: a codex job routed to $backend $(date)" >> "$log"
  fi
  # A codex-sized job on claude gets a budget for its size rather than the $1 default of a claude job.
  if [[ $sel_exec == codex && $backend == claude && -z ${LAUNCH_CLAUDE_BUDGET:-} ]]; then
    LAUNCH_CLAUDE_BUDGET=5.00
    print -- "claude budget 5.00: a codex job routed to claude $(date)" >> "$log"
  fi
  # RULE #1: the concurrency cap queues a job, it does not refuse one. It waits for a slot (up to
  # LAUNCH_QUEUE_SECONDS, default 2 h), then runs anyway with a warning in harness-blocks.jsonl.
  queued=0
  while :; do
    python3 "${LAUNCH_GUARD:-${self:h:h}/rstack/tools/launch-guard}" \
      --job "$job" --lane "$lane" --backend "$backend" --provider "${LAUNCH_PROVIDER:-}" --log "$log"
    guard_rc=$?
    (( guard_rc == 0 )) && break
    if (( queued >= ${LAUNCH_QUEUE_SECONDS:-7200} )); then
      refuses launch.concurrency "still over the concurrency cap after ${queued}s in the queue; running anyway" "LAUNCH_MAX_CONCURRENT=N" && { print -- "exit $guard_rc concurrency-refused $(date)" >> "$log"; exit "$guard_rc"; }
      break
    fi
    (( queued == 0 )) && print -- "queued: concurrency cap (launch-guard exit $guard_rc) $(date)" >> "$log"
    sleep ${LAUNCH_QUEUE_POLL:-60}; (( queued += ${LAUNCH_QUEUE_POLL:-60} ))
  done
  export RSTACK_LANE="$lane"
  # Authentication is read only by the executing shell, never put in a receipt or command file.
  if [[ -n ${LAUNCH_PROVIDER:-} && ( $LAUNCH_PROVIDER != (openrouter|gemini) || $backend != codex ) ]]; then
    print -u2 -- "launch.sh refused $job: unsupported LAUNCH_PROVIDER"; exit 2
  fi
  # Shared context every job gets, injected here and never counted against the word cap above:
  # the job rules (prior art first), the lane's goal in the owner's words, and the lessons the
  # lane has already paid for. Before 11-06 only `rh ideas promote` enforced prior art and only
  # sweep prompts carried lessons, so 31 of the last 60 specs never mentioned either.
  { [[ ! -f ${self:h}/RULES.md ]] || { cat "${self:h}/RULES.md"; printf '\n---\n\n'; }
    # LAUNCH_PREAMBLE: files (colon separated) every job of this host reads first, e.g. the lanes' FRONT.md.
    for f in ${(s.:.)LAUNCH_PREAMBLE}; do
      [[ -f $f ]] || continue
      cat "$f"; [[ $(tail -n 1 "$f") == --- ]] && printf '\n' || printf '\n---\n\n'
    done
    [[ ! -f $lane_dir/GOAL.md ]] || { printf -- '--- LANE GOAL (%s, the owner'\''s words; agents never edit it) ---\n' "$lane"; cat "$lane_dir/GOAL.md"; printf '\n---\n\n'; }
    [[ -z $lessons ]] || { printf -- '--- LESSONS THIS LANE ALREADY PAID FOR ---\n%s\n---\n\n' "$lessons"; }
    # Fail-open checks let the job run and carry their warnings into the prompt.
    if [[ -n $spec_warn$round_warn$yield_hold$cov_warn ]]; then
      printf -- '--- HARNESS WARNINGS FOR THIS JOB (it runs anyway; act on them) ---\n'
      [[ -z $spec_warn ]] || printf -- '%s\n' "$spec_warn"
      [[ -z $round_warn ]] || printf -- 'Round gate:\n%s\n' "$round_warn"
      [[ $round_warn != *'[rounds.baseline-drift]'* ]] || printf -- 'BASELINE DRIFT: a registered baseline no longer reproduces, so any comparison against it is flagged. Say so in REPORT.md and do not count a beat against it as new.\n'
      [[ -z $yield_hold ]] || printf -- 'Lane yield: %s\n' "$yield_hold"
      [[ -z $cov_warn ]] || printf -- 'Bug-hunt coverage: %s\n' "$cov_warn"
      printf -- '---\n\n'
    fi
    cat "$spec"; (( i > 1 )) && resume_prompt "$i"; } > "$log.prompt"
}
attempt_timeout=$LAUNCH_TIMEOUT_SECONDS
for (( i = start; i <= 5 || effort_resumed; i++ )); do
  if (( ! effort_resumed )); then
    prepare_attempt
    attempt_budget=${LAUNCH_CLAUDE_BUDGET:-1.00}
  elif [[ -n $LAUNCH_RESUME ]]; then
    # Keep the prompt and selected route from the original attempt.
    resume_prompt "$i" >> "$log.prompt"
  fi
  print -- "=== attempt $i model $m${LAUNCH_HOST:+ host $LAUNCH_HOST} $(date)" >> "$log"
  attempt_log="$log.attempt-$i"
  out=${spec:r}.last.md
  if (( effort_percent )) && [[ -z $effort_started ]]; then effort_started=$SECONDS; fi
  effort_pull_failed=0
  if [[ -z $LAUNCH_HOST ]]; then
    if [[ ${LAUNCH_PROVIDER:-} == openrouter ]]; then
      export OPENROUTER_API_KEY="$(cat "$HOME/.config/openrouter/key")" || exit 2
      [[ -n $OPENROUTER_API_KEY ]] || { print -u2 -- 'missing OpenRouter key'; exit 2; }
    fi
    if [[ ${LAUNCH_PROVIDER:-} == gemini ]]; then
      export GEMINI_API_KEY="$(cat "$HOME/.config/gemini/api_key")" || exit 2
      [[ -n $GEMINI_API_KEY ]] || { print -u2 -- 'missing Gemini key'; exit 2; }
    fi
    env RH_JOB="${job:t}" "${cache_env[@]}" "${effort_env[@]}" nice -n 10 python3 "$H/agent_executor.py" --backend "$backend" \
      --executable "$cx" --directory "$dir" --model "$m" --effort "$LAUNCH_EFFORT" \
      --output "$out" --budget "$attempt_budget" \
      --allowed-tools "$LAUNCH_CLAUDE_TOOLS" --timeout-seconds "$attempt_timeout" \
      < "$log.prompt" 2>&1 | tee "$attempt_log" >> "$log"
    rc=$?   # pipefail: the executor's code, not tee's
    effort_ended=$SECONDS
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
      # 11-15: stamps can differ while the files are identical (a main commit that installs nothing moves one
      # Mac's stamp, not the other's), and every m5 job was refused. Different stamps only refuse when the
      # installed files differ too: both installs matching main (harness-sync --check) means the same code.
      # RULE #1: drift is repaired, not refused. harness-sync --host brings the host to this machine's
      # commit, and the job runs either way, with a warning if the repair did not take.
      if [[ -n $mine && $mine != $theirs ]] && ! { harness-sync --check >/dev/null 2>&1 && harness-sync --check --host "$LAUNCH_HOST" >/dev/null 2>&1; }; then
        if ! harness-sync --host "$LAUNCH_HOST" >> "$log" 2>&1 &&
           refuses launch.host-drift "$LAUNCH_HOST runs harness ${theirs:-unreadable} and this machine runs ${mine[1,12]}; harness-sync --host did not repair it" "harness-sync --host $LAUNCH_HOST"; then
          print -- "exit 2 harness-drift $LAUNCH_HOST ${theirs:-unreadable} vs ${mine[1,12]} $(date)" >> "$log"
          exit 2
        fi
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
    # The host's ssh PATH is the system one; ~/.local/bin goes first there too (the osascript shim).
    remote_auth=''
    if [[ ${LAUNCH_PROVIDER:-} == openrouter ]]; then
      remote_auth='export OPENROUTER_API_KEY=$(cat "$HOME/.config/openrouter/key")'
    elif [[ ${LAUNCH_PROVIDER:-} == gemini ]]; then
      remote_auth='export GEMINI_API_KEY=$(cat "$HOME/.config/gemini/api_key")'
    fi
    remote="cd ${(q)dir} 2>/dev/null || { echo ${(q)missing} >&2; exit 2; }
export PATH=${${LAUNCH_REMOTE_PATH:+${(q)LAUNCH_REMOTE_PATH}}:-\$HOME/.local/bin:/opt/homebrew/bin:\$PATH}
${LAUNCH_PROVIDER:+export LAUNCH_PROVIDER=${(q)LAUNCH_PROVIDER}}
${RH_ALLOW_OPENROUTER:+export RH_ALLOW_OPENROUTER=${(q)RH_ALLOW_OPENROUTER}}
${RH_ALLOW_GEMINI_API:+export RH_ALLOW_GEMINI_API=${(q)RH_ALLOW_GEMINI_API}}
${LAUNCH_CODEX_SANDBOX:+export LAUNCH_CODEX_SANDBOX=${(q)LAUNCH_CODEX_SANDBOX}}
${LAUNCH_CODEX_NETWORK:+export LAUNCH_CODEX_NETWORK=${(q)LAUNCH_CODEX_NETWORK}}
export RSTACK_LANE=${(q)lane} RSTACK_CALL_ROLE=${(q)RSTACK_CALL_ROLE}
$remote_auth
mkdir -p ${(q)${out:h}} 2>/dev/null || { echo ${(q)nodir} >&2; exit 2; }
mkdir -p $rmarks 2>/dev/null || true
echo \$\$ > $rmarks/${(q)${job:t}}.pid 2>/dev/null || true
exec env RH_JOB=${(q)${job:t}} ${(j: :)${(q)cache_env[@]}} ${(j: :)${(q)effort_env[@]}} nice -n 10 python3 $rexec --backend ${(q)backend} --executable ${(q)cx} --directory ${(q)dir} --model ${(q)m} --effort ${(q)LAUNCH_EFFORT} --output ${(q)out} --budget ${(q)attempt_budget} --allowed-tools ${(q)LAUNCH_CLAUDE_TOOLS} --timeout-seconds ${(q)attempt_timeout}"
    # 11-08: this was one foreground ssh, so the job lived exactly as long as the connection. A
    # network blip ended a 5 h job, and the controller's reset at 22:16 took every job on the host
    # with it. remote_run.py starts the executor detached THERE (nohup, files for stdio, a watcher
    # that records the exit code), streams its output here, survives a dropped connection, and on a
    # restarted launcher reattaches to the attempt in $log.remote.json instead of starting another.
    print -r -- "$remote" > "$log.rcmd"
    # remote_run appends the host's output to the job log as it arrives; this attempt's part is then
    # copied out for the checks below.
    at=$(wc -c < "$log")
    python3 "$H/tools/remote_run.py" --host "$LAUNCH_HOST" --job "${job:t}" \
      --log "$log" --prompt "$log.prompt" --command "$log.rcmd" --state "$log.remote.json"
    rc=$?
    effort_ended=$SECONDS
    tail -c +$(( at + 1 )) "$log" > "$attempt_log"
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
    # 11-22: third_party.jsonl (third_party.py run's receipts) comes home too. Without it the controller has the
    # checkout's folders but not their receipts, and the sweep's check failed math's kill stage for it.
    ledger=(); pull_check=()
    (( ! effort_percent )) || pull_check=(--checksum)
    [[ ${dir:A:h:t} != lanes ]] || ledger=(--exclude='/RESULTS.jsonl')  # the work dir IS a lane
    rsync -a --timeout=120 --max-size="${LAUNCH_PULL_MAX_SIZE:-4m}" -e "${LAUNCH_SSH:-ssh}" \
      "${ledger[@]}" "${pull_check[@]}" \
      --include='*/' --include='STATUS.md' --include='REPORT.md' --include='PLAN.md' \
      --include='RESULTS.jsonl' --include='*.selection.json' --include='*.report.md' \
      --include='prior-art-*.json' \
      --include='third_party.jsonl' \
      --include='CLAIM.md' --include='RESULT.md' --include='NOTE.md' --include='FREEZE.md' \
      --include='DATA.md' --include='VERDICT.md' --include='BASELINES.json' --include='RECHECK.csv' \
      --include='referee_*.md' \
      --include="${out:t}" \
      --exclude='*' "$LAUNCH_HOST:$dir/" "$dir/" >> "$log.pull" 2>&1 || {
      print -- "pull from $LAUNCH_HOST failed rc $? (outputs are on the host) $(date)" >> "$log"
      effort_pull_failed=1
    }
    # The executor's last message is written beside the spec, which for a lane job is not in the work dir
    # (_codex/JOB.last.md), so the pull above cannot bring it back.
    if [[ ${out:A} != ${dir:A}/* ]]; then
      rsync -a --timeout=120 "${pull_check[@]}" -e "${LAUNCH_SSH:-ssh}" "$LAUNCH_HOST:$out" "$out" >> "$log.pull" 2>&1 || {
        print -- "pull of ${out:t} from $LAUNCH_HOST failed $(date)" >> "$log"
        [[ $backend != claude ]] || effort_pull_failed=1
      }
    fi
    # A receipt binds the evidence it cites by path and hash: the X capture copy, or the
    # X_SEARCHES.jsonl copy for a dated none-row, in the run directory. Those file names are the
    # worker's, so the receipts pulled above say which files to bring back too. Without this a
    # receipt that is correct on the host fails here for a missing file (planets, 11-09).
    named=$(python3 -I "$H/tools/receipt_files.py" "$dir" 2>>"$log.pull")
    # One file at a time: openrsync drops the whole list when one name is missing on the host.
    for rel in ${(f)named}; do
      print -r -- "$rel" | rsync -a --timeout=120 --max-size="${LAUNCH_PULL_MAX_SIZE:-4m}" -e "${LAUNCH_SSH:-ssh}" \
        --files-from=- "$LAUNCH_HOST:$dir/" "$dir/" >> $log.pull 2>&1 ||
        print -r -- "pull of receipt evidence $rel from $LAUNCH_HOST failed $(date)" >> $log
    done
    # Say so when the host wrote the ledger anyway. Silence here would mean rows exist on a
    # machine nobody reads, which is how a result gets lost rather than merged wrongly.
    if (( $#ledger )); then
      ours=$(shasum -a 256 "$dir/RESULTS.jsonl" 2>/dev/null | cut -d' ' -f1)
      theirs=$(${=${LAUNCH_SSH:-ssh}} -o BatchMode=yes "$LAUNCH_HOST" \
        "shasum -a 256 ${(q)dir}/RESULTS.jsonl 2>/dev/null | cut -d' ' -f1" 2>/dev/null)
      if [[ -n $theirs && $theirs != $ours ]]; then
        effort_pull_failed=1
        msg="ledger diverged: RESULTS.jsonl on $LAUNCH_HOST differs from this machine's for lane $lane. This machine stays authoritative; the host copy was NOT merged and is still there."
        print -- "LEDGER DIVERGED $LAUNCH_HOST $(date)" >> "$log"
        print -- "$msg" >> "$log"
        notify "$msg"
      fi
    fi
  fi
  policy_flag=0
  if [[ $backend == codex ]] && grep -Fq 'This content was flagged for possible cybersecurity risk' "$attempt_log"; then
    policy_flag=1
    print -- "exit $rc codex-policy-flag $(date)" >> "$log"
    print -- "Codex policy flag (exit $rc): This content was flagged for possible cybersecurity risk. $(date)" >> "$dir/STATUS.md"
  else
    print -- "exit $rc $(date)" >> "$log"
  fi
  effort_elapsed=$(( effort_ended - effort_started ))
  effort_left=$(( LAUNCH_TIMEOUT_SECONDS - (SECONDS - effort_started) ))
  if (( effort_percent && rc == 0 && ! policy_flag &&
        effort_elapsed * 100 < LAUNCH_TIMEOUT_SECONDS * effort_percent &&
        (effort_resumed || effort_left > 0) )); then
    if (( effort_pull_failed )); then
      effort_warn "could not harvest the effort floor's inputs from $LAUNCH_HOST"
    elif effort_next=$(python3 "$effort_helper" check "$dir" "$lane_dir" "$job" "$effort_offsets" \
        "$effort_percent" "$effort_elapsed" "$effort_left" "$LAUNCH_TIMEOUT_SECONDS" "$effort_resumed" \
        "$backend" "$attempt_budget" "$out" "$log.prompt" "$log.selection.json" 2>&1); then
      if [[ -n $effort_next ]]; then
        LAUNCH_RESUME=1; effort_resumed=1
        attempt_timeout=$effort_left; attempt_budget=$effort_next
        LC_ALL=C printf 'effort-floor resume at %.2f/%.2f min\n' \
          "$(( effort_elapsed / 60.0 ))" "$(( LAUNCH_TIMEOUT_SECONDS / 60.0 ))" >> "$log"
        continue
      fi
    else
      effort_warn "$effort_next"
    fi
  fi
  if ! python3 "$selector" --log "$log" --receipt "$log.selection.json" --outcome "$rc" &&
     refuses launch.outcome-receipt "could not record the outcome of $job in its selection receipt" "python3 $selector --log $log --receipt $log.selection.json --outcome $rc"; then
    exit 2
  fi
  print -r -- "GRADE ON RETURN: python3 ${selector:A} --grade pass|partial|fail --note WHY --receipt ${log:A}.selection.json --log ${log:A}" >> "$log"
  (( ! effort_resumed )) || break
  # 11-24 (general): Codex enforces its own limits. A Codex job that failed on quota or a rate limit is rerun
  # with Codex left out (RH_CODEX_CLOSED, set in prepare_attempt): the selector gives agy's Gemini for the
  # role, else Claude. An agy run that hit its quota goes the other way (RH_AGY_CLOSED): Codex, else Claude.
  # Neither is an attempt, so neither uses up the five.
  if [[ $backend == codex && -z $codex_closed ]] && (( rc != 0 )) &&
     tail -40 "$attempt_log" | grep -Eqi 'usage limit|usage_limit_reached|insufficient_quota|rate.?limit|429 too many'; then
    codex_closed='quota or rate limit'
    print -- "codex hit its quota or rate limit: rerunning $job on Gemini (agy), else Claude $(date)" >> "$log"
    (( i-- )); continue
  fi
  if [[ $backend == agy && -z $agy_closed && ${RH_LAUNCHER_EXECUTORS:-codex} == *(codex|claude)* ]] && (( rc != 0 )) &&
     tail -40 "$attempt_log" | grep -Eqi 'AGY_QUOTA|RESOURCE_EXHAUSTED|Individual quota reached'; then
    agy_closed='quota'
    print -- "agy hit its quota: rerunning $job on Codex, else Claude $(date)" >> "$log"
    (( i-- )); continue
  fi
  (( policy_flag == 0 && rc != 0 && i < 5 )) || break
  [[ $backend == codex ]] || break  # A Claude retry must not reset its spend cap.
  # A quota response ends this model's attempt even if it also says 'at capacity'.
  if [[ ${LAUNCH_PROVIDER:-} == gemini ]] && grep -Eqi '429|RESOURCE_EXHAUSTED|quota' "$attempt_log"; then break; fi
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
# 11-19 (general): a returned delegated job is graded here, at return, with no session in the loop: its own
# checks first (exit code, Shipped and You asked lines, the spec's Check: lines), else the lane's reviewing
# model. Whatever cannot be graded is recorded "ungraded" (counted, outside the rate) for the morning report.
# Never blocks and never fails the job. A --host job's outputs stay on the host, so its checks run there.
python3 "$H/auto_grade.py" --receipt "$log.selection.json" --log "$log" --dir "$dir" \
  --spec "$spec" ${LAUNCH_HOST:+--host} ${LAUNCH_HOST:+$LAUNCH_HOST} >> "$log" 2>&1 || true
python3 "$selector" --record-ungraded --receipt "$log.selection.json" --log "$log" >/dev/null 2>&1 || true
yield=${LAUNCH_YIELD_LEDGER:-$PWD/.runtime/job-yield.jsonl}
mkdir -p "${yield:h}" 2>/dev/null
python3 -I -c 'import json, sys, time
print(json.dumps(dict(utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), job=sys.argv[1],
                      rc=sys.argv[2], restated=sys.argv[3] == "1", shipped=sys.argv[4][:300])))' \
  "$job" "$rc" "$ok_ask" "$shipped" >> "$yield" 2>/dev/null
# The notification is optional and never fatal: a missing notifier must not turn a finished job
# into a failed one.
(( ok_ask && ok_ship )) || notify "job $job ended without the hard-rule lines (You asked: $ok_ask, Shipped: $ok_ship)"
exit "$rc"
