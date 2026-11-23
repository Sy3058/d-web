"""add signup verification code challenge and attempts"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a3b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signup_email_verifications",
        sa.Column(
            "challenge_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "signup_email_verifications",
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        "ck_signup_email_verifications_attempts",
        "signup_email_verifications",
        "attempts >= 0 AND attempts <= 5",
    )
    op.create_index(
        "uq_signup_email_verifications_challenge_id",
        "signup_email_verifications",
        ["challenge_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_signup_email_verifications_challenge_id",
        table_name="signup_email_verifications",
    )
    op.drop_constraint(
        "ck_signup_email_verifications_attempts",
        "signup_email_verifications",
        type_="check",
    )
    op.drop_column("signup_email_verifications", "attempts")
    op.drop_column("signup_email_verifications", "challenge_id")
