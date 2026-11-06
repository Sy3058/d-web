"""payment requested method snapshot"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e1f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 당시 수단을 현재 channel 설정으로 추측하지 않는다. 기존 주문은 NULL을 유지한다.
    op.add_column(
        "payment_orders", sa.Column("requested_payment_method", sa.String(40), nullable=True)
    )
    op.add_column(
        "payment_orders", sa.Column("requested_easy_pay_provider", sa.String(40), nullable=True)
    )
    op.create_check_constraint(
        "ck_payment_orders_requested_method",
        "payment_orders",
        "(requested_payment_method IS NULL AND requested_easy_pay_provider IS NULL) OR "
        "(requested_payment_method IS NOT NULL AND ("
        "(requested_payment_method = 'PaymentMethodCard' "
        "AND requested_easy_pay_provider IS NULL) OR "
        "(requested_payment_method = 'PaymentMethodEasyPay' "
        "AND requested_easy_pay_provider IS NOT NULL "
        "AND requested_easy_pay_provider IN ('KAKAOPAY', 'TOSSPAY'))))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_orders_requested_method", "payment_orders", type_="check")
    op.drop_column("payment_orders", "requested_easy_pay_provider")
    op.drop_column("payment_orders", "requested_payment_method")
