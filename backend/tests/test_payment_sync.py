import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.config import settings
from src.models.payment import PaymentLog, PaymentOrder, Purchase
from src.models.work import Episode
from src.services.payment_sync_service import sync_payment
from src.services.portone_rest import PortOnePaymentSnapshot, PortOneTransportError
from tests.factories import PAYWALL, doc, make_episode, make_purchase, make_work, para

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 11, 7, tzinfo=UTC)
_ADAPTERS = []


@pytest.fixture(autouse=True)
def cleanup_adapters():
    yield
    for adapter, engine in _ADAPTERS:
        event.remove(engine.sync_engine, "checkout", adapter.checkout)
        event.remove(engine.sync_engine, "checkin", adapter.checkin)
    _ADAPTERS.clear()


@pytest_asyncio.fixture
async def orders(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "portone_channel_key_card", "card-channel")
    work = await make_work(db_session, user)
    ep = await make_episode(
        db_session, work, is_free=False, content=doc(PAYWALL, para("유료 본문")), price=500
    )
    rows = []
    for index in range(2):
        row = PaymentOrder(
            id=uuid.uuid4(),
            payment_id=f"sync-{index}",
            user_id=user.id,
            kind="episode_purchase",
            episode_id=ep.id,
            expected_amount=500,
            store_id="store",
            requested_channel_key="card-channel",
            requested_payment_method="PaymentMethodCard",
            environment="test",
            order_name="회차",
            item_title="회차",
            status="expired",
            checkout_notice_version="episode-immediate-v1",
            immediate_supply_consented_at=NOW,
            expires_at=NOW - timedelta(minutes=1),
        )
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    return rows


