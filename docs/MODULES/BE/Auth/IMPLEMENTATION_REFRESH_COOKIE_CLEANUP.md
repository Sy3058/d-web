# Refresh 인증 쿠키 정리와 동시 회전 세션 보존

## 문제와 범위

기존 `/auth/refresh`는 토큰 누락·무효·만료의 401에서 쿠키를 정리하지 않았고, 재사용 경로는 주입된 Response에 쿠키 삭제를 넣은 뒤 HTTPException을 던져 실제 응답에 삭제 헤더가 전달되지 않았다. 이 때문에 FE 세션 복구 후에도 오래된 login_hint가 남을 수 있었다.

최종 인증 실패의 쿠키 정리를 실제 반환 응답에 적용한다. DB schema·migration·dependency·FE 제품 코드·결제 권한 로직은 변경하지 않는다.

## 응답과 세션 정책

- 토큰 누락·무효·만료와 이미 폐기된 토큰 재사용은 401 JSONResponse 자체에 `clear_auth_cookies`를 적용한다. 기존 detail과 재사용의 전체 refresh revoke 정책을 유지한다.
- access·refresh·login_hint를 발급 때와 같은 이름·Path·Secure·HttpOnly·SameSite로 만료시킨다. refresh는 `/auth/refresh`, 나머지는 `/`이며 운영 access의 `__Host-` 이름을 유지한다.
- 유효 refresh는 기존 회전과 재발급을 유지한다. access 만료만으로 정상 refresh를 삭제하지 않는다.
- DB 일시 장애는 500을 유지하고 쿠키 삭제를 보내지 않는다. 토큰을 응답 본문이나 로그에 추가하지 않는다.
- 200과 401 인증 응답은 no-store다. response_model·공개 JSON·OpenAPI 계약은 바꾸지 않는다.

쿠키 응답 경계는 [FastAPI 쿠키 문서](https://fastapi.tiangolo.com/advanced/response-cookies/)와 [직접 응답 문서](https://fastapi.tiangolo.com/advanced/response-directly/)를 따른다.

## 정상 동시 회전과 실제 무효 토큰 구분

SELECT 당시 유효했던 같은 토큰을 두 요청이 동시에 회전하면 `_claim_refresh_token`의 단일 승자만 새 토큰을 발급한다. 실패한 요청은 rollback 후 `RefreshRotationConflictError`를 발생시킨다. 이 예외는 기존 InvalidTokenError의 하위 타입으로 호출 호환성을 유지한다.

라우터는 전용 예외를 먼저 처리한다. 기존 401·동일 detail·no-store를 유지하되 Set-Cookie를 보내지 않아, 늦은 실패 응답이 성공한 access·refresh·login_hint를 지우지 않는다. 이미 폐기된 토큰을 다시 제출한 경우의 재사용 탐지는 계속 전체 revoke와 쿠키 정리를 수행한다.

## 검증 (2026-11-10)

실제 ASGI 응답과 PID 전용 PostgreSQL 테스트 DB를 사용했다.

- `test_refresh_cookie_cleanup.py` 13개: 401 다섯 원인과 Secure 두 환경의 실제 쿠키 삭제 헤더, 정상 refresh와 만료 access 복구, DB 일시 장애의 세션 보존을 검증한다.
- `test_refresh_cookie_cleanup_concurrency.py` 4개: 독립 DB 세션 두 개를 SELECT 직후 Barrier로 경쟁시킨다. Secure 두 환경과 두 응답 적용 순서에서 성공 쿠키 3종과 유효 access, 활성 새 refresh 1개를 확인하고 실패 응답의 쿠키 헤더 0을 단언한다.
- 기존 `test_token.py`는 동시 회전의 실패가 전용 예외임을 명시적으로 확인한다.
- 수정 전 쿠키 회귀는 **12 failed, 1 passed**, 추가 동시성 회귀는 **4 failed**로 문제를 재현했다.
- 최종 인증·쿠키·토큰 집중 **72 passed**, Backend 전체 **1,049 passed**(71.16초), Ruff format **110 files**·lint 통과.
- 원본과 수정 후 OpenAPI JSON 동일. Admin 생성 타입은 변경하지 않았다.

검증한 Backend 전체 파일과 PR worktree의 파일이 동일함을 대조했다. 최신 main 반영은 FE 변경만 포함해 Backend 검증 결과를 재사용한다. 의존성은 기존 backend 가상환경을 `UV_PROJECT_ENVIRONMENT`와 `uv run --no-sync`로 재사용했다. 브라우저 실기능 확인은 사용자 수행 범위다.
