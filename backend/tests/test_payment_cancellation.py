import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from src.models.payment import PaymentCancelReason, PaymentOrder
from src.services.payment_cancellation_service import (
    CancellationPreparationResult,
    dispatch_system_cancellation,
    prepare_system_cancellation,
)
from src.services.portone_rest import (
    PortOneApiError,
    PortOneCancellationSnapshot,
    PortOnePaymentSnapshot,
    PortOneTransportError,
)
from tests.factories import make_episode, make_work

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 11, 6, tzinfo=UTC)
_CONNECTION_OWNERS = {}


def payment(**overrides):
    return PortOnePaymentSnapshot.from_payload(
        {
            "id": "pay-cancel-test",
            "storeId": "store-test",
            "status": "PAID",
            "currency": "KRW",
            "amount": {"total": 700},
            **overrides,
        }
    )


@pytest_asyncio.fixture
async def order(db_session, user):
    row = PaymentOrder(
        id=uuid.uuid4(),
        payment_id="pay-cancel-test",
        user_id=user.id,
        kind="donation",
        expected_amount=500,
        store_id="store-test",
        requested_channel_key="channel",
        environment="test",
        order_name="후원",
        item_title="후원",
        status="ready",
        expires_at=NOW + timedelta(minutes=30),
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


async def prepare(factory, order):
    async with factory() as session, session.begin():
        result = await prepare_system_cancellation(
            session, order, PaymentCancelReason.SYSTEM_VERIFICATION, payment(), NOW
        )
        return result == CancellationPreparationResult.PREPARED


async def read(factory, order):
    async with factory() as session:
        return await session.get(PaymentOrder, order)


class Adapter:
    def __init__(self, engine):
        self.engine = engine
        self.connection_owners = _CONNECTION_OWNERS.get(engine)
        if self.connection_owners is None:
            self.connection_owners = {}
            _CONNECTION_OWNERS[engine] = self.connection_owners
            owners = self.connection_owners

            def checkout(connection, record, proxy):
                owners[id(record)] = asyncio.current_task()

            def checkin(connection, record):
                owners.pop(id(record), None)

            event.listen(engine.sync_engine, "checkout", checkout)
            event.listen(engine.sync_engine, "checkin", checkin)
        self.gets = 0
        self.posts = []
        self.snapshot = payment()
        self.failure = None
        self.get_hook = None
        self.post_hook = None

    async def get_payment(self, payment_id, *, store_id):
        assert asyncio.current_task() not in self.connection_owners.values()
        self.gets += 1
        if self.get_hook:
            await self.get_hook()
        return self.snapshot

    async def cancel_payment(self, **kwargs):
        assert asyncio.current_task() not in self.connection_owners.values()
        self.posts.append(kwargs)
        if self.post_hook:
            await self.post_hook()
        if self.failure:
            raise self.failure
        return PortOneCancellationSnapshot.from_payload(
            {"id": "cancel-1", "status": "SUCCEEDED", "totalAmount": 700}
        )


async def test_prepare_cas_keeps_expected_amount_and_caller_rollback(order, session_factory):
    async with session_factory() as session:
        assert (
            await prepare_system_cancellation(
                session, order, PaymentCancelReason.SYSTEM_VERIFICATION, payment(), NOW
            )
            == CancellationPreparationResult.PREPARED
        )
        await session.rollback()
    assert (await read(session_factory, order)).status == "ready"
    assert await prepare(session_factory, order)
    assert not await prepare(session_factory, order)
    row = await read(session_factory, order)
    assert row.expected_amount == 500 and row.provider_total_amount == 700
    assert row.cancel_request_snapshot["amount"] == 700


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "wrong"},
        {"storeId": "wrong"},
        {"amount": {"total": True}},
        {"amount": {"total": 2**31}},
    ],
)
async def test_prepare_invalid_identity_has_no_write(order, session_factory, overrides):
    async with session_factory() as session, session.begin():
        assert (
            await prepare_system_cancellation(
                session, order, PaymentCancelReason.SYSTEM_VERIFICATION, payment(**overrides), NOW
            )
            == CancellationPreparationResult.UNCHANGED
        )
    assert (await read(session_factory, order)).cancel_idempotency_key is None


