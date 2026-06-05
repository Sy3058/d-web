# SECURITY - M1 인증 보안 결정

| 항목 | 내용 |
|------|------|
| 영역 | BE (+ FE 쿠키 처리) |
| 대상 마일스톤 | M1 (인증: 이메일 + 구글) |
| 상태 | A1·B1~B3·C·E1·E2 구현 완료(~2026-06-06), D(OAuth)·E3·F(rate limit)는 설계 확정·구현 전. M1 착수 시 DECISIONS.md "보안 결정"에 이관 |
| 작성 | 2026-05-31 (Opus 설계 리뷰 세션) |
| 근거 | OWASP ASVS, OAuth 2.0 Security BCP, DB_SCHEMA §1, PRD §4.2 |

---

## 개요

M1 인증 설계 리뷰에서 확정한 보안 결정을 한곳에 모은 문서. "가능한 한 보안성 높은 방향"이라는 방침 아래, 단일 작가 개인 사이트 + 소형 VPS(Hetzner CX22) 제약을 함께 고려해 결정했다. 각 항목은 M1_foundation.md의 해당 작업 카드(A1~G5)와 연결된다.

전제: **JWT는 HttpOnly 쿠키 전용**(localStorage 금지), **금액·권한 검증은 서버**, **시크릿 하드코딩 금지**(CLAUDE.md "절대 금지"와 정합).

---

## 1. 토큰 저장 모델

- **access = JWT** (HS256 + `SECRET_KEY`, 15분). stateless. payload는 `sub`(user_id)·`typ=access`·`exp`만, **PII(이메일 등) 미포함**. 단일 서버라 비대칭키 불필요.
- **refresh = opaque 랜덤** (`secrets.token_urlsafe(32)`, 256bit). **JWT 아님** - DB 대조가 어차피 필요하므로 JWT로 만들 이유 없음.
- **refresh 저장 = HMAC-SHA256(token, key=`TOKEN_PEPPER`)**. DB(`refresh_tokens.token_hash`)엔 해시만.
  - 결정적 해시라 `WHERE token_hash = hmac(입력)` **직접 조회 가능** → 쿠키 값은 토큰 원문 그대로(row_id prefix 불필요).
  - 토큰 원문은 **항상 고엔트로피 랜덤**(256bit) - 빠른 해시여도 brute-force가 물리적으로 불가. bcrypt 같은 느린 해시는 불필요(저엔트로피 추측을 막는 도구라 여기선 막을 게 없음).
  - `TOKEN_PEPPER`는 DB 밖 시크릿 → DB 단독 유출 시에도 오프라인 대조 불가. 이메일 인증 토큰(E1)도 동일 방식.

> bcrypt가 아닌 HMAC-SHA256을 쓰는 이유: 해시 속도는 입력 엔트로피에 맞춘다(study `secret-hashing`). 256bit 랜덤 토큰은 빠른 해시로도 안전하고, 결정적이라 직접 조회까지 된다. bcrypt는 비용(verify마다 CPU 블로킹)·복잡도(72byte 한도·salt 때문의 id 조회)만 늘고 추가 보안은 0.

## 2. 리프레시 토큰 회전 + 재사용 탐지

- 갱신마다 기존 refresh **revoke + 신규 발급(회전)**.
- 이미 revoke된(=회전 지난) 토큰이 다시 들어오면 **탈취 신호**로 간주 → 해당 유저 refresh **전체 revoke**(세션 강제 종료).
- 근거: OAuth 2.0 Security BCP의 refresh token rotation 권장.
- 회전 시 기존 revoke + 신규 발급은 **단일 트랜잭션**.
- **로그아웃 = 세션 전체 revoke (확정, 2026-06-05)**: refresh 쿠키가 `Path=/auth/refresh`라 `/auth/logout` 요청엔 전송되지 않아 무효화할 특정 토큰을 받을 수 없다. → access 쿠키로 유저를 식별해 그 유저 refresh를 **전체 revoke**(전 기기 로그아웃). 1인 개인 사이트라 단순·충분하고, access JWT에 session_id를 넣는 복잡도를 피했다. access 만료/무효면 쿠키만 clear(best-effort).

## 3. 쿠키 정책

