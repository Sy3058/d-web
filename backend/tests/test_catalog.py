"""공개 카탈로그 API 테스트 (M2 그룹 A).

인증 불요 - async_client(비로그인)로 직접 호출. 테스트 데이터는 admin API를 거치지
않고 ORM으로 직접 생성한다(공개 read 경로 자체가 검증 대상이므로 원인을 분리한다).
FK 부모(author)는 conftest의 user 픽스처, 자식(Work/Episode)은 여기서 직접 INSERT.
"""

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.user import User
from src.models.work import Episode, Tag, Work, WorkTag

WORKS_URL = "/works"


async def _make_work(db_session: AsyncSession, author: User, **overrides) -> Work:
    work = Work(
        author_id=author.id,
        title=overrides.pop("title", "테스트작"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    return work


async def _make_episode(db_session: AsyncSession, work: Work, **overrides) -> Episode:
    ep = Episode(
        work_id=work.id,
        episode_no=overrides.pop("episode_no", 1),
        title=overrides.pop("title", "1화"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(ep)
    await db_session.commit()
    await db_session.refresh(ep)
    return ep


# ---------------------------------------------------------------------------
# 목록
# ---------------------------------------------------------------------------


async def test_list_excludes_unpublished_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    published = await _make_work(db_session, user, title="공개작")
    await _make_work(db_session, user, title="비공개작", is_published=False)

    resp = await async_client.get(WORKS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert {item["id"] for item in body["items"]} == {str(published.id)}


async def test_list_excludes_soft_deleted_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    published = await _make_work(db_session, user, title="유지")
    deleted = await _make_work(db_session, user, title="삭제됨")
    deleted.deleted_at = datetime.now(UTC)
    db_session.add(deleted)
    await db_session.commit()

    resp = await async_client.get(WORKS_URL)
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(published.id) in ids
    assert str(deleted.id) not in ids


async def test_list_shows_work_with_zero_episodes(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 공개 회차가 0개(커밍순)여도 노출 - 사용자 확정 결정(2026-07-17)
    await _make_work(db_session, user, title="커밍순")

    resp = await async_client.get(WORKS_URL)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["episode_count"] == 0


async def test_list_episode_count_counts_only_published_episodes(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1, is_published=True)
    await _make_episode(db_session, work, episode_no=2, is_published=False)

    resp = await async_client.get(WORKS_URL)
    item = resp.json()["items"][0]
    assert item["episode_count"] == 1


async def test_list_pagination(async_client: AsyncClient, db_session: AsyncSession, user: User):
    for i in range(3):
        await _make_work(db_session, user, title=f"작품{i}")

    page1 = await async_client.get(WORKS_URL, params={"page": 1, "size": 2})
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["total"] == 3
    assert body1["page"] == 1
    assert body1["size"] == 2

    page2 = await async_client.get(WORKS_URL, params={"page": 2, "size": 2})
    assert len(page2.json()["items"]) == 1


async def test_list_tag_filter(async_client: AsyncClient, db_session: AsyncSession, user: User):
    work_romance = await _make_work(db_session, user, title="로맨스작")
    work_action = await _make_work(db_session, user, title="액션작")
    tag_romance = Tag(name="로맨스")
    tag_action = Tag(name="액션")
    db_session.add_all([tag_romance, tag_action])
    await db_session.commit()
    await db_session.refresh(tag_romance)
    await db_session.refresh(tag_action)
    db_session.add(WorkTag(work_id=work_romance.id, tag_id=tag_romance.id))
    db_session.add(WorkTag(work_id=work_action.id, tag_id=tag_action.id))
    await db_session.commit()

    resp = await async_client.get(WORKS_URL, params={"tag": "로맨스"})
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {str(work_romance.id)}


async def test_list_response_excludes_internal_fields(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(
        db_session,
        work,
        price=1234,
        image_keys=["secret-key.webp"],
        content={"type": "doc", "content": [{"type": "paragraph"}]},
    )

    resp = await async_client.get(WORKS_URL)
    item = resp.json()["items"][0]
    assert "content" not in item
    assert "image_keys" not in item
    assert "price" not in item
    assert "secret-key.webp" not in resp.text


async def test_list_cover_image_url_built_from_public_base(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    from src.config import settings

    monkeypatch.setattr(settings, "public_asset_base_url", "https://cover.example.com")
    await _make_work(db_session, user, cover_image="works/x/cover.webp")

    resp = await async_client.get(WORKS_URL)
    item = resp.json()["items"][0]
    assert item["cover_image_url"] == "https://cover.example.com/works/x/cover.webp"


async def test_list_cover_image_url_none_when_no_cover(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    await _make_work(db_session, user)
    resp = await async_client.get(WORKS_URL)
    assert resp.json()["items"][0]["cover_image_url"] is None


# ---------------------------------------------------------------------------
# 상세
# ---------------------------------------------------------------------------


async def test_detail_excludes_unpublished_episode(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    published = await _make_episode(db_session, work, episode_no=1, is_published=True)
    await _make_episode(db_session, work, episode_no=2, is_published=False)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    ep_ids = {ep["id"] for ep in resp.json()["episodes"]}
    assert ep_ids == {str(published.id)}


async def test_detail_episode_free_locked_purchased_flags(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1, is_free=True)
    await _make_episode(db_session, work, episode_no=2, is_free=False)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    episodes = {ep["episode_no"]: ep for ep in resp.json()["episodes"]}
    assert episodes[1]["is_free"] is True
    assert episodes[1]["is_locked"] is False
    assert episodes[2]["is_free"] is False
    assert episodes[2]["is_locked"] is True
    assert episodes[1]["is_purchased"] is False
    assert episodes[2]["is_purchased"] is False


async def test_detail_episode_thumbnail_always_null(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # D2(공개 축소본) 이전 - thumbnail이 원고 키로 세팅돼 있어도 응답엔 노출 금지
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1, thumbnail="works/x/episodes/y/abc123.webp")

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    ep = resp.json()["episodes"][0]
    assert ep["thumbnail_url"] is None
    assert "abc123.webp" not in resp.text


async def test_detail_excludes_internal_fields(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(
        db_session,
        work,
        price=1234,
        image_keys=["secret-key.webp"],
        content={
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "비밀내용"}]}],
        },
    )

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    body = resp.json()
    # 작품 레벨: 묶음 할인율은 M3 소관이라 공개 상세에 노출하지 않는다(리뷰 결정 2026-07-17).
    assert "bundle_discount_rate" not in body
    ep = body["episodes"][0]
    assert "content" not in ep
    assert "image_keys" not in ep
    assert "price" not in ep
    assert "secret-key.webp" not in resp.text
    assert "비밀내용" not in resp.text


async def test_detail_404_when_unpublished(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user, is_published=False)
    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    assert resp.status_code == 404


async def test_detail_404_when_soft_deleted(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    work.deleted_at = datetime.now(UTC)
    db_session.add(work)
    await db_session.commit()

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    assert resp.status_code == 404


async def test_detail_404_when_nonexistent(async_client: AsyncClient):
    resp = await async_client.get(f"{WORKS_URL}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
