"""현재 사용자 프로필 갱신과 공개 아바타의 저장 수명 관리."""

import re
import uuid
from urllib.parse import urlsplit

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.exceptions import InvalidCredentialsError
from src.models.user import User
from src.services import avatar_service, r2_service

logger = structlog.get_logger(__name__)


def _public_base() -> str:
    base = settings.public_asset_base_url.rstrip("/")
    try:
        parsed = urlsplit(base)
        _ = parsed.port  # 잘못된 포트도 외부 쓰기 전에 거부한다.
    except ValueError as exc:
        raise r2_service.R2NotConfiguredError("프로필 이미지 공개 URL이 잘못되었습니다") from exc
    if (
        not r2_service.is_configured()
        or not settings.r2_public_bucket
        or parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in base
        or "#" in base
        or "%" in parsed.path
        or "\\" in base
        or any(char.isspace() or ord(char) < 32 for char in base)
        or any(part in (".", "..") for part in parsed.path.split("/"))
    ):
        raise r2_service.R2NotConfiguredError("프로필 이미지 저장소가 설정되지 않았습니다")
    return base


def _previous_key(url: str | None, user_id: uuid.UUID, base: str) -> str | None:
    if url is None or not url.startswith(f"{base}/"):
        return None
    key = url[len(base) + 1 :]
    # 문자열 일치는 origin, base path, 계정 namespace와 파일명 모두 고정한다.
    if re.fullmatch(rf"avatars/{re.escape(str(user_id))}/[0-9a-f]{{32}}\.webp", key):
        return key
    return None


async def _locked_user(user_id: uuid.UUID, session: AsyncSession) -> User:
    user = (
        await session.exec(
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if user is None:
        raise InvalidCredentialsError()
    return user


async def update_nickname(user_id: uuid.UUID, nickname: str, session: AsyncSession) -> User:
    user = await _locked_user(user_id, session)
    user.nickname = nickname
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _cleanup(key: str) -> None:
    try:
        await r2_service.delete_object(key, bucket=settings.r2_public_bucket)
    except Exception:
        # 저장 URL/파일명은 로그에 남기지 않는다. 실패 객체는 미참조 상태로만 남는다.
        logger.warning("account.avatar_cleanup_failed")


async def update_avatar(user_id: uuid.UUID, data: bytes, session: AsyncSession) -> User:
    base = _public_base()  # 외부 쓰기 전에 URL과 공개 저장소 설정 검증
    converted = await avatar_service.convert_avatar(data)
    key = f"avatars/{user_id}/{uuid.uuid4().hex}.webp"
    try:
        await r2_service.upload_bytes(key, converted, bucket=settings.r2_public_bucket)
    except Exception:
        # PUT 성공 뒤 전송 오류가 나더라도 신규 고유 키만 정리한다.
        await _cleanup(key)
        raise
    try:
        user = await _locked_user(user_id, session)
        previous_key = _previous_key(user.profile_image, user_id, base)
        user.profile_image = f"{base}/{key}"
        session.add(user)
    except Exception:
        await session.rollback()
        await _cleanup(key)
        raise
    try:
        await session.commit()
    except Exception:
        # COMMIT 응답 유실은 실제 성공과 구분할 수 없다. 참조 중일 수 있는 신규
        # 객체를 지우지 않고 보존한다(실제 롤백이면 미참조 객체만 남는다).
        await session.rollback()
        raise
    # DB가 새 URL을 확정한 다음 이전 객체를 지운다. 동시 요청도 잠금 아래 실제 이전값 사용.
    if previous_key:
        await _cleanup(previous_key)
    await session.refresh(user)
    return user
