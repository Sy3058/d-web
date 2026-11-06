import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from src.lib.exceptions import EpisodeConflictError, WorkConflictError
from src.models.payment import PaymentOrder, Purchase
from src.models.work import Episode, Work
from src.schemas.work import EpisodeUpdate, WorkUpdate
from src.services import episode_service, work_service
from tests.factories import doc, make_episode, make_work, para

pytestmark = pytest.mark.asyncio


async def setup_order(db_session, user, *, purchase_status=None):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(para("내용")))
    now = datetime.now(UTC)
    order = PaymentOrder(
        id=uuid.uuid4(),
        payment_id=f"pay_{uuid.uuid4().hex}",
        user_id=user.id,
        episode_id=episode.id,
        kind="episode_purchase",
        expected_amount=500,
        store_id="store",
        requested_channel_key="channel",
        environment="test",
        order_name="구매",
        item_title="회차",
        status="paid" if purchase_status else "ready",
        expires_at=now + timedelta(minutes=30),
        paid_at=now if purchase_status else None,
        checkout_notice_version="v1",
        immediate_supply_consented_at=now,
    )
    db_session.add(order)
    await db_session.flush()
    if purchase_status:
        db_session.add(
            Purchase(
                payment_order_id=order.id,
                user_id=user.id,
                episode_id=episode.id,
                environment="test",
                status=purchase_status,
                amount=500,
                paid_at=now,
            )
        )
    await db_session.commit()
    return work, episode, order


@pytest.mark.parametrize("target", ["work", "episode"])
@pytest.mark.parametrize("status", ["active", "refund_pending", "review_required"])
async def test_delete_blocks_remaining_entitlement(db_session, user, target, status):
    work, episode, order = await setup_order(db_session, user, purchase_status=status)
    work_id, episode_id = work.id, episode.id
    with pytest.raises(WorkConflictError if target == "work" else EpisodeConflictError):
        if target == "work":
            await work_service.soft_delete_work(work, db_session)
        else:
            await episode_service.soft_delete_episode(episode, db_session)
    await db_session.rollback()
    assert (await db_session.get(Work, work_id)).deleted_at is None
    assert (await db_session.get(Episode, episode_id)).deleted_at is None


@pytest.mark.parametrize("target", ["work", "episode"])
async def test_unpublish_expires_open_order_preserves_purchase(db_session, user, target):
    work, episode, order = await setup_order(db_session, user)
    if target == "work":
        await work_service.update_work(work, WorkUpdate(is_published=False), db_session)
    else:
        await episode_service.update_episode(episode, EpisodeUpdate(is_published=False), db_session)
    await db_session.refresh(order)
    assert order.status == "expired"
    assert order.next_reconcile_at is not None


@pytest.mark.parametrize("target", ["work", "episode"])
async def test_delete_after_refunded_allowed(db_session, user, target):
    work, episode, order = await setup_order(db_session, user, purchase_status="refunded")
    if target == "work":
        await work_service.soft_delete_work(work, db_session)
        await db_session.refresh(work)
        assert work.deleted_at is not None
    else:
        await episode_service.soft_delete_episode(episode, db_session)
        await db_session.refresh(episode)
        assert episode.deleted_at is not None


async def test_delete_waits_for_purchase_commit(session_factory, db_session, user):
    work, episode, order = await setup_order(db_session, user)
    work_id, episode_id, order_id, user_id = work.id, episode.id, order.id, user.id
    started = asyncio.Event()
    async with session_factory() as buyer:
        await buyer.exec(select(Work).where(Work.id == work_id).with_for_update())
        await buyer.exec(select(Episode).where(Episode.id == episode_id).with_for_update())
        current = await buyer.get(PaymentOrder, order_id, with_for_update=True)
        current.status = "paid"
        current.paid_at = datetime.now(UTC)
        buyer.add(current)
        await buyer.flush()
        buyer.add(
            Purchase(
                payment_order_id=order_id,
                user_id=user_id,
                episode_id=episode_id,
                environment="test",
                status="active",
                amount=500,
                paid_at=current.paid_at,
            )
        )

        async def delete():
            async with session_factory() as deleter:
                stale = await deleter.get(Episode, episode_id)
                started.set()
                with pytest.raises(EpisodeConflictError):
                    await episode_service.soft_delete_episode(stale, deleter)

        task = asyncio.create_task(delete())
        await started.wait()
        await buyer.commit()
        await asyncio.wait_for(task, 5)
    async with session_factory() as check:
        assert (await check.get(Episode, episode_id)).deleted_at is None
        assert len((await check.exec(select(Purchase))).all()) == 1


@pytest.mark.parametrize("target", ["work", "episode"])
async def test_unpublish_keeps_active_entitlement(db_session, user, target):
    work, episode, order = await setup_order(db_session, user, purchase_status="active")
    if target == "work":
        await work_service.update_work(work, WorkUpdate(is_published=False), db_session)
    else:
        await episode_service.update_episode(episode, EpisodeUpdate(is_published=False), db_session)
    purchase = (await db_session.exec(select(Purchase))).one()
    await db_session.refresh(order)
    assert purchase.status == "active"
    assert order.status == "paid"
