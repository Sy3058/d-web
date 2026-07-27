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
from urllib.parse import quote

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.db import get_session
from src.models.user import RoleEnum, User


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


# 시계 역점프 허용 오차(초) - 이 모듈의 모든 jwt.decode에 leeway로 전달한다.
# 발급·검증이 같은 서버여도 시계는 단조가 아니다: NTP/WSL2 보정으로 시계가 뒤로 점프하면
# 방금 발급한 토큰의 iat가 "미래"가 되고 PyJWT(2.6+)가 ImmatureSignatureError로 거부한다.
# 실제로 테스트 스위트 도중 ~1.9초 역점프가 관측돼(2026-07-27, PG 로그 타임스탬프 역행 -
# 상세는 MISTAKES) 임의 테스트 1개가 401로 죽는 간헐 실패를 만들었다. 10초 = 실측 점프의
# 5배 여유. exp 판정도 같이 10초 관대해지지만 최단 수명 토큰(pending·oauth_tx 600초)
# 대비 1.7%라 수용한다.
JWT_LEEWAY_SECONDS = 10


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
            leeway=JWT_LEEWAY_SECONDS,
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

# 네비 표시용 힌트 쿠키. 비-HttpOnly: FE 섬이 document.cookie로 직접 읽어야 한다.
# 인증이 아니라 표시용이라 노출/위조돼도 인가 영향이 없다(서버는 이 값을 신뢰하지 않는다).
# access의 __Host- 프리픽스는 안 붙인다 - JS가 dev/운영 무관하게 고정 이름으로 읽게 한다.
LOGIN_HINT_COOKIE_NAME = "login_hint"


def access_cookie_name() -> str:
    """access 쿠키 이름. 운영(Secure)에서만 __Host- 프리픽스를 붙인다.

    C 그룹에서 쿠키를 읽을 때도 이 함수로 이름을 맞춰야 dev/운영이 일관된다.
    """
    return "__Host-access_token" if settings.cookie_secure else "access_token"


