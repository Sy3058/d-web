"""작품/에피소드 요청·응답 스키마 (M1.5 그룹 A).

table 모델(models/work.py)과 분리한 순수 DTO. 요청은 입력 검증, 응답은 ORM→직렬화.
표지/에피소드 이미지 업로드(멀티파트)는 그룹 D 소관 - 여기선 R2 키 문자열만 다룬다.
태그 중첩·에피소드 요약이 붙는 목록 응답(selectinload)은 그룹 C에서 확장한다.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.work import WorkStatus

TITLE_MAX = 200
TAG_NAME_MAX = 50


def _validate_tag_names(names: list[str]) -> list[str]:
    for name in names:
        if not 1 <= len(name) <= TAG_NAME_MAX:
            raise ValueError(f"태그 이름은 1~{TAG_NAME_MAX}자여야 합니다")
    return names


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


# ── 작품 ──────────────────────────────────────────────────────────────────────


class WorkCreate(BaseModel):
    # author_id는 요청에 없다 - 서버가 요청 관리자 user.id로 세팅(C1, 클라 입력 무시).
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    synopsis: str | None = None
    cover_image: str | None = None  # R2 key
    episode_base_price: int = Field(default=500, ge=0)
    bundle_discount_rate: Decimal = Field(default=Decimal("0.1"), ge=0, le=1)
    status: WorkStatus = WorkStatus.ONGOING
    tag_names: list[str] = Field(default_factory=list)

    _check_tags = field_validator("tag_names")(_validate_tag_names)


class WorkUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    synopsis: str | None = None
    cover_image: str | None = None
    episode_base_price: int | None = Field(default=None, ge=0)
    bundle_discount_rate: Decimal | None = Field(default=None, ge=0, le=1)
    status: WorkStatus | None = None
    tag_names: list[str] | None = None

    @field_validator("tag_names")
    @classmethod
    def _check_tags(cls, v: list[str] | None) -> list[str] | None:
        return v if v is None else _validate_tag_names(v)


class WorkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    title: str
    synopsis: str | None
    cover_image: str | None
    episode_base_price: int
    bundle_discount_rate: Decimal
    status: WorkStatus
    created_at: datetime
    updated_at: datetime


# ── 에피소드 ──────────────────────────────────────────────────────────────────


class EpisodeCreate(BaseModel):
    # image_keys(페이지 이미지)는 그룹 D 멀티파트 업로드 소관 - 요청 바디에 없다.
    episode_no: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)
    is_free: bool = False
    thumbnail: str | None = None  # R2 key


class EpisodeUpdate(BaseModel):
    episode_no: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)
    is_free: bool | None = None
    thumbnail: str | None = None
    published_at: datetime | None = None


class EpisodeRead(BaseModel):
    """관리자(owner) 응답 전용. image_keys(R2 키)를 노출하므로 독자용으로 재사용 금지 -
    독자 뷰어 응답은 M2에서 image_keys를 제외한 별도 DTO(Signed URL만)로 만든다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
    episode_no: int
    title: str
    thumbnail: str | None
    price: int | None
    is_free: bool
    image_keys: list[str]
    is_published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
