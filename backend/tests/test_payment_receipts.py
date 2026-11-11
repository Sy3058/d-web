from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select

from src.models.payment import PaymentOrder, Purchase
from src.services.payment_sync_service import sync_payment
from src.services.portone_rest import PortOneTransportError
from tests.test_payment_entrypoints import login, no_store
from tests.test_payment_sync import NOW, Adapter
from tests.test_payment_sync import cleanup_adapters as cleanup_adapters
from tests.test_payment_sync import orders as orders

pytestmark = pytest.mark.asyncio
RECEIPT = "https://receipt.example/verified-payment"


async def assert_receipt(factory, order_id, expected, viewed_at=None):
    async with factory() as session:
        order = await session.get(PaymentOrder, order_id)
        assert order.receipt_url == expected
        purchases = (
            await session.exec(select(Purchase).where(Purchase.payment_order_id == order_id))
        ).all()
        assert len(purchases) == 1
        assert purchases[0].first_viewed_at == viewed_at


@pytest.mark.parametrize("receipt", [RECEIPT, None, "http://receipt.example/unsafe"])
async def test_verified_sync_receipt_reaches_history(
    orders, session_factory, test_engine, async_client, user, receipt
):
    adapter = Adapter(test_engine, {"receiptUrl": receipt, "transactionId": "original-tx"})
    result = await sync_payment(session_factory, adapter, orders[0].payment_id, "browser", now=NOW)
    assert result == "paid"
    expected = RECEIPT if receipt == RECEIPT else None
    await assert_receipt(session_factory, orders[0].id, expected)
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["receipt_url"] == expected


@pytest.mark.parametrize("transaction_id", [None, "original-tx"])
async def test_paid_order_recovers_receipt_from_verified_requery(
    orders, session_factory, test_engine, async_client, user, transaction_id
):
    adapter = Adapter(test_engine, {"transactionId": transaction_id})
    assert (
        await sync_payment(session_factory, adapter, orders[0].payment_id, "browser", now=NOW)
        == "paid"
    )
    await assert_receipt(session_factory, orders[0].id, None)
    viewed_at = NOW + timedelta(seconds=1)
    async with session_factory() as session:
        purchase = (
            await session.exec(select(Purchase).where(Purchase.payment_order_id == orders[0].id))
        ).one()
        purchase.first_viewed_at = viewed_at
        session.add(purchase)
        await session.commit()
    adapter.changes["receiptUrl"] = RECEIPT
    assert (
        await sync_payment(session_factory, adapter, orders[0].payment_id, "admin", now=NOW)
        == "paid"
    )
    await assert_receipt(session_factory, orders[0].id, RECEIPT, viewed_at)
    login(async_client, user.id)
    response = await async_client.get("/my/purchases")
    no_store(response, 200)
    assert response.json()["items"][0]["receipt_url"] == RECEIPT


@pytest.mark.parametrize(
    "changes",
    [
        {"receiptUrl": None},
        {"receiptUrl": "http://receipt.example/unsafe"},
        {"receiptUrl": "https://u:p@receipt.example/unsafe"},
        {"id": "another-payment"},
        {"storeId": "another-store"},
        {"currency": "USD"},
        {"amount": {"total": 700}},
        {"channel": {"type": "TEST", "key": "another-channel"}},
        {"channel": {"type": "LIVE", "key": "card-channel"}},
        {"method": {"type": "PaymentMethodEasyPay", "provider": "KAKAOPAY"}},
        {"paidAt": "2026-11-06T00:00:00Z"},
        {"transactionId": "another-transaction"},
        {"status": "READY"},
        {"status": "FAILED"},
        {"status": "UNKNOWN"},
    ],
)
async def test_requery_does_not_replace_receipt_with_unverified_metadata(
    orders, session_factory, test_engine, changes
):
    adapter = Adapter(test_engine, {"receiptUrl": RECEIPT, "transactionId": "original-tx"})
    assert (
        await sync_payment(session_factory, adapter, orders[0].payment_id, "browser", now=NOW)
        == "paid"
    )
    adapter.changes = {
        "receiptUrl": "https://receipt.example/replacement",
        "transactionId": "original-tx",
        **changes,
    }
    await sync_payment(session_factory, adapter, orders[0].payment_id, "reconcile", now=NOW)
    await assert_receipt(session_factory, orders[0].id, RECEIPT)


async def test_failed_requery_preserves_receipt(orders, session_factory, test_engine):
    adapter = Adapter(test_engine, {"receiptUrl": RECEIPT})
    assert (
        await sync_payment(session_factory, adapter, orders[0].payment_id, "browser", now=NOW)
        == "paid"
    )
    adapter.get_payment = AsyncMock(side_effect=PortOneTransportError("unavailable"))
    await sync_payment(session_factory, adapter, orders[0].payment_id, "reconcile", now=NOW)
    await assert_receipt(session_factory, orders[0].id, RECEIPT)
