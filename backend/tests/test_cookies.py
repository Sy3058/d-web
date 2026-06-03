"""HttpOnly 쿠키 발급/제거 단위 테스트 (M1 B3).

엔드포인트가 아직 없으므로(C 그룹) Response 객체에 직접 쿠키를 set/clear해
Set-Cookie 헤더의 플래그가 정확한지 검증한다.
"""

from fastapi import Response

from src.config import settings
from src.lib.auth import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    access_cookie_name,
    clear_auth_cookies,
    set_auth_cookies,
)


def _set_cookie_headers(response: Response) -> list[str]:
    return [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]


def _find(headers: list[str], name: str) -> str:
    for h in headers:
        if h.startswith(f"{name}="):
            return h
    raise AssertionError(f"{name} 쿠키를 찾지 못함: {headers}")


# ---------------------------------------------------------------------------
# access 쿠키 이름 (__Host- 프리픽스 환경 분기)
# ---------------------------------------------------------------------------


def test_access_cookie_name_dev(monkeypatch):
    monkeypatch.setattr(settings, "env", "development")
    assert access_cookie_name() == "access_token"


def test_access_cookie_name_prod(monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    assert access_cookie_name() == "__Host-access_token"


# ---------------------------------------------------------------------------
# set_auth_cookies
# ---------------------------------------------------------------------------


def test_set_cookies_dev_flags(monkeypatch):
    """로컬(dev): Secure·__Host- 없음, access=Lax/Path=/, refresh=Strict/Path 제한."""
    monkeypatch.setattr(settings, "env", "development")
    resp = Response()
    set_auth_cookies(resp, "acc-token", "ref-token")
    headers = _set_cookie_headers(resp)
    assert len(headers) == 2

    access = _find(headers, "access_token")
    assert "access_token=acc-token" in access
    assert "HttpOnly" in access
    assert "Path=/" in access
    assert "samesite=lax" in access.lower()
    assert "secure" not in access.lower()  # dev http는 Secure 금지
    assert "__host-" not in access.lower()  # Secure 없으면 프리픽스도 금지

    refresh = _find(headers, REFRESH_COOKIE_NAME)
    assert "refresh_token=ref-token" in refresh
    assert "HttpOnly" in refresh
    assert f"Path={REFRESH_COOKIE_PATH}" in refresh
    assert "samesite=strict" in refresh.lower()
    assert "secure" not in refresh.lower()


def test_set_cookies_prod_flags(monkeypatch):
    """운영(prod): 둘 다 Secure, access만 __Host- 프리픽스 + Path=/."""
    monkeypatch.setattr(settings, "env", "production")
    assert settings.cookie_secure is True
    resp = Response()
    set_auth_cookies(resp, "acc-token", "ref-token")
    headers = _set_cookie_headers(resp)

    access = _find(headers, "__Host-access_token")
    assert "Secure" in access
    assert "Path=/" in access
    assert "samesite=lax" in access.lower()

    refresh = _find(headers, REFRESH_COOKIE_NAME)
    assert "Secure" in refresh
    assert f"Path={REFRESH_COOKIE_PATH}" in refresh
    assert "__host-" not in refresh.lower()  # refresh는 Path 제한이라 프리픽스 제외


def test_set_cookies_max_age(monkeypatch):
    """access=15분, refresh=7일 만료가 Max-Age로 반영."""
    monkeypatch.setattr(settings, "env", "development")
    resp = Response()
    set_auth_cookies(resp, "acc-token", "ref-token")
    headers = _set_cookie_headers(resp)

    access = _find(headers, "access_token")
    refresh = _find(headers, REFRESH_COOKIE_NAME)
    assert f"Max-Age={settings.jwt_access_token_expire_minutes * 60}" in access
    assert f"Max-Age={settings.jwt_refresh_token_expire_days * 86400}" in refresh


# ---------------------------------------------------------------------------
# clear_auth_cookies
# ---------------------------------------------------------------------------


def test_clear_cookies_expire(monkeypatch):
    """로그아웃: 두 쿠키 모두 Max-Age=0으로 만료. Path는 set 때와 일치해야 삭제됨."""
    monkeypatch.setattr(settings, "env", "development")
    resp = Response()
    clear_auth_cookies(resp)
    headers = _set_cookie_headers(resp)
    assert len(headers) == 2

    access = _find(headers, "access_token")
    refresh = _find(headers, REFRESH_COOKIE_NAME)
    assert "Max-Age=0" in access
    assert "Max-Age=0" in refresh
    assert "Path=/" in access
    assert f"Path={REFRESH_COOKIE_PATH}" in refresh
