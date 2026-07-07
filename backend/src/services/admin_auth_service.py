"""관리자 TOTP 등록(enrollment) 로직 (M1.5 B2). 2단계 로그인(stage1/stage2)은 B3.

시크릿 원문은 provisioning URI(QR 1회 표시)에만 존재한다 - DB에는 Fernet 암호문만
저장하고(lib/totp.py), 원문·URI·코드는 로깅하지 않는다(backend/CLAUDE.md).
"""

from datetime import UTC, datetime

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib import totp
from src.lib.auth import create_access_token
from src.models.user import User
from src.services.auth_service import create_refresh_token

logger = structlog.get_logger(__name__)


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


async def confirm_totp(user: User, code: str, session: AsyncSession) -> tuple[str, str] | None:
    """첫 코드를 검증하고 성공 시 활성화(totp_confirmed_at) + (access, refresh) 발급.

    confirm 시점엔 비번(1단계 pending 쿠키)과 TOTP 코드가 모두 검증된 상태라 2단계
    로그인과 등가 - 재로그인 없이 바로 세션을 연다(ledger 그룹 B 확정결정 1). 실패는 None.
    """
    if user.totp_secret is None:
        return None
    if not totp.verify_code(totp.decrypt_secret(user.totp_secret), code):
        logger.info("auth.admin_2fa", outcome="confirm_fail", user_id=str(user.id))
        return None
    user.totp_confirmed_at = datetime.now(UTC)
    session.add(user)
    access = create_access_token(str(user.id))
    refresh = await create_refresh_token(user.id, session)
    await session.commit()
    logger.info("auth.admin_2fa", outcome="confirmed", user_id=str(user.id))
    return access, refresh
