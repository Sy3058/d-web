# 관리자 2FA 등록 + 2단계 로그인 + 신뢰 기기 (M1.5 그룹 B - B2·B3)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 B - B2(등록)·B3(로그인·가드) |
| 작성 시점 | 2026-07-10 (구현은 2026-07-05~08, PR #58 - 사후 작성) |
| 상태 | 구현 완료·머지(#58). 테스트 신규 45개(전체 148) 그린, 강 모델 보안 리뷰 통과(Critical/Major 0). 후속: 죽은 토큰 정리 잡 #57 (TOTP replay 방지 #56은 2026-07-22 구현 완료 - §3 해당 절) |
| 관련 문서 | DECISIONS.md "2FA"(신뢰 기기 포함), [IMPLEMENTATION_RBAC_TOTP_FOUNDATION.md](./IMPLEMENTATION_RBAC_TOTP_FOUNDATION.md)(B1 기반), study `trusted-device-2fa` |

B1의 role·TOTP 컬럼 위에 얹은 관리자 로그인 플로우 전체. "owner의 유효 세션 = 전부 TOTP 통과" 불변식이 이 모듈의 핵심 설계 목표다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/routers/admin_auth.py` | `POST /admin/2fa/setup`·`/admin/2fa/confirm`(B2), `POST /admin/login`·`/admin/login/totp`(B3) - 전부 rate limit IP 5회/분 |
| `backend/src/services/admin_auth_service.py` | `authenticate_owner`(비열거 1단계), `setup_totp`/`confirm_totp`, `login_totp`, 신뢰 기기 발급/검증/일괄 revoke |
| `backend/src/lib/auth.py` | `admin_totp_pending` 서명쿠키 유틸, 신뢰 기기 쿠키 유틸, **`require_role(*roles)` 팩토리 + `require_owner`** |
| `backend/src/services/auth_service.py` | **`requires_totp_login(user)`** - owner 세션 발급 지점 봉쇄의 단일 판정. `/auth/login`이 owner를 generic 401 거부 |
| `backend/src/services/oauth_service.py` | 구글 OAuth 콜백도 `requires_totp_login` 경유(owner generic 거부) |
| `backend/src/models/user.py` + `migrations/versions/20260707_1707_add_trusted_devices.py` | `TrustedDevice`(token_hash UNIQUE·user_id 인덱스) |
| `backend/scripts/promote_admin.py` | 승격 시 refresh 전체 revoke + 신뢰 기기 revoke, 소셜 전용 계정 승격 거부 |
| 테스트 | `test_admin_2fa.py`(15)·`test_admin_login.py`(30)·`test_admin_bootstrap.py` 보강 |

---

## 2. 플로우

```
POST /admin/login (이메일/비번, 비열거 1단계)
  ├─ 미등록 owner  → admin_totp_pending(totp_setup_pending) 쿠키 → stage="totp_setup"
  │     → POST /admin/2fa/setup   (시크릿 생성·암호화 저장, otpauth:// URI 반환 - QR)
  │     → POST /admin/2fa/confirm (첫 코드 검증 → 활성화 + 즉시 세션 오픈)
  ├─ 신뢰 기기 쿠키 유효 → TOTP 생략, 즉시 세션 → stage="complete"
  └─ 활성 owner   → admin_totp_pending(totp_pending) 쿠키 → stage="totp"
        → POST /admin/login/totp (코드 검증 → set_auth_cookies + 옵트인 신뢰 기기)
```

---

## 3. 주요 결정

### 2FA 우회 봉쇄 = "owner 세션 발급 지점 봉쇄" (승격 표식 대안 기각)
B2 시점의 공백: owner가 일반 `/auth/login`으로 로그인하면 TOTP 없이 `require_owner`를 통과할 수 있었다. 해결은 세션을 여는 **모든 경로**(비번 로그인, 구글 OAuth, 미래의 카카오 등)가 발급 전 `requires_totp_login(user)`를 거쳐 owner면 거부하는 것 - 판정을 한 함수로 모아 새 로그인 경로가 반드시 경유하게 했다. 거부 응답은 다른 실패와 동일한 generic 401(올바른 비번 소지자에게도 "이 계정이 관리자"라는 성공 신호를 안 줌), 서버 로그로만 구분.

### require_role: DB role + owner TOTP 활성 보조 검사
`require_role(*roles)`는 `get_current_user` 위에 합성 - authz는 매 요청 DB `user.role`(추가 쿼리 0, 강등 즉시 반영). M1.5는 `require_owner`만 부착. 보조 규칙: **owner인데 `totp_confirmed_at IS NULL`이면 403** - 발급 지점 봉쇄가 못 덮는 잔존 창(reader로 로그인 중 승격되면 stateless access ≤15분이 owner 권한 획득)을 닫는다.

### 1→2단계 운반 = 단명 서명쿠키 (stateless, oauth_tx 패턴)
`admin_totp_pending`: jwt_secret 서명 JWT, `purpose=totp_pending|totp_setup_pending` + sub, **10분**, `Path=/admin`, SameSite=Strict(admin SPA same-site fetch만 견디면 됨 - oauth_tx가 Lax인 사유가 여기엔 없음), HttpOnly. 서버 저장 없음. 쿠키가 유효해도 **DB를 재확인**(role·활성 상태) - 발급 후 강등·리셋 즉시 반영. 게이트 실패는 원인(쿠키 무효/역할 미달/상태 불일치) 구분 없는 generic 401(비열거).

### confirm 성공 = 즉시 세션 오픈 (재로그인 없음)
confirm 시점엔 비번(1단계 pending 쿠키)과 TOTP 코드가 모두 검증된 상태라 2단계 로그인과 등가 - `set_auth_cookies`로 바로 세션을 연다(2026-07-06 확정).

### 신뢰 기기 30일 (remember_device 옵트인, 2026-07-08 사용자 요청)
- **토큰 위생 = refresh와 동일 원칙**: 쿠키엔 opaque 원문(`secrets.token_urlsafe(32)`), DB엔 HMAC-SHA256(+TOKEN_PEPPER) 해시만. 쿠키 `Path=/admin`(읽는 곳이 `/admin/login` 하나), SameSite=Strict.
- **비번 검증 '뒤'에만 검사**: 쿠키가 대체하는 건 TOTP(2차)뿐, 비번(1차)이 아니다. 순서가 뒤집히면 쿠키 탈취만으로 로그인된다.
- **절대 만료**(슬라이딩 갱신 없음): 접속해도 수명 연장 없음 - 탈취 시 노출창이 `expires_at`에서 캡(refresh 절대수명 cap과 같은 철학).
- **TOTP 재등록 시 자동 실효**: 유효 조건에 `created_at >= totp_confirmed_at` 포함 - 재등록(대개 기기 분실 복구)하면 옛 등록 시절 신뢰가 전부 무효. `created_at`은 server_default 대신 앱 시계로 명시해 판정 양변의 시계 스큐 오판 제거.
- 무효/만료 신뢰 쿠키는 에러 없이 정리 후 TOTP 단계로 폴백(편의 기능의 실패가 로그인을 막으면 안 됨).

### 승격 스크립트 보강 (B1 문서의 후속)
승격 전에 열린 세션은 전부 비-TOTP라 owner 권한을 얻으면 안 됨 → refresh 체인 일괄 revoke(+ 신뢰 기기 위생 revoke). 소셜 전용(비번 없음) 계정은 승격 거부 - 승격하면 `/admin/login` 1단계(비번)를 영원히 못 넘고 구글 로그인은 봉쇄돼 로그인 경로가 0개(락아웃).

### 비열거·rate limit
1단계 실패는 미존재(더미 해시로 타이밍 평탄화)/틀린 비번/비-owner/탈퇴 전부 `/auth/login`과 같은 문구의 401로 수렴. 4개 엔드포인트 전부 IP 5회/분(M1 `RateLimit` 재사용) - 6자리 brute(10^6)는 5/분이면 비현실적.

---

### TOTP replay 방지 = totp_last_step 엄격 증가 + 조건부 UPDATE (#56, 2026-07-22 추가)

- `users.totp_last_step`(BIGINT NULL)에 성공 검증된 time-step을 기록, **매칭 step > last_step(엄격 증가)만 통과**. valid_window(±30s) 창 안에서 같은/이전 코드를 다시 제출하면 거부된다(RFC 6238 verifier 요구). confirm(등록)과 login(2단계)이 같은 컬럼을 공유 - 등록에 쓴 코드로 곧장 로그인 재사용 불가.
- `lib/totp.verify_code`를 **매칭 step(int) | None 반환**으로 재구현(pyotp `verify()`는 bool만 반환). 같은 창 순회 + 상수시간 `strings_equal`, ⚠️ 시각은 **aware UTC 고정**(naive를 넘기면 pyotp `timecode`가 `mktime` 로컬 해석 경로로 빠져 서버 TZ만큼 step이 밀린다).
- step 전진은 **조건부 UPDATE**(`WHERE last_step IS NULL OR last_step < :step`, rowcount 판정 - refresh 회전 선점 I1과 같은 패턴)로 원자화. 같은 코드 **동시 제출**(실시간 릴레이 race)도 행 락 + READ COMMITTED 재평가로 한쪽만 승자 - read-compare-write였다면 둘 다 통과하는 TOCTOU가 남는다.
- `setup_totp`가 `totp_last_step`을 리셋: step은 시크릿이 아니라 **시각 기반**이라 수동 복구(시크릿 분실 - 컬럼 NULL 후 재등록) 때 잔재가 이월되면 새 시크릿의 첫 confirm이 replay로 오거부될 수 있다(자가치유). 수동 복구 시엔 totp 3컬럼(secret·confirmed_at·last_step)을 함께 NULL(models/user.py 주석).
- 검증(2026-07-22): pytest 전체 397 그린(신규 6: matched-step 창 단위 + replay 400·다음 창 통과·cross-endpoint 재사용 거부·동시 단일 승자·setup 리셋), ruff·alembic check(스크래치 DB) 클린. 마이그레이션 `e8ce7c708538`(nullable 컬럼 추가 1개).

## 4. 후속 (의도적 보류)

| 항목 | 상태 |
|------|------|
| TOTP 코드 replay(같은 30s 창 재사용) 방지 | ✅ 2026-07-22 구현 완료(#56) - §3 해당 절 |
| 만료 `trusted_devices` 행 정리 | #57 죽은 토큰 정리 잡에 합류 |
| TOTP 백업 코드 | 미도입 - 분실 복구는 운영자 DB 조작(DECISIONS) |

---

## 5. 검증

- `uv run pytest` 전체 148 그린(신규 45: 등록 게이트·재등록·잘못된 코드·비열거 응답 동일성·신뢰 기기 생략/만료/재등록 실효/비번 선행·승격 revoke)
- `uv run ruff check`·`alembic check` 클린
- 강 모델 보안 리뷰(Opus) 통과: Critical/Major 0, Minor 1 반영
