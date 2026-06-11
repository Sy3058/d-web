"""email_verifications user_id index

Revision ID: fefbcb3265c0
Revises: 97b9912aa03e
Create Date: 2026-06-11 11:02:45.115901+00:00

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fefbcb3265c0'
down_revision: str | Sequence[str] | None = '97b9912aa03e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # M1 I2: 재발송/무효화(E3)의 WHERE user_id=? AND used_at IS NULL 조회용.
    # Postgres는 FK에 인덱스를 자동 생성하지 않으므로 명시 (DB_SCHEMA §6).
    op.create_index(
        'idx_email_verifications_user_id',
        'email_verifications',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'idx_email_verifications_user_id',
        table_name='email_verifications',
    )
