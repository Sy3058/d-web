"""공개 카탈로그 API 테스트 (M2 그룹 A).

인증 불요 - async_client(비로그인)로 직접 호출. 테스트 데이터는 admin API를 거치지
않고 ORM으로 직접 생성한다(공개 read 경로 자체가 검증 대상이므로 원인을 분리한다).
FK 부모(author)는 conftest의 user 픽스처, 자식(Work/Episode)은 여기서 직접 INSERT.
"""

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.user import User
from src.models.work import Tag, Work, WorkTag
from tests.factories import make_episode as _make_episode
from tests.factories import make_work as _make_work

WORKS_URL = "/works"


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


async def test_list_size_over_max_422(async_client: AsyncClient):
    # size 상한은 조용한 클램프가 아니라 422 명시 거부 - 응답 size로 페이지 수를
    # 계산하는 클라이언트가 실제 반환량과 어긋나지 않게 (코드리뷰 2026-07-18 반영)
    resp = await async_client.get(WORKS_URL, params={"size": 101})
    assert resp.status_code == 422


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
    work = await _make_work(db_session, user, cover_image="works/x/cover.webp")

    resp = await async_client.get(WORKS_URL)
    item = resp.json()["items"][0]
    expected_version = int(work.updated_at.timestamp())
    assert (
        item["cover_image_url"]
        == f"https://cover.example.com/works/x/cover.webp?v={expected_version}"
    )


async def test_list_cover_image_url_trailing_slash_base_normalized(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    # .env에 base를 트레일링 슬래시로 넣는 실수가 이중 슬래시 URL로 번지지 않아야 한다
    from src.config import settings

    monkeypatch.setattr(settings, "public_asset_base_url", "https://cover.example.com/")
    work = await _make_work(db_session, user, cover_image="works/x/cover.webp")

    resp = await async_client.get(WORKS_URL)
    item = resp.json()["items"][0]
    expected_version = int(work.updated_at.timestamp())
    assert (
        item["cover_image_url"]
        == f"https://cover.example.com/works/x/cover.webp?v={expected_version}"
    )


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


async def test_detail_episode_thumbnail_url_from_public_bucket(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    # M2 D2: thumbnail(원고 키)이 세팅돼 있으면 결정적 공개 축소본 키로 URL이 뜬다 -
    # 단, 응답에 실리는 건 그 파생 키뿐이고 원고 페이지 키 자체는 절대 노출되면 안 된다.
    from src.config import settings
    from src.services import r2_service

    monkeypatch.setattr(settings, "public_asset_base_url", "https://cover.example.com")
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session, work, episode_no=1, thumbnail="works/x/episodes/y/abc123.webp"
    )

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    body = resp.json()["episodes"][0]
    expected_key = r2_service.episode_thumb_key(work.id, ep.id)
    expected_version = int(ep.updated_at.timestamp())
    assert body["thumbnail_url"] == f"https://cover.example.com/{expected_key}?v={expected_version}"
    assert "abc123.webp" not in resp.text


async def test_detail_episode_thumbnail_falls_back_to_work_cover(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    # 회차 썸네일 미선택 시 작품 표지로 대체(M2 D2 결정) - 원고 첫 페이지 fallback 금지.
    from src.config import settings

    monkeypatch.setattr(settings, "public_asset_base_url", "https://cover.example.com")
    work = await _make_work(db_session, user, cover_image="works/x/cover.webp")
    await _make_episode(db_session, work, episode_no=1)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    body = resp.json()["episodes"][0]
    assert body["thumbnail_url"].startswith("https://cover.example.com/works/x/cover.webp?v=")


async def test_detail_episode_thumbnail_none_when_no_thumbnail_and_no_cover(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    body = resp.json()["episodes"][0]
    assert body["thumbnail_url"] is None


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
        draft={
            "title": "비밀 제목",
            "subtitle": None,
            "content": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "비밀편집본"}]}
                ],
            },
        },
    )

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    body = resp.json()
    # 작품 레벨: 묶음 할인율은 M3 소관이라 공개 상세에 노출하지 않는다(리뷰 결정 2026-07-17).
    assert "bundle_discount_rate" not in body
    ep = body["episodes"][0]
    assert "content" not in ep
    assert "image_keys" not in ep
    # 편집본(#86)은 owner 전용 - 공개 상세에 필드도 내용도 실리면 안 된다.
    assert "draft" not in ep
    # price는 #83부터 실효 판매가로 의도적 공개(내부값 은닉 대상에서 제외) - 위 오버라이드 값
    assert ep["price"] == 1234
    assert "secret-key.webp" not in resp.text
    assert "비밀내용" not in resp.text
    assert "비밀편집본" not in resp.text


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


