"""구글 OAuth/OIDC 로그인 (M1 D1).

authorization code flow를 백엔드가 받는 BFF 표준을 따른다(공식 문서:
identity/protocols/oauth2/web-server, identity/openid-connect/openid-connect):

  1) /auth/login/google 에서 state(CSRF)·nonce(replay) 생성 후 구글 authorize로 302
  2) 구글이 /auth/callback/google 로 code를 반환
  3) 백엔드가 code를 토큰 엔드포인트에서 교환 -> id_token(JWT) 획득
  4) google-auth로 id_token 서명/aud/iss/exp 검증, nonce는 라이브러리가 안 보므로 수동 대조
  5) sub로 OAuthAccount 조회 -> 기존 유저 / 신규 생성(자동 병합 금지, DB_SCHEMA Q6)
  6) access·refresh 발급(쿠키 set은 호출자 router)

코드 교환은 우리 서버가 client_secret으로 TLS 직접 수행하지만, 공식 권장대로 id_token 서명은
공개키(JWKS)로 로컬 검증한다. JWKS fetch는 sync 네트워크라 anyio.to_thread로 오프로드한다
(이벤트 루프 비블로킹). transport는 이미 설치된 urllib3 기반(requests 의존 회피).
"""

import urllib.parse
from datetime import UTC, datetime

import certifi
import httpx
import structlog
import urllib3
from anyio import to_thread
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import urllib3 as google_auth_urllib3
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import create_access_token
from src.lib.exceptions import OAuthEmailExistsError, OAuthExchangeError
from src.models.user import OAuthAccount, User
from src.services.auth_service import (
    _normalize_email,
    create_refresh_token,
    get_user_by_email,
    requires_totp_login,
)

logger = structlog.get_logger(__name__)

_PROVIDER = "google"
_AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_SCOPE = "openid email profile"
_TIMEOUT_SECONDS = 5.0

# id_token 검증용 google-auth transport. JWKS(공개키)를 가져온다. PoolManager는 비용이 있어
# 모듈 로드 시 1회 생성(네트워크는 첫 검증 때 발생, 루프 없는 import 시점이라 무해).
# certifi CA 명시 + 타임아웃으로 무한 대기 차단.
_http = urllib3.PoolManager(
    cert_reqs="CERT_REQUIRED",
    ca_certs=certifi.where(),
    timeout=urllib3.Timeout(total=_TIMEOUT_SECONDS),
)
_google_request = google_auth_urllib3.Request(_http)


class GoogleClaims(BaseModel):
    """검증을 통과한 id_token에서 뽑은 최소 필드."""

    sub: str
    email: str
    email_verified: bool
    name: str | None = None


