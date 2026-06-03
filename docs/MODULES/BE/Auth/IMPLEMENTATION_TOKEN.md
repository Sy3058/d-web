# 토큰 발급/검증 (M1 그룹 B - B2)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 B - B2 |
| 작성 시점 | M1 B2 (2026-06-03) |
| 상태 | 구현 완료, 단위 테스트 통과 |
| 관련 문서 | [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md), [IMPLEMENTATION_PASSWORD_HASHING.md](./IMPLEMENTATION_PASSWORD_HASHING.md), study `refresh-token-rotation`, `secret-hashing` |

이 문서는 M1 B2에서 구현한 토큰 프리미티브를 다룬다. access는 JWT(HS256), refresh는 opaque 랜덤 + HMAC 해시 저장. 회전/재사용 탐지/쿠키 발급은 후속 작업(B3·C4)에서 이 프리미티브를 조합한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/auth.py` | `create_access_token`/`decode_token` + `TokenError` (JWT 유틸, DB 무관) |
| `backend/src/services/auth_service.py` | refresh 프리미티브: `create_refresh_token`/`get_refresh_token`/`revoke_refresh_token`/`revoke_all_refresh_tokens` + 내부 `_hash_token` |
| `backend/src/config.py` | `token_pepper: SecretStr` 설정 필드 (필수, default 없음) |
| `backend/.env.example` | `TOKEN_PEPPER` 템플릿 + 생성 명령 안내 |
| `backend/tests/test_token.py` | 단위 테스트 12개 (JWT 5 + refresh 7) |
| `backend/tests/conftest.py` | `db_session` 픽스처를 commit + 테이블 cleanup 방식으로 교체 |
| `backend/pyproject.toml` | `PyJWT>=2.13.0` 의존성 + pytest 루프 스코프 설정 |

---

## 2. access 토큰 (JWT, lib/auth.py)

### 2.1 구조
- **HS256 + `jwt_secret`** (단일 서버라 비대칭키 불필요). 만료 15분(`jwt_access_token_expire_minutes`).
- payload: `sub`(= `str(user_id)`), `typ="access"`, `iat`, `exp`. **PII(이메일·닉네임) 미포함.**

### 2.2 검증 (`decode_token`)
- 만료(`ExpiredSignatureError`)·위조 서명(`InvalidTokenError`)은 PyJWT가 던지고, 이를 잡아 도메인 예외 `TokenError`로 변환.
- ⚠️ **`typ` 수동 검증**: PyJWT는 커스텀 클레임 `typ`을 자동 검증하지 않는다. 디코드 후 `payload["typ"] != "access"`면 `TokenError`. (JWT 헤더의 `typ`과 혼동 금지 - 여기선 payload 커스텀 클레임)
- 라우터(C 그룹)에서 `TokenError`를 잡아 401로 매핑한다. B2에선 라우터가 없으므로 예외만 제공하고 `lib/exceptions.py`는 만들지 않음.

---

## 3. refresh 토큰 (opaque + HMAC, auth_service.py)

### 3.1 생성·저장
- 원문 = `secrets.token_urlsafe(32)` (256bit opaque 랜덤). JWT 아님 - DB 대조가 어차피 필요하므로 JWT로 만들 이유 없음.
- DB 저장값 = `HMAC-SHA256(원문, key=TOKEN_PEPPER).hexdigest()` (64자, `token_hash` 컬럼). **원문 저장 금지.**
- `expires_at` = now + `jwt_refresh_token_expire_days`(7일). 원문은 호출자(쿠키 발급, B3)에게 반환.
- **commit은 프리미티브가 하지 않는다.** 발급은 `flush`(INSERT만 전송, FK 위반 조기 노출), revoke는 dirty 표시만. 트랜잭션 경계는 호출자(C2 로그인, C4 회전)가 잡는다 → C4의 "기존 revoke + 신규 발급을 한 트랜잭션"(재사용 탐지 중 공백 방지) 요구를 만족.

### 3.2 왜 빠른 해시(HMAC)로 충분한가
- 256bit 랜덤은 brute-force가 물리적으로 불가 → 추측당 비용을 키우는 느린 해시(bcrypt) 불필요. study `secret-hashing`(엔트로피 기준) 참조.
- 결정적 해시라 `WHERE token_hash = HMAC(입력)` **직접 조회** 가능 → refresh 쿠키 값은 원문 그대로(row_id prefix 불필요).
- pepper(`TOKEN_PEPPER`)는 DB 단독 유출 시 오프라인 대조 차단용. post-hash라 재-HMAC으로 로테이션 가능(비번 pre-hash와 다름).

### 3.3 조회 프리미티브는 revoked 행도 반환한다 (중요)
`get_refresh_token`은 revoked/만료 여부를 **숨기지 않고** 그대로 행을 돌려준다. revoked를 None으로 가리면 C4 재사용 탐지가 "토큰 없음(404)"과 "이미 revoke됨(=탈취 신호)"을 구분할 수 없게 된다. 만료/revoke 판단·세션 전체 revoke 오케스트레이션은 C4(`/auth/refresh`)에서 한다.

---

## 4. 키 관리: `TOKEN_PEPPER`
- env `TOKEN_PEPPER`, config `token_pepper: SecretStr`. **default 없음** → 미설정 시 `Settings()` 단계에서 기동 실패(fail-fast). 시크릿에 default를 주면 레포의 공개 값으로 조용히 동작해 pepper 효과가 0이 되므로 금지.
- `PASSWORD_PEPPER`(B1, 비번 pre-hash)·`jwt_secret`(JWT 서명)과 **별개 키** (키 분리 원칙).
- 이메일 인증 토큰(E1) 해시에도 같은 `TOKEN_PEPPER` 정책 적용 예정.

---

## 5. 검증

`uv run pytest tests/` 17개 통과(기존 6 + B2 11... JWT 5 + refresh 6).

| 테스트 | 확인 |
|--------|------|
| `test_access_token_round_trip` | 발급→디코드 시 `sub`/`typ` 복원 |
| `test_expired_token_raises` | 만료 토큰 `TokenError` |
| `test_forged_signature_raises` | 서명 변조 거부 |
| `test_wrong_typ_raises` | `typ != "access"` 거부 |
| `test_pii_not_in_payload` | payload에 email/nickname 없음 |
| `test_refresh_token_round_trip` | 발급→조회 일치 |
| `test_refresh_token_hash_not_raw` | DB 저장값이 원문이 아닌 해시 |
| `test_revoke_single` | 단건 revoke 반영 |
| `test_get_returns_revoked_record` | revoked 행도 조회됨(재사용 탐지 전제) |
| `test_unknown_token_returns_none` | 미존재 토큰 None |
| `test_revoke_all` | 유저 전체 revoke |

> 테스트 인프라: session-scope 엔진을 쓰므로 `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope` 둘 다 `"session"`. 프리미티브는 commit하지 않고 같은 세션 내 flush 가시성으로 검증된다. `db_session`은 commit된 픽스처(`test_user`)를 위해 테이블 cleanup으로 격리. FK 때문에 `test_user`로 부모 행 선생성. 상세 함정은 `docs/MISTAKES.md` "pytest / 비동기 DB 테스트".

---

## 6. 한계 / 후속

- **CI env**: `TOKEN_PEPPER`는 default 없는 필수값이라, 향후 CI pytest 환경에 반드시 주입(없으면 import 크래시). `PASSWORD_PEPPER`와 동일.
- **절대 수명 cap**: refresh 회전이 무한 연장되지 않도록 상한(예: 30일)을 둘지 C4 회전 구현 시 결정.
- **후속**: B3(HttpOnly 쿠키 발급 유틸), C2(로그인 시 refresh insert), C4(`/auth/refresh` 회전 + 재사용 탐지). `M1_foundation.md` 참조.

### 6.1 코드 리뷰 FYI - 나중에 처리 (2026-06-03 Opus 리뷰)

B2 단위로는 정상이며 아래는 후속에서 처리한다.

- **`refresh_tokens.token_hash`에 UNIQUE 인덱스 추가** (C4 전, 마이그레이션 필요): `/auth/refresh`마다 `WHERE token_hash=?`가 hot path인데 현재 인덱스가 없어 seq scan. 결정적 해시라 UNIQUE가 의도에도 맞다(조회 가속 + 무결성). 모델엔 `idx_refresh_tokens_user_id`만 있음.
- **`config.jwt_secret`을 `SecretStr`로 전환**: 현재 평문 `str`이라 시크릿 3형제 중 혼자 로그 마스킹 안 됨(`password_pepper`/`token_pepper`는 `SecretStr`). JWT 서명 로직 손댈 때 같이.
