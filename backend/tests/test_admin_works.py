"""작품 CRUD API 테스트 (M1.5 C1).

require_owner는 access 쿠키의 DB user.role + totp_confirmed_at을 본다(B3). 로그인 플로우
전체를 재현할 필요 없이 create_access_token + 쿠키 직접 set으로 인가 경계만 검증한다
(test_auth_endpoints.py와 동일 패턴 - MISTAKES: 점 있는 호스트 + domain 명시 필수).
"""

from datetime import UTC, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import access_cookie_name, create_access_token
from src.models.user import RoleEnum, User
from src.models.work import Tag
from src.services import auth_service, work_service

WORKS_URL = "/admin/works"


async def _authed(client: AsyncClient, user: User) -> None:
    token = create_access_token(str(user.id))
    client.cookies.set(access_cookie_name(), token, domain="test.example")


async def _create_work(client: AsyncClient, **fields) -> str:
    """작품 생성 후 id 반환. '생성 → id 추출' 2줄 반복을 한 곳으로 모은다."""
    resp = await client.post(WORKS_URL, json={"title": "작품", **fields})
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    """TOTP 활성 owner. require_owner 통과 조건(role=owner + totp_confirmed_at NOT NULL)."""
    user = await auth_service.create_user("owner@example.com", "OwnerPass1!", "작가", db_session)
    user.role = RoleEnum.OWNER
    user.totp_confirmed_at = datetime.now(UTC)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def owner_client(async_client: AsyncClient, owner: User) -> AsyncClient:
    await _authed(async_client, owner)
    return async_client


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


async def test_unauthenticated_401(async_client: AsyncClient):
    resp = await async_client.get(WORKS_URL)
    assert resp.status_code == 401


async def test_reader_forbidden_403(async_client: AsyncClient, existing_user: User):
    await _authed(async_client, existing_user)
    resp = await async_client.get(WORKS_URL)
    assert resp.status_code == 403


async def test_owner_totp_unconfirmed_forbidden_403(
    async_client: AsyncClient, user: User, db_session: AsyncSession
):
    # role=owner인데 totp_confirmed_at NULL - require_role의 잔존 세션 창 차단(B3)
    user.role = RoleEnum.OWNER
    db_session.add(user)
    await db_session.commit()
    await _authed(async_client, user)
    resp = await async_client.get(WORKS_URL)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 생성 + 태그
# ---------------------------------------------------------------------------