def snapshot(payment_id, **changes):
    return PortOnePaymentSnapshot.from_payload(
        {
            "id": payment_id,
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


class Adapter:
    def __init__(self, engine, changes=None):
        _ADAPTERS.append((self, engine))
        self.changes = changes or {}
        self.hook = None
        self.posts = []
        self.owners = {}
        event.listen(engine.sync_engine, "checkout", self.checkout)
        event.listen(engine.sync_engine, "checkin", self.checkin)

    def checkout(self, connection, record, proxy):
        self.owners[id(record)] = asyncio.current_task()

    def checkin(self, connection, record):
        self.owners.pop(id(record), None)

    async def get_payment(self, payment_id, *, store_id):
        assert asyncio.current_task() not in self.owners.values()
        if self.hook:
            await self.hook()
        return snapshot(payment_id, **self.changes)

    async def cancel_payment(self, **kwargs):
        assert asyncio.current_task() not in self.owners.values()
        self.posts.append(kwargs)
        raise PortOneTransportError("timeout")


async def read_all(factory, model):
    async with factory() as session:
        return (await session.exec(select(model))).all()


async def test_four_sources_one_purchase(orders, session_factory, test_engine):
    adapter = Adapter(test_engine)
    barrier = asyncio.Barrier(4)
    adapter.hook = barrier.wait
    results = await asyncio.gather(
        *[
            sync_payment(session_factory, adapter, orders[0].payment_id, source, now=NOW)
            for source in ("browser", "webhook", "reconcile", "admin")
        ]
    )
    assert "paid" in results
    purchases = await read_all(session_factory, Purchase)
    assert len(purchases) == 1 and purchases[0].status == "active"
    assert len(await read_all(session_factory, PaymentLog)) == 1
    assert adapter.posts == []


async def test_two_approvals_one_purchase_one_compensation(orders, session_factory, test_engine):
    adapter = Adapter(test_engine)
    await asyncio.gather(
        *[
            sync_payment(session_factory, adapter, row.payment_id, "browser", now=NOW)
            for row in orders
        ]
    )
    assert len(await read_all(session_factory, Purchase)) == 1
    rows = await read_all(session_factory, PaymentOrder)
    assert sorted(row.status for row in rows) == ["cancel_pending", "paid"]
    assert len(adapter.posts) == 1
    loser = next(row for row in rows if row.status == "cancel_pending")
    assert loser.cancel_reason == "system_duplicate"
    assert loser.cancel_request_snapshot["amount"] == 500


@pytest.mark.parametrize("status", ["active", "refund_pending", "review_required", "refunded"])
@pytest.mark.parametrize("environment", ["test", "live"])
async def test_existing_purchase_duplicate_compensation_respects_status_and_environment(
    orders, db_session, user, session_factory, test_engine, status, environment
):
    episode = await db_session.get(Episode, orders[0].episode_id)
    existing, _ = await make_purchase(
        db_session, user, episode, status=status, environment=environment
    )
    existing_id = existing.id
    adapter = Adapter(test_engine)
    result = await sync_payment(session_factory, adapter, orders[0].payment_id, "browser", now=NOW)
    protected = environment == "test" and status != "refunded"
    assert result == ("cancel_pending" if protected else "paid")
    purchases = await read_all(session_factory, Purchase)
    original = next(row for row in purchases if row.id == existing_id)
    assert original.status == status
    new_purchases = [row for row in purchases if row.payment_order_id == orders[0].id]
    if protected:
        assert new_purchases == []
        assert len(adapter.posts) == 1
        rows = await read_all(session_factory, PaymentOrder)
        order = next(row for row in rows if row.id == orders[0].id)
        assert order.cancel_reason == "system_duplicate"
    else:
        assert len(new_purchases) == 1
        assert new_purchases[0].status == "active"
        assert adapter.posts == []


@pytest.mark.parametrize(
    "changes,expected,reason",
    [
        ({"currency": "USD"}, "review_required", "unsupported_payment_currency"),
        ({"amount": {"total": 700}}, "cancel_pending", None),
        ({"channel": {"type": "LIVE", "key": "card-channel"}}, "cancel_pending", None),
        ({"method": {"type": "PaymentMethodEasyPay"}}, "cancel_pending", None),
        ({"paidAt": None}, "cancel_pending", None),
        ({"storeId": "foreign"}, "review_required", "payment_identity_mismatch"),
        ({"status": "PARTIAL_CANCELLED"}, "review_required", "unsupported_money_state"),
    ],
)
async def test_invalid_snapshot_no_entitlement(
    orders, session_factory, test_engine, changes, expected, reason
):
    adapter = Adapter(test_engine, changes)
    assert await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW) == expected
    assert await read_all(session_factory, Purchase) == []
    row = next(
        row for row in await read_all(session_factory, PaymentOrder) if row.payment_id == "sync-0"
    )
    assert row.needs_action_reason == reason
    assert row.expected_amount == 500
    if changes.get("amount"):
        assert row.provider_total_amount == 700
        assert adapter.posts[0]["request"].amount == 700


async def test_cancel_revokes_and_stale_paid_cannot_restore(orders, session_factory, test_engine):
    adapter = Adapter(test_engine)
    await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
    adapter.changes = {"status": "CANCELLED"}
    assert await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW) == "cancelled"
    adapter.changes = {}
    assert await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW) == "cancelled"
    assert (await read_all(session_factory, Purchase))[0].status == "refunded"


async def test_old_response_not_applied(orders, session_factory, test_engine):
    adapter = Adapter(test_engine)
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold():
        entered.set()
        await release.wait()

    adapter.hook = hold
    task = asyncio.create_task(sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW))
    await entered.wait()
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.status = "review_required"
        session.add(row)
    release.set()
    assert await task == "stale"
    assert await read_all(session_factory, Purchase) == []


