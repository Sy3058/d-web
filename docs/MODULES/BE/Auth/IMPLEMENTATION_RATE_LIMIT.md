# 인증 표면 rate limit (M1 그룹 I - I2 / 그룹 F - F1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 I - I2, 그룹 F - F1 (council 리뷰 fix, 이슈 #28) |
| 작성 시점 | M1 I2 (2026-06-11) |
| 상태 | IP rate limit 구현 완료, `pytest` 61개 통과 + Opus 자가 검증(코드 Critical/Major 없음). 계정 lockout은 후속 PR로 분리 |
| 관련 문서 | [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §5, study `rate-limiting` |

council 리뷰(2026-06-06)가 식별한 선존 이슈: `/auth/login`·`signup`·`resend-verification`이 **무제한**이라 브루트포스/이메일 폭탄에 노출. IP 단위 rate limit을 부착하고, 재발송/무효화 조회가 seq scan이던 `email_verifications.user_id` 인덱스를 함께 보강한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/lib/rate_limit.py` | `limits.aio` MemoryStorage + MovingWindow + `RateLimit(limit, scope)` 의존성 (IP 키, 429+Retry-After), 테스트용 `reset_rate_limits` |
| `backend/src/routers/auth.py` | `login`/`signup`/`resend-verification`에 `dependencies=[Depends(RateLimit("5/minute", scope=...))]` |
| `backend/src/models/user.py` | `EmailVerification` `idx_email_verifications_user_id` 인덱스 |
| `backend/migrations/versions/20260611_1102_email_verifications_user_id_index.py` | 인덱스 마이그레이션 `fefbcb3265c0` (forward-only, down=`97b9912aa03e`) |
| `backend/tests/conftest.py` | autouse `_reset_rate_limits`(동기 rebind) |
| `backend/tests/test_rate_limit.py` | 6회째 429+Retry-After, scope 독립 (2개) |

새 의존성: `limits>=5.8.0` (+ 전이 `deprecated`, `wrapt`).

---

## 2. 구현 방식 결정: `limits` 직접 (slowapi 아님)

| 후보 | 판단 |
|------|------|
| slowapi 0.1.9 | ❌ 2024-02 이후 정체·자칭 alpha. 데코레이터 + 엔드포인트마다 `request: Request` 주입 강제 + 전역 예외 핸들러 등록 → 우리 `Depends` 합성 패턴(`get_current_user` 등)과 이질 |
| **`limits` 직접** | ✅ slowapi가 내부에서 쓰는 코어. 활발히 유지보수 + async 네이티브(`limits.aio`). `Depends(RateLimit(...))`로 기존 idiom에 합성, 429 응답 모양·키 함수 완전 제어. 분산 한도는 storage를 `async+redis://`로 교체(코드 한 줄) |
| 완전 자체 dict | ❌ 슬라이딩 윈도우 로직·락 재발명 |

```python
class RateLimit:
    def __init__(self, limit: str, scope: str) -> None:
        self._item = parse(limit)        # "5/minute" → RateLimitItem
        self._scope = scope              # 엔드포인트별 독립 버킷
    async def __call__(self, request: Request) -> None:
        if not await _limiter.hit(self._item, self._scope, _client_key(request)):
            raise HTTPException(429, detail=..., headers={"Retry-After": str(self._item.get_expiry())})
```

---

## 3. 핵심 결정

- **키 = 클라이언트 IP only** (이메일 미혼합): 의존성이 핸들러 로직 '전에' 429를 던지므로 회원 존재 여부와 무관 → **비열거 중립**(account-enumeration). 이메일을 키에 섞으면 한도/헤더 차이로 회원 여부가 샌다.
- **엔드포인트별 scope 버킷**: `hit(item, scope, ip)`의 scope로 login 5/분과 signup 5/분을 분리(한 엔드포인트 소진이 다른 엔드포인트를 막지 않음).
- **계정 lockout은 후속 분리**: (a) 존재 계정만 잠겨 "잠김" 응답이 회원 확정 신호가 되는 비열거 충돌, (b) 카운터를 I1 교훈상 인메모리가 아닌 DB(`users.failed_login_attempts`/`locked_until`)에 둬야 신뢰 가능 → 설계·council 리뷰가 별도 필요. 이 PR은 IP rate limit + 인덱스로 한정(Small-PR).
- **테스트 격리 = 동기 rebind**: 모듈 전역 storage가 프로세스 공유라 테스트 누적 hit이 다른 테스트를 429로 깬다. `reset_rate_limits()`가 storage/limiter를 새 인스턴스로 교체(생성은 루프 불필요한 동기 연산 → 동기 테스트 `test_cookies`와도 호환). `storage.reset()`은 async라 동기 테스트와 충돌해 채택 안 함.

---

## 4. 알려진 한계 (정직성)

- ⚠️ **멀티워커**: `MemoryStorage`는 프로세스별이라 N워커면 실효 한도 ≈ N×limit (I1 "인메모리 앱 상태는 워커 간 신뢰 불가"와 동형). coarse anti-automation 속도 제한이라 초기 단일/소수 워커에선 허용. 엄밀 분산 한도는 Redis storage.
- ⚠️ **프록시 IP (배포 필수, 신뢰 경계 2겹)**: Caddy 뒤에서 `request.client.host`가 실제 클라이언트 IP가 되려면 **둘 다** 필요하다.
  - (1) uvicorn `--proxy-headers --forwarded-allow-ips=<caddy>`: 외부가 uvicorn에 직접 연결해 XFF 위조하는 경로 차단(Caddy 우회 방지). 미설정 시 모든 요청이 프록시 IP 한 키 → **전역 5회/분 = 자기 DoS**.
  - (2) Caddy가 `X-Forwarded-For`를 **overwrite로 정화** (`header_up X-Forwarded-For {http.request.remote.host}`): XFF는 프록시마다 append되는 리스트라, append만 하면 클라가 보낸 위조값이 왼쪽에 남고 uvicorn 옛 기본은 leftmost를 채택해 그 위조값을 믿을 수 있다. overwrite로 위조값을 버리고 실제 peer만 남긴다.
  - (1)만으론 Caddy를 통과시킨 위조 XFF 밀반입을 못 막는다. infra(Dockerfile/compose + Caddyfile)에서 둘 다 설정해야 실효.
- 📌 `Retry-After`는 `get_expiry()`(윈도우 60초 전체)로 - 정확한 잔여시간 아닌 안전 상한. 단순성 우선.
- 📌 `async_client` 픽스처가 `test_auth_endpoints`와 중복 - I4(conftest 정리)에서 승격하며 통합 예정.

---

## 5. 검증

`uv run pytest` 61개 통과(기존 59 + I2 2), `ruff check` clean, `alembic check` 클린(single head), Opus 자가 검증 코드 Critical/Major 없음.

| 테스트 | 확인 |
|--------|------|
| `test_login_sixth_request_returns_429` | 미존재 이메일 5회 401 → 6회째 429 + Retry-After (비열거 중립 경로) |
| `test_rate_limit_scopes_are_independent` | login 버킷 소진(429) 후에도 signup은 독립 버킷이라 200 |
