"""뷰어 진행도 모델 (DB_SCHEMA §2 "뷰어 진행도", M2 그룹 C1).

독자가 회차를 읽은 마지막 위치를 저장한다. page_no는 #76 콘텐츠 모델 전환
(episodes.content = TipTap JSON 문서) 이후 "문서 최상위 블록 인덱스"로
재해석된 값이다. block_offset_bp는 그 블록 내부의 상대 위치(0..10000)다.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlmodel import Field, SQLModel


class ViewerProgress(SQLModel, table=True):
    __tablename__ = "viewer_progress"
    __table_args__ = (
        # 유저당 회차 하나에 진행도 1행 (UPSERT 대상 - progress_service).
        UniqueConstraint("user_id", "episode_id", name="uq_viewer_progress_user_episode"),
        CheckConstraint(
            "block_offset_bp >= 0 AND block_offset_bp <= 10000",
            name="ck_viewer_progress_block_offset_bp",
        ),
        # 위 UNIQUE 인덱스는 (user_id, episode_id) 순이라 episode_id 단독 조회엔 안 쓰인다.
        # ON DELETE CASCADE가 부모(episodes) 삭제 시 자식 행을 찾을 때 필요 - 없으면
        # 순차 스캔이다(FK엔 인덱스 자동 생성 안 됨 - DB_SCHEMA §6, models/work.py의
        # idx_episodes_work_id와 같은 이유).
        Index("idx_viewer_progress_episode_id", "episode_id"),
    )

    id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    episode_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    page_no: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    block_offset_bp: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
