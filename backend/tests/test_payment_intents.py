import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.config import settings
from src.lib.auth import access_cookie_name, create_access_token
from src.models.payment import PaymentOrder, PaymentOrderStatus, Purchase, PurchaseStatus
from src.models.user import User
from src.models.work import Episode, Work
from src.schemas.payment import EpisodePaymentIntentCreate
from src.services import payment_intent_service as intents
from src.services.portone_rest import PortOnePaymentSnapshot, PortOneTransportError
from tests.factories import PAYWALL, doc, make_episode, make_work, para

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def payment_settings(monkeypatch):
    for name, value in {
        "payments_accept_new": True,
        "payment_environment": "test",
        "portone_store_id": "store-intent-test",
        "portone_channel_key_card": "channel-card-test",
        "portone_channel_key_kakaopay": "channel-kakao-test",
        "portone_channel_key_tosspay": "channel-toss-test",
    }.items():
        monkeypatch.setattr(settings, name, value)


@pytest_asyncio.fixture
async def checkout(db_session, user):
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()
    work = await make_work(db_session, user, episode_base_price=500)
    episode = await make_episode(
        db_session, work, price=None, is_free=False, content=doc(PAYWALL, para("유료 본문"))
    )
    return user.id, work.id, episode.id


def body(episode_id, **overrides):
    return EpisodePaymentIntentCreate.model_validate(
        {
            "episode_id": episode_id,
            "expected_amount": 500,
            "payment_method": "card",
            "checkout_notice_version": intents.NOTICE_VERSION,
            "immediate_supply_consented": True,
            **overrides,
        }
    )


class FakePortOne:
    def __init__(self, session, session_factory):
        self.session = session
        self.session_factory = session_factory
        self.registered = []
        self.gets = []
        self.state = "READY"
        self.not_found = False
        self.fail_get = False
        self.fail_register = False
        self.hook = None
        self.snapshot_overrides = {}
        self.closed = False

    async def aclose(self):
        self.closed = True

    async def get_payment(self, payment_id, *, store_id):
        assert not self.session.in_transaction()
        self.gets.append((payment_id, store_id))
        if self.fail_get:
            raise PortOneTransportError("private-provider-body")
        if self.hook:
            await self.hook()
        if self.not_found:
            return None
        async with self.session_factory() as session:
            order = (
                await session.exec(
                    select(PaymentOrder).where(PaymentOrder.payment_id == payment_id)
                )
            ).one()
            return PortOnePaymentSnapshot.from_payload(
                {
                    "status": self.state,
                    "id": payment_id,
                    "storeId": store_id,
                    "amount": {"total": order.expected_amount},
                    "currency": "KRW",
                    "channel": {"key": order.requested_channel_key},
                    **self.snapshot_overrides,
                }
            )

    async def pre_register_payment(self, **kwargs):
        assert not self.session.in_transaction()
        async with self.session_factory() as session:
            order = (
                await session.exec(
                    select(PaymentOrder).where(PaymentOrder.payment_id == kwargs["payment_id"])
                )
            ).one()
            assert order.status == PaymentOrderStatus.PREPARING
            assert order.expected_amount == kwargs["total_amount"]
        self.registered.append(kwargs)
        if self.hook:
            await self.hook()
        if self.fail_register:
            raise PortOneTransportError("private-provider-body")


async def orders(session):
    return list(
        (await session.exec(select(PaymentOrder).execution_options(populate_existing=True))).all()
    )


