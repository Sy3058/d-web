import pytest
from pydantic import ValidationError

from src.config import Settings

_BASE_SETTINGS = {
    "database_url": "postgresql+asyncpg://user:password@db.example/dweb",
    "jwt_secret": "jwt-secret",
    "password_pepper": "password-pepper",
    "token_pepper": "token-pepper",
    "app_base_url": "https://reader.example.com",
    "admin_base_url": "https://admin.example.com",
    "api_base_url": "https://api.example.com",
    "totp_encryption_key": "totp-key",
    "portone_v2_api_secret": "api-secret-value",
    "portone_store_id": "store-test",
    "portone_webhook_secret": "webhook-secret-value",
    "portone_channel_key_card": "channel-key-card",
    "portone_channel_key_kakaopay": "channel-key-kakao",
    "portone_channel_key_tosspay": "channel-key-toss",
}


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **(_BASE_SETTINGS | overrides))


def test_new_payments_disabled_allows_missing_provider_settings():
    settings = _settings(
        payments_accept_new=False,
        app_base_url="http://localhost:4321",
        api_base_url="http://localhost:8000",
        portone_v2_api_secret="",
        portone_store_id="",
        portone_webhook_secret="",
        portone_channel_key_card="",
        portone_channel_key_kakaopay="",
        portone_channel_key_tosspay="",
    )

    assert settings.payments_accept_new is False


@pytest.mark.parametrize(
    "field_name,setting_name",
    [
        ("portone_v2_api_secret", "PORTONE_V2_API_SECRET"),
        ("portone_store_id", "PORTONE_STORE_ID"),
        ("portone_webhook_secret", "PORTONE_WEBHOOK_SECRET"),
        ("portone_channel_key_card", "PORTONE_CHANNEL_KEY_CARD"),
        ("portone_channel_key_kakaopay", "PORTONE_CHANNEL_KEY_KAKAOPAY"),
        ("portone_channel_key_tosspay", "PORTONE_CHANNEL_KEY_TOSSPAY"),
    ],
)
def test_new_payments_enabled_rejects_missing_provider_setting(field_name, setting_name):
    with pytest.raises(ValidationError) as exc_info:
        _settings(payments_accept_new=True, **{field_name: "   "})

    message = str(exc_info.value)
    assert setting_name in message
    assert "api-secret-value" not in message
    assert "webhook-secret-value" not in message


@pytest.mark.parametrize("field_name", ["app_base_url", "api_base_url"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://localhost:8000",
        "https://localhost",
        "https://localhost.",
        "https://127.0.0.1",
        "https://127.1",
        "https://api.exa mple.com",
        "https://api.example.com:invalid",
        "https://[",
    ],
)
def test_new_payments_enabled_requires_public_https_urls(field_name, value):
    with pytest.raises(ValidationError) as exc_info:
        _settings(payments_accept_new=True, **{field_name: value})

    assert field_name.upper() in str(exc_info.value)


def test_new_payments_enabled_accepts_complete_configuration():
    settings = _settings(payments_accept_new=True)

    assert settings.payments_accept_new is True


def test_new_payments_enabled_rejects_duplicate_channel_keys():
    with pytest.raises(ValidationError) as exc_info:
        _settings(
            payments_accept_new=True,
            portone_channel_key_kakaopay="channel-key-card",
        )

    message = str(exc_info.value)
    assert "PORTONE_CHANNEL_KEY_*" in message
    assert "api-secret-value" not in message
