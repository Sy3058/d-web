"""에피소드 구매 intent 생명주기.

각 PortOne 호출 전 DB transaction을 끝내고, 외부 결과는 새 잠금 transaction에서만
적용한다. PortOne 원문과 secret은 예외나 반환값에 포함하지 않는다.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.content_doc import derive_is_free
from src.models.payment import (
    PaymentEnvironment,
    PaymentOrder,
    PaymentOrderKind,
    PaymentOrderStatus,
    Purchase,
    PurchaseStatus,
)
from src.models.work import Episode, Work
from src.schemas.payment import (
    CheckoutChangedDetail,
    EpisodePaymentIntentCreate,
    EpisodePaymentIntentRead,
    EpisodePaymentMethod,
)
from src.services.portone_rest import (
    PortOneAdapterError,
    PortOneMoneyState,
    PortOnePaymentSnapshot,
    PortOneRestAdapter,
)

NOTICE_VERSION = "episode-immediate-v1"
INTENT_TTL = timedelta(minutes=30)
ORDER_NAME = "웹툰 회차 구매"
_OPEN_STATUSES = (PaymentOrderStatus.PREPARING, PaymentOrderStatus.READY)
_PURCHASE_BLOCKING_STATUSES = (
    PurchaseStatus.ACTIVE,
    PurchaseStatus.REFUND_PENDING,
    PurchaseStatus.REVIEW_REQUIRED,
)


class PaymentAdapter(Protocol):
    async def get_payment(
        self, payment_id: str, *, store_id: str
    ) -> PortOnePaymentSnapshot | None: ...

    async def pre_register_payment(
        self, *, payment_id: str, store_id: str, total_amount: int, currency: str = "KRW"
    ) -> None: ...

    async def aclose(self) -> None: ...


class IntentError(RuntimeError):
    def __init__(self, status_code: int, detail: str | dict) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__("payment intent failed")


@dataclass(frozen=True, slots=True)
class _Checkout:
    episode_id: uuid.UUID
    item_title: str
    amount: int
    channel_key: str
    pay_method: str


def _now() -> datetime:
    return datetime.now(UTC)


def _environment() -> PaymentEnvironment:
    return PaymentEnvironment(settings.payment_environment)


def _channel(method: EpisodePaymentMethod) -> tuple[str, str]:
    values = {
        EpisodePaymentMethod.CARD: (settings.portone_channel_key_card, "CARD"),
        EpisodePaymentMethod.KAKAOPAY: (settings.portone_channel_key_kakaopay, "EASY_PAY"),
        EpisodePaymentMethod.TOSSPAY: (settings.portone_channel_key_tosspay, "EASY_PAY"),
    }
    channel_key, pay_method = values[method]
    if not channel_key.strip():
        raise IntentError(409, "선택한 결제수단을 사용할 수 없습니다")
    return channel_key, pay_method


def _changed(checkout: _Checkout) -> IntentError:
    detail = CheckoutChangedDetail(
        episode_id=checkout.episode_id,
        item_title=checkout.item_title,
        total_amount=checkout.amount,
        notice_version=NOTICE_VERSION,
    )
    return IntentError(409, detail.model_dump(mode="json"))


async def _lock_checkout(session: AsyncSession, episode_id: uuid.UUID) -> _Checkout:
    episode_ref = (
        await session.exec(select(Episode.work_id).where(Episode.id == episode_id))
    ).one_or_none()
    if episode_ref is None:
        raise IntentError(404, "회차를 찾을 수 없습니다")

    work = (
        await session.exec(
            select(Work)
            .where(Work.id == episode_ref)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    episode = (
        await session.exec(
            select(Episode)
            .where(Episode.id == episode_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if (
        work is None
        or episode is None
        or work.deleted_at is not None
        or episode.deleted_at is not None
        or not work.is_published
        or not episode.is_published
    ):
        raise IntentError(404, "회차를 찾을 수 없습니다")
    if episode.is_free or derive_is_free(episode.content):
        raise IntentError(409, "구매할 수 없는 회차입니다")
    amount = episode.price if episode.price is not None else work.episode_base_price
    if amount <= 0:
        raise IntentError(409, "구매할 수 없는 회차입니다")
    return _Checkout(episode.id, episode.title, amount, "", "")


async def _open_order(
    session: AsyncSession, user_id: uuid.UUID, episode_id: uuid.UUID
) -> PaymentOrder | None:
    return (
        await session.exec(
            select(PaymentOrder)
            .where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.episode_id == episode_id,
                PaymentOrder.environment == _environment(),
                PaymentOrder.kind == PaymentOrderKind.EPISODE_PURCHASE,
                PaymentOrder.status.in_(_OPEN_STATUSES),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()


async def _ensure_not_purchased(
    session: AsyncSession, user_id: uuid.UUID, episode_id: uuid.UUID
) -> None:
    purchase = (
        await session.exec(
            select(Purchase)
            .where(
                Purchase.user_id == user_id,
                Purchase.episode_id == episode_id,
                Purchase.environment == _environment(),
                Purchase.status.in_(_PURCHASE_BLOCKING_STATUSES),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()
    if purchase is not None:
        raise IntentError(409, "이미 구매한 회차입니다")


def _compatible(order: PaymentOrder, body: EpisodePaymentIntentCreate, checkout: _Checkout) -> bool:
    return (
        order.expected_amount == body.expected_amount == checkout.amount
        and order.store_id == settings.portone_store_id
        and order.requested_channel_key == checkout.channel_key
        and order.checkout_notice_version == body.checkout_notice_version == NOTICE_VERSION
    )


def _response(order: PaymentOrder, pay_method: str, *, reused: bool) -> EpisodePaymentIntentRead:
    return EpisodePaymentIntentRead(
        payment_id=order.payment_id,
        store_id=order.store_id,
        channel_key=order.requested_channel_key,
        order_name=order.order_name,
        total_amount=order.expected_amount,
        currency=order.currency,
        pay_method=pay_method,
        notice_version=order.checkout_notice_version or NOTICE_VERSION,
        expires_at=order.expires_at,
        reused=reused,
    )


def _provider_matches(
    order: PaymentOrder,
    snapshot: PortOnePaymentSnapshot,
    *,
    allow_failed_expiration: bool = False,
) -> bool:
    is_ready = snapshot.money_state is PortOneMoneyState.READY
    is_failed_expiration = (
        allow_failed_expiration and snapshot.money_state is PortOneMoneyState.FAILED
    )
    base_matches = (
        (is_ready or is_failed_expiration)
        and snapshot.payment_id == order.payment_id
        and snapshot.store_id == order.store_id
        and snapshot.total_amount == order.expected_amount
        and snapshot.currency == order.currency
        and (
            snapshot.channel_key == order.requested_channel_key
            or (is_ready and snapshot.channel_key is None)
        )
        and (
            snapshot.channel_type == order.environment.upper()
            or (is_ready and snapshot.channel_type is None)
        )
    )
    if not base_matches:
        return False

    # READY는 결제수단 선택 전이라 method 전체가 없을 수 있다. 일부만 온 응답은
    # 신원 근거로 쓰지 않고, method가 있다면 channel의 서버 capability와 모두 맞춘다.
    if snapshot.payment_method is None:
        return is_ready and snapshot.easy_pay_provider is None
    capabilities = {
        settings.portone_channel_key_card: ("PaymentMethodCard", None),
        settings.portone_channel_key_kakaopay: ("PaymentMethodEasyPay", "KAKAOPAY"),
        settings.portone_channel_key_tosspay: ("PaymentMethodEasyPay", "TOSSPAY"),
    }
    expected = capabilities.get(order.requested_channel_key)
    return (
        expected is not None
        and (
            snapshot.payment_method,
            snapshot.easy_pay_provider,
        )
        == expected
    )


async def _load_locked_order(session: AsyncSession, order_id: uuid.UUID) -> PaymentOrder | None:
    return (
        await session.exec(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()


async def _expire_after_provider_check(
    session: AsyncSession,
    order_id: uuid.UUID,
    checkout: _Checkout,
    version: tuple[str, datetime | None],
) -> None:
    try:
        current = await _lock_checkout(session, checkout.episode_id)
    except IntentError as exc:
        order = await _load_locked_order(session, order_id)
        if order is None or (order.status, order.updated_at) != version:
            raise IntentError(409, "결제 상태를 확인 중입니다") from None
        order.status = PaymentOrderStatus.EXPIRED
        order.next_reconcile_at = _now()
        order.needs_action_reason = "content_unavailable"
        session.add(order)
        await session.commit()
        raise IntentError(exc.status_code, exc.detail) from None
    order = await _load_locked_order(session, order_id)
    if order is None or (order.status, order.updated_at) != version:
        raise IntentError(409, "결제 상태를 확인 중입니다")
    order.status = PaymentOrderStatus.EXPIRED
    order.next_reconcile_at = _now()
    order.needs_action_reason = "checkout_changed"
    session.add(order)
    await session.commit()
    raise _changed(current)


async def _finalize_ready(
    session: AsyncSession,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    body: EpisodePaymentIntentCreate,
    checkout: _Checkout,
    pay_method: str,
    *,
    reused: bool,
    version: tuple[str, datetime | None],
) -> EpisodePaymentIntentRead:
    try:
        current = await _lock_checkout(session, body.episode_id)
    except IntentError as exc:
        order = await _load_locked_order(session, order_id)
        if order is not None and (order.status, order.updated_at) == version:
            order.status = PaymentOrderStatus.EXPIRED
            order.next_reconcile_at = _now()
            order.needs_action_reason = "content_unavailable"
            session.add(order)
            await session.commit()
        raise IntentError(exc.status_code, exc.detail) from None
    current = _Checkout(
        current.episode_id, current.item_title, current.amount, checkout.channel_key, pay_method
    )
    order = await _load_locked_order(session, order_id)
    await _ensure_not_purchased(session, user_id, body.episode_id)
    if order is None or order.status not in _OPEN_STATUSES:
        await session.rollback()
        raise IntentError(409, "결제 상태가 변경되었습니다")
    compatible = _compatible(order, body, current)
    if (not compatible or order.expires_at <= _now()) and (
        order.status,
        order.updated_at,
    ) != version:
        raise IntentError(409, "결제 상태가 변경되었습니다")
    if not compatible:
        order.status = PaymentOrderStatus.EXPIRED
        order.next_reconcile_at = _now()
        order.needs_action_reason = "checkout_changed"
        session.add(order)
        await session.commit()
        raise _changed(current)
    if order.expires_at <= _now():
        order.status = PaymentOrderStatus.EXPIRED
        order.next_reconcile_at = _now()
        order.needs_action_reason = "checkout_expired"
        session.add(order)
        await session.commit()
        raise _changed(current)
    order.status = PaymentOrderStatus.READY
    order.prepared_at = order.prepared_at or _now()
    order.next_reconcile_at = order.expires_at
    order.needs_action_reason = None
    session.add(order)
    await session.commit()
    return _response(order, pay_method, reused=reused)


async def create_episode_intent(
    body: EpisodePaymentIntentCreate,
    user_id: uuid.UUID,
    session: AsyncSession,
    *,
    adapter: PaymentAdapter | None = None,
) -> EpisodePaymentIntentRead:
    if not settings.payments_accept_new:
        raise IntentError(503, "현재 새 결제를 받을 수 없습니다")
    if not body.immediate_supply_consented:
        raise IntentError(422, "즉시 제공 동의가 필요합니다")

    channel_key, pay_method = _channel(body.payment_method)
    own_adapter = adapter is None
    if adapter is None:
        adapter = PortOneRestAdapter(settings.portone_v2_api_secret)

    try:
        checkout = await _lock_checkout(session, body.episode_id)
        checkout = _Checkout(
            checkout.episode_id, checkout.item_title, checkout.amount, channel_key, pay_method
        )
        order = await _open_order(session, user_id, body.episode_id)
        await _ensure_not_purchased(session, user_id, body.episode_id)
        if order is None:
            if (
                body.expected_amount != checkout.amount
                or body.checkout_notice_version != NOTICE_VERSION
            ):
                await session.rollback()
                raise _changed(checkout)
            order_id = uuid.uuid4()
            now = _now()
            order = PaymentOrder(
                id=order_id,
                payment_id=f"pay_{order_id.hex}",
                user_id=user_id,
                kind=PaymentOrderKind.EPISODE_PURCHASE,
                episode_id=body.episode_id,
                expected_amount=checkout.amount,
                store_id=settings.portone_store_id,
                requested_channel_key=channel_key,
                environment=_environment(),
                order_name=ORDER_NAME,
                item_title=checkout.item_title,
                checkout_notice_version=NOTICE_VERSION,
                immediate_supply_consented_at=now,
                status=PaymentOrderStatus.PREPARING,
                expires_at=now + INTENT_TTL,
                next_reconcile_at=now,
            )
            session.add(order)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                current = await _lock_checkout(session, body.episode_id)
                checkout = _Checkout(
                    current.episode_id, current.item_title, current.amount, channel_key, pay_method
                )
                order = await _open_order(session, user_id, body.episode_id)
                await _ensure_not_purchased(session, user_id, body.episode_id)
                if order is None:
                    await session.rollback()
                    raise IntentError(409, "결제 상태가 변경되었습니다") from None
                await session.commit()
            is_new = order.id == order_id
        else:
            is_new = False
            await session.commit()

        compatible = _compatible(order, body, checkout)
        unexpired = order.expires_at > _now()
        version = (order.status, order.updated_at)
        snapshot = None
        if not is_new:
            try:
                snapshot = await adapter.get_payment(order.payment_id, store_id=order.store_id)
            except PortOneAdapterError:
                raise IntentError(503, "결제 상태를 확인할 수 없습니다") from None

        if not compatible or not unexpired:
            if snapshot is not None and not _provider_matches(
                order, snapshot, allow_failed_expiration=True
            ):
                raise IntentError(409, "결제 상태를 확인 중입니다")
            await _expire_after_provider_check(session, order.id, checkout, version)

        if snapshot is not None:
            if not _provider_matches(order, snapshot):
                raise IntentError(409, "결제 상태를 확인 중입니다")
            return await _finalize_ready(
                session,
                order.id,
                user_id,
                body,
                checkout,
                pay_method,
                reused=not is_new,
                version=version,
            )

        if order.status == PaymentOrderStatus.READY:
            raise IntentError(502, "결제 준비 상태를 확인할 수 없습니다")
        try:
            await adapter.pre_register_payment(
                payment_id=order.payment_id,
                store_id=order.store_id,
                total_amount=order.expected_amount,
                currency=order.currency,
            )
        except PortOneAdapterError:
            raise IntentError(502, "결제 준비에 실패했습니다") from None
        return await _finalize_ready(
            session,
            order.id,
            user_id,
            body,
            checkout,
            pay_method,
            reused=not is_new,
            version=version,
        )
    except SQLAlchemyError:
        raise IntentError(503, "결제 상태를 저장할 수 없습니다") from None
    finally:
        if session.in_transaction():
            await session.rollback()
        if own_adapter:
            await adapter.aclose()
