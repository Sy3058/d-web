"""episodes_first_published_at

Revision ID: 79990ba55b63
Revises: 119aecacde5e
Create Date: 2026-08-04 16:39:52.953727+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "79990ba55b63"
down_revision: str | Sequence[str] | None = "119aecacde5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 재공개 시 published_at이 튀는 문제(E3 결정)를 고치기 위해 "최초 공개 시각"을
    # 별도 컬럼으로 둔다. 백필은 지금 공개 중인 회차만 대상 - 이미 비공개인 회차는
    # published_at이 episode_service에 의해 이미 NULL로 밀려 있어(비공개 전환 시
    # 항상 초기화됨) 복구할 원본 값 자체가 없다. 그 회차들은 first_published_at이
    # NULL로 남고, 다음에 공개될 때 그 시점이 "최초"로 스탬프된다(가짜 날짜 조작 대신
    # 정직한 NULL - 2026-08-05 dev DB 실측: 이런 행 1건, published_at 이미 NULL 확인).
    op.add_column(
        "episodes", sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.execute(
        """
        UPDATE episodes
        SET first_published_at = published_at
        WHERE is_published = true AND published_at IS NOT NULL
        """
    )

    # 소비처 0인 죽은 인덱스 제거(E3 council 검증) - partial 조건(is_published=true)이라
    # 스케줄러(is_published=false 검색)는 애초에 못 타고, 독자 목록 조회는 sort_order로만
    # 정렬해(episode_service.list_episodes, catalog_service.get_work_detail) published_at
    # 정렬/범위 쿼리 자체가 없다.
    op.drop_index("idx_episodes_published_at", table_name="episodes")


def downgrade() -> None:
    op.create_index(
        "idx_episodes_published_at",
        "episodes",
        ["published_at"],
        postgresql_where=sa.text("is_published = true"),
    )
    op.drop_column("episodes", "first_published_at")
