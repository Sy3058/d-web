# 마일스톤 로드맵

| 항목 | 내용 |
|------|------|
| 문서 버전 | v1.1 (2026-07-03, 결제 최후순위 재배치 + PG 포트원 확정 + 문서 모순 정정) · v1.0 (2026-05-27) |
| 대상 | MVP(P0) 4개월 + P1 8주 + P2 시장 검증 후 |
| 우선순위 정의 | P0 = 런칭 차단 / P1 = 런칭 후 8주 / P2 = 안정화 후 |
| 관련 문서 | [PRD.md](../PRD.md), [DECISIONS.md](../DECISIONS.md), [DB_SCHEMA.md](../DB_SCHEMA.md) |

---

## 의존성 다이어그램

```
M0 (기반)
  ↓
M1 (인증)
  ↓
M1.5 (관리자 부트스트랩: 로그인+2FA, 작품/에피소드 업로드 골격)
  ↓
M2 (콘텐츠/뷰어 - 무료 구간)
  ↓
M4 (커뮤니티 - 후원 제외)
  ↓
  ├── M5 (관리자 운영 도구 - 매출/환불 제외) ──┐
  └── M6 (알림) ─────────────────────────────┤
                                             ↓
                          M3 (결제 + 유료 잠금 + 후원 + 매출/환불 도구)
                                             ↓
                          M7 (출시 검증 + 베타)
```

> **결제 최후순위 결정 (2026-07-03)**
> 결제 없이 완결되는 사이트(무료 열람 + 커뮤니티 + 관리자 + 알림)를 먼저 만들고, 결제(M3)를 M7 직전 마지막에 붙인다.
> - 이유: (a) **사업자 등록이 필요한 항목(포트원 실키 가맹점 심사·카카오 비즈앱·통신판매업 신고)을 전부 출시 직전으로 지연** - 포트원은 사업자 없이 가입 즉시 테스트 채널로 연동 개발 가능하므로 M3 개발 자체도 사업자 불필요. (b) 법무(약관·청약철회, Q1/Q7)와 결제 화면이 M7 직전에 붙어 자연 연계. (c) 결제와 무관한 기능이 결제 일정에 블로킹되지 않음.
> - 동반 이동: 후원(M4→M3), 수익·환불·후원 운영 도구(M5→M3).
> - **마일스톤 번호는 재부여하지 않음** - M3~M6은 식별자로 유지(DECISIONS·세부 문서의 상호 참조 보존). 실행 순서는 이 다이어그램이 기준.

> **의존 메모**
> - M2 진입 전 M1.5에서 작품/에피소드 업로드가 최소한 작동해야 시드 데이터로 뷰어를 만들 수 있음
> - M4는 M2 뒤 바로 진행(결제 무관 - 후원만 M3로 이동). M5와 M6은 M4 뒤 병렬 가능
> - M6 알림 트리거 중 "새 에피소드"는 M1.5 공개 전환(E1), "댓글 답글"·"새 게시글"은 M4 이벤트
> - **외부 블로커 (마일스톤 외부 일정)**: 도메인 등록, SMTP 발신 도메인 인증(SPF/DKIM). 사업자 등록이 필요한 항목(포트원 실키·카카오 비즈앱·통신판매업 신고)은 전부 M3~M7로 지연 - 포트원 테스트 채널 키는 사업자 없이 즉시 발급 가능

---

## M0. 프로젝트 기반 세팅

> **목적**: 인프라 + 개발 환경 + 외부 서비스 키. 이후 모든 마일스톤의 전제 조건.
> **DoD**: 로컬에서 `docker compose up`으로 FastAPI + Postgres가 뜨고, 푸시 시 CI가 lint/test를 돌리며, 스테이징 도메인이 HTTPS로 응답.

