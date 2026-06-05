"""인증 엔드포인트 (M1 C 그룹). HTTP 요청 검증/응답 포장만, 로직은 auth_service.

비열거 정책: 가입/로그인 실패 응답·메시지를 통일한다(회원 여부는 수신함 주인만 인지).
토큰은 응답 바디로 내리지 않고 HttpOnly 쿠키로만 전달(localStorage 경로 차단).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import (
    REFRESH_COOKIE_NAME,
    TokenError,
    access_cookie_name,
    clear_auth_cookies,
    decode_token,
    get_current_user,
    set_auth_cookies,
)
from src.lib.db import get_session
from src.lib.exceptions import (
    EmailVerificationError,
    InvalidCredentialsError,
    InvalidTokenError,
    PwnedPasswordError,
    TokenReuseError,
)
from src.models.user import User, UserRead
from src.schemas.auth import (
    LoginRequest,
    MessageResponse,
    SignupRequest,
    VerifyEmailRequest,
)
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# 비열거: 신규/중복 가입 동일 응답.
_SIGNUP_MESSAGE = "입력하신 주소로 메일을 보냈어요"
# 비열거: 이메일/비번 중 무엇이 틀렸는지 구분 노출 금지.
_INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다"
_UNAUTHORIZED = "인증이 필요합니다"
# 비구분: 무효/만료/사용됨 토큰을 단일 메시지로 통일(M1 E2).
_INVALID_VERIFICATION = "유효하지 않거나 만료된 인증 링크입니다"


@router.post("/signup", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def signup(
    body: SignupRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> MessageResponse:
    try:
        await auth_service.signup(
            body.email, body.password, body.nickname, session, background_tasks
        )
    except PwnedPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="유출 이력이 있는 비밀번호입니다. 다른 비밀번호를 사용하세요",
        ) from exc
    return MessageResponse(message=_SIGNUP_MESSAGE)


@router.post("/login", response_model=UserRead)
async def login(
    body: LoginRequest,
    response: Response,
    session: SessionDep,
) -> User:
    try:
        user, access, refresh = await auth_service.login(body.email, body.password, session)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        ) from exc
    set_auth_cookies(response, access, refresh)
    return user


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
) -> MessageResponse:
    # access 쿠키로 유저를 식별해 세션 전체 revoke. 만료/무효면 쿠키만 정리(best-effort).
    token = request.cookies.get(access_cookie_name())
    if token:
        try:
            payload = decode_token(token)
            await auth_service.logout(uuid.UUID(payload["sub"]), session)
        except (TokenError, KeyError, ValueError):
            pass
    clear_auth_cookies(response)
    return MessageResponse(message="로그아웃되었습니다")


@router.post("/refresh", response_model=MessageResponse)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> MessageResponse:
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED)
    try:
        user, access, new_refresh = await auth_service.rotate_refresh(raw, session)
    except TokenReuseError as exc:
        # 탈취 신호: 세션은 service에서 전체 revoke됨. 쿠키도 제거.
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인하세요",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_UNAUTHORIZED
        ) from exc
    set_auth_cookies(response, access, new_refresh)
    return MessageResponse(message="토큰이 갱신되었습니다")


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    session: SessionDep,
) -> MessageResponse:
    # 토큰은 body로 받음(URL/쿼리 로깅 회피). 상태 변경이라 POST -
    # 메일 스캐너의 GET prefetch가 일회용 토큰을 미리 소비하는 것을 차단(M1 E2).
    try:
        await auth_service.verify_email(body.token, session)
    except EmailVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_INVALID_VERIFICATION
        ) from exc
    return MessageResponse(message="이메일 인증이 완료되었습니다")
