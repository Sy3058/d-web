"""관리자 인증 로직 (M1.5 B2 TOTP 등록 + B3 2단계 로그인·신뢰 기기).

시크릿 원문은 provisioning URI(QR 1회 표시)에만 존재한다 - DB에는 Fernet 암호문만
저장하고(lib/totp.py), 원문·URI·코드는 로깅하지 않는다(backend/CLAUDE.md).
신뢰 기기 토큰은 refresh와 동일 원칙: 쿠키엔 opaque 원문, DB엔 HMAC(+TOKEN_PEPPER) 해시만.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib import totp
from src.lib.auth import create_access_token
from src.lib.exceptions import InvalidCredentialsError
from src.models.user import RoleEnum, TrustedDevice, User
from src.services.auth_service import (
    _dummy_verify,
    _hash_token,
    create_refresh_token,
    get_user_by_email,
    verify_password,
)

logger = structlog.get_logger(__name__)


class AdminSessionTokens(NamedTuple):
    """TOTP 검증 성공으로 열린 관리자 세션. trusted_device는 remember_device 옵트인 시만."""

    access: str
    refresh: str
    trusted_device: str | None


async def _issue_tokens(user: User, session: AsyncSession) -> tuple[str, str]:
    """access + refresh 발급(flush까지). commit은 호출자가 상태 변경과 한 트랜잭션으로 묶는다."""
    access = create_access_token(str(user.id))
    refresh = await create_refresh_token(user.id, session)
    return access, refresh


# ---------------------------------------------------------------------------
# TOTP 등록 (B2)
# ---------------------------------------------------------------------------


async def setup_totp(user: User, session: AsyncSession) -> str:
    """새 시크릿을 생성·암호화 저장하고 provisioning URI를 반환한다.

    미확인(totp_confirmed_at IS NULL) 상태의 재호출은 시크릿을 재생성해 덮어쓴다
    (QR 분실 재시도). 활성 유저 차단은 라우터 게이트 소관.
    """
    secret = totp.generate_secret()
    user.totp_secret = totp.encrypt_secret(secret)
    user.totp_confirmed_at = None
    session.add(user)
    await session.commit()
    logger.info("auth.admin_2fa", outcome="setup", user_id=str(user.id))
    return totp.provisioning_uri(secret, user.email)


async def confirm_totp(
    user: User, code: str, session: AsyncSession, *, remember_device: bool = False
) -> AdminSessionTokens | None:
    """첫 코드를 검증하고 성공 시 활성화(totp_confirmed_at) + 세션 토큰 발급. 실패는 None.

    confirm 시점엔 비번(1단계 pending 쿠키)과 TOTP 코드가 모두 검증된 상태라 2단계
    로그인과 등가 - 재로그인 없이 바로 세션을 연다(ledger 그룹 B 확정결정 1).
    """
    if user.totp_secret is None:
        return None
    if not totp.verify_code(totp.decrypt_secret(user.totp_secret), code):
        logger.info("auth.admin_2fa", outcome="confirm_fail", user_id=str(user.id))
        return None
    user.totp_confirmed_at = datetime.now(UTC)
    session.add(user)
    access, refresh = await _issue_tokens(user, session)
    trusted = await create_trusted_device(user, session) if remember_device else None
    await session.commit()
    logger.info("auth.admin_2fa", outcome="confirmed", user_id=str(user.id))
    return AdminSessionTokens(access, refresh, trusted)


# ---------------------------------------------------------------------------
# 2단계 로그인 (B3)
# ---------------------------------------------------------------------------


async def authenticate_owner(email: str, password: str, session: AsyncSession) -> User:
    """관리자 로그인 1단계: 이메일/비번 검증 + owner 확인. 실패는 InvalidCredentialsError.

    비열거: 미존재/소셜전용은 더미 해시로 타이밍 평탄화(/auth/login과 동일), 틀린 비번·
    비-owner(올바른 비번이어도)·탈퇴 전부 같은 예외 하나로 수렴한다 - 응답으로 '이 계정이
    관리자인가'까지 구분할 수 없게 한다. 비-owner 경로도 이미 bcrypt를 소비한 뒤라
    타이밍이 다른 실패 경로와 정렬된다.
    """
    user = await get_user_by_email(email, session)
    if user is None or user.hashed_password is None:
        await _dummy_verify()
        raise InvalidCredentialsError
    if not await verify_password(password, user.hashed_password):
        raise InvalidCredentialsError
    if user.role != RoleEnum.OWNER:
        raise InvalidCredentialsError
    return user


async def login_totp(
    user: User, code: str, session: AsyncSession, *, remember_device: bool = False
) -> AdminSessionTokens | None:
    """2단계: TOTP 코드 검증 성공 시 세션 토큰 발급(+옵트인 신뢰 기기). 실패는 None.

    활성(totp_confirmed_at NOT NULL) owner 전제 - 게이트는 라우터 소관(B2와 동일 분업).
    """
    if user.totp_secret is None:
        return None
    if not totp.verify_code(totp.decrypt_secret(user.totp_secret), code):
        logger.info("auth.admin_login", outcome="totp_fail", user_id=str(user.id))
        return None
    access, refresh = await _issue_tokens(user, session)
    trusted = await create_trusted_device(user, session) if remember_device else None
    await session.commit()
    logger.info("auth.admin_login", outcome="success", user_id=str(user.id))
    return AdminSessionTokens(access, refresh, trusted)


async def issue_trusted_session(user: User, session: AsyncSession) -> tuple[str, str]:
    """유효한 신뢰 기기 확인 후 TOTP 생략 세션 발급(1단계에서 완결) + commit.

    관측 로그는 호출자(라우터)가 남긴다 - stage1 outcome 로그는 전부 라우터에서 ip와
    함께 기록해 대칭을 유지한다.
    """
    access, refresh = await _issue_tokens(user, session)
    await session.commit()
    return access, refresh


# ---------------------------------------------------------------------------
# 신뢰 기기 (B3 - "이 기기에서 2단계 인증 생략")
# ---------------------------------------------------------------------------


async def create_trusted_device(user: User, session: AsyncSession) -> str:
    """신뢰 기기 토큰 발급 - DB엔 HMAC 해시만 저장(flush), 원문 반환(쿠키용). commit은 호출자.

    created_at을 DB server_default에 맡기지 않고 앱 시계로 명시한다 - 유효성 판정
    (created_at >= totp_confirmed_at)의 양변이 같은 시계를 쓰게 해 앱-DB 시계 스큐로 인한
    '방금 발급했는데 무효' 오판을 없앤다. 절대 만료: expires_at 고정, 갱신 경로 없음.
    """
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    record = TrustedDevice(
        user_id=user.id,
        token_hash=_hash_token(raw),
        created_at=now,
        expires_at=now + timedelta(days=settings.totp_trusted_device_days),
    )
    session.add(record)
    await session.flush()
    return raw


async def verify_trusted_device(user: User, raw: str, session: AsyncSession) -> bool:
    """신뢰 기기 토큰 검증. True면 /admin/login이 TOTP 단계를 생략한다.

    유효 조건: 본인 소유 행 존재 + 미revoke + 미만료 + created_at >= totp_confirmed_at.
    마지막 조건으로 TOTP 재등록(대개 기기 분실 복구) 시 옛 등록 시절의 기기 신뢰가
    전부 자동 실효된다 - 잃어버린 기기의 신뢰 쿠키가 리셋 후에도 살아남으면 안 된다.
    """
    if user.totp_confirmed_at is None:
        return False
    result = await session.exec(
        select(TrustedDevice).where(
            TrustedDevice.token_hash == _hash_token(raw),
            TrustedDevice.user_id == user.id,
        )
    )
    record = result.first()
    if record is None or record.revoked_at is not None:
        return False
    return record.expires_at > datetime.now(UTC) and record.created_at >= user.totp_confirmed_at


async def revoke_trusted_devices(user_id: uuid.UUID, session: AsyncSession) -> None:
    """유저의 유효한 신뢰 기기를 전부 revoke 표시. commit은 호출자 책임.

    승격(promote) 시 refresh 일괄 revoke와 함께 호출한다(위생 - 재등록 실효 규칙과 이중 방어).
    """
    now = datetime.now(UTC)
    result = await session.exec(
        select(TrustedDevice).where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    )
    for record in result.all():
        record.revoked_at = now
        session.add(record)
