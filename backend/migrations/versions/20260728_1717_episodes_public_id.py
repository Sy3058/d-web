"""episodes_public_id

Revision ID: f3a43b32fcfb
Revises: c3f0a1d4b25e
Create Date: 2026-07-28 17:17:01.176316+00:00

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a43b32fcfb'
down_revision: Union[str, Sequence[str], None] = 'c3f0a1d4b25e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUBLIC_ID_MIN = 10_000_000
_PUBLIC_ID_MAX = 99_999_999


def upgrade() -> None:
    # 회차 번호 폐기 → 독자 URL 조회키를 랜덤 8자리 정수(전역 유일)로 교체
    # (DECISIONS "회차 번호 폐기" 2026-07-28). 백필은 SQL 한 문장으로 못 하는데,
    # 랜덤값 충돌 회피가 필요해서(같은 트랜잭션 안 아직 UNIQUE 제약이 없어 파이썬 쪽
    # in-memory set만이 유일한 방어선 - 이 시점 이후엔 UNIQUE가 최종 백스톱을 이어받는다).
    op.add_column('episodes', sa.Column('public_id', sa.Integer(), nullable=True))

    conn = op.get_bind()
    episode_ids = [row[0] for row in conn.execute(sa.text('SELECT id FROM episodes')).fetchall()]

    used: set[int] = set()
    for episode_id in episode_ids:
        candidate = secrets.randbelow(_PUBLIC_ID_MAX - _PUBLIC_ID_MIN + 1) + _PUBLIC_ID_MIN
        while candidate in used:
            candidate = secrets.randbelow(_PUBLIC_ID_MAX - _PUBLIC_ID_MIN + 1) + _PUBLIC_ID_MIN
        used.add(candidate)
        conn.execute(
            sa.text('UPDATE episodes SET public_id = :public_id WHERE id = :id'),
            {'public_id': candidate, 'id': episode_id},
        )

    op.alter_column('episodes', 'public_id', nullable=False)
    op.create_unique_constraint('uq_episodes_public_id', 'episodes', ['public_id'])
    op.drop_constraint('uq_episodes_work_id_episode_no', 'episodes', type_='unique')
    op.drop_column('episodes', 'episode_no')


def downgrade() -> None:
    # ⚠️ 원래 episode_no 값을 복원하지 않는다(불가능 - 폐기 시점에 유실됨). 대신
    # created_at 순으로 작품별 1부터 다시 채번해 예전 스키마 형태로만 되돌린다
    # (soft delete로 소진됐던 번호·결번은 재현되지 않음 - downgrade는 "유효한
    # 스키마 재구성"이 목적이지 이력 복원이 아니다).
    op.add_column('episodes', sa.Column('episode_no', sa.Integer(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE episodes e
            SET episode_no = sub.rn
            FROM (
                SELECT id, row_number() OVER (PARTITION BY work_id ORDER BY created_at, id) AS rn
                FROM episodes
            ) sub
            WHERE e.id = sub.id
            """
        )
    )

    op.alter_column('episodes', 'episode_no', nullable=False)
    op.create_unique_constraint('uq_episodes_work_id_episode_no', 'episodes', ['work_id', 'episode_no'])
    op.drop_constraint('uq_episodes_public_id', 'episodes', type_='unique')
    op.drop_column('episodes', 'public_id')