@pytest.mark.parametrize("changes", [{}, {"currency": "USD"}])
async def test_commit_failure_rolls_back_purchase_and_order(
    orders, session_factory, test_engine, caplog, changes
):
    adapter = Adapter(test_engine, changes)

    def reject(connection, cursor, statement, params, context, many):
        if statement.startswith("INSERT INTO payment_logs"):
            raise SQLAlchemyError("injected")

    event.listen(test_engine.sync_engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(SQLAlchemyError):
            await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", reject)
    assert await read_all(session_factory, Purchase) == []
    assert all(row.status == "expired" for row in await read_all(session_factory, PaymentOrder))
    assert not [r for r in caplog.records if r.msg == "payment_sync_anomaly"]


@pytest.mark.parametrize("state", ["READY", "PENDING", "PAY_PENDING", "FAILED", None])
@pytest.mark.parametrize("local", ["ready", "expired", "paid"])
async def test_nonpaid_preserves_money_tracking(orders, session_factory, test_engine, state, local):
    adapter = Adapter(test_engine)
    if local == "paid":
        await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
    elif local == "ready":
        async with session_factory() as session, session.begin():
            row = await session.get(PaymentOrder, orders[0].id)
            row.status = "ready"
            session.add(row)
    if state is None:

        async def absent(payment_id, *, store_id):
            return None

        adapter.get_payment = absent
    else:
        adapter.changes = {"status": state}
    result = await sync_payment(session_factory, adapter, "sync-0", "reconcile", now=NOW)
    assert result == ("paid" if local == "paid" else "expired")
    row = next(
        row for row in await read_all(session_factory, PaymentOrder) if row.payment_id == "sync-0"
    )
    assert row.next_reconcile_at > NOW
    assert len(await read_all(session_factory, Purchase)) == (1 if local == "paid" else 0)


async def test_provider_failure_retries_without_expiring(orders, session_factory, test_engine):
    adapter = Adapter(test_engine)

    async def failed(payment_id, *, store_id):
        raise PortOneTransportError("failure")

    adapter.get_payment = failed
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.status = "ready"
        session.add(row)
    assert await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW) == "ready"
    assert (await read_all(session_factory, PaymentLog))[0].failure_code == "provider_unavailable"


async def test_unsupported_closes_purchase_then_cancelled_refunds(
    orders, session_factory, test_engine
):
    adapter = Adapter(test_engine)
    await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
    adapter.changes = {"status": "UNKNOWN"}
    assert (
        await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW)
        == "review_required"
    )
    assert (await read_all(session_factory, Purchase))[0].status == "review_required"
    adapter.changes = {"status": "CANCELLED"}
    assert await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW) == "cancelled"
    assert (await read_all(session_factory, Purchase))[0].status == "refunded"


@pytest.mark.parametrize("target", ["work", "episode", "deleted", "free"])
async def test_unavailable_before_paid_compensates(orders, session_factory, test_engine, target):
    from src.models.work import Episode, Work

    async with session_factory() as session, session.begin():
        ep = await session.get(Episode, orders[0].episode_id)
        if target == "work":
            work = await session.get(Work, ep.work_id)
            work.is_published = False
            session.add(work)
        elif target == "deleted":
            ep.deleted_at = NOW
        elif target == "free":
            ep.is_free = True
        else:
            ep.is_published = False
        session.add(ep)
    adapter = Adapter(test_engine)
    assert (
        await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
        == "cancel_pending"
    )
    row = next(
        row for row in await read_all(session_factory, PaymentOrder) if row.payment_id == "sync-0"
    )
    assert row.cancel_reason == "system_unavailable"
    assert await read_all(session_factory, Purchase) == []
    assert len(adapter.posts) == 1


@pytest.mark.parametrize(
    "method,provider",
    [
        ("PaymentMethodCard", None),
        ("PaymentMethodEasyPay", "KAKAOPAY"),
        ("PaymentMethodEasyPay", "TOSSPAY"),
    ],
)
async def test_channel_rotation_preserves_existing_approval(
    orders, session_factory, test_engine, monkeypatch, method, provider
):
    monkeypatch.setattr(settings, "portone_channel_key_card", "replacement-channel")
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.requested_payment_method = method
        row.requested_easy_pay_provider = provider
        session.add(row)
    adapter = Adapter(test_engine, {"method": {"type": method, "provider": provider}})
    assert await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW) == "paid"
    assert len(await read_all(session_factory, Purchase)) == 1
    assert adapter.posts == []


