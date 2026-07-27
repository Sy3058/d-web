"""2단계 관리자 로그인 + owner 봉쇄 + require_role + 신뢰 기기 테스트 (M1.5 B3).

pending 쿠키는 /admin/login이 발급하고 jar가 자동 운반한다(B2 테스트와 달리 실제 흐름으로
체이닝). 쿠키를 수동 set할 땐 점 있는 호스트 + domain 명시(MISTAKES pytest 절).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pyotp
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import (
    ADMIN_PENDING_COOKIE_NAME,
    TOTP_PENDING,
    TOTP_SETUP_PENDING,
    TRUSTED_DEVICE_COOKIE_NAME,
    access_cookie_name,
    create_admin_pending_token,
    require_owner,
    require_role,
)
from src.lib import totp
from src.lib.totp import encrypt_secret
from src.models.user import RefreshToken, RoleEnum, TrustedDevice, User
from src.services import admin_auth_service, auth_service
from tests.conftest import EXISTING_USER_EMAIL, EXISTING_USER_PASSWORD

LOGIN_URL = "/admin/login"
TOTP_URL = "/admin/login/totp"

OWNER_EMAIL = "admin@example.com"
OWNER_PASSWORD = "Adm1nPass!"
_LOGIN = {"email": OWNER_EMAIL, "password": OWNER_PASSWORD}


@pytest_asyncio.fixture
async def pw_owner(db_session: AsyncSession) -> User:
    """비번 보유 + TOTP 미등록 owner (승격 직후 상태)."""
    user = await auth_service.create_user(OWNER_EMAIL, OWNER_PASSWORD, "관리자", db_session)
    user.role = RoleEnum.OWNER
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def active_owner(pw_owner: User, db_session: AsyncSession) -> tuple[User, str]:
    """TOTP 활성 owner. (user, 시크릿 원문) 튜플."""
    secret = pyotp.random_base32()
    pw_owner.totp_secret = encrypt_secret(secret)
    pw_owner.totp_confirmed_at = datetime.now(UTC)
    db_session.add(pw_owner)
    await db_session.commit()
    await db_session.refresh(pw_owner)
    return pw_owner, secret


def _pending_typ(resp: Response) -> str | None:
    """응답이 set한 pending 쿠키의 typ 클레임. 없으면 None."""
    raw = resp.cookies.get(ADMIN_PENDING_COOKIE_NAME)
    if raw is None:
        return None
    payload = jwt.decode(raw, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return payload["typ"]


def _cleared(resp: Response, cookie_name: str) -> bool:
    """응답이 해당 쿠키를 만료(Max-Age=0)시켰는가."""
    headers = [h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{cookie_name}=")]
    return bool(headers) and "Max-Age=0" in headers[0]


def _wrong_code(secret: str) -> str:
    """valid_window=1(±30s)의 유효 코드 3개를 전부 피한 결정적 오답 (B2 테스트와 동일)."""
    totp_gen = pyotp.TOTP(secret)
    now = datetime.now(UTC)
    valid = {totp_gen.at(now + timedelta(seconds=offset)) for offset in (-30, 0, 30)}
    for candidate in ("000000", "111111", "222222", "333333"):
        if candidate not in valid:
            return candidate
    raise AssertionError("unreachable: 유효 코드는 최대 3개")


async def _trusted_login(client: AsyncClient, secret: str) -> Response:
    """stage1→stage2(remember_device)로 로그인해 jar에 신뢰 쿠키를 심는다."""
    await client.post(LOGIN_URL, json=_LOGIN)
    resp = await client.post(
        TOTP_URL, json={"code": pyotp.TOTP(secret).now(), "remember_device": True}
    )
    assert resp.status_code == 200
    assert resp.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------------
# stage1 비열거 (전부 generic 401)
# ---------------------------------------------------------------------------


async def test_login_unknown_email_401(async_client: AsyncClient):
    resp = await async_client.post(
        LOGIN_URL, json={"email": "nobody@example.com", "password": "Whatever1!"}
    )
    assert resp.status_code == 401


async def test_login_owner_wrong_password_401(async_client: AsyncClient, active_owner):
    resp = await async_client.post(
        LOGIN_URL, json={"email": OWNER_EMAIL, "password": "WrongPass1!"}
    )
    assert resp.status_code == 401


async def test_login_reader_correct_password_401(async_client: AsyncClient, existing_user):
    # 올바른 비번의 일반 유저도 동일 401 - 응답으로 '관리자 계정 여부'를 확인시켜주지 않는다.
    resp = await async_client.post(
        LOGIN_URL, json={"email": EXISTING_USER_EMAIL, "password": EXISTING_USER_PASSWORD}
    )
    assert resp.status_code == 401


async def test_login_deleted_owner_401(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    owner, _ = active_owner
    owner.deleted_at = datetime.now(UTC)
    db_session.add(owner)
    await db_session.commit()
    assert (await async_client.post(LOGIN_URL, json=_LOGIN)).status_code == 401


async def test_login_failures_share_exact_body(
    async_client: AsyncClient, active_owner, existing_user
):
    # 상태코드가 같아도 바디(detail 문구)가 경로별로 다르면 그 차이로 계정 존재가 샌다 -
    # 비열거는 관찰 가능한 모든 차이를 없애야 하므로 바디까지 문자 그대로 고정한다.
    bodies = []
    for payload in (
        {"email": "nobody@example.com", "password": "Whatever1!"},
        {"email": OWNER_EMAIL, "password": "WrongPass1!"},
        {"email": EXISTING_USER_EMAIL, "password": EXISTING_USER_PASSWORD},
    ):
        resp = await async_client.post(LOGIN_URL, json=payload)
        assert resp.status_code == 401
        bodies.append(resp.json())
    assert bodies[0] == bodies[1] == bodies[2]


# ---------------------------------------------------------------------------
# stage1 분기 (setup / totp)
# ---------------------------------------------------------------------------


async def test_login_unenrolled_owner_requires_setup(async_client: AsyncClient, pw_owner):
    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.status_code == 200
    assert resp.json() == {"stage": "totp_setup"}
    assert _pending_typ(resp) == TOTP_SETUP_PENDING
    # 아직 인증 쿠키는 없다(등록·코드 검증 전).
    assert resp.cookies.get(access_cookie_name()) is None


async def test_login_enrolled_owner_requires_totp(async_client: AsyncClient, active_owner):
    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.status_code == 200
    assert resp.json() == {"stage": "totp"}
    assert _pending_typ(resp) == TOTP_PENDING
    assert resp.cookies.get(access_cookie_name()) is None


# ---------------------------------------------------------------------------
# stage2 (/admin/login/totp)
# ---------------------------------------------------------------------------


async def test_totp_login_success(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    owner, secret = active_owner
    await async_client.post(LOGIN_URL, json=_LOGIN)  # pending 쿠키가 jar에 실린다
    resp = await async_client.post(TOTP_URL, json={"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 200

    body = resp.json()
    assert body["role"] == "owner"  # FE 가드용 role 노출 (B3 DoD)
    assert "totp_secret" not in body
    assert resp.cookies.get(access_cookie_name())
    tokens = (
        await db_session.exec(select(RefreshToken).where(RefreshToken.user_id == owner.id))
    ).all()
    assert len(tokens) == 1
    # pending 쿠키는 일회용 소비, remember 미선택이라 신뢰 쿠키는 없다.
    assert _cleared(resp, ADMIN_PENDING_COOKIE_NAME)
    assert resp.cookies.get(TRUSTED_DEVICE_COOKIE_NAME) is None


async def test_totp_login_wrong_code_400(async_client: AsyncClient, active_owner):
    _, secret = active_owner
    await async_client.post(LOGIN_URL, json=_LOGIN)
    resp = await async_client.post(TOTP_URL, json={"code": _wrong_code(secret)})
    assert resp.status_code == 400
    assert resp.cookies.get(access_cookie_name()) is None


async def test_totp_login_without_cookie_401(async_client: AsyncClient, active_owner):
    resp = await async_client.post(TOTP_URL, json={"code": "123456"})
    assert resp.status_code == 401


async def test_totp_login_with_setup_cookie_401(async_client: AsyncClient, active_owner):
    # 등록 흐름 쿠키(totp_setup_pending)로는 로그인 2단계를 통과할 수 없다(typ 정확 대조).
    owner, secret = active_owner
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME,
        create_admin_pending_token(str(owner.id), TOTP_SETUP_PENDING),
        domain="test.example",
        path="/admin",
    )
    resp = await async_client.post(TOTP_URL, json={"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 401


async def test_totp_login_survives_backward_clock_jump(async_client: AsyncClient, active_owner):
    """pending 쿠키 발급 직후 시계가 뒤로 점프해도 2단계가 통과해야 한다 (JWT leeway).

    실측 사고(2026-07-27): 스위트 도중 WSL2/NTP 보정으로 시계가 ~1.9초 역행하자 stage1이
    발급한 pending JWT의 iat가 "미래"가 돼 PyJWT가 ImmatureSignatureError로 거부, stage2가
    무작위 401이 됐다. iat를 5초 미래로 박은 쿠키(= 역점프 후 검증하는 상황)로 그 사고를
    결정적으로 재현한다.
    """
    owner, secret = active_owner
    with patch("src.lib.auth.datetime") as mock_dt:
        mock_dt.now.return_value = datetime.now(UTC) + timedelta(seconds=5)
        pending = create_admin_pending_token(str(owner.id), TOTP_PENDING)
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME, pending, domain="test.example", path="/admin"
    )
    resp = await async_client.post(TOTP_URL, json={"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 200


async def test_totp_login_demoted_after_stage1_401(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    # pending 발급 후 강등되면 2단계에서 DB 재확인이 막는다(쿠키는 신원 운반만).
    owner, secret = active_owner
    await async_client.post(LOGIN_URL, json=_LOGIN)
    owner.role = RoleEnum.READER
    db_session.add(owner)
    await db_session.commit()
    resp = await async_client.post(TOTP_URL, json={"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TOTP replay 가드 (#56 - totp_last_step 엄격 증가)
# ---------------------------------------------------------------------------


async def test_totp_login_replay_rejected_400(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    # 같은 창의 유효 코드도 재제출이면 거부 - 판정 기준은 코드 유효성이 아니라 step 소모다.
    owner, secret = active_owner
    code = pyotp.TOTP(secret).now()
    await async_client.post(LOGIN_URL, json=_LOGIN)
    assert (await async_client.post(TOTP_URL, json={"code": code})).status_code == 200
    await db_session.refresh(owner)
    assert owner.totp_last_step is not None

    await async_client.post(LOGIN_URL, json=_LOGIN)  # 새 pending 쿠키
    resp = await async_client.post(TOTP_URL, json={"code": code})
    assert resp.status_code == 400
    assert resp.cookies.get(access_cookie_name()) is None


async def test_totp_login_next_step_code_passes(
    async_client: AsyncClient, active_owner, monkeypatch
):
    # 엄격 증가 가드가 정상 재로그인(다음 창의 새 코드)까지 막지 않는다.
    # 서버 검증 시각을 고정해 30s 경계·CI 스톨에 비의존으로 만든다(형제 단위 테스트와 동일
    # 기법 - async_client는 같은 프로세스라 totp.datetime 몽키패치가 서버 verify_code에 적용됨).
    _, secret = active_owner
    otp = pyotp.TOTP(secret)
    base = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
    clock = {"now": base}

    class _FrozenDatetime:
        @staticmethod
        def now(tz: object) -> datetime:
            return clock["now"]

    monkeypatch.setattr(totp, "datetime", _FrozenDatetime)

    await async_client.post(LOGIN_URL, json=_LOGIN)
    assert (await async_client.post(TOTP_URL, json={"code": otp.at(base)})).status_code == 200

    clock["now"] = base + timedelta(seconds=30)
    await async_client.post(LOGIN_URL, json=_LOGIN)
    resp = await async_client.post(TOTP_URL, json={"code": otp.at(clock["now"])})
    assert resp.status_code == 200


async def test_confirm_code_not_reusable_for_login(async_client: AsyncClient, pw_owner: User):
    # confirm(등록)과 login(2단계)은 같은 totp_last_step을 공유한다 - 등록에 쓴 코드를
    # 그대로 로그인 2단계에 재사용할 수 없다(cross-endpoint replay).
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME,
        create_admin_pending_token(str(pw_owner.id), TOTP_SETUP_PENDING),
        domain="test.example",
        path="/admin",
    )
    setup = await async_client.post("/admin/2fa/setup")
    secret = pyotp.parse_uri(setup.json()["otpauth_uri"]).secret
    code = pyotp.TOTP(secret).now()
    assert (await async_client.post("/admin/2fa/confirm", json={"code": code})).status_code == 200

    await async_client.post(LOGIN_URL, json=_LOGIN)
    assert (await async_client.post(TOTP_URL, json={"code": code})).status_code == 400


async def test_accept_totp_concurrent_single_winner(active_owner, session_factory):
    # 같은 코드 동시 제출(TOCTOU) - 조건부 UPDATE 선점이 정확히 한쪽만 승자로 만든다.
    # 두 세션 모두 stale last_step(NULL)을 읽어 코드 검증은 통과하지만, 전진 UPDATE는
    # 행 락 + READ COMMITTED 재평가로 패자가 rowcount 0을 받는다(refresh 회전 I4와 동일).
    owner, secret = active_owner
    code = pyotp.TOTP(secret).now()

    async def attempt() -> bool:
        async with session_factory() as s:
            u = (await s.exec(select(User).where(User.id == owner.id))).one()
            ok = await admin_auth_service._accept_totp(u, code, s)
            if ok:
                await s.commit()
            else:
                await s.rollback()
            return ok

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == [False, True]


# ---------------------------------------------------------------------------
# 신뢰 기기 ("이 기기에서 2단계 인증 생략")
# ---------------------------------------------------------------------------


async def test_remember_device_sets_cookie_and_hashed_row(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    owner, secret = active_owner
    resp = await _trusted_login(async_client, secret)
    raw = resp.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
    rows = (
        await db_session.exec(select(TrustedDevice).where(TrustedDevice.user_id == owner.id))
    ).all()
    assert len(rows) == 1
    assert rows[0].token_hash != raw  # DB엔 원문이 아니라 HMAC 해시
    assert rows[0].revoked_at is None


async def test_trusted_device_skips_totp(async_client: AsyncClient, active_owner):
    _, secret = active_owner
    await _trusted_login(async_client, secret)
    # 재로그인: jar의 신뢰 쿠키로 TOTP 생략, pending 쿠키도 발급되지 않는다.
    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.status_code == 200
    assert resp.json() == {"stage": "complete"}
    assert resp.cookies.get(access_cookie_name())
    assert resp.cookies.get(ADMIN_PENDING_COOKIE_NAME) is None


async def test_trusted_device_wrong_password_still_401(async_client: AsyncClient, active_owner):
    # 신뢰 쿠키는 TOTP만 대체한다 - 비번이 틀리면 쿠키가 있어도 401.
    _, secret = active_owner
    await _trusted_login(async_client, secret)
    resp = await async_client.post(
        LOGIN_URL, json={"email": OWNER_EMAIL, "password": "WrongPass1!"}
    )
    assert resp.status_code == 401
    assert resp.cookies.get(access_cookie_name()) is None


async def test_expired_trusted_device_falls_back_and_clears(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    owner, secret = active_owner
    await _trusted_login(async_client, secret)
    row = (
        await db_session.exec(select(TrustedDevice).where(TrustedDevice.user_id == owner.id))
    ).one()
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.add(row)
    await db_session.commit()

    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.json() == {"stage": "totp"}
    # 죽은 신뢰 쿠키는 위생 정리(만료)된다.
    assert _cleared(resp, TRUSTED_DEVICE_COOKIE_NAME)


async def test_revoked_trusted_device_falls_back(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    owner, secret = active_owner
    await _trusted_login(async_client, secret)
    row = (
        await db_session.exec(select(TrustedDevice).where(TrustedDevice.user_id == owner.id))
    ).one()
    row.revoked_at = datetime.now(UTC)
    db_session.add(row)
    await db_session.commit()
    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.json() == {"stage": "totp"}


async def test_reenrollment_invalidates_trusted_devices(
    async_client: AsyncClient, active_owner, db_session: AsyncSession
):
    # TOTP 재등록(totp_confirmed_at 갱신) -> created_at < confirmed_at이 된 옛 신뢰 자동 실효.
    owner, secret = active_owner
    await _trusted_login(async_client, secret)
    owner.totp_confirmed_at = datetime.now(UTC)
    db_session.add(owner)
    await db_session.commit()
    resp = await async_client.post(LOGIN_URL, json=_LOGIN)
    assert resp.json() == {"stage": "totp"}


async def test_confirm_with_remember_sets_trusted_cookie(
    async_client: AsyncClient, pw_owner, db_session: AsyncSession
):
    # 등록(confirm) 시점에도 remember_device 옵트인이 동작한다(B2 엔드포인트 확장).
    async_client.cookies.set(
        ADMIN_PENDING_COOKIE_NAME,
        create_admin_pending_token(str(pw_owner.id), TOTP_SETUP_PENDING),
        domain="test.example",
        path="/admin",
    )
    setup = await async_client.post("/admin/2fa/setup")
    secret = pyotp.parse_uri(setup.json()["otpauth_uri"]).secret
    resp = await async_client.post(
        "/admin/2fa/confirm", json={"code": pyotp.TOTP(secret).now(), "remember_device": True}
    )
    assert resp.status_code == 200
    assert resp.cookies.get(TRUSTED_DEVICE_COOKIE_NAME)
    rows = (
        await db_session.exec(select(TrustedDevice).where(TrustedDevice.user_id == pw_owner.id))
    ).all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# owner 세션 발급 지점 봉쇄 (/auth/login)
# ---------------------------------------------------------------------------


async def test_auth_login_blocks_active_owner(async_client: AsyncClient, active_owner):
    # owner는 일반 로그인으로 세션을 열 수 없다(2FA 우회 공백 봉쇄). 응답은 generic 401.
    resp = await async_client.post("/auth/login", json=_LOGIN)
    assert resp.status_code == 401
    assert resp.cookies.get(access_cookie_name()) is None


async def test_auth_login_blocks_unenrolled_owner(async_client: AsyncClient, pw_owner):
    # TOTP 등록 전이어도 owner는 일반 로그인 불가 - 등록은 /admin/login 경유로만.
    resp = await async_client.post("/auth/login", json=_LOGIN)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# require_role / require_owner (의존성 단위 테스트 - 라우터 부착은 C1)
# ---------------------------------------------------------------------------


async def test_require_owner_rejects_reader(user: User):
    with pytest.raises(HTTPException) as exc:
        await require_owner(user)
    assert exc.value.status_code == 403


async def test_require_owner_rejects_unenrolled_owner(pw_owner: User):
    # 승격 직후(totp_confirmed_at NULL) 잔존 세션 창 차단 - 등록 완료 전엔 owner 권한 없음.
    with pytest.raises(HTTPException) as exc:
        await require_owner(pw_owner)
    assert exc.value.status_code == 403


async def test_require_owner_passes_active_owner(active_owner):
    owner, _ = active_owner
    assert await require_owner(owner) is owner


async def test_require_role_moderator_exempt_from_totp_rule(db_session: AsyncSession):
    # owner-TOTP 보조 규칙은 owner에만 적용 - moderator(M4, 2FA 정책 미정)는 통과.
    mod = User(email="mod@example.com", nickname="mod", role=RoleEnum.MODERATOR)
    db_session.add(mod)
    await db_session.commit()
    await db_session.refresh(mod)
    guard = require_role(RoleEnum.OWNER, RoleEnum.MODERATOR)
    assert await guard(mod) is mod


# ---------------------------------------------------------------------------
# rate limit (scope 분리)
# ---------------------------------------------------------------------------


async def test_admin_login_rate_limited(async_client: AsyncClient):
    payload = {"email": "nobody@example.com", "password": "Whatever1!"}
    for _ in range(5):
        assert (await async_client.post(LOGIN_URL, json=payload)).status_code == 401
    assert (await async_client.post(LOGIN_URL, json=payload)).status_code == 429


async def test_admin_login_totp_rate_limited(async_client: AsyncClient):
    for _ in range(5):
        assert (await async_client.post(TOTP_URL, json={"code": "123456"})).status_code == 401
    assert (await async_client.post(TOTP_URL, json={"code": "123456"})).status_code == 429
