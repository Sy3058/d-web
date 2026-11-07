# M3 F2 콘텐츠 권한과 첫 전문 발급

## 범위

F1 중앙 권한 판정을 독자 content API에 연결한다. viewer-bootstrap, 프론트 세션 복구, 결제 UI와 실제 환불 서비스는 후속 작업이다. F 전체 완료를 뜻하지 않는다.

## 응답과 인증

`GET /episodes/{id}/content`는 optional auth를 사용한다. 유효한 access 사용자만 구매 권한을 인정하고, 쿠키 없음·무효·만료는 익명으로 처리한다. 이 경로에서 refresh나 쿠키 삭제를 수행하지 않는다. 인증 외 장애는 익명 성공으로 숨기지 않는다.

공개 무료 전문은 `full`, 미구매 부분 유료는 `preview`다. 같은 환경의 활성 구매는 일반 비공개 뒤에도 `full`이다. 삭제·비구매 비공개는 존재를 숨긴 404이며 성공·404·발급 경합 409는 no-store다. `access_scope`는 응답 범위를 표시하고 `has_paid_part`는 기존 뷰어의 잠금 표시 의미를 유지하므로 전문에서는 false다.

권한 판정과 반환 문서는 같은 snapshot을 사용한다. 미리보기는 paywall 절단 뒤 안전하게 투영하고 남은 이미지 키만 서명한다. 전문도 기존 노드·마크 allowlist를 통과하며 원본 key 필드는 응답에 넣지 않는다.

## 첫 전문 발급과 환불 경합

구매에 따른 전문은 presign 성공 뒤 구매 상태를 다시 확인한다. 첫 발급은 `status='active' AND first_viewed_at IS NULL` 조건부 UPDATE를 commit한 뒤 반환한다. 경합으로 UPDATE가 실패하면 준비한 전문과 URL을 버리고 409를 반환한다. presign 또는 commit이 실패하면 전문을 응답하지 않는다. 재열람은 현재 active 상태를 확인하며 첫 발급 시각을 보존한다.

첫 발급과 환불 승인은 같은 purchase 행에서 경합한다. PostgreSQL Read Committed는 대기 중이던 UPDATE의 조건을 선행 commit 뒤 다시 평가한다. [PostgreSQL 16 공식 문서](https://www.postgresql.org/docs/16/transaction-iso.html#XACT-READ-COMMITTED)를 따른다. 실제 환불 요청·취소 서비스는 G에서 연결하며 F2에서는 해당 승인 CAS와 발급의 경합을 독립 DB session으로 검증한다.

## 검증

신규 `tests/test_episode_content_access.py`는 다음 경계를 검증한다.

- 쿠키 없음·위조·만료·탈퇴·없는 사용자: preview, 유료 키 서명 0, Set-Cookie 없음. 인증 이외 예외는 전파한다.
- 현재 환경 active 구매의 공개·비공개 전문, 첫 발급 시각 유지, 다른 환경·사용자·잠긴 구매의 preview.
- 잘못된 구매 문서의 full 차단, presign 실패의 미발급 유지, presign 중 환불 전환의 409와 전문·URL 응답 0, commit 실패의 미발급 유지.
- 무료 전문의 구매 유무에 따른 발급 기록, 판정 직후 원고 수정에도 원래 판정 문서만 반환.
- 독립 DB session과 SELECT 뒤 UPDATE 직전 Barrier로 두 첫 발급의 1성공·1충돌, 첫 발급과 환불 승인 CAS의 양방향 단일 승자.

OpenAPI에서 Admin 타입을 재생성했다. Frontend의 기존 소비자는 추가 필드를 무시하고 `has_paid_part`로 잠금을 표시한다. Frontend 소스와 API 요청 방식은 변경하지 않았다.

2026-11-08 최종 검증:

- Backend `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run ruff format --check .`: 106 files 통과, `uv run ruff check .`: 통과.
- Backend `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run pytest`: **999 passed**, 70.35초, 경고 없음. F1·기존 콘텐츠·신규 발급 테스트 85건을 포함한다.
- Admin `generate:types` 후 `lint`, `test`(**115 passed**), `build` 통과.
- Frontend `lint`, `astro check`, `test`(**132 passed**), `build` 통과. 기존 `buildWorksUrl` 미사용 hint 1건, Sentry auth token 미설정과 Astro transitions sourcemap 경고가 남는다. 빌드 성공과 별개로 소스맵 업로드는 수행되지 않았다.
- `git diff --check`, 변경 파일 U+2014 금지, 문서 상대 링크 검사 통과.

첫 집중 테스트는 PostgreSQL 미실행으로 연결이 거부됐다. `docker compose ps`에서 서비스가 없는 것을 확인하고 기존 볼륨을 유지한 `docker compose up -d postgres` 후 healthy 상태와 위 전체 검증을 확인했다. 테스트는 PID별 격리 DB를 사용했다. 스키마·migration·dependency 변경은 없다. 실제 PortOne write와 사용자 브라우저 확인은 수행하지 않았다.
