# 이메일 인증 재발송 + require_verified_email 가드 (M1 그룹 E - E3)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 E - E3 |
| 작성 시점 | M1 E3 (2026-06-06) |
| 상태 | 구현 완료, 테스트 5개 통과 + /council 5렌즈 리뷰 + Opus 코드리뷰 통과 |
| 관련 문서 | [IMPLEMENTATION_EMAIL.md](./IMPLEMENTATION_EMAIL.md)(E1 발송), [IMPLEMENTATION_EMAIL_VERIFY.md](./IMPLEMENTATION_EMAIL_VERIFY.md)(E2 검증), [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §6·§8 |

E3는 두 가지를 추가한다. (1) **인증 메일 재발송** 엔드포인트 - 미수신/만료로 인증을 못 끝낸 유저가 새 토큰을 다시 받는 경로. (2) **`require_verified_email` 가드** - 이메일 인증을 마친 유저만 통과시키는 FastAPI 의존성. M1에서는 가드 함수만 제공하고 **어떤 라우터에도 부착하지 않는다**(실제 차단은 M3 결제·M4 댓글에서).

토큰 발급·해싱(`create_email_verification`)·발송(`send_verification_email`)은 C/E1에서, 검증(`verify_email`)은 E2에서 끝났다. E3는 그 프리미티브를 재사용해 "직전 토큰 무효화 + 재발급" 흐름과 미인증 차단 의존성만 얹는다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/routers/auth.py` | `POST /auth/resend-verification` 엔드포인트(비열거 동일 200) |
| `backend/src/services/auth_service.py` | `resend_verification(email, session, background_tasks)`, `invalidate_email_verifications(user_id, session)` |
| `backend/src/schemas/auth.py` | `ResendVerificationRequest`(email: `EmailStr`) |
| `backend/src/lib/auth.py` | `require_verified_email` 의존성 + `_FORBIDDEN_UNVERIFIED`(403) |
| `backend/tests/test_auth_endpoints.py` | 테스트 5개(재발송 3 + 가드 단위 2) |

새 의존성 없음. **스키마/마이그레이션 무변경**(기존 `email_verifications` 테이블 재사용).

---

## 2. 흐름

### 2.1 재발송

```
POST /auth/resend-verification  { "email": "<email>" }
  -> resend_verification(email, session, background_tasks)        [service]
       -> user = get_user_by_email(email)        (내부 _normalize_email: 소문자·trim)
       -> user is None  또는  user.is_email_verified
            -> return (no-op: DB 변경·발송 없음)
       -> invalidate_email_verifications(user.id)  (미사용 토큰 used_at = now)
       -> raw_token = create_email_verification(user.id)          (신규 1회용 토큰)
       -> commit                                                  (무효화 + 발급을 한 트랜잭션)
       -> background_tasks.add_task(send_verification_email, user.email, raw_token)
  -> 200 { "message": "인증 메일을 보냈어요" }                    (항상 동일)
```

미존재·이미인증·미인증 **세 경로 모두 HTTP 200 + 동일 메시지**. 실제 발송/토큰 발급 차이는 수신함 주인만 인지한다(비열거).

### 2.2 require_verified_email 가드

```
require_verified_email( current_user = Depends(get_current_user) )
  -> not current_user.is_email_verified  ->  403 "이메일 인증이 필요합니다"
  -> return current_user
```

- `get_current_user` **위에 합성**된다: 비로그인은 거기서 401, 로그인했지만 미인증이면 여기서 403.
- 진실 소스는 `is_email_verified`(bool)이며 `email_verified_at`(시각)이 아니다.
- M1에서는 **라우터 미부착**. M3(결제)·M4(댓글)에서 `Depends(require_verified_email)`로 부착.

---

## 3. 핵심 결정

- **비열거(non-enumeration)**: 미존재/이미인증/미인증 모두 동일 200 + 동일 본문. 인증 표면 전체 통일 원칙(SECURITY §6, study `account-enumeration`)을 재발송에도 적용. 회원/인증 여부는 수신함 주인만 안다.
- **재발송 = 직전 토큰 무효화 + 재발급, 단일 트랜잭션**: 미사용 토큰의 `used_at`을 세팅해 죽이고 신규를 발급한 뒤 한 번에 commit. "최신 메일 링크만 동작"을 보장한다. 무효화는 이 토큰 자체의 보안(고엔트로피 1회용이라 다건 유효해도 추측 불가)보다 **P1 비번재설정 resend와의 의미론 통일**('재발송 = 직전 토큰 무효화')이 주목적 - UX·위생 수준. `invalidate_email_verifications`는 refresh의 `revoke_all_refresh_tokens`와 동형.
- **메일은 commit 후 BackgroundTasks**: 외부 발송 실패가 토큰 발급 트랜잭션을 롤백시키지 않도록(E1·signup과 동일 계약). 비동기 함수에서 동기 블로킹 금지.
- **조회는 `get_user_by_email`(정규화) 경유**: 대소문자/공백 차이로 정상 유저가 no-op에 빠지는 **가용성 버그**를 막는다.
- **타이밍 평탄화 미적용(의도된 한계)**: resend 경로엔 bcrypt가 없어 signup/login식 더미 해시 평탄화를 두지 않았다. 잔여 차(미인증 경로의 DB write 몇 건)는 **응답 바디 동일 + 재발송 rate limit(F1)**으로 커버한다. 완전 평탄화는 아니다(§5 참조).
- **`require_verified_email` 진실 소스 = `is_email_verified`**: 인증 시각(`email_verified_at`)이 아니라 bool 플래그로 판정. `_FORBIDDEN_UNVERIFIED`는 모듈 레벨 상수로 eager 생성.

---

## 4. 검증

`uv run pytest` 57개 통과(기존 52 + E3 5), `ruff check` clean, `alembic check` 클린(스키마 무변경). **/council 5렌즈 플랜 리뷰 + Opus 코드리뷰 통과**(Critical/Major 없음).

| 테스트 | 확인 |
|--------|------|
| `test_resend_invalidates_old_and_issues_new` | 미인증 유저 재발송 → 옛 토큰 `used_at` 세팅 + 신규 미사용 토큰 발급, 발송 1회, 옛 토큰 검증 400 |
| `test_resend_unknown_email_is_silent` | 미존재 이메일 → 200 동일, 토큰 0건, 발송 없음 |
| `test_resend_already_verified_no_send` | 이미 인증된 유저 → 200 동일, 토큰 0건, 발송 없음 |
| `test_require_verified_email_allows_verified` | `is_email_verified=True` → 유저 그대로 통과 |
| `test_require_verified_email_blocks_unverified` | `is_email_verified=False` → 403 |

---

## 5. 제약 / 후속 (council 5렌즈 + Opus 리뷰에서 확인)

- **~~rate limit 부재 (F1 대기, 알려진 열린 구멍)~~ → ✅ I2에서 닫음**: `/auth/resend-verification`은 **비인증 + 메일 발송 트리거**라 알려진 미인증 주소 1개에 반복 호출 = 이메일 폭탄 + Resend 쿼터 소진이 가능했다. I2가 `resend`/`signup`/`login`에 IP 5회/분(`RateLimit`)을 부착해 마감. 계정 lockout은 후속 PR. 상세 [IMPLEMENTATION_RATE_LIMIT.md](./IMPLEMENTATION_RATE_LIMIT.md).
- **타이밍 비대칭 (의도된 한계)**: no-op 경로(미존재/이미인증, 빠름) vs 미인증 경로(DB write 2건 + commit, 느림)로 "등록된 미인증 유저"를 응답시간으로 구분할 여지가 남는다. 응답 바디 동일 + rate limit으로 완화. **I2에서 `email_verifications.user_id` 인덱스가 붙어** 미인증 경로가 빨라져 차가 더 줄었다.
- **~~`email_verifications.user_id` 인덱스 누락~~ → ✅ I2에서 추가**: `invalidate_email_verifications`/`resend_verification`의 `WHERE user_id=?` seq scan이던 것을 `idx_email_verifications_user_id`(마이그레이션 `fefbcb3265c0`, forward-only)로 보강.
- **resend 동시성 (Nit)**: 같은 유저로 동시 2 resend → 각자 옛 토큰 무효화 + 신규 발급 → **유효 토큰 2개**가 남아 "최신 링크만 동작" 약속이 약화된다. 둘 다 본인 수신함이라 보안 위험은 낮음. 필요 시 강화 대상.
- **메일 클릭 완결은 G4 의존 (E2와 동일)**: 재발송 메일 링크도 `{APP_BASE_URL}/auth/verify-email`(프론트 페이지)을 가리킨다. G4가 생겨야 클릭 → 토큰 추출 → `POST /auth/verify-email` 호출로 완결된다. 백엔드 재발송/검증 자체는 완료.
- **`require_verified_email` 미부착**: M1은 가드 함수 + 단위테스트만. 실제 부착은 M3·M4. 관리자용 `require_admin`(M1.5)도 동일 합성 패턴으로 추가 예정.

---

## 관련 문서

- 마일스톤: [M1_foundation.md](../../../milestones/M1_foundation.md) 그룹 E - E3
- 보안 결정: [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §6(비열거)·§8(이메일 인증)
- 선행: [IMPLEMENTATION_EMAIL.md](./IMPLEMENTATION_EMAIL.md)(E1 발송), [IMPLEMENTATION_EMAIL_VERIFY.md](./IMPLEMENTATION_EMAIL_VERIFY.md)(E2 검증)
- study: `account-enumeration`(비열거), `email-verification-link-safety`(POST·1회용 토큰)
