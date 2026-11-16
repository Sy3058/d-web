"""계정 비밀번호 변경의 실제 HTTP·쿠키·재로그인 계약."""

from unittest.mock import AsyncMock

import pytest

from src.lib.auth import (
    ADMIN_PENDING_COOKIE_NAME,
    LOGIN_HINT_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    TRUSTED_DEVICE_COOKIE_NAME,
    access_cookie_name,
    create_access_token,
)
from src.services import hibp

pytestmark = pytest.mark.asyncio
CURRENT = "Passw0rd!"
NEW = "NewPassw0rd!2"


def _body(current=CURRENT, new=NEW, confirmation=NEW):
    return {"current_password": current, "new_password": new, "confirm_password": confirmation}


def _authenticate(client, user):
    host = client.base_url.host
    domain = host if "." in host else f"{host}.local"
    client.cookies.set(
        access_cookie_name(), create_access_token(str(user.id)), domain=domain, path="/"
    )


async def test_password_http_clears_all_cookie_scopes_and_requires_new_login(
    async_client, existing_user
):
    _authenticate(async_client, existing_user)
    response = await async_client.post("/auth/me/password", json=_body())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    for name in (
        access_cookie_name(),
        REFRESH_COOKIE_NAME,
        LOGIN_HINT_COOKIE_NAME,
        ADMIN_PENDING_COOKIE_NAME,
        TRUSTED_DEVICE_COOKIE_NAME,
    ):
        assert any(header.startswith(name + "=") and "Max-Age=0" in header for header in cookies)
    assert CURRENT not in response.text and NEW not in response.text
    assert (await async_client.get("/auth/me")).status_code == 401
    old = await async_client.post(
        "/auth/login", json={"email": existing_user.email, "password": CURRENT}
    )
    assert old.status_code == 401
    fresh = await async_client.post(
        "/auth/login", json={"email": existing_user.email, "password": NEW}
    )
    assert fresh.status_code == 200
    assert fresh.json()["has_password"] is True
    assert "hashed_password" not in fresh.json()


@pytest.mark.parametrize("case,status", [("wrong", 400), ("pwned", 422), ("oauth", 409)])
async def test_password_http_rejection_preserves_login(
    async_client, existing_user, db_session, monkeypatch, case, status
):
    if case == "oauth":
        existing_user.hashed_password = None
        db_session.add(existing_user)
        await db_session.commit()
    if case == "pwned":
        monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=True))
    _authenticate(async_client, existing_user)
    response = await async_client.post(
        "/auth/me/password", json=_body(current="wrong-password" if case == "wrong" else CURRENT)
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert not response.headers.get_list("set-cookie")
    assert CURRENT not in response.text and NEW not in response.text
    me = await async_client.get("/auth/me")
    assert me.status_code == 200
    assert me.headers["cache-control"] == "no-store"


async def test_password_http_requires_authentication_and_does_not_echo_body(async_client):
    response = await async_client.post("/auth/me/password", json=_body())
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert CURRENT not in response.text and NEW not in response.text
