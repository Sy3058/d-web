"""닉네임 PATCH의 실제 브라우저 preflight 경계."""

import pytest

from src.config import settings


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [True, False])
async def test_account_patch_preflight_preserves_origin_allowlist(async_client, allowed):
    origin = settings.app_base_url if allowed else "https://untrusted.example"
    response = await async_client.options(
        "/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == (200 if allowed else 400)
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "PATCH" in response.headers["access-control-allow-methods"].split(", ")
    else:
        assert "access-control-allow-origin" not in response.headers
