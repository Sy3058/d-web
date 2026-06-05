"""JWT 발급·검증 유틸 (M1 B2).

access 토큰만 다룬다. refresh는 opaque 랜덤이라 services/auth_service.py 담당.

payload 구조:
  sub  - str(user_id) UUID 문자열
  typ  - "access" 고정 (수동 검증, PyJWT가 커스텀 클레임 자동 검증 안 함)
  exp  - 만료 시각 (PyJWT 자동 검증)
  iat  - 발급 시각
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.db import get_session
from src.models.user import User


class TokenError(Exception):
    """만료·위조·잘못된 typ 등 토큰 검증 실패."""


def create_access_token(user_id: str) -> str:
    """user_id(UUID str)로 access JWT 발급. PII(이메일 등) payload 포함 금지."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """JWT 검증 후 payload 반환.

    만료·위조 서명·잘못된 typ 시 TokenError를 raise한다.
    라우터(C 그룹)에서 이 예외를 잡아 401로 매핑한다.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenError("expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("invalid") from e

    if payload.get("typ") != "access":
        raise TokenError("invalid typ")

    return payload


# ---------------------------------------------------------------------------
# HttpOnly 쿠키 발급/제거 (M1 B3)
# ---------------------------------------------------------------------------
#
# 토큰은 응답 바디로 내리지 않는다. 쿠키 전용 (localStorage 경로 차단).
#
# access  : SameSite=Lax,    Path=/             - 일반 네비게이션에 동반돼야 함
# refresh : SameSite=Strict, Path=/auth/refresh - 갱신/로그아웃 외 요청엔 안 실어 노출 축소
#
# Secure는 settings.cookie_secure로 환경 분기(로컬 http=False, 운영=True). 하드코딩 금지.
#
# __Host- 프리픽스(access 한정): Secure + Path=/ + Domain 미지정을 브라우저가 강제해
# 하위도메인발 쿠키 주입을 막는다. 단 프리픽스는 Secure를 요구하므로 운영(https)에서만
# 붙인다 - 로컬 http에서 붙이면 브라우저가 쿠키를 거부해 로그인이 깨진다.
# refresh는 Path를 제한하므로(=Path=/ 위반) __Host- 대상에서 제외한다.
#
# ⚠️ 인증 쿠키 same-site 전제: SameSite=Lax/Strict라 FE/Admin/API가 한 eTLD+1 아래
# (Caddy 단일 도메인)에 묶여야 전송된다. API를 별도 도메인으로 분리하면 로그인이 깨진다.

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth/refresh"


def access_cookie_name() -> str:
    """access 쿠키 이름. 운영(Secure)에서만 __Host- 프리픽스를 붙인다.

    C 그룹에서 쿠키를 읽을 때도 이 함수로 이름을 맞춰야 dev/운영이 일관된다.
    """
    return "__Host-access_token" if settings.cookie_secure else "access_token"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """응답에 access/refresh 쿠키를 set. C2 로그인·C4 갱신·D1 OAuth에서 사용."""
    secure = settings.cookie_secure
    response.set_cookie(
        key=access_cookie_name(),
        value=access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="strict",
    )


def clear_auth_cookies(response: Response) -> None:
    """access/refresh 쿠키를 만료시킨다. C3 로그아웃에서 사용.

    브라우저가 삭제하려면 set 때와 key·path·secure·samesite가 일치해야 한다
    (특히 refresh의 Path=/auth/refresh).
    """
    secure = settings.cookie_secure
    response.delete_cookie(
        key=access_cookie_name(),
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="strict",
    )


# ---------------------------------------------------------------------------
# 현재 유저 의존성 (M1 C5 /auth/me, 후속 보호 라우트 공용)
# ---------------------------------------------------------------------------

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다"
)


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """access 쿠키 → JWT 검증 → User 반환. 무효/만료/미존재·탈퇴 유저는 401.

    로그인 상태 판정의 단일 소스(G5 마이페이지·Navbar). 쿠키 이름은 환경 분기되므로
    access_cookie_name()으로 맞춘다.
    """
    token = request.cookies.get(access_cookie_name())
    if not token:
        raise _UNAUTHORIZED
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        raise _UNAUTHORIZED from exc

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise _UNAUTHORIZED
    return user


_FORBIDDEN_UNVERIFIED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="이메일 인증이 필요합니다"
)


async def require_verified_email(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """이메일 인증을 마친 유저만 통과시키는 의존성. 미인증은 403(권한 없음).

    get_current_user 위에 합성된다 - 비로그인은 거기서 401, 로그인했지만 미인증이면
    여기서 403. 진실 소스는 is_email_verified(bool)이며 email_verified_at(시각)이 아니다.

    M1에서는 어떤 라우터에도 부착하지 않고 함수만 제공한다(실제 차단은 M3 결제·M4 댓글).
    """
    if not current_user.is_email_verified:
        raise _FORBIDDEN_UNVERIFIED
    return current_user
