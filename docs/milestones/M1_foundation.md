# M1. 인증 (이메일 + 구글) - 세부

| 항목 | 내용 |
|------|------|
| 문서 버전 | v0.4 (2026-06-10, 그룹 I council fix 계획 추가) |
| 상위 마일스톤 | [M1](./README.md#m1-인증-이메일--구글) |
| 예상 기간 | 약 3주 (이메일 발송/구글 OAuth 콘솔 왕복 포함) |
| 완료 기준 | 신규 유저가 이메일/구글로 가입 → 인증 메일 수신 → 로그인 상태로 마이페이지 진입 (그룹 H 체크리스트) |
| 선행 마일스톤 | [M0](./M0_foundation.md) - 기반 세팅 |
| 다음 마일스톤 | [M1.5](./README.md#m15-관리자-부트스트랩) - 관리자 부트스트랩 |

---

## 선행: 백엔드 스켈레톤 복원

> ⚠️ 업데이트 (2026-06-01): 아래 stash 스켈레톤은 placeholder 수준이라 **폐기**하고, 그룹 A는 정본 `DB_SCHEMA.md §1`에 맞춰 새로 작성했다(UUID PK). stash(`backend src skeleton`)는 drop 완료. 아래 복원 절차는 더 이상 유효하지 않음(이력 보존용).

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

### A1. `users` + `oauth_accounts` + `refresh_tokens` + `email_verifications` 모델 ✅ 완료 (2026-06-01)
- 선행: 스켈레톤 복원
- 산출물: `models/user.py` (`User`, `OAuthAccount`, `RefreshToken`, `EmailVerification`), Alembic 마이그레이션 1개
- DoD: `uv run alembic upgrade head` 성공 → 4개 테이블 + 인덱스 생성. `oauth_accounts` `UNIQUE(provider, provider_id)`, `idx_users_deleted_at` (partial, `deleted_at IS NULL`) 포함
- 결정 (DB_SCHEMA §1 확정):
  - `users.hashed_password` **nullable** (소셜 전용 가입은 NULL)
  - `users.nickname` NOT NULL - 소셜 가입 시 provider 닉네임으로 채움, 충돌 시 suffix 처리
  - `refresh_tokens.token_hash`에 **원문 토큰 저장 금지** (HMAC-SHA256+`TOKEN_PEPPER` 해시만). 결정적 해시라 `token_hash` 직접 조회로 대조 - 상세는 B2
  - `email_verifications.expires_at` = 발급 + 1시간
- 메모: 응답 모델에 `hashed_password`가 새어나가지 않도록 `UserRead` 등 응답 전용 스키마 분리 (SQLModel `table=True` 모델을 그대로 응답에 쓰지 말 것).

---

## 그룹 B. 인증 코어 (해싱 · JWT · 쿠키)

> router/service/lib 레이어 경계 준수: 토큰·쿠키 발급 유틸은 `lib/auth.py`, 비즈니스 로직은 `services/auth_service.py`.

### B1. bcrypt 비밀번호 해싱 ✅ 완료 (2026-06-02)
- 선행: A1
- 산출물: `services/auth_service.py` 해시/검증 함수, `config.py` `password_pepper` 필드, `.env.example` `PASSWORD_PEPPER`
- DoD: 해시 round-trip 단위 테스트 통과, 동일 평문이 매번 다른 해시(salt) 생성 확인, **72바이트 이후만 다른 긴 비번 2개가 서로 다른 해시로 구분됨**(pre-hash 검증)
- **결정 (확정): bcrypt cost=12** (argon2id 아님). 이유: argon2id는 **메모리 하드**(해시당 수십 MiB)라 Hetzner CX22(2 vCPU·4GB, DB+API+FE+Admin+Caddy 동거) 같은 **소형 VPS에서 동시 로그인 시 메모리 압박** + 튜닝을 너무 낮추면 오히려 bcrypt보다 약해질 위험. bcrypt는 CPU 바운드·~4KB로 풋프린트가 작고 예측 가능. OWASP도 bcrypt(work factor ≥10)를 여전히 허용. **pepper·HIBP·lockout**가 더해져 bcrypt로도 충분히 강함.

#### 구현 확정 (2026-06-02, Opus 검증 반영)

- **라이브러리: `bcrypt` 직접 (5.x).** passlib 탈락 - 마지막 릴리스 2020, 사실상 미유지보수 + bcrypt 5.0.0에서 passlib bcrypt 백엔드가 깨짐. 단일 알고리즘 확정이라 다중 해시 추상화 불필요. (`pwdlib`는 다중 알고리즘 필요 시에만 후보)
- **해싱 = OWASP pre-hash 구조**: `bcrypt( base64( hmac_sha384(pw, key=password_pepper) ), gensalt(12) )`. 한 방에 (a) **72바이트 한도 제거**(긴 비번 허용 → C1의 128자 상한과 정합), (b) **pepper 적용**, (c) **password shucking + null 바이트 truncation 방어**.
  - ⚠️ HMAC은 **raw `.digest()`(48B) → `base64`(64자)**. `hexdigest`(96자)는 다시 72바이트 초과로 truncate되니 **금지**.
- **블로킹 회피 (Critical)**: bcrypt cost=12는 ~250~350ms CPU 블로킹 → async 라우터에서 직접 호출 시 이벤트 루프 정지(`backend/CLAUDE.md` 금지). 따라서 **`async def hash_password/verify_password` + `anyio.to_thread.run_sync`로 bcrypt 오프로드**. `anyio`는 fastapi가 이미 포함(새 의존성 아님).
- **키 이름: `password_pepper` (env `PASSWORD_PEPPER`).** 문서상 "SECRET_KEY와 별개"는 곧 기존 `jwt_secret`과 별개. 토큰용 `token_pepper`(B2)와도 **분리**(키 분리 원칙: pre-hash vs post-hash, 알고리즘·로테이션 성질 다름).
  - `SecretStr` 권장(로그 마스킹). 시크릿이라 **default 금지** → `.env.example` + **CI env**에 `PASSWORD_PEPPER` 주입 필수(없으면 `Settings()` import 크래시. `jwt_secret`과 동일 패턴).
- **제약: pre-hash pepper는 로테이션 불가**(교체하려면 원문 비번 필요 → 전 유저 비번 재설정 강제). 유니코드 NFC 정규화는 v1 생략(문서화만).
- 메모: cost=12가 **실제 프로덕션 하드웨어에서 ~250~350ms**가 되도록 배포 후 1회 측정·보정. 설치 직전 `bcrypt` 5.x 최신 패치 WebSearch 재확인. 관련 study: [[secret-hashing]].

### B2. 토큰 발급/검증 (access JWT + refresh opaque) ✅ 완료 (2026-06-03)
- 선행: A1
- 산출물: `lib/auth.py` - `create_access_token`(15분, JWT) / `decode_token`(만료·서명·typ 검증), `services/auth_service.py` refresh 프리미티브(발급·조회·revoke·revoke_all), `config.py`/`.env.example` `TOKEN_PEPPER`, PyJWT 2.13.0. 구현: [IMPLEMENTATION_TOKEN.md](../MODULES/BE/Auth/IMPLEMENTATION_TOKEN.md)
- DoD: 만료 토큰·위조 서명·잘못된 `typ` 거부 단위 테스트 통과 ✅ (pytest 17개 통과)
- 결정:
  - **access = JWT, HS256 + `SECRET_KEY`** (단일 서버라 비대칭키 불필요). 키는 `.env`, config 경유. 하드코딩 금지.
  - access payload에 `sub`(user_id), `typ=access`, `exp` 포함. PII(이메일 등) payload에 넣지 않음.
- **결정 (확정): 리프레시 토큰 저장 = HMAC-SHA256(token, key=`TOKEN_PEPPER`)** (DB_SCHEMA §1 `refresh_tokens.token_hash`). 단 아래 제약:
  1. **refresh는 JWT가 아닌 opaque 랜덤** (`secrets.token_urlsafe(32)`, 256bit). 해시는 보강일 뿐 약한 토큰을 구제 못 함 → 원문 자체가 고엔트로피여야 함
  2. **빠른 해시(HMAC-SHA256)로 충분** - 256bit 랜덤은 brute-force가 물리적으로 불가라 bcrypt 같은 느린 해시 불필요(저엔트로피 추측 방어 도구라 여기선 무의미). study [[secret-hashing]] 참조
  3. **결정적 해시라 `WHERE token_hash = hmac(입력)` 직접 조회 가능** → refresh 쿠키 값은 토큰 원문 그대로(row_id prefix 불필요)
- **결정 (권장 채택): 리프레시 토큰 회전 + 재사용 탐지** - 갱신마다 기존 refresh revoke + 신규 발급(회전). 이미 revoke된(=회전 지난) 토큰이 다시 들어오면 **탈취 신호**로 간주해 해당 유저 refresh 전체 revoke(세션 강제 종료). OAuth 2.0 Security BCP 권장. 최종 채택 확정 시 DECISIONS "보안 결정"에 기록.
- **결정 (확정): HMAC-SHA256 + 서버측 pepper(`TOKEN_PEPPER`).** token_hash 산식에 `.env` pepper 시크릿(`TOKEN_PEPPER`) 포함 → DB 단독 유출 시에도 오프라인 공격 불가. pepper는 `jwt_secret`·`password_pepper`와 **별도 키**. refresh는 ≤cap 내 자연 회전하므로 pepper 교체 시 현재+이전 키 dual-verify로 무중단 로테이션 가능(옛 토큰은 cap 내 소멸). 이메일 인증 토큰(E1/E2) 해시에도 동일 적용.

### B3. HttpOnly 쿠키 발급 유틸 ✅ 완료 (2026-06-04)
- 선행: B2
- 산출물: `lib/auth.py` `set_auth_cookies`/`clear_auth_cookies`/`access_cookie_name` + 상수, `config.py` `cookie_secure` computed 필드, `tests/test_cookies.py`(6개). 구현: [IMPLEMENTATION_COOKIE.md](../MODULES/BE/Auth/IMPLEMENTATION_COOKIE.md)
- DoD: 응답 `Set-Cookie` 헤더에 플래그 정확히 반영됨을 테스트로 확인 ✅ (pytest 23개 통과)
- 결정 (PRD §4.2 / README M1):
  - access: `HttpOnly + SameSite=Lax`, refresh: `HttpOnly + SameSite=Strict`
  - `Secure` 플래그는 **환경 분기** - 로컬 http는 False, 스테이징/프로덕션은 True (`config.cookie_secure` = `env != "development"`, 하드코딩 없음)
  - **결정 (확정): refresh 쿠키 `Path=/auth/refresh` 제한** - 갱신/로그아웃 외 요청엔 미전송. clear도 같은 Path로 매칭(C3 주의)
  - **결정 (확정): `__Host-` 프리픽스는 access에만** - 프리픽스가 Secure를 요구하므로 운영(https)에서만 `__Host-access_token`, 로컬은 `access_token`(이름 환경 분기). refresh는 Path 제한과 상충해 제외
- **결정 (제약): 인증 쿠키는 단일 등록가능도메인(same-site) 배포 전제.** SameSite=Lax/Strict 쿠키는 cross-site에서 전송 안 됨 → FE/Admin/API가 Caddy 리버스 프록시로 한 eTLD+1 아래 묶여야 작동(`admin.도메인`·`api.도메인`은 same-site, **포트 차이는 무관**). API를 별도 도메인으로 분리하면 인증이 깨짐 → **M0 Caddy 단일 도메인 구조 유지 필수**. (로컬 `localhost:8000` 직접 호출도 same-site라 OK)
- 메모: ⚠️ 토큰을 응답 바디로 내려 클라이언트가 localStorage에 담는 경로를 만들지 말 것. 쿠키 전용.

---

## 그룹 C. 이메일·비밀번호 인증 엔드포인트

> `routers/auth.py`. 요청 검증/HTTP 포장은 router, 트랜잭션·로직은 service.

> **결정 (확정): 인증 표면 전체 비열거(non-enumeration) 정책.** 가입·로그인·비번 재설정(P1)·재발송 등 **인증 전 모든 엔드포인트가 "회원/비회원"을 응답으로 구분하지 않는다.** 한 곳만 막으면 다른 곳에서 새므로 표면 전체를 통일한다. 회원 여부를 아는 사람은 **수신함 주인뿐**(공격자는 HTTP 응답에서 아무것도 못 얻음). 응답 분기에 따른 **타이밍 차이도 제거**(없는 유저/중복 유저 경로에 더미 작업으로 시간 평탄화).

### C1. 회원가입 (`POST /auth/signup`) - AUTH-01 ✅ 구현 완료 (2026-06-05)
- 선행: B1, A1
- 산출물: 가입 엔드포인트 + Pydantic 요청 스키마
- DoD: 신규 이메일 → 미인증 user 생성 + 인증 메일(E1). **중복 이메일 → user 생성 없이 "이미 가입된 계정" 안내 메일**(로그인/비번재설정 링크)을 그 주소로 발송. **두 경우 HTTP 응답은 동일**("입력하신 주소로 메일을 보냈어요"). 비번 정책/HIBP 위반은 이메일 존재 여부와 무관하므로 422 가능
- 메모: 중복 경로에서도 bcrypt 더미 해시 등으로 **응답 시간 평탄화**(타이밍 enumeration 차단). 메일 내용 차이는 수신함 주인만 보므로 안전. 가입 시도 rate limit(F1)으로 자동 열거 속도 억제.
- 결정: 비번 정책 **8자 이상 + 영문·숫자·특수문자 각 1개 이상** (AUTH-01). 검증은 서버 필수(프론트는 UX 보조). **비번 최대 길이 상한**(예: 128자) 적용 - bcrypt 72바이트 truncate 회피 + 초장문 비번 CPU DoS 방지.
- **결정 (확정): 유출 비번 차단 (HIBP)** - 가입(및 P1 비번 변경) 시 HaveIBeenPwned k-anonymity API(비번 SHA-1 앞 5자리만 전송)로 유출 비번 거부. 외부 API 장애 시 가입을 막지 않도록 fail-open + 경고 로깅.
- 메모: 가입 직후 미인증 상태(`is_email_verified=False`)로 생성. 가입과 메일 발송을 한 트랜잭션에 묶지 말 것 - 메일은 DB 커밋 후 발송(외부 호출 실패가 가입을 롤백시키지 않도록).

### C2. 로그인 (`POST /auth/login`) - AUTH-02 ✅ 구현 완료 (2026-06-05)
- 선행: B1, B2, B3
- 산출물: 로그인 엔드포인트
- DoD: 비번 검증 성공 → access/refresh 쿠키 발급 + `refresh_tokens` insert(token_hash). 실패 시 401, 이메일/비번 어느 쪽이 틀렸는지 구분 노출 금지(동일 메시지)
- 메모: 타이밍 공격 완화를 위해 미존재 유저도 더미 해시 검증 후 동일 응답 시간 유지 고려.

### C3. 로그아웃 (`POST /auth/logout`) - AUTH-06 ✅ 구현 완료 (2026-06-05)
- 선행: C2
- 산출물: 로그아웃 엔드포인트
- DoD: access/refresh 쿠키 만료 + 해당 `refresh_tokens.revoked_at` 기록. 재사용 시 갱신(C4) 거부됨을 테스트로 확인

### C4. 토큰 갱신 (`POST /auth/refresh`) ✅ 구현 완료 (2026-06-05)
- 선행: C2
- 산출물: 갱신 엔드포인트
- DoD: 유효 refresh 쿠키 → `token_hash`(HMAC) 직접 조회·대조 → 신규 access 발급. 무효/revoked/만료 토큰 401
- 결정: B2의 회전 + 재사용 탐지를 여기서 구현. 회전 시 기존 refresh revoke + 신규 발급을 한 트랜잭션으로, revoke된 토큰 재제출 시 유저 세션 전체 revoke.

### C5. 현재 유저 조회 (`GET /auth/me`) ✅ 구현 완료 (2026-06-05)
- 선행: B2, C2
- 산출물: access 쿠키 → 현재 유저 반환 엔드포인트
- DoD: 유효 access 시 200 + `nickname`/`email`/`is_email_verified`/`is_admin`, 무효·만료 시 401
- 메모: G5 마이페이지·Navbar 로그인 상태 판정의 **단일 소스**. 응답은 민감 필드(`hashed_password` 등) 제외한 `UserRead` 스키마. SSR 페이지가 쿠키를 그대로 전달(`credentials: 'include'`)해 호출.

> **구현 요약 (2026-06-05)**: C1~C5 구현 + Opus 리뷰 완료. 상세 [IMPLEMENTATION_AUTH_ENDPOINTS.md](../MODULES/BE/Auth/IMPLEMENTATION_AUTH_ENDPOINTS.md).
> - 산출물: `routers/auth.py`(5개), `schemas/auth.py`, `services/hibp.py`(HIBP k-anonymity), `services/email_service.py`(E1 계약 스텁), `services/auth_service.py`(유저 CRUD+플로우), `lib/auth.py` `get_current_user`, `lib/exceptions.py`, `tests/test_auth_endpoints.py`(15개). 의존성 `httpx`·`email-validator` 추가.
> - 결정: **로그아웃 = 세션 전체 revoke**(refresh 쿠키 `Path=/auth/refresh`라 `/auth/logout`엔 미전송 → access로 유저 식별 후 전체 revoke). 타이밍 평탄화 더미 해시는 **import 시 eager 생성**(lazy면 첫 호출 때 bcrypt가 이벤트 루프 블로킹 - Opus 리뷰 Major 수정).
> - 검증: 단위 17개 통과. DB 통합 테스트는 현재 환경 docker/Postgres 부재로 미실행 → 기동 후 그린 확인 + 커밋 예정. 그룹 H의 pytest DoD는 그때 체크.

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

### E1. 이메일 발송 서비스 (Resend) ✅ 완료 (2026-06-05)
- 선행: A1, A4
- 산출물: `services/email_service.py` (httpx 비동기 호출), 인증 메일 템플릿. 구현: [IMPLEMENTATION_EMAIL.md](../MODULES/BE/Auth/IMPLEMENTATION_EMAIL.md)
- DoD: 가입 시 `email_verifications`에 1시간 토큰 insert + 메일 발송 → 수신함 도착 확인
- **검증 완료 (2026-06-05)**: 본인 메일로 실제 가입 → Resend API 200 → 인증 링크 메일 수신함 도착 확인. DoD 충족. (dev 발신 `onboarding@resend.dev`, 커스텀 도메인 DKIM은 도메인 확보 후 적용)
- **결정 (확정): 인증 토큰 at-rest 해시 저장.** 메일 링크엔 원문 토큰을 싣되 DB(`email_verifications.token`)에는 **HMAC-SHA256(+pepper, B2 동일 키 정책) 해시만** 저장 → 토큰 1회용 고엔트로피 랜덤. 검증(E2)은 입력 토큰을 동일 해시해 대조. (스키마 컬럼명은 `token`이나 저장값은 해시)
- 결정: 비동기 함수에서 동기 블로킹 호출 금지 - `httpx.AsyncClient` 사용. **발송 = `BackgroundTasks` 확정**(응답 후 실행 → 메일 실패가 가입을 롤백 안 함 + 비열거 타이밍에 영향 없음). C 그룹에서 `signup`이 이미 `email_service.send_*`를 BackgroundTasks로 호출 중 → E1은 스텁을 실제 Resend 연동으로 채우는 범위.
- **결정 (확정): 발송 fail-open.** `RESEND_API_KEY` 미설정 또는 발송 실패(httpx 오류) 시 가입을 막지 않고 경고 로그만(가용성 우선, HIBP와 동일 철학). 미수신은 E3 재발송으로 복구. **단 `env==production` & 키 미설정이면 기동 시 1회 경고 로그**로 프로덕션 silent-failure(전 유저 메일 조용히 미발송)를 방지.
- **결정 (확정): dev 발신은 `onboarding@resend.dev`.** Resend 테스트 모드라 **본인 Resend 계정 이메일로만 발송** → dev DoD(수신함 도착)는 본인 메일로 가입해 검증(임의 주소는 Resend가 거부, fail-open이 삼켜 "에러 없이 미수신"). 커스텀 도메인 DKIM 인증(M0 A4) 완료 후 `EMAIL_FROM`만 교체(코드 변경 없음).
- 메모: ⚠️ 개인정보(이메일 전체) plaintext 로깅 금지 - 마스킹 적용. **원문 토큰/인증 URL도 비로깅**(이벤트명 + 마스킹 이메일만).
- 메모: ⚠️ 메일 HTML 템플릿에 user input(닉네임 등) 직접 삽입 금지(HTML 인젝션) - v1은 미삽입 또는 `html.escape`.

### E2. 이메일 인증 검증 (`POST /auth/verify-email`) ✅ 구현 완료 (2026-06-06)
- 선행: E1
- 산출물: 토큰 검증 엔드포인트
- DoD: 유효 토큰 → `users.is_email_verified=True` + `email_verified_at` 기록 + `email_verifications.used_at` 세팅. 만료/사용됨 토큰 거부
- **결정 (확정): `POST` 엔드포인트** (GET 아님). 상태 변경 + 메일 스캐너/링크 프리뷰의 GET prefetch가 일회용 토큰을 미리 소비하는 것 차단(OWASP 권장). 토큰은 **body**로 받아 URL/쿼리 로깅 회피. 메일 링크는 프론트(G4) 페이지를 가리키고 G4가 버튼 클릭 시 백엔드 POST 호출 - E1 메일 링크 형식은 변경 없음.
- **결정 (확정): 실패 응답 단일 generic 메시지** - 무효/만료/사용됨을 구분 노출하지 않음(400). 재발송 안내는 E3/G4로 복구.
- **결정 (확정): `email_verifications.token` UNIQUE INDEX 추가** (새 alembic 마이그레이션, forward-only). 결정적 해시 `WHERE token=?` 직접 조회라 인덱스 필요 + 중복 방지. `refresh_tokens.token_hash`도 동일 인덱스 누락이나 B2(커밋됨) 영역이라 이 PR 밖 - DB_SCHEMA에 후속 메모만.
- 메모: 토큰 1회용. 검증 후 `used_at` 세팅으로 재사용 차단. 멱등 - 이미 `is_email_verified=True`면 `email_verified_at`은 덮어쓰지 않음(인증 시각 보존). 동시 더블클릭은 결과가 멱등이라 무해(별도 락 불필요). 토큰 원문/해시 비로깅(E1 일관, 이벤트는 user_id만).

> **구현 요약 (2026-06-06)**: `POST /auth/verify-email`(body 토큰) + `auth_service.verify_email`(HMAC 해시 조회 → 만료/사용 검사 → 멱등 인증 마킹). 산출물: `routers/auth.py`, `services/auth_service.py`, `schemas/auth.py` `VerifyEmailRequest`, `lib/exceptions.py` `EmailVerificationError`, `models/user.py` `uq_email_verifications_token` UNIQUE 인덱스 + 마이그레이션 `6d33b06659a8`, `tests/test_auth_endpoints.py` 5개. 검증: pytest 52개 통과(Postgres 통합 포함), `alembic check` 클린, Opus 리뷰 통과(Critical/Major 없음). 구현: [IMPLEMENTATION_EMAIL_VERIFY.md](../MODULES/BE/Auth/IMPLEMENTATION_EMAIL_VERIFY.md).

### E3. 재발송 + `require_verified_email` 의존성 골격 ✅ 구현 완료 (2026-06-06)
- 선행: E1, E2
- 산출물: 인증 메일 재발송 엔드포인트 + `lib/auth.py` `require_verified_email` FastAPI Depends
- DoD: 재발송 시 기존 미사용 토큰 무효화 + 신규 발급. `require_verified_email` 의존성이 미인증 유저에 403 반환(단위 테스트). **실제 적용은 M3/M4** - M1에서는 가드 함수만 제공하고 라우터 부착은 안 함
- 결정: 재발송 rate limit(남용 방지)은 F1과 함께 검토.

> **구현 요약 (2026-06-06)**: `POST /auth/resend-verification`(비인증·body email·비열거 동일 200) + `require_verified_email` 가드(get_current_user 합성, 미인증 403, **라우터 미부착**). 산출물: `routers/auth.py`, `services/auth_service.py`(`invalidate_email_verifications` + `resend_verification`), `schemas/auth.py` `ResendVerificationRequest`, `lib/auth.py` `require_verified_email`, `tests/test_auth_endpoints.py` 5개(재발송 3 + 가드 단위 2). 스키마 무변경(마이그레이션 불필요). 검증: pytest 57개 통과·ruff check clean·alembic check 클린. /council 5렌즈 플랜 리뷰 + Opus 코드리뷰 통과(Critical/Major 없음). 구현: [IMPLEMENTATION_EMAIL_RESEND.md](../MODULES/BE/Auth/IMPLEMENTATION_EMAIL_RESEND.md).
> - **결정 (확정)**: 재발송 = 직전 미사용 토큰 무효화(`used_at`) + 신규 발급을 **단일 트랜잭션 commit**, 메일은 commit 후 BackgroundTasks. 무효화는 이 토큰 자체 보안보다 **P1 비번재설정 resend와의 의미론 통일**('재발송=직전 토큰 무효화')이 목적(이 토큰만 보면 verify가 다건 유효 토큰을 허용하므로 무효화는 UX·위생 수준). 조회는 `get_user_by_email`(정규화) 경유로 대소문자/공백 가용성 버그 차단. resend엔 bcrypt가 없어 타이밍 평탄화 미적용 - 잔여 차(미인증 경로 DB write 몇 건)는 응답 바디 동일 + 재발송 rate limit(F1)으로 커버(완전 평탄화 아님, 의도된 한계).

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
- [x] `require_verified_email` 의존성이 미인증 403 반환(단위 테스트, 부착은 아직 안 함) - E3 완료
- [ ] 동일 이메일 소셜 시도 시 자동 병합 없이 안내 노출 (Q6)
- [ ] 비열거 검증: 신규/중복 이메일 가입의 HTTP 응답·응답시간이 동일, 중복 시 안내 메일은 수신함 주인에게만 발송
- [ ] `uv run pytest` 통과 (auth_service + 엔드포인트 테스트), CI(F1, M0) 그린

---

## 그룹 I. council 리뷰 fix (선존 이슈, 2026-06-06 발견)

> 2026-06-06 `/council` 5렌즈 + Opus가 M1 인증 코드(main 머지 B~E3)를 전수 리뷰하며 찾은 **선존 이슈**. E3 브랜치 cleanup이 아니라 이미 main에 있는 코드라 **각각 새 fix 브랜치/PR**로 처리(합의). 트래킹: GitHub 이슈 #28, 메모리 `project_m1_council_fix_backlog`.

### I1. refresh 회전 race 원자화 🔴 (1순위·보안) - 계획 확정 (2026-06-10)
- 브랜치: `be/fix/refresh-rotation-race`
- 선행: B2(refresh 프리미티브), C4(회전 엔드포인트) - 둘 다 main 머지됨
- 문제: `services/auth_service.py` `rotate_refresh`가 락 없이 SELECT(revoke 확인) → ORM dirty-set revoke → 새 토큰 INSERT. 동시 2요청이 SELECT에서 둘 다 `revoked_at IS NULL`을 보면 둘 다 통과 → **한 옛 토큰에서 새 토큰 2개 발급**(회전 불변식 붕괴 → 재사용 탐지 무력화 / 정상유저 오탐). 추가로 `refresh_tokens.token_hash`에 **인덱스 자체가 없어**(`idx_refresh_tokens_user_id`만) 매 갱신·로그인의 `WHERE token_hash=?`가 seq scan.
- 산출물:
  1. `models/user.py` `RefreshToken.__table_args__`에 `Index("uq_refresh_tokens_token_hash", "token_hash", unique=True)` (email_verifications와 동일 패턴). 누락 인덱스 + 유일성 불변 + 방어선.
  2. 새 Alembic 마이그레이션(forward-only, `down_revision=6d33b06659a8`), `op.create_index(..., unique=True)`. autogenerate 1회 생성 후 실제 파일 Read 확인(손편집 X). 단일 소형 VPS라 plain CREATE UNIQUE INDEX(대용량용 `CONCURRENTLY`는 주석만).
  3. `rotate_refresh` 원자화: revoke를 조건부 `UPDATE refresh_tokens SET revoked_at=now() WHERE id=:id AND revoked_at IS NULL`의 **rowcount**로 교체(헬퍼 `_claim_refresh_token`로 분리). 앱 락은 멀티워커에서 프로세스별 메모리라 무효 → 모든 워커가 공유하는 단일 지점인 DB에서 원자화.
- DoD: 동시 회전 중 단 하나만 새 토큰 발급(나머지 거부). `_claim` 1회차 True·2회차 False 결정적 테스트, `token_hash` UNIQUE 위반 IntegrityError 테스트, 기존 happy-path/stale reuse 전체 revoke 유지. `alembic check` 클린, pytest 그린, Opus 리뷰 통과.
- **결정 (확정, 2026-06-10): race 패자(`_claim` rowcount=0)는 401 단순 거부(세션 유지).** 그 분기는 SELECT 땐 유효였는데 그 사이 동시 회전/로그아웃이 일어난 경우라 탈취 신호가 아님 - 전체 revoke하면 정상 유저 더블클릭에 세션이 통째로 끊기는 오탐. 진짜 stale-토큰 재사용은 SELECT가 `revoked_at`을 보는 기존 분기에서 전체 revoke로 잡힌다.
- 커밋: (1) 모델+마이그레이션 `[BE] feat:`, (2) 서비스 `[BE] fix:`, (3) 테스트 `[BE] test:`.

### I2. 인증 표면 rate limit (M1 F1) - `be/feat/auth-rate-limit`
- `/auth/resend-verification`·`signup`·`login` 무제한 → 이메일 폭탄/브루트포스. IP 5회/분 + 계정 lockout, `email_verifications.user_id` 인덱스 동반. 상세는 그룹 F.

### I3. CORS 와일드카드 좁히기
- `main.py` `allow_methods=["*"]`/`allow_headers=["*"]` + `allow_credentials=True` → 실제 필요한 메서드/헤더로 제한(루트 CLAUDE.md "CORS 와일드카드 금지" 정렬).

### I4. 죽은 테스트 픽스처 정리
- `tests/conftest.py` `TestClient` 기반 `client` 픽스처 제거(미사용·루프 불일치 위험) + `async_client`/`existing_user`를 conftest로 승격(M3/M4 재사용).

> 설계 메모 (5명 공통 맹점): ① 메일 발송 단일 장애점(발송 실패/지연, 이메일 변경 시 토큰 무효화 미설계) ② 배포 토폴로지(멀티워커) 미명시 → race 해법은 앱 락이 아닌 DB 제약 ③ 미인증 유저 세션 상태기계 검증 0.

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
  - refresh = opaque 랜덤 + HMAC-SHA256(+`TOKEN_PEPPER`) 해시, `token_hash` 직접 조회로 대조
  - 리프레시 회전 + 재사용 탐지
  - HMAC + 서버측 pepper (refresh·이메일 인증 토큰 해시 공통)
  - id_token 완전 검증 + OAuth state/nonce + open redirect 차단
  - 단일 도메인(same-site) 쿠키 전제
  - 비번: `bcrypt` 직접(5.x, passlib 아님) + cost=12(argon2id 아님 - 소형 VPS 메모리 제약), **OWASP pre-hash 구조** `bcrypt(base64(hmac_sha384(pw, password_pepper)))`(72byte·shucking 해결), async+`anyio.to_thread` 오프로드, 길이 상한, HIBP 유출 비번 차단
  - 로그인: IP rate limit + 계정 lockout/백오프
  - 이메일 인증 토큰 at-rest 해시
  - **인증 표면 전체 비열거** (가입/로그인/비번재설정/재발송 응답·타이밍 통일, 회원 여부는 수신함 주인만 인지)
  - 이메일 인증 검증(E2) = **POST**(GET prefetch 토큰 소비 차단) + 토큰 body + 실패 단일 generic, `email_verifications.token` UNIQUE INDEX
- 커밋은 영역 prefix `[BE]`/`[FE]`, 한 커밋 하나의 논리 변경 (모델 → service → router → test → 프론트 순 분리, GUIDE_COMMIT).
