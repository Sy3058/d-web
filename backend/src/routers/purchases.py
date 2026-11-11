from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from src.routers.payments import CurrentUserDep, NoStoreRoute, SessionDep
from src.schemas.purchase import PurchaseHistoryRead
from src.services.purchase_history_service import get_purchase_history

router = APIRouter(prefix="/my/purchases", tags=["purchases"], route_class=NoStoreRoute)


@router.get("", response_model=PurchaseHistoryRead)
async def purchase_history(
    current_user: CurrentUserDep,
    session: SessionDep,
    page: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
) -> PurchaseHistoryRead:
    try:
        return await get_purchase_history(current_user.id, page, session)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "구매 내역을 불러올 수 없습니다") from exc
