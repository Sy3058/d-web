"""작품/에피소드 요청·응답 스키마 (M1.5 그룹 A).

table 모델(models/work.py)과 분리한 순수 DTO. 요청은 입력 검증, 응답은 ORM→직렬화.
표지/에피소드 이미지 업로드(멀티파트)는 그룹 D 소관 - 여기선 R2 키 문자열만 다룬다.
태그 중첩·에피소드 요약이 붙는 목록 응답(selectinload)은 그룹 C에서 확장한다.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

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
    """draft 생성(is_published=false). 이미지·본문은 이후 요청(D3 구조 A + F3 에디터 PUT).

    F3 재설계(2026-07-15): 에디터가 "캔버스 먼저, 메타는 발행 모달" 흐름이라
    episode_no 생략 = 서버가 해당 작품 max+1 자동 할당, title 생략 = "무제".
    is_free는 입력에서 제거 - content의 유료 경계에서 서버가 파생하는 컬럼이 됐다.

    thumbnail이 없는 이유는 기존과 동일 - 생성 시점엔 검증할 image_keys가 없어
    임의 키 주입 통로가 된다. published_at은 예약 공개 시각 - **과거 시각도 허용**
    (스케줄러 다음 틱 공개). AwareDatetime이라 naive 시각은 422(KST가 UTC로
    오해석돼 9시간 밀리는 조용한 오동작 차단).
    """

    episode_no: int | None = Field(default=None, ge=1)  # None = 서버가 max+1 할당
    title: str = Field(default="무제", min_length=1, max_length=TITLE_MAX)
    subtitle: str | None = Field(default=None, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)  # NULL = works.episode_base_price 참조
    published_at: AwareDatetime | None = None


class EpisodeUpdate(BaseModel):
    """부분 수정. 생략 = 미변경, 명시적 null은 nullable 컬럼(subtitle·price·thumbnail·
    published_at)만.

    - content: 본문(TipTap JSON - lib/content_doc 화이트리스트·상한·이미지 키 소유 검증).
      유료 경계(paywall 노드) 위치가 곧 무료/유료 분량이고 is_free는 서버가 파생한다
      (직접 입력 폐지 - F3 재설계 2026-07-15).
    - image_keys: 업로드 매니페스트 정리(삭제). 기존 키의 중복 없는 부분집합만(service
      검증 - 임의 키 주입 금지). 표시 순서의 진실은 content로 이동했다.
    - thumbnail: 회차 대표 컷. 이 회차 image_keys 중 하나여야 하며(작가가 표지 일러스트
      페이지를 직접 선택 - 첫 페이지가 표지가 아닌 웹툰 관행), null = 해제.
    - is_published=true: 즉시 공개 - published_at이 없으면(NULL·미래) 서버가 now로 스탬프,
      본문에 유의미 내용(글/이미지) 필요. false 전환 시 published_at은 **페이로드와
      무관하게 항상 NULL 초기화**(E1 부활 차단 - stale 에코 방어. 재예약은 is_published
      없이 published_at만 별도 요청). published_at 과거값 = 다음 틱 공개(E1).
      naive 시각은 422(AwareDatetime).
    """

    episode_no: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    subtitle: str | None = Field(default=None, max_length=TITLE_MAX)
    price: int | None = Field(default=None, ge=0)
    is_published: bool | None = None
    thumbnail: str | None = None
    published_at: AwareDatetime | None = None
    image_keys: list[str] | None = None
    content: dict[str, Any] | None = None

    # WorkUpdate와 같은 규칙: `X | None`의 None은 "생략" 표현이지 null 대입 허용이 아니다.
    _NON_NULLABLE = frozenset({"episode_no", "title", "is_published", "image_keys", "content"})

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
    subtitle: str | None
    thumbnail: str | None
    price: int | None
    is_free: bool
    content: dict[str, Any]
    image_keys: list[str]
    is_published: bool
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EpisodeImageUrl(BaseModel):
    """페이지 1장의 R2 키 + presigned GET URL 쌍. 관리자 미리보기 응답 전용.

    URL만 주지 않고 키를 함께 주는 이유: 재배열·썸네일 선택 UI가 "이 이미지 = 어느
    키"의 매핑을 알아야 PUT(image_keys 부분집합·thumbnail 키)을 만들 수 있다.
    url은 PRESIGN_GET_EXPIRES 후 만료되는 일회성 값 - 저장·캐시 금지.
    """

    key: str
    url: str
