"""토큰 발급/검증 단위 테스트 (M1 B2).

JWT 테스트(순수 함수, DB 불필요) + refresh 프리미티브 테스트(db_session 픽스처 사용).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from src.config import settings
from src.lib.auth import TokenError, create_access_token, decode_token
from src.lib.exceptions import InvalidTokenError
from src.models.user import RefreshToken
from src.services import auth_service
from src.services.auth_service import (
    _claim_refresh_token,
    create_refresh_token,
    get_refresh_token,
    revoke_all_refresh_tokens,
    revoke_refresh_token,
    rotate_refresh,
)

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


async def test_backward_clock_jump_within_leeway_accepted():
    """iat가 약간 미래인 토큰(= 발급 직후 시계 역점프)은 leeway 안에서 통과해야 한다.

    같은 서버라도 NTP/WSL2 보정으로 시계가 뒤로 점프할 수 있다(2026-07-27 스위트 도중
    ~1.9초 역행 실측 - PG 로그 타임스탬프 역전). leeway가 없으면 PyJWT가
    ImmatureSignatureError로 거부해, 방금 발급된 토큰을 쓰는 요청 하나가 무작위로
    401이 된다. JWT_LEEWAY_SECONDS(auth.py)가 이를 흡수한다.
    """
    user_id = str(uuid.uuid4())
    with patch("src.lib.auth.datetime") as mock_dt:
        # 발급 시각을 5초 미래로 - 역점프 직후 검증하는 상황의 재현(leeway 10초 이내)
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(seconds=5)
        token = create_access_token(user_id)
    assert decode_token(token)["sub"] == user_id


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


async def test_refresh_token_round_trip(db_session, user):
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert record.user_id == user.id
    assert record.revoked_at is None


async def test_refresh_token_hash_not_raw(db_session, user):
    """DB에 저장된 값이 원문 토큰이 아닌 해시여야 한다."""
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert record.token_hash != raw


async def test_revoke_single(db_session, user):
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    await revoke_refresh_token(record, db_session)

    refreshed = await get_refresh_token(raw, db_session)
    assert refreshed is not None
    assert refreshed.revoked_at is not None


async def test_get_returns_revoked_record(db_session, user):
    """revoke된 행도 반환해야 C4 재사용 탐지가 'None(없음)'과 '이미 revoke됨'을 구분 가능."""
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    await revoke_refresh_token(record, db_session)

    result = await get_refresh_token(raw, db_session)
    assert result is not None  # None이 아니라 revoked 행을 돌려줘야 함
    assert result.revoked_at is not None


async def test_unknown_token_returns_none(db_session):
    """존재하지 않는 토큰은 None."""
    result = await get_refresh_token("nonexistent-token", db_session)
    assert result is None


async def test_revoke_all(db_session, user):
    raw1 = await create_refresh_token(user.id, db_session)
    raw2 = await create_refresh_token(user.id, db_session)

    await revoke_all_refresh_tokens(user.id, db_session)

    r1 = await get_refresh_token(raw1, db_session)
    r2 = await get_refresh_token(raw2, db_session)
    assert r1 is not None and r1.revoked_at is not None
    assert r2 is not None and r2.revoked_at is not None


# ---------------------------------------------------------------------------
# 회전 원자화 (M1 I1)
# ---------------------------------------------------------------------------


async def test_claim_refresh_token_single_winner(db_session, user):
    """동시 회전의 결정적 프록시: 같은 토큰을 두 번 선점하면 1회차만 성공(True),
    2회차는 이미 revoked라 0행 매칭(False) → 한 토큰에서 새 토큰 2개 발급 차단.

    같은 트랜잭션 내 첫 UPDATE가 revoked_at을 세팅하면 둘째 UPDATE는
    revoked_at IS NULL 조건에 0행 매칭(자기 트랜잭션의 미커밋 변경을 본다).
    """
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)

    assert await _claim_refresh_token(record, db_session) is True
    assert await _claim_refresh_token(record, db_session) is False


async def test_refresh_token_hash_unique(db_session, user):
    """token_hash UNIQUE 인덱스가 같은 해시 중복 INSERT를 차단(회전 불변식 방어선)."""
    expires = datetime.now(UTC) + timedelta(days=7)
    issued = datetime.now(UTC)
    db_session.add(
        RefreshToken(
            user_id=user.id, token_hash="dup-hash", expires_at=expires, original_issued_at=issued
        )
    )
    await db_session.flush()
    db_session.add(
        RefreshToken(
            user_id=user.id, token_hash="dup-hash", expires_at=expires, original_issued_at=issued
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_concurrent_rotation_single_winner(db_session, user, session_factory, monkeypatch):
    """실측 동시성: 같은 refresh 토큰으로 두 독립 세션(커넥션 분리)이 동시에 rotate_refresh를
    호출하면 DB 행 락 + READ COMMITTED 재평가로 정확히 하나만 새 토큰을 발급하고 나머지는
    거부된다. I1의 _claim 프록시 테스트(단일 세션)가 못 메운 실제 동시성을 검증한다.

    asyncio.Barrier로 두 코루틴이 SELECT를 마친 시점에 _claim UPDATE를 동시 발사하도록 강제해
    직렬화를 막는다(둘 다 revoked_at IS NULL을 본 진짜 race). 따라서 패자는 stale-reuse가
    아니라 _claim 패배 → 세션 유지하는 InvalidTokenError(TokenReuseError 서브클래스 아님)다.
    """
    raw = await create_refresh_token(user.id, db_session)
    await db_session.commit()  # 다른 커넥션이 보도록 커밋

    barrier = asyncio.Barrier(2)
    real_claim = _claim_refresh_token

    async def claim_after_barrier(record, session):
        # 두 세션의 SELECT가 모두 끝난 뒤 UPDATE를 동시 발사(진짜 행 락 경쟁 유도)
        await barrier.wait()
        return await real_claim(record, session)

    monkeypatch.setattr(auth_service, "_claim_refresh_token", claim_after_barrier)

    async def rotate():
        async with session_factory() as session:
            return await auth_service.rotate_refresh(raw, session)

    results = await asyncio.gather(rotate(), rotate(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 1
    # 패자는 동시 회전 정상 케이스(탈취 아님) → 세션 유지 InvalidTokenError(stale-reuse 아님)
    assert type(failures[0]) is InvalidTokenError

    # 한 옛 토큰에서 새 토큰이 정확히 1개만 발급(이중 발급 없음) + 세션 유지 확인
    async with session_factory() as verify:
        result = await verify.exec(select(RefreshToken).where(RefreshToken.user_id == user.id))
        rows = result.all()
    active = [r for r in rows if r.revoked_at is None]
    assert len(active) == 1


# ---------------------------------------------------------------------------
# 절대 수명 cap (M1 A)
# ---------------------------------------------------------------------------


async def test_create_sets_original_issued_at_to_now(db_session, user):
    """최초 발급(original_issued_at 미지정)은 그 값을 now로 설정한다."""
    before = datetime.now(UTC)
    raw = await create_refresh_token(user.id, db_session)
    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert before <= record.original_issued_at <= datetime.now(UTC)


async def test_rotate_inherits_original_issued_at(db_session, user):
    """회전된 새 토큰은 부모의 original_issued_at을 승계한다(회전해도 cap 기준점 불변)."""
    raw = await create_refresh_token(user.id, db_session)
    parent = await get_refresh_token(raw, db_session)
    parent_issued = parent.original_issued_at
    await db_session.commit()

    _user, _access, new_raw = await rotate_refresh(raw, db_session)
    new_record = await get_refresh_token(new_raw, db_session)
    assert new_record is not None
    assert new_record.original_issued_at == parent_issued


async def test_rotate_rejected_past_absolute_cap(db_session, user):
    """original_issued_at이 절대 수명 상한을 넘으면 회전을 거부(InvalidTokenError)한다.
    만료 전이라도 cap이 우선이다.

    토큰을 revoke하지 않는다(의도): cap이 회전을 영구 거부하므로 revoke는 불필요하고,
    revoke하면 재제출이 stale-reuse로 오분류돼 다른 기기 세션까지 끊긴다. 거부만 하면
    재제출도 일관되게 cap에서 막히고 다른 세션은 보존된다.

    sabotage-proof: cap 분기가 없으면 회전이 성공해 InvalidTokenError가 안 나고 assert 실패.
    """
    old = datetime.now(UTC) - timedelta(days=settings.jwt_refresh_absolute_max_days + 1)
    raw = await create_refresh_token(user.id, db_session, original_issued_at=old)
    await db_session.commit()

    with pytest.raises(InvalidTokenError):
        await rotate_refresh(raw, db_session)

    record = await get_refresh_token(raw, db_session)
    assert record is not None
    assert record.revoked_at is None  # cap 거부는 revoke하지 않음(다른 세션 보존)


async def test_rotate_past_cap_does_not_revoke_other_sessions(db_session, user):
    """cap 거부는 같은 토큰이 재제출돼도 stale-reuse(재사용 탐지)로 번지지 않아 다른 기기
    세션을 보존한다. cap 분기가 토큰을 revoke하면 재제출이 revoke_all로 번져 이 테스트가 깨진다.
    """
    old = datetime.now(UTC) - timedelta(days=settings.jwt_refresh_absolute_max_days + 1)
    capped = await create_refresh_token(user.id, db_session, original_issued_at=old)
    other = await create_refresh_token(user.id, db_session)  # 다른 기기, cap 전(now)
    await db_session.commit()

    # cap 토큰 회전 거부 + 같은 토큰 재제출(모바일 재시도·두 탭) - 둘 다 InvalidTokenError.
    # cap 분기가 revoke했다면 둘째 호출은 revoked 토큰을 stale-reuse로 보고 TokenReuseError를
    # 던지므로(InvalidTokenError 서브클래스 아님) pytest.raises가 못 잡아 테스트가 깨진다.
    with pytest.raises(InvalidTokenError):
        await rotate_refresh(capped, db_session)
    with pytest.raises(InvalidTokenError):
        await rotate_refresh(capped, db_session)

    # 다른 기기 세션은 revoke되지 않고 살아있어야 한다(cap 거부가 세션 전체로 번지지 않음).
    other_record = await get_refresh_token(other, db_session)
    assert other_record is not None
    assert other_record.revoked_at is None
