"""구글 OAuth 로그인 통합 테스트 (M1 D1).

외부 호출(구글 코드 교환·id_token 검증)은 목으로 막고 라우터 + resolve_google_user의
DB 로직을 검증한다. 실제 흐름을 흉내 내기 위해 /auth/login/google로 oauth_tx 쿠키와 state를
먼저 받고, 그 state로 콜백을 친다(쿠키는 async_client jar가 자동 운반).
"""

import urllib.parse
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.exceptions import OAuthExchangeError
from src.models.user import OAuthAccount, User
from src.services import oauth_service
from src.services.oauth_service import GoogleClaims


async def _login_get_state(client: AsyncClient) -> str:
    """/auth/login/google를 쳐서 oauth_tx 쿠키를 jar에 심고 state를 돌려준다."""
    resp = await client.get("/auth/login/google", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    return params["state"][0]


def _mock_google(claims: GoogleClaims):
    """exchange_code/verify_id_token를 목으로 교체하는 컨텍스트매니저 쌍을 반환."""
    return (
        patch.object(oauth_service, "exchange_code", AsyncMock(return_value="fake.jwt")),
        patch.object(oauth_service, "verify_id_token", AsyncMock(return_value=claims)),
    )


async def test_login_redirects_to_google_and_sets_tx_cookie(async_client: AsyncClient):
    resp = await async_client.get("/auth/login/google", follow_redirects=False)

    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile"]
    assert query["redirect_uri"] == [settings.google_redirect_uri]
    assert "state" in query and "nonce" in query
    assert resp.cookies.get("oauth_tx") is not None


async def test_callback_creates_new_user(async_client: AsyncClient, db_session: AsyncSession):
    state = await _login_get_state(async_client)
    claims = GoogleClaims(
        sub="google-sub-new", email="New@Example.com", email_verified=True, name="새 유저"
    )
    exchange, verify = _mock_google(claims)
    with exchange, verify:
        resp = await async_client.get(
            f"/auth/callback/google?code=abc&state={state}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == settings.app_base_url
    assert resp.cookies.get("access_token")
    assert resp.cookies.get("refresh_token")

    user = (await db_session.exec(select(User).where(User.email == "new@example.com"))).first()
    assert user is not None
    assert user.hashed_password is None  # 소셜 전용 계정
    assert user.is_email_verified is True
    assert user.nickname == "새 유저"

    account = (
        await db_session.exec(
            select(OAuthAccount).where(OAuthAccount.provider_id == "google-sub-new")
        )
    ).first()
    assert account is not None
    assert account.provider == "google"
    assert account.user_id == user.id


async def test_callback_existing_account_logs_in(
    async_client: AsyncClient, db_session: AsyncSession
):
    user = User(email="social@example.com", nickname="소셜", is_email_verified=True)
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        OAuthAccount(user_id=user.id, provider="google", provider_id="google-sub-existing")
    )
    await db_session.commit()

    state = await _login_get_state(async_client)
    claims = GoogleClaims(
        sub="google-sub-existing", email="social@example.com", email_verified=True, name="소셜"
    )
    exchange, verify = _mock_google(claims)
    with exchange, verify:
        resp = await async_client.get(
            f"/auth/callback/google?code=abc&state={state}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == settings.app_base_url
    assert resp.cookies.get("access_token")

    users = (await db_session.exec(select(User).where(User.email == "social@example.com"))).all()
    assert len(users) == 1  # 중복 생성 없음
    accounts = (
        await db_session.exec(
            select(OAuthAccount).where(OAuthAccount.provider_id == "google-sub-existing")
        )
    ).all()
    assert len(accounts) == 1


async def test_callback_email_exists_rejected(async_client: AsyncClient, existing_user: User):
    # existing_user는 같은 이메일의 비-소셜(비번) 계정 -> 자동 병합 금지(Q6).
    state = await _login_get_state(async_client)
    claims = GoogleClaims(
        sub="google-sub-clash", email=existing_user.email, email_verified=True, name="x"
    )
    exchange, verify = _mock_google(claims)
    with exchange, verify:
        resp = await async_client.get(
            f"/auth/callback/google?code=abc&state={state}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert "error=email_exists" in resp.headers["location"]
    assert resp.cookies.get("access_token") is None


async def test_callback_email_unverified_rejected(
    async_client: AsyncClient, db_session: AsyncSession
):
    # 로그인 성공(계정 소유 증명)해도 구글이 이메일 소유를 검증 못 한(email_verified=false)
    # 신규 계정은 가입 거부 -> generic oauth_failed. 도용 위험 차단.
    state = await _login_get_state(async_client)
    claims = GoogleClaims(
        sub="google-sub-unverified",
        email="unverified@example.com",
        email_verified=False,
        name="미검증",
    )
    exchange, verify = _mock_google(claims)
    with exchange, verify:
        resp = await async_client.get(
            f"/auth/callback/google?code=abc&state={state}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["location"]
    assert resp.cookies.get("access_token") is None

    # 유저/계정 모두 생성되지 않아야 한다.
    user = (
        await db_session.exec(select(User).where(User.email == "unverified@example.com"))
    ).first()
    assert user is None
    account = (
        await db_session.exec(
            select(OAuthAccount).where(OAuthAccount.provider_id == "google-sub-unverified")
        )
    ).first()
    assert account is None


async def test_callback_state_mismatch(async_client: AsyncClient):
    await _login_get_state(async_client)  # oauth_tx 쿠키는 심되, 다른 state로 친다
    resp = await async_client.get(
        "/auth/callback/google?code=abc&state=tampered", follow_redirects=False
    )

    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["location"]
    assert resp.cookies.get("access_token") is None


async def test_callback_without_tx_cookie(async_client: AsyncClient):
    # 로그인 시작 없이 콜백 직행 -> oauth_tx 없음 -> CSRF 차단.
    resp = await async_client.get(
        "/auth/callback/google?code=abc&state=whatever", follow_redirects=False
    )

    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["location"]


async def test_callback_verify_failure(async_client: AsyncClient):
    state = await _login_get_state(async_client)
    with (
        patch.object(oauth_service, "exchange_code", AsyncMock(return_value="fake.jwt")),
        patch.object(oauth_service, "verify_id_token", AsyncMock(side_effect=OAuthExchangeError())),
    ):
        resp = await async_client.get(
            f"/auth/callback/google?code=abc&state={state}", follow_redirects=False
        )

    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["location"]
    assert resp.cookies.get("access_token") is None


async def test_callback_user_consent_denied(async_client: AsyncClient):
    state = await _login_get_state(async_client)
    # 구글이 error=access_denied로 콜백 -> generic oauth_failed.
    resp = await async_client.get(
        f"/auth/callback/google?error=access_denied&state={state}", follow_redirects=False
    )

    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["location"]


async def test_resolve_race_recovers_to_login(db_session: AsyncSession):
    # 동시 콜백 경합: 우리 select 이후·flush 이전에 다른 요청이 같은 sub로 가입을 끝낸 상황.
    # get_user_by_email 호출 시점에 승자(User+OAuthAccount)를 커밋해 주입하면, 우리 flush가
    # email unique로 IntegrityError -> rollback -> 승자 레코드로 재조회해 로그인 회복해야 한다.
    claims = GoogleClaims(
        sub="race-sub", email="race@example.com", email_verified=True, name="경합"
    )

    async def _seed_winner_then_none(email: str, session: AsyncSession):
        winner = User(email="race@example.com", nickname="승자", is_email_verified=True)
        session.add(winner)
        await session.flush()
        session.add(OAuthAccount(user_id=winner.id, provider="google", provider_id="race-sub"))
        await session.commit()
        return None  # 우리 트랜잭션 시점엔 아직 안 보였다고 가정

    with patch.object(oauth_service, "get_user_by_email", side_effect=_seed_winner_then_none):
        user, access, refresh = await oauth_service.resolve_google_user(claims, db_session)

    assert access and refresh
    # 중복 생성 없이 승자 1명만, 그 유저로 로그인됐다.
    users = (await db_session.exec(select(User).where(User.email == "race@example.com"))).all()
    assert len(users) == 1
    assert user.id == users[0].id
    accounts = (
        await db_session.exec(select(OAuthAccount).where(OAuthAccount.provider_id == "race-sub"))
    ).all()
    assert len(accounts) == 1
