"""작품/에피소드 도메인 모델 (DB_SCHEMA §2 "작품/에피소드 도메인").

SQLModel `table=True` 모델은 DB 테이블이자 내부 타입. 외부 응답엔 schemas/work.py의
DTO를 쓴다(M1 A1 교훈 - table 모델 직접 노출 금지).

PK는 DB_SCHEMA "설계 원칙"대로 전 테이블 UUID(`gen_random_uuid()`).
`works_tags`·`episodes.work_id`는 ON DELETE CASCADE. `works.author_id`는 CASCADE 없음
(작가 계정은 soft delete가 기본이라 작품 하드 삭제가 딸려가면 안 됨).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlmodel import Field, Relationship, SQLModel


class WorkStatus(StrEnum):
    """작품 연재 상태. VARCHAR(20) 저장(네이티브 PG enum 아님) + 앱 레벨 검증.

    StrEnum(str 서브클래스)이라 컬럼(String)에 멤버 값("ongoing" 등)이 그대로 저장된다.
    후속 상태 추가는 이 enum 값만 늘리면 되고 DB 마이그레이션이 필요 없다.
    """

    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"


def _pk_column() -> Column:
    """UUID PK, DB측 gen_random_uuid() 기본값 (DB_SCHEMA 설계 원칙)."""
    return Column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _created_at_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at_column() -> Column:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkTag(SQLModel, table=True):
    __tablename__ = "works_tags"

    work_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("works.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    tag_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )


class Work(SQLModel, table=True):
    __tablename__ = "works"
    # UPDATE에도 RETURNING으로 서버 계산 컬럼(onupdate updated_at 등)을 즉시 받아온다.
    # 기본값 "auto"는 INSERT만 커버해서, UPDATE 후 만료된 updated_at을 응답 직렬화가
    # 동기 접근하다 MissingGreenlet으로 죽는 함정이 있었다(2026-07-09 리뷰 - 콜사이트별
    # session.refresh 수동 열거 대신 매퍼 정책으로 일반화).
    __mapper_args__ = {"eager_defaults": True}

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    # 1인 작가라 값은 role=owner 유저 id. 확장 대비 FK는 유지(CASCADE 없음 - soft delete 기본).
    author_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("users.id"),
            nullable=False,
        )
    )
    title: str = Field(sa_column=Column(String(200), nullable=False))
    synopsis: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # 표지 R2 키(공개 URL 아님). 업로드는 그룹 C/D, 여기선 키 문자열만 보관.
    cover_image: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    episode_base_price: int = Field(
        default=500,
        sa_column=Column(Integer, nullable=False, server_default=text("500")),
    )
    # 전편 묶음 할인율(0.1 = 10%). 컬럼은 지금, 실제 할인 로직은 M3 결제.
    bundle_discount_rate: Decimal = Field(
        default=Decimal("0.1"),
        sa_column=Column(Numeric(4, 3), nullable=False, server_default=text("0.1")),
    )
    status: WorkStatus = Field(
        default=WorkStatus.ONGOING,
        sa_column=Column(String(20), nullable=False, server_default=text("'ongoing'")),
    )
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column())
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # 그룹 C1 응답용(WorkRead.tags). works_tags 경유 다대다. 조회 시 selectinload 필수
    # (lazy load 금지 - backend/CLAUDE.md N+1 규칙).
    tags: list["Tag"] = Relationship(link_model=WorkTag)


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    # UNIQUE가 곧 name 조회용 인덱스(WHERE name=?) 겸용이라 별도 idx_tags_name은 두지 않는다
    # (같은 컬럼 중복 인덱스). get-or-create(C1)의 충돌 방어선도 이 UNIQUE가 담당.
    name: str = Field(sa_column=Column(String(50), nullable=False, unique=True))
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())


class Episode(SQLModel, table=True):
    __tablename__ = "episodes"
    # Work와 동일 - updated_at onupdate 컬럼이 있어 update 경로(D3)에서 같은 함정 방지.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        # 한 작품 안에서 회차 번호 유일 (DB_SCHEMA §2)
        UniqueConstraint("work_id", "episode_no", name="uq_episodes_work_id_episode_no"),
        # work_id별 에피소드 조회 (FK엔 인덱스 자동생성 안 됨 - DB_SCHEMA §6)
        Index("idx_episodes_work_id", "work_id"),
        # 공개된 에피소드의 published_at 정렬/범위 조회 (partial)
        Index(
            "idx_episodes_published_at",
            "published_at",
            postgresql_where=text("is_published = true"),
        ),
        # work_id별 공개 에피소드만 조회 (idx_episodes_work_id와 별개 partial)
        Index(
            "idx_episodes_published",
            "work_id",
            postgresql_where=text("is_published = true"),
        ),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    work_id: uuid.UUID = Field(
        sa_column=Column(
            PgUUID(as_uuid=True),
            ForeignKey("works.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    episode_no: int = Field(sa_column=Column(Integer, nullable=False))
    title: str = Field(sa_column=Column(String(200), nullable=False))
    # 썸네일 R2 키 (공개 URL 아님)
    thumbnail: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # NULL이면 런타임에 works.episode_base_price 참조 (금액 하드코딩 금지 - DECISIONS)
    price: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # "무료 회차 수"의 단일 진실(별도 컬럼 없음). 관리자 UI가 앞 N화의 is_free를 토글.
    is_free: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    # 배열 인덱스 = 페이지 순서. R2 키 저장(공개 URL 아님). 업로드는 그룹 D.
    image_keys: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    is_published: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    # 예약 공개 시각(스케줄러가 도달 시 is_published 전환 - 그룹 E)
    published_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=_updated_at_column())
