# 이메일 발송 서비스 (M1 그룹 E - E1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 E - E1 |
| 작성 시점 | M1 E1 (2026-06-06) |
| 상태 | 구현 완료, 단위 테스트 9개 통과 + 실제 발송 검증 |
| 관련 문서 | [IMPLEMENTATION_AUTH_ENDPOINTS.md](./IMPLEMENTATION_AUTH_ENDPOINTS.md)(signup 호출부), [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) |

C 그룹의 **계약 스텁(no-op)** 을 실제 Resend HTTP 발송으로 채운 작업. 인증 토큰의 발급·해싱은 C 그룹(`create_email_verification`)에서 끝났고, E1은 그 토큰을 **메일로 실어 보내는 IO 계층**만 담당한다. 시그니처/호출부(`signup`이 BackgroundTasks로 호출)는 그대로다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/services/email_service.py` | `_send`(Resend 호출) + 메일 템플릿 2종 + `send_verification_email`/`send_already_registered_email` |
| `backend/src/config.py` | `resend_api_key`(SecretStr), `email_from` 필드 |
| `backend/src/main.py` | production & 키 미설정 시 기동 1회 경고 |
| `backend/.env.example` | `RESEND_API_KEY`, `EMAIL_FROM` |
| `backend/tests/test_email_service.py` | 단위 테스트 9개 |

새 의존성 없음 (`httpx`는 HIBP에서 이미 사용 중).

---

## 2. 발송 흐름

```
signup(신규)
  -> create_user + create_email_verification(raw_token 발급, DB엔 HMAC 해시 저장)  [C 그룹]
  -> session.commit()
  -> background_tasks.add_task(send_verification_email, email, raw_token)          [E1]
        -> _send(to, subject, _verification_html(verify_url))
              -> POST https://api.resend.com/emails  (Bearer)
```

- **원문 토큰은 메일 링크에만**, DB에는 HMAC-SHA256(+`TOKEN_PEPPER`) 해시만 저장(C 그룹 정책). 검증(E2)은 입력 토큰을 동일 해시해 대조.
- 인증 링크: `{APP_BASE_URL}/auth/verify-email?token={raw}` -> 프론트 G4 페이지가 받아 E2 호출. **G4/E2 미구현 동안 클릭 시 404가 정상**(E1은 "메일 도착"까지가 DoD).
- **BackgroundTasks(응답 후 실행)**: 메일 발송 실패가 가입을 롤백하지 않고, 발송 지연이 HTTP 응답 시간에 섞이지 않아 **비열거 타이밍에도 영향 없음**(신규/중복 양쪽 다 post-response).

---

## 3. fail-open (가용성 우선)

발송은 가입을 막지 않는다. HIBP와 동일 철학.

```python
async def _send(to, subject, html):
    api_key = settings.resend_api_key.get_secret_value()
    if not api_key:
        logger.warning("email_send_skipped_no_api_key", to=_mask_email(to))
        return                                   # 키 없으면 no-op
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(_RESEND_API_URL, headers=..., json=...)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("email_send_failed_fail_open", to=_mask_email(to), error=str(exc))
```

- 키 미설정 / HTTP 오류 -> 경고 로그 + 무시. 미수신은 E3 재발송으로 복구.
- **단, production & 키 미설정이면 기동 시 1회 경고**(`main.py` lifespan) -> 프로덕션에서 전 유저 메일이 조용히 안 나가는 silent-failure 방지.

---

## 4. 보안

- **HTML 인젝션 방어**: 메일 HTML에 user input(닉네임·이메일 등) 미삽입. URL은 `html.escape`로 이스케이프(`test_verification_html_escapes_url`로 회귀 방어).
- **비로깅**: 원문 토큰·인증 URL을 절대 로깅하지 않음. 로그에는 마스킹 이메일(`_mask_email`) + 이벤트명만.
- **비열거**: 중복 가입 경로도 `send_already_registered_email`로 **동일 HTTP 응답**, 차이는 메일 내용뿐 -> 회원 여부는 수신함 주인만 인지(C 그룹 정책의 발송 측 구현).
- **dev 발신 제약**: `onboarding@resend.dev`는 Resend 테스트 모드라 **본인 Resend 계정 이메일로만** 발송됨. 임의 주소는 Resend가 거부하고 fail-open이 삼켜 "에러 없이 미수신"이 되니, dev 검증은 본인 메일로 가입할 것.

---

## 5. 검증

- `uv run pytest tests/test_email_service.py` 9개 통과. `httpx.AsyncClient.post`를 monkeypatch해 실제 발송 없이 payload/링크/이스케이프/fail-open 검증.
- **실제 발송 검증 (2026-06-06)**: 본인 메일로 가입 -> `POST api.resend.com/emails 200 OK` -> 인증 링크 메일 **수신함 도착** 확인. E1 DoD 충족.

| 테스트 | 확인 |
|--------|------|
| `test_send_skips_when_no_api_key` | 키 미설정 시 post 미호출(no-op) |
| `test_send_calls_resend_when_api_key_set` | payload `to`/`subject` 정확 |
| `test_send_uses_bearer_auth` | `Authorization: Bearer <key>` |
| `test_send_fail_open_on_http_error` | HTTPError 시 예외 미전파 |
| `test_verification_email_token_in_url` | 인증 HTML에 토큰이 verify-email URL로 포함 |
| `test_verification_email_to_address` | 수신자 정확 |
| `test_already_registered_email_has_login_link` | 중복 안내 메일에 로그인 링크 |
| `test_already_registered_email_to_address` | 수신자 정확 |
| `test_verification_html_escapes_url` | URL 특수문자 이스케이프(인젝션 방어) |

---

## 6. 제약 / 후속

- **메일 링크는 E2/G4 전까지 404** - `GET /auth/verify-email`(E2) + 프론트 `/auth/verify-email`(G4)가 생겨야 클릭이 동작. 의도된 상태.
- **커스텀 도메인 DKIM**: dev는 onboarding 도메인. 프로덕션 발신·스팸 분류 회피는 도메인 SPF/DKIM 인증 후 `EMAIL_FROM`만 교체(코드 변경 없음).
- **후속**: E2(토큰 검증 -> `is_email_verified=True`), E3(재발송 + `require_verified_email` 의존성 골격). `M1_foundation.md` 그룹 E 참조.
