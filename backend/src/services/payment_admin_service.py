"""관리자 주문 UUID로 저장 당시 결제 정보를 재조회한다."""

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.models.payment import PaymentOrder
from src.schemas.payment import PaymentCompleteRead
from src.services.payment_intent_service import IntentError
from src.services.payment_sync_service import PaymentSyncUnavailable, sync_payment
from src.services.portone_rest import PortOneNotConfiguredError, PortOneRestAdapter


async def sync_admin_payment(
    order_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> PaymentCompleteRead:
    # 다른 관리자 리소스처럼 경로 id는 로컬 UUID다. 현재 환경으로 과거 주문을 숨기지 않는다.
    async with session_factory() as session:
        order = await session.get(PaymentOrder, order_id)
        if order is None:
            raise IntentError(404, "결제 주문을 찾을 수 없습니다")
        payment_id = order.payment_id
    try:
        async with PortOneRestAdapter(settings.portone_v2_api_secret) as adapter:
            result = await sync_payment(
                session_factory, adapter, payment_id, "admin", raise_on_unavailable=True
            )
    except (PortOneNotConfiguredError, PaymentSyncUnavailable) as exc:
        raise IntentError(503, "결제 상태를 확인할 수 없습니다. 잠시 후 다시 시도하세요") from exc
    if result == "stale":
        raise IntentError(409, "결제 상태가 변경되었습니다. 다시 확인해 주세요")
    if result == "not_found":
        raise IntentError(404, "결제 주문을 찾을 수 없습니다")
    return PaymentCompleteRead(payment_id=payment_id, status=result)
