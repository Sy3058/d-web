"""로그인한 사용자 자신의 계정 설정 API."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import (
    clear_admin_pending_cookie,
    clear_auth_cookies,
    clear_trusted_device_cookie,
    get_current_user,
    set_login_hint_cookie,
)
from src.lib.db import get_session
from src.lib.exceptions import ImageValidationError, InvalidCredentialsError, PwnedPasswordError
from src.lib.rate_limit import RateLimit
from src.models.user import User, UserRead
from src.schemas.account import NicknameUpdateRequest, PasswordChangeRequest
from src.schemas.auth import MessageResponse
from src.services import account_password_service, account_service, avatar_service
from src.services.r2_service import R2NotConfiguredError


class _PrivateAccountRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private_handler(request: Request) -> Response:
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
                raise
            except RequestValidationError as exc:
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": jsonable_encoder(
                            [
                                {
                                    key: value
                                    for key, value in error.items()
                                    if key not in ("input", "ctx")
                                }
                                for error in exc.errors()
                            ]
                        )
                    },
                )
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_handler


router = APIRouter(prefix="/auth", tags=["account"], route_class=_PrivateAccountRoute)
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.patch(
    "/me",
    response_model=UserRead,
    dependencies=[Depends(RateLimit("10/minute", scope="account_nickname"))],
)
async def update_nickname(
    body: NicknameUpdateRequest,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
) -> User:
    try:
        user = await account_service.update_nickname(current_user.id, body.nickname, session)
    except InvalidCredentialsError as exc:
        raise HTTPException(401, "인증이 필요합니다") from exc
    set_login_hint_cookie(response, user.nickname)
    return user


@router.post(
    "/me/profile-image",
    response_model=UserRead,
    dependencies=[Depends(RateLimit("5/minute", scope="account_avatar"))],
)
async def update_avatar(
    current_user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> User:
    try:
        data = await file.read(avatar_service.MAX_AVATAR_BYTES + 1)
        return await account_service.update_avatar(current_user.id, data, session)
    except ImageValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except R2NotConfiguredError as exc:
        raise HTTPException(503, "프로필 이미지 저장소를 사용할 수 없습니다") from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(401, "인증이 필요합니다") from exc
    finally:
        await file.close()


@router.put(
    "/me/profile",
    response_model=UserRead,
    dependencies=[Depends(RateLimit("5/minute", scope="account_profile"))],
)
async def update_profile(
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    nickname: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    remove_image: Annotated[bool, Form()] = False,
) -> User:
    try:
        try:
            validated = NicknameUpdateRequest(nickname=nickname)
        except ValidationError as exc:
            raise RequestValidationError(
                [
                    {**error, "loc": ("body", *error["loc"])}
                    for error in exc.errors(include_input=False, include_context=False)
                ]
            ) from exc
        if file is not None and remove_image:
            raise HTTPException(422, "이미지 업로드와 삭제를 함께 요청할 수 없습니다")
        data = await file.read(avatar_service.MAX_AVATAR_BYTES + 1) if file is not None else None
        user = await account_service.update_profile(
            current_user.id, validated.nickname, session, data=data, remove_image=remove_image
        )
    except ImageValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except R2NotConfiguredError as exc:
        raise HTTPException(503, "프로필 이미지 저장소를 사용할 수 없습니다") from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(401, "인증이 필요합니다") from exc
    finally:
        if file is not None:
            await file.close()
    set_login_hint_cookie(response, user.nickname)
    return user


@router.post(
    "/me/password",
    response_model=MessageResponse,
    dependencies=[Depends(RateLimit("5/minute", scope="account_password"))],
)
async def change_password(
    body: PasswordChangeRequest,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
) -> MessageResponse:
    try:
        await account_password_service.change_password(
            current_user.id, body.current_password, body.new_password, session
        )
    except account_password_service.CurrentPasswordMismatchError as exc:
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다") from exc
    except account_password_service.PasswordChangeNotAllowedError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except PwnedPasswordError as exc:
        raise HTTPException(
            422, "유출 이력이 있는 비밀번호입니다. 다른 비밀번호를 사용하세요"
        ) from exc
    clear_auth_cookies(response)
    clear_admin_pending_cookie(response)
    clear_trusted_device_cookie(response)
    return MessageResponse(message="비밀번호가 변경되었습니다. 다시 로그인해 주세요")
