"""계정 프로필 HTTP 경계와 실제 이미지/R2 저장 수명 회귀."""

import asyncio
import uuid
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image, JpegImagePlugin
from pydantic import ValidationError

from src.config import settings
from src.lib.auth import create_access_token
from src.lib.exceptions import ImageValidationError
from src.models.user import User
from src.schemas.account import NicknameUpdateRequest, PasswordChangeRequest
from src.services import account_service, avatar_service, r2_service


def image_bytes(format="PNG", size=(300, 120), **kwargs):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format=format, **kwargs)
    return output.getvalue()


def login_cookie(client, user):
    client.cookies.set("access_token", create_access_token(str(user.id)), domain="test.example")


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(settings, "public_asset_base_url", "https://assets.example/media")
    monkeypatch.setattr(r2_service, "is_configured", lambda: True)
    upload = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(r2_service, "upload_bytes", upload)
    monkeypatch.setattr(r2_service, "delete_object", delete)
    return upload, delete


@pytest.mark.parametrize("nickname", ["", "  ", "a" * 51, "hello\n", "hello\x00", "hello\u200b"])
def test_nickname_rejects_empty_controls_or_long(nickname):
    with pytest.raises(ValidationError):
        NicknameUpdateRequest(nickname=nickname)


def test_nickname_trims_and_rejects_profile_fields():
    assert NicknameUpdateRequest(nickname=" 새 이름 ").nickname == "새 이름"
    for extra in ({"id": str(uuid.uuid4())}, {"profile_image": "https://external.example/x"}):
        with pytest.raises(ValidationError):
            NicknameUpdateRequest(nickname="이름", **extra)


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
async def test_real_images_become_square_webp(format):
    converted = await avatar_service.convert_avatar(image_bytes(format))
    with Image.open(BytesIO(converted)) as image:
        assert image.format == "WEBP"
        assert image.size == (256, 256)
        assert not image.info.get("exif")
        assert not image.info.get("icc_profile")


async def test_jpeg_never_uses_draft_and_strips_exif(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("draft must not run")

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", forbidden)
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010E] = "private metadata"
    result = await avatar_service.convert_avatar(image_bytes("JPEG", (1200, 800), exif=exif))
    with Image.open(BytesIO(result)) as image:
        assert image.size == (256, 256)
        assert not image.getexif()
        assert b"private metadata" not in result


@pytest.mark.parametrize(
    "data", [b"not image", b"\x00\x00\x00\x0cjP  \r\n\x87\n", image_bytes("GIF")]
)
async def test_rejects_invalid_and_non_allowlisted_decoders(data):
    with pytest.raises(ImageValidationError):
        await avatar_service.convert_avatar(data)


async def test_size_limit_and_pixel_limit_before_load(monkeypatch):
    with pytest.raises(ImageValidationError):
        await avatar_service.convert_avatar(b"x" * (avatar_service.MAX_AVATAR_BYTES + 1))
    data = image_bytes("PNG", (4001, 4000))
    from PIL import PngImagePlugin

    def forbidden(*args, **kwargs):
        raise AssertionError("oversized image must not decode")

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "load", forbidden)
    with pytest.raises(ImageValidationError, match="1600만"):
        await avatar_service.convert_avatar(data)


