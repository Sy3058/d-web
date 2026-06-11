"""CORS 미들웨어 설정 검증 (M1 I3).

allow_methods/allow_headers 와일드카드(`*`)를 공유 api.ts 래퍼가 쓰는
메서드(GET/POST/PUT/DELETE/OPTIONS) + Content-Type으로 좁힌 뒤, 실제로
좁혀졌는지(목록 밖 메서드/헤더 거부)와 credentials+origin 동작이 유지되는지
회귀 방지한다. 미들웨어만 검증하므로 DB/async 픽스처 불필요.
"""

from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

client = TestClient(app)

ALLOWED_ORIGIN = settings.cors_origins[0]


# ---------------------------------------------------------------------------
# preflight (OPTIONS) - 좁혀진 메서드/헤더만 허용
# ---------------------------------------------------------------------------


def test_preflight_allowed_origin_narrowed():
    """허용 origin preflight: Allow-Methods/Headers에 와일드카드 없이 명시값만."""
    resp = client.options(
        "/",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200

    allow_methods = resp.headers["access-control-allow-methods"]
    for method in ("GET", "POST", "PUT", "DELETE"):
        assert method in allow_methods
    assert "*" not in allow_methods
    assert "PATCH" not in allow_methods  # 목록 밖 메서드는 노출 안 됨

    allow_headers = resp.headers["access-control-allow-headers"]
    assert "content-type" in allow_headers.lower()
    assert "*" not in allow_headers

    assert resp.headers["access-control-allow-credentials"] == "true"
    assert resp.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_preflight_disallowed_method_rejected():
    """PATCH preflight는 400 - allow_methods가 ["*"]였다면 200이었을 직접 증거."""
    resp = client.options(
        "/",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
        },
    )
    assert resp.status_code == 400


def test_preflight_disallowed_header_rejected():
    """허용 목록 밖 요청 헤더는 400 - allow_headers가 좁혀졌음을 보장."""
    resp = client.options(
        "/",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-evil-header",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 실제 요청 - origin 검사 + credentials 유지
# ---------------------------------------------------------------------------


def test_disallowed_origin_no_cors_header():
    """비허용 origin 요청엔 Allow-Origin 헤더 미부여(브라우저 차단)."""
    resp = client.get("/", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_allowed_origin_reflected_with_credentials():
    """허용 origin 요청엔 origin 반영 + credentials 허용 유지."""
    resp = client.get("/", headers={"Origin": ALLOWED_ORIGIN})
    assert resp.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert resp.headers["access-control-allow-credentials"] == "true"