@pytest.mark.parametrize(
    "failure",
    [
        PortOneTransportError("timeout"),
        PortOneApiError(409, "IDEMPOTENCY_OUTSTANDING_REQUEST", retryable=True),
    ],
)
async def test_timeout_retry_gets_first_and_reuses_exact_request(
    order, session_factory, test_engine, failure
):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    adapter.failure = failure
    for _ in range(2):
        assert (
            await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
            == "pending"
        )
    assert adapter.gets == 2 and len(adapter.posts) == 2
    assert adapter.posts[0] == adapter.posts[1]
    assert (await read(session_factory, order)).cancel_dispatch_token is None


@pytest.mark.parametrize(
    "offset,count", [(timedelta(0), 1), (timedelta(hours=3), 0), (timedelta(seconds=-1), 0)]
)
async def test_exact_key_window(order, session_factory, test_engine, offset, count):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW + offset)
    assert adapter.gets == 1 and len(adapter.posts) == count
    assert (await read(session_factory, order)).status == "cancel_pending"


async def test_single_claim_and_token_blocks_other_workers(order, session_factory, test_engine):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    both_gets = asyncio.Event()
    release_post = asyncio.Event()
    entered_post = asyncio.Event()

    async def get_hook():
        if adapter.gets == 2:
            both_gets.set()
        await asyncio.wait_for(both_gets.wait(), timeout=5)

    async def post_hook():
        entered_post.set()
        await asyncio.wait_for(release_post.wait(), timeout=5)

    adapter.get_hook, adapter.post_hook = get_hook, post_hook
    tasks = [
        asyncio.create_task(
            dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
        )
        for _ in range(2)
    ]
    await asyncio.wait_for(entered_post.wait(), timeout=5)
    assert (
        await dispatch_system_cancellation(
            session_factory, adapter, order, clock=lambda: NOW + timedelta(days=1)
        )
        == "not_dispatchable"
    )
    release_post.set()
    await asyncio.gather(*tasks)
    assert len(adapter.posts) == 1 and adapter.gets == 2


async def test_task_cancel_preserves_token_without_ttl_reclaim(order, session_factory, test_engine):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    entered = asyncio.Event()

    async def block():
        entered.set()
        await asyncio.Event().wait()

    adapter.post_hook = block
    task = asyncio.create_task(
        dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    )
    await asyncio.wait_for(entered.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await read(session_factory, order)).cancel_dispatch_token is not None
    await dispatch_system_cancellation(
        session_factory, adapter, order, clock=lambda: NOW + timedelta(days=1)
    )
    assert adapter.gets == len(adapter.posts) == 1


@pytest.mark.parametrize(
    "items,status",
    [
        ([{"id": "cancel-1", "status": "FAILED"}], "review_required"),
        ([{"id": "cancel-1", "status": "SUCCEEDED", "totalAmount": 700}], "cancelled"),
        ([{"id": "cancel-1", "status": "SUCCEEDED", "totalAmount": 699}], "review_required"),
        ([{"id": "cancel-1", "status": "REQUESTED"}], "cancel_pending"),
        ([{"id": "cancel-1", "status": "FUTURE"}], "cancel_pending"),
        ([{"id": "other", "status": "FAILED"}], "cancel_pending"),
        ([], "cancel_pending"),
    ],
)
async def test_latest_get_matches_current_cancellation(
    order, session_factory, test_engine, items, status
):
    await prepare(session_factory, order)
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, order)
        row.cancellation_id = "cancel-1"
        session.add(row)
    adapter = Adapter(test_engine)
    adapter.snapshot = payment(cancellations=items)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    assert (await read(session_factory, order)).status == status
    assert not adapter.posts


async def test_expiry_between_claim_and_post(order, session_factory, test_engine):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    times = iter([NOW + timedelta(hours=3, microseconds=-1), NOW + timedelta(hours=3)])
    assert (
        await dispatch_system_cancellation(
            session_factory, adapter, order, clock=lambda: next(times)
        )
        == "key_window_closed"
    )
    assert not adapter.posts
    assert (await read(session_factory, order)).cancel_dispatch_token is None


@pytest.mark.parametrize("change", ["key", "token", "state"])
async def test_stale_post_response_cannot_overwrite_new_owner(
    order, session_factory, test_engine, change
):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    new_token = uuid.uuid4()

    async def change_order():
        async with session_factory() as session, session.begin():
            row = await session.get(PaymentOrder, order)
            if change == "key":
                row.cancel_idempotency_key = "replacement-key-0000000"
            elif change == "token":
                row.cancel_dispatch_token = new_token
            else:
                row.status = "review_required"
            session.add(row)

    adapter.post_hook = change_order
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    row = await read(session_factory, order)
    assert row.cancellation_id is None
    if change == "token":
        assert row.cancel_dispatch_token == new_token
    elif change == "key":
        assert row.cancel_dispatch_token is not None
    else:
        assert row.status == "review_required" and row.cancel_dispatch_token is None


