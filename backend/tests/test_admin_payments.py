import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event

from src.config import settings
from src.models.payment import PaymentLog, Purchase
from src.models.user import RoleEnum
from src.services import payment_admin_service
from tests import test_payment_entrypoints as entrypoints
from tests.test_payment_entrypoints import (
    Provider,
    login,
    no_store,
    rows,
)

api = entrypoints.api
order = entrypoints.order
payment_settings = entrypoints.payment_settings

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def provider(test_engine, monkeypatch):
    adapter = Provider()
    event.listen(test_engine.sync_engine, "checkout", adapter.checkout)
    event.listen(test_engine.sync_engine, "checkin", adapter.checkin)
    monkeypatch.setattr(payment_admin_service, "PortOneRestAdapter", lambda secret: adapter)
    yield adapter
    event.remove(test_engine.sync_engine, "checkout", adapter.checkout)
    event.remove(test_engine.sync_engine, "checkin", adapter.checkin)


async def owner_login(api, user, db_session):
    user.role = RoleEnum.OWNER
    user.totp_confirmed_at = datetime.now(UTC)
    db_session.add(user)
    await db_session.commit()
    login(api, user.id)


@pytest.mark.parametrize("role", [None, "reader", "moderator", "owner"])
async def test_sync_owner_boundary(api, order, user, db_session, provider, role):
    if role:
        user.role = RoleEnum(role)
        db_session.add(user)
        await db_session.commit()
        login(api, user.id)
    no_store(await api.post(f"/admin/payments/{order.id}/sync"), 401 if role is None else 403)
    assert provider.gets == []


@pytest.mark.parametrize("order_id,status", [("invalid", 422), (str(uuid.uuid4()), 404)])
async def test_sync_id_boundary(api, user, db_session, provider, order_id, status):
    await owner_login(api, user, db_session)
    no_store(await api.post(f"/admin/payments/{order_id}/sync"), status)
    assert provider.gets == []


async def test_sync_historic_order_with_new_payments_disabled(
    api, order, user, db_session, provider, session_factory, monkeypatch
):
    await owner_login(api, user, db_session)
    monkeypatch.setattr(settings, "payment_environment", "live")
    monkeypatch.setattr(settings, "portone_store_id", "current-live-store")
    monkeypatch.setattr(settings, "payments_accept_new", False)
    response = await api.post(f"/admin/payments/{order.id}/sync")
    no_store(response, 200)
    assert response.json() == {"payment_id": order.payment_id, "status": "paid"}
    assert provider.gets == [(order.payment_id, "entrypoint-store")]
    assert provider.closed
    assert len(await rows(session_factory, Purchase)) == 1
    assert (await rows(session_factory, PaymentLog))[0].source == "admin"


async def test_sync_provider_failure(api, order, user, db_session, provider, session_factory):
    await owner_login(api, user, db_session)
    provider.failure = True
    response = await api.post(f"/admin/payments/{order.id}/sync")
    no_store(response, 503)
    assert "private-provider-body" not in response.text
    assert await rows(session_factory, Purchase) == []


@pytest.mark.parametrize("case", ["missing", "stale", "database"])
async def test_sync_error_mapping(
    api, order, user, db_session, provider, session_factory, monkeypatch, case
):
    from unittest.mock import AsyncMock

    from sqlalchemy.exc import SQLAlchemyError

    from src.models.payment import PaymentOrder
    from src.routers import admin_payments

    await owner_login(api, user, db_session)
    if case == "missing":
        provider.get_payment = AsyncMock(return_value=None)
    elif case == "stale":

        async def change():
            async with session_factory() as session, session.begin():
                current = await session.get(PaymentOrder, order.id)
                current.status = "review_required"
                session.add(current)

        provider.hook = change
    else:
        monkeypatch.setattr(
            admin_payments,
            "sync_admin_payment",
            AsyncMock(side_effect=SQLAlchemyError("private-body")),
        )
    response = await api.post(f"/admin/payments/{order.id}/sync")
    no_store(response, 409 if case == "stale" else 503)
    assert "private-body" not in response.text
    assert await rows(session_factory, Purchase) == []


async def test_sync_missing_secret(api, order, user, db_session, monkeypatch):
    from pydantic import SecretStr

    await owner_login(api, user, db_session)
    monkeypatch.setattr(settings, "portone_v2_api_secret", SecretStr(""))
    no_store(await api.post(f"/admin/payments/{order.id}/sync"), 503)


async def test_sync_rate_limit(api, user, db_session, provider):
    await owner_login(api, user, db_session)
    path = f"/admin/payments/{uuid.uuid4()}/sync"
    for _ in range(20):
        no_store(await api.post(path), 404)
    response = await api.post(path)
    no_store(response, 429)
    assert response.headers["retry-after"] == "60"
    assert provider.gets == []


@pytest.mark.parametrize("lost_token", [False, True])
async def test_sync_system_cancel_reuses_request_or_recovers_terminal(
    api, order, user, db_session, provider, session_factory, lost_token
):
    from unittest.mock import AsyncMock

    from src.models.payment import PaymentCancelReason, PaymentOrder
    from src.services.payment_cancellation_service import prepare_system_cancellation
    from src.services.portone_rest import PortOneCancellationSnapshot

    await owner_login(api, user, db_session)
    snapshot = await provider.get_payment(order.payment_id, store_id=order.store_id)
    async with session_factory() as session, session.begin():
        await prepare_system_cancellation(
            session, order.id, PaymentCancelReason.SYSTEM_VERIFICATION, snapshot, datetime.now(UTC)
        )
    async with session_factory() as session, session.begin():
        pending = await session.get(PaymentOrder, order.id)
        key, request = pending.cancel_idempotency_key, pending.cancel_request_snapshot
        if lost_token:
            pending.cancel_dispatch_token = uuid.uuid4()
            pending.cancel_dispatch_started_at = datetime.now(UTC)
            session.add(pending)
    provider.cancel_payment = AsyncMock(
        return_value=PortOneCancellationSnapshot.from_payload(
            {"id": "owner-cancel", "status": "SUCCEEDED", "totalAmount": 500}
        )
    )
    response = await api.post(f"/admin/payments/{order.id}/sync")
    no_store(response, 200)
    if lost_token:
        assert response.json()["status"] == "cancel_pending"
        provider.cancel_payment.assert_not_awaited()
        provider.changes = {"status": "CANCELLED"}
        response = await api.post(f"/admin/payments/{order.id}/sync")
        no_store(response, 200)
        provider.cancel_payment.assert_not_awaited()
    else:
        provider.cancel_payment.assert_awaited_once()
        sent = provider.cancel_payment.await_args.kwargs
        assert sent["payment_id"] == order.payment_id
        assert sent["idempotency_key"] == key
        assert sent["request"].snapshot() == request
        assert response.json()["status"] == "cancel_pending"
        provider.changes = {"status": "CANCELLED"}
        response = await api.post(f"/admin/payments/{order.id}/sync")
        no_store(response, 200)
        assert provider.cancel_payment.await_count == 1
    assert response.json()["status"] == "cancelled"
    async with session_factory() as session:
        final = await session.get(PaymentOrder, order.id)
        assert final.cancel_idempotency_key == key
        assert final.cancel_request_snapshot == request
        assert final.cancel_dispatch_token is None
