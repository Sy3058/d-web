# M1. 인증 (이메일 + 구글) - 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.1 (2026-05-31) |
| 상위 마일스톤 | [M1](./README.md#m1-인증-이메일--구글) |
| 예상 기간 | 약 3주 (이메일 발송/구글 OAuth 콘솔 왕복 포함) |
| 완료 기준 | 신규 유저가 이메일/구글로 가입 → 인증 메일 수신 → 로그인 상태로 마이페이지 진입 (그룹 H 체크리스트) |
| 선행 마일스톤 | [M0](./M0_foundation.md) - 기반 세팅 |
| 다음 마일스톤 | [M1.5](./README.md#m15-관리자-부트스트랩) - 관리자 부트스트랩 |

---

## 선행: 백엔드 스켈레톤 복원

M0(B1)에서 작성한 `models/routers/services/lib` 골격이 git stash에 보관돼 있다. **그룹 A 시작 전 1회 복원**:

```bash
git stash list   # "backend src skeleton (models/routers/services) - M1~M4 필요" → 현재 stash@{0}
git stash pop stash@{0}
```

복원 후 `uv run uvicorn src.main:app` 기동과 `uv run pytest` 통과를 먼저 확인하고 그룹 A로 넘어간다.

---

## 의존성 다이어그램

```
[A] 인증 도메인 모델 + 마이그레이션
      ↓
[B] 인증 코어 (해싱 · JWT · 쿠키)
      ├─────────────┬─────────────┐
      ↓             ↓             ↓
[C] 이메일/비번    [D] 구글       [E] 이메일 인증
    엔드포인트         OAuth          (발송+검증+가드)
      └─────────────┴─────────────┘
                    ↓
            [F] 보안 가드 (rate limit)
                    ↓
            [G] 프론트엔드 (Astro + React 아일랜드)
                    ↓
            [H] M1 완료 검증
```

- C / D / E는 B 완료 후 병렬 가능. 단 회원가입(C1)이 이메일 인증 발송(E1)을 트리거하므로 C1↔E1은 계약(인터페이스)만 먼저 맞춘다.
- F(rate limit)는 C2(로그인) 엔드포인트가 존재해야 의미가 있어 C 이후.
- G(프론트)는 C/D/E의 **API 계약 확정 후** 시작. 백엔드 미완성 부분은 mock 응답으로 선행 가능.

> **외부 블로커 (M0 그룹 A에서 발급)**: A4 Resend SPF/DKIM 인증(E 그룹 전제), A6 구글 OAuth Client ID + 리다이렉트 URI 등록(D 그룹 전제). 둘 다 미완료면 해당 그룹 진입 불가.

---

## 그룹 A. 인증 도메인 모델 + 마이그레이션

> DB_SCHEMA §1 "계정/인증 도메인" 그대로 구현. SQLModel = DB 모델 + 응답 타입 겸용.

### A1. `users` + `oauth_accounts` + `refresh_tokens` + `email_verifications` 모델
- 선행: 스켈레톤 복원
- 산출물: `models/user.py` (`User`, `OAuthAccount`, `RefreshToken`, `EmailVerification`), Alembic 마이그레이션 1개
- DoD: `uv run alembic upgrade head` 성공 → 4개 테이블 + 인덱스 생성. `oauth_accounts` `UNIQUE(provider, provider_id)`, `idx_users_deleted_at` (partial, `deleted_at IS NULL`) 포함
- 결정 (DB_SCHEMA §1 확정):
  - `users.hashed_password` **nullable** (소셜 전용 가입은 NULL)
  - `users.nickname` NOT NULL - 소셜 가입 시 provider 닉네임으로 채움, 충돌 시 suffix 처리
  - `refresh_tokens.token_hash`에 **원문 토큰 저장 금지** (bcrypt 해시만). 조회는 `id`(row id)로 하고 `bcrypt.verify`로 대조 - 상세는 B2
  - `email_verifications.expires_at` = 발급 + 1시간
- 메모: 응답 모델에 `hashed_password`가 새어나가지 않도록 `UserRead` 등 응답 전용 스키마 분리 (SQLModel `table=True` 모델을 그대로 응답에 쓰지 말 것).

---

## 그룹 B. 인증 코어 (해싱 · JWT · 쿠키)

> router/service/lib 레이어 경계 준수: 토큰·쿠키 발급 유틸은 `lib/auth.py`, 비즈니스 로직은 `services/auth_service.py`.

### B1. bcrypt 비밀번호 해싱
- 선행: A1
- 산출물: `services/auth_service.py` 해시/검증 함수
- DoD: 해시 round-trip 단위 테스트 통과, 동일 평문이 매번 다른 해시(salt) 생성 확인
- **결정 (확정): bcrypt cost=12** (argon2id 아님). 이유: argon2id는 **메모리 하드**(해시당 수십 MiB)라 Hetzner CX22(2 vCPU·4GB, DB+API+FE+Admin+Caddy 동거) 같은 **소형 VPS에서 동시 로그인 시 메모리 압박** + 튜닝을 너무 낮추면 오히려 bcrypt보다 약해질 위험. bcrypt는 CPU 바운드·~4KB로 풋프린트가 작고 예측 가능. OWASP도 bcrypt(work factor ≥10)를 여전히 허용. **pepper(B2)·HIBP·lockout**가 더해져 bcrypt로도 충분히 강함.
- 메모: cost=12가 **실제 프로덕션 하드웨어에서 ~250~350ms**가 되도록 배포 후 1회 측정·보정 (너무 빠르면 상향). 라이브러리는 설치 시 WebSearch로 최신 안정 버전 확인 후 선정 (`passlib[bcrypt]` vs `bcrypt` 직접).

### B2. 토큰 발급/검증 (access JWT + refresh opaque)
- 선행: A1
- 산출물: `lib/auth.py` - `create_access_token`(15분, JWT) / `decode_token`(만료·서명 검증), `services/auth_service.py` refresh 토큰 발급·대조
- DoD: 만료 토큰·위조 서명·잘못된 `typ` 거부 단위 테스트 통과
- 결정:
  - **access = JWT, HS256 + `SECRET_KEY`** (단일 서버라 비대칭키 불필요). 키는 `.env`, config 경유. 하드코딩 금지.
  - access payload에 `sub`(user_id), `typ=access`, `exp` 포함. PII(이메일 등) payload에 넣지 않음.
- **결정 (확정): 리프레시 토큰 저장 = bcrypt 해시** (DB_SCHEMA §1 `refresh_tokens.token_hash`). 단 아래 3개 제약 필수:
  1. **refresh는 JWT가 아닌 opaque 랜덤** (`secrets.token_urlsafe(32)`, 256bit). bcrypt는 보강일 뿐 약한 토큰을 구제 못 함 → 원문 자체가 고엔트로피여야 함
  2. **bcrypt 72바이트 한도 준수** - 원문을 72바이트 이하로 유지(token_urlsafe(32)=43자는 안전). 긴 값을 refresh 원문으로 쓰지 말 것(초과분 조용히 truncate → 보안 저하)
  3. **bcrypt salt 때문에 `WHERE token_hash=?` 직접 조회 불가** → refresh 쿠키 값을 `<토큰_row_id>.<랜덤시크릿>` 형태로 두고, **id로 행 조회 후 `bcrypt.verify(시크릿, row.token_hash)`**
- **결정 (권장 채택): 리프레시 토큰 회전 + 재사용 탐지** - 갱신마다 기존 refresh revoke + 신규 발급(회전). 이미 revoke된(=회전 지난) 토큰이 다시 들어오면 **탈취 신호**로 간주해 해당 유저 refresh 전체 revoke(세션 강제 종료). OAuth 2.0 Security BCP 권장. 최종 채택 확정 시 DECISIONS "보안 결정"에 기록.
- **결정 (확정): HMAC-SHA256 + 서버측 pepper 병행.** token_hash 산식에 `.env` pepper 시크릿 포함 → DB 단독 유출 시에도 오프라인 공격 불가. pepper는 `SECRET_KEY`와 **별도 키**로 관리, 로테이션 시 재해싱 전략 필요. 이메일 인증 토큰(E1/E2) 해시에도 동일 적용.

### B3. HttpOnly 쿠키 발급 유틸
- 선행: B2
- 산출물: `lib/auth.py` 쿠키 set/clear 헬퍼
- DoD: 응답 `Set-Cookie` 헤더에 플래그 정확히 반영됨을 테스트로 확인
- 결정 (PRD §4.2 / README M1):
  - access: `HttpOnly + SameSite=Lax`, refresh: `HttpOnly + SameSite=Strict`
  - `Secure` 플래그는 **환경 분기** - 로컬 http는 False, 스테이징/프로덕션은 True (config 값으로 결정, 코드 분기 하드코딩 금지)
  - refresh 쿠키 `Path`를 토큰 갱신 엔드포인트로 제한할지 검토 (불필요한 전송 축소)
  - 프로덕션 쿠키에 **`__Host-` 프리픽스** 적용 검토 (Secure + Path=/ + Domain 미지정 강제 → 하위도메인 쿠키 주입 방지). 단 Path 제한과 상충하므로 access/refresh 중 적용 대상 선별
- **결정 (제약): 인증 쿠키는 단일 등록가능도메인(same-site) 배포 전제.** SameSite=Lax/Strict 쿠키는 cross-site에서 전송 안 됨 → FE/Admin/API가 Caddy 리버스 프록시로 한 eTLD+1 아래 묶여야 작동(`admin.도메인`·`api.도메인`은 same-site, **포트 차이는 무관**). API를 별도 도메인으로 분리하면 인증이 깨짐 → **M0 Caddy 단일 도메인 구조 유지 필수**. (로컬 `localhost:8000` 직접 호출도 same-site라 OK)
- 메모: ⚠️ 토큰을 응답 바디로 내려 클라이언트가 localStorage에 담는 경로를 만들지 말 것. 쿠키 전용.

---

## 그룹 C. 이메일·비밀번호 인증 엔드포인트

> `routers/auth.py`. 요청 검증/HTTP 포장은 router, 트랜잭션·로직은 service.

> **결정 (확정): 인증 표면 전체 비열거(non-enumeration) 정책.** 가입·로그인·비번 재설정(P1)·재발송 등 **인증 전 모든 엔드포인트가 "회원/비회원"을 응답으로 구분하지 않는다.** 한 곳만 막으면 다른 곳에서 새므로 표면 전체를 통일한다. 회원 여부를 아는 사람은 **수신함 주인뿐**(공격자는 HTTP 응답에서 아무것도 못 얻음). 응답 분기에 따른 **타이밍 차이도 제거**(없는 유저/중복 유저 경로에 더미 작업으로 시간 평탄화).

### C1. 회원가입 (`POST /auth/signup`) - AUTH-01
- 선행: B1, A1
- 산출물: 가입 엔드포인트 + Pydantic 요청 스키마
- DoD: 신규 이메일 → 미인증 user 생성 + 인증 메일(E1). **중복 이메일 → user 생성 없이 "이미 가입된 계정" 안내 메일**(로그인/비번재설정 링크)을 그 주소로 발송. **두 경우 HTTP 응답은 동일**("입력하신 주소로 메일을 보냈어요"). 비번 정책/HIBP 위반은 이메일 존재 여부와 무관하므로 422 가능
- 메모: 중복 경로에서도 bcrypt 더미 해시 등으로 **응답 시간 평탄화**(타이밍 enumeration 차단). 메일 내용 차이는 수신함 주인만 보므로 안전. 가입 시도 rate limit(F1)으로 자동 열거 속도 억제.
- 결정: 비번 정책 **8자 이상 + 영문·숫자·특수문자 각 1개 이상** (AUTH-01). 검증은 서버 필수(프론트는 UX 보조). **비번 최대 길이 상한**(예: 128자) 적용 - bcrypt 72바이트 truncate 회피 + 초장문 비번 CPU DoS 방지.
- **결정 (확정): 유출 비번 차단 (HIBP)** - 가입(및 P1 비번 변경) 시 HaveIBeenPwned k-anonymity API(비번 SHA-1 앞 5자리만 전송)로 유출 비번 거부. 외부 API 장애 시 가입을 막지 않도록 fail-open + 경고 로깅.
- 메모: 가입 직후 미인증 상태(`is_email_verified=False`)로 생성. 가입과 메일 발송을 한 트랜잭션에 묶지 말 것 - 메일은 DB 커밋 후 발송(외부 호출 실패가 가입을 롤백시키지 않도록).

### C2. 로그인 (`POST /auth/login`) - AUTH-02
- 선행: B1, B2, B3
- 산출물: 로그인 엔드포인트
- DoD: 비번 검증 성공 → access/refresh 쿠키 발급 + `refresh_tokens` insert(token_hash). 실패 시 401, 이메일/비번 어느 쪽이 틀렸는지 구분 노출 금지(동일 메시지)
- 메모: 타이밍 공격 완화를 위해 미존재 유저도 더미 해시 검증 후 동일 응답 시간 유지 고려.

### C3. 로그아웃 (`POST /auth/logout`) - AUTH-06
- 선행: C2
- 산출물: 로그아웃 엔드포인트
- DoD: access/refresh 쿠키 만료 + 해당 `refresh_tokens.revoked_at` 기록. 재사용 시 갱신(C4) 거부됨을 테스트로 확인

### C4. 토큰 갱신 (`POST /auth/refresh`)
- 선행: C2
- 산출물: 갱신 엔드포인트
- DoD: 유효 refresh 쿠키 → row id로 행 조회 + `bcrypt.verify` → 신규 access 발급. 무효/revoked/만료 토큰 401
- 결정: B2의 회전 + 재사용 탐지를 여기서 구현. 회전 시 기존 refresh revoke + 신규 발급을 한 트랜잭션으로, revoke된 토큰 재제출 시 유저 세션 전체 revoke.

### C5. 현재 유저 조회 (`GET /auth/me`)
- 선행: B2, C2
- 산출물: access 쿠키 → 현재 유저 반환 엔드포인트
- DoD: 유효 access 시 200 + `nickname`/`email`/`is_email_verified`/`is_admin`, 무효·만료 시 401
- 메모: G5 마이페이지·Navbar 로그인 상태 판정의 **단일 소스**. 응답은 민감 필드(`hashed_password` 등) 제외한 `UserRead` 스키마. SSR 페이지가 쿠키를 그대로 전달(`credentials: 'include'`)해 호출.

---

## 그룹 D. 구글 OAuth - AUTH-04

> 선행 외부키: M0 A6 (구글 Client ID + 로컬/스테이징 리다이렉트 URI). 카카오(AUTH-03)는 M1.5 이후 사업자 서류 완료 후 별도 진행 - **M1 범위 외** (Q20).

### D1. 구글 OAuth2 콜백 처리
- 선행: B, A6
- 산출물: `services/auth_service.py` 구글 토큰 교환·프로필 조회, `routers/auth.py` 콜백 엔드포인트
- DoD: 구글 동의 → 콜백 → 신규 시 `users` + `oauth_accounts` **단일 트랜잭션** 생성 → JWT 쿠키 발급. 기존 유저는 로그인 처리
- 결정:
  - 소셜 가입 이메일은 **이미 검증됨**으로 간주 → `is_email_verified=True` 즉시 세팅 (DECISIONS "이메일 인증 필수": 소셜은 별도 인증 생략)
  - **자동 병합 금지** (Q6): 동일 이메일의 비번 계정이 이미 있으면 병합하지 않고 "이미 해당 이메일로 가입된 계정이 있어요" 안내 → 별도 계정 생성 흐름과 분리
  - 리다이렉트 URI/CORS는 `config.py`가 `APP_BASE_URL`에서 조립 (env 직박 금지, DECISIONS "환경 베이스 URL")
  - **id_token 완전 검증**: 구글 OIDC `id_token`의 서명(JWKS)·`iss`·`aud`·`exp` 검증 후 신뢰. 프로필을 검증 없이 신뢰하지 말 것
  - **open redirect 차단**: 로그인 후 복귀 경로(`next`/`redirect`)는 **same-origin 허용목록**으로만 통과 (외부 URL 리다이렉트 금지)
- 결정 필요:
  - OAuth **state(CSRF) 파라미터 저장 위치** - 단기 HttpOnly 쿠키 vs 서버 측 임시 저장. 콜백에서 state 대조 누락 시 CSRF 취약. D1 직전 확정.
  - **nonce** 사용 여부 - id_token 재생(replay) 방지. state와 함께 발급·대조 권장.

---

## 그룹 E. 이메일 인증 (발송 + 검증 + 미인증 가드) - AUTH-08

> 선행 외부키: M0 A4 (Resend SPF/DKIM). DKIM 미인증 시 스팸 분류되어 DoD 검증 불가.
> ⚠️ AUTH-08은 PRD 우선순위상 P1이나, 다운스트림(M3 결제·M4 댓글)의 `require_verified_email` 의존성을 위해 **발송·검증 인프라는 M1에 선구현**한다 (실제 차단 적용은 M3/M4).

### E1. 이메일 발송 서비스 (Resend)
- 선행: A1, A4
- 산출물: `services/email_service.py` (httpx 비동기 호출), 인증 메일 템플릿
- DoD: 가입 시 `email_verifications`에 1시간 토큰 insert + 메일 발송 → 수신함 도착 확인
- **결정 (확정): 인증 토큰 at-rest 해시 저장.** 메일 링크엔 원문 토큰을 싣되 DB(`email_verifications.token`)에는 **HMAC-SHA256(+pepper, B2 동일 키 정책) 해시만** 저장 → 토큰 1회용 고엔트로피 랜덤. 검증(E2)은 입력 토큰을 동일 해시해 대조. (스키마 컬럼명은 `token`이나 저장값은 해시)
- 결정: 비동기 함수에서 동기 블로킹 호출 금지 - `httpx.AsyncClient` 사용. 발송은 FastAPI `BackgroundTasks` 또는 await(응답 지연 허용 범위 내) 중 택1.
- 메모: ⚠️ 개인정보(이메일 전체) plaintext 로깅 금지 - 로그에는 마스킹(M0 B4 결정 규칙) 적용.

### E2. 이메일 인증 검증 (`GET /auth/verify-email`)
- 선행: E1
- 산출물: 토큰 검증 엔드포인트
- DoD: 유효 토큰 → `users.is_email_verified=True` + `email_verified_at` 기록 + `email_verifications.used_at` 세팅. 만료/사용됨 토큰 거부
- 메모: 토큰 1회용. 검증 후 재사용 차단.

### E3. 재발송 + `require_verified_email` 의존성 골격
- 선행: E1, E2
- 산출물: 인증 메일 재발송 엔드포인트 + `lib/auth.py` `require_verified_email` FastAPI Depends
- DoD: 재발송 시 기존 미사용 토큰 무효화 + 신규 발급. `require_verified_email` 의존성이 미인증 유저에 403 반환(단위 테스트). **실제 적용은 M3/M4** - M1에서는 가드 함수만 제공하고 라우터 부착은 안 함
- 결정: 재발송 rate limit(남용 방지)은 F1과 함께 검토.

---

## 그룹 F. 보안 가드

### F1. Rate limiting - 로그인 5회/분
- 선행: C2
- 산출물: 로그인(및 가입/재발송) 엔드포인트 rate limit 미들웨어
- DoD: 1분 내 6회째 로그인 시도 429 반환
- **결정 (확정): 계정 단위 lockout + 지수 백오프 병행.** IP rate limit과 별개로 **계정별 연속 실패 누적** 시 잠금/지연(예: 5회 실패 후 점증 지연, N회 후 일시 잠금) → 분산 IP로 한 계정 노리는 느린 brute-force 방어. 실패 카운터는 성공 로그인 시 리셋.
- 결정 필요: 구현 방식 - `slowapi`(인메모리/Redis) vs 자체 미들웨어. 단일 인스턴스 초기엔 인메모리로 충분, 다중 인스턴스 전환 시 Redis. 계정 lockout 카운터도 동일 저장소. 설치 라이브러리는 WebSearch로 최신 버전 확인.
- 메모: PRD §4.2 - 로그인 5회/분(여기), 결제 10회/분(M3), 댓글 10회/분(M4). IP rate limit 키는 IP + 이메일 조합 고려.

---

## 그룹 G. 프론트엔드 (Astro + React 아일랜드)

> frontend/CLAUDE.md 패턴: 인증·OAuth는 `client:load`. 쿠키는 HttpOnly라 JS 접근 불가 → 로그인 상태는 SSR(`Astro.request.headers`)로 판정. fetch는 `credentials: 'include'`.
> M0 B6 deferred 보강을 여기서 함께 처리: `lib/validation.ts` zod v4 `z.email()` 전환, `lib/api.ts` FastAPI `{"detail": ...}` JSON 파싱, `frontend/.env.example`에 `PUBLIC_API_BASE_URL` 문서화.

### G1. 회원가입 페이지 - AUTH-01
- 선행: C1 계약 확정
- 산출물: `pages/auth/signup.astro` + `components/auth/SignupForm.tsx`(`client:load`), `packages/shared` Zod 스키마 재사용(react-hook-form + Zod)
- DoD: 비번 정책 클라이언트 검증 + 서버 422 에러 표시. 가입 성공 → 이메일 인증 안내 페이지로 이동

### G2. 로그인 페이지 + 구글 버튼 - AUTH-02 / 04
- 선행: C2, D1
- 산출물: `pages/auth/login.astro` + `components/auth/LoginForm.tsx` + `components/auth/GoogleButton.tsx`(`client:load`)
- DoD: 이메일 로그인 성공 → 쿠키 세팅 후 마이페이지 이동. 구글 버튼 → OAuth 동의 → 콜백 복귀
- 메모: ⚠️ Astro `SECRET_*` 클라이언트 참조 금지. 구글 Client ID 등 공개 가능 값만 `PUBLIC_*`로.

### G3. OAuth 콜백 페이지 (SSR)
- 선행: D1
- 산출물: `pages/auth/callback.astro` (`export const prerender = false`)
- DoD: 백엔드 콜백 처리 후 쿠키 보유 상태로 원래 페이지/마이페이지로 리다이렉트. 실패 시 로그인 페이지 + 에러 안내

### G4. 이메일 인증 안내 + 재발송
- 선행: E2, E3
- 산출물: `pages/auth/verify-email.astro` (안내 + 재발송 버튼 React 아일랜드)
- DoD: 메일 링크 클릭 → 검증 성공 화면. 재발송 버튼 동작(쿨다운/429 표시)

### G5. 마이페이지 골격 (SSR, 로그인 필수)
- 선행: C5
- 산출물: `pages/my/index.astro` (`prerender = false`, 쿠키를 `/auth/me`로 전달해 로그인 판정, 401이면 로그인 페이지 리다이렉트)
- DoD: 로그인 유저 진입 시 `/auth/me` 응답의 닉네임/이메일 표시
- 메모: 구매 목록(M3)·알림 설정(M6) 영역은 placeholder만.

---

## 그룹 H. M1 완료 검증 (DoD)

- [ ] 이메일 가입 → 인증 메일 수신 → 링크 클릭 → `is_email_verified=True` 반영
- [ ] 이메일 로그인 → access/refresh 쿠키 발급(HttpOnly, 플래그 정확) → `/auth/me` 200 → 마이페이지 진입
- [ ] 구글 가입/로그인 → id_token 검증 통과 → 신규 `users`+`oauth_accounts` 생성, 기존 유저 로그인 동작
- [ ] 토큰 갱신(`/auth/refresh`) 동작(회전), 로그아웃 후 갱신 거부됨, revoke된 refresh 재제출 시 세션 전체 무효화
- [ ] 로그인 5회/분 초과 시 429
- [ ] `require_verified_email` 의존성이 미인증 403 반환(단위 테스트, 부착은 아직 안 함)
- [ ] 동일 이메일 소셜 시도 시 자동 병합 없이 안내 노출 (Q6)
- [ ] 비열거 검증: 신규/중복 이메일 가입의 HTTP 응답·응답시간이 동일, 중복 시 안내 메일은 수신함 주인에게만 발송
- [ ] `uv run pytest` 통과 (auth_service + 엔드포인트 테스트), CI(F1, M0) 그린

---

## M1에서 의도적으로 제외 (후속 마일스톤)

| 항목 | 이동처 | 근거 |
|------|--------|------|
| 카카오 OAuth (AUTH-03) | M1.5 이후 | 비즈앱 사업자 서류 필요 (Q20) |
| 비밀번호 재설정 (AUTH-05) | P1 사이클 | PRD 우선순위 |
| 회원 탈퇴 (AUTH-07) | P1 사이클 | soft delete + 닉네임 익명화, 결제 5년 보관 연계 |
| `require_verified_email` 실제 차단 | M3(결제) / M4(댓글) | M1은 가드 함수만 제공 |
| 알림 설정 UI | M6 | 마이페이지 placeholder만 |
| 관리자 로그인 + 2FA(TOTP) | M1.5 | ADM-01, 별도 부트스트랩 |

---

## 외부 의존 / 일정 리스크

| 항목 | 리스크 | 완화 |
|------|--------|------|
| Resend SPF/DKIM 전파 (M0 A4) | 최대 24h, 스팸 분류 | M0에서 첫날 시작했어야 함. 미완료면 E 그룹 전 점검 |
| 구글 OAuth 동의 화면 인증 (M0 A6) | 미인증 앱 60일 제한 / 사용자 수 제약 | 개발·베타는 테스트 사용자 등록으로 회피, 정식 인증은 M7 |
| 리프레시 회전/재사용 탐지 | 구현 후 변경 시 쿠키/DB 흐름 재작업 | B2에서 선결정 후 C4 진행 (회전+탐지 권장) |
| OAuth state/nonce 미설정 | CSRF·id_token replay 취약 | D1 직전 확정, 콜백에서 state·nonce 대조 필수 |
| 인증 쿠키 same-site 전제 | API 별도 도메인 분리 시 로그인 붕괴 | Caddy 단일 도메인 구조 유지(B3), 분리 필요 시 토큰 전략 재설계 |

---

## 메모

- **순서**: 계획(Opus) → 코딩(Sonnet) → 검증(Opus, `@docs/reviews/GUIDE_REVIEW.md` + `CODE_REVIEW_BE.md`/`CODE_REVIEW_FE.md`) → 커밋. 인증·토큰·쿠키는 보안 로직이라 **Opus 검증 생략 금지**.
- 백엔드 실행은 항상 `uv run` 접두사 (`uv run uvicorn`, `uv run pytest`, `uv run alembic`).
- 패키지/라이브러리(bcrypt, JWT, rate limit 등)는 설치 직전 WebSearch로 최신 안정 버전 확인 (GUIDE_WORKFLOW "검색 규칙").
- 결정 필요 항목(OAuth state/nonce 저장 방식, rate limit 라이브러리, `__Host-` 프리픽스 적용 범위, 회전 시 refresh 절대 수명 cap)은 해당 작업 직전 짧게 합의 후 진행.
- **확정된 보안 결정**(M1 착수 시 DECISIONS.md "보안 결정"에 한 번에 기록):
  - refresh = opaque 랜덤 + bcrypt 해시, `id` 조회 후 verify
  - 리프레시 회전 + 재사용 탐지
  - HMAC + 서버측 pepper (refresh·이메일 인증 토큰 해시 공통)
  - id_token 완전 검증 + OAuth state/nonce + open redirect 차단
  - 단일 도메인(same-site) 쿠키 전제
  - 비번: bcrypt cost=12(argon2id 아님 - 소형 VPS 메모리 제약), 길이 상한, HIBP 유출 비번 차단
  - 로그인: IP rate limit + 계정 lockout/백오프
  - 이메일 인증 토큰 at-rest 해시
  - **인증 표면 전체 비열거** (가입/로그인/비번재설정/재발송 응답·타이밍 통일, 회원 여부는 수신함 주인만 인지)
- 커밋은 영역 prefix `[BE]`/`[FE]`, 한 커밋 하나의 논리 변경 (모델 → service → router → test → 프론트 순 분리, GUIDE_COMMIT).
