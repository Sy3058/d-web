# 이메일·비밀번호 인증 엔드포인트 (M1 그룹 C - C1~C5)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 C - C1~C5 |
| 작성 시점 | M1 C (2026-06-05) |
| 상태 | 구현 + Opus 리뷰 완료. 단위 17개 통과, DB 통합 테스트(신규 15개)는 Postgres 기동 후 검증 대기 |
| 관련 문서 | [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md), [IMPLEMENTATION_COOKIE.md](./IMPLEMENTATION_COOKIE.md), [IMPLEMENTATION_PASSWORD_HASHING.md](./IMPLEMENTATION_PASSWORD_HASHING.md), [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md), study `account-enumeration`·`hibp-k-anonymity` |

B1~B3에서 만든 프리미티브(해싱·토큰·쿠키)를 HTTP 엔드포인트로 연결한다. router는 요청 검증·HTTP 포장만, 트랜잭션 경계와 비즈니스 로직은 service가 소유한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `routers/auth.py` | `/auth/signup`·`/login`·`/logout`·`/refresh`·`/me` 5개 엔드포인트 |
| `schemas/auth.py` | `SignupRequest`/`LoginRequest`/`MessageResponse` + 비번 정책 검증 |
| `services/auth_service.py` | `get_user_by_email`·`create_user`·`signup`·`login`·`logout`·`rotate_refresh`·`create_email_verification`·`_dummy_verify` 추가 |
| `services/hibp.py` | `is_password_pwned` (HIBP k-anonymity, fail-open) |
| `services/email_service.py` | 발송 스텁 (C1↔E1 계약, 마스킹 로깅) |
| `lib/auth.py` | `get_current_user` 의존성 |
| `lib/exceptions.py` | `InvalidCredentialsError`/`PwnedPasswordError`/`InvalidTokenError`/`TokenReuseError` |
| `main.py` | `include_router(auth.router)` |
| `tests/test_auth_endpoints.py` | 통합 테스트 15개 (httpx ASGITransport) |

새 의존성: `httpx`(HIBP + E1) 메인 승격, `email-validator`(EmailStr) 추가.

---

## 2. 엔드포인트

| 메서드 · 경로 | 인증 | 성공 | 실패 |
|--------------|------|------|------|
| `POST /auth/signup` | 없음 | 200 `{"message": ...}` (비열거 통일) | 422 (비번 정책/HIBP) |
| `POST /auth/login` | 없음 | 200 `UserRead` + 쿠키 set | 401 (동일 메시지) |
| `POST /auth/logout` | access 쿠키(best-effort) | 200 + 쿠키 clear | - |
| `POST /auth/refresh` | refresh 쿠키 | 200 + 쿠키 재set | 401 (무효/만료/재사용) |
| `GET /auth/me` | access 쿠키 | 200 `UserRead` | 401 |

토큰은 **응답 바디로 내리지 않는다**(쿠키 전용). `login`/`me` 응답 바디는 민감 필드를 뺀 `UserRead`.

---

## 3. 비열거 + 타이밍 평탄화 (signup, login)

`account-enumeration` 개념의 "표면 전체 통일"을 코드로 구현.

- **HIBP를 존재확인보다 먼저**: 유출 비번이면 422를 던지는데, 이는 이메일 존재 여부와 무관하므로 신규/중복 모두 동일하게 422가 나와 누설이 없다.
- **signup 신규 vs 중복 동일 응답**: 신규는 미인증 user 생성 + 인증 토큰 발급 → commit 후 인증 메일(백그라운드). 중복은 user 생성 없이 "이미 가입됨" 안내 메일. **두 경우 HTTP 200 + 동일 메시지**("입력하신 주소로 메일을 보냈어요").
- **login 일반화**: 미존재/소셜전용/비번불일치 모두 동일 401 메시지.
- **타이밍 평탄화**: 유저가 없는/중복 경로에서도 `_dummy_verify`로 진짜 경로와 같은 bcrypt 비용을 소비해 응답 시간차로 회원 여부가 새지 않게 한다.

### 더미 해시는 import 시 eager 생성 (이벤트 루프 블로킹 회피)

더미 해시는 비번과 무관한 고정값이라 **모듈 로드 시 1회** 생성한다(`_DUMMY_HASH = _hash_sync(_prehash(...))`).

> ⚠️ 처음엔 lazy 캐시(`global ... if None: _hash_sync()`)로 짰는데, 그러면 첫 호출(최초 로그인 실패/중복 가입) 때 bcrypt cost=12(~300ms)가 **이벤트 루프 스레드에서 동기 블로킹**된다(`backend/CLAUDE.md` 금지). 비용은 프로세스당 1회라 어차피 한 번 내야 하고, lazy는 그 1회를 부팅(요청 안 받는 중, 무해)에서 요청 처리 중(유해)으로 옮길 뿐이라 손해. import 시점엔 루프가 없어 블로킹이 무해하므로 eager가 정답. (Opus 리뷰 Major로 잡아 수정.)

