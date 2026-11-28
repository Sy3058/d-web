"""비밀번호 재설정 발급과 소비를 비열거 및 원자적 세션 폐기 정책으로 처리한다."""

import hashlib
import hmac
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import BackgroundTasks
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.exceptions import PwnedPasswordError
from src.lib.rate_limit import allow_password_reset_notice
from src.models.user import OAuthAccount, PasswordReset, RefreshToken, User
from src.schemas.auth import validate_password_policy
from src.services import auth_service, email_service, hibp
from src.services.admin_auth_service import revoke_trusted_devices

RESET_TTL = timedelta(hours=1)
SEND_COOLDOWN = timedelta(seconds=60)
logger = structlog.get_logger(__name__)


class InvalidPasswordResetError(Exception):
    pass


class SamePasswordResetError(Exception):
    pass


@dataclass(frozen=True)
class PasswordResetResult:
    email: str
    login_url: str


def _credential_tag(password_hash: str) -> str:
    return hmac.new(
        settings.token_pepper.get_secret_value().encode("utf-8"),
        f"password-reset-credential:{password_hash}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _eligible(user: User | None) -> bool:
    return bool(
        user is not None
        and user.deleted_at is None
        and user.is_email_verified
        and user.hashed_password is not None
    )


async def _queue_notice(
    email: str,
    target: str,
    send: Callable[[str], Awaitable[None]],
    background_tasks: BackgroundTasks,
) -> None:
    if not await allow_password_reset_notice(target):
        logger.info("auth.password_reset_request", outcome="notice_cooldown", target=target)
        return
    background_tasks.add_task(send, email)
    logger.info("auth.password_reset_request", outcome="notice_queued", target=target)


async def request_reset(
    email: str, session: AsyncSession, background_tasks: BackgroundTasks
) -> None:
    target = auth_service.email_login_tag(email)
    normalized_email = email.strip().lower()
    existing = (await session.exec(select(User).where(User.email == normalized_email))).first()
    if existing is None:
        await session.rollback()
        await _queue_notice(
            normalized_email,
            target,
            email_service.send_non_registered_email,
            background_tasks,
        )
        return
    user = (
        await session.exec(
            select(User)
            .where(User.id == existing.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if (
        user is not None
        and user.deleted_at is None
        and user.is_email_verified
        and user.hashed_password is None
        and not auth_service.requires_totp_login(user)
    ):
        google_account = (
            await session.exec(
                select(OAuthAccount.id).where(
                    OAuthAccount.user_id == user.id,
                    OAuthAccount.provider == "google",
                )
            )
        ).first()
        if google_account is not None:
            notice_email = user.email
            await session.rollback()
            await _queue_notice(
                notice_email,
                target,
                email_service.send_google_registered_email,
                background_tasks,
            )
            return
    if not _eligible(user):
        await session.rollback()
        logger.info(
            "auth.password_reset_request",
            outcome="ineligible",
            phase="locked",
            target=target,
        )
        return
    now = datetime.now(UTC)
    latest = (
        await session.exec(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.id)
            .order_by(PasswordReset.created_at.desc())
            .limit(1)
        )
    ).first()
    if (
        latest is not None
        and latest.created_at is not None
        and latest.created_at > now - SEND_COOLDOWN
    ):
        await session.rollback()
        logger.info("auth.password_reset_request", outcome="cooldown", target=target)
        return
    older = await session.exec(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.used_at.is_(None),
        )
    )
    for record in older.all():
        record.used_at = now
        session.add(record)
    raw_token = secrets.token_urlsafe(32)
    session.add(
        PasswordReset(
            user_id=user.id,
            token_hash=auth_service._hash_token(raw_token),
            credential_tag=_credential_tag(user.hashed_password),
            expires_at=now + RESET_TTL,
            created_at=now,
        )
    )
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    background_tasks.add_task(email_service.send_password_reset_email, user.email, raw_token)
    logger.info("auth.password_reset_request", outcome="queued", target=target)


async def reset_password(
    raw_token: str, new_password: str, session: AsyncSession
) -> PasswordResetResult:
    validate_password_policy(new_password)
    token_hash = auth_service._hash_token(raw_token)
    candidate = (
        await session.exec(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
    ).first()
    now = datetime.now(UTC)
    if candidate is None or candidate.used_at is not None or candidate.expires_at <= now:
        await session.rollback()
        raise InvalidPasswordResetError
    user_id = candidate.user_id
    await session.rollback()

    if await hibp.is_password_pwned(new_password):
        raise PwnedPasswordError
    new_hash = await auth_service.hash_password(new_password)

    user = await auth_service.lock_user(user_id, session)
    record = (
        await session.exec(
            select(PasswordReset)
            .where(PasswordReset.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    locked_now = datetime.now(UTC)
    if (
        not _eligible(user)
        or record is None
        or record.user_id != user_id
        or record.used_at is not None
        or record.expires_at <= locked_now
        or not hmac.compare_digest(record.credential_tag, _credential_tag(user.hashed_password))
    ):
        await session.rollback()
        raise InvalidPasswordResetError
    same_password = await auth_service.verify_password(new_password, user.hashed_password)
    if record.expires_at <= datetime.now(UTC):
        await session.rollback()
        raise InvalidPasswordResetError
    if same_password:
        await session.rollback()
        raise SamePasswordResetError
    email = user.email
    login_url = f"{settings.app_base_url.rstrip('/')}/auth/login"
    try:
        user.hashed_password = new_hash
        await session.flush()
        await session.exec(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        await revoke_trusted_devices(user_id, session)
        await session.exec(delete(PasswordReset).where(PasswordReset.user_id == user_id))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return PasswordResetResult(email=email, login_url=login_url)
