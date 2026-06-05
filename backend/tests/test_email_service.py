"""이메일 발송 서비스 단위 테스트 (M1 E1).

_send: API 키 가드, HTTP 오류 fail-open, payload 검증
send_verification_email: 인증 URL에 토큰 포함, 올바른 제목
send_already_registered_email: 로그인/비번재설정 링크, 올바른 제목
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from src.services import email_service

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_post():
    """httpx.AsyncClient를 AsyncMock으로 교체해 실제 HTTP 발송을 막는다."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.services.email_service.httpx.AsyncClient", return_value=mock_client):
        yield mock_client.post


@pytest.fixture
def set_api_key(monkeypatch):
    monkeypatch.setattr(email_service.settings, "resend_api_key", SecretStr("re_test_key"))


@pytest.fixture
def clear_api_key(monkeypatch):
    monkeypatch.setattr(email_service.settings, "resend_api_key", SecretStr(""))


# ---------------------------------------------------------------------------
# _send: API 키 가드
# ---------------------------------------------------------------------------


async def test_send_skips_when_no_api_key(mock_post, clear_api_key):
    await email_service._send("user@example.com", "제목", "<p>본문</p>")
    mock_post.assert_not_called()


async def test_send_calls_resend_when_api_key_set(mock_post, set_api_key):
    await email_service._send("user@example.com", "제목", "<p>본문</p>")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["to"] == ["user@example.com"]
    assert payload["subject"] == "제목"


async def test_send_uses_bearer_auth(mock_post, set_api_key):
    await email_service._send("user@example.com", "제목", "<p>본문</p>")
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer re_test_key"


# ---------------------------------------------------------------------------
# _send: HTTP 오류 fail-open
# ---------------------------------------------------------------------------


async def test_send_fail_open_on_http_error(monkeypatch, set_api_key):
    """발송 중 HTTPError가 발생해도 예외가 전파되지 않아야 한다."""
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock()
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.services.email_service.httpx.AsyncClient", return_value=mock_client):
        await email_service._send("user@example.com", "제목", "<p>본문</p>")  # 예외 없이 통과


# ---------------------------------------------------------------------------
# send_verification_email
# ---------------------------------------------------------------------------


async def test_verification_email_token_in_url(monkeypatch, set_api_key):
    """인증 메일 HTML에 토큰 원문이 verify-email URL에 포함돼야 한다."""
    sent: dict = {}

    async def capture(to, subject, html):
        sent.update({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_verification_email("user@example.com", "tok_abc123")

    assert "tok_abc123" in sent["html"]
    assert "/auth/verify-email?token=tok_abc123" in sent["html"]
    assert "이메일 인증" in sent["subject"]


async def test_verification_email_to_address(monkeypatch, set_api_key):
    sent: dict = {}

    async def capture(to, subject, html):
        sent["to"] = to

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_verification_email("user@example.com", "tok_xyz")
    assert sent["to"] == "user@example.com"


# ---------------------------------------------------------------------------
# send_already_registered_email
# ---------------------------------------------------------------------------


async def test_already_registered_email_has_login_link(monkeypatch, set_api_key):
    sent: dict = {}

    async def capture(to, subject, html):
        sent.update({"html": html, "subject": subject})

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_already_registered_email("user@example.com")

    assert "/auth/login" in sent["html"]
    assert "이미 가입" in sent["subject"]


async def test_already_registered_email_to_address(monkeypatch, set_api_key):
    sent: dict = {}

    async def capture(to, subject, html):
        sent["to"] = to

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_already_registered_email("dup@example.com")
    assert sent["to"] == "dup@example.com"


# ---------------------------------------------------------------------------
# HTML 이스케이프 (URL 인젝션 방어)
# ---------------------------------------------------------------------------


async def test_verification_html_escapes_url(monkeypatch, set_api_key):
    """verify_url에 특수문자가 있어도 HTML에 그대로 박히지 않아야 한다."""
    sent: dict = {}

    async def capture(to, subject, html):
        sent["html"] = html

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_verification_email(
        "user@example.com", 'tok&evil="<script>'
    )
    # 원본 특수문자가 그대로 출력되면 안 됨
    assert "<script>" not in sent["html"]
