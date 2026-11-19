"""계정 비밀번호 변경의 실제 HTTP·쿠키·세션 계약."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from scripts.promote_admin import promote_user
from src.lib.auth import (
    LOGIN_HINT_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    access_cookie_name,
    create_access_token,
)
from src.lib.db import get_session
from src.main import app
from src.models.user import RefreshToken, RoleEnum, User
from src.services import account_password_service, auth_service, hibp
from tests.conftest import EXISTING_USER_PASSWORD

pytestmark = pytest.mark.asyncio
CURRENT = EXISTING_USER_PASSWORD
NEW = "NewPassw0rd!2"


def _body(current=CURRENT, new=NEW, confirmation=NEW):
    return {"current_password": current, "new_password": new, "confirm_password": confirmation}


def _authenticate(client, user):
    host = client.base_url.host
    domain = host if "." in host else f"{host}.local"
    client.cookies.set(
        access_cookie_name(), create_access_token(str(user.id)), domain=domain, path="/"
    )


async def test_password_http_keeps_current_session_and_ends_other_refresh_sessions(
    async_client, existing_user
):
    login = {"email": existing_user.email, "password": CURRENT}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=async_client.base_url) as other:
        assert (await async_client.post("/auth/login", json=login)).status_code == 200
        assert (await other.post("/auth/login", json=login)).status_code == 200
        old_refresh = async_client.cookies.get(REFRESH_COOKIE_NAME)
        assert old_refresh and other.cookies.get(REFRESH_COOKIE_NAME)

        response = await async_client.post("/auth/me/password", json=_body())
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"message": "비밀번호가 변경되었습니다"}
        new_refresh = async_client.cookies.get(REFRESH_COOKIE_NAME)
        assert new_refresh and new_refresh != old_refresh
        assert async_client.cookies.get(LOGIN_HINT_COOKIE_NAME) == existing_user.nickname
        assert (await async_client.get("/auth/me")).status_code == 200

        assert (await other.post("/auth/refresh")).status_code == 401
        assert other.cookies.get(REFRESH_COOKIE_NAME) is None
        assert (await async_client.post("/auth/refresh")).status_code == 200
        assert async_client.cookies.get(REFRESH_COOKIE_NAME) != new_refresh
        assert (await async_client.get("/auth/me")).status_code == 200

        assert (await other.post("/auth/login", json=login)).status_code == 401
        fresh = await other.post("/auth/login", json={**login, "password": NEW})
        assert fresh.status_code == 200
        assert fresh.json()["has_password"] is True
        assert "hashed_password" not in fresh.json()


async def test_late_refresh_failure_does_not_clear_password_change_cookies(
    db_session, existing_user, session_factory, monkeypatch
):
    old_refresh = await auth_service.create_refresh_token(existing_user.id, db_session)
    await db_session.commit()
    await auth_service.rotate_refresh(old_refresh, db_session)
    old_deleted, old_read, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    revoke_trusted = account_password_service.revoke_trusted_devices
    read_refresh = auth_service.get_refresh_token

    async def pause_after_delete(user_id, session):
        old_deleted.set()
        await release.wait()
        await revoke_trusted(user_id, session)

    async def read_old_refresh(raw, session):
        record = await read_refresh(raw, session)
        if raw == old_refresh:
            assert record is not None and record.revoked_at is not None
            old_read.set()
        return record

    async def independent_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(account_password_service, "revoke_trusted_devices", pause_after_delete)
    monkeypatch.setattr(auth_service, "get_refresh_token", read_old_refresh)
    monkeypatch.setitem(app.dependency_overrides, get_session, independent_session)

    transport = ASGITransport(app=app)
    base_url = "https://test.example"
    async with (
        AsyncClient(transport=transport, base_url=base_url) as current,
        AsyncClient(transport=transport, base_url=base_url) as stale,
    ):
        _authenticate(current, existing_user)
        stale.cookies.set(
            REFRESH_COOKIE_NAME, old_refresh, domain="test.example", path=REFRESH_COOKIE_PATH
        )
        async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
            change = tasks.create_task(current.post("/auth/me/password", json=_body()))
            await old_deleted.wait()
            refresh = tasks.create_task(stale.post("/auth/refresh"))
            await old_read.wait()
            release.set()

        assert change.result().status_code == 200
        late = refresh.result()
        assert late.status_code == 401
        assert late.headers.get_list("set-cookie") == []
        current.cookies.extract_cookies(late)
        assert (await current.get("/auth/me")).status_code == 200
        assert (await current.post("/auth/refresh")).status_code == 200


async def test_password_http_rejects_user_promoted_while_request_waits_for_lock(
    async_client, db_session, existing_user, session_factory, monkeypatch
):
    user_id, email, old_hash = existing_user.id, existing_user.email, existing_user.hashed_password
    existing_user.is_email_verified = True
    await db_session.commit()
    login = await async_client.post("/auth/login", json={"email": email, "password": CURRENT})
    assert login.status_code == 200
    old_refresh = async_client.cookies.get(REFRESH_COOKIE_NAME)
    waiting, proceed = asyncio.Event(), asyncio.Event()
    lock_user = auth_service.lock_user

    async def pause_request_lock(user_id, session):
        if session is db_session:
            waiting.set()
            await proceed.wait()
        return await lock_user(user_id, session)

    monkeypatch.setattr(auth_service, "lock_user", pause_request_lock)
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        change = tasks.create_task(async_client.post("/auth/me/password", json=_body()))
        await waiting.wait()
        async with session_factory() as session:
            assert await promote_user(email, session) == "promoted"
        proceed.set()

    response = change.result()
    assert response.status_code == 403
    assert response.headers.get_list("set-cookie") == []
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user.role == RoleEnum.OWNER
        assert user.hashed_password == old_hash
        refresh = (await session.exec(select(RefreshToken))).one()
        assert refresh.token_hash == auth_service._hash_token(old_refresh)
        assert refresh.revoked_at is not None


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
