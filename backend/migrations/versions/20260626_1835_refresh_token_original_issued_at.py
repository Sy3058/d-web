"""refresh token original issued at

Revision ID: 5a55bab9de3d
Revises: fefbcb3265c0
Create Date: 2026-06-26 18:35:18.056990+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a55bab9de3d'
down_revision: Union[str, Sequence[str], None] = 'fefbcb3265c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # M1 A: refresh 토큰 절대 수명 cap의 기준점. 토큰 체인의 최초 발급 시각(회전돼도 불변).
    # 기존 행은 최초 발급 시각을 알 수 없어 created_at으로 근사한다(forward-only).
    # add nullable -> backfill -> NOT NULL 3단계로 기존 행 NOT NULL 위반을 피한다.
    op.add_column(
        "refresh_tokens",
        sa.Column("original_issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE refresh_tokens SET original_issued_at = created_at "
        "WHERE original_issued_at IS NULL"
    )
    op.alter_column("refresh_tokens", "original_issued_at", nullable=False)


def downgrade() -> None:
    op.drop_column("refresh_tokens", "original_issued_at")
