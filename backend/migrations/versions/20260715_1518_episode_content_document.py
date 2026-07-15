"""episode content document

Revision ID: 2a9ae60edceb
Revises: 4d1613a602e5
Create Date: 2026-07-15 15:18:18+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a9ae60edceb'
down_revision: Union[str, Sequence[str], None] = '4d1613a602e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # F3 재설계(2026-07-15): 회차 본문 = TipTap JSON 문서(episodes.content).
    # server_default가 EMPTY_DOC이라 기존 행은 일단 빈 문서로 채워진 뒤 아래에서 백필.
    op.add_column('episodes', sa.Column('subtitle', sa.String(length=200), nullable=True))
    op.add_column('episodes', sa.Column(
        'content',
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text('\'{"type": "doc", "content": []}\'::jsonb'),
        nullable=False,
    ))

    # 백필: image_keys(기존 페이지 순서의 진실)를 순서 그대로 image 노드로 나열.
    # 기존 is_free=false는 "회차 전체 유료"였으므로 paywall을 맨 앞에 둬 의미 보존
    # (미리보기 0). is_free=true는 경계 없음 = 전체 무료. 정적 SQL(입력 조합 없음).
    op.execute(
        """
        UPDATE episodes
        SET content = jsonb_build_object(
            'type', 'doc',
            'content',
            (CASE WHEN is_free THEN '[]'::jsonb ELSE '[{"type": "paywall"}]'::jsonb END)
            || (
                SELECT jsonb_agg(
                    jsonb_build_object('type', 'image', 'attrs', jsonb_build_object('key', k))
                    ORDER BY ord
                )
                FROM jsonb_array_elements_text(episodes.image_keys) WITH ORDINALITY AS t(k, ord)
            )
        )
        WHERE jsonb_array_length(image_keys) > 0
        """
    )
    # is_free는 이제 content 파생 컬럼: 빈 문서(이미지 0장 행)는 무료가 정합
    # (derive_is_free(EMPTY_DOC) = true). 유료로 남겨두면 "내용 없는 유료 회차" 모순.
    op.execute(
        "UPDATE episodes SET is_free = true"
        " WHERE jsonb_array_length(image_keys) = 0 AND is_free = false"
    )


def downgrade() -> None:
    # is_free 정규화(0장 행 false→true)는 되돌리지 않는다 - 원래 값이 남아있지 않고,
    # 구모델에서도 0장 draft의 is_free는 공개 전 임시값이라 손실 무해.
    op.drop_column('episodes', 'content')
    op.drop_column('episodes', 'subtitle')
