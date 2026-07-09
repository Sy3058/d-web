# 관리자 작품 CRUD API (M1.5 그룹 C - C1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 C - C1 (ADM-02) |
| 작성 시점 | M1.5 C1 (2026-07-09) |
| 상태 | 구현 + 강 모델 리뷰(/code-review high) 발견 10건 수정 완료. `pytest` 170 passed(신규 22), ruff·`alembic check` 클린 |
| 관련 문서 | M1.5_foundation.md C1, MISTAKES.md "SQLAlchemy / AsyncSession", study `sqlalchemy-async-expiry` |

관리자(owner)가 작품 데이터를 넣을 수 있는 최소 골격. M2 콘텐츠 마일스톤의 전제. 표지/에피소드 이미지 업로드는 그룹 D 소관 - 여기선 R2 키 문자열만 수용한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/routers/admin_works.py` | `/admin/works` 5개 엔드포인트(POST 201 / GET 목록 / GET 상세 / PUT / DELETE 204), 전부 `require_owner`, 404 매핑 `_get_or_404(with_tags 플래그)` |
| `backend/src/services/work_service.py` | `_get_or_create_tags`(SAVEPOINT 격리 get-or-create), `create_work`/`list_works`/`get_work`/`update_work`/`soft_delete_work` |
| `backend/src/models/work.py` | `Work.tags` Relationship(`link_model=WorkTag`, ORM 전용 - 마이그레이션 0), `Work`·`Episode`에 `eager_defaults=True` |
| `backend/src/schemas/work.py` | `WorkRead.tags`, tag_names strip + 순서 유지 dedup, `WorkUpdate` 명시적 null 거부(`model_fields_set`) |
| `backend/src/main.py` | 라우터 등록 |
| `backend/tests/test_admin_works.py` | 22개: 권한(401/reader 403/TOTP 미활성 owner 403), 생성+태그, 422 3종, 목록/조회, 수정 5종, 삭제 2종, 리뷰 회귀 4종(경합 폴백 결정적 재현 포함) |

새 의존성: 없음. DB 마이그레이션: 없음(`alembic check` 클린으로 입증).

---

## 2. 주요 결정

### 엔드포인트 5개 (DELETE 추가)
마일스톤 원안은 4개였으나 착수 시 사용자 결정으로 `DELETE`(soft) 추가. `deleted_at` 세팅만 - 하드 삭제·CASCADE 발동 경로 없음(A1 결정), 에피소드는 그대로 남고 목록·상세에서만 숨김.

### 소유권 필터 없음
모든 owner가 전 작품을 관리한다(`author_id` 필터 없음). 근거: 작가는 1인이지만 그 1인이 owner 계정을 바꿀 수 있음 - 계정 단위로 소유권을 쪼개면 옛 계정으로 만든 작품을 새 계정이 못 건드리는 자기 잠금이 생긴다. `author_id`는 서버가 `require_owner` 반환 User로 세팅(클라 입력 무시 - 스키마에 필드 자체가 없음), 기록용.

### 태그 get-or-create = SAVEPOINT 격리 (전체 rollback 금지)
이름으로 SELECT → 없는 것만 배치 생성. 생성 flush는 `async with session.begin_nested():`(SAVEPOINT) 안에서 - 동시 요청이 같은 이름을 먼저 커밋해 `tags.name` UNIQUE 충돌이 나면 **SAVEPOINT만 롤백**되고 재조회로 커밋된 행을 재사용한다.
- **전체 `session.rollback()`을 쓰면 안 되는 이유**(리뷰 발견): rollback은 `expire_on_commit=False`와 무관하게 세션의 **모든** 객체를 만료시킨다. update 경로가 미리 로드해 둔 `work`까지 만료돼, 직후 `work.tags = new_tags` 대입이 만료된 컬렉션을 동기 lazy load하다 `MissingGreenlet` 500 - 경합을 처리하라고 만든 경로가 자기 자신을 죽인다.
- 재-flush 재시도는 두지 않음: 2차 충돌이 미처리로 터지는 데다 단일 owner 운영에서 복구 가치가 없다(YAGNI).
- 입구에서 순서 유지 dedup(스키마 검증을 우회하는 미래 호출자 방어 - 중복이 오면 works_tags 복합 PK 충돌).

### refresh 정책 = `eager_defaults=True` (콜사이트 수동 열거 금지)
서버 계산 컬럼(`onupdate=func.now()`)은 UPDATE 후 만료로 남고, 기본값 `"auto"`는 INSERT만 RETURNING(PK를 어차피 받아야 해서)이라 update 응답 직렬화가 `MissingGreenlet`으로 죽었다. 콜사이트별 `session.refresh(work, attribute_names=[...])` 열거는 다음 함수에서 하나 빠뜨리면 재발하는 땜질 → `__mapper_args__ = {"eager_defaults": True}`로 UPDATE도 RETURNING(같은 왕복, 추가 쿼리 0). `Episode`에도 적용(D3 update 경로 대비).

### 태그만 변경 시 updated_at 명시 갱신
다대다 연결만 바뀌면 `works` 행 UPDATE 자체가 안 나가 onupdate가 발화하지 않는다(eager_defaults도 무력 - UPDATE가 없으면 RETURNING할 게 없음). 태그 교체 시 `work.updated_at = func.now()` 명시 대입으로 행을 dirty로 만들어 UPDATE를 유발한다(대입의 목적은 값이 아니라 UPDATE 발생. func.now()는 SQL 표현식이라 항상 변경으로 기록 + DB 시계 일관).

### WorkUpdate 명시적 null 거부
부분 수정 스키마의 `X | None = None`에서 None은 "생략(미변경)" 표현인데, 명시적 JSON null도 검증을 통과하고 `exclude_unset` dump에 살아남아 NOT NULL 컬럼에 대입 → 미처리 500이었다(리뷰 발견, 실증). `model_fields_set`(요청에 실제 등장한 필드 집합)으로 NOT NULL 필드 4개(title·episode_base_price·bundle_discount_rate·status)의 명시적 null을 422 거부. nullable 필드(synopsis·cover_image)의 "null = 비우기"는 유지.

### 기타
- 페이지네이션 없음(1인 작가 소수 작품, YAGNI), 목록은 `created_at DESC`.
- 조회는 `selectinload(Work.tags)` 명시(N+1/lazy load 규칙). DELETE 경로는 태그를 읽지 않으므로 `with_tags=False`로 로드 생략.
- `create_work` 필드 복사는 `model_dump` 기반 - 수동 나열은 새 필드 추가 시 조용히 유실되는 함정(리뷰 발견).
- 검증 실패는 FastAPI 기본 422(기존 관례와 일치 - Pydantic 검증=422, 비즈니스 규칙=400).

---

## 3. 리뷰에서 기각(REFUTED)된 것들 - 의도적 미수정

| 후보 | 기각 근거 |
|------|----------|
| tag_names 개수 무제한 | owner 전용 엔드포인트(신뢰 경계 안) - 하드닝 노이즈 |
| strip 정규화의 경계 변화 2건 | 계획에서 승인한 의도된 동작(공백만 태그 거부, 트림 후 50자 허용) |
| `_NOT_FOUND` 모듈 싱글턴 | 관측 채널 없음(Sentry는 5xx만 수집, 4xx 트레이스백 소비자 없음) + `lib/auth.py` 기존 관례 |

---

## 4. 검증

- `uv run pytest` 170 passed (기존 148 + 신규 22, 회귀 0)
- 경합 폴백은 결정적 재현 테스트로 커버: 태그를 미리 커밋해 두고 monkeypatch로 1회차 SELECT만 블라인드 → flush가 실제 UNIQUE 충돌 → SAVEPOINT 복구 확인 (전체 rollback 방식이면 이 테스트가 500으로 깨짐)
- `uv run ruff check` + `format --check` 클린, `uv run alembic check` 클린(모델 변경이 ORM 전용임을 입증)
