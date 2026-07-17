"""공개 카탈로그 응답 스키마 (M2 그룹 A).

독자용 전용 DTO. schemas/work.py의 AdminEpisodeRead는 image_keys·content(원고 실물)를
그대로 노출하므로 여기서 재사용하지 않는다 - 비관리자에게 원고 키가 새는 통로가 된다.

썸네일 URL은 이 그룹에서는 항상 None이다: 현재 episodes.thumbnail은 dweb(비공개 원고
버킷)의 페이지 키를 그대로 참조하고 있어(models/work.py), 공개 URL로 조립하면 유료
회차의 원고 실물이 노출된다. 공개 축소본(dweb-cover)을 만들어 그 키로 대체하는 작업은
M2 그룹 D2 - 그 전까지는 값을 채우지 않는다(FE는 placeholder 처리).
"""

import uuid

from pydantic import BaseModel, ConfigDict

from src.models.work import WorkStatus
from src.schemas.work import TagRead


class WorkListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    cover_image_url: str | None
    status: WorkStatus
    tags: list[TagRead]
    # 공개(is_published) 회차만 센 개수. models.work.Work.episode_count(전체 카운트)와는
    # 다른 값이고, 전체 카운트를 그대로 쓰면 미공개 회차 수가 노출되므로 재사용하지 않는다.
    episode_count: int


class WorkListResponse(BaseModel):
    items: list[WorkListItem]
    total: int
    page: int
    size: int


class EpisodeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    episode_no: int
    title: str
    subtitle: str | None
    # D2(공개 축소본) 이전까지 항상 None - 모듈 docstring 참조.
    thumbnail_url: str | None
    is_free: bool
    # 유료 구간 존재 여부(= not is_free). 배지 표시용.
    is_locked: bool
    # M2는 결제가 없어 항상 false(M3에서 실제 구매 여부로 대체).
    is_purchased: bool


class WorkDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    synopsis: str | None
    cover_image_url: str | None
    episode_base_price: int
    # bundle_discount_rate(묶음 할인율)는 M3 묶음 구매 구현 시 노출한다 - M2엔 소비자가 없어 제외.
    status: WorkStatus
    tags: list[TagRead]
    episodes: list[EpisodeSummary]
