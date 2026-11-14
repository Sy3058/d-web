import uuid
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from src.config import settings
from src.lib.payment_receipt import safe_receipt_url
from src.models.payment import PurchaseStatus
from src.models.user import User
from src.services import r2_service
from tests import factories
from tests.factories import PAYWALL, doc, make_episode, make_purchase, make_work, para
from tests.test_payment_entrypoints import login, no_store

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setattr(settings, "payment_environment", "test")


@pytest.mark.parametrize("page", ["0", "-1", "2147483648", "abc"])
async def test_auth_validation(async_client, user, page):
    no_store(await async_client.get("/my/purchases"), 401)
    login(async_client, user.id)
    no_store(await async_client.get("/my/purchases", params={"page": page}), 422)


@pytest.mark.parametrize("hidden", ["work", "episode", "both"])
async def test_snapshot_private_link_read_only(
    async_client, db_session, user, monkeypatch, test_engine, hidden
):
    work = await make_work(db_session, user, is_published=hidden == "episode")
    ep = await make_episode(
        db_session,
        work,
        title="구매 당시",
        is_published=hidden == "work",
        content=doc(PAYWALL, para("비밀")),
    )
    purchase, order = await make_purchase(db_session, user, ep)
    ep.title = "변경 제목"
    ep.price = 900
    order.receipt_url = "https://receipt.example/123"
    db_session.add_all([ep, order])
    await db_session.commit()
    login(async_client, user.id)
    presign = Mock(side_effect=AssertionError("history must not presign"))
    monkeypatch.setattr(r2_service, "presign_get_urls", presign)
    selects = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await async_client.get("/my/purchases")
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", capture)
    no_store(response, 200)
    # 인증은 identity map에 따라 SELECT를 생략할 수 있다. 내역 조회 두 건만 센다.
    assert len([statement for statement in selects if "FROM purchases" in statement]) == 2
    presign.assert_not_called()
    item = response.json()["items"][0]
    assert set(item) == {
        "id",
        "payment_id",
        "item_title",
        "work_title",
        "thumbnail_url",
        "order_name",
        "amount",
        "currency",
        "paid_at",
        "status",
        "first_viewed_at",
        "refunded_at",
        "refund_amount",
        "receipt_url",
        "viewer_path",
    }
    assert item["item_title"] == "구매 당시"
    assert item["work_title"] == work.title
    assert item["amount"] == 500
    assert item["viewer_path"] == f"/works/{work.id}/{ep.public_id}"
    assert item["receipt_url"] == order.receipt_url
    await db_session.refresh(purchase)
    assert purchase.first_viewed_at is None


@pytest.mark.parametrize(
    "case",
    [
        "refund_pending",
        "refunded",
        "review_required",
        "malformed",
        "episode_deleted",
        "work_deleted",
    ],
)
async def test_retained_unavailable(async_client, db_session, user, case):
    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work, content=doc(PAYWALL, para("본문")))
    status = (
        PurchaseStatus(case) if case in {s.value for s in PurchaseStatus} else PurchaseStatus.ACTIVE
    )
    purchase, _ = await make_purchase(db_session, user, ep, status=status)
    if case == "malformed":
        ep.content = {"type": "doc", "content": [{"type": "unknown"}]}
    elif case == "episode_deleted":
        ep.deleted_at = datetime.now(UTC)
    elif case == "work_deleted":
        work.deleted_at = datetime.now(UTC)
    elif case == "refunded":
        purchase.refunded_at = datetime.now(UTC)
        purchase.refund_amount = 500
    db_session.add_all([ep, work, purchase])
    await db_session.commit()
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["viewer_path"] is None
    assert response.json()["items"][0]["status"] == status
    assert response.json()["items"][0]["refund_amount"] == purchase.refund_amount


@pytest.mark.parametrize("asset", ["thumbnail", "cover", "none"])
async def test_private_purchase_public_thumbnail(
    async_client, db_session, user, monkeypatch, asset
):
    monkeypatch.setattr(settings, "public_asset_base_url", "https://assets.example")
    work_updated = datetime(2026, 8, 1, tzinfo=UTC)
    episode_updated = datetime(2026, 8, 2, tzinfo=UTC)
    cover = "works/private/cover.webp" if asset != "none" else None
    original = "private/manuscript-page.webp"
    work = await make_work(
        db_session,
        user,
        title="비공개 구매 작품",
        is_published=False,
        cover_image=cover,
        updated_at=work_updated,
    )
    ep = await make_episode(
        db_session,
        work,
        is_published=False,
        thumbnail=original if asset == "thumbnail" else None,
        image_keys=[original],
        content=doc(PAYWALL, para("비공개 본문")),
        updated_at=episode_updated,
    )
    await make_purchase(db_session, user, ep)
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    item = response.json()["items"][0]
    assert item["work_title"] == "비공개 구매 작품"
    expected_key = r2_service.episode_thumb_key(work.id, ep.id) if asset == "thumbnail" else cover
    version = episode_updated if asset == "thumbnail" else work_updated
    assert item["thumbnail_url"] == r2_service.public_url(expected_key, version=version)
    assert original not in response.text