- access: `HttpOnly + SameSite=Lax`, refresh: `HttpOnly + SameSite=Strict`.
- `Secure` 플래그 **환경 분기**: 로컬 http=False, 스테이징/프로덕션=True (config 값, 코드 분기 하드코딩 금지).
- 프로덕션 **`__Host-` 프리픽스** 적용 검토 (Secure + Path=/ + Domain 미지정 강제 → 하위도메인 쿠키 주입 방지). Path 제한과 상충하므로 access/refresh 중 적용 대상 선별.
- **단일 등록가능도메인(same-site) 배포 전제 [제약]**: SameSite=Lax/Strict는 cross-site에서 전송 안 됨. FE/Admin/API가 Caddy 리버스 프록시로 한 eTLD+1 아래 묶여야 작동(`admin.도메인`·`api.도메인`은 same-site, 포트 차이는 무관). **API를 별도 도메인으로 분리하면 인증이 깨짐** → M0 Caddy 단일 도메인 구조 유지 필수.
- 토큰을 **응답 바디로 내려 localStorage에 담는 경로 금지**.

## 4. 비밀번호 해싱

- **bcrypt cost=12** (argon2id 아님).
  - argon2id는 메모리 하드(해시당 수십 MiB)라 CX22(2 vCPU·4GB, DB+API+FE+Admin+Caddy 동거)에서 동시 로그인 시 메모리 압박. 파라미터를 낮추면 이점이 사라져 오히려 bcrypt보다 약해질 위험.
  - bcrypt는 CPU 바운드·~4KB로 풋프린트 작고 예측 가능. OWASP도 bcrypt(work factor ≥10) 허용.
  - **pepper + HIBP + lockout**가 더해져 bcrypt로도 충분히 강함.
  - cost=12가 **프로덕션 하드웨어에서 ~250~350ms** 되도록 배포 후 1회 측정·보정.
- **해싱 구조 (B1 구현 완료, 2026-06-02)**: OWASP pre-hash `bcrypt(base64(hmac_sha384(pw, PASSWORD_PEPPER)), gensalt(12))`. 라이브러리는 `bcrypt` 직접(5.x, passlib 아님). bcrypt 블로킹은 `anyio.to_thread`로 오프로드. `PASSWORD_PEPPER`는 `TOKEN_PEPPER`·`jwt_secret`과 별개 키, `SecretStr` 필수 설정. pre-hash라 pepper 로테이션 불가(교체 시 전 유저 재설정). 상세: [IMPLEMENTATION_PASSWORD_HASHING.md](./IMPLEMENTATION_PASSWORD_HASHING.md).
- 비번 정책: **8자 이상 + 영문·숫자·특수문자 각 1개 이상** (AUTH-01). 서버 검증 필수.
- **비번 최대 길이 상한**(예: 128자) - pre-hash로 bcrypt 72바이트 문제는 해소됨. 상한은 초장문 비번의 HMAC/CPU DoS 방지용.
- **유출 비번 차단 (HIBP)**: 가입/비번 변경(P1) 시 HaveIBeenPwned k-anonymity API(SHA-1 앞 5자리만 전송)로 유출 비번 거부. 외부 API 장애 시 **fail-open + 경고 로깅**.

## 5. 로그인 보호 (brute-force)

- **IP rate limit 5회/분** (PRD §4.2).
- **계정 단위 lockout + 지수 백오프**: IP 제한과 별개로 계정별 연속 실패 누적 시 잠금/지연 → 분산 IP로 한 계정 노리는 느린 brute-force 방어. 성공 시 카운터 리셋.
- **일반화 에러**: 이메일/비번 중 어느 쪽이 틀렸는지 구분 노출 금지(동일 메시지).
- **타이밍 평탄화**: 미존재 유저도 더미 해시 검증 후 동일 응답 시간.

## 6. 비열거(non-enumeration) 정책 - 인증 표면 전체

- 가입·로그인·비번재설정(P1)·재발송 등 **인증 전 모든 엔드포인트가 "회원/비회원"을 응답으로 구분하지 않는다.** 한 곳만 막으면 다른 곳에서 새므로 표면 전체 통일.
- **회원 여부를 아는 사람은 수신함 주인뿐** - 공격자는 HTTP 응답에서 아무것도 못 얻음.
- 가입: 신규는 미인증 user 생성 + 인증 메일, **중복은 user 생성 없이 "이미 가입된 계정" 안내 메일**(로그인/비번재설정 링크). **두 경우 HTTP 응답 동일**("입력하신 주소로 메일을 보냈어요").
- **응답 타이밍도 통일**(중복 경로에 bcrypt 더미 해시 등). 비번 정책/HIBP 위반은 이메일 존재와 무관하므로 422 가능.

