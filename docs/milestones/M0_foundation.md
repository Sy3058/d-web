# M0. 프로젝트 기반 세팅 - 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.1 (2026-05-27) |
| 상위 마일스톤 | [M0](./README.md#m0-프로젝트-기반-세팅) |
| 예상 기간 | 1.5~2주 (DNS 전파 대기 포함) |
| 완료 기준 | 로컬 + 스테이징 + CI/CD + 백업 + 모니터링 모두 작동 (그룹 G 체크리스트) |
| 다음 마일스톤 | [M1](./README.md#m1-인증-이메일--구글) - 인증 |

---

## 의존성 다이어그램

```
[A] 외부 계정/키 ─┐
                  ├─→ [C] 로컬 통합 ─→ [D] VPS 배포 ─→ [E] 운영 자동화 ─→ [G] 검증
[B] 로컬 개발 환경┘                                  ↘ [F] CI/CD ↗
```

- A, B는 병렬 진행. A4(SMTP DKIM), A1(도메인 DNS)은 전파 대기가 있어 **첫날 시작 권장**.
- C는 A 일부(R2 외) + B 전부 의존.
- D, E, F는 C 완료 후 병렬 가능.

---

## 그룹 A. 외부 계정/키 발급 (병렬, T+0)

> 웹 콘솔 클릭 작업. 키는 안전한 곳(1Password 등)에 보관 후 `.env`에 적용.

- [ ] **A1. 도메인 등록** - Cloudflare 또는 가비아. 첫날 시작 (DNS 전파 24h). *(보류 - 그룹 D 전체를 나중으로 미룸)*
- [ ] **A2. Hetzner VPS** - CX22 싱가포르, SSH 키 등록, 결제 카드 확인. *(보류 - 그룹 D 전체를 나중으로 미룸)*
- [ ] **A3. Cloudflare R2** - 운영 버킷 + **백업 버킷** 2개, S3 호환 access key. *(보류 - E1이 D4에 의존하므로 그룹 D와 함께 보류)*
- [ ] **A4. Resend (SMTP)** - 발신 도메인 SPF/DKIM DNS 등록. **A1 직후, 첫날 시작** (DKIM 전파 24h).
- [ ] **A5. 토스페이먼츠 샌드박스** - 클라이언트/시크릿 키. 실 키 교체는 M7.
- [x] **A6. 구글 OAuth Client ID** - 로컬 리다이렉트 URI 등록 완료. 스테이징 URI는 도메인(A1)·그룹 D 보류와 함께 후속.
- [x] **A7. Sentry / UptimeRobot 가입** - Sentry BE/FE 프로젝트 2개 DSN, UptimeRobot 가입까지 (모니터 등록은 E2). *(B4/B9 연동 완료)*

---

## 그룹 B. 로컬 개발 환경 (병렬, T+0)

### B1. 백엔드 프로젝트 구조 ✅
- 선행: 없음
- 산출물: `backend/src/` (routers, services, models, lib), `pyproject.toml`, ruff 설정
- DoD: `uvicorn main:app` 실행 시 `GET /` 응답 200
- 결정: **Python 3.12 + uv** (DECISIONS "Python 버전" / "패키지 매니저")
- 메모: models/routers/services/lib 스켈레톤 골격이 작성되어 있으나 미커밋 상태로 git stash에 보관 중.
  M1 시작 전 아래 명령으로 복원할 것:
  ```bash
  git stash list  # "backend src skeleton (models/routers/services) - M1~M4 필요" 찾기
  git stash pop stash@{N}  # 해당 번호로 교체
  ```

### B2. SQLModel + Alembic + asyncpg ✅
- 선행: B1
- 산출물: `lib/db.py` (AsyncSession + get_session), `alembic/` 비동기 env, 최초 빈 마이그레이션
- DoD: 로컬 Postgres에 `alembic upgrade head` 성공
- 결정: **별도 테스트 DB (`TEST_DATABASE_URL`)** - `.env`에 `dweb_test` DB 정의, testcontainers/compose 추가 인프라 없이 가장 단순. CI에서는 GitHub Actions postgres 서비스로 대응.

### B3. Pydantic Settings + .env.example ✅
- 선행: B1
- 산출물: `config.py` (`APP_BASE_URL`/`ADMIN_BASE_URL`에서 OAuth `REDIRECT_URI`, `CORS_ORIGINS` 조립 - DECISIONS "환경 베이스 URL"), `.env.example`
- DoD: `.env` 누락 시 명확한 에러, 정상 로딩 시 ASGI 기동
- 결정: **단일 `.env` + 환경변수 오버라이드** - 로컬은 `.env` (gitignore), VPS는 서버에 `.env` 수동 1회 작성. CI/CD는 env 파일 관리 없이 SSH로 `docker compose pull && up -d`만 실행.

### B4. structlog + Sentry BE ✅
- 선행: B1, A7
- 산출물: `lib/logging.py` (JSON 구조화), Sentry SDK init
- DoD: 의도적 `ZeroDivisionError` → Sentry 수신 확인
- 결정 필요: 개인정보 마스킹 규칙 (이메일·IP 어디까지 가릴지)

### B5. pytest 골격 ✅
- 선행: B2
- 산출물: `tests/`, `conftest.py` (async DB 픽스처 + Sentry mock), `test_health.py` (GET / 더미 테스트)
- DoD: `pytest` 실행 시 통과
- 결정: **별도 테스트 DB** (B2와 동일 결정)

### B6. Astro 독자용 프론트엔드 ✅
- 선행: 없음
- 산출물: `frontend/` (`frontend/AGENTS.md` 구조), Tailwind, React 통합, `BaseLayout.astro`
- DoD: `astro dev` 실행 시 `/` 응답
- 결정: **Node 24 LTS** (DECISIONS "Node 버전")
- 후속 보강(deferred, 골격이라 미룸):
  - `lib/validation.ts`: `z.string().email(msg)` → zod v4 권장형 `z.email(msg)`로 교체 (M1 인증 폼 작업 시)
  - `lib/api.ts`: 에러 바디를 raw text가 아닌 FastAPI `{"detail": ...}` JSON 파싱 (에러 UI 붙일 때)
  - `frontend/.env.example` 추가 - 브라우저 `PUBLIC_API_URL`과 SSR `API_INTERNAL_URL` 분리 문서화

### B7. Vite React SPA 관리자 ✅
- 선행: 없음
- 산출물: `admin/`, Tailwind v4 (`@tailwindcss/vite`), TanStack Router (파일 기반 `routes/`)
- DoD: `vite dev` 실행 시 `/` 응답 (확인: 200)
- 결정: **TanStack Router** (DECISIONS "관리자 라우터")
- 메모:
  - 파일 기반 라우팅(`@tanstack/router-plugin`) 채택 → `routeTree.gen.ts` 자동 생성. `tsc -b`가 빌드 스크립트 선두라 생성 파일이 없으면 CI tsc 실패 → **`routeTree.gen.ts`를 커밋**해 chicken-egg 회피 (`@ts-nocheck` 헤더라 lint/tsc 안전)
  - TanStack Query / react-hook-form은 M1.5 기능 작업 시 추가 (B7 골격 범위 외)

### B8. 공통 api / zod 래퍼 ✅
- 선행: B6, B7
- 산출물: `packages/shared/`에 `lib/api.ts` (`credentials: 'include'` 기본) + `lib/validation.ts` Zod 골격, frontend/admin에서 import
- DoD: 더미 API 함수 + 타입 검증 통과, 양쪽 빌드 성공
- 결정: **pnpm workspace + `packages/shared`** (DECISIONS "FE/Admin 공유 코드")
- 메모:
  - Astro 6는 Vite 7을 사용하므로 workspace 전체를 Vite 7로 통일 (admin도 vite@^7, @vitejs/plugin-react@^5)
  - `@tailwindcss/vite@4.3.0`이 Vite 8 바인딩에서 tsconfigPaths 필드를 요구하는 버그 있음 - Vite 7로 고정해 회피
  - Astro 7은 Vite 8 기반으로 출시됐지만 현재는 Astro 6/Vite 7 유지. 별도 migration 착수 시 frontend(astro@7), admin(vite@8 + @vitejs/plugin-react@6), frontend의 Vite 고정과 호환성을 함께 검증

### B9. Sentry FE 양쪽 ✅
- 선행: B6, B7, A7
- 산출물: Sentry SDK init (Astro + Vite)
- DoD: 의도적 에러 -> 양쪽 Sentry 프로젝트 수신
- 결정: Sentry 프로젝트 1개(BE/FE 공용 DSN). 프로젝트 분리는 트래픽 증가 후 검토.
- 메모:
  - frontend: `@sentry/astro` + `sentry.client.config.ts` / `sentry.server.config.ts`
  - admin: `@sentry/react`, `Sentry.init()`을 `main.tsx` render 전에 호출
  - DSN 미설정 시 init skip (guard 처리) - 빈 env로도 앱 정상 기동
  - Vite 빌드 시 `[sentry-vite-plugin] No auth token` 경고는 정상 (소스맵 업로드 미설정). CI/CD(F2) 때 `SENTRY_AUTH_TOKEN` 추가로 해결

---

## 그룹 C. 로컬 통합 (Docker Compose)

### C1. compose.yml ✅
- 선행: B1, B6, B7
- 산출물: `api`, `frontend`, `admin`, `postgres`, `caddy` 5개 서비스 + volumes + healthcheck
- DoD: `docker compose up` → 모든 컨테이너 healthy
- 결정: **컨테이너 외부 dev 서버** - 일상 개발 시 `docker compose up postgres`만 띄우고 api/frontend/admin은 로컬에서 각각 실행. `docker compose up`은 전체 스택 통합 확인 용도.
- 메모:
  - backend Dockerfile: `python:3.12-slim` + uv, `src.main:app` 모듈 경로
  - frontend Dockerfile: 멀티스테이지 빌드 (Node 24 pnpm build → Astro Node standalone, M2 G에서 SSR 런타임으로 전환)
  - admin Dockerfile: 동일 패턴 (Vite SPA → nginx:alpine, try_files /index.html)
  - compose 내 DATABASE_URL은 `postgres` 컨테이너 호스트명으로 오버라이드 (backend/.env의 localhost 값을 덮어씀)
  - Astro SSR 페이지(M1 이후) 추가 시 `@astrojs/node` 어댑터 + Dockerfile Node 서버 방식으로 전환 필요

### C2. Caddy 로컬 라우팅 ✅
- 선행: C1
- 산출물: `Caddyfile` (api → api:8000, frontend → frontend:4321, admin.localhost → admin:80)
- DoD: localhost로 3개 서비스 라우팅 정상
- 결정: **서브도메인 `admin.localhost`** - 스테이징/프로덕션 구조(admin.도메인)와 동일 패턴 유지
- 메모:
  - `admin.localhost`는 Linux/WSL2에서 `/etc/hosts`에 `127.0.0.1 admin.localhost` 추가 필요
  - 로컬 HTTP만 사용 (HTTPS는 D4 - VPS Caddy + Let's Encrypt 에서 처리)
  - api는 localhost:8000 직접 접근 가능 (ports 노출), `api.localhost`는 Caddy 통한 편의 접근

---

## 그룹 D. VPS 배포 기반 *(전체 보류 - 나중으로 미룸)*

> 그룹 C까지 완료 후 CI/CD(F), 인증(M1) 등 개발을 먼저 진행. VPS 배포는 개발이 충분히 진행된 후 시작.
> A1(도메인), A2(VPS), A3(R2)도 이 그룹과 함께 보류.

> **⚠️ VPS 배포 전 필수 보안 처리 (C1/C2 compose 재사용 시)**
> 현재 `compose.yml`은 로컬 전용으로 안전하게 설정돼 있으나(포트 127.0.0.1 바인딩),
> 이 파일을 VPS에 그대로 올리면 안 됨. C1/C2 코드리뷰(Opus, 2026-05-31)에서 나온 Major 3건:
>
> 1. **DB/API 포트 노출 차단**: `postgres:5432`, `api:8000`을 VPS 공인 인터페이스에 노출 금지.
>    프로덕션 compose에서는 `ports` 매핑 제거(컨테이너 네트워크 내부 통신만) 또는 Caddy 경유만 허용.
>    외부 접근은 Caddy(80/443)로만. 로컬은 `127.0.0.1` 바인딩으로 이미 처리됨.
> 2. **POSTGRES_PASSWORD 강한 값 필수**: 현재 `${POSTGRES_PASSWORD:-postgres}` 기본값 의존.
>    프로덕션은 `.env`에 강한 랜덤 비밀번호 명시, 기본값 fallback에 의존 금지.
> 3. **컨테이너 비root 실행**: `backend/Dockerfile`에 `USER` 지시어 없어 root로 uvicorn 실행 중.
>    결제/JWT 다루는 API에 RCE 발생 시 컨테이너 root 탈취. 비root 사용자 추가 후 `USER appuser`.
>
> 추가 권장(Nit, 여유 시): admin nginx 보안 헤더(X-Frame-Options 등)는 D4 프로덕션 Caddy에서 일괄 주입 검토.

### D1. VPS 보안 기본
- 선행: A2
- 산출물: 방화벽 22/80/443만 개방, SSH 키 only(비번 차단), 비root 작업 사용자
- DoD: 외부에서 다른 포트 차단 확인, root SSH 거부 확인
- 결정 필요: fail2ban 설치 여부

### D2. DNS A 레코드
- 선행: A1, A2
- 산출물: 서비스 도메인 + 관리자 도메인 → VPS IP
- DoD: `dig` 결과 정상, 전파 확인
- 결정 필요: Cloudflare 프록시 사용 여부 (Caddy 자체 HTTPS와 충돌 주의 - Full(Strict) 모드면 OK)

### D3. VPS Docker 환경
- 선행: D1
- 산출물: Docker, Docker Compose, 컨테이너 레지스트리 로그인
- DoD: `docker pull` 동작
- 결정 필요: 레지스트리 (GHCR vs Docker Hub)

### D4. Caddy + Let's Encrypt 검증
- 선행: D2, D3, C1, C2
- 산출물: 스테이징 도메인 HTTPS 정상 응답
- DoD: 브라우저 접속 시 유효 인증서 (만료 30일 이상)

### D5. R2 커스텀 도메인 연결
- 선행: A3, A1
- 산출물: `cdn.도메인` → R2 버킷
- DoD: 더미 이미지 PUT 후 `https://cdn.도메인/...`로 GET 성공

---

## 그룹 E. 운영 자동화

### E1. PostgreSQL 일 1회 R2 백업 (Q18)
- 선행: D4, A3
- 산출물: `pg_dump` → R2 업로드 스크립트, cron 등록, **30일 retention**
- DoD: 수동 실행 1회 → R2 백업 버킷에 dump 존재, 30일 자동 삭제 룰 확인
- 결정 필요: 백업 암호화 (GPG vs R2 접근 제한만)

### E2. UptimeRobot 모니터 등록
- 선행: D4, A7
- 산출물: HTTPS 모니터 5분 간격, 알림 이메일 + 카카오톡
- DoD: 의도적 컨테이너 중단 → 5분 내 알림 수신
- 결정 필요: 카카오톡 알림 경로 (UptimeRobot 자체 통합 vs 별도 봇)

---

## 그룹 F. CI/CD

### F1. lint + test 워크플로우
- 선행: B1, B5, B6, B7
- 산출물: `.github/workflows/ci.yml` - PR 시 ruff + pytest + eslint + tsc
- DoD: PR 생성 시 5분 내 체크 통과
- 결정 (2026-06-22): `paths` 필터 **미적용** - required check면 path-skip이 pending으로 머지를 막고, 1인 저PR 볼륨이라 분 절약 한계효용 낮음.
- 메모: 린트는 ESLint로 통일(biome 미채택, DECISIONS "린트/포맷"). frontend도 2026-08-18에 `eslint-plugin-astro` 기반 ESLint 10 flat config를 도입했다.
- **부분 구현 (백엔드분, 2026-06-22, PR `common/ci/backend-ci`)**: `.github/workflows/ci.yml` 백엔드 job = `postgres:16` 서비스 + `uv sync --locked` + `ruff check src/` + `ruff format --check src/ tests/` + `pytest`(81). 범위는 be.md 게이트와 일치(migrations 제외). 상세 결정은 DECISIONS "CI/CD 결정". **FE/admin(eslint+tsc)은 frontend ESLint 셋업 선행 → 후속.** ⚠️ branch protection에 `backend` required check 등록이 게이트 효력의 전제(GHA 그린 확인 후 P0). 그린 확인 후 그룹 G "PR 푸시 시 CI 통과" 마킹.
- **부분 구현 (프론트엔드분, 2026-07-23, PR `common/chore/frontend-ci`)**: frontend job = `pnpm/action-setup@v6`(pnpm 10, setup-node보다 선행 - cache가 pnpm 요구) + `setup-node@v7`(Node 24, cache: pnpm) + `pnpm install --frozen-lockfile` + `astro check` + `build` + `vitest run`(12). Sentry는 auth token 미설정 시 경고만(소스맵 업로드 skip, 실측).
- **부분 구현 (admin분, 2026-07-23, 동일 PR `common/chore/frontend-ci`)**: admin job = frontend job과 동일 셋업 + `eslint .` + `tsc -b && vite build` + `vitest run`(54). admin은 ESLint 기설정이라 "FE/admin 후속" 중 admin은 선행 조건이 없었음을 확인하고 편입. `.env` 제거 상태 build·test 그린 실측.
- **frontend ESLint 구현 (2026-08-18)**: ESLint 10 flat config에 JS/TS/Astro recommended와 React Hooks recommended를 적용하고 `.astro`가 포함된 명시적 lint script를 추가했다. frontend CI는 lint를 astro check 앞에서 실행한다. 로컬 전체 gate와 frozen lockfile 설치는 통과했으며 PR의 실제 Actions 통과 확인은 아직 남았다. type-aware lint, Prettier, JSX a11y, import/style 규칙은 제외했다. 상세는 `docs/MODULES/FE/Scaffold/IMPLEMENTATION_FRONTEND_ESLINT.md`.
- **F1 완료 (2026-08-19)**: PR #123에서 backend, frontend, admin 세 job이 모두 성공했다. frontend ESLint의 실제 Actions 통과까지 확인했으므로 위 "부분 구현"과 "확인 대기" 문구는 도입 이력으로만 남긴다.

### F2. build + push 워크플로우
- 선행: F1, D3
- 산출물: main 머지 시 BE/FE/관리자 이미지 빌드 + 레지스트리 푸시
- DoD: 머지 후 레지스트리에 새 태그 확인

### F3. 스테이징 자동 배포
- 선행: F2, D4
- 산출물: VPS SSH로 `docker compose pull && up -d` (예: `appleboy/ssh-action`)
- DoD: main 머지 → 스테이징 변경 자동 반영
- 결정 필요: 무중단 배포 (rolling vs 짧은 down 허용)

### F4. PR / 이슈 템플릿 동작 확인
- 선행: 없음
- 산출물: 기존 영역별 PR 템플릿 + 이슈 템플릿 (이미 존재 - 실 PR 1건 생성으로 확인)
- DoD: PR 작성 시 영역 템플릿 자동 로드

---

## 그룹 G. M0 완료 검증

- [ ] 로컬 `docker compose up` → BE + FE + 관리자 + DB 모두 healthy
- [ ] 스테이징 HTTPS 정상 (3개 도메인)
- [x] PR 푸시 시 CI 5분 내 통과 (PR #123, backend/frontend/admin 성공)
- [ ] main 머지 시 스테이징 자동 반영
- [ ] R2 백업 버킷에 dump 파일 존재 (수동 1회)
- [ ] Sentry BE/FE 의도적 에러 수신 확인
- [ ] UptimeRobot 의도적 다운 알림 수신 확인

---

## 외부 의존 / 일정 리스크

| 항목 | 리스크 | 완화 |
|------|--------|------|
| SMTP DKIM DNS 전파 | 최대 24h | A4 첫날 시작 |
| 도메인 DNS 전파 | 최대 24h | A1 첫날 시작 |
| 토스페이먼츠 가맹점 심사 | 1~2주 (실 키) | 샌드박스로 M0~M6 진행, M7에서 심사 |
| 카카오 비즈앱 사업자 서류 | M1.5 시점 필요 | 사업자 등록 진행 (M0 외 트랙) |
| Hetzner 해외 카드 결제 거절 | 즉시 | 결제 가능 카드 사전 확인 |

---

## 메모

- 그룹 A의 키들은 그룹 B 작업 중 `.env.example`에 자리만 잡아두고, 실제 값은 발급되는 대로 채움.
- 그룹 D~F의 작업은 스테이징 환경 기준. **프로덕션 분리는 M7에서** (도메인·DB 인스턴스·SMTP 발신 도메인 모두 별도).
- 결정 필요 항목은 해당 작업 직전 별도 PR/이슈로 짧게 합의 후 진행.
