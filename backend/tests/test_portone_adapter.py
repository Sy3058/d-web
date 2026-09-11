import base64
import hashlib
import hmac
import json
import time
from dataclasses import FrozenInstanceError

import httpx
import pytest
from pydantic import SecretStr

from src.config import settings
from src.models.payment import PaymentCancelReason
from src.services.portone_rest import (
    PortOneApiError,
    PortOneCancellationState,
    PortOneCancelRequest,
    PortOneMoneyState,
    PortOneRestAdapter,
    PortOneTransportError,
    quote_idempotency_key,
)
from src.services.portone_webhook import PortOneWebhookError, verify_portone_webhook

API_SECRET = "portone-api-secret-for-tests"


def _secret() -> SecretStr:
    return SecretStr(API_SECRET)


def test_portone_config_masks_secrets(monkeypatch):
    api_secret = "api-secret-must-not-appear"
    webhook_secret = "webhook-secret-must-not-appear"
    monkeypatch.setattr(settings, "portone_v2_api_secret", SecretStr(api_secret))
    monkeypatch.setattr(settings, "portone_webhook_secret", SecretStr(webhook_secret))

    assert isinstance(settings.portone_v2_api_secret, SecretStr)
    assert isinstance(settings.portone_webhook_secret, SecretStr)
    serialized = settings.model_dump_json()
    assert api_secret not in serialized
    assert webhook_secret not in serialized


@pytest.mark.asyncio
async def test_rest_adapter_uses_explicit_timeout_and_allowlist_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"PortOne {API_SECRET}"
        assert str(request.url) == "https://api.portone.io/payments/pay_123"
        return httpx.Response(
            200,
            json={
                "status": "PAID",
                "id": "pay_123",
                "transactionId": "tx-123",
                "storeId": "store-123",
                "channel": {
                    "type": "TEST",
                    "key": "channel-key-123",
                    "pgProvider": "TOSS_PAYMENTS",
                    "newProviderField": "ignored",
                },
                "amount": {"total": 700, "paid": 600, "newAmountField": 1},
                "currency": "KRW",
                "orderName": "테스트 주문",
                "method": {"type": "PaymentMethodEasyPay", "provider": "KAKAOPAY"},
                "receiptUrl": "https://receipt.example/test",
                "paidAt": "2026-09-01T01:00:00Z",
                "customer": {"email": "must-not-survive@example.com"},
            },
        )

    adapter = PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler))
    try:
        snapshot = await adapter.get_payment("pay_123")
        assert adapter._client.timeout.connect == 5.0
        assert adapter._client.timeout.read == 65.0
        assert adapter._client.timeout.write == 10.0
        assert adapter._client.timeout.pool == 5.0
    finally:
        await adapter.aclose()

    assert snapshot is not None
    assert snapshot.money_state is PortOneMoneyState.PAID
    assert snapshot.total_amount == 700
    assert snapshot.channel_key == "channel-key-123"
    assert snapshot.easy_pay_provider == "KAKAOPAY"
    assert "must-not-survive@example.com" not in repr(snapshot)


@pytest.mark.asyncio
async def test_unknown_payment_response_is_isolated_without_crashing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "SETTLEMENT_PENDING",
                "id": "pay_unknown",
                "brandNewOneOf": {"secretFutureField": "not retained"},
            },
        )

    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        snapshot = await adapter.get_payment("pay_unknown")

    assert snapshot is not None
    assert snapshot.money_state is PortOneMoneyState.UNKNOWN
    assert snapshot.provider_status == "SETTLEMENT_PENDING"
    assert snapshot.payment_id == "pay_unknown"
    assert "secretFutureField" not in repr(snapshot)


@pytest.mark.asyncio
async def test_get_returns_none_only_for_typed_payment_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "PAYMENT_NOT_FOUND",
                "message": f"{API_SECRET} buyer@example.com",
            },
        )

    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        snapshot = await adapter.get_payment("pay_missing")

    assert snapshot is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type", "expected_error_type"),
    [
        (
            b"<html><body>portone-api-secret-for-tests buyer@example.com</body></html>",
            "text/html",
            "UNKNOWN_ERROR",
        ),
        (
            b'{"type":"ROUTE_NOT_FOUND","message":"buyer@example.com"}',
            "application/json",
            "ROUTE_NOT_FOUND",
        ),
    ],
)
async def test_get_fails_closed_for_untyped_404(
    content: bytes,
    content_type: str,
    expected_error_type: str,
):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            content=content,
            headers={"Content-Type": content_type},
        )

    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        with pytest.raises(PortOneApiError) as caught:
            await adapter.get_payment("pay_unknown_404")

    assert caught.value.status_code == 404
    assert caught.value.error_type == expected_error_type
    assert caught.value.retryable is False
    assert API_SECRET not in str(caught.value)
    assert "buyer@example.com" not in str(caught.value)


