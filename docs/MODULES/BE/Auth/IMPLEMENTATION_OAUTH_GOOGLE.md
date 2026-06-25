# 구글 OAuth 로그인 (BFF 표준) (M1 그룹 D - D1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 D - D1 (구글 소셜 로그인) |
| 작성 시점 | M1 D1 (2026-06-15) |
| 상태 | 구현 완료, `pytest` 80개 통과 + 수동 브라우저 E2E 성공 + Opus 자가 검증(council 5렌즈 + fix) |
| 관련 문서 | [DECISIONS.md](../../../DECISIONS.md) "구글 OAuth: 백엔드가 콜백 수신", [IMPLEMENTATION_COOKIE.md](./IMPLEMENTATION_COOKIE.md)(`__Host-`·쿠키 헬퍼), [IMPLEMENTATION_AUTH_DOMAIN_MODEL.md](./IMPLEMENTATION_AUTH_DOMAIN_MODEL.md)(`OAuthAccount` A1), [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md)(refresh 프리미티브), [IMPLEMENTATION_REFRESH_ROTATION_RACE.md](./IMPLEMENTATION_REFRESH_ROTATION_RACE.md)(DB 권위 동시성 패턴) |

구글 OAuth 로그인을 **BFF 표준(백엔드가 redirect_uri 콜백을 받는다)**으로 구현. 브라우저(JS)가 토큰을 직접 교환·보관하는 순수-SPA식은 우리 규칙(HttpOnly만, JS에 토큰 금지)과 충돌하므로 폐기하고, 백엔드가 코드 교환·id_token 검증·유저 처리·인증 쿠키 발급을 모두 수행한다. `__Host-` 인증 쿠키는 API 호스트(백엔드)가 자기 응답에서 Set-Cookie 해야 하므로 BFF와 자연 정합.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/config.py` | `api_base_url` 신설, `google_redirect_uri`/`kakao_redirect_uri`를 `API_BASE_URL` 기준 조립 |
| `backend/src/lib/exceptions.py` | `OAuthError`(베이스)/`OAuthExchangeError`/`OAuthEmailExistsError` |
| `backend/src/lib/auth.py` | `oauth_tx` 단명 서명 쿠키 헬퍼(set/read/clear), SameSite=Lax, Path=/auth |
| `backend/src/services/oauth_service.py` | authorize URL 생성·코드 교환·id_token 검증·`resolve_google_user` |
| `backend/src/routers/oauth.py` | `GET /auth/login/google`, `GET /auth/callback/google` |
| `backend/src/main.py` | 라우터 등록 |
| `backend/tests/test_oauth.py` | 통합 테스트 10개 |
| `backend/pyproject.toml`,`uv.lock` | `google-auth` 의존성 |

마이그레이션 없음 - `OAuthAccount` 테이블은 A1에서 생성됨(`alembic check` = No new upgrade operations).

---

## 2. 흐름 (BFF)

```
GET /auth/login/google
  state(CSRF)+nonce(replay) 생성 → oauth_tx 서명쿠키 set → 구글 authorize로 302
구글 동의
GET /auth/callback/google?code&state
  oauth_tx 읽기 + state constant-time 비교(불일치/누락 → oauth_failed)
  exchange_code(code)          → 토큰 엔드포인트에서 id_token 교환(client_secret, 서버측)
  verify_id_token(id_token)    → google-auth로 서명(JWKS)/aud/iss/exp 검증 + nonce 수동 대조
  resolve_google_user(claims)  → 유저 확정 + access/refresh 발급
  set_auth_cookies + clear_oauth_tx → app_base_url 홈으로 302
