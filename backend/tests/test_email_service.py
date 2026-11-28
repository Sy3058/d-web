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


async def test_send_calls_resend_when_api_key_set(monkeypatch, mock_post, set_api_key):
    monkeypatch.setattr(email_service.settings, "email_from", "legacy@example.com")
    html = "<p>본문</p>"
    await email_service._send("user@example.com", "제목", html)
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["to"] == ["user@example.com"]
    assert payload["subject"] == "제목"
    assert payload["html"] == html
    assert payload["from"] == "legacy@example.com"
    assert "template" not in payload


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


async def test_signup_verification_email_uses_published_template(
    monkeypatch, mock_post, set_api_key
):
    monkeypatch.setattr(email_service.settings, "email_from", "legacy@example.com")
    await email_service.send_signup_code_email("user@example.com", "012345")

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {
        "to": ["user@example.com"],
        "template": {
            "id": "email-verification",
            "variables": {"verifycode": "012345"},
        },
    }
    assert not ({"from", "subject", "html", "text", "react"} & payload.keys())


async def test_signup_verification_email_skips_without_api_key(mock_post, clear_api_key):
    await email_service.send_signup_code_email("user@example.com", "012345")

    mock_post.assert_not_called()


async def test_signup_verification_email_http_error_is_fail_open_and_sanitized(
    monkeypatch, set_api_key
):
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock()
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_logger = MagicMock()
    monkeypatch.setattr(email_service, "logger", mock_logger)

    with patch("src.services.email_service.httpx.AsyncClient", return_value=mock_client):
        await email_service.send_signup_code_email("private@example.com", "012345")

    logged = repr(mock_logger.method_calls)
    assert "email_send_failed_fail_open" in logged
    assert "012345" not in logged
    assert "re_test_key" not in logged
    assert "private@example.com" not in logged


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


async def test_already_registered_email_uses_published_template(
    monkeypatch, mock_post, set_api_key
):
    monkeypatch.setattr(email_service.settings, "email_from", "legacy@example.com")
    await email_service.send_already_registered_email("user@example.com")

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {
        "to": ["user@example.com"],
        "template": {
            "id": "already-registered",
            "variables": {"loginurl": f"{email_service.settings.app_base_url}/auth/login"},
        },
    }
    assert not ({"from", "subject", "html", "text", "react"} & payload.keys())


async def test_already_registered_email_to_address(monkeypatch, set_api_key):
    sent: dict = {}

    async def capture(to, *, template):
        sent["to"] = to

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_already_registered_email("dup@example.com")
    assert sent["to"] == "dup@example.com"


@pytest.mark.parametrize(
    "send,alias,variable,path",
    [
        (
            email_service.send_google_registered_email,
            "gmail-registered",
            "loginurl",
            "/auth/login",
        ),
        (
            email_service.send_non_registered_email,
            "non-registered",
            "registerurl",
            "/auth/signup",
        ),
    ],
)
async def test_password_account_notice_uses_published_template(
    mock_post, set_api_key, send, alias, variable, path
):
    await send("user@example.com")

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {
        "to": ["user@example.com"],
        "template": {
            "id": alias,
            "variables": {variable: f"{email_service.settings.app_base_url}{path}"},
        },
    }
    assert not ({"from", "subject", "html", "text", "react"} & payload.keys())


async def test_password_reset_email_uses_published_template_and_does_not_log_token(
    monkeypatch, mock_post, set_api_key
):
    mock_logger = MagicMock()
    monkeypatch.setattr(email_service, "logger", mock_logger)
    token = "secret-reset-token"
    await email_service.send_password_reset_email("private@example.com", token)

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {
        "to": ["private@example.com"],
        "template": {
            "id": "password-reset",
            "variables": {
                "reseturl": (
                    f"{email_service.settings.app_base_url}/auth/reset-password#token={token}"
                )
            },
        },
    }
    assert not ({"from", "subject", "html", "text", "react"} & payload.keys())
    logged = repr(mock_logger.method_calls)
    assert token not in logged
    assert "private@example.com" not in logged


@pytest.mark.parametrize(
    "login_url",
    [None, "https://admin.example.com/login"],
)
async def test_password_reset_complete_email_uses_published_template(
    mock_post, set_api_key, login_url
):
    await email_service.send_password_reset_complete_email("user@example.com", login_url)

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {
        "to": ["user@example.com"],
        "template": {
            "id": "password-reset-complete",
            "variables": {
                "loginurl": login_url
                or f"{email_service.settings.app_base_url.rstrip('/')}/auth/login"
            },
        },
    }
    assert not ({"from", "subject", "html", "text", "react"} & payload.keys())


# ---------------------------------------------------------------------------
# HTML 이스케이프 (URL 인젝션 방어)
# ---------------------------------------------------------------------------


async def test_verification_html_escapes_url(monkeypatch, set_api_key):
    """verify_url에 특수문자가 있어도 HTML에 그대로 박히지 않아야 한다."""
    sent: dict = {}

    async def capture(to, subject, html):
        sent["html"] = html

    monkeypatch.setattr(email_service, "_send", capture)
    await email_service.send_verification_email("user@example.com", 'tok&evil="<script>')
    # 원본 특수문자가 그대로 출력되면 안 됨
    assert "<script>" not in sent["html"]
