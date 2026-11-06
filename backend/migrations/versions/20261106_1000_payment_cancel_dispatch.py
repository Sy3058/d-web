"""payment cancellation dispatch ownership"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d0c3a4b5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_orders",
        sa.Column("cancel_key_issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payment_orders", sa.Column("cancel_dispatch_token", sa.Uuid(), nullable=True))
    op.add_column(
        "payment_orders",
        sa.Column("cancel_dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    orders = sa.table(
        "payment_orders",
        sa.column("cancel_reason", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("cancel_key_issued_at", sa.DateTime(timezone=True)),
    )
    # 과거 키의 재생 허용 시간을 migration 시점부터 연장하지 않는다.
    op.execute(
        orders.update()
        .where(orders.c.cancel_reason.is_not(None))
        .values(cancel_key_issued_at=orders.c.created_at)
    )
    op.drop_constraint("ck_payment_orders_cancel_request_bundle", "payment_orders", type_="check")
    op.create_check_constraint(
        "ck_payment_orders_cancel_request_bundle",
        "payment_orders",
        "(cancel_reason IS NULL AND cancel_idempotency_key IS NULL AND "
        "cancel_request_snapshot IS NULL AND cancel_key_issued_at IS NULL) OR "
        "(cancel_reason IS NOT NULL AND cancel_idempotency_key IS NOT NULL AND "
        "cancel_request_snapshot IS NOT NULL AND cancel_key_issued_at IS NOT NULL AND "
        "provider_total_amount IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_payment_orders_cancel_dispatch_bundle",
        "payment_orders",
        "(cancel_dispatch_token IS NULL AND cancel_dispatch_started_at IS NULL) OR "
        "(cancel_dispatch_token IS NOT NULL AND cancel_dispatch_started_at IS NOT "
        "NULL AND cancel_reason IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_orders_cancel_dispatch_bundle", "payment_orders", type_="check")
    op.drop_constraint("ck_payment_orders_cancel_request_bundle", "payment_orders", type_="check")
    op.create_check_constraint(
        "ck_payment_orders_cancel_request_bundle",
        "payment_orders",
        "(cancel_reason IS NULL AND cancel_idempotency_key IS NULL AND "
        "cancel_request_snapshot IS NULL) OR (cancel_reason IS NOT NULL AND "
        "cancel_idempotency_key IS NOT NULL AND cancel_request_snapshot IS NOT NULL "
        "AND provider_total_amount IS NOT NULL)",
    )
    op.drop_column("payment_orders", "cancel_dispatch_started_at")
    op.drop_column("payment_orders", "cancel_dispatch_token")
    op.drop_column("payment_orders", "cancel_key_issued_at")