```

- 콜백은 top-level 브라우저 내비게이션이라 JSON이 아니라 **302 redirect**로 응답. 실패는 비열거 generic 코드(`oauth_failed`/`email_exists`)를 프론트 로그인 페이지 `?error=`로 넘긴다.
- 쿠키는 반환하는 `RedirectResponse` 객체에 직접 set(주입된 `Response`에 set하면 실제 반환 객체엔 안 실림).

---

## 3. 핵심 결정

- **콜백 수신 = 백엔드(BFF)**: 업계 표준(NextAuth/Django allauth/Spring Security/Passport)이 전부 백엔드 콜백. IETF "OAuth 2.0 for Browser-Based Apps" BCP도 토큰을 JS에 두지 말 것을 권장. 초기 문서(`callback.astro`)는 폐기.
- **state + nonce를 `oauth_tx` 서명쿠키로 stateless 운반**: `state`=CSRF, `nonce`=id_token replay. `jwt_secret`로 서명한 단명 JWT 쿠키(600s)에 담아 서버 세션 저장소 없이 처리. **SameSite=Lax** - 구글 복귀는 cross-site top-level GET이라 Strict면 쿠키가 안 실림(의도된 예외). Path=/auth로 노출 최소화.
- **PKCE 제외**: 공식 server-side(web-server) 플로우는 state 기반이고, 컨피덴셜 클라이언트(client_secret 보유)라 코드 탈취돼도 secret 없이는 교환 불가 → PKCE 이득 미미. `access_type=offline` 미설정(로그인엔 id_token만 필요, 구글 API 지속 호출 없음).
- **id_token 로컬 검증**: 코드 교환은 우리 서버가 TLS로 직접 하지만, id_token 서명은 공개키(JWKS)로 로컬 검증(`google-auth verify_oauth2_token`, `clock_skew_in_seconds=10`). JWKS fetch는 sync 네트워크라 `anyio.to_thread`로 오프로드(이벤트 루프 비블로킹). transport는 이미 설치된 urllib3 기반(requests 의존 회피). nonce는 라이브러리가 안 보므로 수동 대조.
- **자동 병합 금지(Q6)**: 같은 이메일의 비-소셜(또는 다른 provider) 계정이 있으면 자동 병합은 계정 탈취 벡터라 거부(`email_exists`). open redirect 차단(복귀경로 파라미터 미지원, 홈 고정).
- **`email_verified=false` 신규 가입 거부 (D1 fix, Option A)**: 로그인 성공(계정 소유 증명) ≠ 이메일 검증. @gmail은 항상 true지만 **외부 IdP 페더레이션 Workspace** 등은 구글이 이메일 소유를 검증 못 해 `email_verified=false`가 올 수 있다. 이 값을 신뢰해 가입시키면 타인 이메일 도용 위험 → 신규 가입만 거부(`oauth_failed`). 기존 유저(이미 OAuthAccount 보유)는 위 분기에서 먼저 처리돼 영향 없음. **방식 A**: `hd`(hosted domain) 전체 차단이 아니라 `email_verified`만 본다 → 검증된 회사계정은 통과.
- **동시 가입 경합 회복 (D1 fix)**: `resolve_google_user`는 select-then-insert라 동시 콜백 2개가 같은 `sub`로 둘 다 "신규"로 판단하는 check-then-act race가 있다. `User`+`OAuthAccount` insert를 `try/except IntegrityError`로 감싸, 패자는 `rollback` 후 승자 레코드를 재조회해 **로그인으로 회복**한다. DB UNIQUE 제약(`users.email`, `oauth_accounts (provider, provider_id)`)이 최종 권위. → [IMPLEMENTATION_REFRESH_ROTATION_RACE.md](./IMPLEMENTATION_REFRESH_ROTATION_RACE.md) §7 백로그의 "signup 동시 중복가입 IntegrityError" 항목을 소셜 가입 쪽에서 소진(일반 이메일 가입 경로도 `be/fix/signup-duplicate-race`에서 같은 패턴으로 닫음).

> **신규 행 경합 vs 기존 행 상태전이**: refresh 회전(I1)은 *기존 행*의 상태 전이라 조건부 `UPDATE … WHERE revoked_at IS NULL` + rowcount 선점을 쓴다. OAuth 가입은 *새 행 생성*이라 바꿀 기존 행이 없어 조건부 UPDATE가 안 맞고, 대신 UNIQUE 제약 + insert-then-select가 같은 역할(DB 단일 직렬화 권위)을 한다. study `db-atomic-claim` "UNIQUE 제약 방어선".

---

## 4. 검증

`uv run pytest` 80개 통과(기존 70 + OAuth 10), `ruff check`/`format --check` clean, `alembic check` 클린(모델 변경 없음). 수동 dev E2E로 실제 구글 로그인 성공 확인.

| 테스트 | 확인 |
|--------|------|
| `test_login_redirects_to_google_and_sets_tx_cookie` | authorize 302 + scope/response_type/redirect_uri + oauth_tx 쿠키 |
| `test_callback_creates_new_user` | 신규 유저+OAuthAccount 생성, 비번 NULL, 인증 쿠키 set |
| `test_callback_existing_account_logs_in` | 기존 OAuthAccount 재로그인(중복 생성 없음) |
| `test_callback_email_exists_rejected` | 같은 이메일 비-소셜 계정 → `email_exists`(Q6) |
| `test_callback_email_unverified_rejected` | `email_verified=false` 신규 → `oauth_failed`, 유저/계정 미생성 |
| `test_callback_state_mismatch` / `test_callback_without_tx_cookie` | state 위조/oauth_tx 누락 → CSRF 차단 |
| `test_callback_verify_failure` / `test_callback_user_consent_denied` | id_token 검증 실패/동의 거부 → `oauth_failed` |
| `test_resolve_race_recovers_to_login` | 동시 가입 경합: IntegrityError → 승자 레코드로 로그인 회복(User 1명) |

외부 호출(`exchange_code`/`verify_id_token`)은 목으로 막고 라우터 + `resolve_google_user` DB 로직을 검증.

---

## 5. 제약 / 후속

- **prod 배포 시**: 구글 콘솔에 prod `redirect_uri`(`{API_BASE_URL}/auth/callback/google`) 등록 + `API_BASE_URL`을 배포 토폴로지(단일호스트 path-routed vs api 서브도메인)에 맞게 설정. SameSite 쿠키가 실리려면 app/api가 prod에서 같은 eTLD+1이어야 한다([IMPLEMENTATION_COOKIE.md](./IMPLEMENTATION_COOKIE.md)).
- **카카오 OAuth**: 같은 BFF 구조로 후속(provider 추상화는 2개 생기면 그때, 지금은 구글 단일). `kakao_redirect_uri`는 config에 이미 조립됨.
- **계정 병합 UX**: `email_exists` 거부 시 프론트는 "이미 가입된 이메일입니다, 비밀번호로 로그인 후 연동" 안내만. 실제 연동(소셜↔비번 계정 link) 플로우는 범위 밖.
- **exchange 실패 관측**: 토큰 엔드포인트 4xx는 `HTTPStatusError` 분기에서 status+응답 바디를 로깅(`invalid_grant`/`redirect_uri_mismatch` 원인 추적). 바디에 secret/PII 없음.