async def test_legacy_snapshot_is_quarantined_without_refund(orders, session_factory, test_engine):
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.requested_payment_method = None
        session.add(row)
    adapter = Adapter(test_engine)
    assert (
        await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
        == "review_required"
    )
    assert adapter.posts == []
    assert await read_all(session_factory, Purchase) == []


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"currency": "USD"}, "unsupported_payment_currency"),
        ({"status": "UNKNOWN"}, "unsupported_money_state"),
        ({"amount": {"total": 700}}, "payment_snapshot_mismatch"),
    ],
)
async def test_anomaly_logged_after_commit(
    orders, session_factory, test_engine, caplog, changes, code
):
    adapter = Adapter(test_engine, changes)
    await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
    records = [r for r in caplog.records if r.msg == "payment_sync_anomaly"]
    assert len(records) == 1
    record = records[0]
    assert record.failure_code == code
    assert record.payment_order_id == str(orders[0].id)
    assert record.from_status == "expired"
    assert record.to_status in {"review_required", "cancel_pending"}
    assert "USD" not in record.getMessage()
    if code != "payment_snapshot_mismatch":
        caplog.clear()
        await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW)
        assert not [r for r in caplog.records if r.msg == "payment_sync_anomaly"]


async def test_anomaly_reaches_sentry_without_network():
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    from src.services.payment_sync_service import _report_anomaly

    events = []

    def capture(event, hint):
        events.append(event)
        return None

    client = sentry_sdk.Client(
        dsn="https://public@example.invalid/1",
        default_integrations=False,
        integrations=[LoggingIntegration()],
        before_send=capture,
    )
    with sentry_sdk.isolation_scope() as scope:
        scope.set_client(client)
        _report_anomaly("order-id", "ready", "review_required", "unsupported_money_state")
    client.close()
    assert len(events) == 1
    assert events[0]["extra"]["failure_code"] == "unsupported_money_state"
    assert events[0]["extra"]["payment_order_id"] == "order-id"


async def test_dispatch_quarantine_is_reported(orders, session_factory, test_engine, caplog):
    adapter = Adapter(test_engine, {"amount": {"total": 700}})
    calls = 0

    async def change_after_prepare():
        nonlocal calls
        calls += 1
        if calls == 2:
            adapter.changes["status"] = "UNKNOWN"

    adapter.hook = change_after_prepare
    assert (
        await sync_payment(session_factory, adapter, "sync-0", "browser", now=NOW)
        == "review_required"
    )
    codes = [r.failure_code for r in caplog.records if r.msg == "payment_sync_anomaly"]
    assert codes == ["payment_snapshot_mismatch", "cancel_money_state_unknown"]
    assert adapter.posts == []


async def test_reconcile_claim_is_counted_once_and_fenced(orders, session_factory, test_engine):
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.reconcile_attempts = 8
        session.add(row)
    adapter = Adapter(test_engine, {"status": "FAILED"})
    assert (
        await sync_payment(
            session_factory, adapter, "sync-0", "reconcile", now=NOW, reconcile_attempt=8
        )
        == "expired"
    )
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert row.reconcile_attempts == 8
    assert row.next_reconcile_at == NOW + timedelta(hours=1)
    adapter.hook = lambda: pytest.fail("stale claim must not reach provider")
    assert (
        await sync_payment(
            session_factory, adapter, "sync-0", "reconcile", now=NOW, reconcile_attempt=7
        )
        == "stale"
    )


async def test_reconcile_new_claim_during_get_rejects_old_snapshot(
    orders, session_factory, test_engine
):
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, orders[0].id)
        row.reconcile_attempts = 1
        session.add(row)
    adapter = Adapter(test_engine)

    async def reclaim():
        async with session_factory() as session, session.begin():
            row = await session.get(PaymentOrder, orders[0].id)
            row.reconcile_attempts = 2
            session.add(row)

    adapter.hook = reclaim
    assert (
        await sync_payment(
            session_factory, adapter, "sync-0", "reconcile", now=NOW, reconcile_attempt=1
        )
        == "stale"
    )
    assert await read_all(session_factory, Purchase) == []
    assert await read_all(session_factory, PaymentLog) == []


