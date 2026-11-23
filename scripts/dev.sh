#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

for command in docker pnpm uv setsid; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: $command" >&2
    exit 1
  fi
done

docker compose --profile preview stop caddy admin frontend api
pnpm run dev:db

for port in 4321 5173 8000; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    echo "Port $port is already in use. Stop the existing process and retry." >&2
    exit 1
  fi
done

child_pids=()
cleanup() {
  local status=$?
  local pid
  local deadline

  trap - EXIT INT TERM

  for pid in "${child_pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done

  deadline=$((SECONDS + 5))
  while ((SECONDS < deadline)); do
    local running=false
    for pid in "${child_pids[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then
        running=true
        break
      fi
    done
    if [[ $running == false ]]; then
      break
    fi
    sleep 0.1
  done

  for pid in "${child_pids[@]}"; do
    kill -KILL -- "-$pid" 2>/dev/null || true
  done
  wait "${child_pids[@]}" 2>/dev/null || true

  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

setsid pnpm run dev:api &
child_pids+=("$!")
setsid pnpm run dev:fe &
child_pids+=("$!")
setsid pnpm run dev:admin &
child_pids+=("$!")

set +e
wait -n "${child_pids[@]}"
status=$?
set -e

exit "$status"
