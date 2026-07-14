# TROUBLESHOOTING - episode_count 추가 후 PUT·표지 업로드 응답이 전부 500 (MissingGreenlet)

대상: backend (FastAPI + SQLModel/SQLAlchemy async), M1.5 F2
관련 구현: `IMPLEMENTATION_WORK_CRUD.md`(후속 변경 배너), `../../ADMIN/Works/IMPLEMENTATION_WORK_CRUD_SCREENS.md` §4
발생: 2026-07-15, `Work.episode_count`(column_property) 도입 직후 테스트 실행

## 증상

관리자 목록의 "총 N화"를 위해 `WorkRead.episode_count`를 추가하자, **일부 엔드포인트만** 500이 났다.

```
FAILED tests/test_admin_works.py::test_update_partial_preserves_other_fields
FAILED tests/test_admin_works.py::test_update_tag_names_omitted_keeps_tags
FAILED tests/test_admin_works.py::test_update_tag_names_empty_list_clears_tags
... (PUT 계열 7개)
FAILED tests/test_admin_episodes.py::test_upload_cover_sets_cover_image
8 failed, 59 passed
```

```
fastapi.exceptions.ResponseValidationError: 1 validation error:
  {'type': 'get_attribute_error',
   'loc': ('response', 'episode_count'),
   'msg': "Error extracting attribute: MissingGreenlet: greenlet_spawn has not been
           called; can't call await_only() here. Was IO attempted in an unexpected place?"}
```

**혼란스러운 부분**: `POST`(생성)·`GET`(목록/상세)는 **멀쩡히 통과**했다. 깨진 건 **커밋을 수반하는 나머지 경로**(PUT, 표지 업로드)뿐이다.

## 왜 헷갈리는가 (⚠️ 기존 처방이 안 듣는다)

이 저장소는 같은 `MissingGreenlet`을 이미 한 번 겪었고(C1의 `updated_at`), 그 결론이 문서·MISTAKES에 이렇게 남아 있다.

> 서버 계산 컬럼은 UPDATE 후 만료로 남는다 → `__mapper_args__ = {"eager_defaults": True}`로 UPDATE도 RETURNING.
> 콜사이트별 `session.refresh(...)` 열거는 다음 함수에서 하나 빠뜨리면 재발하는 **땜질**.

그래서 `Work`에는 **이미 `eager_defaults=True`가 걸려 있었다.** "그 정책으로 일반화했으니 이 문제는 닫혔다"고 읽기 딱 좋다. 그런데 안 듣는다.

## 원인

`eager_defaults`가 커버하는 건 **컬럼**(`server_default`·`onupdate` 같은 서버 계산 값)이다. `column_property`는 컬럼이 아니라 **SQL 표현식**이라 성질이 다르다.

```python
Work.episode_count = column_property(
    select(func.count(Episode.id))
    .where(Episode.work_id == Work.id)
    .correlate_except(Episode)
    .scalar_subquery()
)
```

1. **INSERT/UPDATE RETURNING에 실을 수 없다.** RETURNING은 그 행의 컬럼을 돌려주는 것이지, 다른 테이블을 세는 서브쿼리를 실행해주지 않는다 → `eager_defaults`가 해줄 게 없다.
2. **flush 후 만료된다.** SQLAlchemy는 UPDATE가 나가면 이 표현식의 값이 달라졌을 수 있다고 보고 속성을 expire시킨다(재계산하려면 다시 SELECT해야 하므로).

만료된 속성을 응답 직렬화(Pydantic `from_attributes`)가 읽으면 → lazy load 시도 → async 세션 밖 동기 IO → `MissingGreenlet`.

**경로별로 갈린 이유**가 이걸로 설명된다.

| 경로 | episode_count 상태 | 결과 |
|---|---|---|
| `GET` 목록/상세 | SELECT에 서브쿼리가 함께 실려 옴 | ✅ |
| `POST` 생성 | (미리 refresh를 넣어둠) | ✅ |
| `PUT` 수정 | 커밋 flush로 **만료** | 💥 |
| `POST` 표지 업로드 | 커밋 flush로 **만료** | 💥 |

처음엔 "INSERT엔 값이 없다"는 것만 예상해 **생성 경로에만** refresh를 넣었다. UPDATE 경로가 *이미 로드해 둔 값마저 잃는다*는 건 예상하지 못했고, 테스트가 그걸 잡았다.

## 해결

커밋을 수반하는 **모든** 경로에서 그 속성만 다시 로드한다.

```python
# services/work_service.py
async def _load_episode_count(work: Work, session: AsyncSession) -> None:
    await session.refresh(work, attribute_names=["episode_count"])
```

`create_work` / `update_work` / `set_cover_image` 세 곳의 `commit()` 뒤에 호출. `soft_delete_work`는 응답 본문이 없어(204) 불필요.

**여기서는 콜사이트 열거가 "땜질"이 아니라 유일한 수단이다.** `eager_defaults` 같은 매퍼 정책으로는 덮을 수 없다(위 원인 1). C1의 교훈("refresh 열거 대신 매퍼 정책")을 이 케이스에 그대로 적용하려 들면 답이 없다.

## 회귀 방지

`test_admin_works.py::test_episode_count_reflects_episodes`가 **생성·상세·목록·수정 네 경로를 모두 지나며** 값을 확인한다. 세 경로는 값을 얻는 방식이 서로 달라(커밋 후 refresh vs SELECT에 실려 옴) 하나만 검증하면 나머지가 조용히 깨진다.

## 교훈

- `MissingGreenlet`은 원인이 하나가 아니다. **"만료된 속성을 async 밖에서 읽었다"**는 증상이 같을 뿐, 만료된 이유(rollback / UPDATE 후 서버 계산 컬럼 / column_property)마다 처방이 다르다.
- 기존 처방을 그대로 대입하기 전에 **"내가 읽으려는 속성이 정확히 어떤 종류인가"**(컬럼인가, 표현식인가, 관계인가)를 먼저 확인할 것.
- MISTAKES.md "SQLAlchemy / AsyncSession"에 `eager_defaults`가 column_property를 커버하지 않는다는 항목을 추가해 뒀다.
