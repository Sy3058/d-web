# 뷰어 진행도 (M2 그룹 C1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Viewer |
| 관련 마일스톤 | [M2](../../../milestones/M2_foundation.md) 그룹 C - C1 |
| 작성 시점 | M2 C1 (2026-07-20) |
| 상태 | 구현 + Opus 계획 검증 → Sonnet 구현 → Opus 코드 리뷰(xhigh) 발견 8건 전부 반영. `pytest` 337 passed(신규 17), ruff·`alembic check` 클린. **DB 마이그레이션 1개**(신규 테이블 + episode_id 인덱스) |
| 관련 문서 | DB_SCHEMA.md §2 viewer_progress, M2_foundation.md 그룹 C, MISTAKES.md |

독자가 회차를 읽은 마지막 위치(문서 최상위 블록 인덱스)를 저장·복원하는 API. 그룹 B(회차 콘텐츠 API)가 아직 없는 상태에서 그룹 D(공개 버킷)와 병렬로 진행했다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/viewer.py` | `ViewerProgress`(신규 테이블) |
| `backend/migrations/versions/20260719_1757_viewer_progress.py` | `viewer_progress` 테이블 생성(FK CASCADE 2개, UNIQUE) |
| `backend/src/schemas/viewer.py` | `ProgressUpdate`(page_no ge=0) / `ProgressRead` |
| `backend/src/services/progress_service.py` | `upsert_progress`(공개성 게이트 + ON CONFLICT DO UPDATE) / `get_progress` |
| `backend/src/services/catalog_service.py` | `public_episode_exists()` 추가 |
| `backend/src/routers/progress.py` | `PUT`/`GET /episodes/{id}/progress` |
| `backend/tests/factories.py` | `make_work`/`make_episode` 공용 팩토리(test_catalog와 공유) |
| `backend/tests/test_progress.py` | 17케이스 |

| 엔드포인트 | 인증 | 역할 |
|-----------|------|------|
| `PUT /episodes/{id}/progress` | 필수 | 진행도 upsert. 회차가 공개+미삭제가 아니면 404. 응답 `no-store` |
| `GET /episodes/{id}/progress` | 필수 | 저장된 진행도 조회. 행 없으면 404. 응답 `no-store` |

---

## 2. 주요 결정

### 회차 공개성 검증 = `catalog_service.public_episode_exists()` 신설
M2 문서 C1 원문은 "회차 존재 검증은 그룹 B(회차 콘텐츠 API)와 같은 공개 조회를 재사용"이라 적었으나, 착수 시점에 B1/B2가 아직 없어 재사용 대상이 없었다. `progress_service`에 사설 조회를 두면 B가 나중에 생겼을 때 필터가 두 곳으로 갈라진다 - 대신 기존 `public_work_filters()`(작품 공개+미삭제의 단일 출처)를 그대로 태우는 얇은 함수를 `catalog_service`에 추가해, B가 나중에 별도 로딩 버전을 만들어도 필터는 한 곳에 남도록 했다. `Episode.id`만 select해 `content`(JSONB) 로딩을 피한다.

### PUT은 공개성 검사, GET은 검사 없음 (2026-07-20 사용자 확정)
PUT은 저장 자체를 막는 게이트라 `public_episode_exists()`를 매번 통과해야 한다. 반대로 GET은 진행도 행 존재만 확인한다 - 작품이 일시 비공개로 전환됐다 재공개되는 경우, 기존 진행도가 계속 살아있는 편이 UX상 맞다고 판단했다(비공개 전환은 실수·일시적일 수 있고, 진행도 유실은 독자 경험을 해친다). 유출 위험도 없다 - GET이 노출하는 값은 요청한 본인의 정수 진행도 하나뿐이라, 회차 존재 여부 자체가 민감 정보가 아니다.

### upsert = `postgresql.insert().on_conflict_do_update()` + `set_`에 `updated_at` 명시
`ViewerProgress.updated_at`은 `onupdate=func.now()`로 선언돼 있지만, 이는 ORM/Core의 일반 UPDATE 문에만 적용되고 **INSERT의 `ON CONFLICT ... DO UPDATE SET` 절에는 자동으로 붙지 않는다.** `set_={"page_no": ..., "updated_at": func.now()}`로 명시하지 않으면 재저장 시 `updated_at`이 최초 삽입 시각에 멈춘다. `test_put_twice_bumps_updated_at`으로 독립 검증했다.

### `session.exec()` vs `session.execute()`
`on_conflict_do_update().returning(...)` 문을 처음엔 `session.execute()`로 실행했는데 sqlmodel이 deprecation 경고를 띄웠다. sqlmodel `AsyncSession.exec()` 소스(`sqlmodel/ext/asyncio/session.py`)를 확인한 결과 `UpdateBase`(Insert/Update/Delete 전체) 오버로드가 공식 지원돼, `session.exec(stmt)`로 교체했다(레포 전체가 `exec()`를 관례로 쓰는 것과도 일치, 동작은 동일 - `.scalars().one()`은 그대로 필요).

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

**검증 중 사고**: 반영 후 전체 스위트가 실행마다 다른 지점에서 깨졌다. 원인은 teardown의 `DELETE FROM users`가 FK 위반으로 중단되어 `dweb_test`에 데이터가 잔류했고, 이후 실행들이 무관한 곳(admin_episodes 업로드 409 등)에서 연쇄 실패한 것. 기각한 가설: 테이블 삭제 순서 붕괴(`works`(3) < `users`(8)로 정상), 개발 DB 오염(`TEST_DATABASE_URL=dweb_test` 분리 확인), 동시 pytest(관측 시 부재). **최초 트리거는 특정하지 못했다** - 동시 접속 증거가 없어 타 세션 경합이라 단정할 수 없다. `dweb_test` 스키마 초기화로 해소했고 이후 337 passed 3회 연속 안정.

## 4. 이연 / 후속

| 항목 | 이동처 |
|------|--------|
| 그룹 B(회차 콘텐츠 API) 완성 후 `public_episode_exists()`와 B의 로딩 조회 통합 여부 재검토 | B1/B2 착수 시 |
| FE debounce 저장 호출 + 재진입 복원 UI | 그룹 F (뷰어 아일랜드) |