@pytest.mark.asyncio
async def test_get_retries_one_temporary_response_with_jitter():
    calls = 0
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"type": "TEMPORARY_ERROR"})
        return httpx.Response(200, json={"status": "READY", "id": "pay_retry"})

    async with PortOneRestAdapter(
        _secret(),
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        jitter=lambda _start, _end: 0.1,
    ) as adapter:
        snapshot = await adapter.get_payment("pay_retry")

    assert calls == 2
    assert delays == [0.1]
    assert snapshot is not None
    assert snapshot.money_state is PortOneMoneyState.READY


@pytest.mark.asyncio
async def test_get_does_not_retry_read_timeout():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("provider took too long", request=request)

    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        with pytest.raises(PortOneTransportError, match="timed out"):
            await adapter.get_payment("pay_timeout")

    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(307, False), (503, True)],
)
async def test_write_is_not_automatically_retried_and_error_is_sanitized(
    status_code: int,
    retryable: bool,
):
    calls = 0
    leaked = f"{API_SECRET} buyer@example.com"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url) == "https://api.portone.io/payments/pay_write/pre-register"
        return httpx.Response(
            status_code,
            json={"type": "TEMPORARY_ERROR", "message": leaked},
        )

    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        with pytest.raises(PortOneApiError) as caught:
            await adapter.pre_register_payment(
                payment_id="pay_write",
                store_id="store-123",
                total_amount=500,
            )

    assert calls == 1
    assert caught.value.retryable is retryable
    assert caught.value.error_type == "TEMPORARY_ERROR"
    assert API_SECRET not in str(caught.value)
    assert "buyer@example.com" not in str(caught.value)


@pytest.mark.asyncio
async def test_cancel_reuses_fixed_key_and_exact_snapshot_only_by_explicit_call():
    captured_headers: list[str] = []
    captured_bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.portone.io/payments/pay_cancel/cancel"
        captured_headers.append(request.headers["Idempotency-Key"])
        captured_bodies.append(request.content)
        return httpx.Response(
            200,
            json={
                "cancellation": {
                    "status": "SUCCEEDED",
                    "id": "cancel-123",
                    "totalAmount": 500,
                    "cancelledAt": "2026-09-01T01:02:00Z",
                    "customer": {"email": "ignored@example.com"},
                }
            },
        )

    request = PortOneCancelRequest(
        store_id="store-123",
        reason=PaymentCancelReason.SYSTEM_VERIFICATION,
        amount=500,
        current_cancellable_amount=500,
    )
    key = "cancel-key-123456"
    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        first = await adapter.cancel_payment(
            payment_id="pay_cancel",
            idempotency_key=key,
            request=request,
        )
        second = await adapter.cancel_payment(
            payment_id="pay_cancel",
            idempotency_key=key,
            request=request,
        )

    assert first == second
    assert first.state is PortOneCancellationState.SUCCEEDED
    assert captured_headers == [f'"{key}"', f'"{key}"']
    assert captured_bodies[0] == captured_bodies[1]
    assert json.loads(captured_bodies[0]) == request.snapshot()
    with pytest.raises(FrozenInstanceError):
        request.amount = 100  # type: ignore[misc]


@pytest.mark.asyncio
async def test_cancel_outstanding_request_is_retryable_but_not_automatically_retried():
    calls = 0
    leaked = f"{API_SECRET} buyer@example.com"

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            409,
            json={
                "type": "IDEMPOTENCY_OUTSTANDING_REQUEST",
                "message": leaked,
            },
        )

    request = PortOneCancelRequest(
        store_id="store-123",
        reason=PaymentCancelReason.SYSTEM_VERIFICATION,
        amount=500,
        current_cancellable_amount=500,
    )
    async with PortOneRestAdapter(_secret(), transport=httpx.MockTransport(handler)) as adapter:
        with pytest.raises(PortOneApiError) as caught:
            await adapter.cancel_payment(
                payment_id="pay_cancel",
                idempotency_key="cancel-key-123456",
                request=request,
            )

    assert calls == 1
    assert caught.value.status_code == 409
    assert caught.value.error_type == "IDEMPOTENCY_OUTSTANDING_REQUEST"
    assert caught.value.retryable is True
    assert API_SECRET not in str(caught.value)
    assert "buyer@example.com" not in str(caught.value)


