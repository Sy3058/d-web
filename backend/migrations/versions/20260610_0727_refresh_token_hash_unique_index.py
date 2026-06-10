"""refresh token hash unique index

Revision ID: 97b9912aa03e
Revises: 6d33b06659a8
Create Date: 2026-06-10 07:27:03.801155+00:00

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '97b9912aa03e'
down_revision: str | Sequence[str] | None = '6d33b06659a8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # M1 I1: WHERE token_hash=? 직접 조회 인덱스 + 회전 불변식 방어선
    # (결정적 해시 + 고엔트로피 랜덤이라 충돌 없어 UNIQUE 가능).
    # 단일 소형 VPS라 plain CREATE UNIQUE INDEX. 대용량이면 CONCURRENTLY 고려.
    op.create_index(
        'uq_refresh_tokens_token_hash',
        'refresh_tokens',
        ['token_hash'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'uq_refresh_tokens_token_hash',
        table_name='refresh_tokens',
    )
