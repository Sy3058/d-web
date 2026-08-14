"""viewer_progress_block_offset

Revision ID: b8d1f4e9a2c7
Revises: 79990ba55b63
Create Date: 2026-08-14 21:00:00+09:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d1f4e9a2c7"
down_revision: str | Sequence[str] | None = "79990ba55b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행과 구버전 클라이언트는 블록 시작점(0)으로 안전하게 해석한다.
    op.add_column(
        "viewer_progress",
        sa.Column("block_offset_bp", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_viewer_progress_block_offset_bp",
        "viewer_progress",
        "block_offset_bp >= 0 AND block_offset_bp <= 10000",
    )


def downgrade() -> None:
    op.drop_constraint("ck_viewer_progress_block_offset_bp", "viewer_progress", type_="check")
    op.drop_column("viewer_progress", "block_offset_bp")
