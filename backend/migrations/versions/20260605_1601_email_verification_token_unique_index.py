"""email verification token unique index

Revision ID: 6d33b06659a8
Revises: 5dc1f89ada58
Create Date: 2026-06-05 16:01:43.570367+00:00

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6d33b06659a8'
down_revision: str | Sequence[str] | None = '5dc1f89ada58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # M1 E2: 토큰 해시 직접 조회 인덱스 + 중복 방지(결정적 해시 + 고엔트로피 랜덤)
    op.create_index(
        'uq_email_verifications_token',
        'email_verifications',
        ['token'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'uq_email_verifications_token',
        table_name='email_verifications',
    )
