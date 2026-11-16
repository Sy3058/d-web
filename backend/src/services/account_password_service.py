"""비밀번호 변경과 모든 refresh/신뢰 기기 폐기를 한 트랜잭션으로 처리한다."""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.exceptions import PwnedPasswordError
from src.schemas.auth import validate_password_policy
from src.services import auth_service, hibp
from src.services.admin_auth_service import revoke_trusted_devices


class CurrentPasswordMismatchError(Exception):
    """현재 비밀번호 검증 실패."""


class PasswordChangeNotAllowedError(Exception):
    """소셜 전용 계정 또는 동일한 새 비밀번호."""

    def __init__(self, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


async def change_password(
    user_id: uuid.UUID, current_password: str, new_password: str, session: AsyncSession
) -> None:
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
    if user is None or user.hashed_password is None:
        raise PasswordChangeNotAllowedError("비밀번호로 가입한 계정만 변경할 수 있습니다")
    if not await auth_service.verify_password(current_password, user.hashed_password):
        raise CurrentPasswordMismatchError
    user.hashed_password = new_hash
    session.add(user)
    await auth_service.revoke_all_refresh_tokens(user_id, session)
    await revoke_trusted_devices(user_id, session)
    await session.commit()