@pytest.mark.parametrize(
    "changes,recovered",
    [
        ({"status": "CANCELLED"}, True),
        ({"status": "CANCELLED", "storeId": "wrong"}, False),
        ({"status": "CANCELLED", "currency": "USD"}, False),
        ({"status": "CANCELLED", "amount": {"total": 400}}, False),
        ({"status": "PAID"}, False),
        ({"status": "FAILED"}, False),
        ({"status": "UNKNOWN"}, False),
    ],
)
async def test_lost_dispatch_token_requires_verified_full_cancellation(
    orders, session_factory, test_engine, changes, recovered
):
    from src.models.payment import PaymentCancelReason
    from src.services.payment_cancellation_service import prepare_system_cancellation

    token = uuid.uuid4()
    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session,
            orders[0].id,
            PaymentCancelReason.SYSTEM_DUPLICATE,
            snapshot("sync-0"),
            NOW - timedelta(days=1),
        )
        row = await session.get(PaymentOrder, orders[0].id, populate_existing=True)
        row.cancel_dispatch_token = token
        row.cancel_dispatch_started_at = NOW - timedelta(days=1)
        session.add(row)
    adapter = Adapter(test_engine, changes)
    await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW)
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert (row.cancel_dispatch_token is None) == recovered
    if recovered:
        assert row.status == "cancelled" and row.next_reconcile_at is None
        assert row.cancel_dispatch_started_at is None and row.cancelled_amount == 500
    else:
        assert row.cancel_dispatch_token == token
        assert row.status in {"cancel_pending", "review_required"}
    assert adapter.posts == []
    assert await read_all(session_factory, Purchase) == []
    logs = await read_all(session_factory, PaymentLog)
    assert len([r for r in logs if r.event_type == "cancel_dispatch_recovered"]) == int(recovered)


@pytest.mark.parametrize("succeeded", [False, True])
async def test_terminal_recovery_fences_inflight_cancellation_response(
    orders, session_factory, test_engine, succeeded
):
    from src.models.payment import PaymentCancelReason
    from src.services.payment_cancellation_service import (
        dispatch_system_cancellation,
        prepare_system_cancellation,
    )
    from src.services.portone_rest import PortOneCancellationSnapshot

    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session, orders[0].id, PaymentCancelReason.SYSTEM_DUPLICATE, snapshot("sync-0"), NOW
        )
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingAdapter(Adapter):
        async def cancel_payment(self, **kwargs):
            self.posts.append(kwargs)
            entered.set()
            await release.wait()
            return PortOneCancellationSnapshot.from_payload(
                {"id": "old-cancel", "status": "FAILED", "totalAmount": 500}
            )

    posting = BlockingAdapter(test_engine)
    task = asyncio.create_task(
        dispatch_system_cancellation(session_factory, posting, orders[0].id, clock=lambda: NOW)
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        async with session_factory() as session, session.begin():
            pending = await session.get(PaymentOrder, orders[0].id)
            pending.cancellation_id = "current" if succeeded else None
            session.add(pending)
        changes = (
            {
                "status": "PAID",
                "cancellations": [{"id": "current", "status": "SUCCEEDED", "totalAmount": 500}],
            }
            if succeeded
            else {"status": "CANCELLED"}
        )
        checking = Adapter(test_engine, changes)
        assert (
            await sync_payment(session_factory, checking, "sync-0", "admin", now=NOW) == "cancelled"
        )
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=5)
    assert task.result() == "stale"
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert row.status == "cancelled" and row.cancel_dispatch_token is None
    assert row.cancellation_id == ("current" if succeeded else None)
    assert len(posting.posts) == 1 and checking.posts == []


