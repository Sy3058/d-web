from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.payment import (
    PaymentCancelReason,
    PaymentEnvironment,
    PaymentOrder,
    PaymentOrderKind,
    PaymentOrderStatus,
    Purchase,
    PurchaseStatus,
)
from src.models.user import User
from src.models.work import Episode
from tests.factories import make_episode, make_work


def _now() -> datetime:
    return datetime.now(UTC)


async def _episode(db_session: AsyncSession, user: User) -> Episode:
    work = await make_work(db_session, user)
    return await make_episode(db_session, work, is_free=False, price=500)


def _order(
    user: User,
    episode: Episode,
    *,
    payment_id: str,
    environment: PaymentEnvironment,
    status: PaymentOrderStatus,
) -> PaymentOrder:
    now = _now()
    return PaymentOrder(
        payment_id=payment_id,
        user_id=user.id,
        kind=PaymentOrderKind.EPISODE_PURCHASE,
        episode_id=episode.id,
        expected_amount=500,
        store_id="store-test",
        requested_channel_key="channel-key-test",
        environment=environment,
        order_name="테스트 주문",
        item_title=episode.title,
        checkout_notice_version="episode-immediate-v1",
        immediate_supply_consented_at=now,
        status=status,
        expires_at=now + timedelta(minutes=30),
        paid_at=now if status is PaymentOrderStatus.PAID else None,
    )


def _donation_order(
    user: User,
    episode: Episode | None,
    *,
    payment_id: str,
    donation_message: str | None,
) -> PaymentOrder:
    now = _now()
    return PaymentOrder(
        payment_id=payment_id,
        user_id=user.id,
        kind=PaymentOrderKind.DONATION,
        episode_id=episode.id if episode is not None else None,
        expected_amount=1000,
        store_id="store-test",
        requested_channel_key="channel-key-test",
        environment=PaymentEnvironment.TEST,
        order_name="테스트 후원",
        item_title=episode.title if episode is not None else "작가 후원",
        donation_message=donation_message,
        status=PaymentOrderStatus.READY,
        expires_at=now + timedelta(minutes=30),
    )


def _cancel_snapshot(
    order: PaymentOrder,
    reason: PaymentCancelReason,
    provider_total_amount: int,
) -> dict[str, str | int]:
    return {
        "storeId": order.store_id,
        "reason": reason.value,
        "amount": provider_total_amount,
        "currentCancellableAmount": provider_total_amount,
        "requester": "CUSTOMER" if reason is PaymentCancelReason.CUSTOMER_REFUND else "ADMIN",
    }


def _set_cancel_bundle(
    order: PaymentOrder,
    reason: PaymentCancelReason,
    *,
    provider_total_amount: int,
) -> None:
    order.provider_total_amount = provider_total_amount
    order.cancel_reason = reason
    order.cancel_idempotency_key = f"cancel-{order.payment_id}"
    order.cancel_request_snapshot = _cancel_snapshot(order, reason, provider_total_amount)


