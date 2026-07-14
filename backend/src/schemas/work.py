"""작품/에피소드 요청·응답 스키마 (M1.5 그룹 A).

table 모델(models/work.py)과 분리한 순수 DTO. 요청은 입력 검증, 응답은 ORM→직렬화.
표지/에피소드 이미지 업로드(멀티파트)는 그룹 D 소관 - 여기선 R2 키 문자열만 다룬다.
태그 중첩·에피소드 요약이 붙는 목록 응답(selectinload)은 그룹 C에서 확장한다.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.models.work import WorkStatus

TITLE_MAX = 200
TAG_NAME_MAX = 50


def _validate_tag_names(names: list[str]) -> list[str]:
    # strip 후 검증 + 순서 유지 중복 제거(같은 이름 두 번 보내도 get-or-create가 한 번만 연결).
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        name = raw.strip()
        if not 1 <= len(name) <= TAG_NAME_MAX:
            raise ValueError(f"태그 이름은 1~{TAG_NAME_MAX}자여야 합니다")
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


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
    """부분 수정. 필드 생략 = 미변경(exclude_unset). None 허용은 컬럼 nullability를 따른다."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    synopsis: str | None = None
    cover_image: str | None = None
    episode_base_price: int | None = Field(default=None, ge=0)
    bundle_discount_rate: Decimal | None = Field(default=None, ge=0, le=1)
    status: WorkStatus | None = None
    tag_names: list[str] | None = None

    # DB에서 NOT NULL인 필드들. `X | None`의 None은 "생략(미변경)"을 표현하기 위한 것이지
    # null 대입 허용이 아니다 - 명시적 null은 여기서 422로 거부한다(안 막으면 exclude_unset
    # dump에 None이 살아남아 NOT NULL 컬럼 UPDATE에서 500 - 2026-07-09 리뷰).
    _NON_NULLABLE = frozenset({"title", "episode_base_price", "bundle_discount_rate", "status"})

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "WorkUpdate":
        for name in self.model_fields_set & self._NON_NULLABLE:
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 지정할 수 없습니다 (생략 = 미변경)")
        return self

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
    # models/work.py Work.tags Relationship 직렬화. service가 selectinload(Work.tags)로
    # 미리 로드해둬야 함 - 여기서 접근 시 lazy load 트리거되면 비동기 세션 에러(N+1 규칙).
    tags: list[TagRead]
    # Work.episode_count(column_property - 상관 서브쿼리). Work를 SELECT하면 함께 실려 오지만,
    # 갓 INSERT한 인스턴스에는 없어 create 경로가 refresh로 채운다(models/work.py 주석).
    episode_count: int
    created_at: datetime
    updated_at: datetime


# ── 에피소드 ──────────────────────────────────────────────────────────────────


class EpisodeCreate(BaseModel):
    """draft 생성(is_published=false). 이미지는 별도 단건 업로드(D3 구조 A) - 바디에 없다.

    thumbnail도 없다 - 생성 시점엔 검증할 image_keys가 없어 임의 키 주입 통로가 된다.
    업로드 후 PUT으로 선택한다. published_at은 예약 공개 시각 - **과거 시각도 허용**되며
    "스케줄러 다음 틱에 공개"를 뜻한다(E1 계약 선확정). AwareDatetime이라 오프셋 없는
    naive 시각은 422 - KST 로컬 시각이 UTC로 오해석돼 9시간 밀리는 조용한 오동작 차단.
    """

    episode_no: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)  # NULL = works.episode_base_price 참조
    is_free: bool = False
    published_at: AwareDatetime | None = None


class EpisodeUpdate(BaseModel):
    """부분 수정. 생략 = 미변경, 명시적 null은 nullable 컬럼(price·thumbnail·published_at)만.

    - image_keys: 페이지 재배열/삭제. 기존 키의 중복 없는 부분집합만(service 검증 -
      임의 키 주입 금지). 배열 순서 = 표시 순서(키 파일명은 uuid, 순서 의미 없음).
    - thumbnail: 회차 대표 컷. 이 회차 image_keys 중 하나여야 하며(작가가 표지 일러스트
      페이지를 직접 선택 - 첫 페이지가 표지가 아닌 웹툰 관행), null = 해제.
    - is_published=true: 즉시 공개 - published_at이 없으면(NULL·미래) 서버가 now로 스탬프,
      최소 1페이지 필요. false 전환 시 published_at은 **페이로드와 무관하게 항상 NULL
      초기화**(E1 부활 차단 - stale 에코 방어. 재예약은 is_published 없이 published_at만
      별도 요청). published_at 과거값 = 다음 틱 공개(E1). naive 시각은 422(AwareDatetime).
    """

    episode_no: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)
    is_free: bool | None = None
    is_published: bool | None = None
    thumbnail: str | None = None
    published_at: AwareDatetime | None = None
    image_keys: list[str] | None = None

    # WorkUpdate와 같은 규칙: `X | None`의 None은 "생략" 표현이지 null 대입 허용이 아니다.
    _NON_NULLABLE = frozenset({"episode_no", "title", "is_free", "is_published", "image_keys"})

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "EpisodeUpdate":
        for name in self.model_fields_set & self._NON_NULLABLE:
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 지정할 수 없습니다 (생략 = 미변경)")
        return self


class AdminEpisodeRead(BaseModel):
    """관리자(owner) 응답 **전용** - 이름부터 Admin: image_keys(R2 키)를 노출하므로
    독자용 라우터(M2)가 무심코 재사용하면 미결제 유저에게 키가 새는 경로가 된다.
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
