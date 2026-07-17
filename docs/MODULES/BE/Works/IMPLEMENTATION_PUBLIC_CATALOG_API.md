# 공개 작품 카탈로그 조회 API (M2 그룹 A)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works (공개 읽기 경로) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 A (A1+A2, WORK-01·02) |
| 작성 시점 | M2 A (2026-07-18) |
| 상태 | 구현 + Opus 리뷰(Major 1 반영) + /code-review high(10건 중 6건 반영) 완료. `pytest` 312 passed(신규 19), ruff·`alembic check` 클린 |
| 관련 문서 | M2_foundation.md 그룹 A·결정 2·5, MISTAKES.md "SQLAlchemy / AsyncSession"(sqlmodel.select 함정), IMPLEMENTATION_WORK_CRUD.md(admin 쓰기 측) |

비로그인 독자가 작품 목록/상세를 조회하는 첫 공개 API. `GET /works`(페이지네이션·태그 필터·공개 회차 수) + `GET /works/{id}`(작품 메타 + 공개 회차 요약). 회차 본문 서빙(절단·presign)은 그룹 B 소관.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/migrations/versions/20260717_0843_works_is_published_flag.py` | `works.is_published`(bool, NOT NULL, default false) + 기존 행 `true` backfill |
| `backend/src/models/work.py` | `Work.is_published` 컬럼(공개 카탈로그 노출 게이트, status와 별개 축) |
| `backend/src/lib/pagination.py` | `compute_offset(page,size)` - [1,`MAX_PAGE_SIZE`=100] 클램프 |
| `backend/src/schemas/catalog.py` | 공개 전용 DTO: `WorkListItem`/`WorkListResponse`/`WorkDetail`/`EpisodeSummary` |
| `backend/src/services/catalog_service.py` | `public_work_filters()`, `list_works`(COUNT + 공개회차 상관 서브쿼리), `get_work_detail` |
| `backend/src/routers/works.py` | `/works` 공개 라우터(인증 불요), size `le=` 상한 |
| `backend/src/schemas/work.py` | admin `WorkCreate`(기본 비공개)/`WorkUpdate`(`_NON_NULLABLE` 추가)/`WorkRead`에 `is_published` |
| `backend/src/config.py` + `.env.example` | `public_asset_base_url`(dweb-cover 커스텀 도메인, 미설정 부팅 허용) |
| `backend/tests/test_catalog.py` | 19개: 노출 필터(비공개/soft-delete/0회차), 페이지네이션(+size 상한 422), 태그 필터, 유출 부재(응답 텍스트 검색), 표지 URL 조립(+트레일링 슬래시), 플래그, 404 3종 |

새 의존성: 없음. DB 마이그레이션: 1개(위 backfill 포함).

---

## 2. 주요 결정

### 작품 단위 공개 플래그 `works.is_published` (2026-07-17 사용자 확정)
- 공개 회차 0개(표지만 있는 커밍순)여도 **노출**하고, 준비 중 작품은 삭제가 아니라 플래그로 숨긴다. 회차 발행 여부에서 노출을 파생하는 안(0회차 숨김)은 커밍순 노출 불가라 기각.
- `status`(연재 상태)와 별개 축. 신규 작품 기본 **비공개**, 기존 행은 backfill로 `true`(이미 운영 중이던 데이터 유지 - 마이그레이션 주석에 근거 기록).
- admin 제어는 `WorkCreate`/`WorkUpdate` API로 즉시 가능. **폼 토글 UI는 후속 admin PR**(그때 `generate:types` 재생성 필수 - 기본값 필드가 required로 뽑히는 codegen 함정, MISTAKES 참조).

### 공개 DTO 완전 분리 (`schemas/catalog.py`)
`AdminEpisodeRead`(image_keys·content 노출) 재사용 금지 - 독자 응답은 필드 하나까지 별도 정의. `content`·`image_keys`·회차 `price`·`bundle_discount_rate`(M3 미구현 할인율, Opus 리뷰 Major로 제거)는 **필드 자체가 없다**. 테스트는 필드 부재뿐 아니라 **응답 텍스트에서 비밀 문자열(원고 키·본문) 검색**으로 유출을 이중 검증.

### 썸네일 URL = 이 단계에선 항상 null
`episodes.thumbnail`은 현재 dweb(비공개 원고 버킷) 페이지 키라, 공개 URL 조립 시 원고 키 문자열이 독자 JSON에 노출된다(계획 검증에서 Major로 잡음). D2(공개 축소본 `dweb-cover/.../thumb.webp`) 이후에 조립을 얹는다. 표지는 전용 파일이라 URL 조립하되 D1(버킷 전환) 전까지 404 placeholder(문서화된 단계).

### `episode_count` = 공개 회차만 세는 별도 상관 서브쿼리
모델의 `Work.episode_count`(column_property)는 **전체** 회차 카운트라 값이 다를 뿐 아니라 **미공개 회차 수량이 노출**된다("총 7화"가 초안 5개의 존재를 알림). 공개용은 `is_published` 필터 서브쿼리로 별도 계산하고, 안 쓰는 column_property는 `defer(Work.episode_count)`로 행마다 계산되는 낭비를 차단(/code-review 반영).

### `public_work_filters()` - 공개 가시성 술어의 단일 출처
`Work.is_published AND deleted_at IS NULL`을 헬퍼로 추출. ⚠️ **그룹 B/C가 admin `episode_service.get_episode`의 Work join 패턴을 복사하면 `is_published` 검사가 빠진다**(admin은 비공개 작품도 봐야 해서 `deleted_at`만 검사) - 숨긴 작품의 공개 회차가 회차 ID 직접 접근으로 새는 함정. 회차 경로의 Work join은 반드시 이 헬퍼를 쓸 것(/code-review CONFIRMED 발견).

### sqlmodel.select vs sqlalchemy.select (구현 중 실사고)
`sqlalchemy.select`로 단일 엔티티를 select하면 `session.exec().first()`가 `Work` 대신 `Row`를 반환해 상세 API가 `AttributeError`로 죽었다(다중 컬럼인 목록 API는 우연히 통과해 파묻힐 뻔). 엔티티 select는 반드시 `from sqlmodel import select`. 단일 컬럼 count는 결과가 이미 `ScalarResult`라 `.one()`(`.scalar_one()` 아님). 전문: MISTAKES.md.

### 페이지네이션 = offset/limit + total (M2 결정 5)
`size`는 라우터 `Query(ge=1, le=MAX_PAGE_SIZE)`로 **422 명시 거부**(조용한 클램프만 있으면 응답 size로 페이지 수를 계산하는 클라이언트가 어긋남 - /code-review CONFIRMED), 응답 `size`는 클램프된 limit(단일 출처). 정렬은 `created_at DESC, id`(동일 타임스탬프 일괄 삽입의 페이지 경계 중복/누락 방지 tie-breaker).

---

## 3. 리뷰에서 기각/보류된 것들 - 의도적 미수정

| 후보 | 판단 |
|------|------|
| backfill=true가 기존 작품을 일괄 공개 | 사용자 승인 결정(운영 중 데이터 유지) + 프로덕션 DB 부재(출시 M7) - REFUTED |
| COUNT 쿼리를 페이지 미달 시 스킵 | 수십 행 규모에서 이득 0, 분기만 추가 - REFUTED |
| `_NOT_FOUND`·`SessionDep` 라우터별 반복 | 기존 6개 라우터 전부의 관례 - REFUTED |
| `is_locked`(=`not is_free`) 중복 필드 | 계약 안정성 선택 - M3가 구매 상태를 접어 의미를 확장할 자리 |
| backfill이 soft-delete 행에도 true | 현재 무해(카탈로그가 deleted_at 필터). 복구(un-delete) 기능 설계 시 공개 결정 분리 필요 - 잠재 함정 메모 |
| admin 공개 토글 부재 + codegen required | 후속 admin PR에서 함께 해소(ledger 추적) - 그 전까지 admin 신규 작품은 API로만 공개 가능 |

---

## 4. 검증

- `uv run pytest` 312 passed (기존 293 + 신규 19, 회귀 0)
- 유출 검증: 상세/목록 응답에 `content`·`image_keys`·`price`·`bundle_discount_rate` 필드 부재 + 원고 키/본문 문자열이 `resp.text` 어디에도 없음
- 노출 게이트: 비공개 작품 목록 제외·상세 404, soft-delete 동일, 미공개 회차 제외, 공개 회차만 카운트
- `uv run ruff check`+`format --check` 클린, `uv run alembic check` "No new upgrade operations detected"
- 실DB 스모크(ASGITransport): 목록 200 → 상세 200 → 미존재 404
