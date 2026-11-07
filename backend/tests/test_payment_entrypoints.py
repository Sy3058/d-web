"""완료 API와 raw 서명 webhook의 인증·영속성 경계 통합 테스트."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.config import settings
from src.lib.auth import access_cookie_name, create_access_token
from src.main import app
from src.models.payment import PaymentLog, PaymentOrder, PaymentWebhookReceipt, Purchase
from src.models.user import User
from src.routers.payments import get_payment_session_factory
from src.services import payment_complete_service
from src.services.portone_rest import PortOnePaymentSnapshot, PortOneTransportError
from tests.factories import PAYWALL, doc, make_episode, make_work, para

pytestmark = pytest.mark.asyncio
RAW_SECRET = b"entrypoint-webhook-secret"
SECRET = SecretStr("whsec_" + base64.b64encode(RAW_SECRET).decode())


class Provider:
    def __init__(self):
        self.changes = {}
        self.gets = []
        self.hook = None
        self.failure = False
        self.connections = {}
        self.closed = False

    def checkout(self, connection, record, proxy):
        self.connections[id(record)] = asyncio.current_task()

    def checkin(self, connection, record):
        self.connections.pop(id(record), None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def get_payment(self, payment_id, *, store_id):
        assert asyncio.current_task() not in self.connections.values()
        self.gets.append((payment_id, store_id))
        if self.failure:
            raise PortOneTransportError("private-provider-body")
        if self.hook:
            await self.hook()
        return PortOnePaymentSnapshot.from_payload(
            {
                "id": payment_id,
                "storeId": "entrypoint-store",
                "status": "PAID",
                "currency": "KRW",
                "amount": {"total": 500},
                "channel": {"type": "TEST", "key": "entrypoint-card"},
                "method": {"type": "PaymentMethodCard"},
                "paidAt": datetime.now(UTC).isoformat(),
                **self.changes,
            }
        )

    async def cancel_payment(self, **kwargs):
        assert asyncio.current_task() not in self.connections.values()
        raise PortOneTransportError("private-provider-body")


@pytest.fixture(autouse=True)
def payment_settings(monkeypatch):
    monkeypatch.setattr(settings, "payment_environment", "test")
    monkeypatch.setattr(settings, "portone_channel_key_card", "entrypoint-card")
    monkeypatch.setattr(settings, "portone_webhook_secret", SECRET)


@pytest_asyncio.fixture
async def provider(test_engine, monkeypatch):
    adapter = Provider()
    event.listen(test_engine.sync_engine, "checkout", adapter.checkout)
    event.listen(test_engine.sync_engine, "checkin", adapter.checkin)
    monkeypatch.setattr(payment_complete_service, "PortOneRestAdapter", lambda secret: adapter)
    yield adapter
    event.remove(test_engine.sync_engine, "checkout", adapter.checkout)
    event.remove(test_engine.sync_engine, "checkin", adapter.checkin)


@pytest_asyncio.fixture
async def api(async_client, session_factory):
    app.dependency_overrides[get_payment_session_factory] = lambda: session_factory
    yield async_client
    app.dependency_overrides.pop(get_payment_session_factory, None)


@pytest_asyncio.fixture
async def order(db_session, user):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session, work, price=500, is_free=False, content=doc(PAYWALL, para("유료 본문"))
    )
    now = datetime.now(UTC)
    row = PaymentOrder(
        id=uuid.uuid4(),
        payment_id="entrypoint-payment",
        user_id=user.id,
        kind="episode_purchase",
        episode_id=episode.id,
        expected_amount=500,
        store_id="entrypoint-store",
        requested_channel_key="entrypoint-card",
        requested_payment_method="PaymentMethodCard",
        environment="test",
        order_name="회차",
        item_title="회차",
        status="ready",
        checkout_notice_version="episode-immediate-v1",
        immediate_supply_consented_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    db_session.add(row)
    await db_session.commit()
    return row


def login(api, user_id):
    api.cookies.set(access_cookie_name(), create_access_token(str(user_id)), domain="test.example")


def no_store(response, status):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"


async def rows(factory, model):
    async with factory() as session:
        return (await session.exec(select(model))).all()


def signed(payload, *, webhook_id="entrypoint-event", timestamp=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    message = webhook_id.encode() + b"." + timestamp.encode() + b"." + payload
    signature = base64.b64encode(hmac.digest(RAW_SECRET, message, hashlib.sha256)).decode()
    return {
        "Webhook-Id": webhook_id,
        "Webhook-Timestamp": timestamp,
        "Webhook-Signature": f"v1,{signature}",
    }


def webhook_body(event_type="Transaction.Paid", payment_id="entrypoint-payment"):
    return json.dumps(
        {"type": event_type, "data": {"paymentId": payment_id, "email": "private@example.com"}}
    ).encode()


async def test_complete_verifies_provider_and_duplicate_grants_once(
    api, order, user, provider, session_factory
):
    assert user.is_email_verified is False
    login(api, user.id)
    for _ in range(2):
        response = await api.post(f"/payments/{order.payment_id}/complete")
        no_store(response, 200)
        assert response.json() == {"payment_id": order.payment_id, "status": "paid"}
    assert len(await rows(session_factory, Purchase)) == 1
    logs = await rows(session_factory, PaymentLog)
    assert len(logs) == 2
    assert all(log.source == "browser" for log in logs)
    assert provider.gets == [(order.payment_id, "entrypoint-store")] * 2
    assert provider.closed


@pytest.mark.parametrize("case", ["anonymous", "other_owner", "other_environment", "missing"])
async def test_complete_access_boundary(api, order, user, db_session, provider, case):
    if case == "other_owner":
        other = User(email="other@example.com", nickname="other")
        db_session.add(other)
        await db_session.commit()
        login(api, other.id)
    elif case != "anonymous":
        login(api, user.id)
    if case == "other_environment":
        order.environment = "live"
        db_session.add(order)
        await db_session.commit()
    payment_id = "missing" if case == "missing" else order.payment_id
    no_store(
        await api.post(f"/payments/{payment_id}/complete"), 401 if case == "anonymous" else 404
    )
    assert provider.gets == []


async def test_complete_ignores_client_payment_claims(api, order, user, provider, session_factory):
    login(api, user.id)
    provider.changes = {"status": "FAILED"}
    response = await api.post(
        f"/payments/{order.payment_id}/complete",
        json={"status": "paid", "amount": 1, "user_id": str(user.id)},
    )
    no_store(response, 200)
    assert response.json()["status"] == "ready"
    assert await rows(session_factory, Purchase) == []
    assert (await rows(session_factory, PaymentOrder))[0].expected_amount == 500


@pytest.mark.parametrize("case", ["provider_failure", "stale"])
async def test_complete_failure_preserves_entitlement_boundary(
    api, order, user, provider, session_factory, case
):
    login(api, user.id)
    if case == "provider_failure":
        provider.failure = True
    else:

        async def change_after_get():
            async with session_factory() as session, session.begin():
                row = await session.get(PaymentOrder, order.id)
                row.status = "review_required"
                session.add(row)

        provider.hook = change_after_get
    response = await api.post(f"/payments/{order.payment_id}/complete")
    no_store(response, 503 if case == "provider_failure" else 409)
    assert "private-provider-body" not in response.text
    assert await rows(session_factory, Purchase) == []


async def test_complete_rate_limit_no_store(api, user, provider):
    login(api, user.id)
    for _ in range(20):
        no_store(await api.post("/payments/missing/complete"), 404)
    response = await api.post("/payments/missing/complete")
    no_store(response, 429)
    assert response.headers["retry-after"] == "60"
    assert provider.gets == []


async def test_complete_long_id_validation_no_store(api, user):
    login(api, user.id)
    no_store(await api.post(f"/payments/{'x' * 65}/complete"), 422)


async def test_webhook_durable_duplicate_and_unknown(api, provider, session_factory):
    payload = webhook_body()
    no_store(
        await api.post("/payments/webhooks/portone", content=payload, headers=signed(payload)), 204
    )
    first = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert first.payment_id == "entrypoint-payment"
    assert first.processed_at is None and first.ignored_at is None and first.attempts == 0
    changed = webhook_body("Transaction.Cancelled", "different-payment")
    no_store(
        await api.post("/payments/webhooks/portone", content=changed, headers=signed(changed)), 204
    )
    receipts = await rows(session_factory, PaymentWebhookReceipt)
    assert len(receipts) == 1
    assert receipts[0].model_dump() == first.model_dump()
    unknown = webhook_body("Transaction.FutureState")
    no_store(
        await api.post(
            "/payments/webhooks/portone",
            content=unknown,
            headers=signed(unknown, webhook_id="future-event"),
        ),
        204,
    )
    unknown_receipt = next(
        row
        for row in await rows(session_factory, PaymentWebhookReceipt)
        if row.webhook_id == "future-event"
    )
    assert unknown_receipt.ignored_at is not None
    assert provider.gets == []
    assert await rows(session_factory, Purchase) == []
    assert "private@example.com" not in repr(receipts)


@pytest.mark.parametrize("case", ["unsigned", "old", "tampered", "malformed", "invalid_shape"])
async def test_webhook_rejects_invalid_signature_or_body(api, session_factory, caplog, case):
    payload = webhook_body()
    headers = signed(payload)
    if case == "unsigned":
        headers = {}
    elif case == "old":
        headers = signed(payload, timestamp=int(time.time()) - 600)
    elif case == "tampered":
        payload = payload.replace(b"entrypoint-payment", b"tampered-payment")
    else:
        payload = b"{private@example.com" if case == "malformed" else b'["private@example.com"]'
        headers = signed(payload)
    response = await api.post("/payments/webhooks/portone", content=payload, headers=headers)
    no_store(response, 400)
    assert await rows(session_factory, PaymentWebhookReceipt) == []
    combined = response.text + caplog.text
    assert "private@example.com" not in combined
    assert SECRET.get_secret_value() not in combined
    assert headers.get("Webhook-Signature", "v1,not-present") not in combined


async def test_webhook_missing_secret_and_oversize(api, session_factory, monkeypatch):
    payload = webhook_body()
    monkeypatch.setattr(settings, "portone_webhook_secret", SecretStr(""))
    no_store(
        await api.post("/payments/webhooks/portone", content=payload, headers=signed(payload)), 503
    )
    monkeypatch.setattr(settings, "portone_webhook_secret", SECRET)
    payload = b"x" * 65537
    no_store(
        await api.post("/payments/webhooks/portone", content=payload, headers=signed(payload)), 413
    )
    assert await rows(session_factory, PaymentWebhookReceipt) == []


async def test_webhook_commit_failure_is_retryable(api, session_factory, test_engine):
    def fail_commit(connection):
        raise SQLAlchemyError("private-database-error")

    payload = webhook_body()
    event.listen(test_engine.sync_engine, "commit", fail_commit)
    try:
        response = await api.post(
            "/payments/webhooks/portone", content=payload, headers=signed(payload)
        )
    finally:
        event.remove(test_engine.sync_engine, "commit", fail_commit)
    no_store(response, 503)
    assert "private-database-error" not in response.text
    assert await rows(session_factory, PaymentWebhookReceipt) == []


async def test_browser_and_webhook_worker_race_grants_once(
    api, order, user, provider, session_factory
):
    from src.services.payment_webhook_service import process_webhook_receipts

    login(api, user.id)
    payload = webhook_body()
    no_store(
        await api.post("/payments/webhooks/portone", content=payload, headers=signed(payload)), 204
    )
    barrier = asyncio.Barrier(2)
    provider.hook = barrier.wait
    response, processed = await asyncio.gather(
        api.post(f"/payments/{order.payment_id}/complete"),
        process_webhook_receipts(session_factory, provider),
    )
    assert processed == 1
    assert response.status_code in {200, 409}
    assert response.headers["cache-control"] == "no-store"
    assert len(await rows(session_factory, Purchase)) == 1
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    provider.hook = None
    if receipt.processed_at is None:
        assert receipt.next_attempt_at is not None
        assert (
            await process_webhook_receipts(
                session_factory, provider, now=receipt.next_attempt_at + timedelta(seconds=1)
            )
            == 1
        )
    receipt = (await rows(session_factory, PaymentWebhookReceipt))[0]
    assert receipt.processed_at is not None
    assert len(await rows(session_factory, Purchase)) == 1
