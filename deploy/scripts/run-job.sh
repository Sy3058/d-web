#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
trap '' HUP

if [[ $# -ne 2 || ( $1 != staging && $1 != production ) || ! $2 =~ ^[0-9a-f]{40}$ ]]; then
  exit 64
fi
readonly deploy_env=$1
readonly deploy_sha=$2
readonly script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly deploy_root=${DWEB_DEPLOY_ROOT:-$(dirname -- "$script_dir")}
readonly job_dir=$deploy_root/$deploy_env/jobs/$deploy_sha
readonly state_file=$job_dir/state
readonly worker_lock=$job_dir/worker.lock
[[ -d $job_dir && ! -L $job_dir && ! -L $state_file && ! -L $worker_lock ]] || exit 1

if [[ ${DWEB_WORKER_LOCK_FD-} != 8 ]]; then
  exec 8>>"$worker_lock"
fi
flock -n 8 || exit 0

write_state() {
  local state=$1 state_tmp
  state_tmp=$(mktemp "$job_dir/.state.XXXXXX")
  printf '%s\n' "$state" > "$state_tmp"
  mv -- "$state_tmp" "$state_file"
}

worker_result=failed
finish_job() {
  write_state "$worker_result"
}
trap finish_job EXIT
write_state running
"$script_dir/deploy.sh" "$deploy_env" "$deploy_sha"
worker_result=success