## 7. 구글 OAuth (AUTH-04)

- **id_token 완전 검증**: 구글 OIDC `id_token`의 서명(JWKS)·`iss`·`aud`·`exp` 검증 후 신뢰. 프로필 무검증 신뢰 금지.
- **state(CSRF) + nonce(replay)** 발급·대조. 콜백에서 누락 시 CSRF/재생 취약.
- **open redirect 차단**: 로그인 후 복귀 경로(`next`/`redirect`)는 **same-origin 허용목록**으로만 통과.
- 소셜 가입 이메일은 **검증됨으로 간주** → `is_email_verified=True` 즉시 세팅.
- **자동 병합 금지 (Q6)**: 동일 이메일 비번 계정이 있어도 병합하지 않고 안내. 별도 계정 유지.
- 리다이렉트 URI/CORS는 `config.py`가 `APP_BASE_URL`에서 조립(env 직박 금지).
- 카카오 OAuth(AUTH-03)는 비즈앱 사업자 서류 필요 → M1.5 이후 (Q20).

## 8. 이메일 인증 (AUTH-08)

- 인증 토큰은 **고엔트로피 1회용**, **at-rest 해시 저장**(HMAC-SHA256 + pepper, refresh와 동일 키 정책). 메일 링크엔 원문, DB엔 해시만. 검증은 입력 토큰을 동일 해시해 대조.
- 만료 **1시간**, 사용 시 `used_at` 세팅, 재사용 차단.
- **검증 = `POST /auth/verify-email`** (E2, GET 아님): 상태 변경 + 메일 스캐너/링크 프리뷰의 GET prefetch가 일회용 토큰을 클릭 전에 소비하는 것 차단(OWASP). 토큰은 **body**로 받아 URL/쿼리 로깅 회피. study `email-verification-link-safety`.
- 실패(무효/만료/사용됨)는 **비구분 단일 메시지**(400), **멱등**(이미 인증된 유저 재검증 시 `email_verified_at` 보존). `email_verifications.token` **UNIQUE 인덱스**(결정적 해시 직접 조회 + 중복 방지).
- **`require_verified_email` 의존성**은 M1에서 가드 함수만 제공, **실제 차단 적용은 M3(결제)·M4(댓글)**. 열람은 미인증도 허용(Q5).

## 9. 시크릿 / 로깅

- `SECRET_KEY`(JWT 서명)와 **pepper는 별도 키**로 `.env` 관리, 하드코딩 금지. pepper 로테이션 시 재해싱 전략 필요.
- **개인정보(이메일 등) plaintext 로깅 금지**, 토큰 로깅 금지. 마스킹 규칙(M0 B4) 적용.

---

## 결정 보류 (작업 직전 확정)

- OAuth state/nonce 저장 위치 (단기 HttpOnly 쿠키 vs 서버 측 임시 저장)
- rate limit / lockout 카운터 저장소 (인메모리 vs Redis - 다중 인스턴스 전환 시)
- `__Host-` 프리픽스 적용 대상 (access/refresh 중)
- 회전 시 refresh **절대 수명 cap** (예: 회전해도 30일 상한)
- HMAC pepper 로테이션 절차

---

## 관련 문서

- 마일스톤: M1_foundation.md (A1 모델 / B1 해싱 / B2 토큰 / B3 쿠키 / C1 비열거·HIBP / C4 회전 / D1 OAuth / E1·E2 이메일 인증 / F1 rate limit·lockout)
- DECISIONS.md: "보안 결정"(2FA·이메일 인증·환경 베이스 URL) - M1 착수 시 본 문서 내용 이관
- DB_SCHEMA.md: §1 계정/인증 도메인 (users, oauth_accounts, refresh_tokens, email_verifications)
- CLAUDE.md / backend/CLAUDE.md: "절대 금지" (JWT localStorage·CORS 와일드카드·시크릿 하드코딩)
