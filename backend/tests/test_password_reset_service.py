"""비밀번호 재설정의 비열거, 재검증, 단일 소비와 원자적 세션 폐기 회귀."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks
from sqlmodel import select

from src.config import settings
from src.models.user import OAuthAccount, PasswordReset, RoleEnum, TrustedDevice, User
from src.services import (
    admin_auth_service,
    auth_service,
    email_service,
    hibp,
    password_reset_service,
)
from tests.conftest import EXISTING_USER_PASSWORD

pytestmark = pytest.mark.asyncio
NEW_PASSWORD = "Reset-Passw0rd!"


async def _issue(email: str, session) -> str:
    tasks = BackgroundTasks()
    await password_reset_service.request_reset(email, session, tasks)
    assert len(tasks.tasks) == 1
    return tasks.tasks[0].args[1]


async def test_request_reset_issues_latest_only_and_enforces_silent_cooldown(
    db_session, existing_user
):
    email = existing_user.email
    first = await _issue(email, db_session)
    tasks = BackgroundTasks()
    await password_reset_service.request_reset(email, db_session, tasks)

    assert tasks.tasks == []
    rows = (await db_session.exec(select(PasswordReset))).all()
    assert len(rows) == 1
    assert rows[0].token_hash == auth_service._hash_token(first)

    rows[0].created_at = datetime.now(UTC) - password_reset_service.SEND_COOLDOWN
    db_session.add(rows[0])
    await db_session.commit()
    second = await _issue(email, db_session)
    rows = (await db_session.exec(select(PasswordReset).order_by(PasswordReset.created_at))).all()
    assert len(rows) == 2
    assert rows[0].used_at is not None
    assert rows[1].token_hash == auth_service._hash_token(second)


@pytest.mark.parametrize("case", ["unverified", "oauth", "deleted", "future_social"])
async def test_request_reset_silently_excludes_ineligible_users(db_session, existing_user, case):
    email = existing_user.email
    if case == "unverified":
        existing_user.is_email_verified = False
    elif case in {"oauth", "future_social"}:
        existing_user.hashed_password = None
        if case == "future_social":
            db_session.add(
                OAuthAccount(
                    user_id=existing_user.id,
                    provider="kakao",
                    provider_id="future-social",
                )
            )
    else:
        existing_user.deleted_at = datetime.now(UTC)
    await db_session.commit()
    tasks = BackgroundTasks()

    await password_reset_service.request_reset(email, db_session, tasks)

    assert tasks.tasks == []
    assert (await db_session.exec(select(PasswordReset))).all() == []


async def test_request_reset_queues_missing_and_google_account_notices(db_session, existing_user):
    user_id, email = existing_user.id, existing_user.email
    missing_email = "nobody@example.com"
    missing_tasks = BackgroundTasks()
    await password_reset_service.request_reset(missing_email, db_session, missing_tasks)
    assert len(missing_tasks.tasks) == 1
    assert missing_tasks.tasks[0].func is email_service.send_non_registered_email
    assert missing_tasks.tasks[0].args == (missing_email,)

    existing_user = await db_session.get(User, user_id)
    existing_user.hashed_password = None
    db_session.add(
        OAuthAccount(
            user_id=existing_user.id,
            provider="google",
            provider_id="google-user",
        )
    )
    await db_session.commit()
    google_tasks = BackgroundTasks()
    await password_reset_service.request_reset(email, db_session, google_tasks)
    assert len(google_tasks.tasks) == 1
    assert google_tasks.tasks[0].func is email_service.send_google_registered_email
    assert google_tasks.tasks[0].args == (email,)


async def test_password_reset_notice_has_silent_per_address_cooldown(db_session, monkeypatch):
    email = "nobody@example.com"
    target = auth_service.email_login_tag(email)
    mock_logger = MagicMock()
    monkeypatch.setattr(password_reset_service, "logger", mock_logger)

    first = BackgroundTasks()
    second = BackgroundTasks()
    await password_reset_service.request_reset(email, db_session, first)
    await password_reset_service.request_reset(email, db_session, second)

    assert len(first.tasks) == 1
    assert second.tasks == []
    assert mock_logger.info.call_args.args == ("auth.password_reset_request",)
    assert mock_logger.info.call_args.kwargs == {
        "outcome": "notice_cooldown",
        "target": target,
    }


async def test_request_reset_logs_safe_internal_outcomes(db_session, existing_user, monkeypatch):
    user_id, email = existing_user.id, existing_user.email
    target = auth_service.email_login_tag(email)
    mock_logger = MagicMock()
    monkeypatch.setattr(password_reset_service, "logger", mock_logger)

    token = await _issue(email, db_session)
    queued_call = mock_logger.info.call_args
    assert queued_call.args == ("auth.password_reset_request",)
    assert queued_call.kwargs == {"outcome": "queued", "target": target}
    logged_calls = [repr(mock_logger.method_calls)]

    mock_logger.reset_mock()
    tasks = BackgroundTasks()
    await password_reset_service.request_reset(email, db_session, tasks)
    cooldown_call = mock_logger.info.call_args
    assert cooldown_call.args == ("auth.password_reset_request",)
    assert cooldown_call.kwargs == {"outcome": "cooldown", "target": target}
    logged_calls.append(repr(mock_logger.method_calls))

    mock_logger.reset_mock()
    user = await db_session.get(User, user_id)
    user.is_email_verified = False
    await db_session.commit()
    await password_reset_service.request_reset(email, db_session, BackgroundTasks())
    ineligible_call = mock_logger.info.call_args
    assert ineligible_call.args == ("auth.password_reset_request",)
    assert ineligible_call.kwargs == {
        "outcome": "ineligible",
        "phase": "locked",
        "target": target,
    }
    logged_calls.append(repr(mock_logger.method_calls))

    logged = "".join(logged_calls)
    assert token not in logged
    assert email not in logged


async def test_reset_changes_password_and_revokes_sessions_and_trusted_devices(
    db_session, existing_user, monkeypatch
):
    user_id, user_email = existing_user.id, existing_user.email
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    raw_reset = await _issue(user_email, db_session)
    raw_refresh = await auth_service.create_refresh_token(user_id, db_session)
    raw_device = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()

    result = await password_reset_service.reset_password(raw_reset, NEW_PASSWORD, db_session)

    assert result.email == user_email
    assert result.login_url == f"{settings.app_base_url.rstrip('/')}/auth/login"
    fresh = await db_session.get(User, user_id)
    assert await auth_service.verify_password(NEW_PASSWORD, fresh.hashed_password)
    assert await auth_service.get_refresh_token(raw_refresh, db_session) is None
    assert (await db_session.exec(select(PasswordReset))).all() == []
    device = (
        await db_session.exec(
            select(TrustedDevice).where(
                TrustedDevice.token_hash == auth_service._hash_token(raw_device)
            )
        )
    ).one()
    assert device.revoked_at is not None


async def test_reader_issued_link_still_resets_after_promotion_to_owner(
    db_session, existing_user, monkeypatch
):
    user_id, email = existing_user.id, existing_user.email
    raw_reset = await _issue(email, db_session)
    existing_user.role = RoleEnum.OWNER
    existing_user.totp_secret = "preserved-ciphertext"
    confirmed_at = datetime.now(UTC)
    existing_user.totp_confirmed_at = confirmed_at
    existing_user.totp_last_step = 12345
    raw_refresh = await auth_service.create_refresh_token(user_id, db_session)
    raw_device = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    result = await password_reset_service.reset_password(raw_reset, NEW_PASSWORD, db_session)

    assert result == password_reset_service.PasswordResetResult(
        email=email,
        login_url=f"{settings.app_base_url.rstrip('/')}/auth/login",
    )
    fresh = await db_session.get(User, user_id)
    assert fresh.role == RoleEnum.OWNER
    assert fresh.totp_secret == "preserved-ciphertext"
    assert fresh.totp_confirmed_at == confirmed_at
    assert fresh.totp_last_step == 12345
    assert await auth_service.get_refresh_token(raw_refresh, db_session) is None
    device = (
        await db_session.exec(
            select(TrustedDevice).where(
                TrustedDevice.token_hash == auth_service._hash_token(raw_device)
            )
        )
    ).one()
    assert device.revoked_at is not None


@pytest.mark.parametrize("owner", [False, True])
async def test_same_password_rejection_preserves_state_and_token_for_retry(
    db_session, existing_user, monkeypatch, owner
):
    user_id, email, old_hash = (
        existing_user.id,
        existing_user.email,
        existing_user.hashed_password,
    )
    confirmed_at = datetime.now(UTC)
    if owner:
        existing_user.role = RoleEnum.OWNER
        existing_user.totp_secret = "preserved-owner-ciphertext"
        existing_user.totp_confirmed_at = confirmed_at
        existing_user.totp_last_step = 54321
        await db_session.commit()
    raw_reset = await _issue(email, db_session)
    raw_refresh = await auth_service.create_refresh_token(user_id, db_session)
    raw_device = await admin_auth_service.create_trusted_device(existing_user, db_session)
    await db_session.commit()
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    with pytest.raises(password_reset_service.SamePasswordResetError):
        await password_reset_service.reset_password(raw_reset, EXISTING_USER_PASSWORD, db_session)

    fresh = await db_session.get(User, user_id)
    assert fresh.hashed_password == old_hash
    if owner:
        assert fresh.role == RoleEnum.OWNER
        assert fresh.totp_secret == "preserved-owner-ciphertext"
        assert fresh.totp_confirmed_at == confirmed_at
        assert fresh.totp_last_step == 54321
    assert await auth_service.get_refresh_token(raw_refresh, db_session) is not None
    device = (
        await db_session.exec(
            select(TrustedDevice).where(
                TrustedDevice.token_hash == auth_service._hash_token(raw_device)
            )
        )
    ).one()
    assert device.revoked_at is None
    token = (await db_session.exec(select(PasswordReset))).one()
    assert token.used_at is None

    result = await password_reset_service.reset_password(raw_reset, NEW_PASSWORD, db_session)
    assert result.login_url == f"{settings.app_base_url.rstrip('/')}/auth/login"


async def test_token_expiring_during_same_password_check_is_generic_invalid(
    db_session, existing_user, monkeypatch
):
    email = existing_user.email
    raw = await _issue(email, db_session)
    record = (await db_session.exec(select(PasswordReset))).one()
    original_expires_at = record.expires_at
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    observed_times = iter(
        [
            original_expires_at - timedelta(seconds=2),
            original_expires_at - timedelta(seconds=1),
            original_expires_at + timedelta(seconds=1),
        ]
    )

    class AdvancingDatetime:
        @classmethod
        def now(cls, _tz):
            return next(observed_times)

    monkeypatch.setattr(password_reset_service, "datetime", AdvancingDatetime)

    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(raw, EXISTING_USER_PASSWORD, db_session)
    preserved = (await db_session.exec(select(PasswordReset))).one()
    assert preserved.expires_at == original_expires_at
    assert preserved.used_at is None


async def test_invalid_token_is_rejected_before_hibp_and_hash(db_session, monkeypatch):
    pwned = AsyncMock()
    hashed = AsyncMock()
    monkeypatch.setattr(hibp, "is_password_pwned", pwned)
    monkeypatch.setattr(auth_service, "hash_password", hashed)

    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password("invalid", NEW_PASSWORD, db_session)

    pwned.assert_not_awaited()
    hashed.assert_not_awaited()


async def test_expired_reused_and_password_changed_tokens_share_rejection(
    db_session, existing_user, monkeypatch
):
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    user_id = existing_user.id
    raw = await _issue(existing_user.email, db_session)
    record = (await db_session.exec(select(PasswordReset))).one()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(raw, NEW_PASSWORD, db_session)

    record = (await db_session.exec(select(PasswordReset))).one()
    existing_user = await db_session.get(User, user_id)
    record.expires_at = datetime.now(UTC) + timedelta(hours=1)
    existing_user.hashed_password = await auth_service.hash_password("Changed-Earlier1!")
    await db_session.commit()
    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(raw, NEW_PASSWORD, db_session)


async def test_same_token_concurrency_has_one_winner(
    db_session, existing_user, session_factory, monkeypatch
):
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    raw = await _issue(existing_user.email, db_session)
    hash_password = auth_service.hash_password
    ready = asyncio.Barrier(2)

    async def hash_before_competing_for_user(password):
        result = await hash_password(password)
        await ready.wait()
        return result

    monkeypatch.setattr(auth_service, "hash_password", hash_before_competing_for_user)

    async def consume():
        async with session_factory() as session:
            try:
                await password_reset_service.reset_password(raw, NEW_PASSWORD, session)
                return "success"
            except password_reset_service.InvalidPasswordResetError:
                return "invalid"

    results = await asyncio.wait_for(asyncio.gather(consume(), consume()), 15)
    assert sorted(results) == ["invalid", "success"]


@pytest.mark.parametrize("case", ["unverified", "oauth", "deleted"])
async def test_reset_rechecks_account_eligibility_at_consumption(
    db_session, existing_user, monkeypatch, case
):
    user_id, email, old_hash = (
        existing_user.id,
        existing_user.email,
        existing_user.hashed_password,
    )
    raw = await _issue(email, db_session)
    user = await db_session.get(User, user_id)
    if case == "unverified":
        user.is_email_verified = False
    elif case == "oauth":
        user.hashed_password = None
    else:
        user.deleted_at = datetime.now(UTC)
    await db_session.commit()
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(raw, NEW_PASSWORD, db_session)

    fresh = await db_session.get(User, user_id)
    if case != "oauth":
        assert fresh.hashed_password == old_hash


async def test_reset_rechecks_expiry_after_password_hashing(
    db_session, existing_user, session_factory, monkeypatch
):
    email = existing_user.email
    raw = await _issue(email, db_session)
    token_hash = auth_service._hash_token(raw)
    replacement_hash = await auth_service.hash_password(NEW_PASSWORD)
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    async def expire_while_hashing(_plain):
        async with session_factory() as other:
            record = (
                await other.exec(
                    select(PasswordReset).where(PasswordReset.token_hash == token_hash)
                )
            ).one()
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await other.commit()
        return replacement_hash

    monkeypatch.setattr(auth_service, "hash_password", expire_while_hashing)

    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(raw, NEW_PASSWORD, db_session)


async def test_new_request_invalidates_previous_link(db_session, existing_user, monkeypatch):
    email = existing_user.email
    first = await _issue(email, db_session)
    record = (await db_session.exec(select(PasswordReset))).one()
    record.created_at = datetime.now(UTC) - password_reset_service.SEND_COOLDOWN
    await db_session.commit()
    second = await _issue(email, db_session)
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))

    with pytest.raises(password_reset_service.InvalidPasswordResetError):
        await password_reset_service.reset_password(first, NEW_PASSWORD, db_session)
    result = await password_reset_service.reset_password(second, NEW_PASSWORD, db_session)
    assert result.email == email


async def test_reset_rolls_back_password_and_tokens_on_revoke_failure(
    db_session, existing_user, monkeypatch
):
    user_id = existing_user.id
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    raw = await _issue(existing_user.email, db_session)
    old_hash = existing_user.hashed_password
    refresh = await auth_service.create_refresh_token(user_id, db_session)
    await db_session.commit()
    monkeypatch.setattr(
        password_reset_service,
        "revoke_trusted_devices",
        AsyncMock(side_effect=RuntimeError),
    )

    with pytest.raises(RuntimeError):
        await password_reset_service.reset_password(raw, NEW_PASSWORD, db_session)

    assert (await db_session.get(User, user_id)).hashed_password == old_hash
    assert await auth_service.get_refresh_token(refresh, db_session) is not None
    assert (await db_session.exec(select(PasswordReset))).one().used_at is None
