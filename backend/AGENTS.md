# Backend 지침

- 이 디렉터리 작업에는 루트 `AGENTS.md`와 이 파일을 함께 적용한다.
- router는 요청·응답 경계, service는 비즈니스 로직과 트랜잭션 경계, model은 영속성 구조에 집중한다.
- 관계 데이터는 필요한 로딩 전략을 명시하고 N+1을 피한다. 비동기 함수에서 동기 블로킹 I/O를 직접 실행하지 않는다.
- 다중 DB 변경은 트랜잭션으로 묶고 외부 I/O와 DB 커밋 순서를 실패 시나리오까지 검토한다.
- 스키마 변경은 Alembic migration으로 수행한다. 원시 SQL 문자열을 직접 조합하거나 psql로 스키마를 우회 변경하지 않는다.
- 열람 권한을 서버가 확정한 콘텐츠만 서명한다. 독자 DTO에 draft, 미공개 원고, 허용되지 않은 이미지 키를 포함하지 않는다.
- Python과 테스트 명령은 `backend/`에서 `uv run`으로 실행한다.
- 기본 검증은 `uv run ruff format --check .`, `uv run ruff check .`, `uv run pytest`이며 migration 변경 시 Alembic drift와 upgrade/downgrade도 확인한다.
- DB 작업 전 `docs/guides/DB_GUIDE.md`, 리뷰 전 `docs/reviews/CODE_REVIEW_BE.md`와 `docs/reviews/GUIDE_REVIEW.md`를 읽는다.
