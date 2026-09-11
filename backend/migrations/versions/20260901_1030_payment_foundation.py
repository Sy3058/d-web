"""payment foundation

Revision ID: d0c3a4b5e6f7
Revises: b8d1f4e9a2c7
Create Date: 2026-09-01 10:30:00+09:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d0c3a4b5e6f7"
down_revision: str | Sequence[str] | None = "b8d1f4e9a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_orders",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payment_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("episode_id", sa.UUID(), nullable=True),
        sa.Column("expected_amount", sa.Integer(), nullable=False),
        sa.Column("provider_total_amount", sa.Integer(), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'KRW'"),
            nullable=False,
        ),
        sa.Column("store_id", sa.String(length=255), nullable=False),
        sa.Column("requested_channel_key", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("order_name", sa.String(length=255), nullable=False),
        sa.Column("item_title", sa.String(length=200), nullable=False),
        sa.Column("checkout_notice_version", sa.String(length=32), nullable=True),
        sa.Column("immediate_supply_consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("donation_message", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider_status", sa.String(length=40), nullable=True),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("cancellation_id", sa.String(length=255), nullable=True),
        sa.Column("pg_provider", sa.String(length=40), nullable=True),
        sa.Column("payment_method", sa.String(length=40), nullable=True),
        sa.Column("easy_pay_provider", sa.String(length=40), nullable=True),
        sa.Column("receipt_url", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=40), nullable=True),
        sa.Column("cancel_idempotency_key", sa.String(length=256), nullable=True),
        sa.Column(
            "cancel_request_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("cancelled_amount", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reconcile_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_action_reason", sa.String(length=80), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cancel_idempotency_key IS NULL OR "
            "(char_length(cancel_idempotency_key) BETWEEN 16 AND 256 "
            "AND octet_length(cancel_idempotency_key) = char_length(cancel_idempotency_key) "
            "AND cancel_idempotency_key ~ '^[ -~]+$')",
            name="ck_payment_orders_cancel_idempotency_key",
        ),
        sa.CheckConstraint(
            "(cancel_reason IS NULL AND cancel_idempotency_key IS NULL "
            "AND cancel_request_snapshot IS NULL) OR "
            "(cancel_reason IS NOT NULL AND cancel_idempotency_key IS NOT NULL "
            "AND cancel_request_snapshot IS NOT NULL "
            "AND provider_total_amount IS NOT NULL)",
            name="ck_payment_orders_cancel_request_bundle",
        ),
        sa.CheckConstraint(
            "status <> 'cancel_pending' OR cancel_reason IS NOT NULL",
            name="ck_payment_orders_cancel_pending_bundle",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN "
            "('system_verification', 'system_unavailable', 'system_duplicate', "
            "'customer_refund')",
            name="ck_payment_orders_cancel_reason",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "cancelled_amount IS NULL OR "
            "(provider_total_amount IS NOT NULL AND cancelled_amount > 0 "
            "AND cancelled_amount <= provider_total_amount)",
            name="ck_payment_orders_cancelled_amount",
        ),
        sa.CheckConstraint("currency = 'KRW'", name="ck_payment_orders_currency"),
        sa.CheckConstraint(
            "environment IN ('test', 'live')",
            name="ck_payment_orders_environment",
        ),
        sa.CheckConstraint(
            "expected_amount > 0",
            name="ck_payment_orders_expected_amount",
        ),
        sa.CheckConstraint(
            "provider_total_amount IS NULL OR provider_total_amount > 0",
            name="ck_payment_orders_provider_total_amount",
        ),
        sa.CheckConstraint(
            "kind IN ('episode_purchase', 'donation')",
            name="ck_payment_orders_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'episode_purchase' AND episode_id IS NOT NULL "
            "AND donation_message IS NULL) OR "
            "(kind = 'donation')",
            name="ck_payment_orders_kind_target",
        ),
        sa.CheckConstraint(
            "(kind = 'episode_purchase' AND checkout_notice_version IS NOT NULL "
            "AND immediate_supply_consented_at IS NOT NULL) OR "
            "(kind = 'donation' AND checkout_notice_version IS NULL "
            "AND immediate_supply_consented_at IS NULL)",
            name="ck_payment_orders_purchase_consent",
        ),
        sa.CheckConstraint(
            "reconcile_attempts >= 0",
            name="ck_payment_orders_reconcile_attempts",
        ),
        sa.CheckConstraint(
            "status IN ('preparing', 'ready', 'expired', 'paid', 'cancel_pending', "
            "'cancelled', 'review_required')",
            name="ck_payment_orders_status",
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
        sa.UniqueConstraint(
            "id",
            "user_id",
            "kind",
            "episode_id",
            "environment",
            "expected_amount",
            "paid_at",
            name="uq_payment_orders_purchase_provenance",
        ),
    )
    op.create_index(
        "idx_payment_orders_episode_id",
        "payment_orders",
        ["episode_id"],
        unique=False,
    )
    op.create_index(
        "idx_payment_orders_reconcile",
        "payment_orders",
        ["environment", "status", "next_reconcile_at"],
        unique=False,
    )
    op.create_index(
        "idx_payment_orders_user_environment_created_at",
        "payment_orders",
        ["user_id", "environment", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_payment_orders_open_episode_intent",
        "payment_orders",
        ["user_id", "episode_id", "environment"],
        unique=True,
        postgresql_where=sa.text("kind = 'episode_purchase' AND status IN ('preparing', 'ready')"),
    )

    op.create_table(
        "purchases",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payment_order_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "payment_order_kind",
            sa.String(length=24),
            server_default=sa.text("'episode_purchase'"),
            nullable=False,
        ),
        sa.Column("episode_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_amount", sa.Integer(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_purchases_amount"),
        sa.CheckConstraint(
            "environment IN ('test', 'live')",
            name="ck_purchases_environment",
        ),
        sa.CheckConstraint(
            "payment_order_kind = 'episode_purchase'",
            name="ck_purchases_payment_order_kind",
        ),
        sa.CheckConstraint(
            "refund_amount IS NULL OR (refund_amount > 0 AND refund_amount <= amount)",
            name="ck_purchases_refund_amount",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'refund_pending', 'refunded', 'review_required')",
            name="ck_purchases_status",
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_order_id"),
    )
    op.create_index("idx_purchases_user_id", "purchases", ["user_id"], unique=False)
    op.create_index("idx_purchases_episode_id", "purchases", ["episode_id"], unique=False)
    op.create_index(
        "uq_purchases_entitlement",
        "purchases",
        ["user_id", "episode_id", "environment"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'refund_pending', 'review_required')"),
    )

    op.create_table(
        "payment_webhook_receipts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("webhook_id", sa.String(length=255), nullable=False),
        sa.Column("payment_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ignored_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_payment_webhook_receipts_attempts"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("webhook_id"),
    )
    op.create_index(
        "idx_payment_webhook_receipts_payment_id",
        "payment_webhook_receipts",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        "idx_payment_webhook_receipts_pending",
        "payment_webhook_receipts",
        ["next_attempt_at", "received_at"],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL AND ignored_at IS NULL"),
    )

    op.create_table(
        "payment_logs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("payment_order_id", sa.UUID(), nullable=False),
        sa.Column("webhook_receipt_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("provider_status", sa.String(length=40), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('browser', 'webhook', 'reconcile', 'admin')",
            name="ck_payment_logs_source",
        ),
        sa.ForeignKeyConstraint(
            ["payment_order_id"],
            ["payment_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_receipt_id"],
            ["payment_webhook_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_payment_logs_payment_order_id",
        "payment_logs",
        ["payment_order_id"],
        unique=False,
    )
    op.create_index(
        "idx_payment_logs_webhook_receipt_id",
        "payment_logs",
        ["webhook_receipt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_payment_logs_webhook_receipt_id", table_name="payment_logs")
    op.drop_index("idx_payment_logs_payment_order_id", table_name="payment_logs")
    op.drop_table("payment_logs")

    op.drop_index(
        "idx_payment_webhook_receipts_pending",
        table_name="payment_webhook_receipts",
        postgresql_where=sa.text("processed_at IS NULL AND ignored_at IS NULL"),
    )
    op.drop_index(
        "idx_payment_webhook_receipts_payment_id",
        table_name="payment_webhook_receipts",
    )
    op.drop_table("payment_webhook_receipts")

    op.drop_index(
        "uq_purchases_entitlement",
        table_name="purchases",
        postgresql_where=sa.text("status IN ('active', 'refund_pending', 'review_required')"),
    )
    op.drop_index("idx_purchases_episode_id", table_name="purchases")
    op.drop_index("idx_purchases_user_id", table_name="purchases")
    op.drop_table("purchases")

    op.drop_index(
        "uq_payment_orders_open_episode_intent",
        table_name="payment_orders",
        postgresql_where=sa.text("kind = 'episode_purchase' AND status IN ('preparing', 'ready')"),
    )
    op.drop_index(
        "idx_payment_orders_user_environment_created_at",
        table_name="payment_orders",
    )
    op.drop_index("idx_payment_orders_reconcile", table_name="payment_orders")
    op.drop_index("idx_payment_orders_episode_id", table_name="payment_orders")
    op.drop_table("payment_orders")
