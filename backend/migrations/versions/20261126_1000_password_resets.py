"""add password reset tokens"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b4c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_tag", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_password_resets_user_id", "password_resets", ["user_id"])
    op.create_index("uq_password_resets_token_hash", "password_resets", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_password_resets_token_hash", table_name="password_resets")
    op.drop_index("idx_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
