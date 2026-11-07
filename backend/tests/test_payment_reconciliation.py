import asyncio
from datetime import timedelta

import pytest

from src.models.payment import PaymentOrder
from src.services.payment_reconciliation_service import _claim_order, reconcile_payments
from tests.test_payment_sync import NOW, Adapter, read_all
from tests.test_payment_sync import cleanup_adapters as cleanup_adapters
from tests.test_payment_sync import orders as orders

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("status", "paid_age", "expected"),
    [
        ("preparing", None, 1),
        ("ready", None, 1),
        ("expired", None, 1),
        ("cancel_pending", None, 1),
        ("review_required", None, 1),
        ("paid", 192, 1),
        ("paid", 192.001, 0),
        ("paid", None, 0),
        ("cancelled", None, 0),
    ],
)
async def test_selector(orders, session_factory, test_engine, status, paid_age, expected):
    async with session_factory() as session:
        first = await session.get(PaymentOrder, orders[0].id)
        first.status = status
        if status == "cancel_pending":
            first.cancel_reason = "customer_refund"
            first.cancel_idempotency_key = "test-key-000000000000"
            first.cancel_key_issued_at = NOW
            first.provider_total_amount = 500
            first.cancel_request_snapshot = {
                "storeId": "store",
                "reason": "customer_refund",
                "amount": 500,
                "currentCancellableAmount": 500,
                "requester": "CUSTOMER",
            }
        first.paid_at = NOW - timedelta(hours=paid_age) if paid_age is not None else None
        other = await session.get(PaymentOrder, orders[1].id)
        other.next_reconcile_at = NOW + timedelta(days=1)
        await session.commit()
    adapter = Adapter(test_engine, {"status": "READY"})
    assert await reconcile_payments(session_factory, adapter, now=NOW) == expected


async def test_claim_lease_restart_backoff_and_lock(orders, session_factory):
    async with session_factory() as session:
        row = await session.get(PaymentOrder, orders[1].id)
        row.next_reconcile_at = NOW + timedelta(days=1)
        await session.commit()
    claims = await asyncio.gather(
        *[_claim_order(session_factory, NOW, expired=True, excluded=set()) for _ in range(2)]
    )
    claim = next(row for row in claims if row is not None)
    assert sum(row is not None for row in claims) == 1
    assert claim.reconcile_attempts == 1
    assert claim.next_reconcile_at == NOW + timedelta(seconds=330)
    assert await _claim_order(session_factory, NOW, expired=True, excluded=set()) is None
    recovered = await _claim_order(
        session_factory, NOW + timedelta(seconds=330), expired=True, excluded=set()
    )
    assert recovered.id == claim.id and recovered.reconcile_attempts == 2
    async with session_factory() as session:
        row = await session.get(PaymentOrder, claim.id)
        row.reconcile_attempts = 1000
        row.next_reconcile_at = NOW
        await session.commit()
    capped = await _claim_order(session_factory, NOW, expired=True, excluded=set())
    assert capped.next_reconcile_at == NOW + timedelta(hours=1)


async def test_separate_item_budgets_and_no_duplicate(orders, session_factory, test_engine):
    async with session_factory() as session:
        row = await session.get(PaymentOrder, orders[0].id)
        row.status = "ready"
        await session.commit()
    adapter = Adapter(test_engine, {"status": "READY"})
    assert await reconcile_payments(session_factory, adapter, batch_size=1, now=NOW) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert all(row.reconcile_attempts == 1 for row in rows)
    assert all(row.next_reconcile_at > NOW for row in rows)


async def test_expired_has_independent_time_budget(orders, session_factory, test_engine):
    async with session_factory() as session:
        row = await session.get(PaymentOrder, orders[0].id)
        row.status = "ready"
        await session.commit()
    adapter = Adapter(test_engine, {"status": "READY"})
    calls = []

    async def slow():
        calls.append(True)
        await asyncio.sleep(1)

    adapter.hook = slow
    assert (
        await reconcile_payments(session_factory, adapter, max_duration_seconds=0.1, now=NOW) == 2
    )
    assert len(calls) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert all(row.next_reconcile_at == NOW + timedelta(seconds=330) for row in rows)


async def test_old_store_test_order_still_reconciled(
    orders, session_factory, test_engine, monkeypatch
):
    from src.config import settings

    monkeypatch.setattr(settings, "payment_environment", "live")
    monkeypatch.setattr(settings, "portone_store_id", "new-store")
    adapter = Adapter(test_engine)
    assert await reconcile_payments(session_factory, adapter, now=NOW) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert all(row.status in {"paid", "cancel_pending"} for row in rows)


async def test_pool_batch_cap(orders, session_factory, test_engine):
    import uuid

    async with session_factory() as session:
        for index in range(101):
            data = orders[0].model_dump(warnings=False)
            data.update(id=uuid.uuid4(), payment_id=f"cap-{index}", status="review_required")
            session.add(PaymentOrder.model_validate(data))
        await session.commit()
    adapter = Adapter(test_engine, {"status": "READY"})
    # The nonexpired pool stops at 100 while the two expired rows retain their budget.
    assert await reconcile_payments(session_factory, adapter, batch_size=1000, now=NOW) == 102
    rows = await read_all(session_factory, PaymentOrder)
    assert sum(row.reconcile_attempts == 0 for row in rows) == 1


