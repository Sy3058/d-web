"""TOTP 등록(enrollment) 엔드포인트 테스트 (M1.5 B2).

게이트 쿠키(totp_setup_pending)는 B3 /admin/login이 발급하지만, 계약의 단일 출처는
lib/auth.py create_admin_pending_token이라 테스트가 직접 발급해 게이트를 검증한다.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pyotp
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import (
    ADMIN_PENDING_COOKIE_NAME,
    TOTP_PENDING,
    TOTP_SETUP_PENDING,
    access_cookie_name,
    create_admin_pending_token,
)
from src.lib.totp import decrypt_secret
from src.models.user import RefreshToken, RoleEnum, User

SETUP_URL = "/admin/2fa/setup"
CONFIRM_URL = "/admin/2fa/confirm"


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    u = User(email="2fa-owner@example.com", nickname="owner", role=RoleEnum.OWNER)
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


def _set_pending(client: AsyncClient, user: User, typ: str = TOTP_SETUP_PENDING) -> None:
    # 점 있는 호스트 + domain 명시: 점 없는 호스트는 cookiejar 도메인 매칭이 깨져
    # 쿠키가 미전송된다(MISTAKES pytest 절).
    client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME,
        create_admin_pending_token(str(user.id), typ),
        domain="test.example",
        path="/admin",
    )


def _wrong_code(secret: str) -> str:
    """valid_window=1(±30s)의 유효 코드 3개를 전부 피한 결정적 오답."""
    totp_gen = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    valid = {totp_gen.at(now + timedelta(seconds=offset)) for offset in (-30, 0, 30)}
    for candidate in ("000000", "111111", "222222", "333333"):
        if candidate not in valid:
            return candidate
    raise AssertionError("unreachable: 유효 코드는 최대 3개")


async def _enroll(client: AsyncClient, owner: User) -> str:
    """setup을 통과시키고 provisioning URI에서 시크릿 원문을 추출한다."""
    _set_pending(client, owner)
    response = await client.post(SETUP_URL)
    assert response.status_code == 200
    return pyotp.parse_uri(response.json()["otpauth_uri"]).secret


# ---------------------------------------------------------------------------
# 게이트 (비열거 - 전부 generic 401)
# ---------------------------------------------------------------------------


async def test_setup_without_cookie_401(async_client: AsyncClient):
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_confirm_without_cookie_401(async_client: AsyncClient):
    response = await async_client.post(CONFIRM_URL, json={"code": "123456"})
    assert response.status_code == 401


async def test_setup_forged_cookie_401(async_client: AsyncClient, owner: User):
    forged = jwt.encode(
        {
            "sub": str(owner.id),
            "typ": TOTP_SETUP_PENDING,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "wrong-secret-0123456789abcdef0123456789abcdef",
        algorithm=settings.jwt_algorithm,
    )
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME, forged, domain="test.example", path="/admin"
    )
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_setup_expired_cookie_401(async_client: AsyncClient, owner: User):
    expired = jwt.encode(
        {
            "sub": str(owner.id),
            "typ": TOTP_SETUP_PENDING,
            "iat": datetime.now(UTC) - timedelta(minutes=20),
            "exp": datetime.now(UTC) - timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME, expired, domain="test.example", path="/admin"
    )
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_setup_wrong_typ_401(async_client: AsyncClient, owner: User):
    # 로그인 흐름 쿠키(totp_pending)로는 등록 엔드포인트를 통과할 수 없다.
    _set_pending(async_client, owner, typ=TOTP_PENDING)
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_setup_reader_401(async_client: AsyncClient, user: User):
    # 서명이 유효해도 DB role 재확인에서 막힌다(reader).
    _set_pending(async_client, user)
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_setup_deleted_owner_401(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    owner.deleted_at = datetime.now(UTC)
    db_session.add(owner)
    await db_session.commit()
    _set_pending(async_client, owner)
    assert (await async_client.post(SETUP_URL)).status_code == 401


async def test_active_owner_blocked_from_reenroll(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    # 활성화 완료 후엔 setup/confirm 모두 게이트가 차단한다(재등록은 DB 직접 조작으로만).
    secret = await _enroll(async_client, owner)
    code = pyotp.TOTP(secret).now()
    assert (await async_client.post(CONFIRM_URL, json={"code": code})).status_code == 200

    _set_pending(async_client, owner)
    assert (await async_client.post(SETUP_URL)).status_code == 401
    assert (await async_client.post(CONFIRM_URL, json={"code": code})).status_code == 401


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


async def test_setup_stores_ciphertext_and_returns_uri(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    _set_pending(async_client, owner)
    response = await async_client.post(SETUP_URL)
    assert response.status_code == 200

    body = response.json()
    # 응답엔 otpauth_uri 하나만 - raw 시크릿 별도 필드 노출 금지.
    assert set(body.keys()) == {"otpauth_uri"}
    uri = body["otpauth_uri"]
    assert uri.startswith("otpauth://totp/")
    assert settings.totp_issuer in uri

    secret = pyotp.parse_uri(uri).secret
    await db_session.refresh(owner)
    # DB엔 평문이 아닌 Fernet 암호문 - 복호하면 URI의 시크릿과 일치.
    assert owner.totp_secret != secret
    assert decrypt_secret(owner.totp_secret) == secret
    assert owner.totp_confirmed_at is None


async def test_setup_retry_regenerates_secret(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    # QR 분실 재시도: 미확인 상태의 재호출은 새 시크릿으로 덮어쓴다.
    first = await _enroll(async_client, owner)
    second = await _enroll(async_client, owner)
    assert first != second
    await db_session.refresh(owner)
    assert decrypt_secret(owner.totp_secret) == second


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


async def test_confirm_activates_and_logs_in(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    secret = await _enroll(async_client, owner)
    response = await async_client.post(CONFIRM_URL, json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == owner.email
    assert "totp_secret" not in body

    await db_session.refresh(owner)
    assert owner.totp_confirmed_at is not None

    # 바로 로그인: 인증 쿠키(access/refresh) 발급 + refresh_tokens insert.
    assert response.cookies.get(access_cookie_name())
    tokens = (
        await db_session.exec(select(RefreshToken).where(RefreshToken.user_id == owner.id))
    ).all()
    assert len(tokens) == 1

    # pending 쿠키는 일회용으로 소비(clear)된다.
    cleared = [
        h
        for h in response.headers.get_list("set-cookie")
        if h.startswith(f"{ADMIN_PENDING_COOKIE_NAME}=")
    ]
    assert cleared and "Max-Age=0" in cleared[0]


async def test_confirm_wrong_code_400(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    secret = await _enroll(async_client, owner)
    response = await async_client.post(CONFIRM_URL, json={"code": _wrong_code(secret)})
    assert response.status_code == 400

    await db_session.refresh(owner)
    assert owner.totp_confirmed_at is None
    # 실패 시 인증 쿠키를 발급하지 않는다.
    assert response.cookies.get(access_cookie_name()) is None


async def test_confirm_without_setup_400(async_client: AsyncClient, owner: User):
    # 게이트는 통과(미활성 owner)하지만 시크릿이 없어 검증 불가.
    _set_pending(async_client, owner)
    response = await async_client.post(CONFIRM_URL, json={"code": "123456"})
    assert response.status_code == 400


async def test_confirm_malformed_code_422(async_client: AsyncClient, owner: User):
    _set_pending(async_client, owner)
    for bad in ("12345", "1234567", "12345a", ""):
        response = await async_client.post(CONFIRM_URL, json={"code": bad})
        assert response.status_code == 422


async def test_setup_resets_stale_last_step(
    async_client: AsyncClient, owner: User, db_session: AsyncSession
):
    # 수동 복구는 totp_last_step까지 NULL이 규칙이지만(models/user.py), 빠뜨려도 setup이
    # 리셋해 재등록 confirm이 replay로 오거부되지 않는다(#56 자가치유).
    owner.totp_last_step = 10**10  # 어떤 현재 step보다 큰 잔재(최악 케이스)
    db_session.add(owner)
    await db_session.commit()

    secret = await _enroll(async_client, owner)
    response = await async_client.post(CONFIRM_URL, json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# rate limit
# ---------------------------------------------------------------------------


async def test_setup_rate_limited(async_client: AsyncClient):
    # 게이트보다 rate limit이 먼저 - 쿠키 없이도 6번째는 429.
    for _ in range(5):
        assert (await async_client.post(SETUP_URL)).status_code == 401
    assert (await async_client.post(SETUP_URL)).status_code == 429
