#!/usr/bin/env bash
# d-web-m2 워크트리 전용 dev 서버 기동 스크립트.
#
# d-web(원본 워크트리)과 "동시에" 띄우지 않는 게 전제다. 포트는 dev.sh와 완전히
# 동일하게 8000/4321/5173을 그대로 쓴다(APP_BASE_URL 등 오버라이드 없음) - 이유는
# 2026-07-20 실측 사고 2건:
#   1) 포트를 다르게 분리했더니(8001/5174/4322) admin 두 탭이 서로 다른 백엔드
#      프로세스로 같은 HttpOnly 쿠키(쿠키는 포트를 구분하지 않는다)를 각자
#      회전(rotate_refresh)시키다가, 한쪽이 이미 회전시킨 죽은 토큰을 다른 쪽이
#      재제출 - 서버가 "재사용(탈취)"으로 오판해 전체 세션을 revoke했다
#      (auth_service.py rotate_refresh, "이미 revoke된 토큰 재제출" 분기).
#   2) 구글/카카오 OAuth의 redirect_uri는 개발자 콘솔에 등록된 값과 정확히 일치해야
#      하는데, 그 등록 목록은 우리 코드 밖(외부 콘솔)이라 포트를 바꾸면 로그인
#      자체가 redirect_uri_mismatch로 막힌다.
# 포트를 안 바꾸면 이 둘 다 구조적으로 사라진다(CORS 오버라이드도 필요 없어짐).
# 대가: d-web과 동시에 못 띄운다 - 이 스크립트를 돌리기 전에 d-web 쪽 dev 서버
# (uvicorn/vite/astro)를 먼저 꺼야 한다(postgres는 꺼도 됨/안 꺼도 됨, 상관없음).
#
# postgres는 이 스크립트가 절대 건드리지 않는다 - 두 워크트리가 같은 dev DB를
# 공유하는 게 이 프로젝트의 전제(docs/MISTAKES.md)라, d-web 쪽이 관리하는
# 컨테이너(d-web-postgres-1, localhost:5432)를 그대로 쓴다. 살아있는지 확인만
# 하고, 없으면 안내만 하고 종료한다(대신 띄우지 않음 - 이 디렉터리에서
# `docker compose up -d postgres`를 돌리면 프로젝트명이 달라(d-web-m2) 별도의
# 빈 볼륨 컨테이너가 생겨 5432를 가로채는 사고가 난다. 2026-07-20 실제로 났었음).
#
# backend/.env는 d-web/backend/.env의 심볼릭 링크(공유 파일)다 - 어차피 포트를
# 안 바꾸므로 이 스크립트는 그 값을 오버라이드할 필요가 없다.
#
# 사용법:
#   ./dev-m2.sh   전체 개발 환경 기동 (Ctrl+C 로 dev 서버 일괄 종료)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

c_api=$'\033[32m'; c_fe=$'\033[34m'; c_admin=$'\033[35m'; c_db=$'\033[33m'; c_off=$'\033[0m'

# 1) postgres는 건드리지 않고 살아있는지만 확인
echo "${c_db}[db]${c_off} d-web-postgres-1 확인 중 (이 스크립트는 postgres를 직접 띄우지 않음)..."
if ! docker exec d-web-postgres-1 pg_isready -U postgres >/dev/null 2>&1; then
  echo "${c_db}[db]${c_off} d-web-postgres-1이 안 보이거나 준비 안 됨."
  echo "  d-web 워크트리에서 ./dev.sh --no-db 를 먼저 띄우거나,"
  echo "  docker start d-web-postgres-1 로 기존 컨테이너를 직접 재기동해라."
  echo "  ⚠️ 이 디렉터리(d-web-m2)에서 docker compose up -d postgres를 직접 돌리지 말 것 -"
  echo "     프로젝트명이 달라(d-web-m2) 별도의 빈 볼륨 컨테이너가 5432를 가로챈다."
  exit 1
fi
echo "${c_db}[db]${c_off} ready (127.0.0.1:5432, d-web 워크트리가 관리하는 공유 DB)"

# 2) d-web 쪽 서버가 포트를 이미 물고 있으면 여기서 바로 걸러 명확한 에러로 안내
#    (아니면 uvicorn/vite/astro가 자체 에러 메시지로만 실패해 원인 파악이 늦어진다)
for port in 8000 4321 5173; do
  if lsof -i ":$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "포트 $port 가 이미 사용 중이다 - d-web 쪽 dev 서버를 먼저 끌 것 (Ctrl+C)."
    exit 1
  fi
done

# 3) dev 서버 3개 백그라운드 기동, 로그에 prefix 부착
pids=()
run() { # run <prefix> <color> <dir> <command...>
  local prefix=$1 color=$2 dir=$3; shift 3
  ( cd "$dir" && "$@" 2>&1 | sed "s/^/${color}[${prefix}]${c_off} /" ) &
  pids+=($!)
}

cleanup() {
  echo
  echo "dev 서버 종료 중... (postgres는 건드리지 않음 - d-web 쪽에서 관리)"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  pkill -P $$ 2>/dev/null || true
  wait 2>/dev/null || true
  echo "종료 완료."
  exit 0
}
trap cleanup INT TERM

run api   "$c_api"   "$ROOT/backend" uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
run fe    "$c_fe"    "$ROOT"         pnpm dev:fe
run admin "$c_admin" "$ROOT"         pnpm dev:admin

echo
echo "──────────────────────────────────────────"
echo " api    → http://localhost:8000  (d-web-m2 코드)"
echo " front  → http://localhost:4321  (d-web-m2 코드)"
echo " admin  → http://localhost:5173  (d-web-m2 코드)"
echo " d-web과 포트가 같으므로 동시에 띄우지 말 것."
echo " (Ctrl+C 로 dev 서버 일괄 종료. postgres는 계속 떠 있음)"
echo "──────────────────────────────────────────"

wait
