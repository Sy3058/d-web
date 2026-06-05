"""인증 엔드포인트 통합 테스트 (M1 C 그룹).

TestClient는 자체 이벤트 루프라 session-scope async db_session(asyncpg)과 루프가
어긋난다(MISTAKES "different loop"). httpx ASGITransport로 같은 루프에서 앱을 돌린다.
HIBP/이메일 발송은 외부 의존이라 mock으로 대체한다.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import (
    REFRESH_COOKIE_NAME,
    access_cookie_name,
    create_access_token,
    require_verified_email,
)
from src.lib.db import get_session
from src.main import app
from src.models.user import EmailVerification, RefreshToken, User
from src.services import auth_service, email_service, hibp

_CREDS = {"email": "user@example.com", "password": "Passw0rd!", "nickname": "tester"}
_LOGIN = {"email": _CREDS["email"], "password": _CREDS["password"]}


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test.example") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def externals(monkeypatch) -> SimpleNamespace:
    """HIBP(기본 False) + 이메일 발송 함수를 mock. 호출 검증용 핸들 반환."""
    verification = AsyncMock()
    already = AsyncMock()
    monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=False))
    monkeypatch.setattr(email_service, "send_verification_email", verification)
    monkeypatch.setattr(email_service, "send_already_registered_email", already)
    return SimpleNamespace(verification=verification, already=already, monkeypatch=monkeypatch)


@pytest_asyncio.fixture
async def existing_user(db_session: AsyncSession) -> User:
    user = await auth_service.create_user(
        _CREDS["email"], _CREDS["password"], _CREDS["nickname"], db_session
    )
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def social_user(db_session: AsyncSession) -> User:
    user = User(
        email="social@example.com",
        hashed_password=None,
        nickname="social",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


def _set_cookie_value(response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(name + "="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


async def _refresh_tokens(session: AsyncSession, user_id) -> list[RefreshToken]:
    result = await session.exec(
        select(RefreshToken).where(RefreshToken.user_id == user_id)
    )
    return list(result.all())


# --- C1 회원가입 ------------------------------------------------------------


async def test_signup_new_creates_unverified_user(async_client, db_session, externals):
    resp = await async_client.post(
        "/auth/signup",
        json={"email": "New@Example.com", "password": "Passw0rd!", "nickname": "n"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "입력하신 주소로 메일을 보냈어요"

    users = (
        await db_session.exec(select(User).where(User.email == "new@example.com"))
    ).all()
    assert len(users) == 1
    assert users[0].is_email_verified is False
    assert len((await db_session.exec(select(EmailVerification))).all()) == 1
    externals.verification.assert_awaited_once()
    externals.already.assert_not_awaited()


async def test_signup_duplicate_is_indistinguishable(
    async_client, db_session, existing_user, externals
):
    resp = await async_client.post(
        "/auth/signup",
        json={"email": "user@example.com", "password": "Passw0rd!", "nickname": "x"},
    )
    # 비열거: 신규와 동일 응답
    assert resp.status_code == 200
    assert resp.json()["message"] == "입력하신 주소로 메일을 보냈어요"
    # user 추가 생성 없음
    users = (
        await db_session.exec(select(User).where(User.email == "user@example.com"))
    ).all()
    assert len(users) == 1
    externals.already.assert_awaited_once()
    externals.verification.assert_not_awaited()


async def test_signup_weak_password_rejected(async_client):
    resp = await async_client.post(
        "/auth/signup",
        json={"email": "weak@example.com", "password": "short", "nickname": "n"},
    )
    assert resp.status_code == 422


async def test_signup_pwned_password_rejected(async_client, externals):
    externals.monkeypatch.setattr(hibp, "is_password_pwned", AsyncMock(return_value=True))
    resp = await async_client.post(
        "/auth/signup",
        json={"email": "pwned@example.com", "password": "Passw0rd!", "nickname": "n"},
    )
    assert resp.status_code == 422


# --- C2 로그인 --------------------------------------------------------------


async def test_login_success_sets_cookies(async_client, db_session, existing_user):
    resp = await async_client.post("/auth/login", json=_LOGIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == _CREDS["email"]
    assert "hashed_password" not in body

    set_cookies = resp.headers.get_list("set-cookie")
    assert any(c.startswith(access_cookie_name() + "=") for c in set_cookies)
    assert any(c.startswith(REFRESH_COOKIE_NAME + "=") for c in set_cookies)
    # refresh_tokens 행 발급됨
    assert len(await _refresh_tokens(db_session, existing_user.id)) == 1


async def test_login_wrong_password_generic_401(async_client, existing_user):
    resp = await async_client.post(
        "/auth/login", json={"email": _CREDS["email"], "password": "WrongPass1!"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "이메일 또는 비밀번호가 올바르지 않습니다"


async def test_login_unknown_email_same_message(async_client):
    resp = await async_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "Whatever1!"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "이메일 또는 비밀번호가 올바르지 않습니다"


async def test_login_social_only_account_rejected(async_client, social_user):
    resp = await async_client.post(
        "/auth/login", json={"email": "social@example.com", "password": "Whatever1!"}
    )
    assert resp.status_code == 401


# --- C5 /auth/me ------------------------------------------------------------


async def test_me_returns_current_user(async_client, existing_user):
    token = create_access_token(str(existing_user.id))
    async_client.cookies.set(access_cookie_name(), token, domain="test.example")
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == _CREDS["email"]
    assert "hashed_password" not in body


async def test_me_without_cookie_401(async_client):
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token_401(async_client):
    async_client.cookies.set(access_cookie_name(), "garbage", domain="test.example")
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 401


# --- C3 로그아웃 ------------------------------------------------------------


async def test_logout_revokes_all_sessions(async_client, db_session, existing_user):
    await async_client.post("/auth/login", json=_LOGIN)
    token = create_access_token(str(existing_user.id))
    async_client.cookies.clear()
    async_client.cookies.set(access_cookie_name(), token, domain="test.example")
    resp = await async_client.post("/auth/logout")
    assert resp.status_code == 200

    rows = await _refresh_tokens(db_session, existing_user.id)
    assert rows
    assert all(r.revoked_at is not None for r in rows)


# --- C4 토큰 갱신 -----------------------------------------------------------


async def test_refresh_rotates_token(async_client, db_session, existing_user):
    login = await async_client.post("/auth/login", json=_LOGIN)
    old_raw = _set_cookie_value(login, REFRESH_COOKIE_NAME)
    async_client.cookies.clear()
    async_client.cookies.set(REFRESH_COOKIE_NAME, old_raw, domain="test.example")

    resp = await async_client.post("/auth/refresh")
    assert resp.status_code == 200

    rows = await _refresh_tokens(db_session, existing_user.id)
    assert len(rows) == 2
    assert sum(1 for r in rows if r.revoked_at is not None) == 1
    assert sum(1 for r in rows if r.revoked_at is None) == 1


async def test_refresh_reuse_revokes_session(async_client, db_session, existing_user):
    login = await async_client.post("/auth/login", json=_LOGIN)
    old_raw = _set_cookie_value(login, REFRESH_COOKIE_NAME)
    async_client.cookies.clear()
    async_client.cookies.set(REFRESH_COOKIE_NAME, old_raw, domain="test.example")

    first = await async_client.post("/auth/refresh")
    assert first.status_code == 200
    async_client.cookies.clear()
    async_client.cookies.set(REFRESH_COOKIE_NAME, old_raw, domain="test.example")

    # 이미 회전 지난(revoked) 토큰 재제출 → 탈취 신호
    reuse = await async_client.post("/auth/refresh")
    assert reuse.status_code == 401

    rows = await _refresh_tokens(db_session, existing_user.id)
    assert all(r.revoked_at is not None for r in rows)


async def test_refresh_without_cookie_401(async_client):
    resp = await async_client.post("/auth/refresh")
    assert resp.status_code == 401


# --- E2 이메일 인증 검증 ----------------------------------------------------

_INVALID_VERIFICATION = "유효하지 않거나 만료된 인증 링크입니다"


async def _issue_verification(session: AsyncSession, user_id) -> str:
    raw = await auth_service.create_email_verification(user_id, session)
    await session.commit()
    return raw


async def test_verify_email_success(async_client, db_session, existing_user):
    user_id = existing_user.id
    raw = await _issue_verification(db_session, user_id)

    resp = await async_client.post("/auth/verify-email", json={"token": raw})
    assert resp.status_code == 200
    assert resp.json()["message"] == "이메일 인증이 완료되었습니다"

    user = (await db_session.exec(select(User).where(User.id == user_id))).first()
    assert user.is_email_verified is True
    assert user.email_verified_at is not None
    record = (await db_session.exec(select(EmailVerification))).first()
    assert record.used_at is not None


async def test_verify_email_expired_rejected(async_client, db_session, existing_user):
    user_id = existing_user.id
    raw = await _issue_verification(db_session, user_id)
    record = (await db_session.exec(select(EmailVerification))).first()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(record)
    await db_session.commit()

    resp = await async_client.post("/auth/verify-email", json={"token": raw})
    assert resp.status_code == 400
    assert resp.json()["detail"] == _INVALID_VERIFICATION
    user = (await db_session.exec(select(User).where(User.id == user_id))).first()
    assert user.is_email_verified is False


async def test_verify_email_reuse_rejected(async_client, db_session, existing_user):
    raw = await _issue_verification(db_session, existing_user.id)
    first = await async_client.post("/auth/verify-email", json={"token": raw})
    assert first.status_code == 200
    # 일회용: used_at이 세팅된 토큰 재제출은 거부
    second = await async_client.post("/auth/verify-email", json={"token": raw})
    assert second.status_code == 400
    assert second.json()["detail"] == _INVALID_VERIFICATION


async def test_verify_email_unknown_token_rejected(async_client, existing_user):
    resp = await async_client.post(
        "/auth/verify-email", json={"token": "nonexistent-token"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == _INVALID_VERIFICATION


async def test_verify_email_idempotent_preserves_verified_at(
    async_client, db_session, existing_user
):
    # 이미 인증된 유저가 또 다른 미사용 토큰으로 검증해도 email_verified_at은 보존
    user_id = existing_user.id
    raw1 = await _issue_verification(db_session, user_id)
    await async_client.post("/auth/verify-email", json={"token": raw1})
    user = (await db_session.exec(select(User).where(User.id == user_id))).first()
    first_verified_at = user.email_verified_at
    assert first_verified_at is not None

    raw2 = await _issue_verification(db_session, user_id)
    resp = await async_client.post("/auth/verify-email", json={"token": raw2})
    assert resp.status_code == 200
    user = (await db_session.exec(select(User).where(User.id == user_id))).first()
    assert user.email_verified_at == first_verified_at


# --- E3 재발송 --------------------------------------------------------------

_RESEND_MESSAGE = "인증 메일을 보냈어요"


async def test_resend_invalidates_old_and_issues_new(
    async_client, db_session, existing_user, externals
):
    user_id = existing_user.id
    old_raw = await _issue_verification(db_session, user_id)

    resp = await async_client.post(
        "/auth/resend-verification", json={"email": _CREDS["email"]}
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == _RESEND_MESSAGE

    records = (
        await db_session.exec(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )
    ).all()
    # 기존 1개 무효화(used_at) + 신규 1개 발급(미사용)
    assert len(records) == 2
    assert sum(1 for r in records if r.used_at is not None) == 1
    assert sum(1 for r in records if r.used_at is None) == 1
    externals.verification.assert_awaited_once()

    # 무효화된 옛 토큰은 이제 검증 거부됨
    reject = await async_client.post("/auth/verify-email", json={"token": old_raw})
    assert reject.status_code == 400


async def test_resend_unknown_email_is_silent(async_client, db_session, externals):
    resp = await async_client.post(
        "/auth/resend-verification", json={"email": "nobody@example.com"}
    )
    # 비열거: 미존재도 신규와 동일 200
    assert resp.status_code == 200
    assert resp.json()["message"] == _RESEND_MESSAGE
    assert len((await db_session.exec(select(EmailVerification))).all()) == 0
    externals.verification.assert_not_awaited()


async def test_resend_already_verified_no_send(
    async_client, db_session, social_user, externals
):
    resp = await async_client.post(
        "/auth/resend-verification", json={"email": "social@example.com"}
    )
    # 비열거: 이미 인증된 유저도 동일 200, 단 실제 발송/토큰 발급은 없음
    assert resp.status_code == 200
    assert resp.json()["message"] == _RESEND_MESSAGE
    assert len((await db_session.exec(select(EmailVerification))).all()) == 0
    externals.verification.assert_not_awaited()


# --- E3 require_verified_email 가드 (단위) ----------------------------------


async def test_require_verified_email_allows_verified():
    user = User(email="verified@example.com", nickname="v", is_email_verified=True)
    assert await require_verified_email(user) is user


async def test_require_verified_email_blocks_unverified():
    user = User(email="unverified@example.com", nickname="u", is_email_verified=False)
    with pytest.raises(HTTPException) as exc:
        await require_verified_email(user)
    assert exc.value.status_code == 403
