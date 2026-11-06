"""시스템 전액 보상 취소. 외부 I/O 동안 DB 세션을 보유하지 않는다."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.payment import PaymentCancelReason, PaymentOrder, PaymentOrderStatus
from src.services.portone_rest import (
    PortOneAdapterError,
    PortOneCancellationState,
    PortOneCancelRequest,
    PortOneMoneyState,
    PortOnePaymentSnapshot,
    PortOneRestAdapter,
)

_SYSTEM_REASONS = {
    PaymentCancelReason.SYSTEM_VERIFICATION,
    PaymentCancelReason.SYSTEM_UNAVAILABLE,
    PaymentCancelReason.SYSTEM_DUPLICATE,
}
_RETRY_DELAY = timedelta(minutes=1)
_KEY_WINDOW = timedelta(hours=3)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _identity(order: PaymentOrder, payment: PortOnePaymentSnapshot) -> bool:
    return (
        payment.payment_id == order.payment_id
        and payment.store_id == order.store_id
        and payment.currency == order.currency == "KRW"
        and type(payment.total_amount) is int
        and 0 < payment.total_amount <= 2_147_483_647
    )


class CancellationPreparationResult(StrEnum):
    PREPARED = "prepared"
    REVIEW_REQUIRED = "review_required"
    UNCHANGED = "unchanged"


async def prepare_system_cancellation(
    session: AsyncSession,
    order_id: uuid.UUID,
    reason: PaymentCancelReason,
    payment: PortOnePaymentSnapshot,
    now: datetime,
) -> CancellationPreparationResult:
    """호출자 transaction에 저장하며 commit하지 않는다.

    구매 결정과 판매 대상 lock은 E2 호출자 책임이다. paid 주문에는 적용하지 않는다.
    지원하지 않는 통화는 취소 요청을 만들지 않고 운영 검토 대상으로 격리한다.
    """
    if reason not in _SYSTEM_REASONS:
        raise ValueError("system cancellation reason required")
    order = await session.get(PaymentOrder, order_id, populate_existing=True)
    if (
        order is None
        or payment.money_state != PortOneMoneyState.PAID
        or payment.payment_id != order.payment_id
        or payment.store_id != order.store_id
    ):
        return CancellationPreparationResult.UNCHANGED
    conditions = (
        PaymentOrder.id == order_id,
        PaymentOrder.updated_at == order.updated_at,
        PaymentOrder.status == order.status,
        PaymentOrder.status.in_(["preparing", "ready", "expired"]),
        PaymentOrder.cancel_reason.is_(None),
        PaymentOrder.cancel_idempotency_key.is_(None),
        PaymentOrder.cancel_request_snapshot.is_(None),
        PaymentOrder.cancel_key_issued_at.is_(None),
        PaymentOrder.cancel_dispatch_token.is_(None),
        PaymentOrder.cancel_dispatch_started_at.is_(None),
        PaymentOrder.cancellation_id.is_(None),
    )
    if payment.currency != "KRW":
        values = dict(
            status=PaymentOrderStatus.REVIEW_REQUIRED,
            needs_action_reason="unsupported_payment_currency",
            next_reconcile_at=now,
        )
        outcome = CancellationPreparationResult.REVIEW_REQUIRED
    else:
        if not _identity(order, payment):
            return CancellationPreparationResult.UNCHANGED
        request = PortOneCancelRequest(
            store_id=order.store_id,
            reason=reason,
            amount=payment.total_amount,
            current_cancellable_amount=payment.total_amount,
        )
        values = dict(
            status=PaymentOrderStatus.CANCEL_PENDING,
            provider_total_amount=payment.total_amount,
            cancel_reason=reason,
            cancel_idempotency_key=f"system-cancel-{order_id.hex}",
            cancel_request_snapshot=request.snapshot(),
            cancel_key_issued_at=now,
            next_reconcile_at=now,
        )
        outcome = CancellationPreparationResult.PREPARED
    result = await session.exec(
        update(PaymentOrder)
        .where(*conditions)
        .values(**values)
        .execution_options(synchronize_session="fetch")
    )
    return outcome if result.rowcount == 1 else CancellationPreparationResult.UNCHANGED


def _request(order: PaymentOrder) -> PortOneCancelRequest | None:
    data = order.cancel_request_snapshot
    if not isinstance(data, dict):
        return None
    try:
        request = PortOneCancelRequest(
            store_id=data["storeId"],
            reason=data["reason"],
            amount=data["amount"],
            current_cancellable_amount=data["currentCancellableAmount"],
            requester=data["requester"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    if (
        request.snapshot() != data
        or request.reason != order.cancel_reason
        or request.store_id != order.store_id
        or type(request.amount) is not int
        or request.amount != order.provider_total_amount
    ):
        return None
    return request


async def dispatch_system_cancellation(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: PortOneRestAdapter,
    order_id: uuid.UUID,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> str:
    """GET 선행 후 CAS로 발송한다. 잃은 token은 자동 회수하지 않는다."""
    async with session_factory() as session:
        order = await session.get(PaymentOrder, order_id)
        if (
            order is None
            or order.status != PaymentOrderStatus.CANCEL_PENDING
            or order.cancel_reason not in _SYSTEM_REASONS
            or order.cancel_dispatch_token is not None
        ):
            return "not_dispatchable"
        request = _request(order)
        if request is None or not order.cancel_idempotency_key:
            return "invalid_request"
        payment_id, store_id = order.payment_id, order.store_id
        key, cancellation_id = order.cancel_idempotency_key, order.cancellation_id
        issued_at = order.cancel_key_issued_at
        snapshot = dict(order.cancel_request_snapshot)
    try:
        payment = await adapter.get_payment(payment_id, store_id=store_id)
    except PortOneAdapterError:
        payment = None
    now, token = clock(), uuid.uuid4()
    conditions = (
        PaymentOrder.id == order_id,
        PaymentOrder.updated_at == order.updated_at,
        PaymentOrder.currency == "KRW",
        PaymentOrder.status == PaymentOrderStatus.CANCEL_PENDING,
        PaymentOrder.cancel_reason == request.reason,
        PaymentOrder.cancel_idempotency_key == key,
        PaymentOrder.cancel_key_issued_at == issued_at,
        PaymentOrder.cancel_request_snapshot == snapshot,
        PaymentOrder.cancellation_id == cancellation_id,
        PaymentOrder.cancel_dispatch_token.is_(None),
        PaymentOrder.provider_total_amount == request.amount,
        PaymentOrder.payment_id == payment_id,
        PaymentOrder.store_id == store_id,
    )
    values = {"next_reconcile_at": now + _RETRY_DELAY}
    outcome, send = "pending", False
    if payment is not None:
        if (
            payment.payment_id == payment_id
            and payment.store_id == store_id
            and payment.currency != "KRW"
        ):
            values.update(
                status=PaymentOrderStatus.REVIEW_REQUIRED,
                needs_action_reason="unsupported_payment_currency",
            )
            outcome = "review_required"
        elif not _identity(order, payment) or payment.total_amount != request.amount:
            values.update(
                status=PaymentOrderStatus.REVIEW_REQUIRED,
                needs_action_reason="cancel_identity_mismatch",
            )
            outcome = "review_required"
        elif payment.money_state == PortOneMoneyState.CANCELLED:
            values.update(
                status=PaymentOrderStatus.CANCELLED,
                cancelled_amount=request.amount,
                cancelled_at=(
                    payment.cancelled_at
                    if payment.cancelled_at is not None
                    and payment.cancelled_at.utcoffset() is not None
                    else now
                ),
                next_reconcile_at=None,
            )
            outcome = "cancelled"
        elif payment.money_state in {
            PortOneMoneyState.PARTIAL_CANCELLED,
            PortOneMoneyState.VIRTUAL_ACCOUNT_ISSUED,
            PortOneMoneyState.UNKNOWN,
        }:
            values.update(
                status=PaymentOrderStatus.REVIEW_REQUIRED,
                needs_action_reason="cancel_money_state_unknown",
            )
            outcome = "review_required"
        elif payment.money_state == PortOneMoneyState.PAID:
            match = payment.match_cancellation(cancellation_id)
            if cancellation_id:
                if match and match.state == PortOneCancellationState.FAILED:
                    values.update(
                        status=PaymentOrderStatus.REVIEW_REQUIRED,
                        needs_action_reason="system_cancellation_failed",
                    )
                    outcome = "review_required"
                elif (
                    match
                    and match.total_amount is not None
                    and match.total_amount != request.amount
                ):
                    values.update(
                        status=PaymentOrderStatus.REVIEW_REQUIRED,
                        needs_action_reason="cancel_amount_mismatch",
                    )
                    outcome = "review_required"
                elif (
                    match
                    and match.state == PortOneCancellationState.SUCCEEDED
                    and match.total_amount == request.amount
                ):
                    values.update(
                        status=PaymentOrderStatus.CANCELLED,
                        cancelled_amount=request.amount,
                        cancelled_at=now,
                        next_reconcile_at=None,
                    )
                    outcome = "cancelled"
            elif not payment.cancellations:
                if issued_at is not None and issued_at <= now < issued_at + _KEY_WINDOW:
                    send = True
                    values.update(cancel_dispatch_token=token, cancel_dispatch_started_at=now)
                else:
                    outcome = "key_window_closed"
    async with session_factory() as session, session.begin():
        result = await session.exec(update(PaymentOrder).where(*conditions).values(**values))
        if result.rowcount != 1:
            return "stale"
    if not send:
        return outcome
    if issued_at is None or not issued_at <= clock() < issued_at + _KEY_WINDOW:
        async with session_factory() as session, session.begin():
            await session.exec(
                update(PaymentOrder)
                .where(
                    PaymentOrder.id == order_id,
                    PaymentOrder.cancel_idempotency_key == key,
                    PaymentOrder.cancel_dispatch_token == token,
                )
                .values(cancel_dispatch_token=None, cancel_dispatch_started_at=None)
            )
        return "key_window_closed"
    try:
        response = await adapter.cancel_payment(
            payment_id=payment_id, idempotency_key=key, request=request
        )
    except PortOneAdapterError:
        response = None
    # task cancellation 또는 commit 실패는 token을 남겨 중복 발송을 막는다.
    async with session_factory() as session, session.begin():
        current = await session.get(PaymentOrder, order_id, with_for_update=True)
        if (
            current is None
            or current.cancel_dispatch_token != token
            or current.cancel_idempotency_key != key
        ):
            return "stale"
        current.cancel_dispatch_token = None
        current.cancel_dispatch_started_at = None
        if current.status == PaymentOrderStatus.CANCEL_PENDING:
            current.next_reconcile_at = clock() + _RETRY_DELAY
            if response and response.cancellation_id:
                if current.cancellation_id not in {None, response.cancellation_id}:
                    current.status = PaymentOrderStatus.REVIEW_REQUIRED
                    current.needs_action_reason = "cancel_response_id_conflict"
                else:
                    current.cancellation_id = response.cancellation_id
        session.add(current)
    return "dispatched" if response else "pending"
