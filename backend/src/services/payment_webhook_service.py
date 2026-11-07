"""서명 검증된 결제 webhook의 durable inbox와 제한된 재처리 worker."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.payment import PaymentLogSource, PaymentWebhookReceipt
from src.services.payment_sync_service import sync_payment
from src.services.portone_rest import PortOneRestAdapter
from src.services.portone_webhook import VerifiedPortOneWebhook

_logger = logging.getLogger(__name__)
_EVENT_TYPES = frozenset(
    f"Transaction.{name}"
    for name in (
        "Ready",
        "Paid",
        "VirtualAccountIssued",
        "PartialCancelled",
        "Cancelled",
        "Failed",
        "PayPending",
        "CancelPending",
        "DisputeCreated",
        "DisputeResolved",
    )
)


async def ingest_webhook(
    session_factory: async_sessionmaker[AsyncSession],
    event: VerifiedPortOneWebhook,
    *,
    now: datetime | None = None,
) -> None:
    """호출자가 raw 서명 검증을 끝낸 이벤트만 전달한다. 반환 전에 반드시 commit한다."""
    now = now or datetime.now(UTC)
    async with session_factory() as session, session.begin():
        await session.exec(
            insert(PaymentWebhookReceipt)
            .values(
                webhook_id=event.webhook_id,
                event_type=event.event_type,
                payment_id=event.payment_id,
                received_at=now,
                ignored_at=(
                    now if event.event_type not in _EVENT_TYPES or not event.payment_id else None
                ),
            )
            .on_conflict_do_nothing(index_elements=[PaymentWebhookReceipt.webhook_id])
        )


async def _claim_receipt(
    session_factory: async_sessionmaker[AsyncSession], now: datetime
) -> PaymentWebhookReceipt | None:
    async with session_factory() as session, session.begin():
        receipt = (
            await session.exec(
                select(PaymentWebhookReceipt)
                .where(
                    PaymentWebhookReceipt.processed_at.is_(None),
                    PaymentWebhookReceipt.ignored_at.is_(None),
                    or_(
                        PaymentWebhookReceipt.next_attempt_at.is_(None),
                        PaymentWebhookReceipt.next_attempt_at <= now,
                    ),
                )
                .order_by(PaymentWebhookReceipt.received_at, PaymentWebhookReceipt.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).one_or_none()
        if receipt is None:
            return None
        receipt.attempts += 1
        # 예약은 I/O 전에 commit한다. crash 이후에도 기한이 지나면 다시 선점할 수 있다.
        delay_seconds = min(3600, 30 * 2 ** min(receipt.attempts - 1, 7))
        receipt.next_attempt_at = now + timedelta(seconds=delay_seconds)
        session.add(receipt)
        await session.flush()
        # expire_on_commit 설정과 무관하게 I/O 단계에 ORM lazy load를 남기지 않는다.
        detached = PaymentWebhookReceipt.model_validate(receipt)
    return detached


async def process_webhook_receipts(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: PortOneRestAdapter,
    *,
    batch_size: int = 25,
    max_duration_seconds: float = 180.0,
    now: datetime | None = None,
) -> int:
    """한 틱에 최대 100건·300초만 사용한다. 반환값은 선점한 receipt 수다."""
    if batch_size < 1 or max_duration_seconds <= 0:
        raise ValueError("worker limits must be positive")
    attempted = 0
    try:
        async with asyncio.timeout(min(max_duration_seconds, 300.0)):
            for _ in range(min(batch_size, 100)):
                receipt = await _claim_receipt(session_factory, now or datetime.now(UTC))
                if receipt is None:
                    break
                attempted += 1
                try:
                    await sync_payment(
                        session_factory,
                        adapter,
                        receipt.payment_id,
                        PaymentLogSource.WEBHOOK,
                        now=now,
                        receipt_id=receipt.id,
                        receipt_attempt=receipt.attempts,
                    )
                except Exception:
                    # 예외 메시지/traceback에는 provider 응답·개인정보가 있을 수 있다.
                    _logger.error(
                        "payment_webhook_processing_failed",
                        extra={"webhook_receipt_id": str(receipt.id)},
                    )
    except TimeoutError:
        pass
    return attempted
