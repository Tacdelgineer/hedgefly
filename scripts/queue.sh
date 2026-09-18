#!/usr/bin/env bash
# Run jobs one after another, unattended.
#
#   scripts/queue.sh queue/day7.jobs              # status and logs go to runs/queue/<jobs-name>/
#   nohup setsid scripts/queue.sh queue/day7.jobs >/dev/null 2>&1 &   # detached, survives logout
#
# A jobs file has one job per line:   <name> <gpu|cpu> <command...>
# Blank lines and lines starting with # are skipped. Each command runs from the repo root under
# bash, with its own log at runs/queue/<jobs-name>/logs/<name>.log.
#
# After each job, a line is appended to runs/queue/<jobs-name>/status.tsv:
#   finished_at  job  exit_code  started_at  minutes  log
# The queue's own diary (starts, waits, stops) is runs/queue/<jobs-name>/queue.log.
#
# Rules it keeps:
# - Stops at the first job that fails. Fix it and start the queue again: jobs already recorded
#   with exit 0 are skipped, so it resumes where it stopped.
# - Never starts a gpu job while another GPU job is running: it waits until no known GPU job of
#   this project is alive (evolution, the finale scripts, the benchmarks) and the GPU has been
#   quiet for three samples in a row. Idle services that merely hold a GPU context (ComfyUI and
#   friends) do not count; only work does.
# - Only one queue runs at a time (a lock file).
# - Touch runs/queue/<jobs-name>/STOP to stop gracefully before the next job.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="${1:?usage: scripts/queue.sh <jobs-file>}"
[[ "$JOBS" = /* ]] || JOBS="$REPO/$JOBS"
NAME="$(basename "$JOBS" .jobs)"
DIR="$REPO/runs/queue/$NAME"
STATUS="$DIR/status.tsv"
DIARY="$DIR/queue.log"
mkdir -p "$DIR/logs"

GPU_JOBS='scripts[./]run_evolution|finale_flies\.py|finale_llm\.py|scripts[./]check_sensitivity|scripts[./]bench'
GPU_QUIET_PERCENT=25          # below this, three samples running, the GPU counts as free
POLL_SECONDS=60

now() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "$(now)  $*" | tee -a "$DIARY"; }

exec 9>"$DIR/.lock"
if ! flock -n 9; then echo "another queue is already running $NAME" >&2; exit 3; fi

[[ -f "$STATUS" ]] || printf 'finished_at\tjob\texit_code\tstarted_at\tminutes\tlog\n' > "$STATUS"
say "queue $NAME started (pid $$), jobs from $JOBS"

gpu_busy() {
    # a GPU job of ours is alive
    if pgrep -f "$GPU_JOBS" >/dev/null 2>&1; then echo "a GPU job is running"; return 0; fi
    # or something else is working the GPU hard
    local k u
    for k in 1 2 3; do
        u="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc '0-9')"
        [[ -z "$u" ]] && { echo "nvidia-smi gave no reading"; return 0; }
        (( u < GPU_QUIET_PERCENT )) || { echo "the GPU is at ${u}%"; return 0; }
        sleep 5
    done
    return 1
}

done_ok() { awk -F'\t' -v j="$1" '$2==j && $3=="0" {found=1} END {exit !found}' "$STATUS"; }

while read -r job kind cmd; do
    [[ -z "${job:-}" || "$job" == \#* ]] && continue
    if [[ -f "$DIR/STOP" ]]; then say "STOP file found; stopping before $job"; exit 0; fi
    if done_ok "$job"; then say "skip $job (already finished with exit 0)"; continue; fi

    if [[ "$kind" == gpu ]]; then
        while reason="$(gpu_busy)"; do
            say "waiting to start $job: $reason"
            sleep "$POLL_SECONDS"
        done
    fi

    log="$DIR/logs/$job.log"
    started="$(now)"; t0=$SECONDS
    say "start $job ($kind): $cmd"
    ( cd "$REPO" && echo "# $started  $job  $cmd" && bash -c "$cmd" ) >"$log" 2>&1
    code=$?
    minutes=$(( (SECONDS - t0) / 60 ))
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(now)" "$job" "$code" "$started" "$minutes" "$log" >> "$STATUS"
    say "finish $job: exit $code after $minutes min"

    if (( code != 0 )); then
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(now)" "QUEUE-STOPPED" "$code" "$started" "-" "$job failed; see its log" >> "$STATUS"
        say "QUEUE STOPPED: $job failed with exit $code; later jobs were not started"
        exit "$code"
    fi
done < "$JOBS"

say "queue $NAME finished: every job exited 0"