def set_auth_cookies(
    response: Response, access_token: str, refresh_token: str, nickname: str
) -> None:
    """access/refresh + 네비 표시용 login_hint 쿠키를 set. 로그인·갱신·OAuth 공용.

    login_hint는 인증 쿠키와 같은 함수에서 발급해 둘이 항상 함께 set/clear되도록 한다
    (한쪽 누락 desync 방지). 라벨 출처는 access(15분)가 아니라 refresh 수명에 맞춘다 -
    getMe 401은 access 만료일 수 있어 로그아웃과 구분되지 않으므로 라벨 gate에 쓸 수 없다.
    """
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
    # 닉네임은 한글/특수문자 가능 -> quote(safe="")로 URL 인코딩해 쿠키/헤더 인젝션을 차단한다.
    # FE는 document.cookie로 읽어 decodeURIComponent로 복원한다. httponly=False는 의도된 것.
    response.set_cookie(
        key=LOGIN_HINT_COOKIE_NAME,
        value=quote(nickname, safe=""),
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/",
        httponly=False,
        secure=secure,
        samesite="lax",
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
    # login_hint도 함께 제거. set 때와 path·secure·samesite·httponly가 일치해야 브라우저가 지운다.
    response.delete_cookie(
        key=LOGIN_HINT_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=secure,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# OAuth 트랜잭션 쿠키 (M1 D1 소셜 로그인 - state/nonce 단명 운반)
# ---------------------------------------------------------------------------
#
# 로그인 시작(/auth/login/google)에서 만든 state(CSRF)·nonce(id_token replay)를 콜백까지
# 나르는 단명 쿠키. 서버 저장 없이 jwt_secret 서명 JWT로 stateless 처리한다.
#
# SameSite=Lax: 구글 콜백은 cross-site top-level GET 내비게이션이라 Strict면 쿠키가 안 실려
# 로그인이 깨진다. Lax는 top-level GET에 동반되므로 Lax가 정답(인증 쿠키 Strict와 다른 의도).
# Path=/auth: 로그인/콜백 외 요청엔 노출하지 않는다. (__Host-는 Path=/ 를 요구하므로 미사용)

OAUTH_TX_COOKIE_NAME = "oauth_tx"
OAUTH_TX_MAX_AGE = 600  # 10분 - 로그인 시작~콜백 왕복엔 충분, 그 이상은 만료시켜 재사용 차단


def set_oauth_tx_cookie(response: Response, state: str, nonce: str) -> None:
    """state·nonce를 서명 JWT로 oauth_tx 쿠키에 set. 콜백에서 read_oauth_tx로 검증한다."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "state": state,
            "nonce": nonce,
            "typ": "oauth_tx",
            "iat": now,
            "exp": now + timedelta(seconds=OAUTH_TX_MAX_AGE),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response.set_cookie(
        key=OAUTH_TX_COOKIE_NAME,
        value=token,
        max_age=OAUTH_TX_MAX_AGE,
        path="/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def read_oauth_tx(request: Request) -> dict[str, str] | None:
    """oauth_tx 쿠키를 검증·디코드해 {"state","nonce"} 반환. 누락/만료/위조면 None.

    서명·만료는 jwt.decode가 검증한다. typ가 oauth_tx가 아니면 다른 토큰 오용이라 거부.
    """
    raw = request.cookies.get(OAUTH_TX_COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(
            raw,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            leeway=JWT_LEEWAY_SECONDS,
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "oauth_tx":
        return None
    state = payload.get("state")
    nonce = payload.get("nonce")
    if not isinstance(state, str) or not isinstance(nonce, str):
        return None
    return {"state": state, "nonce": nonce}


def clear_oauth_tx_cookie(response: Response) -> None:
    """oauth_tx 쿠키를 만료시킨다. 콜백 처리(성공/실패) 후 일회용으로 소비한다."""
    response.delete_cookie(
        key=OAUTH_TX_COOKIE_NAME,
        path="/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# 관리자 2FA pending 쿠키 (M1.5 B2/B3 - 로그인 1단계와 TOTP 단계 사이 단명 운반)
# ---------------------------------------------------------------------------
#
# /admin/login 1단계(B3)가 발급하고 /admin/2fa/*(B2 등록)·/admin/login/totp(B3)가 소비한다.
# oauth_tx처럼 서버 저장 없는 jwt_secret 서명 JWT. typ 클레임이 두 흐름을 구분한다:
#   totp_setup_pending - TOTP 미등록 owner. /admin/2fa/setup·confirm만 통과
#   totp_pending       - TOTP 활성 owner. /admin/login/totp만 통과
# SameSite=Strict: oauth_tx가 Lax인 사유(구글발 cross-site top-level GET 콜백)가 여기엔
# 없다 - 이 쿠키는 admin SPA의 same-site fetch POST에만 실리면 된다. Path=/admin으로
# 로그인/2FA 외 요청 노출을 줄인다.

ADMIN_PENDING_COOKIE_NAME = "admin_totp_pending"
ADMIN_PENDING_MAX_AGE = 600  # 10분 - 1단계 통과~코드 입력엔 충분, 그 이상은 만료로 재사용 차단
ADMIN_PENDING_PATH = "/admin"
TOTP_SETUP_PENDING = "totp_setup_pending"
TOTP_PENDING = "totp_pending"


def create_admin_pending_token(user_id: str, typ: str) -> str:
    """pending 단계 운반용 서명 JWT. typ은 TOTP_SETUP_PENDING 또는 TOTP_PENDING."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "typ": typ,
            "iat": now,
            "exp": now + timedelta(seconds=ADMIN_PENDING_MAX_AGE),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def set_admin_pending_cookie(response: Response, user_id: str, typ: str) -> None:
    """1단계(이메일/비번) 통과 직후 pending 쿠키를 set. B3 /admin/login이 호출한다."""
    response.set_cookie(
        key=ADMIN_PENDING_COOKIE_NAME,
        value=create_admin_pending_token(user_id, typ),
        max_age=ADMIN_PENDING_MAX_AGE,
        path=ADMIN_PENDING_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def read_admin_pending(request: Request, expected_typ: str) -> str | None:
    """pending 쿠키를 검증·디코드해 user_id(sub)를 반환. 누락/만료/위조/typ 불일치면 None.

    setup 흐름과 로그인 흐름의 쿠키를 서로 오용할 수 없도록 typ을 정확히 대조한다
    (setup_pending으로 /admin/login/totp 통과 금지, 역방향 동일). 이 쿠키는 신원 운반만
    담당한다 - role·활성화 상태는 발급 후 바뀔 수 있으므로 소비자가 DB에서 재확인한다.
    """
    raw = request.cookies.get(ADMIN_PENDING_COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = jwt.decode(
            raw,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            leeway=JWT_LEEWAY_SECONDS,
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != expected_typ:
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    return sub


def clear_admin_pending_cookie(response: Response) -> None:
    """pending 쿠키를 만료시킨다. TOTP 단계 성공 시 일회용으로 소비한다."""
    response.delete_cookie(
        key=ADMIN_PENDING_COOKIE_NAME,
        path=ADMIN_PENDING_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


# ---------------------------------------------------------------------------
# 신뢰 기기 쿠키 (M1.5 B3 - "이 기기에서 2단계 인증 생략")
# ---------------------------------------------------------------------------
#
# TOTP 검증 성공 + remember_device 옵트인 시 발급. /admin/login 1단계가 유효한
# 신뢰 기기(DB trusted_devices 행)를 확인하면 TOTP 단계를 건너뛴다.
# 발급·검증 로직은 admin_auth_service 소관 - 여기는 쿠키 운반만.
#
# 서명 JWT가 아니라 opaque 원문인 이유: pending/oauth_tx는 stateless라 쿠키가 스스로
# 진위를 증명해야 하지만(서명 필수), 이 토큰은 진위 권위가 DB 행(trusted_devices)에
# 있어 조회 키 역할의 랜덤이면 충분하다. DB 행이 있어야 revoke·재등록 실효도 가능.
#
# Path=/admin: 이 쿠키를 읽는 곳은 /admin/login 하나뿐이라 노출을 최소화한다.
# SameSite=Strict: pending 쿠키와 동일 사유(admin SPA의 same-site fetch만 견디면 됨).
# 절대 만료: 발급 후 Max-Age를 갱신하는 경로를 두지 않는다(탈취 노출창 상한 고정).

TRUSTED_DEVICE_COOKIE_NAME = "admin_trusted_device"
TRUSTED_DEVICE_PATH = "/admin"


def set_trusted_device_cookie(response: Response, raw_token: str) -> None:
    """신뢰 기기 opaque 토큰 원문을 쿠키에 set. DB엔 해시만(admin_auth_service)."""
    response.set_cookie(
        key=TRUSTED_DEVICE_COOKIE_NAME,
        value=raw_token,
        max_age=settings.totp_trusted_device_days * 86400,
        path=TRUSTED_DEVICE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def clear_trusted_device_cookie(response: Response) -> None:
    """신뢰 기기 쿠키를 만료시킨다. 무효/만료 토큰 감지 시 위생 정리용."""
    response.delete_cookie(
        key=TRUSTED_DEVICE_COOKIE_NAME,
        path=TRUSTED_DEVICE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


# ---------------------------------------------------------------------------
# 현재 유저 의존성 (M1 C5 /auth/me, 후속 보호 라우트 공용)
# ---------------------------------------------------------------------------

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")


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


# ---------------------------------------------------------------------------
# role 가드 (M1.5 B3 - RBAC)
# ---------------------------------------------------------------------------

_FORBIDDEN_ROLE = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="권한이 없습니다")


def require_role(*roles: RoleEnum):
    """role 기반 접근 가드 팩토리. get_current_user 위에 합성된다.

    authz 진실 소스는 DB user.role(JWT claim 아님) - get_current_user가 이미 매 요청
    User를 로드하므로 추가 쿼리 0으로 항상 최신 role을 본다(강등 즉시 반영).
    M1.5는 require_owner만 부착, M4에서 require_role(OWNER, MODERATOR) 등으로 확장.
    """

    async def _require(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            raise _FORBIDDEN_ROLE
        # owner는 TOTP 활성이 권한의 전제. owner 세션은 발급 지점 봉쇄(B3)로 전부 TOTP
        # 통과가 보장되지만, 봉쇄가 못 덮는 잔존 세션 창 하나를 이 검사가 마저 닫는다.
        # (moderator 2FA 정책은 M4 소관 - 이 검사는 owner에만 적용되므로 영향 없음)
        # 잔존 세션 창: reader로 로그인 중 승격되면 기존 access(≤15분, stateless라 회수
        # 불가)가 owner 권한을 얻는다 - 그 시점 totp_confirmed_at은 NULL이라 여기서 막힌다.
        if current_user.role == RoleEnum.OWNER and current_user.totp_confirmed_at is None:
            raise _FORBIDDEN_ROLE
        return current_user

    return _require


require_owner = require_role(RoleEnum.OWNER)