### 인프라
- [ ] 서비스 도메인 등록 + DNS A/AAAA 레코드 (Cloudflare)
- [ ] Hetzner VPS 초기화 + SSH 키 + 방화벽 (22/80/443만 개방)
- [x] Docker Compose 구성 (FastAPI + PostgreSQL + Caddy) (C1, 로컬 검증 완료)
- [ ] Caddy 리버스 프록시 + 자동 HTTPS 동작 확인 (로컬 라우팅은 C2 완료, 자동 HTTPS는 D4에서 / 그룹 D 보류)
- [ ] Cloudflare R2 버킷 생성 + 액세스 키 + 커스텀 도메인 연결 (버킷 `dweb`+Object R/W 키 완료 2026-07-10, 실버킷 스모크 검증. **커스텀 도메인만 미연결** - 서빙 시점(M2~M3)까지 미룰 수 있음)
  - ⚠️ **커스텀 도메인은 `dweb`에 붙이지 말 것** (2026-07-15 결정). R2의 공개 설정은 버킷 단위라 `dweb`을 공개하면 같은 버킷의 미공개·유료 원고까지 서명 없이 받아진다. 표지 서빙은 **표지 전용 공개 버킷**을 새로 만들어 거기에 도메인을 붙인다 (DECISIONS "표지 서빙"). 원고는 비공개 유지 + presigned URL(M3).
- [ ] PostgreSQL **일 1회 풀 덤프 → R2 30일 보관** 스크립트 + cron 등록 (Q18)

### 백엔드 기반
- [x] FastAPI 프로젝트 구조 잡기 (routers/services/models/lib)
- [x] SQLModel + Alembic + asyncpg 세팅
- [x] Pydantic Settings로 `.env` 로딩 + 베이스 URL에서 OAuth/CORS 조립 (DECISIONS "환경 베이스 URL")
- [x] structlog JSON 로깅
- [x] Sentry 백엔드 연결
- [x] pytest 기본 골격 + DB 픽스처

### 프론트엔드 기반
- [x] Astro 프로젝트 생성 + React 통합 + Tailwind
- [x] Vite React SPA 프로젝트 생성 (관리자) + Tailwind
- [x] Sentry 프론트엔드 연결 (양쪽)
- [x] 공통 API 래핑(lib/api.ts) + Zod 검증 스키마 골격

### 외부 서비스 연결
- [ ] **SMTP 외부 메일 서비스** 가입 + 발신 도메인 SPF/DKIM 인증 (Resend 또는 SendGrid 무료 플랜)
- [ ] **포트원 테스트 채널** 키 발급 (Q4 정정 2026-07-03: 처음부터 포트원 확정, 토스 샌드박스 경유 폐기. 사업자 불필요 - M3 착수 전까지만 준비하면 됨)
- [x] 구글 OAuth Client ID 발급 (로컬 리다이렉트 URI 등록 완료, 스테이징 URI는 도메인(A1) 후)
- [ ] UptimeRobot 모니터 등록 (5분 간격)

### CI/CD
- [ ] GitHub Actions: lint(ruff + eslint) + test + build - **백엔드분 구현**(ruff+pytest+Postgres, PR `common/ci/backend-ci`; DECISIONS "CI/CD 결정") + **프론트엔드분 구현**(astro check+build+vitest, 2026-07-23, PR `common/chore/frontend-ci`). eslint(FE/admin)·admin job·CD는 후속
- [ ] main 머지 시 스테이징 자동 배포 (docker pull → compose up)
- [ ] PR 템플릿/이슈 템플릿 동작 확인

---

## M1. 인증 (이메일 + 구글)

> **목적**: 가입/로그인/세션 + 이메일 인증. **카카오 OAuth는 M1.5에서 별도 진행** (Q20 결정: 비즈앱 사업자 서류 필요).
> **선행**: M0
> **DoD**: 신규 유저가 이메일 또는 구글로 가입 → 인증 메일 수신 → 로그인 상태로 마이페이지 진입까지 완주.