@pytest.mark.asyncio
async def test_test_purchase_does_not_block_live_order(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    test_order = _order(
        user,
        episode,
        payment_id="pay_test_paid",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    db_session.add(test_order)
    await db_session.commit()
    await db_session.refresh(test_order)
    assert test_order.paid_at is not None
    db_session.add(
        Purchase(
            payment_order_id=test_order.id,
            user_id=user.id,
            episode_id=episode.id,
            environment=PaymentEnvironment.TEST,
            status=PurchaseStatus.ACTIVE,
            amount=500,
            paid_at=test_order.paid_at,
        )
    )
    await db_session.commit()

    live_order = _order(
        user,
        episode,
        payment_id="pay_live_open",
        environment=PaymentEnvironment.LIVE,
        status=PaymentOrderStatus.PREPARING,
    )
    db_session.add(live_order)
    await db_session.commit()
    await db_session.refresh(live_order)

    assert live_order.id is not None
    assert live_order.environment == PaymentEnvironment.LIVE


@pytest.mark.asyncio
async def test_donation_order_allows_artist_and_episode_targets(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    artist_donation = _donation_order(
        user,
        None,
        payment_id="pay_artist_donation",
        donation_message=None,
    )
    episode_donation = _donation_order(
        user,
        episode,
        payment_id="pay_episode_donation",
        donation_message="재미있게 봤어요",
    )
    db_session.add_all([artist_donation, episode_donation])
    await db_session.commit()
    await db_session.refresh(artist_donation)
    await db_session.refresh(episode_donation)

    assert artist_donation.episode_id is None
    assert episode_donation.episode_id == episode.id


@pytest.mark.asyncio
async def test_open_episode_order_is_unique_within_environment(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    db_session.add(
        _order(
            user,
            episode,
            payment_id="pay_first_open",
            environment=PaymentEnvironment.TEST,
            status=PaymentOrderStatus.PREPARING,
        )
    )
    await db_session.commit()

    db_session.add(
        _order(
            user,
            episode,
            payment_id="pay_second_open",
            environment=PaymentEnvironment.TEST,
            status=PaymentOrderStatus.READY,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_active_purchase_is_unique_per_environment(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    orders = [
        _order(
            user,
            episode,
            payment_id=f"pay_paid_{index}",
            environment=environment,
            status=PaymentOrderStatus.PAID,
        )
        for index, environment in enumerate(
            [PaymentEnvironment.TEST, PaymentEnvironment.TEST, PaymentEnvironment.LIVE]
        )
    ]
    db_session.add_all(orders)
    await db_session.commit()
    for order in orders:
        await db_session.refresh(order)
        assert order.paid_at is not None

    db_session.add(
        Purchase(
            payment_order_id=orders[0].id,
            user_id=user.id,
            episode_id=episode.id,
            environment=PaymentEnvironment.TEST,
            status=PurchaseStatus.ACTIVE,
            amount=500,
            paid_at=orders[0].paid_at,
        )
    )
    db_session.add(
        Purchase(
            payment_order_id=orders[2].id,
            user_id=user.id,
            episode_id=episode.id,
            environment=PaymentEnvironment.LIVE,
            status=PurchaseStatus.ACTIVE,
            amount=500,
            paid_at=orders[2].paid_at,
        )
    )
    await db_session.commit()

    db_session.add(
        Purchase(
            payment_order_id=orders[1].id,
            user_id=user.id,
            episode_id=episode.id,
            environment=PaymentEnvironment.TEST,
            status=PurchaseStatus.REVIEW_REQUIRED,
            amount=500,
            paid_at=orders[1].paid_at,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_purchase_provenance_must_match_paid_episode_order(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    other_episode = await _episode(db_session, user)
    other_user = User(email="other-reader@example.com", nickname="다른 독자")
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    order = _order(
        user,
        episode,
        payment_id="pay_purchase_provenance",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    assert order.id is not None
    assert order.user_id is not None
    assert order.episode_id is not None
    assert order.paid_at is not None
    assert other_user.id is not None
    assert other_episode.id is not None

    invalid_purchases = [
        Purchase(
            payment_order_id=order.id,
            user_id=other_user.id,
            episode_id=order.episode_id,
            environment=order.environment,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount,
            paid_at=order.paid_at,
        ),
        Purchase(
            payment_order_id=order.id,
            user_id=order.user_id,
            episode_id=other_episode.id,
            environment=order.environment,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount,
            paid_at=order.paid_at,
        ),
        Purchase(
            payment_order_id=order.id,
            user_id=order.user_id,
            episode_id=order.episode_id,
            environment=PaymentEnvironment.LIVE,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount,
            paid_at=order.paid_at,
        ),
        Purchase(
            payment_order_id=order.id,
            user_id=order.user_id,
            episode_id=order.episode_id,
            environment=order.environment,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount + 1,
            paid_at=order.paid_at,
        ),
        Purchase(
            payment_order_id=order.id,
            user_id=order.user_id,
            episode_id=order.episode_id,
            environment=order.environment,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount,
            paid_at=order.paid_at + timedelta(seconds=1),
        ),
    ]
    for purchase in invalid_purchases:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(purchase)
                await db_session.flush()

    matching_purchase = Purchase(
        payment_order_id=order.id,
        user_id=order.user_id,
        episode_id=order.episode_id,
        environment=order.environment,
        status=PurchaseStatus.ACTIVE,
        amount=order.expected_amount,
        paid_at=order.paid_at,
    )
    db_session.add(matching_purchase)
    await db_session.commit()
    await db_session.refresh(matching_purchase)

    assert matching_purchase.id is not None
    assert matching_purchase.payment_order_kind == PaymentOrderKind.EPISODE_PURCHASE


@pytest.mark.asyncio
async def test_donation_order_cannot_back_purchase(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    order = _donation_order(
        user,
        episode,
        payment_id="pay_donation_not_purchase",
        donation_message="후원만 할게요",
    )
    order.status = PaymentOrderStatus.PAID
    order.paid_at = _now()
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    assert order.id is not None
    assert order.episode_id is not None
    assert order.paid_at is not None

    purchase = Purchase(
        payment_order_id=order.id,
        user_id=order.user_id,
        episode_id=order.episode_id,
        environment=order.environment,
        status=PurchaseStatus.ACTIVE,
        amount=order.expected_amount,
        paid_at=order.paid_at,
    )
    db_session.add(purchase)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_purchase_locks_order_provenance_but_allows_status_transitions(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id="pay_purchase_immutable_provenance",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    assert order.id is not None
    assert order.episode_id is not None
    assert order.paid_at is not None

    db_session.add(
        Purchase(
            payment_order_id=order.id,
            user_id=order.user_id,
            episode_id=order.episode_id,
            environment=order.environment,
            status=PurchaseStatus.ACTIVE,
            amount=order.expected_amount,
            paid_at=order.paid_at,
        )
    )
    await db_session.commit()

    _set_cancel_bundle(
        order,
        PaymentCancelReason.SYSTEM_VERIFICATION,
        provider_total_amount=700,
    )
    order.status = PaymentOrderStatus.CANCEL_PENDING
    await db_session.commit()
    order.status = PaymentOrderStatus.CANCELLED
    order.cancelled_amount = 700
    await db_session.commit()

    assert order.expected_amount == 500
    assert order.provider_total_amount == 700

    order.expected_amount += 1
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cancel_request_bundle_rejects_free_form_reason(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id="pay_invalid_cancel_reason",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    order.cancel_reason = "buyer@example.com requested a refund"  # type: ignore[assignment]
    order.cancel_idempotency_key = "cancel-key-123456"
    order.provider_total_amount = order.expected_amount
    order.cancel_request_snapshot = {
        "storeId": order.store_id,
        "reason": PaymentCancelReason.SYSTEM_VERIFICATION,
        "amount": order.provider_total_amount,
        "currentCancellableAmount": order.provider_total_amount,
        "requester": "ADMIN",
    }
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cancel_pending_requires_exact_replay_bundle(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    missing_bundle = _order(
        user,
        episode,
        payment_id="pay_cancel_missing_bundle",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    db_session.add(missing_bundle)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    invalid_snapshot = _order(
        user,
        episode,
        payment_id="pay_cancel_invalid_snapshot",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    invalid_snapshot.cancel_reason = PaymentCancelReason.SYSTEM_UNAVAILABLE
    invalid_snapshot.cancel_idempotency_key = "cancel-invalid-123456"
    invalid_snapshot.provider_total_amount = invalid_snapshot.expected_amount
    invalid_snapshot.cancel_request_snapshot = {
        **_cancel_snapshot(
            invalid_snapshot,
            PaymentCancelReason.SYSTEM_UNAVAILABLE,
            invalid_snapshot.provider_total_amount,
        ),
        "email": "buyer@example.com",
    }
    db_session.add(invalid_snapshot)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    mismatched_reason = _order(
        user,
        episode,
        payment_id="pay_cancel_mismatched_snapshot_reason",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    mismatched_reason.cancel_reason = PaymentCancelReason.SYSTEM_UNAVAILABLE
    mismatched_reason.cancel_idempotency_key = "cancel-mismatch-12345"
    mismatched_reason.provider_total_amount = mismatched_reason.expected_amount
    mismatched_reason.cancel_request_snapshot = _cancel_snapshot(
        mismatched_reason,
        PaymentCancelReason.SYSTEM_VERIFICATION,
        mismatched_reason.provider_total_amount,
    )
    db_session.add(mismatched_reason)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    valid_bundle = _order(
        user,
        episode,
        payment_id="pay_cancel_valid_bundle",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    _set_cancel_bundle(
        valid_bundle,
        PaymentCancelReason.SYSTEM_DUPLICATE,
        provider_total_amount=valid_bundle.expected_amount,
    )
    db_session.add(valid_bundle)
    await db_session.commit()
    await db_session.refresh(valid_bundle)

    assert valid_bundle.id is not None


@pytest.mark.parametrize("provider_total_amount", [300, 500, 700])
@pytest.mark.asyncio
async def test_cancel_uses_authenticated_provider_total_without_changing_order_amount(
    db_session: AsyncSession,
    user: User,
    provider_total_amount: int,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id=f"pay_cancel_provider_{provider_total_amount}",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    _set_cancel_bundle(
        order,
        PaymentCancelReason.SYSTEM_VERIFICATION,
        provider_total_amount=provider_total_amount,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    assert order.status == PaymentOrderStatus.CANCEL_PENDING
    order.status = PaymentOrderStatus.CANCELLED
    order.cancelled_amount = provider_total_amount
    await db_session.commit()
    await db_session.refresh(order)

    assert order.expected_amount == 500
    assert order.provider_total_amount == provider_total_amount
    assert order.cancelled_amount == provider_total_amount


@pytest.mark.parametrize("provider_total_amount", [0, -1])
@pytest.mark.asyncio
async def test_provider_total_amount_must_be_positive_when_present(
    db_session: AsyncSession,
    user: User,
    provider_total_amount: int,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id=f"pay_invalid_provider_total_{provider_total_amount}",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    order.provider_total_amount = provider_total_amount
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(
    ("amount", "current_cancellable_amount"),
    [(500, 500), (None, None)],
)
@pytest.mark.asyncio
async def test_cancel_bundle_requires_authenticated_provider_total(
    db_session: AsyncSession,
    user: User,
    amount: int | None,
    current_cancellable_amount: int | None,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id=f"pay_cancel_without_provider_total_{amount}",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    order.cancel_reason = PaymentCancelReason.SYSTEM_VERIFICATION
    order.cancel_idempotency_key = "cancel-without-provider-total"
    order.cancel_request_snapshot = {
        "storeId": order.store_id,
        "reason": order.cancel_reason.value,
        "amount": amount,
        "currentCancellableAmount": current_cancellable_amount,
        "requester": "ADMIN",
    }
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(
    ("amount", "current_cancellable_amount"),
    [(500, 500), (None, 700), (700, None)],
)
@pytest.mark.asyncio
async def test_cancel_snapshot_must_match_authenticated_provider_total(
    db_session: AsyncSession,
    user: User,
    amount: int | None,
    current_cancellable_amount: int | None,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id=f"pay_cancel_snapshot_{amount}_{current_cancellable_amount}",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    order.provider_total_amount = 700
    order.cancel_reason = PaymentCancelReason.SYSTEM_VERIFICATION
    order.cancel_idempotency_key = "cancel-mismatched-provider-total"
    order.cancel_request_snapshot = {
        "storeId": order.store_id,
        "reason": order.cancel_reason.value,
        "amount": amount,
        "currentCancellableAmount": current_cancellable_amount,
        "requester": "ADMIN",
    }
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("cancelled_amount", [0, 701])
@pytest.mark.asyncio
async def test_cancelled_amount_must_be_within_authenticated_provider_total(
    db_session: AsyncSession,
    user: User,
    cancelled_amount: int,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id=f"pay_invalid_cancelled_amount_{cancelled_amount}",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    _set_cancel_bundle(
        order,
        PaymentCancelReason.SYSTEM_VERIFICATION,
        provider_total_amount=700,
    )
    order.cancelled_amount = cancelled_amount
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cancelled_amount_requires_authenticated_provider_total_independently(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    order = _order(
        user,
        episode,
        payment_id="pay_cancelled_amount_without_provider_total",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCELLED,
    )
    order.cancelled_amount = 500
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_payment_order_database_checks_kind_status_environment_and_cancel_bundle(
    db_session: AsyncSession,
    user: User,
):
    episode = await _episode(db_session, user)
    invalid_kind = _order(
        user,
        episode,
        payment_id="pay_invalid_kind",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    invalid_kind.kind = "donation"  # type: ignore[assignment]
    db_session.add(invalid_kind)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    invalid_status = _order(
        user,
        episode,
        payment_id="pay_invalid_status",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    invalid_status.status = "succeeded"  # type: ignore[assignment]
    db_session.add(invalid_status)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    invalid_environment = _order(
        user,
        episode,
        payment_id="pay_invalid_environment",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.PAID,
    )
    invalid_environment.environment = "sandbox"  # type: ignore[assignment]
    db_session.add(invalid_environment)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    await db_session.refresh(user)
    await db_session.refresh(episode)

    incomplete_cancel = _order(
        user,
        episode,
        payment_id="pay_incomplete_cancel",
        environment=PaymentEnvironment.TEST,
        status=PaymentOrderStatus.CANCEL_PENDING,
    )
    incomplete_cancel.cancel_idempotency_key = "cancel-key-123456"
    db_session.add(incomplete_cancel)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
