"""M3 결제 주문, 구매 권한, webhook receipt와 감사 로그 모델.

PortOne은 실제 자금 상태, PaymentOrder는 서버 주문과 마지막 동기화 상태,
Purchase는 열람 권한의 진실이다. 외부 응답 원문과 개인정보는 이 모델들에 저장하지 않는다.
모든 상태 enum은 PostgreSQL native enum이 아니라 길이가 고정된 VARCHAR에 저장한다.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlmodel import Field, SQLModel


class PaymentEnvironment(StrEnum):
    TEST = "test"
    LIVE = "live"


class PaymentOrderKind(StrEnum):
    EPISODE_PURCHASE = "episode_purchase"
    DONATION = "donation"


class PaymentOrderStatus(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    EXPIRED = "expired"
    PAID = "paid"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REVIEW_REQUIRED = "review_required"


class PurchaseStatus(StrEnum):
    ACTIVE = "active"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    REVIEW_REQUIRED = "review_required"


class PaymentCancelReason(StrEnum):
    SYSTEM_VERIFICATION = "system_verification"
    SYSTEM_UNAVAILABLE = "system_unavailable"
    SYSTEM_DUPLICATE = "system_duplicate"
    CUSTOMER_REFUND = "customer_refund"


class PaymentLogSource(StrEnum):
    BROWSER = "browser"
    WEBHOOK = "webhook"
    RECONCILE = "reconcile"
    ADMIN = "admin"


def _pk_column() -> Column:
    return Column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _uuid_fk_column(target: str, *, nullable: bool = False, unique: bool = False) -> Column:
    return Column(
        PgUUID(as_uuid=True),
        ForeignKey(target, ondelete="RESTRICT"),
        nullable=nullable,
        unique=unique,
    )


def _created_at_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaymentOrder(SQLModel, table=True):
    __tablename__ = "payment_orders"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "kind IN ('episode_purchase', 'donation')",
            name="ck_payment_orders_kind",
        ),
        CheckConstraint(
            "status IN ('preparing', 'ready', 'expired', 'paid', 'cancel_pending', "
            "'cancelled', 'review_required')",
            name="ck_payment_orders_status",
        ),
        CheckConstraint(
            "environment IN ('test', 'live')",
            name="ck_payment_orders_environment",
        ),
        CheckConstraint("expected_amount > 0", name="ck_payment_orders_expected_amount"),
        CheckConstraint(
            "provider_total_amount IS NULL OR provider_total_amount > 0",
            name="ck_payment_orders_provider_total_amount",
        ),
        CheckConstraint("currency = 'KRW'", name="ck_payment_orders_currency"),
        CheckConstraint(
            "(kind = 'episode_purchase' AND episode_id IS NOT NULL "
            "AND donation_message IS NULL) OR "
            "(kind = 'donation')",
            name="ck_payment_orders_kind_target",
        ),
        CheckConstraint(
            "(kind = 'episode_purchase' AND checkout_notice_version IS NOT NULL "
            "AND immediate_supply_consented_at IS NOT NULL) OR "
            "(kind = 'donation' AND checkout_notice_version IS NULL "
            "AND immediate_supply_consented_at IS NULL)",
            name="ck_payment_orders_purchase_consent",
        ),
        CheckConstraint(
            "reconcile_attempts >= 0",
            name="ck_payment_orders_reconcile_attempts",
        ),
        CheckConstraint(
            "cancelled_amount IS NULL OR "
            "(provider_total_amount IS NOT NULL AND cancelled_amount > 0 "
            "AND cancelled_amount <= provider_total_amount)",
            name="ck_payment_orders_cancelled_amount",
        ),
        CheckConstraint(
            "(cancel_reason IS NULL AND cancel_idempotency_key IS NULL "
            "AND cancel_request_snapshot IS NULL) OR "
            "(cancel_reason IS NOT NULL AND cancel_idempotency_key IS NOT NULL "
            "AND cancel_request_snapshot IS NOT NULL "
            "AND provider_total_amount IS NOT NULL)",
            name="ck_payment_orders_cancel_request_bundle",
        ),
        CheckConstraint(
            "status <> 'cancel_pending' OR cancel_reason IS NOT NULL",
            name="ck_payment_orders_cancel_pending_bundle",
        ),
        CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN "
            "('system_verification', 'system_unavailable', 'system_duplicate', "
            "'customer_refund')",
            name="ck_payment_orders_cancel_reason",
        ),
        CheckConstraint(
            "cancel_request_snapshot IS NULL OR cancel_request_snapshot = "
            "jsonb_build_object("
            "'storeId', store_id, "
            "'reason', cancel_reason, "
            "'amount', provider_total_amount, "
            "'currentCancellableAmount', provider_total_amount, "
            "'requester', CASE WHEN cancel_reason = 'customer_refund' "
            "THEN 'CUSTOMER' ELSE 'ADMIN' END)",
            name="ck_payment_orders_cancel_request_snapshot",
        ),
        CheckConstraint(
            "cancel_idempotency_key IS NULL OR "
            "(char_length(cancel_idempotency_key) BETWEEN 16 AND 256 "
            "AND octet_length(cancel_idempotency_key) = char_length(cancel_idempotency_key) "
            "AND cancel_idempotency_key ~ '^[ -~]+$')",
            name="ck_payment_orders_cancel_idempotency_key",
        ),
        UniqueConstraint(
            "id",
            "user_id",
            "kind",
            "episode_id",
            "environment",
            "expected_amount",
            "paid_at",
            name="uq_payment_orders_purchase_provenance",
        ),
        Index(
            "uq_payment_orders_open_episode_intent",
            "user_id",
            "episode_id",
            "environment",
            unique=True,
            postgresql_where=text("kind = 'episode_purchase' AND status IN ('preparing', 'ready')"),
        ),
        Index(
            "idx_payment_orders_reconcile",
            "environment",
            "status",
            "next_reconcile_at",
        ),
        Index(
            "idx_payment_orders_user_environment_created_at",
            "user_id",
            "environment",
            text("created_at DESC"),
        ),
        Index("idx_payment_orders_episode_id", "episode_id"),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    payment_id: str = Field(sa_column=Column(String(64), nullable=False, unique=True))
    user_id: uuid.UUID = Field(sa_column=_uuid_fk_column("users.id"))
    kind: PaymentOrderKind = Field(sa_column=Column(String(24), nullable=False))
    episode_id: uuid.UUID | None = Field(
        default=None,
        sa_column=_uuid_fk_column("episodes.id", nullable=True),
    )
    expected_amount: int = Field(sa_column=Column(Integer, nullable=False))
    provider_total_amount: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    currency: str = Field(
        default="KRW",
        sa_column=Column(String(3), nullable=False, server_default=text("'KRW'")),
    )
    store_id: str = Field(sa_column=Column(String(255), nullable=False))
    requested_channel_key: str = Field(sa_column=Column(String(255), nullable=False))
    environment: PaymentEnvironment = Field(sa_column=Column(String(8), nullable=False))
    order_name: str = Field(sa_column=Column(String(255), nullable=False))
    item_title: str = Field(sa_column=Column(String(200), nullable=False))
    checkout_notice_version: str | None = Field(
        default=None,
        sa_column=Column(String(32), nullable=True),
    )
    immediate_supply_consented_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    donation_message: str | None = Field(
        default=None,
        sa_column=Column(String(500), nullable=True),
    )
    status: PaymentOrderStatus = Field(sa_column=Column(String(24), nullable=False))
    provider_status: str | None = Field(
        default=None,
        sa_column=Column(String(40), nullable=True),
    )
    transaction_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    cancellation_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    pg_provider: str | None = Field(default=None, sa_column=Column(String(40), nullable=True))
    payment_method: str | None = Field(default=None, sa_column=Column(String(40), nullable=True))
    easy_pay_provider: str | None = Field(
        default=None,
        sa_column=Column(String(40), nullable=True),
    )
    receipt_url: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cancel_reason: PaymentCancelReason | None = Field(
        default=None,
        sa_column=Column(String(40), nullable=True),
    )
    cancel_idempotency_key: str | None = Field(
        default=None,
        sa_column=Column(String(256), nullable=True),
    )
    cancel_request_snapshot: dict | None = Field(
        default=None,
        # JSONB 기본은 Python None을 JSON `null` 값으로 직렬화한다. 취소 요청이 아직
        # 없다는 뜻은 SQL NULL이어야 reason·key·snapshot 묶음 CHECK와 IS NULL 조회가
        # 일치한다.
        sa_column=Column(JSONB(none_as_null=True), nullable=True),
    )
    cancelled_amount: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    next_reconcile_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    reconcile_attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    last_synced_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    needs_action_reason: str | None = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    prepared_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    paid_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    cancelled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class Purchase(SQLModel, table=True):
    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('test', 'live')",
            name="ck_purchases_environment",
        ),
        CheckConstraint(
            "status IN ('active', 'refund_pending', 'refunded', 'review_required')",
            name="ck_purchases_status",
        ),
        CheckConstraint(
            "payment_order_kind = 'episode_purchase'",
            name="ck_purchases_payment_order_kind",
        ),
        CheckConstraint("amount > 0", name="ck_purchases_amount"),
        CheckConstraint(
            "refund_amount IS NULL OR (refund_amount > 0 AND refund_amount <= amount)",
            name="ck_purchases_refund_amount",
        ),
        ForeignKeyConstraint(
            [
                "payment_order_id",
                "user_id",
                "payment_order_kind",
                "episode_id",
                "environment",
                "amount",
                "paid_at",
            ],
            [
                "payment_orders.id",
                "payment_orders.user_id",
                "payment_orders.kind",
                "payment_orders.episode_id",
                "payment_orders.environment",
                "payment_orders.expected_amount",
                "payment_orders.paid_at",
            ],
            name="fk_purchases_payment_order_provenance",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        Index(
            "uq_purchases_entitlement",
            "user_id",
            "episode_id",
            "environment",
            unique=True,
            postgresql_where=text("status IN ('active', 'refund_pending', 'review_required')"),
        ),
        Index("idx_purchases_user_id", "user_id"),
        Index("idx_purchases_episode_id", "episode_id"),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    payment_order_id: uuid.UUID = Field(
        sa_column=Column(PgUUID(as_uuid=True), nullable=False, unique=True)
    )
    user_id: uuid.UUID = Field(sa_column=_uuid_fk_column("users.id"))
    payment_order_kind: PaymentOrderKind = Field(
        default=PaymentOrderKind.EPISODE_PURCHASE,
        sa_column=Column(
            String(24),
            nullable=False,
            server_default=text("'episode_purchase'"),
        ),
    )
    episode_id: uuid.UUID = Field(sa_column=_uuid_fk_column("episodes.id"))
    environment: PaymentEnvironment = Field(sa_column=Column(String(8), nullable=False))
    status: PurchaseStatus = Field(sa_column=Column(String(24), nullable=False))
    amount: int = Field(sa_column=Column(Integer, nullable=False))
    paid_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    first_viewed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    refunded_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    refund_amount: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class PaymentWebhookReceipt(SQLModel, table=True):
    __tablename__ = "payment_webhook_receipts"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_payment_webhook_receipts_attempts"),
        Index(
            "idx_payment_webhook_receipts_pending",
            "next_attempt_at",
            "received_at",
            postgresql_where=text("processed_at IS NULL AND ignored_at IS NULL"),
        ),
        Index("idx_payment_webhook_receipts_payment_id", "payment_id"),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    webhook_id: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    payment_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    event_type: str = Field(sa_column=Column(String(40), nullable=False))
    attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    next_attempt_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    received_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ignored_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class PaymentLog(SQLModel, table=True):
    __tablename__ = "payment_logs"
    __table_args__ = (
        CheckConstraint(
            "source IN ('browser', 'webhook', 'reconcile', 'admin')",
            name="ck_payment_logs_source",
        ),
        Index("idx_payment_logs_payment_order_id", "payment_order_id"),
        Index("idx_payment_logs_webhook_receipt_id", "webhook_receipt_id"),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    payment_order_id: uuid.UUID = Field(sa_column=_uuid_fk_column("payment_orders.id"))
    webhook_receipt_id: uuid.UUID | None = Field(
        default=None,
        sa_column=_uuid_fk_column("payment_webhook_receipts.id", nullable=True),
    )
    source: PaymentLogSource = Field(sa_column=Column(String(20), nullable=False))
    event_type: str = Field(sa_column=Column(String(40), nullable=False))
    from_status: str | None = Field(default=None, sa_column=Column(String(24), nullable=True))
    to_status: str | None = Field(default=None, sa_column=Column(String(24), nullable=True))
    provider_status: str | None = Field(
        default=None,
        sa_column=Column(String(40), nullable=True),
    )
    failure_code: str | None = Field(default=None, sa_column=Column(String(80), nullable=True))
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