async def test_stale_get_does_not_dispatch_after_other_dispatch_completed(
    order, session_factory, test_engine
):
    await prepare(session_factory, order)
    stale_adapter = Adapter(test_engine)

    async def competing_dispatch():
        adapter = Adapter(test_engine)
        adapter.failure = PortOneTransportError("timeout")
        await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
        assert len(adapter.posts) == 1

    stale_adapter.get_hook = competing_dispatch
    assert (
        await dispatch_system_cancellation(session_factory, stale_adapter, order, clock=lambda: NOW)
        == "stale"
    )
    assert not stale_adapter.posts


@pytest.mark.parametrize("state", ["PARTIAL_CANCELLED", "UNKNOWN", "VIRTUAL_ACCOUNT_ISSUED"])
async def test_unsupported_money_state_is_quarantined(order, session_factory, test_engine, state):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    adapter.snapshot = payment(status=state)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    assert (await read(session_factory, order)).status == "review_required"
    assert not adapter.posts


@pytest.mark.parametrize("items", [[{"id": "other", "status": "FAILED"}], {"bad": "shape"}])
async def test_existing_ambiguous_cancellation_prevents_initial_post(
    order, session_factory, test_engine, items
):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    adapter.snapshot = payment(cancellations=items)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    assert not adapter.posts


async def test_episode_purchase_compensation(order, db_session, session_factory, user, test_engine):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, is_free=False, price=500)
    row = await db_session.get(PaymentOrder, order)
    row.kind = "episode_purchase"
    row.episode_id = episode.id
    row.checkout_notice_version = "episode-immediate-v1"
    row.immediate_supply_consented_at = NOW
    db_session.add(row)
    await db_session.commit()
    assert await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    row = await read(session_factory, order)
    assert row.expected_amount == 500 and row.provider_total_amount == 700
    assert row.status == "cancel_pending" and len(adapter.posts) == 1


async def test_prepare_concurrent_single_snapshot(order, session_factory):
    async def attempt(reason):
        async with session_factory() as session, session.begin():
            return await prepare_system_cancellation(session, order, reason, payment(), NOW)

    results = await asyncio.gather(
        attempt(PaymentCancelReason.SYSTEM_DUPLICATE),
        attempt(PaymentCancelReason.SYSTEM_VERIFICATION),
    )
    assert sorted(results) == sorted(
        [CancellationPreparationResult.UNCHANGED, CancellationPreparationResult.PREPARED]
    )
    row = await read(session_factory, order)
    assert row.cancel_request_snapshot["reason"] == row.cancel_reason


async def test_naive_provider_cancelled_at_uses_utc_clock(order, session_factory, test_engine):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    adapter.snapshot = payment(status="CANCELLED", cancelledAt="2026-11-06T12:00:00")
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    row = await read(session_factory, order)
    assert row.status == "cancelled" and row.cancelled_at == NOW


async def test_response_commit_failure_preserves_claim(order, session_factory, test_engine):
    await prepare(session_factory, order)
    adapter = Adapter(test_engine)
    failing_session = None
    calls = 0

    def factory():
        nonlocal calls, failing_session
        calls += 1
        session = session_factory()
        if calls == 3:
            failing_session = session.sync_session

            def fail_commit(session):
                raise SQLAlchemyError("injected result commit failure")

            event.listen(failing_session, "before_commit", fail_commit)
        return session

    with pytest.raises(SQLAlchemyError, match="injected"):
        await dispatch_system_cancellation(factory, adapter, order, clock=lambda: NOW)
    row = await read(session_factory, order)
    assert row.cancel_dispatch_token is not None
    assert row.cancellation_id is None
    assert len(adapter.posts) == 1


def cancellation_bundle(row):
    return (
        row.cancel_reason,
        row.cancel_idempotency_key,
        row.cancel_request_snapshot,
        row.cancel_key_issued_at,
        row.cancel_dispatch_token,
        row.cancel_dispatch_started_at,
        row.cancellation_id,
    )


