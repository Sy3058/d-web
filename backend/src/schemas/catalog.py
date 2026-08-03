"""공개 카탈로그 응답 스키마 (M2 그룹 A).

독자용 전용 DTO. schemas/work.py의 AdminEpisodeRead는 image_keys·content(원고 실물)를
그대로 노출하므로 여기서 재사용하지 않는다 - 비관리자에게 원고 키가 새는 통로가 된다.

썸네일 URL(M2 D2): episodes.thumbnail은 dweb(비공개 원고 버킷)의 페이지 키를 그대로
참조하므로(models/work.py) 그 키를 직접 공개 URL로 조립하지 않는다 - 대신 회차 저장
시점에 파생한 공개 축소본(dweb-cover의 결정적 키)을 가리킨다(episode_service.
update_episode). 썸네일 미선택 회차는 작품 표지로 대체, 표지도 없으면 None(FE placeholder).
"""

import uuid

from pydantic import BaseModel

from src.models.work import WorkStatus
from src.schemas.work import TagRead

# 이 모듈의 DTO는 전부 서비스가 명시적 kwargs로 조립한다(계산 필드가 섞여 있어
# model_validate(ORM) 자동 매핑 대상이 아님 - from_attributes를 켜지 않는 이유).
# 중첩 tags의 ORM->TagRead 변환은 TagRead 자신의 from_attributes가 담당한다.


class WorkListItem(BaseModel):
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
    id: uuid.UUID
    public_id: int
    title: str
    subtitle: str | None
    # 회차 공개 축소본 또는 작품 표지 fallback - 모듈 docstring 참조.
    thumbnail_url: str | None
    is_free: bool
    # 유료 구간 존재 여부(= not is_free). 배지 표시용.
    is_locked: bool
    # M2는 결제가 없어 항상 false(M3에서 실제 구매 여부로 대체).
    is_purchased: bool
    # 실효 판매가(#83): episodes.price ?? works.episode_base_price를 서버가 계산해
    # 내보낸다 - fallback 규칙을 클라이언트가 알 필요 없게. 무료 회차는 None
    # (0원 판매와 혼동 방지 + is_free를 무시한 가격 표기 방지).
    price: int | None


class PublicTag(BaseModel):
    id: uuid.UUID
    name: str
    # 이 태그가 달린 공개(public_work_filters) 작품 수. 필터 UI의 "판타지 (3)" 표기용.
    work_count: int


class WorkDetail(BaseModel):
    id: uuid.UUID
    title: str
    synopsis: str | None
    cover_image_url: str | None
    episode_base_price: int
    # bundle_discount_rate(묶음 할인율)는 M3 묶음 구매 구현 시 노출한다 - M2엔 소비자가 없어 제외.
    status: WorkStatus
    tags: list[TagRead]
    episodes: list[EpisodeSummary]
