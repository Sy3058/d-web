"""비밀번호 재설정 HTTP 계약과 rate limit, 쿠키 비발급 회귀."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pyotp
import pytest
from sqlmodel import select

from src.config import settings
from src.lib import auth, totp
from src.models.user import RefreshToken, RoleEnum, TrustedDevice, User
from src.services import admin_auth_service, auth_service, email_service, hibp
from tests.conftest import EXISTING_USER_PASSWORD

pytestmark = pytest.mark.asyncio
NEW_PASSWORD = "Reset-Passw0rd!"


@pytest.fixture(autouse=True)
def prevent_password_email_delivery(monkeypatch):
    """BackgroundTasks가 테스트에서 실제 Resend 요청을 실행하지 않도록 막는다."""
    monkeypatch.setattr(email_service, "send_password_reset_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_password_reset_complete_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_google_registered_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_non_registered_email", AsyncMock())


async def test_forgot_password_is_generic_no_store_for_existing_and_missing(
    async_client, existing_user, monkeypatch
):
    monkeypatch.setattr(email_service, "send_password_reset_email", AsyncMock())
    responses = [
        await async_client.post("/auth/forgot-password", json={"email": existing_user.email}),
        await async_client.post("/auth/forgot-password", json={"email": "nobody@example.com"}),
    ]
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert all(response.headers["cache-control"] == "no-store" for response in responses)
    assert all("set-cookie" not in response.headers for response in responses)


async def test_reset_success_sets_no_auth_cookies(async_client, existing_user, monkeypatch):
    user_email = existing_user.email
    sent = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(email_service, "send_password_reset_email", sent)
    monkeypatch.setattr(email_service, "send_password_reset_complete_email", complete)
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    assert (
        await async_client.post("/auth/forgot-password", json={"email": user_email})
    ).status_code == 200
    token = sent.await_args.args[1]

    response = await async_client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["login_url"] == f"{settings.app_base_url.rstrip('/')}/auth/login"
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    complete.assert_awaited_once_with(user_email, f"{settings.app_base_url.rstrip('/')}/auth/login")


async def test_reset_invalid_and_reused_are_same_generic_400(
    async_client, existing_user, monkeypatch
):
    sent = AsyncMock()
    monkeypatch.setattr(email_service, "send_password_reset_email", sent)
    monkeypatch.setattr(email_service, "send_password_reset_complete_email", AsyncMock())
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    await async_client.post("/auth/forgot-password", json={"email": existing_user.email})
    token = sent.await_args.args[1]
    success = await async_client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    invalid = await async_client.post(
        "/auth/reset-password", json={"token": "invalid", "new_password": NEW_PASSWORD}
    )
    reused = await async_client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert success.status_code == 200
    assert invalid.status_code == reused.status_code == 400
    assert invalid.json() == reused.json()
    assert invalid.headers["cache-control"] == reused.headers["cache-control"] == "no-store"


async def test_reset_pwned_password_is_422(async_client, existing_user, monkeypatch):
    sent = AsyncMock()
    monkeypatch.setattr(email_service, "send_password_reset_email", sent)
    await async_client.post("/auth/forgot-password", json={"email": existing_user.email})
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=True))
    response = await async_client.post(
        "/auth/reset-password",
        json={"token": sent.await_args.args[1], "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


async def test_same_password_is_422_without_consuming_link_or_sending_completion(
    async_client, existing_user, monkeypatch
):
    email = existing_user.email
    sent = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(email_service, "send_password_reset_email", sent)
    monkeypatch.setattr(email_service, "send_password_reset_complete_email", complete)
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    await async_client.post("/auth/forgot-password", json={"email": email})
    token = sent.await_args.args[1]

    rejected = await async_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": EXISTING_USER_PASSWORD},
    )

    assert rejected.status_code == 422
    assert rejected.json() == {"detail": "새 비밀번호는 현재 비밀번호와 달라야 합니다"}
    assert rejected.headers["cache-control"] == "no-store"
    assert "set-cookie" not in rejected.headers
    complete.assert_not_awaited()

    retried = await async_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert retried.status_code == 200
    complete.assert_awaited_once()


async def test_owner_reset_preserves_totp_and_requires_admin_password_plus_totp(
    async_client, db_session, existing_user, monkeypatch
):
    user_id, email = existing_user.id, existing_user.email
    old_hash = existing_user.hashed_password
    secret = pyotp.random_base32()
    encrypted_secret = totp.encrypt_secret(secret)
    confirmed_at = datetime.now(UTC)
    existing_user.role = RoleEnum.OWNER
    existing_user.totp_secret = encrypted_secret
    existing_user.totp_confirmed_at = confirmed_at
    existing_user.totp_last_step = pyotp.TOTP(secret).timecode(confirmed_at) - 2
    raw_refresh = await auth_service.create_refresh_token(user_id, db_session)
    raw_trusted = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    sent = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(email_service, "send_password_reset_email", sent)
    monkeypatch.setattr(email_service, "send_password_reset_complete_email", complete)
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    pending = auth.create_admin_pending_token(str(user_id), auth.TOTP_PENDING, old_hash)
    async_client.cookies.set(
        auth.ADMIN_PENDING_COOKIE_NAME,
        pending,
        domain="test.example",
        path="/admin",
    )
    async_client.cookies.set(
        auth.TRUSTED_DEVICE_COOKIE_NAME,
        raw_trusted,
        domain="test.example",
        path="/admin",
    )
    forgot = await async_client.post("/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    reset = await async_client.post(
        "/auth/reset-password",
        json={"token": sent.await_args.args[1], "new_password": NEW_PASSWORD},
    )

    reader_login_url = f"{settings.app_base_url.rstrip('/')}/auth/login"
    assert reset.status_code == 200
    assert reset.json()["login_url"] == reader_login_url
    assert "set-cookie" not in reset.headers
    complete.assert_awaited_once_with(email, reader_login_url)

    fresh = await db_session.get(User, user_id)
    assert fresh.role == RoleEnum.OWNER
    assert fresh.totp_secret == encrypted_secret
    assert fresh.totp_confirmed_at == confirmed_at
    assert fresh.totp_last_step == pyotp.TOTP(secret).timecode(confirmed_at) - 2
    assert (await db_session.exec(select(RefreshToken))).all() == []
    trusted = (await db_session.exec(select(TrustedDevice))).one()
    assert trusted.revoked_at is not None
    assert await auth_service.get_refresh_token(raw_refresh, db_session) is None

    stale_pending = await async_client.post(
        "/admin/login/totp",
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert stale_pending.status_code == 401
    regular = await async_client.post(
        "/auth/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert regular.status_code == 401
    old_admin = await async_client.post(
        "/admin/login", json={"email": email, "password": EXISTING_USER_PASSWORD}
    )
    assert old_admin.status_code == 401
    async_client.cookies.set(
        auth.TRUSTED_DEVICE_COOKIE_NAME,
        raw_trusted,
        domain="test.example",
        path="/admin",
    )
    new_admin = await async_client.post(
        "/admin/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert new_admin.status_code == 200
    assert new_admin.json()["stage"] == "totp"
    assert auth.access_cookie_name() not in new_admin.cookies
    totp_gen = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    valid_codes = {totp_gen.at(now.timestamp() + offset) for offset in (-30, 0, 30)}
    wrong_code = next(
        code for code in ("000000", "111111", "222222", "333333") if code not in valid_codes
    )
    wrong = await async_client.post("/admin/login/totp", json={"code": wrong_code})
    assert wrong.status_code == 400
    correct = await async_client.post("/admin/login/totp", json={"code": pyotp.TOTP(secret).now()})
    assert correct.status_code == 200


@pytest.mark.parametrize(
    "path,body",
    [
        ("/auth/forgot-password", {"email": "nobody@example.com"}),
        ("/auth/reset-password", {"token": "invalid", "new_password": NEW_PASSWORD}),
    ],
)
async def test_password_reset_endpoints_rate_limit_five_per_minute(async_client, path, body):
    responses = [await async_client.post(path, json=body) for _ in range(6)]
    assert [response.status_code for response in responses[:5]] != [429] * 5
    assert responses[-1].status_code == 429
