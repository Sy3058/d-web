import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlmodel import select

from src.models.payment import PaymentLog, PaymentOrder, PaymentWebhookReceipt, Purchase
from src.services.payment_sync_service import PaymentSyncUnavailable, sync_payment
from src.services.payment_webhook_service import (
    _claim_receipt,
    ingest_webhook,
    process_webhook_receipts,
)
from src.services.portone_rest import PortOnePaymentSnapshot, PortOneTransportError
from src.services.portone_webhook import VerifiedPortOneWebhook
from tests.factories import PAYWALL, doc, make_episode, make_work, para

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 11, 7, tzinfo=UTC)


@pytest_asyncio.fixture
async def order(db_session, user):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session, work, is_free=False, content=doc(PAYWALL, para("유료")), price=500
    )
    row = PaymentOrder(
        id=uuid.uuid4(),
        payment_id="webhook-payment",
        user_id=user.id,
        kind="episode_purchase",
        episode_id=episode.id,
        expected_amount=500,
        store_id="store",
        requested_channel_key="card-channel",
        requested_payment_method="PaymentMethodCard",
        environment="test",
        order_name="회차",
        item_title="회차",
        status="ready",
        checkout_notice_version="episode-immediate-v1",
        immediate_supply_consented_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    db_session.add(row)
    await db_session.commit()
    return row


def webhook(webhook_id="webhook-1", event_type="Transaction.Paid", payment_id="webhook-payment"):
    return VerifiedPortOneWebhook(webhook_id, event_type, payment_id)


def adapter(**changes):
    snapshot = PortOnePaymentSnapshot.from_payload(
        {
            "id": "webhook-payment",
            "storeId": "store",
            "status": "PAID",
            "currency": "KRW",
            "amount": {"total": 500},
            "channel": {"type": "TEST", "key": "card-channel"},
            "method": {"type": "PaymentMethodCard"},
            "paidAt": NOW.isoformat(),
            **changes,
        }
    )
    return AsyncMock(
        get_payment=AsyncMock(return_value=snapshot),
        cancel_payment=AsyncMock(side_effect=PortOneTransportError("timeout")),
    )


async def rows(factory, model):
    async with factory() as session:
        return (await session.exec(select(model))).all()


async def test_concurrent_duplicate_preserves_original_receipt(db_session, session_factory):
    await asyncio.gather(*[ingest_webhook(session_factory, webhook(), now=NOW) for _ in range(4)])
    await ingest_webhook(
        session_factory, webhook(event_type="Unrecognized", payment_id="different"), now=NOW
    )
    receipts = await rows(session_factory, PaymentWebhookReceipt)
    assert len(receipts) == 1
    assert receipts[0].payment_id == "webhook-payment"
    assert receipts[0].event_type == "Transaction.Paid"
    assert receipts[0].processed_at is None and receipts[0].ignored_at is None


@pytest.mark.parametrize(
    "event_type,payment_id,ignored",
    [
        ("Transaction.Paid", None, True),
        ("Transaction.Other", "payment", True),
        ("Transaction.PartialCancelled", "payment", False),
        ("Transaction.DisputeCreated", "payment", False),
        ("Transaction.DisputeResolved", "payment", False),
    ],
)
async def test_unknown_events_ignored_after_ingest(
    db_session, session_factory, event_type, payment_id, ignored
):
    await ingest_webhook(
        session_factory, webhook(event_type=event_type, payment_id=payment_id), now=NOW
    )
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert (receipt.ignored_at == NOW) == ignored


async def test_ingest_commit_failure_is_not_acknowledged(db_session, session_factory):
    def reject(session):
        raise SQLAlchemyError("injected commit failure")

    event.listen(Session, "before_commit", reject)
    try:
        with pytest.raises(SQLAlchemyError):
            await ingest_webhook(session_factory, webhook(), now=NOW)
    finally:
        event.remove(Session, "before_commit", reject)
    assert await rows(session_factory, PaymentWebhookReceipt) == []


async def test_worker_atomic_success_and_no_connection_during_provider(
    order, session_factory, test_engine
):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()
    owners = {}

    def checkout(connection, record, proxy):
        owners[id(record)] = asyncio.current_task()

    def checkin(connection, record):
        owners.pop(id(record), None)

    async def verify_no_connection(*args, **kwargs):
        assert asyncio.current_task() not in owners.values()
        return adapter().get_payment.return_value

    provider.get_payment.side_effect = verify_no_connection
    event.listen(test_engine.sync_engine, "checkout", checkout)
    event.listen(test_engine.sync_engine, "checkin", checkin)
    try:
        assert await process_webhook_receipts(session_factory, provider, now=NOW) == 1
    finally:
        event.remove(test_engine.sync_engine, "checkout", checkout)
        event.remove(test_engine.sync_engine, "checkin", checkin)
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at == NOW and receipt.attempts == 1
    assert (await rows(session_factory, PaymentOrder))[0].status == "paid"
    assert len(await rows(session_factory, Purchase)) == 1
    log = (await rows(session_factory, PaymentLog))[0]
    assert log.webhook_receipt_id == receipt.id and log.source == "webhook"
    assert await process_webhook_receipts(session_factory, provider, now=NOW) == 0


@pytest.mark.parametrize(
    "changes,status",
    [({"currency": "USD"}, "review_required"), ({"amount": {"total": 700}}, "cancel_pending")],
)
async def test_successful_lookup_finishes_receipt_even_when_quarantined_or_compensating(
    order, session_factory, changes, status
):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    assert await process_webhook_receipts(session_factory, adapter(**changes), now=NOW) == 1
    assert (await rows(session_factory, PaymentWebhookReceipt))[0].processed_at == NOW
    assert (await rows(session_factory, PaymentOrder))[0].status == status
    assert await rows(session_factory, Purchase) == []


async def test_transaction_failure_rolls_back_receipt_order_purchase_and_log(
    order, session_factory, caplog
):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    observed_completion = []

    def reject(session):
        if any(isinstance(row, PaymentLog) for row in session.new):
            observed_completion.extend(
                row.processed_at for row in session.dirty if isinstance(row, PaymentWebhookReceipt)
            )
            raise SQLAlchemyError("sensitive raw provider body")

    event.listen(Session, "before_commit", reject)
    try:
        assert await process_webhook_receipts(session_factory, adapter(), now=NOW) == 1
    finally:
        event.remove(Session, "before_commit", reject)
    assert observed_completion == [NOW]
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at is None and receipt.attempts == 1
    assert receipt.next_attempt_at == NOW + timedelta(seconds=30)
    assert (await rows(session_factory, PaymentOrder))[0].status == "ready"
    assert await rows(session_factory, Purchase) == []
    assert await rows(session_factory, PaymentLog) == []
    assert "sensitive raw provider body" not in caplog.text


@pytest.mark.parametrize("result", [None, PortOneTransportError("provider error")])
async def test_unavailable_receipt_waits_then_retries(order, session_factory, result):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()
    if isinstance(result, Exception):
        provider.get_payment.side_effect = result
    else:
        provider.get_payment.return_value = result
    assert await process_webhook_receipts(session_factory, provider, now=NOW) == 1
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at is None
    assert await process_webhook_receipts(session_factory, provider, now=NOW) == 0
    assert (
        await process_webhook_receipts(session_factory, provider, now=NOW + timedelta(seconds=30))
        == 1
    )
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.attempts == 2
    assert receipt.next_attempt_at == NOW + timedelta(seconds=90)


async def test_unknown_local_payment_never_calls_provider(db_session, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()
    assert await process_webhook_receipts(session_factory, provider, now=NOW) == 1
    provider.get_payment.assert_not_awaited()
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at is None and receipt.next_attempt_at > NOW


async def test_concurrent_workers_claim_once(order, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()
    results = await asyncio.gather(
        *[process_webhook_receipts(session_factory, provider, now=NOW) for _ in range(3)]
    )
    assert sum(results) == 1
    assert provider.get_payment.await_count == 1
    assert len(await rows(session_factory, Purchase)) == 1


async def test_claim_skips_receipt_locked_by_another_session(db_session, session_factory):
    await ingest_webhook(session_factory, webhook("locked"), now=NOW)
    await ingest_webhook(session_factory, webhook("available"), now=NOW + timedelta(seconds=1))
    async with session_factory() as locker, locker.begin():
        locked = (
            await locker.exec(
                select(PaymentWebhookReceipt)
                .where(PaymentWebhookReceipt.webhook_id == "locked")
                .with_for_update()
            )
        ).one()
        claimed = await asyncio.wait_for(_claim_receipt(session_factory, NOW), timeout=1)
        assert claimed.webhook_id == "available"
        assert claimed.id != locked.id


async def test_expired_claim_generation_cannot_commit(order, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    first = await _claim_receipt(session_factory, NOW)
    entered, release = asyncio.Event(), asyncio.Event()
    provider = adapter()

    async def hold(*args, **kwargs):
        entered.set()
        await release.wait()
        return adapter().get_payment.return_value

    provider.get_payment.side_effect = hold
    task = asyncio.create_task(
        sync_payment(
            session_factory,
            provider,
            order.payment_id,
            "webhook",
            now=NOW,
            receipt_id=first.id,
            receipt_attempt=first.attempts,
        )
    )
    await entered.wait()
    second = await _claim_receipt(session_factory, NOW + timedelta(seconds=30))
    release.set()
    assert await task == "stale"
    assert second.attempts == 2
    assert (await rows(session_factory, PaymentWebhookReceipt))[0].processed_at is None
    assert await rows(session_factory, Purchase) == []
    assert await rows(session_factory, PaymentLog) == []
    assert (
        await sync_payment(
            session_factory,
            adapter(),
            order.payment_id,
            "webhook",
            now=NOW,
            receipt_id=second.id,
            receipt_attempt=second.attempts,
        )
        == "paid"
    )


async def test_order_changed_during_lookup_leaves_receipt_pending(order, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    claim = await _claim_receipt(session_factory, NOW)
    provider = adapter()

    async def change_order(*args, **kwargs):
        async with session_factory() as session, session.begin():
            current = await session.get(PaymentOrder, order.id)
            current.status = "review_required"
            session.add(current)
        return adapter().get_payment.return_value

    provider.get_payment.side_effect = change_order
    assert (
        await sync_payment(
            session_factory,
            provider,
            order.payment_id,
            "webhook",
            now=NOW,
            receipt_id=claim.id,
            receipt_attempt=claim.attempts,
        )
        == "stale"
    )
    assert (await rows(session_factory, PaymentWebhookReceipt))[0].processed_at is None
    assert await rows(session_factory, Purchase) == []
    assert await rows(session_factory, PaymentLog) == []


@pytest.mark.parametrize("field", ["payment", "ignored", "processed", "missing"])
async def test_receipt_must_match_pending_payment(order, session_factory, field):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    claim = await _claim_receipt(session_factory, NOW)
    async with session_factory() as session, session.begin():
        receipt = await session.get(PaymentWebhookReceipt, claim.id)
        if field == "payment":
            receipt.payment_id = "other-payment"
        elif field == "ignored":
            receipt.ignored_at = NOW
        elif field == "processed":
            receipt.processed_at = NOW
        else:
            await session.delete(receipt)
        if field != "missing":
            session.add(receipt)
    assert (
        await sync_payment(
            session_factory,
            adapter(),
            order.payment_id,
            "webhook",
            now=NOW,
            receipt_id=claim.id,
            receipt_attempt=claim.attempts,
        )
        == "stale"
    )
    assert await rows(session_factory, Purchase) == []
    assert await rows(session_factory, PaymentLog) == []


async def test_receipt_requires_webhook_source_before_lookup(order, session_factory):
    provider = adapter()
    with pytest.raises(ValueError):
        await sync_payment(
            session_factory,
            provider,
            order.payment_id,
            "browser",
            now=NOW,
            receipt_id=uuid.uuid4(),
            receipt_attempt=1,
        )
    provider.get_payment.assert_not_awaited()


async def test_batch_bound_and_backoff_cap(db_session, session_factory):
    for index in range(3):
        await ingest_webhook(session_factory, webhook(f"event-{index}"), now=NOW)
    assert await process_webhook_receipts(session_factory, adapter(), batch_size=2, now=NOW) == 2
    assert sorted(r.attempts for r in await rows(session_factory, PaymentWebhookReceipt)) == [
        0,
        1,
        1,
    ]
    async with session_factory() as session, session.begin():
        receipts = (await session.exec(select(PaymentWebhookReceipt))).all()
        for receipt in receipts:
            receipt.attempts = 10000
            receipt.next_attempt_at = NOW
            session.add(receipt)
    claimed = await _claim_receipt(session_factory, NOW)
    assert claimed.next_attempt_at == NOW + timedelta(hours=1)


async def test_worker_wall_time_and_crash_recovery(order, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()

    async def hold(*args, **kwargs):
        await asyncio.sleep(60)

    provider.get_payment.side_effect = hold
    assert (
        await asyncio.wait_for(
            process_webhook_receipts(session_factory, provider, max_duration_seconds=0.05, now=NOW),
            timeout=2,
        )
        == 1
    )
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at is None and receipt.attempts == 1
    assert (
        await process_webhook_receipts(session_factory, adapter(), now=NOW + timedelta(seconds=30))
        == 1
    )
    assert (await rows(session_factory, PaymentWebhookReceipt))[0].processed_at is not None


async def test_external_cancellation_propagates(order, session_factory):
    await ingest_webhook(session_factory, webhook(), now=NOW)
    provider = adapter()
    provider.get_payment.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await process_webhook_receipts(session_factory, provider, now=NOW)
    assert (await rows(session_factory, PaymentWebhookReceipt))[0].processed_at is None


async def test_browser_unavailable_signal_preserves_committed_log(order, session_factory):
    provider = adapter()
    provider.get_payment.return_value = None
    with pytest.raises(PaymentSyncUnavailable):
        await sync_payment(
            session_factory,
            provider,
            order.payment_id,
            "browser",
            now=NOW,
            raise_on_unavailable=True,
        )
    assert len(await rows(session_factory, PaymentLog)) == 1
    assert (await rows(session_factory, PaymentOrder))[0].status == "ready"
