"""관리자 인증 엔드포인트 (M1.5 B2 - TOTP 등록). 2단계 로그인(/admin/login)은 B3.

게이트는 로그인 1단계(B3 /admin/login)가 발급하는 totp_setup_pending 서명쿠키.
게이트 실패는 쿠키 무효/역할 미달/이미 활성을 구분하지 않는 generic 401로 통일한다
(비열거 - M1 정책 연장). 서명쿠키가 유효해도 DB를 재확인해 강등·활성화를 즉시 반영한다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import (
    TOTP_SETUP_PENDING,
    clear_admin_pending_cookie,
    read_admin_pending,
    set_auth_cookies,
)
from src.lib.db import get_session
from src.lib.rate_limit import RateLimit
from src.models.user import RoleEnum, User, UserRead
from src.schemas.auth import TotpConfirmRequest, TotpSetupResponse
from src.services import admin_auth_service

router = APIRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_PENDING_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다"
)
_INVALID_CODE = "인증 코드가 올바르지 않습니다"


async def _setup_pending_owner(request: Request, session: AsyncSession) -> User:
    """totp_setup_pending 쿠키 → 미활성 owner User. 그 외는 전부 generic 401(비열거)."""
    sub = read_admin_pending(request, TOTP_SETUP_PENDING)
    if sub is None:
        raise _PENDING_UNAUTHORIZED
    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:
        raise _PENDING_UNAUTHORIZED from exc
    user = await session.get(User, user_id)
    if (
        user is None
        or user.deleted_at is not None
        or user.role != RoleEnum.OWNER
        or user.totp_confirmed_at is not None
    ):
        raise _PENDING_UNAUTHORIZED
    return user


@router.post(
    "/2fa/setup",
    response_model=TotpSetupResponse,
    dependencies=[Depends(RateLimit("5/minute", scope="admin_2fa_setup"))],
)
async def totp_setup(request: Request, session: SessionDep) -> TotpSetupResponse:
    user = await _setup_pending_owner(request, session)
    otpauth_uri = await admin_auth_service.setup_totp(user, session)
    return TotpSetupResponse(otpauth_uri=otpauth_uri)


@router.post(
    "/2fa/confirm",
    response_model=UserRead,
    dependencies=[Depends(RateLimit("5/minute", scope="admin_2fa_confirm"))],
)
async def totp_confirm(
    body: TotpConfirmRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> User:
    user = await _setup_pending_owner(request, session)
    tokens = await admin_auth_service.confirm_totp(user, body.code, session)
    if tokens is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_CODE)
    access, refresh = tokens
    # confirm = 비번(1단계)+TOTP 모두 검증됨 -> 2단계 로그인과 등가라 바로 세션을 연다.
    set_auth_cookies(response, access, refresh, user.nickname)
    clear_admin_pending_cookie(response)
    return user