`verify_password` 자체는 B1대로 `anyio.to_thread`로 오프로드되므로 평탄화 verify는 루프를 막지 않는다.

---

## 4. 토큰 갱신: 회전 + 재사용 탐지 (refresh)

`rotate_refresh`(service)가 한 트랜잭션으로 처리:

1. `token_hash`(HMAC) 직접 조회로 행을 찾는다(없으면 401).
2. **이미 revoke된 토큰 재제출 = 탈취 신호** → 해당 유저 refresh **전체 revoke** + commit → `TokenReuseError`(401 + 쿠키 clear).
3. 만료 토큰 → 401.
4. 유효 → 기존 revoke + 신규 refresh/access 발급을 **한 트랜잭션**으로 commit 후 쿠키 재set.

근거·상세는 [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §2, study `refresh-token-rotation`.

---

## 5. 로그아웃 = 세션 전체 revoke (결정)

**문제**: refresh 쿠키는 `Path=/auth/refresh`(B3)라 `/auth/logout` 요청엔 **실리지 않는다**. 즉 로그아웃 핸들러는 무효화할 특정 refresh 토큰 원문을 받을 수 없다.

**결정**: access 쿠키로 유저를 식별해 그 유저의 refresh를 **전체 revoke**(전 기기 로그아웃). 1인 개인 사이트라 전체 로그아웃이 단순하고 충분하며, DoD("재사용 시 갱신 거부")도 전체 revoke로 충족된다. access→refresh 결합 클레임(session_id)을 access JWT에 넣는 복잡도를 피했다. access가 만료/무효면 유저 식별 불가 → 쿠키만 clear(best-effort 200).

---

## 6. `get_current_user` 의존성 (C5)

access 쿠키(`access_cookie_name()`으로 환경 일관) → `decode_token` → `sub`로 `User` 조회 → `deleted_at` 확인. 무효/만료/미존재·탈퇴 시 401. G5 마이페이지·Navbar 로그인 판정의 단일 소스이며, 후속 보호 라우트에 재사용한다.

---

## 7. 트랜잭션 경계

service가 commit을 소유한다(레이어 분리): `signup`(신규 경로)·`login`·`logout`·`rotate_refresh`가 각자 commit. router는 쿠키 set/clear와 예외→HTTP 매핑만. `create_user`/`create_refresh_token`/`create_email_verification`는 `flush`만 하고 commit은 호출자가 묶는다. 메일 발송은 `BackgroundTasks`라 **commit 이후** 실행되어, 외부 호출 실패가 가입을 롤백시키지 않는다.

---

## 8. 검증

`uv run pytest` - 기존 단위 17개 통과. 신규 통합 15개는 **httpx `ASGITransport`**로 작성(TestClient는 자체 이벤트 루프라 session-scope async `db_session`(asyncpg)과 루프가 어긋나 `different loop` 에러 → 같은 루프에서 앱을 돌리는 ASGITransport로 회피). HIBP·이메일 발송은 mock. **현재 환경에 docker/Postgres가 없어 DB 의존 테스트는 미실행 상태**(기존 `test_token` 6개도 동일 사유로 대기). Postgres 기동 후 전체 그린 확인 예정.

| 테스트 그룹 | 확인 |
|------------|------|
| signup | 신규(미인증 user + 인증토큰 + 인증메일), 중복(동일 응답·user 미생성·안내메일), 약한 비번 422, 유출 비번 422 |
| login | 성공(쿠키 2종 + refresh insert), 오답·미존재·소셜전용 동일 401 |
| me | 유효 200(UserRead, 민감필드 제외), 무쿠키·무효토큰 401 |
| logout | 세션 전체 revoke |
| refresh | 회전(기존 revoke + 신규 1), 재사용 탐지(전체 revoke + 401), 무쿠키 401 |

---

## 9. 범위 밖 / 후속

- **E1 실제 발송**: 현재 `email_service`는 no-op 스텁(시그니처 고정). Resend 연동은 그룹 E(A4 DKIM 선행).
- **Rate limit / 계정 lockout**: 그룹 F. signup/login 비열거의 자동 열거 억제는 F1과 함께 완성.
- **구글 OAuth**: 그룹 D.
- **FYI (M1 규모 허용)**: signup 존재확인↔insert 사이 동시성(이메일 UNIQUE 위반 가능), refresh 회전 row lock 부재. 저트래픽이라 수용, 다중 인스턴스 전환 시 재검토.
