# 마일스톤 로드맵

| 항목 | 내용 |
|------|------|
| 문서 버전 | v1.7 (2026-08-30, M3 완료 판정과 간편결제 테스트 channel 동기화) · v1.6 (2026-08-30) |
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
M3 (결제 + 유료 잠금 + 후원 + 매출/환불 도구)
  ↓
M4 (커뮤니티 - 후원 제외)
  ↓
  ├── M5 (관리자 운영 도구 - 매출/환불 제외) ──┐
  └── M6 (알림) ─────────────────────────────┤
                                             ↓
                          M7 (출시 검증 + 베타)
```

> **M3 즉시 착수 결정 (2026-08-26)**
> 사용자의 최신 지시로 M3를 M2 다음에 진행한다. 2026-07-03의 결제 최후순위 결정은 대체됐다. 테스트 채널 개발에는 사업자 등록이 필요하지 않으므로 실키 심사·카카오 비즈앱·통신판매업 신고와 법무 검토는 계속 M7 출시 gate까지 미룬다.
> - 후원은 M3, 비결제 커뮤니티는 M4, 비결제 운영 도구와 알림은 M5·M6이라는 범위 분리는 유지한다.
> - 마일스톤 번호는 식별자로 유지하며 실행 순서는 이 다이어그램이 기준이다.
> - M3는 개발자 소유의 임시 PortOne 테스트 고객사에서 진행하고, M7 실결제는 작가 소유의 새 Owner 계정·Store에서 진행한다. 외부 거래 이관 없이 배포 설정만 교체한다.

> **의존 메모**
> - M2 진입 전 M1.5에서 작품/에피소드 업로드가 최소한 작동해야 시드 데이터로 뷰어를 만들 수 있음
> - M3는 M2의 paywall 절단·잠금 placeholder·복원 앵커 위에 구매 전문과 결제를 얹는다. M4는 M3 뒤 진행하며 M5와 M6은 M4 뒤 병렬 가능
> - M6 알림 트리거 중 "새 에피소드"는 M1.5 공개 전환(E1), "댓글 답글"·"새 게시글"은 M4 이벤트
> - **외부 블로커 (마일스톤 외부 일정)**: M3 테스트에는 개발자 소유 PortOne 카드와 카카오페이 `TC0ONETIME`·토스페이 `tosstest` 직연동 테스트 channel, 공개 FE/API/webhook HTTPS 주소가 필요하다. 세 테스트 수단은 M3에서 브라우저 스모크하고 계약·심사를 거친 작가 실 MID는 M7 출시 gate에서 검증한다

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
- [ ] **개발자 소유 PortOne V2 테스트 고객사·channel** 발급 (M3 Day 0: Store/API/webhook secret + 카드·카카오페이 `TC0ONETIME`·토스페이 `tosstest` channel 필수, 작가 사업자 정보 미사용)
- [x] 구글 OAuth Client ID 발급 (로컬 리다이렉트 URI 등록 완료, 스테이징 URI는 도메인(A1) 후)
- [ ] UptimeRobot 모니터 등록 (5분 간격)

### CI/CD
- [x] GitHub Actions: backend, frontend, admin lint/test/build job 구현 + PR #123 세 job 실통과 확인
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
- 카카오 OAuth → 사업자 등록 후(M7 출시 준비 시기, Q20)
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
- [x] `works` + `tags` + `works_tags` + `episodes` 모델 + 마이그레이션 (#51, schemas 요청/응답 분리·로컬 DB 검증 완료; `bundle_discount_rate`는 현재 범위 제외인 전편 구매용 호환 컬럼이라 M3에서 미사용, `idx_tags_name`은 name UNIQUE로 대체)
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

> ⚠️ TOTP 시크릿은 DB에 암호문으로 저장하고 로그·영속 클라이언트 저장소에 노출하지 않는다. 초기 등록의 일회성 `otpauth_uri`만 메모리에 전달하고 confirm·logout 시 폐기한다.
> ⚠️ 비권한(일반 유저·role 미달) 관리자 API 호출 시 403, 라우터 단 `require_role` 일관 적용 점검.
> ⚠️ **개발자 매출 차단은 product 역할이 아님**: 개발자는 product 역할로 만들지 않는다(관측은 외부 도구 Sentry 등). "개발자가 매출을 못 본다"는 라우트 가드가 아니라 인프라/자격증명 소유권 - 진짜 장벽은 M7 인프라 분리 시(DECISIONS "관리자 권한 분리").

---

## M2. 콘텐츠 (무료 구간)

> **목적**: 작품 목록 → 에피소드 목록 → 뷰어 3단계 + 회차 내 무료 구간 정책.
> **선행**: M1.5 (시드 데이터 입력 가능 상태)
> **DoD**: 비로그인 유저가 작품 목록에서 무료 회차와 부분 유료 회차의 paywall 이전 구간을 열람하고, 경계에서 잠금 placeholder를 확인.
> **세부**: [M2_foundation.md](./M2_foundation.md) - 그룹 A~H 분해 + 설계 결정 6개(무료 presigned·dweb-cover·SSR·이미지 로딩 등)

### 백엔드
- [x] 작품 목록 API (페이지네이션, 태그 필터) *(그룹 A 완료 2026-07-18: `works.is_published` 게이트 신설 + 공개 회차 카운트. IMPLEMENTATION_PUBLIC_CATALOG_API.md)*
- [x] 작품 상세 API (works + tags + 공개 episodes 요약, `selectinload` 사용) *(그룹 A 완료 2026-07-18: 썸네일 URL은 D2까지 null - 원고 키 노출 차단)*
- [x] 에피소드 목록 API (제목·부제·썸네일·공개일·무료/잠금 상태, `public_id` URL과 `sort_order` 표시 순서 분리) *(그룹 B1 완료 2026-07-21, 후속 회차 번호 폐기 반영)*
- [x] **무료 구간 콘텐츠 API** (#76 콘텐츠 모델: content를 paywall 경계에서 **서버 절단** + image 키 presigned URL 치환, no-store. 절단은 M3→M2 앞당김 2026-07-16 - 경계 뒤 반환·결제 검증만 M3) *(그룹 B2 완료 2026-07-21: 절단은 `is_free`와 무관하게 항상 수행, 절단→presign 순서 고정. IMPLEMENTATION_FREE_CONTENT_API.md)*
- [x] `viewer_progress` 모델 + 진행도 저장 API (블록 인덱스 기준 - #76 재해석, WORK-09) *(그룹 C1 완료 2026-07-20: PUT/GET /episodes/{id}/progress, upsert. IMPLEMENTATION_VIEWER_PROGRESS.md)*
- [x] 랜딩(`/`)·`/commission` 데이터 API + admin 편집 기반 (`commission_items`·`site_texts`, #107·#110. 독자 SSR 화면은 그룹 G FE)

### 프론트엔드 (Astro)
- [x] 작품 목록 페이지 (SSR `prerender=false` + 짧은 Cache-Control - M2_foundation 결정 3) *(그룹 E1 완료 2026-07-22: 태그 필터·페이지네이션·표지 onerror 폴백. IMPLEMENTATION_CATALOG_PAGES.md)*
- [x] 작품 상세 + 에피소드 목록 페이지 (SSR) *(그룹 E2 완료 2026-07-22: 무료/잠금 배지·회차 링크(F1 라우트 선점). /code-review xhigh 반영)*
- [x] **뷰어 - 콘텐츠 문서 렌더러** (React 아일랜드, `@tiptap/core generateHTML`, 2026-08-21 그룹 H 사용자·자동 검증 완료)
  - 글+이미지 혼합 렌더, **이미지 즉시 전량 요청 + `fetchpriority`**(lazy 아님 - M2_foundation 결정 6), 이전/다음 화 이동, 경계 지점 잠금 placeholder
  - 드래그/복사/우클릭/저장 차단 (UX 우선, 완벽 차단 아님)
  - 진행도 저장 (블록 index + `block_offset_bp`, debounce)
  - 본문은 no-store API로 아일랜드가 fetch (SSR HTML에 presigned 금지)
- [x] 메인 랜딩(`/`) 재설계 - 등록 최신순 작품 중앙 캐러셀 + 소형 작가 프로필 스트립 + 커미션 최대 4개 썸네일 그리드 (공개 API 기반 SSR, 2026-08-13 구현, 2026-08-21 사용자 브라우저 확인)
- [x] `/commission` 홍보 페이지 (가격·일정·예시·모집 상태, 외부 CTA·신청 폼 제외, 2026-08-13 구현, 2026-08-21 사용자 브라우저 확인)

> **M2 완료(2026-08-21)**: 그룹 H의 독자 경로·보안·성능 검증, 대표 이미지 불변식 수정·자동 회귀 검증, 관리자 브라우저 엣지 케이스 확인을 모두 완료했다.

### M2에서 의도적으로 제외
- 작품 검색 (WORK-11, P2)
- 유료 구간(경계 뒤) 반환 + 결제 검증 → M3 (절단 자체는 M2)
- 커미션 내부 신청 폼(이메일 발송) + admin 접수 관리 화면 → M5 (`/commission` 홍보 페이지 자체는 M2)

---

## M3. 결제 + 유료 콘텐츠 잠금 + 후원

> **목적**: PortOne V2 서버 주문·검증, 구매 권한, 유료 전문, 환불·대사, 후원을 복구 가능한 한 경계로 만든다.
> **선행**: M2. 2026-08-26 결정으로 M2 다음에 즉시 진행한다.
> **P0 DoD**: 결제 전 고지·동의 → 서버 주문 → 검증된 결제 → 구매 권한 1건 → 전문 자동 발급 → 환불·장애 복구 → 기본 매출 확인이 테스트 채널에서 끝까지 작동한다.
> **세부 설계**: [M3 foundation](./M3_foundation.md)이 상태 머신, schema, API, PR 순서와 검증의 정본이다.

### P0 판매 경로

- [ ] `payment_orders` + `purchases` + durable `payment_webhook_receipts` + `payment_logs`와 PortOne V2 async REST adapter
- [ ] 서버 가격·Store·`test|live`·channel snapshot, 환경별 열린 주문·구매 UNIQUE, pre-register, 30분 주문 만료
- [ ] browser·webhook receipt worker·대사·owner 공통 단조 sync, out-of-order 방어와 이중 `PAID` 보상 취소
- [ ] 결제·비공개·soft delete race 단일 승자, 일반 비공개 뒤 기존 구매 full 유지, 먼저 비공개된 주문의 늦은 `PAID` 전액 보상
- [ ] 결제 전 즉시 제공 고지·동의 snapshot, 미구매 paywall 절단, `useEffect` login_hint 판별·access 자동 refresh, 활성 구매 full 자동 반환, 첫 전문 발급·환불 승인 race 단일 승자
- [ ] 구매 내역·영수증, 잠정 168시간 전문 미발급 환불, owner 승인·거부·취소·결과 메일 복구
- [ ] 구매 gross/refund/net과 대사 필요 화면, test 결제 기본 제외
- [ ] 개발자 test Store에서 작가 live Store로 DB 이관 없이 배포 설정 교체

### M3 P1 확장

- [ ] 이미지 width·height·byte_size 저장·백필과 뷰어 공간 예약
- [ ] 로그인·게스트 완독, 작품 진행률·구매 배지·CTA 의미 통일
- [ ] 작가·에피소드 후원과 owner 메시지 목록
- [ ] 후원 포함 작품·회차·결제수단 breakdown과 전환율

> 결제 금액과 권한은 서버에서만 검증한다. 미구매 응답에는 유료 key·URL이 없어야 한다. PortOne 외부 I/O 중 DB transaction을 잡지 않으며 모든 외부 `PAID`는 권한 부여나 전액 보상 취소 중 하나로 종결한다. 예상 가능한 카드 거절·사용자 취소는 사용자 안내와 감사 로그 대상이고, 불변식 위반·장기 미수렴만 Sentry 대상이다.

### M3에서 의도적으로 제외

- 전편 구매·묶음 할인·`bundle_id`, 멤버십·구독, 무통장·가상계좌·부분 환불
- 게시글·공개 후원 피드, 범용 ledger·queue, PG 수수료·실정산·세금
- 실키 전환·사업자 심사·Q1/Q7 법무 승인 자체는 M7 gate

---

## M4. 커뮤니티 (후원은 M3로 이동)

> **목적**: 하트 + 댓글 + 작가 게시판(근황). 후원은 앞선 M3에서 완료한다.
> **선행**: M3 (기능 자체는 결제와 독립이지만 2026-08-26 실행 순서를 따른다)
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
- 후원 (PAY-09) → **M3**
- Q&A 게시판 (COMM-07)
- 투표 게시판 (COMM-08) - `polls` 테이블만 만들어두고 작성 UI는 P2
- 비로그인 커뮤니티 읽기 허용 여부 (Q15, 출시 전 결정)

---

## M5. 관리자 운영 도구 (매출/환불/후원 제외 - M3로 이동)

> **목적**: 독자 통계, 댓글/신고 관리, 게시글 작성, 커미션 접수(내부 신청 폼 + 관리 화면). **수익·환불·후원 운영 도구는 M3**에서 먼저 완료한다. `/commission` 홍보 페이지 자체는 **M2**에서 먼저 제공하고, M5는 그 위에 내부 신청 폼을 얹는다.
> **선행**: M4 (신고/게시글) + M1.5 (콘텐츠 관리) + M2 (`/commission` 홍보 페이지)
> **DoD**: 작가가 관리자 화면에서 독자 통계 확인, 신고된 댓글 처리, 게시글 작성, 커미션 신청 폼 동작 확인까지 가능. (매출/환불/후원 화면은 M3 DoD)

### 백엔드
- [ ] 독자 통계 API (가입자 추이, MAU, 회차별 열람 수; 결제 전환율은 M3에서 합류)
- [ ] 신고된 댓글 리스트 + 처리 API
- [ ] 커미션 내부 신청 폼 (이메일 발송, `/commission` 홍보 페이지는 M2에서 이미 존재)
- [ ] 업로드 리마인더 (마지막 업로드 후 N일 경과 시 작가 이메일, **P2**)

### 프론트엔드 (Vite React SPA)
- [ ] 독자 통계 화면
- [ ] 댓글/신고 관리 화면
- [ ] 커뮤니티 게시글 작성 화면 (근황/투표)
- [ ] 커미션 관리 화면

### 독자용 사이트 (Astro)
- [ ] `/commission`에 내부 신청 폼 추가 (`CommissionItem.id`와 신청 대상 연결, 가격·일정·예시는 M2 완료분 이어보기)

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

## M7. 출시 검증 + 베타

> **목적**: P0 마일스톤 완료 후 출시 직전 검증. PRD §5.2 "관리자+QA 1개월"이 여기에 해당.
> **선행**: M0~M6 P0 항목 완료
> **DoD**: 보안/부하/법무 모두 통과, 베타 사용자 10~30명 1주일 운영 후 치명 버그 0.

### 보안
- [ ] **보안 리뷰**: 결제·인증·Signed URL 권한·CORS·rate limit 종합 점검 (`$fable-review`; 메인 Astra가 난도에 맞는 reasoning으로 판단, 모델·위임 기준은 `docs/guides/GUIDE_WORKFLOW.md`)
- [ ] OWASP Top 10 자체 체크리스트 (XSS, CSRF, SQLi, IDOR)
- [ ] 비밀번호 reset 토큰, 이메일 인증 토큰, JWT TTL 재검토
- [ ] 환경변수 누출 점검 (Astro `PUBLIC_*` 외 빌드 산출물 grep)

### 부하 테스트
- [ ] **100명 동시 뷰어 열람** 시나리오 (k6 또는 wrk)
- [ ] DB 쿼리 N+1 점검 (selectinload 누락 여부)
- [ ] R2 egress 시뮬레이션 (월 7GB 경보 임계치, Q17)

### 법무 검토
- [ ] **약관 / 개인정보처리방침 / 청약철회 안내** 초안 (Q1, Q24)
  - 결제 전 "결제 후 즉시 이용 가능, 제공 시작 뒤 단순 변심 청약철회 제한, 표시·광고 또는 계약 불일치 예외"를 명시하고 최종 문구 법무 검토
- [ ] **만 14세 이상** 가입 체크박스 + 약관 명시 (Q7)
- [ ] 결제 약관 노출 위치 확인

### 외부 키 교체 / 사업자 등록 (의도적으로 여기까지 지연)
- [ ] **작가 사업자 등록** (M3는 개발자 소유 테스트 고객사로 개발. M7 일정에서 가맹점 심사 lead time을 역산해 준비)
- [ ] **통신판매업 신고 또는 면제 여부 확인** (사업자 등록과 별도 절차. 면제 여부는 작가 사업 조건·관할 지자체 기준으로 확인하고, 면제돼도 전자상거래 소비자보호 의무는 별도 검토. [공정위 안내](https://www.ftc.go.kr/www/selectExmplView.do?dscsnExmplSn=898&key=330&pageIndex=2&pageUnit=10&searchCnd=all))
- [ ] **작가 소유 PortOne Owner 계정·Store 생성**: 개발자를 Dev로 초대하고 개발자 테스트 고객사의 사업자 전환·거래 이관은 하지 않음
- [ ] **작가 Store 실 키 설정**: 전자결제 신청 + 심사 통과 후 production Store·channel·API/webhook secret 교체, 카카오페이·토스페이 계약 MID 스모크
- [ ] **개발자 테스트 계정 retire 또는 삭제**: 작가 계정 전환 뒤 신규 intent를 닫고 nonterminal·최근 대사 0을 확인한 다음 webhook·scheduler 중단과 테스트 secret 폐기 후 수행
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
