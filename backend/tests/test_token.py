"""토큰 발급/검증 단위 테스트 (M1 B2).

JWT 테스트(순수 함수, DB 불필요) + refresh 프리미티브 테스트(db_session 픽스처 사용).
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.lib.auth import TokenError, create_access_token, decode_token
from src.models.user import RefreshToken, User
from src.services.auth_service import (
    _claim_refresh_token,
    create_refresh_token,
    get_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
)


@pytest_asyncio.fixture
async def test_user(db_session):
    """refresh_tokens.user_id FK를 만족시킬 실제 유저 1명 생성."""
    user = User(email="token-test@example.com", nickname="token-tester")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# JWT (lib/auth.py)
# ---------------------------------------------------------------------------


async def test_access_token_round_trip():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["typ"] == "access"


async def test_expired_token_raises():
    user_id = str(uuid.uuid4())
    with patch("src.lib.auth.datetime") as mock_dt:
        # 발급 시각을 16분 전으로 설정해 만료 토큰 생성
        mock_dt.now.return_value = datetime.now(UTC) - timedelta(minutes=16)
        token = create_access_token(user_id)
    with pytest.raises(TokenError, match="expired"):
        decode_token(token)


async def test_forged_signature_raises():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id)
    # 서명 부분 변조
    header, payload, sig = token.split(".")
    forged = f"{header}.{payload}.{sig[:-4]}XXXX"
    with pytest.raises(TokenError, match="invalid"):
        decode_token(forged)


async def test_wrong_typ_raises():
    """typ != "access" 토큰은 거부해야 한다."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "typ": "refresh",  # 잘못된 typ
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError, match="invalid typ"):
        decode_token(token)


async def test_pii_not_in_payload():
    """payload에 이메일 등 PII가 없는지 확인."""
    token = create_access_token(str(uuid.uuid4()))
    payload = decode_token(token)
    assert "email" not in payload
    assert "nickname" not in payload


# ---------------------------------------------------------------------------
# Refresh 토큰 프리미티브 (services/auth_service.py)
# ---------------------------------------------------------------------------


async def test_refresh_token_round_trip(db_session, test_user):
    raw = await create_refresh_token(test_user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert record.user_id == test_user.id
    assert record.revoked_at is None


async def test_refresh_token_hash_not_raw(db_session, test_user):
    """DB에 저장된 값이 원문 토큰이 아닌 해시여야 한다."""
    raw = await create_refresh_token(test_user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert record.token_hash != raw


async def test_revoke_single(db_session, test_user):
    raw = await create_refresh_token(test_user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    await revoke_refresh_token(record, db_session)

    refreshed = await get_refresh_token(raw, db_session)
    assert refreshed is not None
    assert refreshed.revoked_at is not None


async def test_get_returns_revoked_record(db_session, test_user):
    """revoke된 행도 반환해야 C4 재사용 탐지가 'None(없음)'과 '이미 revoke됨'을 구분 가능."""
    raw = await create_refresh_token(test_user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    await revoke_refresh_token(record, db_session)

    result = await get_refresh_token(raw, db_session)
    assert result is not None  # None이 아니라 revoked 행을 돌려줘야 함
    assert result.revoked_at is not None


async def test_unknown_token_returns_none(db_session):
    """존재하지 않는 토큰은 None."""
    result = await get_refresh_token("nonexistent-token", db_session)
    assert result is None


async def test_revoke_all(db_session, test_user):
    raw1 = await create_refresh_token(test_user.id, db_session)
    raw2 = await create_refresh_token(test_user.id, db_session)

    await revoke_all_refresh_tokens(test_user.id, db_session)

    r1 = await get_refresh_token(raw1, db_session)
    r2 = await get_refresh_token(raw2, db_session)
    assert r1 is not None and r1.revoked_at is not None
    assert r2 is not None and r2.revoked_at is not None


# ---------------------------------------------------------------------------
# 회전 원자화 (M1 I1)
# ---------------------------------------------------------------------------


async def test_claim_refresh_token_single_winner(db_session, test_user):
    """동시 회전의 결정적 프록시: 같은 토큰을 두 번 선점하면 1회차만 성공(True),
    2회차는 이미 revoked라 0행 매칭(False) → 한 토큰에서 새 토큰 2개 발급 차단.

    같은 트랜잭션 내 첫 UPDATE가 revoked_at을 세팅하면 둘째 UPDATE는
    revoked_at IS NULL 조건에 0행 매칭(자기 트랜잭션의 미커밋 변경을 본다).
    """
    raw = await create_refresh_token(test_user.id, db_session)
    record = await get_refresh_token(raw, db_session)

    assert await _claim_refresh_token(record, db_session) is True
    assert await _claim_refresh_token(record, db_session) is False


async def test_refresh_token_hash_unique(db_session, test_user):
    """token_hash UNIQUE 인덱스가 같은 해시 중복 INSERT를 차단(회전 불변식 방어선)."""
    expires = datetime.now(UTC) + timedelta(days=7)
    db_session.add(
        RefreshToken(user_id=test_user.id, token_hash="dup-hash", expires_at=expires)
    )
    await db_session.flush()
    db_session.add(
        RefreshToken(user_id=test_user.id, token_hash="dup-hash", expires_at=expires)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
