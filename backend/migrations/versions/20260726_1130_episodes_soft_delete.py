"""episodes_soft_delete

Revision ID: c3f0a1d4b25e
Revises: b97cd9397338
Create Date: 2026-07-26 11:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3f0a1d4b25e'
down_revision: Union[str, Sequence[str], None] = 'b97cd9397338'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 기존 행은 전부 NULL(= 미삭제)이라 백필 불필요. UNIQUE(work_id, episode_no)는
    # 그대로 둔다 - 삭제된 회차의 번호는 소진된다(#85 결정: 독자 URL의 회차 번호가
    # 나중에 다른 내용을 가리키면 안 됨).
    op.add_column('episodes', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('episodes', 'deleted_at')