def test_idempotency_key_validation_and_rfc_8941_quoting():
    assert quote_idempotency_key('cancel-12345678"\\') == '"cancel-12345678\\"\\\\"'
    with pytest.raises(ValueError, match="between 16 and 256"):
        quote_idempotency_key("too-short")
    with pytest.raises(ValueError, match="printable ASCII"):
        quote_idempotency_key("cancel-key-12345한")


def test_cancel_request_rejects_partial_amount():
    with pytest.raises(ValueError, match="full cancellation amounts must match"):
        PortOneCancelRequest(
            store_id="store-123",
            reason=PaymentCancelReason.SYSTEM_VERIFICATION,
            amount=100,
            current_cancellable_amount=500,
        )


def test_cancel_request_rejects_free_form_reason():
    with pytest.raises(ValueError, match="allowed payment cancel reason"):
        PortOneCancelRequest(
            store_id="store-123",
            reason="buyer@example.com requested a refund",  # type: ignore[arg-type]
            amount=500,
            current_cancellable_amount=500,
        )


def test_cancel_request_normalizes_known_database_reason():
    request = PortOneCancelRequest(
        store_id="store-123",
        reason="system_unavailable",  # type: ignore[arg-type]
        amount=500,
        current_cancellable_amount=500,
    )

    assert request.reason is PaymentCancelReason.SYSTEM_UNAVAILABLE


def test_cancel_request_reason_requires_matching_requester():
    with pytest.raises(ValueError, match="requester does not match"):
        PortOneCancelRequest(
            store_id="store-123",
            reason=PaymentCancelReason.CUSTOMER_REFUND,
            amount=500,
            current_cancellable_amount=500,
        )

    request = PortOneCancelRequest(
        store_id="store-123",
        reason=PaymentCancelReason.CUSTOMER_REFUND,
        amount=500,
        current_cancellable_amount=500,
        requester="CUSTOMER",
    )

    assert request.snapshot()["requester"] == "CUSTOMER"


def _signed_webhook(payload: bytes) -> tuple[SecretStr, dict[str, str]]:
    raw_secret = b"webhook-test-secret"
    secret = SecretStr("whsec_" + base64.b64encode(raw_secret).decode())
    webhook_id = "webhook-test-123"
    timestamp = str(int(time.time()))
    signed = f"{webhook_id}.{timestamp}.{payload.decode()}".encode()
    signature = base64.b64encode(hmac.digest(raw_secret, signed, hashlib.sha256)).decode()
    return secret, {
        "Webhook-Id": webhook_id,
        "Webhook-Timestamp": timestamp,
        "Webhook-Signature": f"v1,{signature}",
    }


def test_webhook_verifier_uses_raw_body_and_returns_allowlist():
    payload = (
        b'{"type":"Transaction.FutureState", "data":{"paymentId":"pay_webhook",'
        b'"email":"must-not-survive@example.com"}}'
    )
    secret, headers = _signed_webhook(payload)

    event = verify_portone_webhook(payload, headers, secret)

    assert event.webhook_id == "webhook-test-123"
    assert event.event_type == "Transaction.FutureState"
    assert event.payment_id == "pay_webhook"
    assert "must-not-survive@example.com" not in repr(event)

    altered = payload.replace(b"pay_webhook", b"pay_changed")
    with pytest.raises(PortOneWebhookError, match="verification failed"):
        verify_portone_webhook(altered, headers, secret)


def test_webhook_verifier_error_does_not_expose_secret_or_body():
    secret = SecretStr("webhook-secret-leak-marker")
    payload = b'{"email":"payload-leak-marker@example.com"}'
    with pytest.raises(PortOneWebhookError) as caught:
        verify_portone_webhook(payload, {}, secret)

    message = str(caught.value)
    assert secret.get_secret_value() not in message
    assert "payload-leak-marker@example.com" not in message


def test_webhook_verifier_sanitizes_signed_invalid_shape():
    payload = b'["payload-leak-marker@example.com"]'
    secret, headers = _signed_webhook(payload)

    with pytest.raises(PortOneWebhookError) as caught:
        verify_portone_webhook(payload, headers, secret)

    assert "payload-leak-marker@example.com" not in str(caught.value)
