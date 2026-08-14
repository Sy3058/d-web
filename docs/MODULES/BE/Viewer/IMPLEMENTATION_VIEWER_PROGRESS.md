# 뷰어 진행도 (M2 그룹 C1, E4 BE)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Viewer |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 C - C1, 그룹 E - E4 |
| 작성 시점 | M2 C1 (2026-07-20), E4 BE (2026-08-11), 긴 블록 복원 보강 (2026-08-14) |
| 상태 | C1 회차 단위 저장·복원과 E4 작품 단위 조회 구현. 긴 블록 내부 상대 위치와 구버전 보존 계약 추가, Backend 전체 gate 통과 |
| 관련 문서 | DB_SCHEMA.md §2 viewer_progress, M2_foundation.md 그룹 C, MISTAKES.md |

독자가 회차를 읽은 마지막 위치(문서 최상위 블록 인덱스 + 블록 내부 상대 위치)를 저장·복원하는 API. 그룹 B(회차 콘텐츠 API)가 아직 없는 상태에서 그룹 D(공개 버킷)와 병렬로 진행했다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/viewer.py` | `ViewerProgress`(신규 테이블) |
| `backend/migrations/versions/20260719_1757_viewer_progress.py` | `viewer_progress` 테이블 생성(FK CASCADE 2개, UNIQUE) |
| `backend/migrations/versions/20260814_2100_viewer_progress_block_offset.py` | `block_offset_bp` 추가 + 0..10000 CHECK |
| `backend/src/schemas/viewer.py` | `ProgressUpdate` / `ProgressRead` / `WorkProgressRead` |
| `backend/src/services/progress_service.py` | 회차 단위 upsert·조회 / 작품 단위 읽은 회차·최근 회차 조회 |
| `backend/src/services/catalog_service.py` | `public_episode_exists()` 추가 |
| `backend/src/routers/progress.py` | `PUT`/`GET /episodes/{id}/progress`, `GET /works/{id}/progress` |
| `backend/tests/factories.py` | `make_work`/`make_episode` 공용 팩토리(test_catalog와 공유) |
| `backend/tests/test_progress.py` | 29케이스(E4 쿼리 방향, 긴 블록 오프셋 경계·구버전 보존 포함) |

| 엔드포인트 | 인증 | 역할 |
|-----------|------|------|
| `PUT /episodes/{id}/progress` | 필수 | 진행도 upsert. 회차가 공개+미삭제가 아니면 404. 응답 `no-store` |
| `GET /episodes/{id}/progress` | 필수 | 저장된 진행도 조회. 행 없으면 404. 응답 `no-store` |
| `GET /works/{id}/progress` | 필수 | 공개·미삭제 회차의 읽은 ID 목록과 최근 회차 반환. 행 없으면 빈 값 200. 응답 `no-store` |

---

## 2. 주요 결정

### 회차 공개성 검증 = `catalog_service.public_episode_exists()` 신설
M2 문서 C1 원문은 "회차 존재 검증은 그룹 B(회차 콘텐츠 API)와 같은 공개 조회를 재사용"이라 적었으나, 착수 시점에 B1/B2가 아직 없어 재사용 대상이 없었다. `progress_service`에 사설 조회를 두면 B가 나중에 생겼을 때 필터가 두 곳으로 갈라진다 - 대신 기존 `public_work_filters()`(작품 공개+미삭제의 단일 출처)를 그대로 태우는 얇은 함수를 `catalog_service`에 추가해, B가 나중에 별도 로딩 버전을 만들어도 필터는 한 곳에 남도록 했다. `Episode.id`만 select해 `content`(JSONB) 로딩을 피한다.

### PUT은 공개성 검사, GET은 검사 없음 (2026-07-20 사용자 확정)
PUT은 저장 자체를 막는 게이트라 `public_episode_exists()`를 매번 통과해야 한다. 반대로 GET은 진행도 행 존재만 확인한다 - 작품이 일시 비공개로 전환됐다 재공개되는 경우, 기존 진행도가 계속 살아있는 편이 UX상 맞다고 판단했다(비공개 전환은 실수·일시적일 수 있고, 진행도 유실은 독자 경험을 해친다). 유출 위험도 없다 - GET이 노출하는 값은 요청한 본인의 정수 진행도 하나뿐이라, 회차 존재 여부 자체가 민감 정보가 아니다.

### upsert = `postgresql.insert().on_conflict_do_update()` + `set_`에 `updated_at` 명시
`ViewerProgress.updated_at`은 `onupdate=func.now()`로 선언돼 있지만, 이는 ORM/Core의 일반 UPDATE 문에만 적용되고 **INSERT의 `ON CONFLICT ... DO UPDATE SET` 절에는 자동으로 붙지 않는다.** `set_`에 `page_no`, `block_offset_bp`, `updated_at`을 모두 명시하지 않으면 재저장 시 위치 일부나 시각이 최초 값에 멈춘다. `test_put_twice_updates_same_row`와 `test_put_twice_bumps_updated_at`으로 독립 검증했다.

### 긴 블록 복원 = `page_no + block_offset_bp` (2026-08-14)

한 장의 원고 이미지가 `398x5400`처럼 여러 패널을 포함하면 최상위 블록 인덱스 하나만으로는 이미지 안에서 어디까지 읽었는지 구분할 수 없다. `block_offset_bp`는 해당 블록 높이 중 뷰포트 상단이 지나온 비율을 0..10000 정수로 저장한다. 부동소수 대신 basis point를 써 JSON과 INTEGER 왕복이 안정적이고, Pydantic 범위 검증과 DB CHECK를 함께 둔다.

기존 클라이언트가 `{page_no}`만 보내는 경우도 필드 누락 여부를 보존한다. 신규 행은 오프셋 0으로 만들고, 기존 행의 같은 블록이면 새 클라이언트가 저장한 오프셋을 유지하며, 다른 블록으로 이동할 때만 0으로 초기화한다. 구버전 탭이 배포 뒤에도 열린 채 PUT을 계속 보내 정밀 위치를 지우는 문제를 막는다.

이 값은 회차 전체 진행률이 아니다. 다른 이미지의 로드 여부나 무료 절단 범위로 전체 분모가 달라져도 현재 블록 내부의 상대 지점만 표현한다. M3의 전체 진행률, 완독 판정, 구매 CTA 계약은 별도로 유지한다.

### `session.exec()` vs `session.execute()`
`on_conflict_do_update().returning(...)` 문을 처음엔 `session.execute()`로 실행했는데 sqlmodel이 deprecation 경고를 띄웠다. sqlmodel `AsyncSession.exec()` 소스(`sqlmodel/ext/asyncio/session.py`)를 확인한 결과 `UpdateBase`(Insert/Update/Delete 전체) 오버로드가 공식 지원돼, `session.exec(stmt)`로 교체했다(레포 전체가 `exec()`를 관례로 쓰는 것과도 일치, 동작은 동일 - `.scalars().one()`은 그대로 필요).

### E4 작품 단위 조회 = 공개 작품 확인 + 읽은 진행도 조회 (2026-08-11)

`GET /works/{work_id}/progress`는 공개·미삭제 작품 PK를 먼저 확인하고, 작품이 있으면 `ViewerProgress → Episode → Work` inner join으로 요청 사용자가 실제로 읽은 행만 조회한다.

- 첫 쿼리 작품 행 없음: 비공개·삭제·미존재이므로 404
- 두 번째 쿼리 진행도 없음: `read_episode_ids=[]`, `last_episode=null`로 200
- 진행도 있음: `updated_at DESC`, `viewer_progress.id DESC` 순으로 읽은 회차와 최근 회차 반환. 최근 회차는 FE가 무엇을 이어 보는지 표시할 수 있도록 `id`·`public_id`·`title`을 포함

최초 구현은 DB 왕복 한 번을 위해 `Work → 공개 Episode 전체 → ViewerProgress` LEFT JOIN을 사용했지만, 진행도 0건인 사용자도 작품의 공개 회차 전량을 생성·정렬·전송하는 성능 Major가 리뷰에서 발견됐다. PK 존재 확인 1회가 늘어나는 대신 두 번째 조회 비용을 읽은 진행도 행에 맞추는 단순한 2쿼리 구조로 교체했다. 두 쿼리 사이에 작품이 비공개 전환되는 경우도 fail-closed가 되도록 두 번째 쿼리에 작품 공개 필터를 다시 적용한다.

회귀 테스트는 공개 회차 13개·진행도 1개 조건에서 응답이 1개뿐임을 확인하고, 실행 SQL이 `FROM viewer_progress JOIN episodes`이며 LEFT JOIN을 포함하지 않는지 검증한다. 응답에는 이어 보기 링크와 문구에 필요한 회차 `id`·`public_id`·`title`만 넣고 `page_no`, 원고 JSONB, 이미지 키는 싣지 않는다. 제목은 이미 조인한 `Episode`에서 함께 선택하므로 추가 DB 왕복은 없다. 개인 응답은 성공과 404 모두 `Cache-Control: no-store`다.

---

## 3. 리뷰

**계획 리뷰**(Opus, `/fable-plan` → `/fable-review`): (a) `onupdate` 함정의 확신도 표기 정정 - DoD 테스트는 유지, (b) GET의 공개성 검사 범위 미정의 → 사용자와 논의 후 "검사 없음" 확정, (c) join은 명시 ON 조건(레포 관례).

**코드 리뷰**(Opus xhigh, 10앵글 + 스윕): 발견 8건 **전부 반영**.

1. **`page_no` 상한 부재 → 500**(실측 확정). 컬럼이 4바이트 `Integer`라 `2147483647` 초과 값이 Pydantic을 통과한 뒤 asyncpg `DataError`로 터졌다 - 핸들러가 없어 깨끗한 422가 아니라 500 + Sentry 이벤트. 임시 테스트로 재현 확인 후 `le=2_147_483_647` + 경계값 테스트 추가. 계획 단계에서 "과대값 피해는 본인 진행도뿐"이라 판단했으나 **INT4 범위 초과가 500이 된다는 점을 놓쳤던 것**.
2. **공개성 게이트가 라우터에만 존재** → `upsert_progress` 안으로 이동(반환 `ViewerProgress | None`). 서비스가 트랜잭션 경계와 도메인 불변식을 함께 소유해야 두 번째 호출부가 생겨도 우회되지 않는다.
3. **교차 유저 격리 테스트 부재** → `other_user` 픽스처 + 2케이스. 코드는 옳았으나 이 기능의 핵심 보안 불변식이 테스트로 지켜지지 않고 있었다.
4. **GET의 404 메시지 오류** → `_EPISODE_NOT_FOUND`/`_PROGRESS_NOT_FOUND` 분리. 회차가 존재하는데 "회차를 찾을 수 없습니다"를 내리면 FE가 틀린 오류를 띄운다.
5. **테스트 헬퍼 복붙** → `tests/factories.py` 신설. `test_catalog.py`는 alias import로 호출부 43곳 무수정(D2 세션과의 충돌면 최소화).
6. `ProgressRead` 조립 중복 → `_to_read()` 헬퍼.
7. 개인 데이터 응답에 캐시 헤더 없음 → `Cache-Control: no-store` + 검증 테스트.
8. `episode_id` 미인덱스(CASCADE 시 순차 스캔) → 모델 `Index` 추가. 마이그레이션이 미커밋 상태라 새 리비전 대신 기존 파일에 `create_index`/`drop_index`를 직접 넣고, 개발 DB는 테이블 drop → 이전 리비전 stamp → `upgrade head`로 **신규 적용 경로를 재현 검증**했다(인덱스 3개 실재 확인).

**검증 중 사고 → 테스트 격리 개선**: 반영 후 전체 스위트가 실행마다 다른 지점에서 깨졌다. 원인은 **워크트리 두 개(`d-web`, `d-web-m2`)가 고정 테스트 DB `dweb_test` 하나를 공유**한 것 - `db_session` teardown이 매 테스트마다 전 테이블을 DELETE하므로 상대 세션이 만든 행이 상대 테스트 도중 사라진다. `DELETE FROM users` FK 위반 → teardown 중단 → 데이터 잔류 → 이후 실행이 무관한 곳(admin_episodes 업로드 409)에서 연쇄 실패로 번졌다.

진단 중 기각했던 가설: 테이블 삭제 순서 붕괴(`works`(3) < `users`(8)로 정상), 개발 DB 오염(`TEST_DATABASE_URL` 분리 확인). **동시 pytest 가설도 한 번 기각했는데 이것이 오판이었다** - 몇 차례 샘플링에서 동시 접속이 0이라 배제했으나 상대 세션이 그 순간 쉬고 있었을 뿐이고, 사용자 제보로 확정됐다. "관측되지 않음"을 "없음"으로 단정한 실수.

해결: conftest `test_engine`이 **PID 전용 DB**(`dweb_test_<pid>`)를 만들고 세션 종료 시 드롭하도록 변경(`CREATE/DROP DATABASE`는 트랜잭션 밖이어야 해 `isolation_level="AUTOCOMMIT"` 연결 사용, 다른 PID의 DB는 건드리지 않음). 검증 = **pytest 2개 동시 실행에서 양쪽 337 passed** + 종료 후 잔재 DB 0개.

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 그룹 B(회차 콘텐츠 API) 완성 후 `public_episode_exists()`와 B의 로딩 조회 통합 여부 재검토 | B1/B2 착수 시 |
| FE debounce 저장 호출 + 재진입 복원 UI | 그룹 F (뷰어 아일랜드) |
| 작품 단위 진행률 바 + 이어 보기 React 섬 | 그룹 E4 FE |
