# HttpOnly 쿠키 발급/제거 유틸 (M1 그룹 B - B3)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 B - B3 |
| 작성 시점 | M1 B3 (2026-06-04) |
| 상태 | 구현 완료, 단위 테스트 통과 |
| 관련 문서 | [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md), [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md), study `cookie-security` |

B2 토큰 프리미티브를 클라이언트로 내보내는 운반 계층. 토큰은 **응답 바디로 내리지 않고 HttpOnly 쿠키로만** 전달한다(localStorage 경로 차단). 엔드포인트는 아직 없으므로(C 그룹) 이 유틸은 `Response` 객체에 쿠키를 set/clear하는 순수 함수로 제공하고, C2 로그인·C3 로그아웃·C4 갱신·D1 OAuth가 호출한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/auth.py` | `set_auth_cookies`/`clear_auth_cookies` + `access_cookie_name()` + 상수 `REFRESH_COOKIE_NAME`/`REFRESH_COOKIE_PATH` |
| `backend/src/config.py` | `cookie_secure` computed 필드 (env 분기) |
| `backend/tests/test_cookies.py` | 단위 테스트 6개 |

새 의존성 없음 (`fastapi.Response`만 추가 import).

---

## 2. 쿠키 정책

| 쿠키 | 이름 | SameSite | Path | Max-Age | HttpOnly | Secure | `__Host-` |
|------|------|----------|------|---------|----------|--------|-----------|
| access | `access_token` (운영 `__Host-access_token`) | Lax | `/` | 15분 | ✅ | env 분기 | 운영 한정 |
| refresh | `refresh_token` | Strict | `/auth/refresh` | 7일 | ✅ | env 분기 | ✗ |

- **access=Lax**: 일반 네비게이션(외부 링크 클릭 진입 등)에 동반돼야 로그인 상태가 유지됨.
- **refresh=Strict + Path 제한**: 갱신/로그아웃 외 요청엔 refresh를 아예 안 실어 노출 표면 축소. CSRF 내성도 강함.
- Max-Age는 `settings.jwt_access_token_expire_minutes`/`jwt_refresh_token_expire_days`에서 산출(하드코딩 금지, JWT 만료와 일관).

---

## 3. `Secure` 환경 분기 + `__Host-` 프리픽스

### 3.1 `cookie_secure` (config)
```python
@computed_field
@property
def cookie_secure(self) -> bool:
    return self.env != "development"
```
로컬 http(dev)는 `False`, 그 외는 `True`. Secure 쿠키는 https에서만 전송되므로 로컬에서 True면 쿠키가 아예 안 실린다. 코드에 `True`/`False`를 박지 않고 config 값으로 결정.

### 3.2 `__Host-` × Secure 충돌 (핵심 함정)
`__Host-` 프리픽스는 브라우저가 **Secure + Path=/ + Domain 미지정**을 강제해 하위도메인발 쿠키 주입을 막는다. 그러나 **프리픽스 자체가 Secure를 요구**하므로 로컬 http에서 `__Host-` 쿠키를 set하면 브라우저가 거부 → 로그인이 깨진다.

→ **쿠키 이름을 환경 분기**한다:
```python
def access_cookie_name() -> str:
    return "__Host-access_token" if settings.cookie_secure else "access_token"
```
- 운영(Secure): `__Host-access_token`
- 로컬(http): `access_token` (프리픽스 없음)

C 그룹에서 쿠키를 **읽을 때도 이 함수로 이름을 맞춰야** dev/운영이 일관된다.

### 3.3 refresh는 왜 `__Host-` 제외인가
`__Host-`는 `Path=/`를 강제하는데, refresh는 노출 축소를 위해 `Path=/auth/refresh`로 제한한다. 둘은 양립 불가 → access에만 프리픽스, refresh는 Path 제한을 택했다.

---

## 4. set / clear 동작

- `set_auth_cookies(response, access, refresh)`: 위 표대로 두 쿠키 set.
- `clear_auth_cookies(response)`: 두 쿠키를 `delete_cookie`(Max-Age=0)로 만료. **브라우저가 삭제하려면 set 때와 key·path·secure·samesite가 일치**해야 한다 - 특히 refresh의 `Path=/auth/refresh`. 그래서 clear도 같은 이름 함수(`access_cookie_name()`)·같은 Path·같은 secure 값을 쓴다.

---

## 5. 검증

`uv run pytest` 23개 통과(기존 17 + 쿠키 6). 엔드포인트 없이 `Response`의 `raw_headers`에서 `set-cookie`를 파싱해 플래그를 검증.

| 테스트 | 확인 |
|--------|------|
| `test_access_cookie_name_dev` | dev는 프리픽스 없는 `access_token` |
| `test_access_cookie_name_prod` | 운영은 `__Host-access_token` |
| `test_set_cookies_dev_flags` | dev: Secure·프리픽스 없음, access=Lax/Path=/, refresh=Strict/Path 제한, 둘 다 HttpOnly |
| `test_set_cookies_prod_flags` | 운영: 둘 다 Secure, access만 `__Host-`, refresh는 프리픽스 없음 |
| `test_set_cookies_max_age` | access=15분·refresh=7일이 Max-Age로 반영 |
| `test_clear_cookies_expire` | 두 쿠키 Max-Age=0 만료 + Path 일치 |

> env 분기 검증은 `monkeypatch.setattr(settings, "env", ...)`로 `cookie_secure`를 양쪽 다 태운다.

---

## 6. 제약 / 후속

- **same-site 전제 (Critical)**: SameSite=Lax/Strict라 FE/Admin/API가 한 eTLD+1(Caddy 단일 도메인) 아래 묶여야 쿠키가 전송된다. API를 별도 도메인으로 분리하면 로그인이 붕괴 → M0 Caddy 단일 도메인 구조 유지 필수. (로컬 `localhost:8000` 직접 호출도 same-site라 OK. 포트 차이는 무관.)
- **유니코드/NFC, 백업코드 등은 범위 밖**. 쿠키 운반만.
- **후속**: C2(로그인 시 `set_auth_cookies` + refresh insert), C3(로그아웃 `clear_auth_cookies` + revoke), C4(`/auth/refresh` 회전 후 재set), C5(`/auth/me`가 `access_cookie_name()`으로 쿠키 읽기), D1(OAuth 콜백 set). `M1_foundation.md` 참조.
