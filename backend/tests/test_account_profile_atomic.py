"""프로필 통합 저장의 성공·실패·경쟁 경계."""

import asyncio
import uuid
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from src.config import settings
from src.lib.auth import create_access_token
from src.lib.rate_limit import reset_rate_limits
from src.services import account_service, r2_service


def picture():
    output = BytesIO()
    Image.new("RGB", (64, 80), "blue").save(output, format="PNG")
    return output.getvalue()


def authenticate(client, user):
    client.cookies.set("access_token", create_access_token(str(user.id)), domain="test.example")


@pytest.fixture
def assets(monkeypatch):
    monkeypatch.setattr(settings, "public_asset_base_url", "https://assets.example/media")
    monkeypatch.setattr(r2_service, "is_configured", lambda: True)
    upload, delete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(r2_service, "upload_bytes", upload)
    monkeypatch.setattr(r2_service, "delete_object", delete)
    return upload, delete


async def test_combined_save(async_client, existing_user, db_session, assets):
    authenticate(async_client, existing_user)
    response = await async_client.put(
        "/auth/me/profile",
        data={"nickname": " 새 프로필 "},
        files={"file": ("x.png", picture(), "image/png")},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["nickname"] == "새 프로필"
    assert response.json()["profile_image"].endswith(assets[0].call_args.args[0])
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1 and cookies[0].startswith("login_hint=")
    await db_session.refresh(existing_user)
    assert (existing_user.nickname, existing_user.profile_image) == (
        "새 프로필",
        response.json()["profile_image"],
    )


async def test_keep_image_without_storage(async_client, user, db_session, assets, monkeypatch):
    user.profile_image = "https://external.example/old.png"
    await db_session.commit()
    monkeypatch.setattr(r2_service, "is_configured", lambda: False)
    authenticate(async_client, user)
    response = await async_client.put("/auth/me/profile", data={"nickname": "new"})
    assert response.status_code == 200
    assert response.json()["profile_image"] == "https://external.example/old.png"
    assets[0].assert_not_awaited()
    assets[1].assert_not_awaited()


@pytest.mark.parametrize("nickname", [" ", "a" * 51, "bad\u200b"])
async def test_invalid_nickname_prevents_upload(async_client, user, db_session, assets, nickname):
    before = user.nickname
    authenticate(async_client, user)
    response = await async_client.put(
        "/auth/me/profile",
        data={"nickname": nickname},
        files={"file": ("x.png", picture(), "image/png")},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert not response.headers.get_list("set-cookie")
    assets[0].assert_not_awaited()
    await db_session.refresh(user)
    assert (user.nickname, user.profile_image) == (before, None)


@pytest.mark.parametrize("payload", [b"invalid", b"x" * (5 * 1024 * 1024 + 1)])
async def test_invalid_image_preserves_nickname(async_client, user, db_session, assets, payload):
    before = user.nickname
    authenticate(async_client, user)
    response = await async_client.put(
        "/auth/me/profile",
        data={"nickname": "new"},
        files={"file": ("x.png", payload, "image/png")},
    )
    assert response.status_code == 422
    assert not response.headers.get_list("set-cookie")
    await db_session.refresh(user)
    assert (user.nickname, user.profile_image) == (before, None)
    assets[0].assert_not_awaited()


@pytest.mark.parametrize("failure", ["upload", "commit", "ack"])
async def test_storage_failures_preserve_pair(user, db_session, assets, monkeypatch, failure):
    before, user_id = user.nickname, user.id
    user.profile_image = "https://external.example/old.png"
    await db_session.commit()
    original_commit = db_session.commit

    async def failed_commit():
        if failure == "ack":
            await original_commit()
        raise RuntimeError("save failed")

    if failure == "upload":
        assets[0].side_effect = RuntimeError("save failed")
    else:
        monkeypatch.setattr(db_session, "commit", failed_commit)
    with pytest.raises(RuntimeError, match="save failed"):
        await account_service.update_profile(user_id, "new", db_session, data=picture())
    await db_session.refresh(user)
    if failure == "ack":
        assert user.nickname == "new"
        assert user.profile_image.endswith(assets[0].call_args.args[0])
    else:
        assert (user.nickname, user.profile_image) == (before, "https://external.example/old.png")
    if failure != "upload":
        assets[1].assert_not_awaited()


async def test_remove_image_with_nickname(async_client, user, db_session, assets):
    key = f"avatars/{user.id}/{uuid.uuid4().hex}.webp"
    user.profile_image = f"https://assets.example/media/{key}"
    await db_session.commit()
    authenticate(async_client, user)
    response = await async_client.put(
        "/auth/me/profile", data={"nickname": "new", "remove_image": "true"}
    )
    assert response.status_code == 200
    assert (response.json()["nickname"], response.json()["profile_image"]) == ("new", None)
    assets[0].assert_not_awaited()
    assets[1].assert_awaited_once_with(key, bucket=settings.r2_public_bucket)


async def test_conflicting_image_intent(async_client, user, assets):
    authenticate(async_client, user)
    response = await async_client.put(
        "/auth/me/profile",
        data={"nickname": "new", "remove_image": "true"},
        files={"file": ("x.png", picture(), "image/png")},
    )
    assert response.status_code == 422
    assert not response.headers.get_list("set-cookie")
    assets[0].assert_not_awaited()


async def test_auth_and_rate_limit(async_client, user, assets):
    assert (await async_client.put("/auth/me/profile", data={"nickname": "new"})).status_code == 401
    reset_rate_limits()
    authenticate(async_client, user)
    for _ in range(5):
        assert (
            await async_client.put("/auth/me/profile", data={"nickname": "new"})
        ).status_code == 200
    response = await async_client.put("/auth/me/profile", data={"nickname": "new"})
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"


async def test_concurrent_saves_do_not_mix_pairs(user, db_session, session_factory, assets):
    user_id = user.id
    keys = {}

    async def uploaded(key, *_args, **_kwargs):
        keys[asyncio.current_task().get_name()] = key

    assets[0].side_effect = uploaded

    async def save(nickname):
        async with session_factory() as session:
            await account_service.update_profile(user_id, nickname, session, data=picture())

    await asyncio.gather(
        asyncio.create_task(save("first"), name="first"),
        asyncio.create_task(save("second"), name="second"),
    )
    await db_session.refresh(user)
    assert user.profile_image == f"https://assets.example/media/{keys[user.nickname]}"
    assert len(assets[0].await_args_list) == 2
    assert len(assets[1].await_args_list) == 1
    assert assets[1].call_args.args[0] != user.profile_image.split("/media/")[1]


async def test_remove_without_storage_preserves_unmanaged_object(
    async_client, user, db_session, assets, monkeypatch
):
    user.profile_image = "https://external.example/old.png"
    await db_session.commit()
    monkeypatch.setattr(r2_service, "is_configured", lambda: False)
    authenticate(async_client, user)
    response = await async_client.put(
        "/auth/me/profile", data={"nickname": "new", "remove_image": "true"}
    )
    assert response.status_code == 200
    await db_session.refresh(user)
    assert (user.nickname, user.profile_image) == ("new", None)
    assets[0].assert_not_awaited()
    assets[1].assert_not_awaited()
