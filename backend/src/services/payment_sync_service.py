"""공통 결제 조회와 원자적 구매 확정. 외부 I/O에는 DB 연결을 보유하지 않는다."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.content_doc import derive_is_free
from src.models.payment import (
    PaymentCancelReason,
    PaymentLog,
    PaymentLogSource,
    PaymentOrder,
    PaymentWebhookReceipt,
    Purchase,
)
from src.models.work import Episode, Work
from src.services.payment_cancellation_service import (
    dispatch_system_cancellation,
    prepare_system_cancellation,
)
from src.services.portone_rest import (
    PortOneAdapterError,
    PortOneCancellationState,
    PortOnePaymentSnapshot,
    PortOneRestAdapter,
)

_logger = logging.getLogger(__name__)

_OPEN = {"preparing", "ready", "expired"}


class PaymentSyncUnavailable(RuntimeError):
    """현재 provider 상태를 확인하지 못했다. 민감한 원인은 노출하지 않는다."""


def reconcile_delay(attempts: int) -> timedelta:
    """추적은 종료하지 않고 결제 상태 재확인 간격만 최대 1시간으로 제한한다."""
    return timedelta(seconds=min(3600, 60 * 2 ** min(max(attempts - 1, 0), 6)))


def _matches(order: PaymentOrder, payment: PortOnePaymentSnapshot) -> bool:
    return (
        payment.currency == order.currency == "KRW"
        and type(payment.total_amount) is int
        and payment.total_amount == order.expected_amount
        and payment.channel_key == order.requested_channel_key
        and payment.channel_type == order.environment.upper()
        and bool(order.requested_channel_key)
        and order.requested_payment_method is not None
        and (payment.payment_method, payment.easy_pay_provider)
        == (order.requested_payment_method, order.requested_easy_pay_provider)
        and payment.paid_at is not None
        and payment.paid_at.utcoffset() is not None
    )


async def sync_payment(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: PortOneRestAdapter,
    payment_id: str,
    source: PaymentLogSource,
    *,
    now: datetime | None = None,
    receipt_id: uuid.UUID | None = None,
    receipt_attempt: int | None = None,
    raise_on_unavailable: bool = False,
    reconcile_attempt: int | None = None,
) -> str:
    """요청 인증은 호출자 책임이다. E3/E4는 이 내부 함수를 재사용한다."""
    fixed_now = now
    source = PaymentLogSource(source)
    if reconcile_attempt is not None and (
        source != PaymentLogSource.RECONCILE or reconcile_attempt < 1
    ):
        raise ValueError("positive reconciliation claim requires reconcile source")
    if (receipt_id is None) != (receipt_attempt is None) or (
        receipt_id is not None and (source != PaymentLogSource.WEBHOOK or receipt_attempt < 1)
    ):
        raise ValueError("webhook receipt and positive claim attempt must be supplied together")
    async with session_factory() as session:
        original = (
            await session.exec(select(PaymentOrder).where(PaymentOrder.payment_id == payment_id))
        ).one_or_none()
        if original is None:
            return "not_found"
        if reconcile_attempt is not None and original.reconcile_attempts != reconcile_attempt:
            return "stale"
        version = (original.status, original.updated_at)
    try:
        payment = await adapter.get_payment(payment_id, store_id=original.store_id)
        failed = False
    except PortOneAdapterError:
        payment, failed = None, True
    now = now or datetime.now(UTC)
    dispatch = False
    async with session_factory() as session, session.begin():
        receipt = None
        if receipt_id is not None:
            receipt = (
                await session.exec(
                    select(PaymentWebhookReceipt)
                    .where(PaymentWebhookReceipt.id == receipt_id)
                    .with_for_update()
                )
            ).one_or_none()
            if (
                receipt is None
                or receipt.payment_id != payment_id
                or receipt.attempts != receipt_attempt
                or receipt.processed_at is not None
                or receipt.ignored_at is not None
            ):
                return "stale"
        # 판매 변경과 동일한 Work→Episode→Order→Purchase 순서를 지킨다.
        work, episode = None, None
        if original.episode_id is not None:
            ref = await session.get(Episode, original.episode_id)
            if ref is not None:
                work = (
                    await session.exec(select(Work).where(Work.id == ref.work_id).with_for_update())
                ).one_or_none()
                episode = (
                    await session.exec(
                        select(Episode)
                        .where(Episode.id == original.episode_id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).one_or_none()
        order = (
            await session.exec(
                select(PaymentOrder).where(PaymentOrder.id == original.id).with_for_update()
            )
        ).one()
        if (order.status, order.updated_at) != version or (
            reconcile_attempt is not None and order.reconcile_attempts != reconcile_attempt
        ):
            return "stale"
        before = order.status
        previous_reason = order.needs_action_reason
        alert_reason = None
        purchase = (
            await session.exec(
                select(Purchase).where(Purchase.payment_order_id == order.id).with_for_update()
            )
        ).one_or_none()
        order.last_synced_at = now
        if reconcile_attempt is None:
            order.reconcile_attempts += 1
        order.next_reconcile_at = now + reconcile_delay(order.reconcile_attempts)
        reason = None
        identity = payment is not None and (
            payment.payment_id == order.payment_id and payment.store_id == order.store_id
        )
        cancellation = payment.match_cancellation(order.cancellation_id) if payment else None
        confirmed_system_cancellation = (
            order.status in {"cancel_pending", "cancelled"}
            and order.cancel_reason
            in {
                PaymentCancelReason.SYSTEM_VERIFICATION,
                PaymentCancelReason.SYSTEM_UNAVAILABLE,
                PaymentCancelReason.SYSTEM_DUPLICATE,
            }
            and identity
            and payment.currency == order.currency == "KRW"
            and payment.money_state == "PAID"
            and type(order.provider_total_amount) is int
            and order.provider_total_amount > 0
            and type(payment.total_amount) is int
            and payment.total_amount == order.provider_total_amount
            and cancellation is not None
            and cancellation.state == PortOneCancellationState.SUCCEEDED
            and type(cancellation.total_amount) is int
            and cancellation.total_amount == order.provider_total_amount
        )
        if order.status == "cancelled":
            order.next_reconcile_at = None
            if payment and payment.money_state == "PAID" and not confirmed_system_cancellation:
                reason = "cancelled_payment_paid"
        elif failed or payment is None:
            if not failed and order.status in _OPEN and order.expires_at <= now:
                order.status = "expired"
        elif not identity:
            reason = "payment_identity_mismatch"
        elif payment.currency != "KRW":
            reason = "unsupported_payment_currency"
        elif payment.money_state == "CANCELLED" or confirmed_system_cancellation:
            total = payment.total_amount
            if (
                type(total) is int
                and total > 0
                and total == (order.provider_total_amount or order.expected_amount)
            ):
                order.status = "cancelled"
                order.provider_total_amount = total
                order.cancelled_amount = total
                order.cancelled_at = (
                    payment.cancelled_at
                    if payment.cancelled_at and payment.cancelled_at.utcoffset() is not None
                    else now
                )
                order.next_reconcile_at = None
                if purchase:
                    purchase.status = "refunded"
                    purchase.refunded_at = order.cancelled_at
                    purchase.refund_amount = purchase.amount
                    session.add(purchase)
            else:
                reason = "cancel_amount_mismatch"
        elif order.status == "review_required":
            pass
        elif order.status == "cancel_pending":
            dispatch = order.cancel_reason != PaymentCancelReason.CUSTOMER_REFUND
        elif payment.money_state in {"UNKNOWN", "PARTIAL_CANCELLED", "VIRTUAL_ACCOUNT_ISSUED"}:
            reason = "unsupported_money_state"
        elif order.status == "paid":
            pass
        elif payment.money_state == "PAID" and order.status in _OPEN:
            cancel_reason = None
            if order.requested_payment_method is None:
                reason = "missing_payment_method_snapshot"
            elif not _matches(order, payment):
                alert_reason = "payment_snapshot_mismatch"
                cancel_reason = PaymentCancelReason.SYSTEM_VERIFICATION
            elif order.kind != "episode_purchase":
                reason = "unsupported_order_kind"
            elif (
                work is None
                or episode is None
                or work.deleted_at is not None
                or episode.deleted_at is not None
                or not work.is_published
                or not episode.is_published
                or episode.is_free
                or derive_is_free(episode.content)
            ):
                cancel_reason = PaymentCancelReason.SYSTEM_UNAVAILABLE
            else:
                winner = (
                    await session.exec(
                        select(Purchase)
                        .where(
                            Purchase.user_id == order.user_id,
                            Purchase.episode_id == order.episode_id,
                            Purchase.environment == order.environment,
                            Purchase.status.in_(["active", "refund_pending", "review_required"]),
                        )
                        .with_for_update()
                    )
                ).first()
                if winner:
                    cancel_reason = PaymentCancelReason.SYSTEM_DUPLICATE
                else:
                    order.provider_status = payment.money_state.value
                    order.transaction_id = payment.transaction_id
                    order.pg_provider = payment.pg_provider
                    order.payment_method = payment.payment_method
                    order.easy_pay_provider = payment.easy_pay_provider
                    order.status = "paid"
                    order.paid_at = payment.paid_at
                    order.provider_total_amount = payment.total_amount
                    order.needs_action_reason = None
                    session.add(order)
                    await session.flush()
                    session.add(
                        Purchase(
                            payment_order_id=order.id,
                            user_id=order.user_id,
                            episode_id=order.episode_id,
                            environment=order.environment,
                            amount=order.expected_amount,
                            paid_at=order.paid_at,
                            status="active",
                        )
                    )
            if cancel_reason:
                session.add(order)
                await session.flush()
                await prepare_system_cancellation(session, order.id, cancel_reason, payment, now)
                await session.refresh(order)
                if order.status in _OPEN:
                    reason = "invalid_provider_amount"
                dispatch = order.status == "cancel_pending"
        elif payment.money_state in {"READY", "PENDING", "PAY_PENDING", "FAILED"}:
            if order.status in _OPEN and order.expires_at <= now:
                order.status = "expired"
        if reason:
            order.needs_action_reason = reason
            if before != "cancelled":
                order.status = "review_required"
                if purchase:
                    purchase.status = "review_required"
                    session.add(purchase)
        # 전체 취소의 확정 증거가 있으면 재발송 없이 종결한다. 과거 발송자는
        # token CAS에서 탈락한다. PAID만으로나 경과 시간으로는 해제하지 않는다.
        if (
            order.status == "cancelled"
            and order.cancel_dispatch_token is not None
            and order.cancel_reason != PaymentCancelReason.CUSTOMER_REFUND
            and identity
            and payment.currency == "KRW"
            and (payment.money_state == "CANCELLED" or confirmed_system_cancellation)
            and type(payment.total_amount) is int
            and payment.total_amount == order.provider_total_amount
            and payment.total_amount > 0
        ):
            order.cancel_dispatch_token = None
            order.cancel_dispatch_started_at = None
            session.add(
                PaymentLog(
                    payment_order_id=order.id,
                    source=source,
                    event_type="cancel_dispatch_recovered",
                    from_status=before,
                    to_status="cancelled",
                    provider_status=payment.money_state.value,
                )
            )
        session.add(order)
        session.add(
            PaymentLog(
                payment_order_id=order.id,
                webhook_receipt_id=receipt_id,
                source=source,
                event_type="sync",
                from_status=before,
                to_status=order.status,
                provider_status=payment.money_state.value if payment else None,
                failure_code=reason or ("provider_unavailable" if failed else None),
            )
        )
        result = order.status
        alert_reason = alert_reason or reason
        alert = (str(order.id), before, result, alert_reason)
        if receipt is not None and not failed and payment is not None:
            receipt.processed_at = now
            session.add(receipt)
    # DB rollback을 운영 이상으로 오인하지 않도록 commit 뒤에만 발행한다.
    if alert_reason and (before != result or previous_reason != alert_reason):
        _report_anomaly(*alert)
    if raise_on_unavailable and (failed or payment is None):
        raise PaymentSyncUnavailable("Payment provider state is unavailable")
    if dispatch:
        if fixed_now is None:
            dispatch_outcome = await dispatch_system_cancellation(
                session_factory, adapter, original.id
            )
        else:
            dispatch_outcome = await dispatch_system_cancellation(
                session_factory, adapter, original.id, clock=lambda: fixed_now
            )
        async with session_factory() as session:
            current = await session.get(PaymentOrder, original.id)
            result = current.status
            dispatch_reason = current.needs_action_reason
        if (
            dispatch_outcome == "review_required"
            and dispatch_reason
            and dispatch_reason != alert_reason
        ):
            _report_anomaly(str(original.id), "cancel_pending", result, dispatch_reason)
    return result


def _report_anomaly(order_id: str, before: str, after: str, reason: str) -> None:
    # Sentry 기본 LoggingIntegration이 ERROR 레코드를 이벤트로 수집한다.
    _logger.error(
        "payment_sync_anomaly",
        extra={
            "payment_order_id": order_id,
            "from_status": before,
            "to_status": after,
            "failure_code": reason,
        },
    )
