"""인증 표면 rate limit 테스트 (M1 F1 / council I2).

IP 단위 5회/분. 6회째 429. limiter는 conftest의 autouse _reset_rate_limits로 매 테스트
초기화되므로 누적 hit이 새지 않는다. async_client는 conftest 공용 픽스처를 쓴다(I4 승격).
"""

from unittest.mock import AsyncMock

from src.services import email_service

# 미존재 이메일: 비열거상 매번 401(회원/비회원 동일). rate limit은 회원 여부와 무관하게
# IP로만 카운트하므로 이 경로로 6회째 429를 검증할 수 있다.
_LOGIN = {"email": "nobody@example.com", "password": "Whatever1!"}


async def test_login_sixth_request_returns_429(async_client):
    for _ in range(5):
        resp = await async_client.post("/auth/login", json=_LOGIN)
        assert resp.status_code == 401
    sixth = await async_client.post("/auth/login", json=_LOGIN)
    assert sixth.status_code == 429
    # 클라이언트가 재시도 시점을 알 수 있도록 Retry-After 포함
    assert "retry-after" in {k.lower() for k in sixth.headers}


async def test_rate_limit_scopes_are_independent(async_client, monkeypatch):
    # signup 경로의 메일 발송은 mock(HIBP는 conftest 전역 stub) - rate limit 버킷만 검증한다.
    monkeypatch.setattr(email_service, "send_verification_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_already_registered_email", AsyncMock())

    # login 버킷 소진(6회째 429)
    for _ in range(5):
        await async_client.post("/auth/login", json=_LOGIN)
    assert (await async_client.post("/auth/login", json=_LOGIN)).status_code == 429

    # 같은 윈도우라도 signup은 독립 버킷이라 통과(엔드포인트별 scope 분리 확인)
    signup = await async_client.post(
        "/auth/signup",
        json={"email": "fresh@example.com", "password": "Passw0rd!", "nickname": "n"},
    )
    assert signup.status_code == 200
