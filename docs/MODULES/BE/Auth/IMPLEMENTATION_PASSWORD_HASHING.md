# 비밀번호 해싱 (M1 그룹 B - B1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 B - B1 |
| 작성 시점 | M1 B1 (2026-06-02) |
| 상태 | 구현 완료, 단위 테스트 통과 |
| 관련 문서 | [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §4, [DECISIONS.md](../../../DECISIONS.md) "보안 결정", study `secret-hashing` |

이 문서는 M1 B1에서 구현한 비밀번호 해싱(`hash_password`/`verify_password`)을 다룬다. OWASP Password Storage Cheat Sheet의 pre-hash 구조를 따랐다. 보안 배경은 `SECURITY_AUTH_DECISIONS.md §4`, 원리는 study `secret-hashing` 참조.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/services/auth_service.py` | `hash_password`/`verify_password` (async) + 내부 `_prehash`/`_hash_sync`/`_verify_sync` |
| `backend/src/services/__init__.py` | services 패키지 |
| `backend/src/config.py` | `password_pepper: SecretStr` 설정 필드 (필수, default 없음) |
| `backend/.env.example` | `PASSWORD_PEPPER` 템플릿 + 생성 명령 안내 |
| `backend/tests/test_auth_service.py` | 단위 테스트 5개 |
| `backend/pyproject.toml` | `bcrypt>=5.0.0` 의존성 |

---

## 2. 해싱 구조 (OWASP pre-hash)

```
bcrypt( base64( hmac_sha384(password, key=PASSWORD_PEPPER) ), gensalt(cost=12) )
```

이 한 구조로 세 가지를 동시에 해결한다.

| 요소 | 역할 |
|------|------|
| `hmac_sha384(pw, pepper)` | **pepper 적용** - 서버측 비밀 키(DB 밖)로 HMAC. DB 단독 유출 시 오프라인 크래킹 차단. |
| `base64(...)` (raw digest) | **72바이트 한도 제거** - SHA384 다이제스트 48B → base64 64자(<72). bcrypt 5.x가 긴 비번에 던지는 `ValueError`/조용한 truncate를 모두 회피. **null 바이트·shucking 방어**. |
| `bcrypt(..., cost=12)` | 느린 해시 본체. salt 자동 생성·포함. |

> ⚠️ HMAC은 반드시 raw `.digest()`(48B) → base64. `hexdigest`(96자)는 다시 72바이트를 초과해 truncate되므로 금지.

---

## 3. 구현 결정

### 3.1 라이브러리: `bcrypt` 직접 (5.x)
passlib 탈락(마지막 릴리스 2020, 미유지보수 + bcrypt 5.0.0에서 백엔드 깨짐). 단일 알고리즘 확정이라 다중 해시 추상화 불필요. `bcrypt.gensalt(12)` → `$2b$12$` 식별자.

### 3.2 블로킹 회피: async + 스레드 오프로드
bcrypt cost=12는 ~250~350ms CPU 블로킹. async 라우터에서 직접 호출하면 이벤트 루프가 멈춰 동시 요청이 밀린다(`backend/CLAUDE.md` "비동기 함수에서 동기 블로킹 호출" 금지). 따라서 `hash_password`/`verify_password`는 `async`이고, bcrypt 부분만 `anyio.to_thread.run_sync`로 워커 스레드에 넘긴다. 싼 HMAC pre-hash는 이벤트 루프에서 바로 계산. `anyio`는 fastapi/starlette가 이미 포함(새 의존성 아님).

### 3.3 pepper 키 관리
- env `PASSWORD_PEPPER`, config `password_pepper: SecretStr`. **default 없음** → 미설정 시 `Settings()` 단계에서 기동 실패(fail-fast). `SecretStr`로 로그 마스킹.
- `TOKEN_PEPPER`(B2, refresh·이메일 토큰 post-hash)와 **분리**, JWT 서명용 `jwt_secret`과도 별개 (키 분리 원칙).
- **로테이션 불가**: pre-hash 방식이라 pepper를 바꾸려면 원문 비번이 필요 → 전 유저 비번 재설정 강제. (토큰 pepper는 post-hash라 재-HMAC으로 로테이션 가능.)

---

## 4. 검증

`uv run pytest tests/test_auth_service.py` 5개 통과 + `uv run ruff check` 클린.

| 테스트 | 확인 |
|--------|------|
| `test_hash_verify_round_trip` | 해시→검증 성공 |
| `test_verify_rejects_wrong_password` | 틀린 비번 거부 |
| `test_same_plain_yields_different_hashes` | salt로 매번 다른 해시, 둘 다 검증됨 |
| `test_bcrypt_hash_format` | `$2b$12$` 포맷(cost=12 반영) |
| `test_long_password_not_truncated` | 72바이트 이후만 다른 긴 비번 2개가 다른 해시로 구분(pre-hash 회귀 안전망) |

---

## 5. 한계 / 후속 (C2 연결 시 처리)

코드 리뷰(`/code-review high`)에서 나온 forward-looking 항목. B1 단위로는 정상이며 C2(로그인)에서 처리한다.

- **`verify_password(plain, None)` 크래시**: 소셜 전용 계정은 `users.hashed_password`가 NULL. C2에서 None 가드 + 더미 해시 검증으로 **타이밍 평탄화**(비열거 정책, SECURITY §6).
- **손상 해시 시 `ValueError` 전파**: `bcrypt.checkpw`가 비정상 해시에 예외 → C2에서 `try/except`로 False 처리 검토.
- **배포/CI env**: `PASSWORD_PEPPER`는 필수라 런타임·`alembic`(env.py가 settings import)·향후 CI pytest 환경에 반드시 주입. 로컬은 `.env`/`.env.example` 처리됨.

후속 작업: B2(토큰 발급/검증, `TOKEN_PEPPER` 추가), B3(쿠키), C(엔드포인트). `M1_foundation.md` 참조.