@pytest.mark.parametrize("source", ["admin", "reconcile", "webhook", "browser"])
@pytest.mark.parametrize("lost_token", [False, True])
async def test_paid_current_full_succeeded_is_terminal(
    orders, session_factory, test_engine, source, lost_token
):
    from src.models.payment import PaymentCancelReason
    from src.services.payment_cancellation_service import prepare_system_cancellation

    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session, orders[0].id, PaymentCancelReason.SYSTEM_DUPLICATE, snapshot("sync-0"), NOW
        )
        row = await session.get(PaymentOrder, orders[0].id, populate_existing=True)
        row.cancellation_id = "current"
        if lost_token:
            row.cancel_dispatch_token = uuid.uuid4()
            row.cancel_dispatch_started_at = NOW
        key, body = row.cancel_idempotency_key, row.cancel_request_snapshot
        session.add(row)
    adapter = Adapter(
        test_engine,
        {
            "cancellations": [
                {"id": "old", "status": "FAILED", "totalAmount": 500},
                {"id": "current", "status": "SUCCEEDED", "totalAmount": 500},
            ]
        },
    )
    for when in (NOW, NOW + timedelta(hours=1)):
        assert (
            await sync_payment(session_factory, adapter, "sync-0", source, now=when) == "cancelled"
        )
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert row.cancel_dispatch_token is None and row.cancel_dispatch_started_at is None
    assert row.cancelled_amount == 500 and row.next_reconcile_at is None
    assert row.cancelled_at == NOW
    assert row.cancel_idempotency_key == key and row.cancel_request_snapshot == body
    assert row.needs_action_reason != "cancelled_payment_paid"
    assert adapter.posts == []
    logs = await read_all(session_factory, PaymentLog)
    recovered = [r for r in logs if r.event_type == "cancel_dispatch_recovered"]
    assert len(recovered) == int(lost_token)
    assert all(r.provider_status == "PAID" for r in logs)


@pytest.mark.parametrize(
    "case",
    [
        "missing_id",
        "old_id",
        "duplicate",
        "failed",
        "requested",
        "unknown",
        "missing_amount",
        "partial_amount",
        "identity",
        "currency",
        "customer",
        "review",
    ],
)
async def test_paid_cancellation_without_full_current_proof_keeps_token(
    orders, session_factory, test_engine, case
):
    from src.models.payment import PaymentCancelReason
    from src.services.payment_cancellation_service import prepare_system_cancellation

    token = uuid.uuid4()
    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session, orders[0].id, PaymentCancelReason.SYSTEM_DUPLICATE, snapshot("sync-0"), NOW
        )
        row = await session.get(PaymentOrder, orders[0].id, populate_existing=True)
        row.cancellation_id = None if case == "missing_id" else "current"
        row.cancel_dispatch_token, row.cancel_dispatch_started_at = token, NOW
        if case == "customer":
            row.cancel_reason = PaymentCancelReason.CUSTOMER_REFUND
            row.cancel_request_snapshot = {
                **row.cancel_request_snapshot,
                "reason": "customer_refund",
                "requester": "CUSTOMER",
            }
        if case == "review":
            row.status = "review_required"
        key, body = row.cancel_idempotency_key, row.cancel_request_snapshot
        session.add(row)
    cancellation = {"id": "current", "status": "SUCCEEDED", "totalAmount": 500}
    if case == "old_id":
        cancellation["id"] = "old"
    if case in {"failed", "requested", "unknown"}:
        cancellation["status"] = case.upper()
    if case == "missing_amount":
        cancellation.pop("totalAmount")
    if case == "partial_amount":
        cancellation["totalAmount"] = 400
    changes = {"cancellations": [cancellation] * (2 if case == "duplicate" else 1)}
    if case == "identity":
        changes["id"] = "wrong"
    if case == "currency":
        changes["currency"] = "USD"
    adapter = Adapter(test_engine, changes)
    await sync_payment(session_factory, adapter, "sync-0", "admin", now=NOW)
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert row.cancel_dispatch_token == token and row.status != "cancelled"
    assert row.cancel_idempotency_key == key and row.cancel_request_snapshot == body
    assert adapter.posts == []
    assert not any(
        r.event_type == "cancel_dispatch_recovered"
        for r in await read_all(session_factory, PaymentLog)
    )


async def test_payment_currency_guard_rejects_non_krw_order(orders, session_factory):
    from sqlalchemy.exc import IntegrityError

    # 비KRW 로컬 주문은 sync 입력이 될 수 없다. provider 통화 불일치는 위에서 검증한다.
    with pytest.raises(IntegrityError, match="ck_payment_orders_currency"):
        async with session_factory() as session, session.begin():
            row = await session.get(PaymentOrder, orders[0].id)
            row.currency = "USD"
            session.add(row)
            await session.flush()
    row = next(r for r in await read_all(session_factory, PaymentOrder) if r.id == orders[0].id)
    assert row.currency == "KRW"