async def test_stale_claim_cannot_commit_provider_result(orders, session_factory, test_engine):
    from src.models.payment import PaymentLog
    from src.services.payment_sync_service import sync_payment

    claim = await _claim_order(session_factory, NOW, expired=True, excluded=set())
    adapter = Adapter(test_engine)

    async def newer_claim():
        async with session_factory() as session:
            row = await session.get(PaymentOrder, claim.id)
            row.reconcile_attempts += 1
            await session.commit()

    adapter.hook = newer_claim
    assert (
        await sync_payment(
            session_factory,
            adapter,
            claim.payment_id,
            "reconcile",
            reconcile_attempt=claim.reconcile_attempts,
            now=NOW,
        )
        == "stale"
    )
    assert await read_all(session_factory, PaymentLog) == []


@pytest.mark.parametrize("initial_state", [None, "FAILED"])
async def test_expired_unresolved_later_paid(orders, session_factory, test_engine, initial_state):
    adapter = Adapter(test_engine, {"status": initial_state})
    if initial_state is None:

        async def missing(payment_id, *, store_id):
            return None

        adapter.get_payment = missing
    assert await reconcile_payments(session_factory, adapter, now=NOW) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert all(row.status == "expired" and row.next_reconcile_at > NOW for row in rows)
    paid = Adapter(test_engine)
    assert await reconcile_payments(session_factory, paid, now=NOW + timedelta(hours=1)) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert {row.status for row in rows} == {"paid", "cancel_pending"}


async def test_worker_exception_is_sanitized(orders, session_factory, test_engine, caplog):
    adapter = Adapter(test_engine)

    async def broken():
        raise RuntimeError("private-provider-response")

    adapter.hook = broken
    assert await reconcile_payments(session_factory, adapter, now=NOW) == 2
    assert "payment_reconciliation_failed" in caplog.text
    assert "private-provider-response" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    rows = await read_all(session_factory, PaymentOrder)
    assert all(row.next_reconcile_at == NOW + timedelta(seconds=330) for row in rows)


async def test_late_paid_duplicate_compensation_converges_after_restart(
    orders, session_factory, test_engine
):
    from src.models.payment import Purchase

    first = Adapter(test_engine)
    assert await reconcile_payments(session_factory, first, now=NOW) == 2
    rows = await read_all(session_factory, PaymentOrder)
    pending = next(row for row in rows if row.status == "cancel_pending")
    winner = next(row for row in rows if row.status == "paid")
    assert len(first.posts) == 1
    assert first.posts[0]["payment_id"] == pending.payment_id
    key = first.posts[0]["idempotency_key"]

    class ResolvedAdapter(Adapter):
        async def get_payment(self, payment_id, *, store_id):
            from tests.test_payment_sync import snapshot

            assert asyncio.current_task() not in self.owners.values()
            return snapshot(
                payment_id, status="CANCELLED" if payment_id == pending.payment_id else "PAID"
            )

    # 새 worker 인스턴스는 DB 예약과 기존 보상만 이어받는다.
    restarted = ResolvedAdapter(test_engine)
    assert await reconcile_payments(session_factory, restarted, now=NOW + timedelta(hours=1)) == 2
    rows = await read_all(session_factory, PaymentOrder)
    assert next(row for row in rows if row.id == pending.id).status == "cancelled"
    assert next(row for row in rows if row.id == pending.id).cancel_idempotency_key == key
    assert next(row for row in rows if row.id == winner.id).status == "paid"
    purchases = await read_all(session_factory, Purchase)
    assert len(purchases) == 1 and purchases[0].status == "active"
    assert restarted.posts == []


async def test_restarted_worker_preserves_token_until_full_cancellation(
    orders, session_factory, test_engine
):
    import uuid

    from src.models.payment import PaymentCancelReason
    from src.services.payment_cancellation_service import prepare_system_cancellation
    from tests.test_payment_sync import snapshot

    token = uuid.uuid4()
    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session,
            orders[0].id,
            PaymentCancelReason.SYSTEM_DUPLICATE,
            snapshot(orders[0].payment_id),
            NOW - timedelta(days=1),
        )
        row = await session.get(PaymentOrder, orders[0].id, populate_existing=True)
        row.cancel_dispatch_token = token
        row.cancel_dispatch_started_at = NOW - timedelta(days=1)
        session.add(row)
        other = await session.get(PaymentOrder, orders[1].id)
        other.next_reconcile_at = NOW + timedelta(days=1)
        session.add(other)
    assert await reconcile_payments(session_factory, Adapter(test_engine), now=NOW) == 1
    row = next(
        row for row in await read_all(session_factory, PaymentOrder) if row.id == orders[0].id
    )
    assert row.status == "cancel_pending" and row.cancel_dispatch_token == token
    confirming = Adapter(test_engine, {"status": "CANCELLED"})
    assert await reconcile_payments(session_factory, confirming, now=NOW + timedelta(hours=1)) == 1
    row = next(
        row for row in await read_all(session_factory, PaymentOrder) if row.id == orders[0].id
    )
    assert row.status == "cancelled" and row.cancel_dispatch_token is None
    assert confirming.posts == []
