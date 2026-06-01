#!/usr/bin/env bash
# 일상 개발 모드 한 방에 켜기
#   - postgres: 도커 (코드와 무관 → 다시 빌드할 일 없음)
#   - api / frontend / admin: 로컬 dev 서버 (hot reload)
# 통합 검증(도커로 전체 빌드)은 이 스크립트가 아니라 `docker compose up -d --build` 사용.
#
# 사용법:
#   ./dev.sh           전체 개발 환경 기동 (Ctrl+C 로 dev 서버 일괄 종료)
#   ./dev.sh --no-db   postgres 도커는 건드리지 않고 dev 서버만 (이미 떠 있을 때)
#   ./dev.sh stop      postgres 도커까지 내림
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# 색상 prefix (api=초록, fe=파랑, admin=마젠타)
c_api=$'\033[32m'; c_fe=$'\033[34m'; c_admin=$'\033[35m'; c_db=$'\033[33m'; c_off=$'\033[0m'

if [[ "${1:-}" == "stop" ]]; then
  echo "${c_db}[db]${c_off} postgres 컨테이너 종료"
  docker compose stop postgres
  exit 0
fi

# 1) postgres 도커 기동 + healthy 대기
if [[ "${1:-}" != "--no-db" ]]; then
  echo "${c_db}[db]${c_off} postgres 기동 중..."
  docker compose up -d postgres
  echo "${c_db}[db]${c_off} healthy 대기..."
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null)" == "healthy" ]; do
    sleep 1
  done
  echo "${c_db}[db]${c_off} ready (127.0.0.1:5432)"
fi

# 2) dev 서버 3개 백그라운드 기동, 로그에 prefix 부착
pids=()
run() { # run <prefix> <color> <dir> <command...>
  local prefix=$1 color=$2 dir=$3; shift 3
  ( cd "$dir" && "$@" 2>&1 | sed "s/^/${color}[${prefix}]${c_off} /" ) &
  pids+=($!)
}

cleanup() {
  echo
  echo "dev 서버 종료 중..."
  # 자식 프로세스 그룹까지 정리
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  pkill -P $$ 2>/dev/null || true
  wait 2>/dev/null || true
  echo "종료 완료. (postgres 는 계속 떠 있음 → 내리려면 ./dev.sh stop)"
  exit 0
}
trap cleanup INT TERM

run api   "$c_api"   "$ROOT/backend" uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
run fe    "$c_fe"    "$ROOT"         pnpm dev:fe
run admin "$c_admin" "$ROOT"         pnpm dev:admin

echo
echo "──────────────────────────────────────────"
echo " api    → http://localhost:8000"
echo " front  → http://localhost:4321"
echo " admin  → http://localhost:5173"
echo " (Ctrl+C 로 dev 서버 일괄 종료)"
echo "──────────────────────────────────────────"

wait
