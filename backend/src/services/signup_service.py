"""가입 전 이메일 링크 검증과 일회성 가입 증명 소비."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.exceptions import PwnedPasswordError
from src.models.user import SignupEmailVerification, User
from src.services import auth_service, email_service, hibp

CODE_TTL = timedelta(minutes=10)
PROOF_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)


class SignupVerificationError(Exception):
    pass


class SignupCooldownError(Exception):
    pass


@dataclass(frozen=True)
class SignupResult:
    duplicate: bool


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hmac(value: str) -> str:
    return hmac.new(
        settings.token_pepper.get_secret_value().encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def _code_hash(challenge_id: uuid.UUID, code: str) -> str:
    return _hmac(f"{challenge_id}:{code}")


async def send_verification(
    email: str, session: AsyncSession, background_tasks: BackgroundTasks
) -> uuid.UUID:
    email = normalize_email(email)
    now = datetime.now(UTC)
    challenge_id = uuid.uuid4()
    code = f"{secrets.randbelow(1_000_000):06d}"
    existing_result = await session.exec(select(User.id).where(User.email == email))
    already_registered = existing_result.first() is not None
    expires_at = now if already_registered else now + CODE_TTL
    result = await session.exec(
        insert(SignupEmailVerification)
        .values(
            email=email,
            challenge_id=challenge_id,
            token_hash=_code_hash(challenge_id, code),
            attempts=0,
            expires_at=expires_at,
            last_sent_at=now,
        )
        .on_conflict_do_update(
            index_elements=["email"],
            set_={
                "challenge_id": challenge_id,
                "token_hash": _code_hash(challenge_id, code),
                "attempts": 0,
                "expires_at": expires_at,
                "last_sent_at": now,
                "proof_hash": None,
                "proof_expires_at": None,
                "used_at": None,
            },
            where=SignupEmailVerification.last_sent_at <= now - RESEND_COOLDOWN,
        )
        .returning(SignupEmailVerification.challenge_id)
    )
    issued_challenge_id = result.scalar_one_or_none()
    if issued_challenge_id is None:
        await session.rollback()
        raise SignupCooldownError
    await session.commit()
    if already_registered:
        background_tasks.add_task(email_service.send_already_registered_email, email)
    else:
        background_tasks.add_task(email_service.send_signup_code_email, email, code)
    return issued_challenge_id


async def verify_email(
    challenge_id: uuid.UUID, code: str, session: AsyncSession
) -> tuple[str, str]:
    result = await session.exec(
        select(SignupEmailVerification)
        .where(SignupEmailVerification.challenge_id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = result.first()
    now = datetime.now(UTC)
    if (
        record is None
        or record.used_at is not None
        or record.proof_hash is not None
        or record.expires_at <= now
        or record.attempts >= 5
    ):
        await session.rollback()
        raise SignupVerificationError
    if not hmac.compare_digest(record.token_hash, _code_hash(challenge_id, code)):
        record.attempts += 1
        session.add(record)
        await session.commit()
        raise SignupVerificationError
    proof = secrets.token_urlsafe(32)
    record.proof_hash = _hmac(proof)
    record.proof_expires_at = now + PROOF_TTL
    session.add(record)
    await session.commit()
    return record.email, proof


async def get_verified_email(proof: str | None, session: AsyncSession) -> str | None:
    if not proof:
        return None
    result = await session.exec(
        select(SignupEmailVerification).where(
            SignupEmailVerification.proof_hash == _hmac(proof),
            SignupEmailVerification.proof_expires_at > datetime.now(UTC),
            SignupEmailVerification.used_at.is_(None),
        )
    )
    record = result.first()
    return record.email if record else None


async def complete_signup(
    email: str, password: str, nickname: str, proof: str | None, session: AsyncSession
) -> SignupResult:
    email = normalize_email(email)
    if not proof or await get_verified_email(proof, session) != email:
        raise SignupVerificationError
    # 초기 proof 조회로 열린 read transaction은 외부 HIBP와 CPU bcrypt 전에 닫는다.
    await session.rollback()
    if await hibp.is_password_pwned(password):
        raise PwnedPasswordError
    password_hash = await auth_service.hash_password(password)

    result = await session.exec(
        select(SignupEmailVerification)
        .where(SignupEmailVerification.proof_hash == _hmac(proof))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = result.first()
    now = datetime.now(UTC)
    if (
        record is None
        or record.email != email
        or record.used_at is not None
        or record.proof_expires_at is None
        or record.proof_expires_at <= now
    ):
        await session.rollback()
        raise SignupVerificationError
    # soft-delete 계정도 users.email UNIQUE를 점유한다. 어떤 기존 행도 덮어쓰지 않는다.
    existing_result = await session.exec(select(User).where(User.email == email))
    if existing_result.first() is not None:
        record.used_at = now
        session.add(record)
        await session.commit()
        return SignupResult(duplicate=True)

    duplicate = False
    try:
        async with session.begin_nested():
            session.add(
                User(
                    email=email,
                    hashed_password=password_hash,
                    nickname=nickname,
                    is_email_verified=True,
                    email_verified_at=now,
                )
            )
            await session.flush()
    except IntegrityError:
        raced = await session.exec(select(User.id).where(User.email == email))
        if raced.first() is None:
            raise
        duplicate = True
    record.used_at = now
    session.add(record)
    await session.commit()
    return SignupResult(duplicate=duplicate)
