from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import settings
from src.lib.auth import get_current_user, require_verified_email
from src.lib.db import async_session_maker, get_session
from src.lib.rate_limit import RateLimit
from src.models.user import User
from src.schemas.payment import (
    EpisodePaymentIntentCreate,
    EpisodePaymentIntentRead,
    PaymentCompleteRead,
)
from src.services.payment_complete_service import complete_payment
from src.services.payment_intent_service import IntentError, create_episode_intent
from src.services.payment_webhook_service import ingest_webhook
from src.services.portone_webhook import PortOneWebhookError, verify_portone_webhook


class NoStoreRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store_handler(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="요청 값이 올바르지 않습니다",
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except StarletteHTTPException as exc:
                headers = dict(exc.headers or {})
                headers["Cache-Control"] = "no-store"
                raise HTTPException(
                    status_code=exc.status_code,
                    detail=exc.detail,
                    headers=headers,
                ) from exc
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store_handler


router = APIRouter(prefix="/payments", tags=["payments"], route_class=NoStoreRoute)
SessionDep = Annotated[AsyncSession, Depends(get_session)]
VerifiedUserDep = Annotated[User, Depends(require_verified_email)]


@router.post(
    "/episode-intents",
    response_model=EpisodePaymentIntentRead,
    dependencies=[Depends(RateLimit("10/minute", scope="episode_payment_intent"))],
)
async def episode_intent(
    body: EpisodePaymentIntentCreate,
    current_user: VerifiedUserDep,
    session: SessionDep,
    response: Response,
) -> EpisodePaymentIntentRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await create_episode_intent(body, current_user.id, session)
    except IntentError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={"Cache-Control": "no-store"},
        ) from exc


def get_payment_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_session_maker


FactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_payment_session_factory)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "/webhooks/portone",
    status_code=204,
)
async def portone_webhook(request: Request, factory: FactoryDep) -> Response:
    if not settings.portone_webhook_secret.get_secret_value():
        raise HTTPException(503, "결제 알림을 처리할 수 없습니다")
    # 본문 크기를 제한하면서 수신하고, 서명은 변환하지 않은 bytes에 대해 검증한다.
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 65536:
            raise HTTPException(413, "결제 알림이 너무 큽니다")
    try:
        event = verify_portone_webhook(
            bytes(chunks), request.headers, settings.portone_webhook_secret
        )
    except PortOneWebhookError as exc:
        raise HTTPException(400, "결제 알림을 검증할 수 없습니다") from exc
    try:
        await ingest_webhook(factory, event)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "결제 알림을 저장할 수 없습니다") from exc
    return Response(status_code=204)


@router.post(
    "/{payment_id}/complete",
    response_model=PaymentCompleteRead,
    dependencies=[Depends(RateLimit("20/minute", scope="payment_complete"))],
)
async def payment_complete(
    payment_id: Annotated[str, ApiPath(min_length=1, max_length=64)],
    current_user: CurrentUserDep,
    session: SessionDep,
    factory: FactoryDep,
) -> PaymentCompleteRead:
    user_id = current_user.id
    # 인증 SELECT가 연 연결도 PortOne GET 전에 반환한다.
    await session.close()
    try:
        return await complete_payment(payment_id, user_id, factory)
    except IntentError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "결제 상태를 저장할 수 없습니다. 다시 시도해 주세요") from exc