async def test_animation_rejected():
    output = BytesIO()
    frames = [Image.new("RGB", (20, 20), color) for color in ("red", "blue")]
    frames[0].save(output, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(ImageValidationError, match="정적"):
        await avatar_service.convert_avatar(output.getvalue())


async def test_exif_rotation_applied_before_center_crop():
    image = Image.new("RGB", (400, 200), "red")
    image.paste("blue", (200, 0, 400, 200))
    exif = Image.Exif()
    exif[0x0112] = 6
    source = BytesIO()
    image.save(source, format="JPEG", exif=exif)
    result = await avatar_service.convert_avatar(source.getvalue())
    with Image.open(BytesIO(result)) as avatar:
        top = avatar.getpixel((128, 20))
        bottom = avatar.getpixel((128, 230))
        assert top[0] > top[2]
        assert bottom[2] > bottom[0]


async def test_patch_changes_only_nickname_and_login_hint(async_client, existing_user, db_session):
    login_cookie(async_client, existing_user)
    before = {key: getattr(existing_user, key) for key in User.model_fields}
    response = await async_client.patch("/auth/me", json={"nickname": " 새 닉네임 "})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["nickname"] == "새 닉네임"
    assert response.json()["has_password"] is True
    assert response.json()["email"] == existing_user.email
    assert set(response.json()) == {
        "id",
        "email",
        "nickname",
        "profile_image",
        "is_email_verified",
        "has_password",
        "role",
        "created_at",
    }
    assert all(
        header.startswith("login_hint=") for header in response.headers.get_list("set-cookie")
    )
    await db_session.refresh(existing_user)
    after = {key: getattr(existing_user, key) for key in User.model_fields}
    for key in before.keys() - {"nickname", "updated_at"}:
        assert before[key] == after[key]


async def test_profile_auth_extra_fields_and_rate_limit(async_client, user):
    response = await async_client.patch("/auth/me", json={"nickname": "new"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    login_cookie(async_client, user)
    response = await async_client.patch("/auth/me", json={"nickname": "new", "role": "owner"})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    from src.lib.rate_limit import reset_rate_limits

    reset_rate_limits()
    for _ in range(10):
        assert (await async_client.patch("/auth/me", json={"nickname": "new"})).status_code == 200
    response = await async_client.patch("/auth/me", json={"nickname": "new"})
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"


async def test_avatar_http_ignores_filename_and_uses_public_namespace(async_client, user, storage):
    upload, delete = storage
    login_cookie(async_client, user)
    response = await async_client.post(
        "/auth/me/profile-image", files={"file": ("../../work.webp", image_bytes(), "text/plain")}
    )
    assert response.status_code == 200
    assert response.json()["has_password"] is False
    assert response.headers["cache-control"] == "no-store"
    key, converted = upload.call_args.args
    assert key.startswith(f"avatars/{user.id}/")
    assert response.json()["profile_image"] == f"https://assets.example/media/{key}"
    assert upload.call_args.kwargs == {"bucket": settings.r2_public_bucket}
    assert Image.open(BytesIO(converted)).size == (256, 256)
    assert not response.headers.get_list("set-cookie")
    delete.assert_not_awaited()


@pytest.mark.parametrize(
    "previous",
    [
        "https://external.example/avatars/{user}/0123456789abcdef0123456789abcdef.webp",
        "https://assets.example/media/avatars/{other}/0123456789abcdef0123456789abcdef.webp",
        "https://assets.example/media/works/cover.webp",
        "https://assets.example/media/avatars/{user}/0123456789abcdef0123456789abcdef.webp?x=1",
        "https://assets.example/media/avatars/{user}/../0123456789abcdef0123456789abcdef.webp",
    ],
)
async def test_external_or_other_namespace_never_deleted(previous, user, db_session, storage):
    user.profile_image = previous.format(user=user.id, other=uuid.uuid4())
    await db_session.commit()
    await account_service.update_avatar(user.id, image_bytes(), db_session)
    storage[1].assert_not_awaited()


async def test_own_old_avatar_deleted_after_commit(user, db_session, storage, monkeypatch):
    old_key = f"avatars/{user.id}/{uuid.uuid4().hex}.webp"
    user.profile_image = f"https://assets.example/media/{old_key}"
    await db_session.commit()

    async def deletion(key, **kwargs):
        assert not db_session.in_transaction()
        assert user.profile_image != f"https://assets.example/media/{key}"

    storage[1].side_effect = deletion
    await account_service.update_avatar(user.id, image_bytes(), db_session)
    storage[1].assert_awaited_once_with(old_key, bucket=settings.r2_public_bucket)


async def test_commit_failure_keeps_old_url_and_preserves_uncertain_object(
    user, db_session, storage, monkeypatch
):
    old_url = "https://external.example/old.png"
    user.profile_image = old_url
    await db_session.commit()
    user_id = user.id
    monkeypatch.setattr(db_session, "commit", AsyncMock(side_effect=RuntimeError("db failure")))
    with pytest.raises(RuntimeError, match="db failure"):
        await account_service.update_avatar(user_id, image_bytes(), db_session)
    await db_session.refresh(user)
    assert user.profile_image == old_url
    storage[1].assert_not_awaited()


@pytest.mark.parametrize(
    "base",
    [
        "",
        "javascript:alert(1)",
        "https://assets.example/?x=1",
        "https://assets.example/?",
        "https://assets.example/#",
        "https://assets.example:bad/path",
        "https://x/../bad",
        "https://user:secret@x",
        "https://x/\npath",
    ],
)
async def test_invalid_config_fails_before_external_write(
    base, async_client, user, storage, monkeypatch
):
    monkeypatch.setattr(settings, "public_asset_base_url", base)
    login_cookie(async_client, user)
    response = await async_client.post(
        "/auth/me/profile-image", files={"file": ("x.png", image_bytes())}
    )
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    storage[0].assert_not_awaited()


async def test_avatar_invalid_and_oversize_do_not_upload(async_client, user, storage):
    login_cookie(async_client, user)
    for data in (b"invalid", b"x" * (avatar_service.MAX_AVATAR_BYTES + 100)):
        response = await async_client.post(
            "/auth/me/profile-image", files={"file": ("x.png", data)}
        )
        assert response.status_code == 422
    storage[0].assert_not_awaited()


async def test_concurrent_avatar_uses_locked_current_url(
    user, db_session, session_factory, storage
):
    initial_key = f"avatars/{user.id}/{uuid.uuid4().hex}.webp"
    user.profile_image = f"https://assets.example/media/{initial_key}"
    await db_session.commit()
    ready = asyncio.Event()
    count = 0

    async def upload(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 5)

    storage[0].side_effect = upload

    async def update():
        async with session_factory() as session:
            # identity map에 기존 snapshot을 넣어도 populate_existing으로 갱신해야 한다.
            await session.get(User, user.id)
            return (
                await account_service.update_avatar(user.id, image_bytes(), session)
            ).profile_image

    await asyncio.gather(update(), update())
    await db_session.refresh(user)
    uploaded_keys = {call.args[0] for call in storage[0].await_args_list}
    deleted_keys = {call.args[0] for call in storage[1].await_args_list}
    live_key = user.profile_image.removeprefix("https://assets.example/media/")
    assert live_key in uploaded_keys
    assert deleted_keys == {initial_key} | (uploaded_keys - {live_key})


def test_password_schema_uses_signup_policy_and_matching_confirmation():
    with pytest.raises(ValidationError):
        PasswordChangeRequest(
            current_password="old", new_password="abcdefgh", confirm_password="abcdefgh"
        )
    with pytest.raises(ValidationError):
        PasswordChangeRequest(
            current_password="old", new_password="Passw0rd!", confirm_password="different"
        )


async def test_password_validation_does_not_echo_credentials(async_client, user):
    login_cookie(async_client, user)
    response = await async_client.post(
        "/auth/me/password",
        json={
            "current_password": "private-current",
            "new_password": "Passw0rd!",
            "confirm_password": "private-confirm",
        },
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "private-current" not in response.text
    assert "private-confirm" not in response.text
    assert "Passw0rd!" not in response.text


async def test_avatar_decoder_allowlist_is_explicit(monkeypatch):
    original = Image.open
    formats_seen = []

    def restricted_open(*args, **kwargs):
        formats_seen.append(kwargs.get("formats"))
        return original(*args, **kwargs)

    monkeypatch.setattr(Image, "open", restricted_open)
    await avatar_service.convert_avatar(image_bytes("PNG"))
    assert formats_seen == [["JPEG", "PNG", "WEBP"]]


async def test_cleanup_failure_preserves_success(user, db_session, storage):
    old_key = f"avatars/{user.id}/{uuid.uuid4().hex}.webp"
    user.profile_image = f"https://assets.example/media/{old_key}"
    await db_session.commit()
    storage[1].side_effect = RuntimeError("storage unavailable")
    result = await account_service.update_avatar(user.id, image_bytes(), db_session)
    assert result.profile_image.endswith(storage[0].call_args.args[0])
    await db_session.refresh(user)
    assert user.profile_image == result.profile_image


async def test_upload_failure_keeps_old_url(user, db_session, storage):
    old = "https://external.example/old.png"
    user.profile_image = old
    await db_session.commit()
    storage[0].side_effect = RuntimeError("upload failure")
    with pytest.raises(RuntimeError, match="upload failure"):
        await account_service.update_avatar(user.id, image_bytes(), db_session)
    await db_session.refresh(user)
    assert user.profile_image == old
    storage[1].assert_awaited_once_with(
        storage[0].call_args.args[0], bucket=settings.r2_public_bucket
    )


async def test_avatar_and_password_rate_limits(async_client, user, storage):
    login_cookie(async_client, user)
    for _ in range(5):
        assert (
            await async_client.post("/auth/me/profile-image", files={"file": ("x.png", b"invalid")})
        ).status_code == 422
    avatar_response = await async_client.post(
        "/auth/me/profile-image", files={"file": ("x.png", b"invalid")}
    )
    assert avatar_response.status_code == 429
    for _ in range(5):
        assert (await async_client.post("/auth/me/password", json={})).status_code == 422
    password_response = await async_client.post("/auth/me/password", json={})
    assert password_response.status_code == 429
    assert avatar_response.headers["cache-control"] == "no-store"
    assert password_response.headers["cache-control"] == "no-store"
    storage[0].assert_not_awaited()


async def test_stale_nickname_snapshot_preserves_latest_avatar(
    user, db_session, session_factory, storage
):
    async with session_factory() as stale_session:
        stale = await stale_session.get(User, user.id)
        assert stale.profile_image is None
        updated = await account_service.update_avatar(user.id, image_bytes(), db_session)
        expected_avatar = updated.profile_image
        renamed = await account_service.update_nickname(user.id, "new nickname", stale_session)
        assert renamed.profile_image == expected_avatar
    await db_session.refresh(user)
    assert user.profile_image == expected_avatar
    assert user.nickname == "new nickname"


async def test_commit_ack_loss_never_deletes_live_image(user, db_session, storage, monkeypatch):
    original_commit = db_session.commit
    user_id = user.id

    async def committed_but_ack_lost():
        await original_commit()
        raise RuntimeError("commit acknowledgment lost")

    monkeypatch.setattr(db_session, "commit", committed_but_ack_lost)
    with pytest.raises(RuntimeError, match="acknowledgment"):
        await account_service.update_avatar(user_id, image_bytes(), db_session)
    await db_session.refresh(user)
    new_key = storage[0].call_args.args[0]
    assert user.profile_image == f"https://assets.example/media/{new_key}"
    storage[1].assert_not_awaited()


async def test_missing_user_before_commit_cleans_new_object(db_session, storage):
    from src.lib.exceptions import InvalidCredentialsError

    with pytest.raises(InvalidCredentialsError):
        await account_service.update_avatar(uuid.uuid4(), image_bytes(), db_session)
    storage[1].assert_awaited_once_with(
        storage[0].call_args.args[0], bucket=settings.r2_public_bucket
    )