# ---------------------------------------------------------------------------
# 회차 실효 가격 (#83)
# ---------------------------------------------------------------------------


async def test_detail_episode_price_override(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user, episode_base_price=500)
    await _make_episode(db_session, work, episode_no=1, is_free=False, price=1200)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    assert resp.json()["episodes"][0]["price"] == 1200


async def test_detail_episode_price_falls_back_to_base_price(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user, episode_base_price=700)
    await _make_episode(db_session, work, episode_no=1, is_free=False, price=None)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    assert resp.json()["episodes"][0]["price"] == 700


async def test_detail_free_episode_price_is_null(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 무료 회차는 price가 세팅돼 있어도 null - 0원 판매와 구분 + is_free 무시 표기 방지
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1, is_free=True, price=900)

    resp = await async_client.get(f"{WORKS_URL}/{work.id}")
    ep = resp.json()["episodes"][0]
    assert ep["is_free"] is True
    assert ep["price"] is None


# ---------------------------------------------------------------------------
# 공개 태그 목록 (#82)
# ---------------------------------------------------------------------------

TAGS_URL = "/tags"


async def _attach_tag(db_session: AsyncSession, work: Work, name: str) -> Tag:
    tag = Tag(name=name)
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    db_session.add(WorkTag(work_id=work.id, tag_id=tag.id))
    await db_session.commit()
    return tag


