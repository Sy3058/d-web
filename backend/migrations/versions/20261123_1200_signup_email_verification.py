"""add signup email verification challenge"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f2a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_email_verifications",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("proof_hash", sa.String(length=64), nullable=True),
        sa.Column("proof_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_signup_email_verifications_proof_hash",
        "signup_email_verifications",
        ["proof_hash"],
        unique=True,
    )
    op.create_index(
        "uq_signup_email_verifications_token_hash",
        "signup_email_verifications",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "uq_signup_email_verifications_email",
        "signup_email_verifications",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_signup_email_verifications_email", table_name="signup_email_verifications")
    op.drop_index(
        "uq_signup_email_verifications_token_hash",
        table_name="signup_email_verifications",
    )
    op.drop_index(
        "uq_signup_email_verifications_proof_hash",
        table_name="signup_email_verifications",
    )
    op.drop_table("signup_email_verifications")
