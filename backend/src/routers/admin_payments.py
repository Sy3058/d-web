"""Owner 전용 결제 상태 재조회. 고객 환불 요청은 생성하지 않는다."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from src.lib.auth import require_owner
from src.lib.rate_limit import RateLimit
from src.models.user import User
from src.routers.payments import FactoryDep, NoStoreRoute, SessionDep
from src.schemas.payment import PaymentCompleteRead
from src.services.payment_admin_service import sync_admin_payment
from src.services.payment_intent_service import IntentError

router = APIRouter(prefix="/admin/payments", tags=["admin-payments"], route_class=NoStoreRoute)
OwnerDep = Annotated[User, Depends(require_owner)]


@router.post(
    "/{order_id}/sync",
    response_model=PaymentCompleteRead,
    dependencies=[Depends(RateLimit("20/minute", scope="admin_payment_sync"))],
)
async def payment_sync(
    order_id: uuid.UUID, owner: OwnerDep, session: SessionDep, factory: FactoryDep
) -> PaymentCompleteRead:
    # 인증 SELECT가 연 연결도 외부 GET 전에 풀로 돌려준다.
    await session.close()
    try:
        return await sync_admin_payment(order_id, factory)
    except IntentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "결제 상태를 저장할 수 없습니다. 다시 시도해 주세요") from exc
