# M0. 프로젝트 기반 세팅 — 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.1 (2026-05-27) |
| 상위 마일스톤 | [M0](./README.md#m0-프로젝트-기반-세팅) |
| 예상 기간 | 1.5~2주 (DNS 전파 대기 포함) |
| 완료 기준 | 로컬 + 스테이징 + CI/CD + 백업 + 모니터링 모두 작동 (그룹 G 체크리스트) |
| 다음 마일스톤 | [M1](./README.md#m1-인증-이메일--구글) — 인증 |

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

- [ ] **A1. 도메인 등록** — Cloudflare 또는 가비아. 첫날 시작 (DNS 전파 24h).
- [ ] **A2. Hetzner VPS** — CX22 싱가포르, SSH 키 등록, 결제 카드 확인.
- [ ] **A3. Cloudflare R2** — 운영 버킷 + **백업 버킷** 2개, S3 호환 access key.
- [ ] **A4. Resend (SMTP)** — 발신 도메인 SPF/DKIM DNS 등록. **A1 직후, 첫날 시작** (DKIM 전파 24h).
- [ ] **A5. 토스페이먼츠 샌드박스** — 클라이언트/시크릿 키. 실 키 교체는 M7.
- [ ] **A6. 구글 OAuth Client ID** — 로컬 + 스테이징 리다이렉트 URI 양쪽 등록.
- [ ] **A7. Sentry / UptimeRobot 가입** — Sentry BE/FE 프로젝트 2개 DSN, UptimeRobot 가입까지 (모니터 등록은 E2).

---

## 그룹 B. 로컬 개발 환경 (병렬, T+0)

### B1. 백엔드 프로젝트 구조
- 선행: 없음
- 산출물: `backend/src/` (routers, services, models, lib), `pyproject.toml`, ruff 설정
- DoD: `uvicorn main:app` 실행 시 `GET /` 응답 200
- 결정 필요: Python 버전 (3.12 vs 3.13), 패키지 매니저 (uv vs poetry)

### B2. SQLModel + Alembic + asyncpg
- 선행: B1
- 산출물: `lib/db.py` (AsyncSession + get_session), `alembic/` 비동기 env, 최초 빈 마이그레이션
- DoD: 로컬 Postgres에 `alembic upgrade head` 성공
- 결정 필요: 테스트용 DB 방식 (testcontainers vs compose test profile)

### B3. Pydantic Settings + .env.example
- 선행: B1
- 산출물: `config.py` (`APP_BASE_URL`/`ADMIN_BASE_URL`에서 OAuth `REDIRECT_URI`, `CORS_ORIGINS` 조립 — DECISIONS "환경 베이스 URL"), `.env.example`
- DoD: `.env` 누락 시 명확한 에러, 정상 로딩 시 ASGI 기동
- 결정 필요: 환경별 분리 방식 (`.env.dev`/`.env.prod` vs 단일 + 환경변수 오버라이드)

### B4. structlog + Sentry BE
- 선행: B1, A7
- 산출물: `lib/logging.py` (JSON 구조화), Sentry SDK init
- DoD: 의도적 `ZeroDivisionError` → Sentry 수신 확인
- 결정 필요: 개인정보 마스킹 규칙 (이메일·IP 어디까지 가릴지)

### B5. pytest 골격
- 선행: B2
- 산출물: `tests/`, `conftest.py` (async DB 픽스처), 더미 테스트 1개
- DoD: `pytest` 실행 시 통과
- 결정 필요: B2와 같이 결정 (테스트 DB 방식)

### B6. Astro 독자용 프론트엔드
- 선행: 없음
- 산출물: `frontend/` (frontend/CLAUDE.md 구조), Tailwind, React 통합, `BaseLayout.astro`
- DoD: `astro dev` 실행 시 `/` 응답
- 결정 필요: Node 버전 (20 vs 22 LTS)

### B7. Vite React SPA 관리자
- 선행: 없음
- 산출물: `admin/`, Tailwind, 라우터
- DoD: `vite dev` 실행 시 `/` 응답
- 결정 필요: 라우터 (React Router vs TanStack Router)

### B8. 공통 api / zod 래퍼
- 선행: B6, B7
- 산출물: 각각 `lib/api.ts` (`credentials: 'include'` 기본), `lib/validation.ts` Zod 골격
- DoD: 더미 API 함수 + 타입 검증 통과
- 결정 필요: 양쪽 공유 방식 (monorepo workspace vs 복붙 vs 사설 패키지)

### B9. Sentry FE 양쪽
- 선행: B6, B7, A7
- 산출물: Sentry SDK init (Astro + Vite)
- DoD: 의도적 에러 → 양쪽 Sentry 프로젝트 수신

---

## 그룹 C. 로컬 통합 (Docker Compose)

### C1. compose.yml
- 선행: B1, B6, B7
- 산출물: `api`, `frontend`, `admin`, `postgres`, `caddy` 5개 서비스 + volumes + healthcheck
- DoD: `docker compose up` → 모든 컨테이너 healthy
- 결정 필요: 개발 hot reload 방식 (volume mount vs 컨테이너 외부 dev 서버)

### C2. Caddy 로컬 라우팅
- 선행: C1
- 산출물: `Caddyfile` (api → 8000, frontend → 4321, admin → 5173)
- DoD: localhost로 3개 서비스 라우팅 정상
- 결정 필요: 관리자 분리 방식 (서브도메인 `admin.localhost` vs 경로 `/admin`)

---

## 그룹 D. VPS 배포 기반

### D1. VPS 보안 기본
- 선행: A2
- 산출물: 방화벽 22/80/443만 개방, SSH 키 only(비번 차단), 비root 작업 사용자
- DoD: 외부에서 다른 포트 차단 확인, root SSH 거부 확인
- 결정 필요: fail2ban 설치 여부

### D2. DNS A 레코드
- 선행: A1, A2
- 산출물: 서비스 도메인 + 관리자 도메인 → VPS IP
- DoD: `dig` 결과 정상, 전파 확인
- 결정 필요: Cloudflare 프록시 사용 여부 (Caddy 자체 HTTPS와 충돌 주의 — Full(Strict) 모드면 OK)

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
- 산출물: `.github/workflows/ci.yml` — PR 시 ruff + pytest + biome/eslint + tsc
- DoD: PR 생성 시 5분 내 체크 통과
- 결정 필요: 변경된 영역만 실행 vs 전체 실행 (`paths` 필터 사용 여부)

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
- 산출물: 기존 영역별 PR 템플릿 + 이슈 템플릿 (이미 존재 — 실 PR 1건 생성으로 확인)
- DoD: PR 작성 시 영역 템플릿 자동 로드

---

## 그룹 G. M0 완료 검증

- [ ] 로컬 `docker compose up` → BE + FE + 관리자 + DB 모두 healthy
- [ ] 스테이징 HTTPS 정상 (3개 도메인)
- [ ] PR 푸시 시 CI 5분 내 통과
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
