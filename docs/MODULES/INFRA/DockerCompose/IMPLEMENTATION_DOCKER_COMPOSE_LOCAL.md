# IMPLEMENTATION - 로컬 Docker Compose + Caddy 통합 (C1, C2)

| 항목 | 내용 |
|------|------|
| 영역 | INFRA |
| 작업 | C1 (compose.yml), C2 (Caddy 로컬 라우팅) |
| 선행 | B1 (backend), B6 (Astro), B7 (Vite SPA) |
| 커밋 | common/feat/c1-docker-compose |

---

## 구현 개요

로컬에서 `docker compose up`으로 전체 스택(FastAPI + Astro + Vite admin + PostgreSQL + Caddy)을 한 번에 띄울 수 있게 구성. 단, 일상 개발은 컨테이너 외부 dev 서버를 쓰고 compose는 통합 검증용 (study [[docker-dev-workflow]]).

## 핵심 결정

- **개발 방식: 컨테이너 외부 dev 서버** - compose는 통합 확인용, 일상 개발은 `docker compose up postgres` + 로컬 dev 서버. Dockerfile은 프로덕션 빌드라 hot reload 없음.
- **admin 라우팅: 서브도메인 `admin.localhost`** - 스테이징/프로덕션 `admin.도메인` 구조와 동일 패턴 유지 (`/admin` 경로 방식 탈락).
- **이미지 구성**: backend는 `python:3.12-slim` + uv, frontend는 Astro Node standalone, admin은 nginx 정적 서빙 (멀티스테이지).

## 구현 내용

### 1. 서비스 구성 (compose.yml)

`postgres`, `api`, `frontend`, `admin`, `caddy` 5개 + healthcheck + depends_on(condition: service_healthy) 체이닝.

- DATABASE_URL은 compose `environment`에서 `postgres` 컨테이너 호스트명으로 오버라이드 (backend/.env의 localhost 값 위에 덮어씀)
- 포트는 `127.0.0.1`로만 바인딩 (보안, 아래 참조)

### 2. Caddy 로컬 라우팅 (Caddyfile)

- `localhost` → frontend:4321
- `admin.localhost` → admin:80 (`/etc/hosts`에 `127.0.0.1 admin.localhost` 필요)
- `api.localhost` → api:8000
- 로컬은 HTTP만. 자동 HTTPS는 D4 (VPS Caddy + Let's Encrypt)에서.

M2 G부터 `/`, `/commission`이 admin 편집 데이터를 SSR로 반영하므로 frontend 최종 이미지는 nginx가 아니라 `@astrojs/node` standalone 서버를 실행한다. frontend healthcheck는 API 의존 SSR 경로 대신 `/favicon.svg`를 확인해 Node 프로세스 readiness와 API 상태를 분리한다.

브라우저는 호스트에서 접근 가능한 `PUBLIC_API_URL`을 쓰고, frontend SSR Node는 compose DNS의 `API_INTERNAL_URL=http://api:8000`을 쓴다. 두 주소를 분리해 컨테이너 안의 `localhost`가 frontend 자신을 가리키는 오류를 막는다.

### 3. 코드리뷰(Opus) 반영 보안 수정

- postgres 5432 / api 8000 포트를 `127.0.0.1` 바인딩 (외부 노출 차단)
- backend Dockerfile uv를 `latest` → `0.11.17` 핀 (재현성 + 보안 패치)
- `backend/.dockerignore` 추가 (루트 .dockerignore가 ./backend 컨텍스트에 미적용되므로 별도)
- **VPS 배포 전 처리 필요 (Major)**: 포트 노출 차단 / DB 강한 비밀번호 / 컨테이너 비root → M0_foundation.md 그룹 D에 기록. 이 compose는 D4 선행이라 VPS에 그대로 올리면 안 됨.

### 4. 주요 트러블슈팅

- **pnpm 빌드 실패 (exit 1)**: 루트 package.json에 `packageManager` 필드 없어 corepack이 버전 못 정함 → Dockerfile에서 `npm install -g pnpm@10.24.0` 명시로 해결
- **alembic DATABASE_URL KeyError**: `migrations/env.py`가 `os.environ`로 직접 읽어 `.env` 미로딩 → `from config import settings`로 변경 ([BE] fix 커밋). 부작용: 마이그레이션도 전체 Settings() 필요.

---

## 관련 문서

- study: [[docker-dev-workflow]], [[pnpm-workspace]]
- 마일스톤: M0_foundation.md C1/C2, 그룹 D (VPS 배포 전 보안 처리)
- DECISIONS.md: "웹서버 Caddy", "VPS Hetzner"
