"""구글 소셜 로그인 엔드포인트 (M1 D1). BFF 표준: 백엔드가 콜백을 받아 쿠키를 발급한다.

라우터는 HTTP 경계만 - state/nonce 생성·쿠키 운반·302는 여기서, 코드 교환·id_token 검증·
유저 처리는 oauth_service. 콜백은 top-level 브라우저 내비게이션이라 JSON이 아니라 프론트로
302 redirect로 응답한다. 실패는 비열거 generic 코드(oauth_failed/email_exists)로 프론트
로그인 페이지에 넘긴다.

쿠키는 반환하는 RedirectResponse 객체에 직접 set한다. 의존성 주입된 Response에 set하면
실제로 반환하는 RedirectResponse에는 실리지 않기 때문이다.
"""

import secrets
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import (
    clear_oauth_tx_cookie,
    read_oauth_tx,
    set_auth_cookies,
    set_oauth_tx_cookie,
)
from src.lib.db import get_session
from src.lib.exceptions import OAuthEmailExistsError, OAuthError
from src.lib.rate_limit import RateLimit
from src.services import oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_LOGIN_REDIRECT = f"{settings.app_base_url}/auth/login"
_HOME_REDIRECT = settings.app_base_url


def _fail_redirect(code: str) -> RedirectResponse:
    """실패 시 프론트 로그인 페이지로 302 + oauth_tx 일회용 소비. code는 비열거 generic."""
    redirect = RedirectResponse(
        url=f"{_LOGIN_REDIRECT}?error={code}", status_code=status.HTTP_302_FOUND
    )
    clear_oauth_tx_cookie(redirect)
    return redirect


@router.get(
    "/login/google",
    dependencies=[Depends(RateLimit("10/minute", scope="oauth_login"))],
)
async def google_login() -> RedirectResponse:
    """구글 동의 화면으로 302. state(CSRF)·nonce(replay)를 생성해 oauth_tx 쿠키로 운반한다."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    authorize_url = oauth_service.build_google_authorize_url(state, nonce)
    redirect = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    set_oauth_tx_cookie(redirect, state, nonce)
    return redirect


@router.get(
    "/callback/google",
    dependencies=[Depends(RateLimit("20/minute", scope="oauth_callback"))],
)
async def google_callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """구글 콜백. code 교환 -> id_token 검증 -> 유저 확정 -> 인증 쿠키 set 후 홈으로 302.

    실패(동의 거부/파라미터 누락/state 위조/검증 실패/이미 가입)는 프론트 로그인 페이지로
    generic 코드와 함께 302. oauth_tx 쿠키는 처리 후 일회용으로 소비한다.
    """
    tx = read_oauth_tx(request)

    # 동의 거부(error)·필수 파라미터 누락·state 누락/위조 -> CSRF 차단(constant-time 비교).
    if (
        error
        or not code
        or not state
        or tx is None
        or not secrets.compare_digest(state, tx["state"])
    ):
        logger.info("auth.oauth", provider="google", outcome="fail", reason=error or "state")
        return _fail_redirect("oauth_failed")

    try:
        id_token_str = await oauth_service.exchange_code(code)
        claims = await oauth_service.verify_id_token(id_token_str, tx["nonce"])
        user, access, refresh = await oauth_service.resolve_google_user(claims, session)
    except OAuthEmailExistsError:
        return _fail_redirect("email_exists")
    except OAuthError:
        return _fail_redirect("oauth_failed")

    redirect = RedirectResponse(url=_HOME_REDIRECT, status_code=status.HTTP_302_FOUND)
    set_auth_cookies(redirect, access, refresh, user.nickname)
    clear_oauth_tx_cookie(redirect)
    return redirect
