"""episodes_sort_order

Revision ID: a7c91d05e3b4
Revises: f3a43b32fcfb
Create Date: 2026-07-30 11:20:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c91d05e3b4'
down_revision: Union[str, Sequence[str], None] = 'f3a43b32fcfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 회차 번호 폐기(f3a43b32fcfb)로 사라진 "작가가 정한 표시 순서"를 별도 컬럼으로
    # 되살린다. public_id를 순번 대신 랜덤으로 만든 이상 정렬 기준이 created_at밖에
    # 안 남는데, 그러면 프롤로그를 나중에 끼워넣거나 잘못 올린 순서를 되돌릴 수 없다.
    #
    # ⚠️ UNIQUE를 걸지 않는다 - 유일 제약이야말로 episode_no가 동시 생성에서 409를
    # 뱉던 원인이었고, 표시 순서는 동점이어도 (created_at, id)가 깨주므로 충돌이
    # 성립하지 않는다.
    #
    # 백필은 기존 정렬(created_at, id)과 같은 순번이라 이 마이그레이션 전후로
    # 독자에게 보이는 순서가 바뀌지 않는다. soft delete된 회차도 같이 채번하는데,
    # 되살릴 일이 생기면 원래 자리로 돌아와야 하기 때문이다.
    op.add_column('episodes', sa.Column('sort_order', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE episodes e
        SET sort_order = sub.rn
        FROM (
            SELECT id, row_number() OVER (PARTITION BY work_id ORDER BY created_at, id) AS rn
            FROM episodes
        ) sub
        WHERE e.id = sub.id
        """
    )

    op.alter_column('episodes', 'sort_order', nullable=False)


def downgrade() -> None:
    # 순서 정보는 유실된다. 되돌리면 정렬이 다시 created_at 순으로 떨어지는데,
    # 작가가 재배열을 한 적이 없다면 결과가 같고 했다면 올린 순서로 복귀한다.
    op.drop_column('episodes', 'sort_order')