@pytest.mark.parametrize(
    "method,channel,pay_method",
    [
        ("card", "channel-card-test", "CARD"),
        ("kakaopay", "channel-kakao-test", "EASY_PAY"),
        ("tosspay", "channel-toss-test", "EASY_PAY"),
    ],
)
async def test_new_intent_and_ready_reuse(
    db_session, session_factory, checkout, method, channel, pay_method
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    request = body(episode_id, payment_method=method)
    first = await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    second = await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert first.payment_id == second.payment_id
    assert first.payment_id.startswith("pay_") and len(first.payment_id) == 36
    assert first.channel_key == channel and first.pay_method == pay_method
    assert first.total_amount == 500 and first.currency == "KRW"
    assert not first.reused and second.reused
    assert len(adapter.registered) == len(adapter.gets) == 1
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.READY
    assert order.immediate_supply_consented_at is not None
    assert order.expires_at - order.immediate_supply_consented_at == timedelta(minutes=30)
    assert order.next_reconcile_at == order.expires_at


@pytest.mark.parametrize("old_price,new_price", [(700, 500), (500, 700)])
async def test_price_change_expires_old_checkout(
    db_session, session_factory, checkout, old_price, new_price
):
    user_id, work_id, episode_id = checkout
    work = await db_session.get(Work, work_id)
    work.episode_base_price = old_price
    db_session.add(work)
    await db_session.commit()
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(
        body(episode_id, expected_amount=old_price), user_id, db_session, adapter=adapter
    )
    async with session_factory() as other:
        current = await other.get(Work, work_id)
        current.episode_base_price = new_price
        other.add(current)
        await other.commit()
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(
            body(episode_id, expected_amount=new_price), user_id, db_session, adapter=adapter
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == {
        "code": "checkout_changed",
        "episode_id": str(episode_id),
        "item_title": "1화",
        "total_amount": new_price,
        "currency": "KRW",
        "notice_version": intents.NOTICE_VERSION,
    }
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.EXPIRED
    assert order.expected_amount == old_price and order.next_reconcile_at is not None
    assert len(adapter.registered) == 1


@pytest.mark.parametrize("change", ["method", "channel", "notice", "expired"])
async def test_incompatible_checkout_never_returns_config(
    db_session, session_factory, checkout, monkeypatch, change
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    request = body(episode_id)
    if change == "method":
        request = body(episode_id, payment_method="kakaopay")
    elif change == "channel":
        monkeypatch.setattr(settings, "portone_channel_key_card", "new-card-channel")
    else:
        (order,) = await orders(db_session)
        if change == "notice":
            order.checkout_notice_version = "previous-notice"
        else:
            order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db_session.add(order)
        await db_session.commit()
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert exc.value.detail["code"] == "checkout_changed"
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.EXPIRED
    assert len(adapter.registered) == 1


@pytest.mark.parametrize(
    "state",
    [
        "PAID",
        "CANCELLED",
        "PARTIAL_CANCELLED",
        "PENDING",
        "PAY_PENDING",
        "VIRTUAL_ACCOUNT_ISSUED",
        "UNKNOWN",
        "transport",
    ],
)
@pytest.mark.parametrize("incompatible", [False, True])
async def test_uncertain_or_approved_provider_never_reopens_or_expires(
    db_session, session_factory, checkout, state, incompatible
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    adapter.state = state
    adapter.fail_get = state == "transport"
    request = body(episode_id, payment_method="kakaopay" if incompatible else "card")
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert exc.value.status_code in {409, 503}
    assert "private-provider-body" not in str(exc.value.detail)
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.READY
    assert len(adapter.registered) == 1


@pytest.mark.parametrize("provider_registered", [False, True])
async def test_preparing_retry_preserves_id_after_failure(
    db_session, session_factory, checkout, monkeypatch, provider_registered
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    original_commit = db_session.commit
    if provider_registered:

        async def fail_commit():
            raise SQLAlchemyError("private-db-body")

        async def fail_local_save():
            monkeypatch.setattr(db_session, "commit", fail_commit)

        adapter.hook = fail_local_save
    else:
        adapter.fail_register = True
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    assert exc.value.status_code in {502, 503}
    monkeypatch.setattr(db_session, "commit", original_commit)
    (order,) = await orders(db_session)
    original_id = order.payment_id
    assert order.status == PaymentOrderStatus.PREPARING
    await db_session.commit()
    adapter.hook = None
    adapter.fail_register = False
    adapter.not_found = not provider_registered
    result = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    assert result.payment_id == original_id and result.reused
    assert len(adapter.gets) == 1
    assert len(adapter.registered) == (1 if provider_registered else 2)


@pytest.mark.parametrize(
    "mutation", ["episode_private", "work_private", "delete", "price", "state"]
)
async def test_external_success_is_revalidated_with_fresh_locks(
    db_session, session_factory, checkout, mutation
):
    user_id, work_id, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)

    async def mutate():
        async with session_factory() as other:
            work = (
                await other.exec(select(Work).where(Work.id == work_id).with_for_update())
            ).one()
            episode = (
                await other.exec(select(Episode).where(Episode.id == episode_id).with_for_update())
            ).one()
            if mutation == "episode_private":
                episode.is_published = False
            elif mutation == "work_private":
                work.is_published = False
            elif mutation == "delete":
                episode.deleted_at = datetime.now(UTC)
                episode.is_published = False
            elif mutation == "price":
                episode.price = 700
            else:
                (order,) = await orders(other)
                order.status = PaymentOrderStatus.EXPIRED
                other.add(order)
            other.add_all([work, episode])
            await other.commit()

    adapter.hook = mutate
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    expected_status = 404 if mutation in {"episode_private", "work_private", "delete"} else 409
    assert exc.value.status_code == expected_status
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.EXPIRED
    if mutation != "state":
        assert order.next_reconcile_at is not None
    assert not (await db_session.exec(select(Purchase))).all()


async def test_concurrent_requests_share_one_order(db_session, session_factory, checkout):
    user_id, _, episode_id = checkout
    entered, release = asyncio.Event(), asyncio.Event()
    first_adapter = None

    async def wait_for_second():
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=5)

    async def first():
        nonlocal first_adapter
        async with session_factory() as session:
            first_adapter = FakePortOne(session, session_factory)
            first_adapter.hook = wait_for_second
            return await intents.create_episode_intent(
                body(episode_id), user_id, session, adapter=first_adapter
            )

    task = asyncio.create_task(first())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        async with session_factory() as session:
            second_adapter = FakePortOne(session, session_factory)
            second_adapter.not_found = True
            result = await intents.create_episode_intent(
                body(episode_id), user_id, session, adapter=second_adapter
            )
    finally:
        release.set()
    first_result = await asyncio.wait_for(task, timeout=5)
    assert first_result.payment_id == result.payment_id
    assert first_adapter is not None
    assert first_adapter.registered[0]["payment_id"] == second_adapter.registered[0]["payment_id"]
    assert len(await orders(db_session)) == 1


@pytest.mark.parametrize(
    "change",
    ["method", "amount", "notice"],
)
async def test_unique_loser_revalidates_winner(
    db_session, session_factory, checkout, monkeypatch, change
):
    user_id, work_id, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    request = body(episode_id)
    if change == "amount":
        work = await db_session.get(Work, work_id)
        work.episode_base_price = 700
        db_session.add(work)
        await db_session.commit()
        request = body(episode_id, expected_amount=700)
    first = await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    request = body(episode_id, payment_method="kakaopay" if change == "method" else "card")
    if change == "amount":
        work = await db_session.get(Work, work_id)
        work.episode_base_price = 500
        db_session.add(work)
        await db_session.commit()
    elif change == "notice":
        (order,) = await orders(db_session)
        order.checkout_notice_version = "old-notice"
        db_session.add(order)
        await db_session.commit()
    original_open = intents._open_order
    calls = 0

    async def miss_once(*args):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await original_open(*args)

    monkeypatch.setattr(intents, "_open_order", miss_once)
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert exc.value.detail["code"] == "checkout_changed"
    (order,) = await orders(db_session)
    assert order.payment_id == first.payment_id and order.status == PaymentOrderStatus.EXPIRED
    assert len(adapter.registered) == 1


@pytest.mark.parametrize("invalid", ["zero", "free", "no_paywall", "private", "purchased"])
async def test_unpurchasable_content_never_calls_provider(
    db_session, session_factory, checkout, invalid
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    episode = await db_session.get(Episode, episode_id)
    if invalid == "zero":
        episode.price = 0
    elif invalid == "free":
        episode.is_free = True
    elif invalid == "no_paywall":
        episode.content = doc(para("무료"))
    elif invalid == "private":
        episode.is_published = False
    else:
        await db_session.commit()
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
        (order,) = await orders(db_session)
        order.status = PaymentOrderStatus.PAID
        order.paid_at = datetime.now(UTC)
        db_session.add(order)
        await db_session.commit()
        db_session.add(
            Purchase(
                payment_order_id=order.id,
                user_id=user_id,
                episode_id=episode_id,
                environment=order.environment,
                amount=500,
                paid_at=order.paid_at,
                status=PurchaseStatus.ACTIVE,
            )
        )
        await db_session.commit()
        adapter.registered.clear()
    if invalid != "purchased":
        db_session.add(episode)
        await db_session.commit()
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    expected_status = 404 if invalid == "private" else 409
    assert exc.value.status_code == expected_status
    assert not adapter.registered and not adapter.gets


async def test_http_auth_validation_kill_switch_and_rate_limit(
    async_client, db_session, checkout, monkeypatch
):
    user_id, _, episode_id = checkout
    payload = body(episode_id).model_dump(mode="json")
    url = "/payments/episode-intents"
    response = await async_client.post(url, json=payload)
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    async_client.cookies.set(
        access_cookie_name(), create_access_token(str(user_id)), domain="test.example"
    )
    user = await db_session.get(User, user_id)
    user.is_email_verified = False
    db_session.add(user)
    await db_session.commit()
    response = await async_client.post(url, json=payload)
    assert response.status_code == 403 and response.headers["cache-control"] == "no-store"
    user.is_email_verified = True
    db_session.add(user)
    await db_session.commit()
    monkeypatch.setattr(settings, "payments_accept_new", False)
    for index in range(9):
        response = await async_client.post(url, json=payload)
        assert response.status_code == (503 if index < 8 else 429)
        assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"]
    assert not await orders(db_session)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_amount": 0},
        {"expected_amount": 2_147_483_648},
        {"expected_amount": True},
        {"expected_amount": "500"},
        {"immediate_supply_consented": False},
        {"immediate_supply_consented": "true"},
        {"payment_method": "bank"},
        {"unexpected": "private-input-secret"},
    ],
)
async def test_invalid_http_input_is_no_store_and_never_echoed(async_client, checkout, overrides):
    user_id, _, episode_id = checkout
    async_client.cookies.set(
        access_cookie_name(), create_access_token(str(user_id)), domain="test.example"
    )
    response = await async_client.post(
        "/payments/episode-intents", json={**body(episode_id).model_dump(mode="json"), **overrides}
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "private-input-secret" not in response.text


async def test_ready_without_channel_recovers_preparing(db_session, session_factory, checkout):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    adapter.fail_register = True
    with pytest.raises(intents.IntentError):
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    adapter.fail_register = False
    adapter.snapshot_overrides = {"channel": None}
    result = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    assert result.reused and result.channel_key == "channel-card-test"
    assert len(adapter.registered) == 1


async def test_failed_provider_state_does_not_promote_preparing(
    db_session, session_factory, checkout
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    adapter.fail_register = True
    with pytest.raises(intents.IntentError):
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    adapter.fail_register = False
    adapter.state = "FAILED"
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    assert exc.value.status_code == 409
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.PREPARING
    assert len(adapter.registered) == 1


@pytest.mark.parametrize(
    "method,provider_method",
    [
        ("card", {"type": "PaymentMethodCard"}),
        ("kakaopay", {"type": "PaymentMethodEasyPay", "provider": "KAKAOPAY"}),
        ("tosspay", {"type": "PaymentMethodEasyPay", "provider": "TOSSPAY"}),
    ],
)
async def test_ready_provider_method_matches_server_capability(
    db_session, session_factory, checkout, method, provider_method
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    request = body(episode_id, payment_method=method)
    await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    adapter.snapshot_overrides = {"method": provider_method}
    result = await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert result.reused


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "other-payment"},
        {"storeId": "other-store"},
        {"currency": "USD"},
        {"amount": {"total": 700}},
        {"channel": {"key": "other-channel"}},
        {"channel": {"key": "channel-card-test", "type": "LIVE"}},
        {"method": {"type": "PaymentMethodTransfer"}},
        {"method": {"type": "PaymentMethodEasyPay", "provider": "KAKAOPAY"}},
    ],
)
async def test_provider_identity_mismatch_is_not_reused_or_expired(
    db_session, session_factory, checkout, overrides
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    adapter.snapshot_overrides = overrides
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(
            body(episode_id, payment_method="kakaopay"), user_id, db_session, adapter=adapter
        )
    assert exc.value.status_code == 409
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.READY and len(adapter.registered) == 1


async def test_easy_pay_provider_mismatch_is_not_reused(db_session, session_factory, checkout):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    request = body(episode_id, payment_method="kakaopay")
    await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    adapter.snapshot_overrides = {"method": {"type": "PaymentMethodEasyPay", "provider": "TOSSPAY"}}
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(request, user_id, db_session, adapter=adapter)
    assert exc.value.status_code == 409
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.READY


async def test_not_found_ready_does_not_reregister(db_session, session_factory, checkout):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    adapter.not_found = True
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    assert exc.value.status_code == 502 and len(adapter.registered) == 1


async def test_order_changed_during_get_is_not_forced_expired(
    db_session, session_factory, checkout
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)

    async def concurrent_update():
        async with session_factory() as other:
            (order,) = await orders(other)
            order.updated_at += timedelta(seconds=1)
            other.add(order)
            await other.commit()

    adapter.hook = concurrent_update
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(
            body(episode_id, payment_method="kakaopay"), user_id, db_session, adapter=adapter
        )
    assert exc.value.status_code == 409
    (order,) = await orders(db_session)
    assert order.status == PaymentOrderStatus.READY
    assert order.next_reconcile_at == order.expires_at and len(adapter.registered) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_amount": 700},
        {"checkout_notice_version": "old-notice"},
    ],
)
async def test_stale_confirmation_creates_no_order(
    db_session, session_factory, checkout, overrides
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(
            body(episode_id, **overrides), user_id, db_session, adapter=adapter
        )
    assert exc.value.detail["code"] == "checkout_changed"
    assert not await orders(db_session)
    assert not adapter.registered and not adapter.gets


async def test_expired_checkout_requires_confirmation_then_new_id(
    db_session, session_factory, checkout
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    first = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    (order,) = await orders(db_session)
    order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(order)
    await db_session.commit()
    with pytest.raises(intents.IntentError):
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    second = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    assert first.payment_id != second.payment_id and not second.reused
    assert len(await orders(db_session)) == 2


async def test_expired_failed_checkout_requires_confirmation_then_new_id(
    db_session, session_factory, checkout
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    first = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    (order,) = await orders(db_session)
    order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(order)
    await db_session.commit()
    adapter.state = "FAILED"
    adapter.snapshot_overrides = {
        "channel": {"key": "channel-card-test", "type": "TEST"},
        "method": {"type": "PaymentMethodCard"},
    }

    with pytest.raises(intents.IntentError) as exc:
        await intents.create_episode_intent(body(episode_id), user_id, db_session, adapter=adapter)
    assert exc.value.detail["code"] == "checkout_changed"

    second = await intents.create_episode_intent(
        body(episode_id), user_id, db_session, adapter=adapter
    )
    assert first.payment_id != second.payment_id and not second.reused
    assert len(await orders(db_session)) == 2


async def test_http_success_changed_and_provider_failure_are_no_store(
    async_client, db_session, session_factory, checkout, monkeypatch
):
    user_id, _, episode_id = checkout
    adapter = FakePortOne(db_session, session_factory)
    monkeypatch.setattr(intents, "PortOneRestAdapter", lambda _: adapter)
    async_client.cookies.set(
        access_cookie_name(), create_access_token(str(user_id)), domain="test.example"
    )
    url = "/payments/episode-intents"
    payload = body(episode_id).model_dump(mode="json")
    response = await async_client.post(url, json=payload)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {
        "payment_id",
        "store_id",
        "channel_key",
        "order_name",
        "total_amount",
        "currency",
        "pay_method",
        "notice_version",
        "expires_at",
        "reused",
    }
    assert adapter.closed
    adapter.fail_get = True
    response = await async_client.post(url, json=payload)
    assert response.status_code == 503 and response.headers["cache-control"] == "no-store"
    assert "private-provider-body" not in response.text
    adapter.fail_get = False
    response = await async_client.post(url, json={**payload, "payment_method": "kakaopay"})
    assert response.status_code == 409 and response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["code"] == "checkout_changed"
    assert "payment_id" not in response.text and "channel_key" not in response.text
