"""비밀번호 변경, 이전 세션 폐기와 현재 기기 세션 발급을 한 트랜잭션으로 처리한다."""

import uuid

from sqlalchemy import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import create_access_token
from src.lib.exceptions import PwnedPasswordError
from src.models.user import RefreshToken, User
from src.schemas.auth import validate_password_policy
from src.services import auth_service, hibp
from src.services.admin_auth_service import revoke_trusted_devices


class CurrentPasswordMismatchError(Exception):
    """현재 비밀번호 검증 실패."""


class PasswordChangeNotAllowedError(Exception):
    """계정 유형 또는 새 비밀번호 정책으로 변경할 수 없음."""

    def __init__(self, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


async def change_password(
    user_id: uuid.UUID, current_password: str, new_password: str, session: AsyncSession
) -> tuple[User, str, str]:
    validate_password_policy(new_password)
    if new_password == current_password:
        raise PasswordChangeNotAllowedError(
            "새 비밀번호는 현재 비밀번호와 달라야 합니다", status_code=422
        )
    if await hibp.is_password_pwned(new_password):
        raise PwnedPasswordError
    # 외부 조회와 새 bcrypt는 User 잠금 전 끝낸다. 현재 비밀번호는 반드시 잠근 최신 행으로 확인한다.
    new_hash = await auth_service.hash_password(new_password)
    user = await auth_service.lock_user(user_id, session)
    if user is not None and auth_service.requires_totp_login(user):
        raise PasswordChangeNotAllowedError(
            "관리자 계정은 이 화면에서 비밀번호를 변경할 수 없습니다", status_code=403
        )
    if user is None or user.hashed_password is None:
        raise PasswordChangeNotAllowedError("비밀번호로 가입한 계정만 변경할 수 있습니다")
    if not await auth_service.verify_password(current_password, user.hashed_password):
        raise CurrentPasswordMismatchError
    try:
        user.hashed_password = new_hash
        await session.flush()
        # 이전 refresh의 재제출이 재사용 탐지로 새 세션까지 폐기하지 않도록 삭제한다.
        await session.exec(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        await revoke_trusted_devices(user_id, session)
        refresh = await auth_service.create_refresh_token(user_id, session)
        access = create_access_token(str(user_id))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return user, access, refresh
