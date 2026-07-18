# 공개 작품 카탈로그 조회 API (M2 그룹 A)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Works (공개 읽기 경로) |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 A (A1+A2, WORK-01·02) |
| 작성 시점 | M2 A (2026-07-18), 후속 A3+가격 추가 (2026-07-19) |
| 상태 | 구현 + Opus 리뷰(Major 1 반영) + /code-review high(10건 중 6건 반영) 완료. 후속(#82·#83) + /code-review xhigh(7건 중 3건 반영) 완료. `pytest` 320 passed, ruff 클린 |
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

---

## 5. 후속: 회차 실효 가격 + 공개 태그 목록 (2026-07-19, #82·#83)

E(FE 목록/상세) 착수 검증에서 **계약 구멍 2개**가 드러나 같은 모듈에 얹었다. 둘 다 "FE가 화면을 만들 수 없다"가 근거지, 리팩터가 아니다.

| 파일 | 내용 |
|------|------|
| `schemas/catalog.py` | `EpisodeSummary.price`(실효가), `PublicTag`(id·name·work_count) |
| `services/catalog_service.py` | `_to_episode_summary(ep, base_price)` 실효가 계산, `list_public_tags()` |
| `routers/tags.py` | `GET /tags` 공개 라우터(인증 불요) |
| `admin/src/types/api.gen.ts` | codegen 재생성(+51줄, 삭제 0) |

### 가격은 은닉 대상이 아니다 - 계약 정정 (#83)
A1/A2는 `price`를 `content`·`image_keys`와 함께 은닉했는데, 그 문장이 **원고 유출 방어**와 **가격 비공개**를 뭉뚱그린 것이었다. 가격은 판매를 위해 공개하는 정보다. 다만 그냥 노출하면 안 되는 이유가 따로 있다: 실제 회차 가격은 `episodes.price ?? works.episode_base_price`(`models/work.py:189`)라, 작품 기준가만 내려주면 **오버라이드된 회차에서 표시 금액과 결제 금액이 어긋난다**(소비자 오인 표시).

→ **fallback 계산을 서버 한 곳에 둔다.** 원시값 2개를 내려 FE가 계산하게 하면 규칙이 BE·FE 두 곳에 복제되고, M3에서 이벤트 할인가가 붙을 때 한쪽만 갱신되면 화면가와 결제가가 갈라진다. 무료 회차는 `null`(0원 판매와 구분 + `is_free`를 무시한 가격 표기 차단). FE 규칙이 "`is_free`면 무료 배지, 아니면 `price`원"으로 단순해진다.

### 태그 목록 API - 필터의 데이터 소스 (#82)
`GET /works?tag=` 필터링은 A1에 있었으나 **"어떤 태그가 존재하는지" 알려주는 경로가 없었다.** 대안(카드에 보이는 태그만 클릭)은 1페이지에 안 나온 태그로는 필터 자체가 불가능해 발견성이 깨진다 - 백엔드를 늘리는 게 맞다는 판단.

⚠️ **inner join + `public_work_filters()`를 WHERE에** 둔다. `Tag`를 전량 조회해 앱단에서 거르거나 LEFT JOIN을 쓰면 미공개 작품에만 달린 태그가 카운트 0으로 응답에 남아 **태그 이름이 숨긴 작품의 존재를 흘린다**. `works_tags` PK가 `(work_id, tag_id)`라 태그당 작품 중복이 불가능해 `count`에 distinct가 불필요하고, `GROUP BY tags.id`는 PK 함수 종속이라 PG에서 Tag 엔티티 선택이 유효하다.

### 리뷰(xhigh 7건) 반영·보류
| 지적 | 처리 |
|------|------|
| `work_count` 혼합 가시성(공개+비공개 동시) 미검증 | **반영** - 카운트가 공개분만 세는지 단언하는 테스트 추가. 이 산술이 틀리면 숫자가 숨긴 작품을 흘린다 |
| `api.gen.ts` 미재생성 | **반영** - `pnpm --filter admin generate:types`. #87이 #81분 드리프트를 이미 해소해 이번 추가분만 반영됨 |
| `db_session` 타입 어노테이션 누락 | 반영 |
| `PublicTag`가 `TagRead`(id·name) 중복 | 보류 - 공개 DTO는 admin 스키마와 의도적으로 분리(§2 참조). 상속하면 그 경계가 흐려짐 |
| `GET /tags` 개수 상한 없음 | 보류 - 1인 작가 태그 규모에서 무의미. `MAX_PAGE_SIZE` 비대칭은 인지 |
| 한글 정렬 단언이 DB collation 의존 | 보류 - C·ICU 양쪽에서 액<판 동일. 깨지면 그때 집합 비교로 완화 |