def build_google_authorize_url(state: str, nonce: str) -> str:
    """구글 동의 화면 URL 생성. response_type=code (authorization code flow).

    access_type=offline은 구글 API 지속 호출용 refresh를 받을 때만 필요 - 로그인엔 불필요해
    생략한다. nonce는 OIDC replay 방어용으로 id_token에 그대로 담겨 돌아온다.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return f"{_AUTHORIZE_ENDPOINT}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> str:
    """authorization code를 토큰 엔드포인트에서 교환하고 id_token(JWT 문자열)을 반환한다.

    교환은 client_secret이 필요해 서버측에서만 가능(컨피덴셜 클라이언트). 외부 호출 실패·
    비정상 응답은 OAuthExchangeError로 통일(콜백에서 generic 302). hibp.py 비동기 httpx 패턴.
    """
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_TOKEN_ENDPOINT, data=data)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        # 토큰 엔드포인트 4xx/5xx. 실패 원인(invalid_grant, redirect_uri_mismatch 등)은
        # 응답 바디에 담겨오므로 함께 남긴다. 바디에 secret/PII는 없다.
        logger.info(
            "auth.oauth",
            provider=_PROVIDER,
            outcome="exchange_failed",
            status=exc.response.status_code,
            body=exc.response.text,
        )
        raise OAuthExchangeError from exc
    except httpx.HTTPError as exc:
        logger.info("auth.oauth", provider=_PROVIDER, outcome="exchange_failed", error=str(exc))
        raise OAuthExchangeError from exc

    id_token_str = body.get("id_token")
    if not id_token_str:
        logger.info("auth.oauth", provider=_PROVIDER, outcome="no_id_token")
        raise OAuthExchangeError
    return id_token_str


def _verify_id_token_sync(id_token_str: str) -> dict:
    """google-auth로 id_token 검증(서명/aud/iss/exp). 동기 - to_thread로 오프로드한다.

    verify_oauth2_token이 JWKS로 서명을 검증하고, audience로 aud를, 내부적으로 iss/exp를
    검증한다(iss는 accounts.google.com / https://accounts.google.com 둘 다 허용). nonce는
    검증하지 않으므로 호출자가 따로 대조한다. clock_skew로 소폭의 시계 오차를 허용한다.
    """
    return google_id_token.verify_oauth2_token(
        id_token_str,
        _google_request,
        audience=settings.google_client_id,
        clock_skew_in_seconds=10,
    )


async def verify_id_token(id_token_str: str, expected_nonce: str) -> GoogleClaims:
    """id_token을 검증하고 GoogleClaims를 반환한다. 검증 실패/nonce 불일치 시 OAuthExchangeError."""
    try:
        idinfo = await to_thread.run_sync(_verify_id_token_sync, id_token_str)
    except (ValueError, GoogleAuthError) as exc:
        logger.info("auth.oauth", provider=_PROVIDER, outcome="verify_failed", error=str(exc))
        raise OAuthExchangeError from exc

    # nonce 수동 대조(replay 방어). 라이브러리는 nonce를 검증하지 않는다.
    if idinfo.get("nonce") != expected_nonce:
        logger.info("auth.oauth", provider=_PROVIDER, outcome="nonce_mismatch")
        raise OAuthExchangeError

    sub = idinfo.get("sub")
    email = idinfo.get("email")
    if not sub or not email:
        raise OAuthExchangeError

    return GoogleClaims(
        sub=sub,
        email=email,
        email_verified=bool(idinfo.get("email_verified", False)),
        name=idinfo.get("name"),
    )


def _nickname_from(claims: GoogleClaims, email: str) -> str:
    """닉네임 후보: 구글 name이 있으면 그것을, 없으면 이메일 local part. 50자 상한(컬럼 제약)."""
    if claims.name and claims.name.strip():
        return claims.name.strip()[:50]
    return email.split("@", 1)[0][:50]


async def _issue_session(user: User, session: AsyncSession, outcome: str) -> tuple[User, str, str]:
    """확정된 유저에게 access·refresh 발급 + commit + 관측 로그. (login/signup/경합회복 공통)

    owner 봉쇄(M1.5 B3): OAuth의 모든 세션 발급이 이 관문을 지나므로 여기 한 곳의 판정이
    로그인·가입·경합회복 세 경로를 전부 덮는다. 신규 가입은 role=reader 기본값이라 실제로는
    기존 owner의 소셜 로그인만 걸린다(promote 스크립트의 비번 보유 검사와 방어심도 이중).
    """
    if requires_totp_login(user):
        logger.info("auth.oauth", provider=_PROVIDER, outcome="owner_blocked", user_id=str(user.id))
        raise OAuthExchangeError
    access = create_access_token(str(user.id))
    refresh = await create_refresh_token(user.id, session)
    await session.commit()
    logger.info("auth.oauth", provider=_PROVIDER, outcome=outcome, user_id=str(user.id))
    return user, access, refresh


async def resolve_google_user(claims: GoogleClaims, session: AsyncSession) -> tuple[User, str, str]:
    """구글 claims로 유저를 확정하고 (user, access, refresh)를 반환한다.

    1) (provider, sub)로 OAuthAccount 조회 -> 있으면 기존 소셜 유저.
    2) 없으면 같은 이메일의 유저 조회 -> 있으면 OAuthEmailExistsError(자동 병합 금지, Q6).
    3) email_verified=false면 가입 거부(구글이 이메일 소유를 보장 못 함 -> 도용 위험).
    4) 없으면 User(비번 NULL) + OAuthAccount를 한 트랜잭션으로 생성.

    select-then-insert는 동시 콜백에서 경합하므로 IntegrityError를 잡아 승자 레코드로
    회복한다(DB unique 제약이 최종 권위). commit은 이 서비스가 잡는다(login/signup과 동일).
    """
    result = await session.exec(
        select(OAuthAccount).where(
            OAuthAccount.provider == _PROVIDER,
            OAuthAccount.provider_id == claims.sub,
        )
    )
    account = result.first()
    if account is not None:
        user = await session.get(User, account.user_id)
        if user is None or user.deleted_at is not None:
            # FK상 거의 불가하나 탈퇴/정합성 깨짐이면 로그인 거부.
            raise OAuthExchangeError
        return await _issue_session(user, session, "login")

    email = _normalize_email(claims.email)
    if await get_user_by_email(email, session) is not None:
        # 같은 이메일의 비-소셜(또는 다른 provider) 계정 존재 -> 자동 병합은 계정 탈취 벡터라 거부.
        raise OAuthEmailExistsError

    if not claims.email_verified:
        # 로그인 성공(계정 소유 증명) != 이메일 검증. 외부 IdP 페더레이션 등으로 구글이 이메일
        # 소유를 검증 못 한 계정은 도용 위험이라 신규 가입을 막는다(기존 유저는 위에서 이미 분기).
        logger.info("auth.oauth", provider=_PROVIDER, outcome="email_unverified")
        raise OAuthExchangeError

    user = User(
        email=email,
        hashed_password=None,
        nickname=_nickname_from(claims, email),
        is_email_verified=True,  # 위 가드로 email_verified=true만 도달
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.flush()  # user.id 확보 + email unique 위반 조기 감지
        session.add(OAuthAccount(user_id=user.id, provider=_PROVIDER, provider_id=claims.sub))
        return await _issue_session(user, session, "signup")
    except IntegrityError:
        # 동시 콜백 경합: 다른 요청이 같은 sub로 먼저 가입을 완료(DB unique 제약이 권위).
        # 롤백 후 승자 레코드로 재조회해 로그인으로 회복한다.
        await session.rollback()
        result = await session.exec(
            select(OAuthAccount).where(
                OAuthAccount.provider == _PROVIDER,
                OAuthAccount.provider_id == claims.sub,
            )
        )
        account = result.first()
        if account is None:
            # email unique로 깨졌으나 sub 매칭이 없으면(같은 이메일 다른 경로) 회복 불가.
            raise OAuthExchangeError from None
        user = await session.get(User, account.user_id)
        if user is None or user.deleted_at is not None:
            raise OAuthExchangeError from None
        return await _issue_session(user, session, "login")
