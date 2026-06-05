# 이메일 인증 검증 엔드포인트 (M1 그룹 E - E2)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 E - E2 |
| 작성 시점 | M1 E2 (2026-06-06) |
| 상태 | 구현 완료, 통합 테스트 5개 통과(Postgres) + Opus 리뷰 통과 |
| 관련 문서 | [IMPLEMENTATION_EMAIL.md](./IMPLEMENTATION_EMAIL.md)(E1 발송), [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §8 |

E1이 발송한 인증 토큰을 받아 **유저를 인증 완료로 표시**하는 검증 측. 토큰 발급·해싱은 C 그룹(`create_email_verification`), 발송은 E1(`send_verification_email`)에서 끝났고, E2는 **입력 토큰을 동일 해시해 대조 -> `is_email_verified=True`** 로 만드는 엔드포인트만 추가한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/routers/auth.py` | `POST /auth/verify-email` 엔드포인트 + 400 매핑 |
| `backend/src/services/auth_service.py` | `verify_email(raw_token, session)` |
| `backend/src/schemas/auth.py` | `VerifyEmailRequest`(token, 상한 512) |
| `backend/src/lib/exceptions.py` | `EmailVerificationError`(-> 400) |
| `backend/src/models/user.py` | `EmailVerification` `uq_email_verifications_token` UNIQUE 인덱스 |
| `backend/migrations/versions/...token_unique_index.py` | 인덱스 마이그레이션 `6d33b06659a8` |
| `backend/tests/test_auth_endpoints.py` | 통합 테스트 5개 |

새 의존성 없음.

---

## 2. 검증 흐름

```
POST /auth/verify-email  { "token": "<raw>" }
  -> verify_email(raw, session)                          [service]
       -> token_hash = HMAC-SHA256(raw, TOKEN_PEPPER)
       -> SELECT email_verifications WHERE token = token_hash   (UNIQUE 인덱스)
       -> 거부: 미존재 | used_at != NULL | expires_at <= now    -> EmailVerificationError
       -> record.used_at = now
       -> (미인증이면) user.is_email_verified = True; email_verified_at = now
       -> commit
  -> 200 { "message": "이메일 인증이 완료되었습니다" } | 400 (비구분)
```

- **결정적 해시 직접 조회**: 입력 토큰을 동일 HMAC 해시해 `WHERE token=?`. E1 at-rest 해시와 대조.
- **멱등**: 이미 `is_email_verified=True`면 토큰(`used_at`)만 소비하고 `email_verified_at`은 보존(최초 인증 시각 유지). 동시 더블클릭도 결과가 같아 별도 락 불필요.

---

## 3. 핵심 결정

- **`POST` (GET 아님)**: 상태 변경 + 메일 스캐너/링크 프리뷰의 GET prefetch가 일회용 토큰을 클릭 전에 소비하는 것 차단(OWASP 권장). 메일 링크는 프론트 G4 페이지를 가리키고, G4가 버튼 클릭 시 이 POST를 호출. study `email-verification-link-safety`.
- **토큰은 body로 수신**(쿼리 X): 액세스 로그·`Referer`·브라우저 히스토리 유출 회피. 원문 토큰/해시 비로깅.
- **실패 비구분**: 무효/만료/사용됨을 단일 메시지(400)로 통일 - 정보 누출 최소화(비열거 철학).
- **`email_verifications.token` UNIQUE 인덱스**: 결정적 해시 직접 조회 O(log n) + 중복 방지. forward-only 마이그레이션.

---

## 4. 검증

`uv run pytest` 52개 통과(기존 47 + E2 5), `alembic check` 클린, Opus 리뷰 Critical/Major 없음.

| 테스트 | 확인 |
|--------|------|
| `test_verify_email_success` | 유효 토큰 -> `is_email_verified=True` + `email_verified_at`/`used_at` 세팅 |
| `test_verify_email_expired_rejected` | 만료 토큰 400, 유저 미인증 유지 |
| `test_verify_email_reuse_rejected` | 성공 후 같은 토큰 재제출 400(1회용) |
| `test_verify_email_unknown_token_rejected` | 미존재 토큰 400 |
| `test_verify_email_idempotent_preserves_verified_at` | 이미 인증된 유저 재검증 시 `email_verified_at` 보존 |

---

## 5. 제약 / 후속

- **프론트 G4 전까지 메일 클릭 미완결**: 메일 링크는 `{APP_BASE_URL}/auth/verify-email`(프론트 페이지). G4가 생겨야 클릭 -> 토큰 추출 -> 이 POST 호출로 이어진다. 백엔드 검증 자체는 완료.
- **soft-deleted 유저 (FYI)**: `verify_email`은 user를 id로 조회(`deleted_at` 필터 없음) - soft delete(AUTH-07, P1) 구현 시 함께 처리.
- **`refresh_tokens.token_hash` 인덱스 누락 (후속)**: 동일 조회 패턴인데 인덱스 없음(B2 영역, 이미 커밋됨). 별도 마이그레이션으로 추가 예정 - `DB_SCHEMA.md` §6 메모.
- **E3**: 재발송 + `require_verified_email` 의존성 골격. `M1_foundation.md` 그룹 E 참조.