async def test_tags_lists_public_work_tags_with_counts(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work_a = await _make_work(db_session, user, title="작품A")
    work_b = await _make_work(db_session, user, title="작품B")
    fantasy = await _attach_tag(db_session, work_a, "판타지")
    db_session.add(WorkTag(work_id=work_b.id, tag_id=fantasy.id))
    await db_session.commit()
    await _attach_tag(db_session, work_b, "액션")

    resp = await async_client.get(TAGS_URL)
    assert resp.status_code == 200
    body = resp.json()
    # order_by(Tag.name) - 액션 < 판타지 (가나다순)
    assert [(t["name"], t["work_count"]) for t in body] == [("액션", 1), ("판타지", 2)]


async def test_tags_work_count_excludes_hidden_works(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 같은 태그가 공개작·비공개작에 걸쳐 달린 경우. 아래 "단독 비공개" 케이스는 태그가
    # 통째로 빠지는지만 보므로 카운트 산술 자체는 여기서 검증한다 - 숫자가 부풀면 그
    # 값이 숨긴 작품의 존재를 흘린다.
    public_work = await _make_work(db_session, user, title="공개작")
    hidden = await _make_work(db_session, user, title="준비중", is_published=False)
    tag = await _attach_tag(db_session, public_work, "판타지")
    db_session.add(WorkTag(work_id=hidden.id, tag_id=tag.id))
    await db_session.commit()

    resp = await async_client.get(TAGS_URL)
    assert [(t["name"], t["work_count"]) for t in resp.json()] == [("판타지", 1)]


async def test_tags_excludes_tag_only_on_unpublished_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 미공개 작품에만 달린 태그가 보이면 미공개 작품의 존재가 샌다
    hidden = await _make_work(db_session, user, title="준비중", is_published=False)
    await _attach_tag(db_session, hidden, "비밀태그")

    resp = await async_client.get(TAGS_URL)
    assert resp.json() == []
    assert "비밀태그" not in resp.text


async def test_tags_excludes_tag_only_on_soft_deleted_work(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user, title="내려간작품")
    await _attach_tag(db_session, work, "삭제작태그")
    work.deleted_at = datetime.now(UTC)
    db_session.add(work)
    await db_session.commit()

    resp = await async_client.get(TAGS_URL)
    assert resp.json() == []


async def test_tags_empty_when_no_tags(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 태그 없는 공개 작품만 있으면 빈 배열(200) - 404가 아니다
    await _make_work(db_session, user)
    resp = await async_client.get(TAGS_URL)
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 회차 목록 (M2 B1)
# ---------------------------------------------------------------------------


def _episodes_url(work_id) -> str:
    return f"{WORKS_URL}/{work_id}/episodes"


async def test_episodes_excludes_unpublished_episode(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    published = await _make_episode(db_session, work, episode_no=1)
    await _make_episode(db_session, work, episode_no=2, is_published=False)

    resp = await async_client.get(_episodes_url(work.id))
    assert resp.status_code == 200
    assert [ep["id"] for ep in resp.json()] == [str(published.id)]


async def test_episodes_ordered_by_episode_no(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    # 생성 순서를 역으로 - 정렬이 삽입 순서가 아니라 episode_no를 따르는지 본다.
    await _make_episode(db_session, work, episode_no=3, title="3화")
    await _make_episode(db_session, work, episode_no=1, title="1화")
    await _make_episode(db_session, work, episode_no=2, title="2화")

    resp = await async_client.get(_episodes_url(work.id))
    assert [ep["episode_no"] for ep in resp.json()] == [1, 2, 3]


async def test_episodes_match_detail_payload(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    """B1과 A2가 같은 배열을 낸다(드리프트 감시).

    두 엔드포인트가 같은 서비스 함수를 쓰므로 구조적으로 어긋날 수 없지만, 누가
    B1에 별도 쿼리를 넣는 순간 여기서 깨진다.
    """
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, episode_no=1)
    await _make_episode(db_session, work, episode_no=2, is_free=True)

    listed = await async_client.get(_episodes_url(work.id))
    detail = await async_client.get(f"{WORKS_URL}/{work.id}")
    assert listed.json() == detail.json()["episodes"]


async def test_episodes_empty_list_when_none_published(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 커밍순(공개 회차 0개) 작품은 빈 배열 200 - 404가 아니다.
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work, is_published=False)

    resp = await async_client.get(_episodes_url(work.id))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_episodes_404_when_work_unpublished(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user, is_published=False)
    await _make_episode(db_session, work)

    resp = await async_client.get(_episodes_url(work.id))
    assert resp.status_code == 404


async def test_episodes_404_when_work_soft_deleted(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    await _make_episode(db_session, work)
    work.deleted_at = datetime.now(UTC)
    db_session.add(work)
    await db_session.commit()

    resp = await async_client.get(_episodes_url(work.id))
    assert resp.status_code == 404


async def test_episodes_404_when_work_nonexistent(async_client: AsyncClient):
    resp = await async_client.get(_episodes_url(uuid.uuid4()))
    assert resp.status_code == 404


async def test_404_is_not_cached(async_client: AsyncClient, db_session: AsyncSession, user: User):
    """숨긴 작품의 404가 캐시되면 공개 토글을 켜도 독자가 계속 404를 본다.

    404는 명세상 기본 캐시 가능 상태 코드라 명시적 헤더가 없으면 heuristic 캐싱
    대상이 된다. 상세·회차목록이 같은 _NOT_FOUND를 쓴다(목록 GET /works는 결과가
    없어도 빈 배열 200이라 404 경로가 없다).
    """
    work = await _make_work(db_session, user, is_published=False)

    for url in (f"{WORKS_URL}/{work.id}", _episodes_url(work.id)):
        resp = await async_client.get(url)
        assert resp.status_code == 404
        assert resp.headers.get("cache-control") == "no-store"