async def test_create_work_sets_author_and_tags(owner_client: AsyncClient, owner: User):
    resp = await owner_client.post(
        WORKS_URL,
        json={"title": "테스트 작품", "tag_names": ["로맨스", "판타지"]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["author_id"] == str(owner.id)
    assert {t["name"] for t in body["tags"]} == {"로맨스", "판타지"}
    assert body["episode_base_price"] == 500
    assert body["status"] == "ongoing"


async def test_create_work_reuses_existing_tag(owner_client: AsyncClient):
    first = await owner_client.post(WORKS_URL, json={"title": "작품1", "tag_names": ["개그"]})
    second = await owner_client.post(WORKS_URL, json={"title": "작품2", "tag_names": ["개그"]})
    assert first.status_code == 201
    assert second.status_code == 201
    tag_id_1 = first.json()["tags"][0]["id"]
    tag_id_2 = second.json()["tags"][0]["id"]
    assert tag_id_1 == tag_id_2  # 같은 이름 -> 같은 row 재사용


async def test_create_work_ignores_client_author_id(owner_client: AsyncClient, owner: User):
    spoofed = "00000000-0000-0000-0000-000000000000"
    resp = await owner_client.post(WORKS_URL, json={"title": "위조 시도", "author_id": spoofed})
    assert resp.status_code == 201
    assert resp.json()["author_id"] == str(owner.id)


async def test_create_work_status_preparing(owner_client: AsyncClient):
    # 연재 준비중(#84). VARCHAR(20)+StrEnum이라 enum 값 추가만으로 검증·저장·직렬화가
    # 끝나야 한다(마이그레이션 0건). 쓰기 응답은 요청 본문에서 만든 enum 멤버를 그대로
    # 돌려주므로(expire_on_commit=False) GET으로 재조회해 DB 읽기 경로까지 함께 고정한다.
    work_id = await _create_work(owner_client, title="준비중 작품", status="preparing")

    resp = await owner_client.get(f"{WORKS_URL}/{work_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "preparing"


async def test_create_work_preparing_can_be_published(owner_client: AsyncClient):
    # status와 is_published는 별개 축이다(#84). "준비중인데 공개"는 커밍순 티저라 정상
    # 조합이고 서버는 둘을 상호 강제하지 않는다. 조합이 저장·재조회를 살아남는지 고정해,
    # 이후 누군가 스키마·서비스에 상호 검증을 넣으면 여기서 깨지게 한다.
    work_id = await _create_work(
        owner_client, title="커밍순", status="preparing", is_published=True
    )

    body = (await owner_client.get(f"{WORKS_URL}/{work_id}")).json()
    assert body["status"] == "preparing"
    assert body["is_published"] is True


# ---------------------------------------------------------------------------
# 검증 실패 (422)
# ---------------------------------------------------------------------------


async def test_create_work_title_too_long_422(owner_client: AsyncClient):
    resp = await owner_client.post(WORKS_URL, json={"title": "가" * 201})
    assert resp.status_code == 422


async def test_create_work_invalid_discount_rate_422(owner_client: AsyncClient):
    resp = await owner_client.post(WORKS_URL, json={"title": "제목", "bundle_discount_rate": "1.1"})
    assert resp.status_code == 422


async def test_create_work_invalid_status_422(owner_client: AsyncClient):
    resp = await owner_client.post(WORKS_URL, json={"title": "제목", "status": "완결안됨"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 목록 / 조회
# ---------------------------------------------------------------------------


async def test_list_excludes_soft_deleted(owner_client: AsyncClient):
    keep_id = await _create_work(owner_client, title="유지")
    drop_id = await _create_work(owner_client, title="삭제될 것")
    await owner_client.delete(f"{WORKS_URL}/{drop_id}")

    resp = await owner_client.get(WORKS_URL)
    ids = {w["id"] for w in resp.json()}
    assert keep_id in ids
    assert drop_id not in ids


async def test_get_work_404(owner_client: AsyncClient):
    resp = await owner_client.get(f"{WORKS_URL}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 수정
# ---------------------------------------------------------------------------


async def test_update_work_status_to_preparing_keeps_published(owner_client: AsyncClient):
    # 상태만 바꾸는 PUT은 공개 여부를 건드리지 않는다(#84 - 별개 축). 공개 중인 작품을
    # 준비중으로 내려도 is_published는 그대로다. 숨길지 말지는 어드민 폼의 기본값 연동이나
    # 명시적인 공개 설정이 정하고, 서버가 상태를 근거로 대신 정하지 않는다.
    work_id = await _create_work(owner_client, is_published=True)

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"status": "preparing"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "preparing"
    assert resp.json()["is_published"] is True

    body = (await owner_client.get(f"{WORKS_URL}/{work_id}")).json()
    assert body["status"] == "preparing"
    assert body["is_published"] is True


async def test_update_partial_preserves_other_fields(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, title="원제", synopsis="원 시놉시스")

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"title": "새 제목"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "새 제목"
    assert body["synopsis"] == "원 시놉시스"  # 미지정 필드 보존


async def test_update_tag_names_omitted_keeps_tags(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, tag_names=["로맨스"])

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"title": "제목 변경"})
    assert {t["name"] for t in resp.json()["tags"]} == {"로맨스"}


async def test_update_tag_names_empty_list_clears_tags(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, tag_names=["로맨스"])

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"tag_names": []})
    assert resp.json()["tags"] == []


async def test_update_tag_names_replaces_tags(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, tag_names=["로맨스"])

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"tag_names": ["액션"]})
    assert {t["name"] for t in resp.json()["tags"]} == {"액션"}


