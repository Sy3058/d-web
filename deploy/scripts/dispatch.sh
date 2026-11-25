#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 1 || ( $1 != staging && $1 != production ) ]]; then
  echo "usage: dispatch.sh staging|production" >&2
  exit 64
fi
readonly deploy_env=$1
readonly command_text=${SSH_ORIGINAL_COMMAND-}
if [[ $command_text =~ ^(deploy|status)\ ([0-9a-f]{40})$ ]]; then
  readonly action=${BASH_REMATCH[1]}
  readonly deploy_sha=${BASH_REMATCH[2]}
else
  echo "rejected deployment command" >&2
  exit 64
fi

readonly script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly deploy_root=${DWEB_DEPLOY_ROOT:-$(dirname -- "$script_dir")}
readonly env_dir=$deploy_root/$deploy_env
readonly jobs_dir=$env_dir/jobs
readonly job_dir=$jobs_dir/$deploy_sha
readonly state_file=$job_dir/state
readonly log_file=$job_dir/job.log
readonly worker_lock=$job_dir/worker.lock
readonly worker=$script_dir/run-job.sh

[[ -d $deploy_root && ! -L $deploy_root ]] || { echo "invalid deployment root" >&2; exit 1; }
[[ -d $env_dir && ! -L $env_dir ]] || { echo "invalid deployment environment" >&2; exit 1; }
[[ -x $worker && ! -L $worker ]] || { echo "deployment worker unavailable" >&2; exit 1; }
[[ ! -L $jobs_dir && ! -L $job_dir ]] || { echo "invalid deployment job path" >&2; exit 1; }
mkdir -p -- "$job_dir"
chmod 700 "$jobs_dir" "$job_dir"
[[ ! -L $state_file && ! -L $log_file && ! -L $worker_lock ]] || { echo "invalid deployment job files" >&2; exit 1; }

read_state() {
  local value=unknown
  if [[ -f $state_file && ! -L $state_file ]]; then
    IFS= read -r value < "$state_file" || value=unknown
  fi
  case $value in running|success|failed) printf '%s\n' "$value" ;; *) printf 'unknown\n' ;; esac
}

write_state() {
  local value=$1 state_tmp
  state_tmp=$(mktemp "$job_dir/.state.XXXXXX")
  printf '%s\n' "$value" > "$state_tmp"
  mv -- "$state_tmp" "$state_file"
}

state=$(read_state)
if [[ $action == status ]]; then
  echo "deployment job: $state"
  [[ $state == success ]]
  exit
fi
exec 8>>"$worker_lock"
if flock -n 8; then
  state=$(read_state)
  if [[ -f $log_file ]]; then
    mv -- "$log_file" "$job_dir/job.previous.$(date -u +%Y%m%dT%H%M%SZ).$$.log"
  fi
  : > "$log_file"
  chmod 600 "$log_file"
  write_state running
  DWEB_WORKER_LOCK_FD=8 nohup setsid "$worker" "$deploy_env" "$deploy_sha" \
    </dev/null >>"$log_file" 2>&1 &
  exec 8>&-
else
  exec 8>&-
fi

readonly monitor_deadline=$((SECONDS + 2700))
while (( SECONDS < monitor_deadline )); do
  state=$(read_state)
  case $state in
    success) echo "deployment job: success"; exit 0 ;;
    failed) echo "deployment job: failed" >&2; exit 1 ;;
  esac
  echo "deployment job: running"
  sleep 5
done
echo "deployment job: still running; query status with the same SHA" >&2
exit 124
