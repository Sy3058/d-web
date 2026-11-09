"""동시 refresh 패자의 응답 순서와 무관하게 승자의 인증 쿠키를 보존한다."""

import asyncio

import httpx
import pytest
from sqlmodel import select

from src.config import settings
from src.lib import auth
from src.lib.db import get_session
from src.main import app
from src.models.user import RefreshToken
from src.services import auth_service

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("secure", [False, True])
@pytest.mark.parametrize("response_order", ["winner-first", "loser-first"])
async def test_concurrent_loser_preserves_successful_refresh_cookies(
    db_session, user, session_factory, monkeypatch, secure, response_order
):
    monkeypatch.setattr(settings, "env", "production" if secure else "development")
    raw = await auth_service.create_refresh_token(user.id, db_session)
    await db_session.commit()
    barrier = asyncio.Barrier(2)
    real_claim = auth_service._claim_refresh_token

    async def claim_after_both_reads(record, session):
        await barrier.wait()
        return await real_claim(record, session)

    monkeypatch.setattr(auth_service, "_claim_refresh_token", claim_after_both_reads)

    async def independent_session():
        async with session_factory() as session:
            yield session

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = independent_session
    try:

        async def refresh():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="https://test.example"
            ) as client:
                client.cookies.set(
                    auth.REFRESH_COOKIE_NAME,
                    raw,
                    domain="test.example",
                    path=auth.REFRESH_COOKIE_PATH,
                )
                return await client.post("/auth/refresh")

        responses = await asyncio.wait_for(asyncio.gather(refresh(), refresh()), timeout=10)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response for response in responses if response.status_code == 200)
    loser = next(response for response in responses if response.status_code == 401)

    assert loser.headers.get_list("set-cookie") == []
    assert loser.headers["cache-control"] == "no-store"
    assert loser.json() == {"detail": "인증이 필요합니다"}

    async with session_factory() as session:
        rows = (await session.exec(select(RefreshToken))).all()
        assert len(rows) == 2
        assert sum(row.revoked_at is None for row in rows) == 1

    # 동일 브라우저가 두 응답을 지정 순서로 받아도 성공 세션은 남아야 한다.
    expected_cookies = httpx.Cookies()
    expected_cookies.extract_cookies(winner)
    expected_names = {
        auth.access_cookie_name(),
        auth.REFRESH_COOKIE_NAME,
        auth.LOGIN_HINT_COOKIE_NAME,
    }
    assert set(expected_cookies) == expected_names
    browser_cookies = httpx.Cookies()
    ordered = (winner, loser) if response_order == "winner-first" else (loser, winner)
    for response in ordered:
        browser_cookies.extract_cookies(response)
    assert set(browser_cookies) == expected_names
    for name in expected_names:
        assert browser_cookies.get(name) == expected_cookies.get(name)
    payload = auth.decode_token(browser_cookies.get(auth.access_cookie_name()))
    assert payload["sub"] == str(user.id)