@pytest.mark.parametrize("currency", ["USD", "JPY", None])
@pytest.mark.parametrize("status", ["preparing", "ready", "expired"])
async def test_unsupported_currency_quarantined_without_amount_or_bundle_changes(
    order, session_factory, test_engine, currency, status
):
    async with session_factory() as session, session.begin():
        row = await session.get(PaymentOrder, order)
        row.status = status
        row.provider_total_amount = 650
        session.add(row)
    async with session_factory() as session, session.begin():
        result = await prepare_system_cancellation(
            session,
            order,
            PaymentCancelReason.SYSTEM_VERIFICATION,
            payment(currency=currency),
            NOW,
        )
        assert result == CancellationPreparationResult.REVIEW_REQUIRED
    row = await read(session_factory, order)
    assert row.status == "review_required"
    assert row.needs_action_reason == "unsupported_payment_currency"
    assert row.next_reconcile_at == NOW
    assert (row.expected_amount, row.provider_total_amount, row.currency) == (500, 650, "KRW")
    assert cancellation_bundle(row) == (None,) * 7
    adapter = Adapter(test_engine)
    await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
    assert adapter.gets == 0 and not adapter.posts
    async with session_factory() as session, session.begin():
        assert (
            await prepare_system_cancellation(
                session,
                order,
                PaymentCancelReason.SYSTEM_VERIFICATION,
                payment(currency=currency),
                NOW,
            )
            == CancellationPreparationResult.UNCHANGED
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "different"},
        {"storeId": "different"},
        {"status": "READY"},
    ],
)
async def test_unsupported_currency_requires_same_paid_identity(order, session_factory, overrides):
    async with session_factory() as session, session.begin():
        assert (
            await prepare_system_cancellation(
                session,
                order,
                PaymentCancelReason.SYSTEM_VERIFICATION,
                payment(currency="USD", **overrides),
                NOW,
            )
            == CancellationPreparationResult.UNCHANGED
        )
    row = await read(session_factory, order)
    assert row.status == "ready" and row.needs_action_reason is None
    assert cancellation_bundle(row) == (None,) * 7


async def test_unsupported_currency_caller_rollback(order, session_factory):
    async with session_factory() as session:
        assert (
            await prepare_system_cancellation(
                session,
                order,
                PaymentCancelReason.SYSTEM_VERIFICATION,
                payment(currency="USD"),
                NOW,
            )
            == CancellationPreparationResult.REVIEW_REQUIRED
        )
        await session.rollback()
    row = await read(session_factory, order)
    assert row.status == "ready" and row.needs_action_reason is None
    assert row.next_reconcile_at is None and row.provider_total_amount is None


@pytest.mark.parametrize("winner", ["paid", "cancelled", "cancel_pending"])
async def test_unsupported_currency_stale_prepare_preserves_winner(
    order, session_factory, monkeypatch, winner
):
    async with session_factory() as session:
        original_get = session.get

        async def stale_get(*args, **kwargs):
            stale = await original_get(*args, **kwargs)
            async with session_factory() as other, other.begin():
                if winner == "cancel_pending":
                    assert (
                        await prepare_system_cancellation(
                            other, order, PaymentCancelReason.SYSTEM_DUPLICATE, payment(), NOW
                        )
                        == CancellationPreparationResult.PREPARED
                    )
                else:
                    row = await other.get(PaymentOrder, order)
                    row.status = winner
                    other.add(row)
            return stale

        monkeypatch.setattr(session, "get", stale_get)
        assert (
            await prepare_system_cancellation(
                session,
                order,
                PaymentCancelReason.SYSTEM_VERIFICATION,
                payment(currency="USD"),
                NOW,
            )
            == CancellationPreparationResult.UNCHANGED
        )
        await session.commit()
    row = await read(session_factory, order)
    assert row.status == winner and row.needs_action_reason is None
    if winner == "cancel_pending":
        assert row.cancel_reason == PaymentCancelReason.SYSTEM_DUPLICATE
        assert row.cancel_request_snapshot["amount"] == 700
    else:
        assert cancellation_bundle(row) == (None,) * 7


@pytest.mark.parametrize("currency", ["USD", "JPY", None])
async def test_dispatch_unsupported_currency_preserves_request_no_post(
    order, session_factory, test_engine, currency
):
    assert await prepare(session_factory, order)
    before = await read(session_factory, order)
    adapter = Adapter(test_engine)
    adapter.snapshot = payment(currency=currency)
    assert (
        await dispatch_system_cancellation(session_factory, adapter, order, clock=lambda: NOW)
        == "review_required"
    )
    row = await read(session_factory, order)
    assert row.needs_action_reason == "unsupported_payment_currency"
    assert cancellation_bundle(row) == cancellation_bundle(before)
    assert (row.expected_amount, row.provider_total_amount, row.currency) == (500, 700, "KRW")
    assert adapter.gets == 1 and not adapter.posts
