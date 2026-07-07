"""관리자 인증 엔드포인트 (M1.5 B2 TOTP 등록 + B3 2단계 로그인).

/admin/login(1단계, 이메일/비번)이 pending 서명쿠키를 발급하고 /admin/2fa/*(등록)·
/admin/login/totp(2단계)가 소비한다. 게이트 실패는 쿠키 무효/역할 미달/활성 상태 불일치를
구분하지 않는 generic 401로 통일한다(비열거 - M1 정책 연장). 서명쿠키가 유효해도 DB를
재확인해 강등·활성화를 즉시 반영한다.
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import (
    TOTP_PENDING,
    TOTP_SETUP_PENDING,
    TRUSTED_DEVICE_COOKIE_NAME,
    clear_admin_pending_cookie,
    clear_trusted_device_cookie,
    read_admin_pending,
    set_admin_pending_cookie,
    set_auth_cookies,
    set_trusted_device_cookie,
)
from src.lib.db import get_session
from src.lib.exceptions import InvalidCredentialsError
from src.lib.rate_limit import RateLimit
from src.models.user import RoleEnum, User, UserRead
from src.schemas.auth import (
    AdminLoginResponse,
    LoginRequest,
    TotpConfirmRequest,
    TotpSetupResponse,
)
from src.services import admin_auth_service, auth_service

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_PENDING_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다"
)
_INVALID_CODE = "인증 코드가 올바르지 않습니다"
# /auth/login과 동일 문구(비열거 - 관리자 로그인이라고 실패 응답이 달라지면 안 된다).
_INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다"


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


async def _totp_pending_owner(request: Request, session: AsyncSession) -> User:
    """totp_pending 쿠키 → TOTP 활성 owner. 그 외는 전부 generic 401(비열거).

    _setup_pending_owner와 대칭 - 이쪽은 활성(totp_confirmed_at 존재)을 요구한다.
    쿠키는 신원 운반만, role·활성화는 DB 재확인(발급 후 강등·리셋 즉시 반영).
    """
    sub = read_admin_pending(request, TOTP_PENDING)
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
        or user.totp_confirmed_at is None
        or user.totp_secret is None
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
    tokens = await admin_auth_service.confirm_totp(
        user, body.code, session, remember_device=body.remember_device
    )
    if tokens is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_CODE)
    # confirm = 비번(1단계)+TOTP 모두 검증됨 -> 2단계 로그인과 등가라 바로 세션을 연다.
    set_auth_cookies(response, tokens.access, tokens.refresh, user.nickname)
    if tokens.trusted_device is not None:
        set_trusted_device_cookie(response, tokens.trusted_device)
    clear_admin_pending_cookie(response)
    return user


# ---------------------------------------------------------------------------
# 2단계 로그인 (B3)
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    dependencies=[Depends(RateLimit("5/minute", scope="admin_login"))],
)
async def admin_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> AdminLoginResponse:
    """관리자 로그인 1단계. 미등록 owner는 등록 게이트, 신뢰 기기는 즉시 완료, 그 외 TOTP 대기.

    실패는 /auth/login과 동일한 generic 401(비열거 - 관리자 계정 여부 비노출).
    """
    tag = auth_service.email_login_tag(body.email)
    client_ip = request.client.host if request.client else None
    try:
        user = await admin_auth_service.authenticate_owner(body.email, body.password, session)
    except InvalidCredentialsError as exc:
        logger.info("auth.admin_login", outcome="fail", target=tag, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        ) from exc

    if user.totp_confirmed_at is None:
        # 미등록 owner는 2FA 등록부터 강제(B1 부트스트랩 결정) - setup 게이트 쿠키 발급.
        set_admin_pending_cookie(response, str(user.id), TOTP_SETUP_PENDING)
        logger.info(
            "auth.admin_login", outcome="setup_required", user_id=str(user.id), ip=client_ip
        )
        return AdminLoginResponse(stage="totp_setup")

    # 신뢰 기기 검사는 반드시 비번 검증 '뒤': 쿠키가 대체하는 건 TOTP(2차)뿐, 비번(1차)은
    # 아니다. 순서가 뒤집히면 쿠키 탈취만으로 비번 없이 로그인된다.
    trusted_raw = request.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
    if trusted_raw and await admin_auth_service.verify_trusted_device(user, trusted_raw, session):
        access, refresh = await admin_auth_service.issue_trusted_session(user, session)
        set_auth_cookies(response, access, refresh, user.nickname)
        logger.info("auth.admin_login", outcome="trusted_skip", user_id=str(user.id), ip=client_ip)
        return AdminLoginResponse(stage="complete")
    if trusted_raw:
        # 무효/만료/실효 신뢰 쿠키는 위생 정리. 편의 기능의 실패가 로그인을 막으면 안 되므로
        # 에러 없이 TOTP 단계로 폴백한다.
        clear_trusted_device_cookie(response)

    set_admin_pending_cookie(response, str(user.id), TOTP_PENDING)
    logger.info("auth.admin_login", outcome="totp_pending", user_id=str(user.id), ip=client_ip)
    return AdminLoginResponse(stage="totp")


@router.post(
    "/login/totp",
    response_model=UserRead,
    dependencies=[Depends(RateLimit("5/minute", scope="admin_login_totp"))],
)
async def admin_login_totp(
    body: TotpConfirmRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> User:
    """관리자 로그인 2단계: TOTP 코드 검증 → 인증 쿠키 발급(+옵트인 신뢰 기기)."""
    user = await _totp_pending_owner(request, session)
    tokens = await admin_auth_service.login_totp(
        user, body.code, session, remember_device=body.remember_device
    )
    if tokens is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_CODE)
    set_auth_cookies(response, tokens.access, tokens.refresh, user.nickname)
    if tokens.trusted_device is not None:
        set_trusted_device_cookie(response, tokens.trusted_device)
    clear_admin_pending_cookie(response)
    return user