### 백엔드
- [x] `users` + `oauth_accounts` + `refresh_tokens` + `email_verifications` 모델 + 마이그레이션 (그룹 A, UUID PK, 로컬 DB 검증 완료)
- [x] bcrypt(cost=12) 비밀번호 해싱 (B1, OWASP pre-hash + pepper, 단위 테스트 통과)
- [x] JWT 발급/검증 (Access 15분 / Refresh 7일) (B2, PyJWT, 단위 테스트 통과)
- [x] HttpOnly + Secure + SameSite=Lax 쿠키 발급 (refresh는 SameSite=Strict) (B3, `__Host-` 프리픽스/Path 제한, 단위 테스트 통과)
- [x] 회원가입 / 로그인 / 로그아웃 / 토큰 갱신 엔드포인트 (그룹 C + `/auth/me`, 비열거·HIBP·회전, 구현+Opus 리뷰 완료, DB 통합 테스트 그린)
- [x] 구글 OAuth2 콜백 처리 (D1, BFF 백엔드 수신, 신규 시 user+oauth_accounts 단일 트랜잭션, id_token google-auth 검증, 통합 테스트 8개)
- [x] 이메일 인증 메일 발송 (1시간 토큰) + 검증 엔드포인트 (E1 Resend 발송 / E2 POST 검증·`uq_email_verifications_token`, 통합 테스트 통과)
- [x] **미인증 차단 의존성 + 인증 메일 재발송** (E3): `require_verified_email` 가드(함수+단위테스트) + `POST /auth/resend-verification`(비열거 재발송, 직전 토큰 무효화) - 가드 실제 부착은 M3/M4
- [x] Rate limiting IP 5회/분 (I2: login/signup/resend, limits 기반·`test_rate_limit`) - 계정 lockout은 council 2026-06-14 보류, 대신 로그인 관측 로그(`auth.login`)
- [x] 동일 이메일 소셜 별도 계정 (Q6): 백엔드 `email_exists` 거부(자동 병합 금지) 완료 - 사용자 메시지 표시는 G3(프론트)
- [x] **council 리뷰 fix (선존 이슈, #28)** - ~~refresh 회전 race 원자화 🔴 (I1 ✅)~~ → ~~인증 표면 rate limit IP (I2 ✅)~~ → ~~CORS(I3) ✅~~ → ~~죽은 테스트 픽스처 + 회전 실측 동시성 테스트(I4) ✅~~. 상세는 M1_foundation.md 그룹 I

### 프론트엔드 (Astro + React 아일랜드)
- [x] 회원가입 / 로그인 페이지 (이메일 + 구글 버튼) (G1/G2, RHF+Zod, 구글 버튼은 백엔드 login-init 링크)
- [x] 구글 로그인 실패 표시 (G3, BFF - 프론트 콜백 페이지 없음, `login.astro`가 `?error=` 표시)
- [x] 이메일 인증 안내 페이지 + 재발송 버튼 (G4, `verify-email.astro` + VerifyEmail 아일랜드, 429 표시)
- [x] 마이페이지 골격 (G5, SSR, `/auth/me`로 로그인 판정·미로그인 리다이렉트. 구매 목록 M3·알림 M6은 placeholder)

> 프론트 인증 UI(그룹 G)는 **#38로 main 머지 완료(`v0.1.0` 포함). 사후 Opus 리뷰 완료(2026-06-28, Critical/Major 0)** - BE 그룹과 동일하게 구현+Opus 리뷰 완료.
> ✅ 네비 로그인 깜빡임 **해소**(2026-06-21): 비-HttpOnly `login_hint` 힌트 쿠키(BE #39) + 네비 라벨을 pre-paint `is:inline` 스크립트로 전환(React 섬 `NavUser.tsx` 제거)해 0프레임 달성. 상세 DECISIONS "네비 로그인 표시".

> ⚠️ JWT는 HttpOnly 쿠키만 사용. localStorage 저장 절대 금지.
> ⚠️ Astro `SECRET_*` 환경변수는 빌드 타임 HTML에 노출되므로 클라이언트 코드에서 참조 금지.

### M1에서 의도적으로 제외 (후속 마일스톤에서 진행)
- 카카오 OAuth → 사업자 등록 후(M3~M7 시기 - 등록 자체를 최대한 지연, Q20. 2026-07-03 결제 최후순위 결정)
- 비밀번호 재설정 (AUTH-05, P1) → P1 사이클
- 회원 탈퇴 (AUTH-07, P1) → P1 사이클
- 알림 설정 UI → M6

---

## M1.5. 관리자 부트스트랩

> **목적**: M2 콘텐츠 마일스톤이 시작되려면 작품/에피소드 데이터를 입력할 수단이 필요. 관리자 로그인(P0)과 업로드 최소 골격을 먼저 깐다.
> **선행**: M1
> **DoD**: 관리자가 2FA로 로그인 → 작품 등록 → 에피소드 이미지 업로드(50장, WebP 변환) → 회차 공개까지 작동.

### 백엔드
- [x] **`users.role`(VARCHAR, reader/owner/moderator) RBAC** + `require_role`/`require_owner` 가드 (authz=DB user.role, JWT 미포함; **M1.5는 owner만 빌드** - moderator=M4; DECISIONS "관리자 권한 분리") *(B1 완료: role 모델 + `is_admin`→owner 이관 마이그레이션. B3 완료: `require_role`/`require_owner` + owner-TOTP 보조 규칙 - B2·B3 한 PR #58)*
- [x] TOTP 시크릿 발급 + 검증 (이메일·비번 → TOTP → JWT 순서; **owner 필수**; 시크릿 Fernet 암호화 at-rest, DECISIONS "2FA"·"관리자 권한 분리") *(B1 완료: Fernet at-rest 저장 + 컬럼 + 부트스트랩 스크립트. B2 완료: `/admin/2fa/setup`·`/admin/2fa/confirm`. B3 완료: 2단계 로그인 `/admin/login`·`/admin/login/totp` + owner 발급 지점 봉쇄 + 신뢰 기기 30일 - B2·B3 한 PR #58)*
  - 백업 코드는 1차 구현 제외, 시크릿 분실 시 DB 직접 조작 복구
  - 부트스트랩: `scripts/promote_admin.py`로 owner 승격 (공개 관리자 가입 없음; moderator는 M4에서 owner가 부여)
- [x] `works` + `tags` + `works_tags` + `episodes` 모델 + 마이그레이션 (#51, schemas 요청/응답 분리·로컬 DB 검증 완료; `bundle_discount_rate` 컬럼 포함/적용 M3, `idx_tags_name`은 name UNIQUE로 대체)
- [x] 작품 등록/수정 API (`require_owner` 필수) *(C1 완료 2026-07-09: DELETE(soft) 포함 5개 엔드포인트 + 태그 get-or-create, #60)*
- [x] **R2 업로드 = 백엔드 경유 변환** (클라→백엔드 multipart→Pillow 800px WebP→R2; presigned PUT 미사용, M1.5_foundation 결정 1) (회차당 최대 50장) *(D1 #62 + D3 #64 머지 - 장당 업로드 구조 A)*
- [x] **이미지 가로 800px WebP 자동 변환** (Q23 확정: 1차 동기 `anyio.to_thread`, 실측 초과 시 Arq+Redis 분리 - 결정 2) *(D2 #62 머지)*
- [x] 에피소드 페이지 순서 저장 (`image_keys` JSONB) *(D3 #64 머지 - 배열 순서=표시 순서, 재배열 PUT)*
- [x] 에피소드 공개 예약 (APScheduler in-process 폴링 잡 + 원자 UPDATE, `published_at` 도달 시 `is_published=true`) *(E1 #65 머지 + #57 토큰 cleanup 잡 close)*

### 프론트엔드 (Vite React SPA)
- [x] 관리자 로그인 화면 (TOTP 입력 단계 + role 가드: `/auth/me` role≠owner이면 차단; M1.5 관리자 화면은 owner 전용) *(F1 완료 2026-07-14: stage 상태머신 + QR 등록 + pathless 레이아웃 가드 `_auth.tsx`, admin 최초 vitest 18개)*
- [x] 작품 목록 / 등록 / 수정 화면 *(F2 완료 2026-07-15: 카드형 목록·RHF/Zod 폼·표지 3:4 크롭·태그 입력, #73)*
- [x] 에피소드 에디터 (TipTap 본문·상시 유료 경계·발행하기 모달·이미지 드래그앤드롭·임시저장) *(F3 완료 2026-07-16, #78 - 업로드 폼에서 포스타입식 에디터로 재정의, DECISIONS "에피소드 콘텐츠 모델")*
- [x] 에피소드 공개 예약 UI *(F4 완료 2026-07-17: 발행 모달 지금/예약 토글 + `datetime-local`, #79)*

> ⚠️ TOTP 시크릿은 DB 저장 + 클라이언트 절대 노출 금지.
> ⚠️ 비권한(일반 유저·role 미달) 관리자 API 호출 시 403, 라우터 단 `require_role` 일관 적용 점검.
> ⚠️ **개발자 매출 차단은 product 역할이 아님**: 개발자는 product 역할로 만들지 않는다(관측은 외부 도구 Sentry 등). "개발자가 매출을 못 본다"는 라우트 가드가 아니라 인프라/자격증명 소유권 - 진짜 장벽은 M7 인프라 분리 시(DECISIONS "관리자 권한 분리").

---

## M2. 콘텐츠 (무료 구간)

> **목적**: 작품 목록 → 에피소드 목록 → 뷰어 3단계 + 무료 회차 정책.
> **선행**: M1.5 (시드 데이터 입력 가능 상태)
> **DoD**: 비로그인 유저가 작품 목록 → 무료 1~N화 끝까지 스크롤. 4화(유료) 진입 시 잠금 UI(M3 작업 전이라 placeholder)까지 노출.
> **세부**: [M2_foundation.md](./M2_foundation.md) - 그룹 A~H 분해 + 설계 결정 5개(무료 presigned·dweb-cover·SSR 등, 2026-07-15)

### 백엔드
- [x] 작품 목록 API (페이지네이션, 태그 필터) *(그룹 A 완료 2026-07-18: `works.is_published` 게이트 신설 + 공개 회차 카운트. IMPLEMENTATION_PUBLIC_CATALOG_API.md)*
- [x] 작품 상세 API (works + tags + 공개 episodes 요약, `selectinload` 사용) *(그룹 A 완료 2026-07-18: 썸네일 URL은 D2까지 null - 원고 키 노출 차단)*
- [x] 에피소드 목록 API (회차 번호·제목·부제목·썸네일·무료/잠금/구매상태) *(그룹 B1 완료 2026-07-21: `GET /works/{id}/episodes` - A2와 같은 서비스 함수 재사용)*
- [x] **무료 구간 콘텐츠 API** (#76 콘텐츠 모델: content를 paywall 경계에서 **서버 절단** + image 키 presigned URL 치환, no-store. 절단은 M3→M2 앞당김 2026-07-16 - 경계 뒤 반환·결제 검증만 M3) *(그룹 B2 완료 2026-07-21: 절단은 `is_free`와 무관하게 항상 수행, 절단→presign 순서 고정. IMPLEMENTATION_FREE_CONTENT_API.md)*
- [x] `viewer_progress` 모델 + 진행도 저장 API (블록 인덱스 기준 - #76 재해석, WORK-09) *(그룹 C1 완료 2026-07-20: PUT/GET /episodes/{id}/progress, upsert. IMPLEMENTATION_VIEWER_PROGRESS.md)*
- [ ] 작가 소개는 Astro 마크다운 확정(백엔드 API 없음 - M2_foundation 결정 4)

### 프론트엔드 (Astro)
- [x] 작품 목록 페이지 (SSR `prerender=false` + 짧은 Cache-Control - M2_foundation 결정 3) *(그룹 E1 완료 2026-07-22: 태그 필터·페이지네이션·표지 onerror 폴백. IMPLEMENTATION_CATALOG_PAGES.md)*
- [x] 작품 상세 + 에피소드 목록 페이지 (SSR) *(그룹 E2 완료 2026-07-22: 무료/잠금 배지·회차 링크(F1 라우트 선점). /code-review xhigh 반영)*
- [ ] **뷰어 - 콘텐츠 문서 렌더러** (React 아일랜드, `@tiptap/core generateHTML`)
  - 글+이미지 혼합 렌더, **이미지 즉시 전량 요청 + `fetchpriority`**(lazy 아님 - M2_foundation 결정 6), 이전/다음 화 이동, 경계 지점 잠금 placeholder
  - 드래그/복사/우클릭/저장 차단 (UX 우선, 완벽 차단 아님)
  - 진행도 저장 (블록 인덱스, debounce)
  - 본문은 no-store API로 아일랜드가 fetch (SSR HTML에 presigned 금지)
- [ ] 작가 소개 페이지 (정적)

### M2에서 의도적으로 제외
- 작품 검색 (WORK-11, P2)
- 유료 구간(경계 뒤) 반환 + 결제 검증 → M3 (절단 자체는 M2)

---

## M4. 커뮤니티 (후원은 M3로 이동)

> **목적**: 하트 + 댓글 + 작가 게시판(근황). 후원은 결제와 함께 **M3**(결제 최후순위 재배치).
> **선행**: M2 (결제 무관 - 2026-07-03 재배치로 M3 선행 해제)
> **DoD**: 인증된 유저가 에피소드/게시글에 하트·댓글·답글 작성. 작가 답글은 배지 표시. 신고 5회 누적 시 자동 숨김.

### 백엔드
- [ ] `comments` + `likes` + `reports` + `posts` + `polls` + `poll_options` + `poll_votes` 모델 + 마이그레이션 (`donations`는 M3)
- [ ] 댓글 CRUD (1depth 답글 강제, 1,000자 제한)
  - 작성 조건 없음(가입 직후 가능) - **Q13 "7일 제한" 폐기(2026-07-03)**, DECISIONS "댓글 작성 조건: 없음" 기준. 스팸은 신고 5회 자동 숨김으로 대응
- [ ] 하트 토글 (1유저 1좋아요, `target_type` = 'episode'|'post'|'comment')
- [ ] 신고 API + **5회 누적 시 자동 숨김** (Q14 결정)
- [ ] 댓글 삭제 (본인/owner/moderator, soft delete; 운영 삭제는 `require_role(OWNER, MODERATOR)`)
- [ ] 작가 게시판 - 근황 CRUD (작성은 `require_owner`만)
- [ ] **moderator 역할 도입**: owner가 부여/회수(`PATCH /admin/users/{id}/role`, owner 전용) + 모더레이션 가드 `require_role(OWNER, MODERATOR)`(댓글·게시글 삭제·신고 처리). 2FA 적용 여부 결정 (3-역할 RBAC, DECISIONS "관리자 권한 분리")
- [ ] 댓글 작성 rate limit (10회/분)

### 프론트엔드 (Astro + React 아일랜드)
- [ ] 에피소드 하단 댓글 UI (`client:idle`)
- [ ] 하트 버튼 (`client:idle`)
- [ ] 작가 게시판 - 근황 페이지
- [ ] 신고 모달

### M4에서 의도적으로 제외
- 후원 (PAY-09) → **M3** (결제와 함께 - 2026-07-03 결제 최후순위 재배치)
- Q&A 게시판 (COMM-07)
- 투표 게시판 (COMM-08) - `polls` 테이블만 만들어두고 작성 UI는 P2
- 비로그인 커뮤니티 읽기 허용 여부 (Q15, 출시 전 결정)

---

## M5. 관리자 운영 도구 (매출/환불/후원 제외 - M3로 이동)

> **목적**: 독자 통계, 댓글/신고 관리, 게시글 작성, 커미션 페이지. **수익·환불·후원 운영 도구는 M3**(결제 최후순위 재배치, 2026-07-03).
> **선행**: M4 (신고/게시글) + M1.5 (콘텐츠 관리)
> **DoD**: 작가가 관리자 화면에서 독자 통계 확인, 신고된 댓글 처리, 게시글 작성, 커미션 페이지 표시까지 가능. (매출/환불/후원 화면은 M3 DoD)

### 백엔드
- [ ] 독자 통계 API (가입자 추이, MAU, 회차별 열람 수; 결제 전환율은 M3에서 합류)
- [ ] 신고된 댓글 리스트 + 처리 API
- [ ] 커미션 신청 폼 (이메일 발송)
- [ ] 업로드 리마인더 (마지막 업로드 후 N일 경과 시 작가 이메일, **P2**)

### 프론트엔드 (Vite React SPA)
- [ ] 독자 통계 화면
- [ ] 댓글/신고 관리 화면
- [ ] 커뮤니티 게시글 작성 화면 (근황/투표)
- [ ] 커미션 관리 화면

### 독자용 사이트 (Astro)
- [ ] 커미션 페이지 `/commission` (작가 가격·일정·예시 + 신청 폼)

> 💡 작품/에피소드 관리(ADM-02/03/04)는 **M1.5 범위**(그쪽에서 구현). M5는 비결제 운영 기능에 집중. 수익·환불·후원(ADM-05/06/08)은 **M3로 이동**했으며, 이동해도 **`require_owner` 전용**(매출 차단; moderator·일반 유저 403, DECISIONS "관리자 권한 분리") 원칙은 그대로.

---

## M6. 알림 (in-app + email + push)

> **목적**: 새 에피소드 / 댓글 답글 / 새 게시글 알림. 채널별 on/off.
> **선행**: M4 (댓글 답글·새 게시글 트리거). 새 에피소드 트리거는 M1.5 공개 전환(E1). M5와 병렬 가능, 결제(M3) 무관
> **DoD**: 알림 동의 유저가 새 에피소드 업로드 시 in-app 알림 즉시 + 이메일 5분 내 수신. 알림 센터에서 읽음 처리. 설정 화면에서 채널별 on/off.

### 백엔드
- [ ] `notification_settings` + `notifications` + `notification_logs` 모델 + 마이그레이션
- [ ] **푸시 채널 결정** (DB 스키마 §7 미결): 웹 푸시 도입 시 `push_tokens` 테이블 추가 또는 P1 보류
- [ ] 알림 발송 서비스 (이벤트 → in-app insert + email send + push send + `notification_logs` 기록)
  - 새 에피소드 업로드 트리거 (M1.5 E1 공개 전환으로 `is_published` 변경 시)
  - 댓글 답글 등록 트리거 (M4 comments insert 시)
  - 새 게시글 등록 트리거 (M4 posts insert 시)
- [ ] 알림 목록 API (페이지네이션, 읽음 필터)
- [ ] 읽음 처리 API
- [ ] 알림 설정 조회/수정 API (채널 × 종류 매트릭스)

### 프론트엔드
- [ ] 알림 센터 UI (Navbar 벨 아이콘 → 드롭다운)
- [ ] 알림 설정 화면 (`/my/notifications`, 채널 × 종류 토글)

### M6에서 의도적으로 제외
- 웹 푸시 (브라우저 권한 + push_tokens) - 복잡도 따라 P1으로 분리 가능
- 카카오톡 알림톡 - 비용/심사 이슈, 보류

---

## M3. 결제 + 유료 콘텐츠 잠금 + 후원 (실행 순서: 마지막, M5·M6 뒤)

> **목적**: 포트원 결제 + 서버 사이드 금액 검증 + Signed URL + 후원 + 결제 운영 도구. **실행 순서상 마지막 기능 마일스톤** (2026-07-03 결제 최후순위 결정 - 상단 다이어그램 참조. 번호는 식별자로 유지).
> **선행**: 기능상 M2(뷰어·잠금 placeholder), 실행은 M5·M6 뒤. 개발은 **포트원 테스트 채널**(사업자 등록 불필요)로 진행, 실키 전환(사업자 등록 + 가맹점 심사)은 M7 "외부 키 교체".
> **DoD**: 미구매 유저가 잠금 UI → 결제 → 서버 검증 통과 → Signed URL로 즉시 열람. 결제 실패는 사용자 안내 + Sentry 알림. 환불은 미열람 회차에 한해 관리자 수동 처리 가능. 후원 결제 + 메시지 등록 동작. 작가가 수익/환불/후원 화면 사용 가능.

### 백엔드
- [ ] `purchases` + `payment_logs` + `donations` 모델 + 마이그레이션 (`donations`는 M4에서 이동)
- [ ] **active 구매 중복 방지 partial unique index** (`refunded_at IS NULL`)
- [ ] **단건 구매 검증 엔드포인트**
  - 클라이언트가 포트원 결제 ID 전달(V1 `imp_uid` / V2 `paymentId` - SDK 버전은 착수 시 결정) → 포트원 REST로 금액·상태 재확인
  - 금액은 반드시 **DB에서 계산** (works.episode_base_price + episodes.price 우선)
  - 검증 통과 시 트랜잭션 1개로 `purchases` + `payment_logs(success)` insert
  - 실패 시 `payment_logs(fail)` + Sentry
- [ ] **유료 에피소드 Signed URL 발급 API**
  - 권한 확인: `purchases` 활성 레코드 (`refunded_at IS NULL`) 존재
  - **회차 단위 1개 URL**, **TTL 10분**, 매 요청마다 생성
- [ ] **첫 열람 시 `first_viewed_at` 기록** (환불 가능 판정 기준)
- [ ] 영수증 URL 반환 (포트원 응답 그대로 노출)
- [ ] **환불 API (관리자 전용)**
  - 조건: `first_viewed_at IS NULL` AND `refunded_at IS NULL`
  - 포트원 cancel API 호출 → `purchases.refunded_at` + `refund_amount` 기록
  - 트랜잭션으로 묶고, **결제 cancel 실패 시 DB 롤백**
- [ ] 후원 결제 (결제 검증 흐름 재사용, `donations` insert) - M4에서 이동
- [ ] 결제 시도 rate limit (10회/분)

### 결제 운영 도구 (M5에서 이동, `require_owner` 전용 - 매출 차단)
- [ ] 수익 집계 API (일/주/월, 작품별·회차별·결제수단별)
- [ ] 환불 요청 리스트 + 승인/거부 API + 관리자 화면
- [ ] 후원 내역 + 메시지 조회 API + 관리자 화면
- [ ] 수익 대시보드 (Vite React SPA)
- [ ] 결제 전환율 통계 (M5 독자 통계에 합류)

### 프론트엔드
- [ ] 유료화 잠금 UI + 구매 버튼 (React 아일랜드 `client:idle`)
- [ ] 포트원 결제창 (카카오페이/토스페이 우선, 카드 후순위)
- [ ] 결제 완료 후 뷰어 자동 언락 (Signed URL 받아서 이미지 로드)
- [ ] 결제 실패 모달 + 재시도 UI
- [ ] 후원 UI + 결제창 (`client:idle`, 1,000/3,000/5,000원 + 메시지) - M4에서 이동
- [ ] 구매 내역 페이지 (`/my/purchases`, SSR, 페이지네이션 20건)
- [ ] 영수증 링크

> ⚠️ 결제 금액 검증은 반드시 서버. 클라이언트 검증 금지.
> ⚠️ 미구매 유저에게 유료 이미지 URL 절대 노출 금지.
> ⚠️ 포트원 API 호출 결과 확인 **후** DB 저장 (외부 호출과 DB 트랜잭션 묶지 말 것).
> ⚠️ Q1 (환불 약관) / Q7 (만 14세) 법무 검토 결과를 결제 화면 약관 텍스트에 반영해야 출시 가능 → 바로 다음이 M7이라 자연 연계.

### M3에서 의도적으로 제외 (P1 후속)
- 전편 구매 (PAY-07) → P1: `purchases.bundle_id` 활용한 일괄 생성/환불

---

## M7. 출시 검증 + 베타

> **목적**: P0 마일스톤 완료 후 출시 직전 검증. PRD §5.2 "관리자+QA 1개월"이 여기에 해당.
> **선행**: M0~M6 P0 항목 완료
> **DoD**: 보안/부하/법무 모두 통과, 베타 사용자 10~30명 1주일 운영 후 치명 버그 0.

### 보안
- [ ] **보안 리뷰**: 결제·인증·Signed URL 권한·CORS·rate limit 종합 점검 (Opus 4.8로 `/security-review`)
- [ ] OWASP Top 10 자체 체크리스트 (XSS, CSRF, SQLi, IDOR)
- [ ] 비밀번호 reset 토큰, 이메일 인증 토큰, JWT TTL 재검토
- [ ] 환경변수 누출 점검 (Astro `PUBLIC_*` 외 빌드 산출물 grep)

### 부하 테스트
- [ ] **100명 동시 뷰어 열람** 시나리오 (k6 또는 wrk)
- [ ] DB 쿼리 N+1 점검 (selectinload 누락 여부)
- [ ] R2 egress 시뮬레이션 (월 7GB 경보 임계치, Q17)

### 법무 검토
- [ ] **약관 / 개인정보처리방침 / 청약철회 안내** 초안 (Q1, Q24)
  - "결제 후 즉시 이용 가능, 청약철회 불가" 결제 화면 명시 필수
- [ ] **만 14세 이상** 가입 체크박스 + 약관 명시 (Q7)
- [ ] 결제 약관 노출 위치 확인

### 외부 키 교체 / 사업자 등록 (의도적으로 여기까지 지연)
- [ ] **사업자 등록** (2026-07-03 결정: 이 전 단계는 전부 사업자 불필요 - 포트원 테스트 채널로 개발. 심사 리드타임 감안해 M3 착수 시점에 서류 준비 시작 권장)
- [ ] **통신판매업 신고** (사업자 등록 후, 유료 판매 개시 전 법적 필수)
- [ ] **포트원 테스트 채널 → 실 키**: 전자결제(가맹점) 신청 + 심사 통과 후 키 교체 (Q4 정정: 토스 샌드박스 경유 폐기)
- [ ] **카카오 OAuth 비즈앱 전환** (사업자 서류 완료 후 활성화, Q20)
- [ ] SMTP 발신 도메인 정식 검증 (스팸 분류 회피)

### 베타
- [ ] 작가 SNS 팔로워 중 10~30명 초청
- [ ] Sentry 에러 모니터링 + 1일 1회 점검
- [ ] 결제·환불·뷰어 흐름 실 사용자 피드백 수집
- [ ] 치명 버그 수정 + 출시 결정

### 운영 준비
- [ ] 다운 감지 알림 작동 확인 (UptimeRobot → 카카오톡)
- [ ] 백업 복원 리허설 1회 (R2 덤프 → 새 VPS로 복구)
- [ ] CS/환불 대응 SOP 문서

---

## 보류 / 제외 결정

전체 목록은 [DECISIONS.md](../DECISIONS.md) "기능 범위 결정 - 보류/나중에" 및 "제외 결정" 섹션 참조. 마일스톤 진입 시 결정이 필요한 항목은 각 마일스톤의 "의도적으로 제외" 블록에서 별도 표기.