@pytest.mark.parametrize("deleted", ["episode", "work"])
async def test_deleted_purchase_has_no_thumbnail(
    async_client, db_session, user, monkeypatch, deleted
):
    monkeypatch.setattr(settings, "public_asset_base_url", "https://assets.example")
    work = await make_work(db_session, user, cover_image="works/cover.webp")
    ep = await make_episode(db_session, work, thumbnail="private/original.webp")
    await make_purchase(db_session, user, ep)
    target = ep if deleted == "episode" else work
    target.deleted_at = datetime.now(UTC)
    db_session.add(target)
    await db_session.commit()
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    item = response.json()["items"][0]
    assert item["thumbnail_url"] is None
    assert item["viewer_path"] is None


async def test_pagination_environment(async_client, db_session, user, monkeypatch):
    work = await make_work(db_session, user)
    now = datetime.now(UTC)
    monkeypatch.setattr(factories, "datetime", Mock(now=lambda tz: now))
    ids = []
    for number in [7, 2, 19, 1, 21, 3, 20, 4, 18, 5, 17, 6, 16, 8, 15, 9, 14, 10, 13, 11, 12]:
        ep = await make_episode(db_session, work)
        purchase, _ = await make_purchase(db_session, user, ep)
        purchase.id = uuid.UUID(int=number)
        db_session.add(purchase)
        await db_session.commit()
        ids.append(str(purchase.id))
    ep = await make_episode(db_session, work)
    await make_purchase(db_session, user, ep, environment="live")
    other = User(email="other-history@example.com", nickname="other")
    db_session.add(other)
    await db_session.commit()
    await make_purchase(db_session, other, ep)
    login(async_client, user.id)
    for page in [1, 2, 3]:
        response = await async_client.get("/my/purchases", params={"page": page})
        no_store(response, 200)
        body = response.json()
        assert body["total"] == 21
        assert body["page_size"] == 20
        assert [item["id"] for item in body["items"]] == sorted(ids, reverse=True)[
            (page - 1) * 20 : page * 20
        ]


@pytest.mark.parametrize(
    "url",
    [
        "http://receipt.example",
        "https://u:p@receipt.example",
        "https://receipt.example:bad",
        "https://receipt.example:",
        "https://[::1]garbage/a",
        "https://receipt.example:99999",
        "https://bad_host/a",
        "https://receipt.example/\nsecret",
        " https://receipt.example",
        "https://",
        "javascript:alert(1)",
        "https://receipt.example/" + "x" * 2048,
    ],
)
async def test_unsafe_receipts(url):
    assert safe_receipt_url(url) is None


@pytest.mark.parametrize(
    "url",
    ["https://receipt.example/a?token=x", "https://receipt.example:443/a", "https://[::1]/receipt"],
)
async def test_safe_receipts(url):
    assert safe_receipt_url(url) == url


async def test_database_failure_no_store(async_client, user, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from src.routers import purchases

    async def fail(*args):
        raise SQLAlchemyError("private connection detail")

    monkeypatch.setattr(purchases, "get_purchase_history", fail)
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 503)
    assert "private connection detail" not in response.text


@pytest.mark.parametrize("receipt", [None, "http://unsafe.example", "https://u:p@receipt.example"])
async def test_receipt_projection_and_viewed_preserved(async_client, db_session, user, receipt):
    from sqlalchemy import update

    from src.models.payment import PaymentOrder

    work = await make_work(db_session, user)
    ep = await make_episode(db_session, work, content=doc(PAYWALL, para("본문")))
    purchase, order = await make_purchase(db_session, user, ep)
    viewed = datetime.now(UTC)
    purchase.first_viewed_at = viewed
    db_session.add(purchase)
    await db_session.commit()
    # Bulk update deliberately leaves the identity map stale.
    await db_session.exec(
        update(PaymentOrder)
        .where(PaymentOrder.id == order.id)
        .values(item_title="서버 최신 스냅샷", receipt_url=receipt)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert order.item_title != "서버 최신 스냅샷"
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    item = response.json()["items"][0]
    assert item["item_title"] == "서버 최신 스냅샷"
    assert item["receipt_url"] is None
    assert item["first_viewed_at"] == viewed.isoformat().replace("+00:00", "Z")
    await db_session.refresh(purchase)
    assert purchase.first_viewed_at == viewed
    await db_session.refresh(order)
    assert order.receipt_url == receipt
