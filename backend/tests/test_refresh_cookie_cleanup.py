"""최종 refresh 401은 실제 응답에서 인증 쿠키를 지우고 일시 장애는 보존한다."""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.config import settings
from src.lib import auth
from src.main import app
from src.models.user import RefreshToken
from src.services import auth_service

pytestmark = pytest.mark.asyncio
REFRESH_URL = "https://test.example/auth/refresh"


def response_cookies(response):
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return cookies


@pytest.mark.parametrize("secure", [False, True])
@pytest.mark.parametrize("failure", ["missing", "malformed", "unknown", "expired", "reused"])
async def test_refresh_401_clears_all_auth_cookies(
    async_client, db_session, user, monkeypatch, secure, failure
):
    monkeypatch.setattr(settings, "env", "production" if secure else "development")
    raw = None
    if failure in {"expired", "reused"}:
        raw = await auth_service.create_refresh_token(user.id, db_session)
        await db_session.commit()
        if failure == "expired":
            record = await auth_service.get_refresh_token(raw, db_session)
            record.expires_at = datetime.now(UTC) - timedelta(days=1)
            await db_session.commit()
        else:
            # 실제 회전으로 revoked 토큰과 살아 있는 후속 토큰을 만든다.
            await auth_service.rotate_refresh(raw, db_session)
    elif failure == "malformed":
        raw = "not-a-refresh-token"
    elif failure == "unknown":
        raw = "A" * 43
    async_client.cookies.set(auth.access_cookie_name(), "stale-access", domain="test.example")
    async_client.cookies.set(auth.LOGIN_HINT_COOKIE_NAME, "stale-hint", domain="test.example")
    if raw is not None:
        async_client.cookies.set(
            auth.REFRESH_COOKIE_NAME,
            raw,
            domain="test.example",
            path=auth.REFRESH_COOKIE_PATH,
        )

    response = await async_client.post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json() == {
        "detail": (
            "세션이 만료되었습니다. 다시 로그인하세요"
            if failure == "reused"
            else "인증이 필요합니다"
        )
    }
    cookies = response_cookies(response)
    assert len(response.headers.get_list("set-cookie")) == 3
    assert set(cookies) == {
        auth.access_cookie_name(),
        auth.REFRESH_COOKIE_NAME,
        auth.LOGIN_HINT_COOKIE_NAME,
    }
    for name, cookie in cookies.items():
        assert cookie.value == ""
        assert cookie["max-age"] == "0"
        assert cookie["path"] == (
            auth.REFRESH_COOKIE_PATH if name == auth.REFRESH_COOKIE_NAME else "/"
        )
        assert bool(cookie["httponly"]) == (name != auth.LOGIN_HINT_COOKIE_NAME)
        assert bool(cookie["secure"]) == secure
        assert cookie["samesite"] == ("strict" if name == auth.REFRESH_COOKIE_NAME else "lax")
        assert cookie["domain"] == ""
    assert response.headers["cache-control"] == "no-store"
    if failure == "reused":
        records = (await db_session.exec(select(RefreshToken))).all()
        assert len(records) == 2
        assert all(record.revoked_at is not None for record in records)


@pytest.mark.parametrize("secure", [False, True])
async def test_valid_refresh_with_expired_access_rotates_without_deleting_cookies(
    async_client, db_session, user, monkeypatch, secure
):
    monkeypatch.setattr(settings, "env", "production" if secure else "development")
    raw = await auth_service.create_refresh_token(user.id, db_session)
    await db_session.commit()
    expired_access = jwt.encode(
        {
            "sub": str(user.id),
            "typ": "access",
            "exp": datetime.now(UTC) - timedelta(days=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    async_client.cookies.set(auth.access_cookie_name(), expired_access, domain="test.example")
    async_client.cookies.set(
        auth.REFRESH_COOKIE_NAME,
        raw,
        domain="test.example",
        path=auth.REFRESH_COOKIE_PATH,
    )

    response = await async_client.post(REFRESH_URL)

    assert response.status_code == 200
    assert response.json() == {"message": "토큰이 갱신되었습니다"}
    cookies = response_cookies(response)
    assert set(cookies) == {
        auth.access_cookie_name(),
        auth.REFRESH_COOKIE_NAME,
        auth.LOGIN_HINT_COOKIE_NAME,
    }
    assert all(int(cookie["max-age"]) > 0 for cookie in cookies.values())
    assert cookies[auth.REFRESH_COOKIE_NAME].value != raw
    assert auth.decode_token(cookies[auth.access_cookie_name()].value)["sub"] == str(user.id)
    assert response.headers["cache-control"] == "no-store"
    records = (await db_session.exec(select(RefreshToken))).all()
    assert len(records) == 2
    assert sum(record.revoked_at is None for record in records) == 1


async def test_transient_rotation_failure_does_not_delete_cookies(
    async_client, db_session, user, monkeypatch
):
    raw = await auth_service.create_refresh_token(user.id, db_session)
    await db_session.commit()
    monkeypatch.setattr(
        auth_service,
        "rotate_refresh",
        AsyncMock(side_effect=SQLAlchemyError("temporary failure")),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="https://test.example") as client:
        client.cookies.set(auth.REFRESH_COOKIE_NAME, raw, domain="test.example")
        response = await client.post("/auth/refresh")

    assert response.status_code == 500
    assert response.headers.get_list("set-cookie") == []
    record = await auth_service.get_refresh_token(raw, db_session)
    assert record.revoked_at is None
