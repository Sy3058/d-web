"""뷰어 진행도 API 테스트 (M2 그룹 C1).

인증 필수 - test_admin_episodes.py와 동일 패턴(쿠키 직접 set - 로그인 플로우
재현 불필요). 작품/회차 생성은 tests/factories.py 공용 헬퍼를 쓴다.
"""

import uuid
from datetime import UTC, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import access_cookie_name, create_access_token
from src.models.user import User
from src.models.viewer import ViewerProgress
from tests.factories import make_episode, make_work

INT32_MAX = 2_147_483_647


def _progress_url(episode_id: uuid.UUID | str) -> str:
    return f"/episodes/{episode_id}/progress"


async def _authed(client: AsyncClient, user: User) -> None:
    """이 클라이언트의 이후 요청을 해당 유저로 인증한다(다시 부르면 유저가 바뀐다)."""
    token = create_access_token(str(user.id))
    client.cookies.set(access_cookie_name(), token, domain="test.example")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """교차 유저 격리 검증용 두 번째 유저(conftest의 user와 다른 계정)."""
    u = User(email="other@example.com", nickname="other")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# PUT - 저장/갱신
# ---------------------------------------------------------------------------


async def test_put_creates_new_progress(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_id"] == str(ep.id)
    assert body["page_no"] == 3


async def test_put_twice_updates_same_row(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 9})
    assert resp.status_code == 200
    assert resp.json()["page_no"] == 9

    rows = (
        await db_session.exec(
            select(ViewerProgress).where(
                ViewerProgress.user_id == user.id, ViewerProgress.episode_id == ep.id
            )
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].page_no == 9


async def test_put_twice_bumps_updated_at(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # onupdate=func.now()는 ON CONFLICT DO UPDATE에 자동 적용되지 않는다 - set_에
    # updated_at을 명시하지 않으면 조용히 최초 삽입 시각에 멈춘다(에러 없음).
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    first = await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    second = await async_client.put(_progress_url(ep.id), json={"page_no": 2})

    first_ts = datetime.fromisoformat(first.json()["updated_at"])
    second_ts = datetime.fromisoformat(second.json()["updated_at"])
    assert second_ts > first_ts


async def test_put_requires_login(async_client: AsyncClient, db_session: AsyncSession, user: User):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    assert resp.status_code == 401


async def test_put_rejects_unpublished_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user, is_published=False)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    assert resp.status_code == 404


async def test_put_rejects_soft_deleted_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    work.deleted_at = datetime.now(UTC)
    db_session.add(work)
    await db_session.commit()
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    assert resp.status_code == 404


async def test_put_rejects_unpublished_episode(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work, is_published=False)
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": 1})
    assert resp.status_code == 404


async def test_put_rejects_nonexistent_episode(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    await _authed(async_client, user)
    resp = await async_client.put(_progress_url(uuid.uuid4()), json={"page_no": 1})
    assert resp.status_code == 404


async def test_put_rejects_negative_page_no(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": -1})
    assert resp.status_code == 422


async def test_put_rejects_page_no_over_int32(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 컬럼이 4바이트 Integer라 상한이 없으면 asyncpg가 DataError를 던져 500이 된다.
    # 스키마 le=INT32_MAX로 DB에 닿기 전에 422로 거부해야 한다.
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    resp = await async_client.put(_progress_url(ep.id), json={"page_no": INT32_MAX + 1})
    assert resp.status_code == 422

    ok = await async_client.put(_progress_url(ep.id), json={"page_no": INT32_MAX})
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# GET - 조회
# ---------------------------------------------------------------------------


async def test_get_restores_saved_progress(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    await async_client.put(_progress_url(ep.id), json={"page_no": 7})
    resp = await async_client.get(_progress_url(ep.id))
    assert resp.status_code == 200
    assert resp.json()["page_no"] == 7


async def test_get_without_saved_progress_404(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    resp = await async_client.get(_progress_url(ep.id))
    assert resp.status_code == 404


async def test_get_requires_login(async_client: AsyncClient, db_session: AsyncSession, user: User):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)

    resp = await async_client.get(_progress_url(ep.id))
    assert resp.status_code == 401


async def test_missing_progress_message_differs_from_missing_episode(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 회차는 멀쩡히 존재하는데 "회차를 찾을 수 없습니다"를 내리면 FE가 틀린 오류를 띄운다.
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    no_progress = await async_client.get(_progress_url(ep.id))
    no_episode = await async_client.put(_progress_url(uuid.uuid4()), json={"page_no": 1})

    assert no_progress.status_code == no_episode.status_code == 404
    assert no_progress.json()["detail"] != no_episode.json()["detail"]


# ---------------------------------------------------------------------------
# 교차 유저 격리
# ---------------------------------------------------------------------------


async def test_get_does_not_return_other_users_progress(
    async_client: AsyncClient, db_session: AsyncSession, user: User, other_user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)

    await _authed(async_client, user)
    await async_client.put(_progress_url(ep.id), json={"page_no": 5})

    await _authed(async_client, other_user)
    resp = await async_client.get(_progress_url(ep.id))
    assert resp.status_code == 404


async def test_each_user_keeps_own_progress(
    async_client: AsyncClient, db_session: AsyncSession, user: User, other_user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)

    await _authed(async_client, user)
    await async_client.put(_progress_url(ep.id), json={"page_no": 3})
    await _authed(async_client, other_user)
    await async_client.put(_progress_url(ep.id), json={"page_no": 8})

    # 서로 덮어쓰지 않고 각자의 행이 남는다(UNIQUE는 user_id+episode_id 쌍 기준).
    assert (await async_client.get(_progress_url(ep.id))).json()["page_no"] == 8
    await _authed(async_client, user)
    assert (await async_client.get(_progress_url(ep.id))).json()["page_no"] == 3

    rows = (
        await db_session.exec(select(ViewerProgress).where(ViewerProgress.episode_id == ep.id))
    ).all()
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# 캐시 헤더
# ---------------------------------------------------------------------------


async def test_responses_are_not_cached(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work)
    await _authed(async_client, user)

    put_resp = await async_client.put(_progress_url(ep.id), json={"page_no": 2})
    get_resp = await async_client.get(_progress_url(ep.id))

    assert put_resp.headers["cache-control"] == "no-store"
    assert get_resp.headers["cache-control"] == "no-store"
