"""커미션 카드·사이트 문구 스키마 (M2 그룹 G).

admin DTO와 공개 DTO를 한 파일에 둔다(카탈로그처럼 나눌 규모가 아님). 공개 DTO는
sample_image_urls(공개 URL 배열)만 내보내고 key 문자열은 싣지 않는다 - 공개 버킷이라
보안 목적이 아니라 "독자 응답에 R2 키 부재"(B2 계약)와의 일관성 목적.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from src.models.commission import SiteTextKey
from src.services import r2_service

TITLE_MAX = 200
SHORT_TEXT_MAX = 100
# 플레인 텍스트 상한(Text 컬럼 무한 입력 차단 - DoS 방어). 소개·유의사항 용도로 넉넉.
DESCRIPTION_MAX = 2_000
SITE_TEXT_MAX = 10_000


class CommissionItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    # 표시 전용 자유 문자열("50,000원~"·"오마카세") - models/commission.py 참조.
    price_text: str = Field(min_length=1, max_length=SHORT_TEXT_MAX)
    duration_text: str | None = Field(default=None, max_length=SHORT_TEXT_MAX)
    is_open: bool = True
    # sample_image_keys는 생성 입력에 없다 - 업로드 엔드포인트가 append하는 매니페스트라
    # 여기 열면 임의 키 주입 통로가 된다(EpisodeCreate가 thumbnail을 빼는 것과 같은 이유).


class CommissionItemUpdate(BaseModel):
    """부분 수정. 생략 = 미변경(exclude_unset). sample_image_keys는 기존 키의 중복 없는
    부분집합만(재배열·삭제 허용, 신규 주입 금지 - service 검증). 제거분은 커밋 성공 후
    공개 버킷에서 삭제된다(commission_service)."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    price_text: str | None = Field(default=None, min_length=1, max_length=SHORT_TEXT_MAX)
    duration_text: str | None = Field(default=None, max_length=SHORT_TEXT_MAX)
    is_open: bool | None = None
    sample_image_keys: list[str] | None = None

    # WorkUpdate와 같은 규칙: `X | None`의 None은 "생략" 표현이지 null 대입 허용이 아니다.
    _NON_NULLABLE = frozenset({"title", "price_text", "is_open", "sample_image_keys"})

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "CommissionItemUpdate":
        for name in self.model_fields_set & self._NON_NULLABLE:
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 지정할 수 없습니다 (생략 = 미변경)")
        return self


class CommissionItemReorder(BaseModel):
    """카드 재배열 - 카드 전량을 원하는 순서로 나열한 id 목록.

    개별 create/update에는 sort_order를 노출하지 않는다. 순서는 컬렉션 전체의 속성이며,
    전량 집합 검사가 다른 탭의 추가·삭제를 감지하는 낙관적 동시성 검사 역할을 한다.
    """

    item_ids: list[uuid.UUID] = Field(min_length=1)


class CommissionSampleImage(BaseModel):
    """샘플 1장의 키 + 공개 URL 쌍(admin 전용). EpisodeImageUrl과 같은 근거 - 재배열·삭제
    UI가 "이 이미지 = 어느 키" 매핑을 알아야 PUT(sample_image_keys)을 만들 수 있다.
    url은 공개 버킷 고정 URL(만료 없음). public_asset_base_url 미설정이면 None."""

    key: str
    url: str | None


class AdminCommissionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    price_text: str
    duration_text: str | None
    sample_image_keys: list[str]
    is_open: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    # WorkRead.cover_url과 같은 패턴 - URL 조립을 라우터에 흩뿌리지 않는다(D1 단일화).
    @computed_field  # type: ignore[prop-decorator]
    @property
    def sample_images(self) -> list[CommissionSampleImage]:
        return [
            CommissionSampleImage(key=key, url=r2_service.public_url(key))
            for key in self.sample_image_keys
        ]


class PublicCommissionItem(BaseModel):
    """독자용 카드. 서비스가 명시적 kwargs로 조립한다(schemas/catalog.py와 같은 방식).
    is_open=false여도 목록에 남는다 - 마감 배지 표시(크레페식 슬롯 상태)."""

    id: uuid.UUID
    title: str
    description: str | None
    price_text: str
    duration_text: str | None
    sample_image_urls: list[str]
    is_open: bool


class SiteTextRead(BaseModel):
    """admin·공개 공용(민감 필드 없음). updated_at이 None이면 아직 저장된 적 없는
    슬롯이다 - admin GET이 행 없음을 404 대신 빈 기본값으로 응답하는 시딩 규약."""

    model_config = ConfigDict(from_attributes=True)

    key: SiteTextKey
    body: str
    updated_at: datetime | None


class SiteTextUpdate(BaseModel):
    # 빈 문자열 허용 - 문구 비우기(FE는 빈 body를 존 접기로 처리).
    body: str = Field(max_length=SITE_TEXT_MAX)
