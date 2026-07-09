# 작품/에피소드 도메인 모델 + 마이그레이션 (M1.5 그룹 A - A1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 A - A1 |
| 작성 시점 | 2026-07-10 (구현은 2026-07-01, PR #51 - 사후 작성) |
| 상태 | 구현 완료·머지(#51). `alembic check` 클린, 모델 round-trip 테스트 통과 |
| 관련 문서 | [DB_SCHEMA.md](../../../DB_SCHEMA.md) §2·§6, M1.5_foundation.md A1, [IMPLEMENTATION_WORK_CRUD.md](./IMPLEMENTATION_WORK_CRUD.md)(C1 - 이 모델 위 CRUD) |

DB_SCHEMA §2 "작품/에피소드 도메인"을 코드로 옮긴 것. M1.5 모든 도메인 작업(C 작품 CRUD, D 업로드, E 예약 공개)의 선행 작업이다. M1 A1 교훈대로 `table=True` 모델을 응답에 직접 노출하지 않고 요청/응답 DTO(`schemas/work.py`)를 분리했다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/work.py` | `Work`, `Tag`, `WorkTag`(link), `Episode` + `WorkStatus`(StrEnum) |
| `backend/src/schemas/work.py` | 요청/응답 DTO 분리(`WorkCreate`/`WorkRead`/`TagRead` 등), 태그 이름 strip+순서 유지 dedup 검증 |
| `backend/src/models/__init__.py` | 신규 모델 import(metadata 등록) |
| `backend/migrations/versions/20260701_1125_work_episode_domain_models.py` | 4개 테이블 + 인덱스 생성 |
| `backend/tests/test_work_models.py` | 모델 round-trip·제약 단위 테스트 |

새 의존성: 없음.

---

## 2. 테이블 구조 (DB_SCHEMA §2)

- **공통**: PK 전 테이블 UUID + `gen_random_uuid()` server_default, 시각 전부 TIMESTAMPTZ. 서버 사이드 기본값(M1 A1 패턴).
- **`works`**: `author_id` FK→users(**CASCADE 없음** - 작가 계정은 soft delete가 기본이라 작품 하드 삭제가 딸려가면 안 됨. 1인 작가라 값은 role=owner 유저 id, FK는 확장 대비 유지), `title` VARCHAR(200), `episode_base_price` default 500, `bundle_discount_rate` NUMERIC(4,3) default 0.1(저장만 - 할인 적용은 M3), `status` VARCHAR(20)(ongoing/completed/hiatus), `deleted_at` soft delete.
- **`tags`**: `name` VARCHAR(50) UNIQUE. UNIQUE가 name 조회 인덱스 겸용이라 별도 `idx_tags_name` 안 둠(중복 인덱스). 이 UNIQUE가 C1 get-or-create의 충돌 방어선.
- **`works_tags`**: `PK(work_id, tag_id)` 복합, 양쪽 FK CASCADE.
- **`episodes`**: `UNIQUE(work_id, episode_no)`, `work_id` FK CASCADE, `price` **nullable**(NULL이면 런타임에 `works.episode_base_price` 참조 - 금액 하드코딩 금지), `is_free`(“무료 회차 수”의 단일 진실 - 별도 컬럼 없음, 관리자 UI가 앞 N화 토글), `image_keys` JSONB `DEFAULT '[]'`(배열 인덱스 = 페이지 순서, R2 **키** 저장 - 공개 URL 아님), `is_published` + `published_at`(예약 공개 - 그룹 E).

### 인덱스 (DB_SCHEMA §6)
- `idx_episodes_work_id` - FK 인덱스 명시(Postgres는 FK 자동 인덱스 없음)
- `idx_episodes_published_at` - partial `WHERE is_published`(공개분 정렬/범위)
- `idx_episodes_published` - partial `work_id WHERE is_published`
- `works_tags` 역방향(tag_id) 인덱스는 태그별 작품 목록이 필요해질 때(M2/M5) 보류

---

## 3. 구현 결정

### StrEnum + VARCHAR (네이티브 PG enum 미사용)
`WorkStatus`는 StrEnum(str 서브클래스)이라 String 컬럼에 멤버 값이 그대로 저장된다. 상태 추가는 앱 enum 값만 늘리면 되고 **DB 마이그레이션 0**. `users.role`(B1)과 같은 패턴.

### sa_column 헬퍼
`_pk_column()`/`_created_at_column()`/`_updated_at_column()`으로 UUID PK·타임스탬프 정의 통일(M1 A1 패턴 답습). `updated_at`은 `onupdate=func.now()`.

### 스키마 계층의 태그 정규화
`tag_names`는 스키마에서 strip 후 1~50자 검증 + 순서 유지 dedup - 같은 이름을 두 번 보내도 get-or-create(C1)가 한 번만 연결하고, `works_tags` 복합 PK 충돌을 입구에서 차단.

### 후속(C1)에서 얹힌 것
`Work.tags` Relationship(ORM 전용, 마이그레이션 0)과 `__mapper_args__ = {"eager_defaults": True}`(UPDATE도 RETURNING)는 A1이 아니라 C1에서 추가됐다 - 경위는 [IMPLEMENTATION_WORK_CRUD.md](./IMPLEMENTATION_WORK_CRUD.md) 참조.

---

## 4. 검증

- `uv run alembic upgrade head` → 4개 테이블 + 인덱스 생성, downgrade/upgrade 왕복 정상
- `uv run alembic check` 클린(모델-마이그레이션 동기화. down_revision은 생성 시 실제 head 확인 - MISTAKES Alembic)
- `uv run pytest` 모델 round-trip·제약(UNIQUE·CASCADE·server_default) 테스트 통과, ruff 클린
- `DB_SCHEMA.md` §2 정합 확인(구현하며 §2/§6 소폭 갱신)
