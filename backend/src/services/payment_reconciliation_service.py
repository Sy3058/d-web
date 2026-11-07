"""미종결 주문과 최근 구매의 결제 상태 재확인 작업."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.payment import PaymentLogSource, PaymentOrder
from src.services.payment_sync_service import reconcile_delay, sync_payment
from src.services.portone_rest import PortOneRestAdapter

_logger = logging.getLogger(__name__)


async def _claim_order(
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime,
    *,
    expired: bool,
    excluded: set[uuid.UUID],
) -> PaymentOrder | None:
    async with session_factory() as session, session.begin():
        eligibility = (
            PaymentOrder.status == "expired"
            if expired
            else or_(
                PaymentOrder.status.in_(
                    ["preparing", "ready", "cancel_pending", "review_required"]
                ),
                and_(
                    PaymentOrder.status == "paid",
                    PaymentOrder.paid_at >= now - timedelta(hours=192),
                ),
            )
        )
        order = (
            await session.exec(
                select(PaymentOrder)
                .where(
                    eligibility,
                    or_(
                        PaymentOrder.next_reconcile_at.is_(None),
                        PaymentOrder.next_reconcile_at <= now,
                    ),
                    PaymentOrder.id.not_in(excluded),
                )
                .order_by(PaymentOrder.next_reconcile_at.asc().nulls_first(), PaymentOrder.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).one_or_none()
        if order is None:
            return None
        order.reconcile_attempts += 1
        # 300초 pool 상한보다 긴 lease를 먼저 commit해 중단된 I/O의 중복 선점을 막는다.
        delay = max(timedelta(seconds=330), reconcile_delay(order.reconcile_attempts))
        order.next_reconcile_at = now + delay
        session.add(order)
        await session.flush()
        detached = PaymentOrder.model_validate(order)
    return detached


async def reconcile_payments(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: PortOneRestAdapter,
    *,
    batch_size: int = 25,
    max_duration_seconds: float = 180.0,
    now: datetime | None = None,
) -> int:
    """각 pool을 최대 100건/300초 처리한다. 반환값은 전체 선점 수다."""
    if batch_size < 1 or max_duration_seconds <= 0:
        raise ValueError("worker limits must be positive")
    attempted = 0
    excluded: set[uuid.UUID] = set()
    for expired in (False, True):
        try:
            async with asyncio.timeout(min(max_duration_seconds, 300.0)):
                for _ in range(min(batch_size, 100)):
                    order = await _claim_order(
                        session_factory,
                        now or datetime.now(UTC),
                        expired=expired,
                        excluded=excluded,
                    )
                    if order is None:
                        break
                    excluded.add(order.id)
                    attempted += 1
                    try:
                        await sync_payment(
                            session_factory,
                            adapter,
                            order.payment_id,
                            PaymentLogSource.RECONCILE,
                            reconcile_attempt=order.reconcile_attempts,
                            now=now,
                        )
                    except Exception:
                        _logger.error(
                            "payment_reconciliation_failed",
                            extra={"payment_order_id": str(order.id)},
                        )
        except TimeoutError:
            pass
    return attempted
