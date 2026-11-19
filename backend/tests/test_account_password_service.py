"""비밀번호 변경의 원자성, 자격 증명 재검증과 인증 발급 경합 회귀."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import jwt
import pyotp
import pytest
from sqlmodel import select

from src.config import settings
from src.lib import auth, totp
from src.lib.exceptions import (
    InvalidCredentialsError,
    PwnedPasswordError,
    RefreshRotationConflictError,
)
from src.models.user import RefreshToken, RoleEnum, TrustedDevice, User
from src.services import account_password_service as passwords
from src.services import admin_auth_service, auth_service, hibp
from tests.conftest import EXISTING_USER_PASSWORD

pytestmark = pytest.mark.asyncio
NEW_PASSWORD = "Changed-Passw0rd!"


async def _replace_password_fixture(user_id, session):
    new_hash = await auth_service.hash_password(NEW_PASSWORD)
    user = await auth_service.lock_user(user_id, session)
    user.hashed_password = new_hash
    await session.commit()


async def test_password_change_replaces_refresh_sessions(db_session, existing_user):
    raw_tokens = [
        await auth_service.create_refresh_token(existing_user.id, db_session) for _ in range(2)
    ]
    await auth_service.revoke_refresh_token(
        await auth_service.get_refresh_token(raw_tokens[0], db_session), db_session
    )
    trusted = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    access = auth.create_access_token(str(existing_user.id))

    user, new_access, new_refresh = await passwords.change_password(
        existing_user.id, EXISTING_USER_PASSWORD, NEW_PASSWORD, db_session
    )

    await db_session.refresh(existing_user)
    assert await auth_service.verify_password(NEW_PASSWORD, existing_user.hashed_password)
    assert not await auth_service.verify_password(
        EXISTING_USER_PASSWORD, existing_user.hashed_password
    )
    for raw in raw_tokens:
        assert await auth_service.get_refresh_token(raw, db_session) is None
    assert user.id == existing_user.id
    assert auth.decode_token(new_access)["sub"] == str(user.id)
    current = (await db_session.exec(select(RefreshToken))).one()
    assert current.token_hash == auth_service._hash_token(new_refresh)
    assert current.revoked_at is None
    device = (
        await db_session.exec(
            select(TrustedDevice).where(
                TrustedDevice.token_hash == auth_service._hash_token(trusted)
            )
        )
    ).one()
    assert device.revoked_at is not None
    # 기존 stateless access는 만료까지 유효하다. 전체 access 즉시 폐기를 주장하지 않는다.
    assert auth.decode_token(access)["sub"] == str(existing_user.id)


@pytest.mark.parametrize("case", ["wrong", "pwned", "same", "weak", "oauth", "owner"])
async def test_rejected_password_change_preserves_credentials(
    db_session, existing_user, monkeypatch, case
):
    user_id, old_hash = existing_user.id, existing_user.hashed_password
    current, replacement = EXISTING_USER_PASSWORD, NEW_PASSWORD
    expected = passwords.CurrentPasswordMismatchError
    if case == "wrong":
        current = "Incorrect-Passw0rd!"
    elif case == "pwned":
        monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=True))
        expected = PwnedPasswordError
    elif case == "same":
        replacement = current
        expected = passwords.PasswordChangeNotAllowedError
    elif case == "weak":
        replacement = "allletters"
        expected = ValueError
    elif case == "owner":
        existing_user.role = RoleEnum.OWNER
        expected = passwords.PasswordChangeNotAllowedError
    else:
        existing_user.hashed_password = None
        old_hash = None
        await db_session.commit()
        expected = passwords.PasswordChangeNotAllowedError
    raw = await auth_service.create_refresh_token(existing_user.id, db_session)
    await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()

    with pytest.raises(expected) as rejected:
        await passwords.change_password(existing_user.id, current, replacement, db_session)
    if case == "owner":
        assert rejected.value.status_code == 403
    await db_session.rollback()
    fresh = await db_session.get(User, user_id)
    assert fresh.hashed_password == old_hash
    refresh = (await db_session.exec(select(RefreshToken))).one()
    assert refresh.token_hash == auth_service._hash_token(raw)
    assert refresh.revoked_at is None
    assert (await db_session.exec(select(TrustedDevice))).one().revoked_at is None


@pytest.mark.parametrize("failure", ["trusted", "refresh", "commit"])
async def test_password_change_rolls_back_all_writes(
    db_session, existing_user, monkeypatch, failure
):
    user_id, old_hash = existing_user.id, existing_user.hashed_password
    raw = await auth_service.create_refresh_token(user_id, db_session)
    await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    fail = AsyncMock(side_effect=RuntimeError)
    if failure == "trusted":
        monkeypatch.setattr(passwords, "revoke_trusted_devices", fail)
    elif failure == "refresh":
        monkeypatch.setattr(auth_service, "create_refresh_token", fail)
    else:
        monkeypatch.setattr(db_session, "commit", fail)

    with pytest.raises(RuntimeError):
        await passwords.change_password(user_id, EXISTING_USER_PASSWORD, NEW_PASSWORD, db_session)
    assert not db_session.in_transaction()
    assert (await db_session.get(User, user_id)).hashed_password == old_hash
    current = (await db_session.exec(select(RefreshToken))).one()
    assert current.token_hash == auth_service._hash_token(raw)
    assert current.revoked_at is None
    assert (await db_session.exec(select(TrustedDevice))).one().revoked_at is None


@pytest.mark.parametrize("first", ["refresh", "password"])
async def test_refresh_password_race_preserves_new_session(
    db_session, existing_user, session_factory, monkeypatch, first
):
    user_id = existing_user.id
    raw = await auth_service.create_refresh_token(user_id, db_session)
    await db_session.commit()
    first_locked, second_waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_lock = auth_service.lock_user

    async def controlled_lock(user_id, session):
        name = asyncio.current_task().get_name()
        if name != first:
            second_waiting.set()
        user = await real_lock(user_id, session)
        if name == first:
            first_locked.set()
            await release.wait()
        return user

    monkeypatch.setattr(auth_service, "lock_user", controlled_lock)

    async def operation(name):
        async with session_factory() as session:
            try:
                if name == "refresh":
                    return await auth_service.rotate_refresh(raw, session)
                return await passwords.change_password(
                    user_id, EXISTING_USER_PASSWORD, NEW_PASSWORD, session
                )
            except RefreshRotationConflictError as exc:
                return exc

    first_task = asyncio.create_task(operation(first), name=first)
    await asyncio.wait_for(first_locked.wait(), 10)
    second = "password" if first == "refresh" else "refresh"
    second_task = asyncio.create_task(operation(second), name=second)
    try:
        await asyncio.wait_for(second_waiting.wait(), 10)
    finally:
        release.set()
    results = await asyncio.wait_for(asyncio.gather(first_task, second_task), 10)
    if first == "password":
        assert isinstance(results[1], RefreshRotationConflictError)
        _, _, new_refresh = results[0]
    else:
        _, _, rotated_refresh = results[0]
        _, _, new_refresh = results[1]
    async with session_factory() as session:
        assert await auth_service.get_refresh_token(raw, session) is None
        if first == "refresh":
            assert await auth_service.get_refresh_token(rotated_refresh, session) is None
        token = (await session.exec(select(RefreshToken))).one()
        assert token.token_hash == auth_service._hash_token(new_refresh)
        assert token.revoked_at is None
        user = await session.get(User, user_id)
        assert await auth_service.verify_password(NEW_PASSWORD, user.hashed_password)


@pytest.mark.parametrize("owner", [False, True])
async def test_login_rechecks_password_changed_after_initial_verify(
    db_session, existing_user, session_factory, monkeypatch, owner
):
    user_id, email = existing_user.id, existing_user.email
    if owner:
        existing_user.role = RoleEnum.OWNER
        await db_session.commit()
    initial_verified, resume = asyncio.Event(), asyncio.Event()
    real_verify = auth_service.verify_password

    async def verify_then_pause(plain, hashed):
        valid = await real_verify(plain, hashed)
        if asyncio.current_task().get_name() == "old-login" and not initial_verified.is_set():
            initial_verified.set()
            await resume.wait()
        return valid

    monkeypatch.setattr(auth_service, "verify_password", verify_then_pause)
    monkeypatch.setattr(admin_auth_service, "verify_password", verify_then_pause)

    async def old_login():
        async with session_factory() as session:
            method = admin_auth_service.authenticate_owner if owner else auth_service.login
            with pytest.raises(InvalidCredentialsError):
                await method(email, EXISTING_USER_PASSWORD, session)

    task = asyncio.create_task(old_login(), name="old-login")
    await asyncio.wait_for(initial_verified.wait(), 10)
    try:
        async with session_factory() as session:
            if owner:
                await _replace_password_fixture(user_id, session)
            else:
                _, _, new_refresh = await passwords.change_password(
                    user_id, EXISTING_USER_PASSWORD, NEW_PASSWORD, session
                )
    finally:
        resume.set()
    await asyncio.wait_for(task, 10)
    async with session_factory() as session:
        tokens = (await session.exec(select(RefreshToken))).all()
        if owner:
            assert tokens == []
        else:
            assert len(tokens) == 1
            assert tokens[0].token_hash == auth_service._hash_token(new_refresh)
            assert tokens[0].revoked_at is None


async def test_pending_before_password_change_cannot_open_session(
    async_client, db_session, existing_user
):
    existing_user.role = RoleEnum.OWNER
    secret = pyotp.random_base32()
    existing_user.totp_secret = totp.encrypt_secret(secret)
    existing_user.totp_confirmed_at = datetime.now(UTC)
    await db_session.commit()
    pending = auth.create_admin_pending_token(
        str(existing_user.id), auth.TOTP_PENDING, existing_user.hashed_password
    )
    await _replace_password_fixture(existing_user.id, db_session)
    async_client.cookies.set(
        auth.ADMIN_PENDING_COOKIE_NAME, pending, domain="test.example", path="/admin"
    )
    response = await async_client.post("/admin/login/totp", json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 401
    assert auth.access_cookie_name() not in response.cookies
    assert (await db_session.exec(select(RefreshToken))).all() == []


async def test_legacy_pending_is_rejected(async_client, existing_user):
    pending = jwt.encode(
        {"sub": str(existing_user.id), "typ": auth.TOTP_SETUP_PENDING},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    async_client.cookies.set(
        auth.ADMIN_PENDING_COOKIE_NAME, pending, domain="test.example", path="/admin"
    )
    response = await async_client.post("/admin/2fa/setup")
    assert response.status_code == 401


@pytest.mark.parametrize("session_kind", ["login", "trusted", "pending"])
async def test_password_change_race_replaces_reader_session_and_preserves_owner_session(
    db_session, existing_user, session_factory, monkeypatch, session_kind
):
    user_id, email, old_hash = existing_user.id, existing_user.email, existing_user.hashed_password
    secret = pyotp.random_base32()
    if session_kind != "login":
        existing_user.role = RoleEnum.OWNER
        existing_user.totp_secret = totp.encrypt_secret(secret)
        existing_user.totp_confirmed_at = datetime.now(UTC)
        await db_session.commit()
    trusted = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    first_locked, password_waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_lock = auth_service.lock_user

    async def controlled_lock(user_id, session):
        name = asyncio.current_task().get_name()
        if name == "password-change":
            password_waiting.set()
        user = await real_lock(user_id, session)
        if name == "session-first":
            first_locked.set()
            await release.wait()
        return user

    monkeypatch.setattr(auth_service, "lock_user", controlled_lock)
    monkeypatch.setattr(admin_auth_service, "lock_user", controlled_lock)

    async def issue_session():
        async with session_factory() as session:
            if session_kind == "login":
                _, _, refresh = await auth_service.login(email, EXISTING_USER_PASSWORD, session)
                return refresh
            if session_kind == "trusted":
                user = await admin_auth_service.authenticate_owner(
                    email, EXISTING_USER_PASSWORD, session
                )
                assert await admin_auth_service.verify_trusted_device(user, trusted, session)
                _, refresh = await admin_auth_service.issue_trusted_session(user, session)
                return refresh
            # 실제 pending 소비자는 최신 User를 잠근 뒤 credential tag를 검증한다.
            user = await auth_service.lock_user(user_id, session)
            tokens = await admin_auth_service.login_totp(
                user, pyotp.TOTP(secret).now(), session, remember_device=True
            )
            assert tokens is not None
            return tokens.refresh

    async def change():
        async with session_factory() as session:
            if session_kind != "login":
                with pytest.raises(passwords.PasswordChangeNotAllowedError) as rejected:
                    await passwords.change_password(
                        user_id, EXISTING_USER_PASSWORD, NEW_PASSWORD, session
                    )
                assert rejected.value.status_code == 403
                return None
            _, _, refresh = await passwords.change_password(
                user_id, EXISTING_USER_PASSWORD, NEW_PASSWORD, session
            )
            return refresh

    issue = asyncio.create_task(issue_session(), name="session-first")
    await asyncio.wait_for(first_locked.wait(), 10)
    change_task = asyncio.create_task(change(), name="password-change")
    try:
        await asyncio.wait_for(password_waiting.wait(), 10)
    finally:
        release.set()
    issued, new_refresh = await asyncio.wait_for(asyncio.gather(issue, change_task), 10)
    async with session_factory() as session:
        refresh = (await session.exec(select(RefreshToken))).one()
        devices = (await session.exec(select(TrustedDevice))).all()
        assert devices
        assert refresh.revoked_at is None
        if session_kind == "login":
            assert await auth_service.get_refresh_token(issued, session) is None
            assert refresh.token_hash == auth_service._hash_token(new_refresh)
            assert all(row.revoked_at is not None for row in devices)
        else:
            assert refresh.token_hash == auth_service._hash_token(issued)
            assert all(row.revoked_at is None for row in devices)
            assert (await session.get(User, user_id)).hashed_password == old_hash


@pytest.mark.parametrize("secure", [False, True])
async def test_password_endpoint_reissues_auth_cookies_and_clears_admin_cookies(
    async_client, db_session, existing_user, monkeypatch, secure
):
    monkeypatch.setattr(settings, "env", "production" if secure else "development")
    async_client.cookies.set(
        auth.access_cookie_name(),
        auth.create_access_token(str(existing_user.id)),
        domain="test.example",
        path="/",
    )
    raw = await auth_service.create_refresh_token(existing_user.id, db_session)
    await db_session.commit()
    response = await async_client.post(
        "/auth/me/password",
        json={
            "current_password": EXISTING_USER_PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    refresh_max_age = settings.jwt_refresh_token_expire_days * 86400
    expected_cookies = {
        auth.access_cookie_name(): (
            "/",
            settings.jwt_access_token_expire_minutes * 60,
            True,
            "lax",
        ),
        auth.REFRESH_COOKIE_NAME: (auth.REFRESH_COOKIE_PATH, refresh_max_age, True, "strict"),
        auth.LOGIN_HINT_COOKIE_NAME: ("/", refresh_max_age, False, "lax"),
        auth.ADMIN_PENDING_COOKIE_NAME: (auth.ADMIN_PENDING_PATH, 0, True, "strict"),
        auth.TRUSTED_DEVICE_COOKIE_NAME: (auth.TRUSTED_DEVICE_PATH, 0, True, "strict"),
    }
    assert len(cookies) == len(expected_cookies)
    for name, (path, max_age, http_only, same_site) in expected_cookies.items():
        header = next(value for value in cookies if value.startswith(f"{name}="))
        attributes = header.split("; ")[1:]
        assert f"Max-Age={max_age}" in attributes
        assert f"Path={path}" in attributes
        assert f"SameSite={same_site}" in attributes
        assert ("Secure" in attributes) == secure
        assert ("HttpOnly" in attributes) == http_only
    assert await auth_service.get_refresh_token(raw, db_session) is None
    assert response.json() == {"message": "비밀번호가 변경되었습니다"}


@pytest.mark.parametrize(
    "case,status", [("wrong", 400), ("oauth", 409), ("pwned", 422), ("same", 422)]
)
async def test_password_endpoint_rejections(
    async_client, db_session, existing_user, monkeypatch, case, status
):
    user_id = existing_user.id
    current, new = EXISTING_USER_PASSWORD, NEW_PASSWORD
    if case == "oauth":
        existing_user.hashed_password = None
        await db_session.commit()
    elif case == "wrong":
        current = "Wrong-Passw0rd!"
    elif case == "pwned":
        monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=True))
    elif case == "same":
        new = current
    old_hash = existing_user.hashed_password
    async_client.cookies.set(
        auth.access_cookie_name(),
        auth.create_access_token(str(user_id)),
        domain="test.example",
        path="/",
    )
    response = await async_client.post(
        "/auth/me/password",
        json={"current_password": current, "new_password": new, "confirm_password": new},
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list("set-cookie") == []
    assert current not in response.text and new not in response.text
    await db_session.refresh(existing_user)
    assert existing_user.hashed_password == old_hash