async def test_update_work_404(owner_client: AsyncClient):
    resp = await owner_client.put(
        f"{WORKS_URL}/00000000-0000-0000-0000-000000000000", json={"title": "x"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 삭제
# ---------------------------------------------------------------------------


async def test_delete_work_soft_deletes(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, title="삭제 대상")

    resp = await owner_client.delete(f"{WORKS_URL}/{work_id}")
    assert resp.status_code == 204
    assert (await owner_client.get(f"{WORKS_URL}/{work_id}")).status_code == 404


async def test_delete_already_deleted_404(owner_client: AsyncClient):
    work_id = await _create_work(owner_client, title="삭제 대상")
    await owner_client.delete(f"{WORKS_URL}/{work_id}")

    resp = await owner_client.delete(f"{WORKS_URL}/{work_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 리뷰 발견 회귀 (2026-07-09)
# ---------------------------------------------------------------------------


async def test_update_explicit_null_on_required_field_422(owner_client: AsyncClient):
    # X | None의 None은 "생략" 표현이지 null 대입 허용이 아니다 - NOT NULL 필드에
    # 명시적 null은 422 (안 막으면 NOT NULL 위반 500).
    work_id = await _create_work(owner_client)
    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"title": None})
    assert resp.status_code == 422


async def test_update_explicit_null_clears_nullable_field(owner_client: AsyncClient):
    # nullable 컬럼(synopsis)은 명시적 null = "비우기"가 유효한 의미 - 계속 허용돼야 한다.
    work_id = await _create_work(owner_client, synopsis="지울 시놉시스")
    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"synopsis": None})
    assert resp.status_code == 200
    assert resp.json()["synopsis"] is None


async def test_update_tags_only_bumps_updated_at(owner_client: AsyncClient):
    # 다대다 연결만 바뀌면 works 행 UPDATE가 없어 onupdate가 발화하지 않는다 -
    # 서비스가 명시 갱신하는지 확인 (안 하면 updated_at이 태그 변경을 반영 못 함).
    work_id = await _create_work(owner_client)
    before = (await owner_client.get(f"{WORKS_URL}/{work_id}")).json()["updated_at"]

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"tag_names": ["액션"]})
    assert resp.status_code == 200
    after = resp.json()["updated_at"]
    assert datetime.fromisoformat(after) > datetime.fromisoformat(before)


async def test_update_tag_race_recovered_without_session_crash(
    owner_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """UNIQUE 경합 폴백의 결정적 재현: 태그를 미리 커밋해 두고 첫 SELECT만 '상대 커밋을
    못 본' 것처럼 비워, flush가 실제 UNIQUE 충돌을 맞게 한다. SAVEPOINT 격리 덕에 로드된
    work가 만료되지 않아 work.tags 대입이 크래시(MissingGreenlet) 없이 재조회 행으로
    복구되는지 검증한다(전체 rollback 방식이었다면 이 테스트가 500으로 깨진다)."""
    work_id = await _create_work(owner_client)
    db_session.add(Tag(name="경합태그"))
    await db_session.commit()

    real_select = work_service._select_tags_by_name
    calls = {"count": 0}

    async def first_call_blind(names: list[str], session: AsyncSession) -> dict[str, Tag]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {}
        return await real_select(names, session)

    monkeypatch.setattr(work_service, "_select_tags_by_name", first_call_blind)

    resp = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"tag_names": ["경합태그"]})
    assert resp.status_code == 200
    assert {t["name"] for t in resp.json()["tags"]} == {"경합태그"}
    assert calls["count"] == 2  # 초회(빈 결과) + 충돌 후 재조회


async def test_episode_count_reflects_episodes(owner_client: AsyncClient) -> None:
    """episode_count(column_property)가 생성·상세·목록 세 경로 모두에서 채워지는지.

    세 경로는 값을 얻는 방식이 다르다 - 생성/수정은 커밋 후 refresh, 상세/목록은 SELECT에
    실려 오는 상관 서브쿼리. 하나라도 빠지면 그 응답만 MissingGreenlet으로 500이 난다.
    """
    resp = await owner_client.post(WORKS_URL, json={"title": "작품"})
    assert resp.status_code == 201
    work_id = resp.json()["id"]
    assert resp.json()["episode_count"] == 0

    for episode_no in (1, 2):
        created = await owner_client.post(
            f"{WORKS_URL}/{work_id}/episodes",
            json={"episode_no": episode_no, "title": f"{episode_no}화"},
        )
        assert created.status_code == 201

    detail = await owner_client.get(f"{WORKS_URL}/{work_id}")
    assert detail.json()["episode_count"] == 2

    listed = (await owner_client.get(WORKS_URL)).json()
    assert next(w for w in listed if w["id"] == work_id)["episode_count"] == 2

    # 수정 응답도 refresh 경로를 탄다(값 자체는 안 변한다).
    updated = await owner_client.put(f"{WORKS_URL}/{work_id}", json={"title": "새 제목"})
    assert updated.json()["episode_count"] == 2
