"""뷰어 초기 메타의 인가·노출 allowlist·공개 네비 계약."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from src.config import settings
from src.lib import auth
from src.models.payment import Purchase, PurchaseStatus
from src.models.work import Work
from src.schemas.work import EpisodeUpdate, WorkUpdate
from src.services import episode_service, r2_service, work_service
from tests.factories import PAYWALL, doc, img, make_episode, make_purchase, make_work, para

pytestmark = pytest.mark.asyncio


def url(work, episode):
    return f"/works/{work.id}/episodes/{episode.public_id}/viewer-bootstrap"


def login(client, user):
    client.cookies.set(
        auth.access_cookie_name(), auth.create_access_token(str(user.id)), domain="test.example"
    )


def assert_no_store(response, status):
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture
def after_bootstrap_read(db_session, monkeypatch):
    """실제 SELECT 완료 뒤 독립 편집 커밋을 끼우되 후속 요청에는 반복하지 않는다."""
    original = db_session.exec

    def install(action):
        fired = False

        async def read_then_edit(statement, *args, **kwargs):
            nonlocal fired
            result = await original(statement, *args, **kwargs)
            columns = getattr(statement, "selected_columns", ())
            if not fired and "previous_public_id" in columns:
                fired = True
                await action()
            return result

        monkeypatch.setattr(db_session, "exec", read_then_edit)

    return install


async def test_public_metadata_allowlist_without_content_issuance(
    async_client, db_session, user, monkeypatch
):
    work = await make_work(db_session, user, title="작품")
    episode = await make_episode(
        db_session,
        work,
        title="현재 회차",
        subtitle="부제",
        content=doc(para("무료"), PAYWALL, img()),
        image_keys=["works/w/episodes/e/page.webp"],
        price=800,
    )
    purchase, _ = await make_purchase(db_session, user, episode)
    login(async_client, user)
    presign = AsyncMock()
    monkeypatch.setattr(r2_service, "presign_get_urls", presign)

    response = await async_client.get(url(work, episode))

    assert_no_store(response, 200)
    assert response.json() == {
        "work_id": str(work.id),
        "work_title": "작품",
        "episode_id": str(episode.id),
        "public_id": episode.public_id,
        "episode_title": "현재 회차",
        "episode_subtitle": "부제",
        "previous_episode": None,
        "next_episode": None,
    }
    presign.assert_not_called()
    assert (
        await db_session.exec(select(Purchase.first_viewed_at).where(Purchase.id == purchase.id))
    ).one() is None


@pytest.mark.parametrize("hidden", ["work", "episode", "both"])
@pytest.mark.parametrize("purchased", [False, True])
async def test_hidden_metadata_requires_active_purchase(
    async_client, db_session, user, hidden, purchased
):
    work = await make_work(db_session, user, is_published=hidden == "episode")
    episode = await make_episode(
        db_session,
        work,
        is_published=hidden == "work",
        content=doc(PAYWALL, para("유료")),
    )
    await make_episode(db_session, work, sort_order=0, title="공개 이웃")
    if purchased:
        await make_purchase(db_session, user, episode)
        login(async_client, user)
    response = await async_client.get(url(work, episode))
    assert_no_store(response, 200 if purchased else 404)
    if purchased and hidden != "episode":
        assert response.json()["previous_episode"] is None
        assert response.json()["next_episode"] is None
    if not purchased:
        assert set(response.json()) == {"detail"}


@pytest.mark.parametrize(
    "invalid",
    [
        "other_user",
        "other_episode",
        "environment",
        "refund_pending",
        "refunded",
    ],
)
async def test_invalid_purchase_cannot_disclose_hidden_metadata(
    async_client, db_session, user, existing_user, invalid
):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session, work, is_published=False, content=doc(PAYWALL, para("유료"))
    )
    target = await make_episode(db_session, work) if invalid == "other_episode" else episode
    status = {
        "refund_pending": PurchaseStatus.REFUND_PENDING,
        "refunded": PurchaseStatus.REFUNDED,
    }.get(invalid, PurchaseStatus.ACTIVE)
    wrong_environment = "live" if settings.payment_environment == "test" else "test"
    await make_purchase(
        db_session,
        existing_user if invalid == "other_user" else user,
        target,
        environment=wrong_environment if invalid == "environment" else settings.payment_environment,
        status=status,
    )
    login(async_client, user)
    assert_no_store(await async_client.get(url(work, episode)), 404)


@pytest.mark.parametrize("deleted", ["work", "episode"])
async def test_deleted_is_hidden_even_from_purchaser(async_client, db_session, user, deleted):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    await make_purchase(db_session, user, episode)
    (work if deleted == "work" else episode).deleted_at = datetime.now(UTC)
    await db_session.commit()
    login(async_client, user)
    assert_no_store(await async_client.get(url(work, episode)), 404)


async def test_wrong_work_and_missing_episode_are_404(async_client, db_session, user):
    work = await make_work(db_session, user)
    other = await make_work(db_session, user)
    episode = await make_episode(db_session, work)
    assert_no_store(await async_client.get(url(other, episode)), 404)
    assert_no_store(
        await async_client.get(f"/works/{work.id}/episodes/99999999/viewer-bootstrap"), 404
    )
    assert_no_store(
        await async_client.get(
            f"/works/{uuid.uuid4()}/episodes/{episode.public_id}/viewer-bootstrap"
        ),
        404,
    )


@pytest.mark.parametrize(
    ("work_id", "public_id"),
    [("bad-uuid", "12345678")]
    + [
        ("00000000-0000-0000-0000-000000000000", value)
        for value in ["abc", "-1", "9999999", "100000000", "2147483648", "1e8"]
    ],
)
async def test_invalid_path_is_422_no_store(async_client, work_id, public_id):
    assert_no_store(
        await async_client.get(f"/works/{work_id}/episodes/{public_id}/viewer-bootstrap"), 422
    )


async def test_invalid_cookie_cannot_disclose_hidden_metadata(async_client, db_session, user):
    work = await make_work(db_session, user, is_published=False)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    await make_purchase(db_session, user, episode)
    async_client.cookies.set(auth.access_cookie_name(), "forged-token", domain="test.example")
    response = await async_client.get(url(work, episode))
    assert_no_store(response, 404)
    assert "set-cookie" not in response.headers
    assert set(response.json()) == {"detail"}


@pytest.mark.parametrize("published", [True, False])
async def test_document_validation_is_preserved(async_client, db_session, user, published):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session, work, is_published=published, content=doc({"type": "unknown"})
    )
    await make_purchase(db_session, user, episode)
    login(async_client, user)
    assert_no_store(await async_client.get(url(work, episode)), 200 if published else 404)


@pytest.mark.parametrize("published", [True, False])
async def test_navigation_uses_catalog_order_and_only_public_neighbors(
    async_client, db_session, user, published
):
    work = await make_work(db_session, user)
    # 생성 순서·sort_order·created_at·UUID를 역전시켜 각 정렬 키를 고정한다.
    now = datetime.now(UTC)
    following = await make_episode(db_session, work, sort_order=20, title="다음")
    await make_episode(db_session, work, sort_order=11, is_published=False, title="숨김")
    await make_episode(db_session, work, sort_order=12, deleted_at=now, title="삭제")
    previous = await make_episode(
        db_session, work, sort_order=10, created_at=now, id=uuid.UUID(int=1), title="이전"
    )
    current = await make_episode(
        db_session,
        work,
        sort_order=10,
        created_at=now,
        id=uuid.UUID(int=2),
        is_published=published,
        content=doc(PAYWALL, para("유료")),
    )
    await make_episode(
        db_session,
        work,
        sort_order=10,
        created_at=now - timedelta(days=1),
        id=uuid.UUID(int=3),
        title="더 이전",
    )
    if not published:
        await make_purchase(db_session, user, current)
        login(async_client, user)
    response = await async_client.get(url(work, current))
    assert_no_store(response, 200)
    assert response.json()["previous_episode"] == {
        "public_id": previous.public_id,
        "title": previous.title,
    }
    assert response.json()["next_episode"] == {
        "public_id": following.public_id,
        "title": following.title,
    }
    assert "숨김" not in response.text
    assert "삭제" not in response.text


async def test_first_and_last_navigation_boundaries(async_client, db_session, user):
    work = await make_work(db_session, user)
    last = await make_episode(db_session, work, sort_order=2)
    first = await make_episode(db_session, work, sort_order=1)
    first_response = await async_client.get(url(work, first))
    last_response = await async_client.get(url(work, last))
    assert first_response.json()["previous_episode"] is None
    assert first_response.json()["next_episode"]["public_id"] == last.public_id
    assert last_response.json()["previous_episode"]["public_id"] == first.public_id
    assert last_response.json()["next_episode"] is None


@pytest.mark.parametrize("reordered", [(1, 2, 0), (2, 0, 1)])
async def test_navigation_keeps_one_snapshot_during_reorder(
    async_client, db_session, session_factory, user, after_bootstrap_read, reordered
):
    work = await make_work(db_session, user)
    first = await make_episode(db_session, work, sort_order=1, title="A")
    current = await make_episode(db_session, work, sort_order=2, title="B")
    last = await make_episode(db_session, work, sort_order=3, title="C")
    episodes = [first, current, last]

    async def reorder_after_read():
        async with session_factory() as editor:
            await episode_service.reorder_episodes(
                work.id, [episodes[index].id for index in reordered], editor
            )

    after_bootstrap_read(reorder_after_read)
    response = await async_client.get(url(work, current))

    assert_no_store(response, 200)
    assert response.json()["previous_episode"] == {"public_id": first.public_id, "title": "A"}
    assert response.json()["next_episode"] == {"public_id": last.public_id, "title": "C"}


@pytest.mark.parametrize("published", ["episode", "work"])
async def test_publish_cannot_authorize_old_private_metadata(
    async_client, db_session, session_factory, user, after_bootstrap_read, published
):
    work = await make_work(
        db_session, user, title="PRIVATE_WORK_TITLE", is_published=published == "episode"
    )
    current = await make_episode(
        db_session,
        work,
        title="PRIVATE_EPISODE_TITLE",
        subtitle="PRIVATE_SUBTITLE",
        is_published=published == "work",
        content=doc(para("무료 본문")),
    )

    async def publish_after_read():
        async with session_factory() as editor:
            episode = await episode_service.get_episode(work.id, current.id, editor)
            await episode_service.update_episode(
                episode,
                EpisodeUpdate(
                    title="PUBLIC_EPISODE_TITLE", subtitle="PUBLIC_SUBTITLE", is_published=True
                ),
                editor,
            )
            if published == "work":
                editable_work = (await editor.exec(select(Work).where(Work.id == work.id))).one()
                await work_service.update_work(
                    editable_work, WorkUpdate(title="PUBLIC_WORK_TITLE", is_published=True), editor
                )

    after_bootstrap_read(publish_after_read)
    response = await async_client.get(url(work, current))
    assert_no_store(response, 404)
    assert "PRIVATE_" not in response.text

    following = await async_client.get(url(work, current))
    assert_no_store(following, 200)
    assert following.json()["episode_title"] == "PUBLIC_EPISODE_TITLE"
    assert following.json()["episode_subtitle"] == "PUBLIC_SUBTITLE"
    if published == "work":
        assert following.json()["work_title"] == "PUBLIC_WORK_TITLE"


async def test_late_purchase_cannot_authorize_old_private_snapshot(
    async_client, db_session, session_factory, user, after_bootstrap_read
):
    work = await make_work(db_session, user, is_published=False)
    current = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    login(async_client, user)

    async def purchase_after_read():
        async with session_factory() as editor:
            await make_purchase(editor, user, current, environment=settings.payment_environment)

    after_bootstrap_read(purchase_after_read)
    response = await async_client.get(url(work, current))
    assert_no_store(response, 404)
    assert set(response.json()) == {"detail"}
    following = await async_client.get(url(work, current))
    assert_no_store(following, 200)
    assert following.json()["episode_title"] == current.title
