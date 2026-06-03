"""인증 서비스 - 비밀번호 해싱 (M1 B1) + refresh 토큰 프리미티브 (M1 B2).

비밀번호 해싱은 OWASP Password Storage Cheat Sheet의 pre-hash 구조를 따른다:

    bcrypt( base64( hmac_sha384(password, key=PASSWORD_PEPPER) ), gensalt(cost=12) )

이 구조 하나로 세 가지를 동시에 해결한다.
  - 72바이트 한도: HMAC-SHA384 다이제스트(48B)를 base64로 인코딩하면 64자(<72)로 고정 ->
    bcrypt 5.x가 긴 비번에 던지는 ValueError와 조용한 truncate를 모두 회피.
  - pepper: HMAC 키로 서버측 시크릿(DB 밖)을 섞어 DB 단독 유출 시 오프라인 크래킹 차단.
  - password shucking / null 바이트: HMAC + base64로 방어.

bcrypt는 ~250~350ms CPU 블로킹이라, 이벤트 루프를 막지 않도록 워커 스레드로 오프로드한다
(backend/CLAUDE.md "비동기 함수에서 동기 블로킹 호출" 금지). 관련 study: secret-hashing.

refresh 토큰은 secrets.token_urlsafe(32) opaque 랜덤(256bit).
DB에는 HMAC-SHA256(token, key=TOKEN_PEPPER) 해시만 저장. 고엔트로피라 빠른 해시로 충분.
결정적 해시라 WHERE token_hash=? 직접 조회 가능. study: secret-hashing, refresh-token-rotation.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from anyio import to_thread
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.models.user import RefreshToken

# OWASP work factor >= 10. 소형 VPS 기준 cost=12 (배포 후 ~250~350ms 되도록 보정).
_BCRYPT_ROUNDS = 12


def _prehash(plain: str) -> bytes:
    """비번을 pepper로 HMAC-SHA384 → base64. bcrypt에 넣기 전 고정 길이(64자)로 정규화.

    반드시 raw digest(48B)를 base64. hexdigest(96자)는 다시 72바이트를 초과해 truncate된다.
    """
    digest = hmac.new(
        settings.password_pepper.get_secret_value().encode("utf-8"),
        plain.encode("utf-8"),
        hashlib.sha384,
    ).digest()
    return base64.b64encode(digest)


def _hash_sync(prehashed: bytes) -> str:
    return bcrypt.hashpw(prehashed, bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("utf-8")


def _verify_sync(prehashed: bytes, hashed: str) -> bool:
    return bcrypt.checkpw(prehashed, hashed.encode("utf-8"))


async def hash_password(plain: str) -> str:
    """평문 비번 → 저장용 해시 문자열. bcrypt는 스레드로 오프로드."""
    return await to_thread.run_sync(_hash_sync, _prehash(plain))


async def verify_password(plain: str, hashed: str) -> bool:
    """평문 비번이 저장된 해시와 일치하는지 확인. 상수 시간 비교(bcrypt.checkpw)."""
    return await to_thread.run_sync(_verify_sync, _prehash(plain), hashed)


# ---------------------------------------------------------------------------
# Refresh 토큰 프리미티브 (M1 B2)
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    """opaque 토큰 원문을 HMAC-SHA256(+TOKEN_PEPPER) 해시로 변환.

    결정적 해시라 WHERE token_hash=? 직접 조회 가능.
    HMAC은 빠른 해시지만 256bit 랜덤 토큰은 brute-force가 물리적으로 불가라 충분.
    """
    return hmac.new(
        settings.token_pepper.get_secret_value().encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def create_refresh_token(user_id: uuid.UUID, session: AsyncSession) -> str:
    """refresh 토큰을 발급하고 hash를 DB에 저장(flush)한다. 원문을 반환(쿠키용).

    commit은 하지 않는다 - 호출자(C2 로그인, C4 회전)가 트랜잭션 경계를 잡는다.
    flush로 INSERT를 보내 FK 위반 등을 이 시점에 노출시킨다.
    """
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    record = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()
    return raw


async def get_refresh_token(raw: str, session: AsyncSession) -> RefreshToken | None:
    """원문 토큰으로 DB 행을 조회해 반환한다.

    revoked/만료 여부는 호출자가 판단한다. revoke된 행도 반환해야 C4 재사용 탐지 가능.
    """
    token_hash = _hash_token(raw)
    result = await session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.first()


async def revoke_refresh_token(record: RefreshToken, session: AsyncSession) -> None:
    """refresh 토큰 1건을 revoke 표시한다. commit은 호출자 책임."""
    record.revoked_at = datetime.now(UTC)
    session.add(record)


async def revoke_all_refresh_tokens(user_id: uuid.UUID, session: AsyncSession) -> None:
    """유저의 유효한 refresh 토큰을 전부 revoke 표시한다. 재사용 탐지 시 세션 전체 무효화용.

    commit은 호출자 책임(C4에서 신규 발급과 한 트랜잭션으로 묶기 위함).
    """
    now = datetime.now(UTC)
    result = await session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    )
    for record in result.all():
        record.revoked_at = now
        session.add(record)
