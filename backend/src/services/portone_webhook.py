"""PortOne Standard Webhooks raw 서명 검증 adapter."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from portone_server_sdk import webhook
from pydantic import SecretStr


class PortOneWebhookError(RuntimeError):
    """Secret, 원시 body와 signature를 포함하지 않는 검증 오류."""


@dataclass(frozen=True, slots=True)
class VerifiedPortOneWebhook:
    webhook_id: str
    event_type: str
    payment_id: str | None


def _bounded_string(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    return value


def verify_portone_webhook(
    raw_body: bytes,
    headers: Mapping[str, str],
    secret: SecretStr,
) -> VerifiedPortOneWebhook:
    """raw body 그대로 검증한 뒤 durable receipt에 필요한 allowlist만 반환한다."""
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    secret_value = secret.get_secret_value()
    if not secret_value:
        raise PortOneWebhookError("PortOne webhook secret is not configured")
    try:
        payload = raw_body.decode("utf-8")
        webhook.verify(secret_value, payload, normalized_headers)
        body = json.loads(payload)
    except (
        UnicodeDecodeError,
        ValueError,
        webhook.InvalidInputError,
        webhook.WebhookVerificationError,
    ):
        raise PortOneWebhookError("PortOne webhook verification failed") from None

    if not isinstance(body, Mapping):
        raise PortOneWebhookError("PortOne webhook payload is invalid")
    webhook_id = _bounded_string(normalized_headers.get("webhook-id"), limit=255)
    if webhook_id is None:
        raise PortOneWebhookError("PortOne webhook id is invalid")
    event_type = _bounded_string(body.get("type"), limit=40) or "Unknown"
    data = body.get("data")
    payment_id = None
    if isinstance(data, Mapping):
        payment_id = _bounded_string(data.get("paymentId"), limit=64)
    return VerifiedPortOneWebhook(
        webhook_id=webhook_id,
        event_type=event_type,
        payment_id=payment_id,
    )
