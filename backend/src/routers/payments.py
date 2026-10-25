from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.lib.auth import require_verified_email
from src.lib.db import get_session
from src.lib.rate_limit import RateLimit
from src.models.user import User
from src.schemas.payment import EpisodePaymentIntentCreate, EpisodePaymentIntentRead
from src.services.payment_intent_service import IntentError, create_episode_intent


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
