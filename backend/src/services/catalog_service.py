"""공개 카탈로그 조회 서비스 (M2 그룹 A).

router는 HTTP 매핑만, 여기서 필터·집계·DTO 조립까지 담당한다. admin work_service와
조회 조건(공개+미삭제만)·응답 DTO가 다르므로 별도 모듈로 둔다(재사용 아님 - 독자 노출
경로는 필드 하나까지 의도적으로 갈라야 한다).
"""

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import defer, selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.pagination import compute_offset
from src.models.work import Episode, Tag, Work, WorkTag
from src.schemas.catalog import (
    EpisodeSummary,
    PublicTag,
    WorkDetail,
    WorkListItem,
    WorkListResponse,
)
from src.services import r2_service


def public_work_filters() -> list:
    """독자에게 노출 가능한 작품 조건(공개 + 미삭제). 작품을 거치는 모든 공개 경로의 단일 출처.

    ⚠️ 그룹 B/C(회차 콘텐츠·진행도)도 Work join 시 반드시 이걸 쓸 것 - admin의
    episode_service.get_episode 패턴은 deleted_at만 검사해서(관리자는 비공개 작품도
    봐야 하므로) 그대로 복사하면 숨긴 작품(is_published=false)의 회차가 새어 나간다.
    """
    return [Work.is_published.is_(True), Work.deleted_at.is_(None)]


def public_episode_filters() -> list:
    """독자에게 노출 가능한 회차 조건(공개 + 미삭제). 회차를 거치는 모든 공개 경로의 단일 출처.

    ⚠️ deleted_at은 중복 방어다. soft delete(#85)가 is_published=false를 같은 UPDATE로
    걸어주므로 원칙상 첫 조건만으로 충분하지만, 그러면 "삭제 ⟹ 비공개" 불변식이 깨지는
    순간 노출 경로 전부가 동시에 뚫린다. 노출은 되돌릴 수 없어 한 줄을 더 쓴다.

    is_published = true를 그대로 포함하므로 partial 인덱스(idx_episodes_published,
    idx_episodes_published_at)의 조건을 여전히 만족한다 - 플래너가 계속 인덱스를 탄다.
    """
    return [Episode.is_published.is_(True), Episode.deleted_at.is_(None)]


def _public_episode_count_subquery():
    """작품별 공개 회차 수. models.work.Work.episode_count(관리자용 전체 카운트,
    column_property)와는 다른 값이라 재사용하지 않고 여기서 별도 계산한다."""
    return (
        select(func.count(Episode.id))
        .where(Episode.work_id == Work.id, *public_episode_filters())
        .correlate(Work)
        .scalar_subquery()
    )


def _to_list_item(work: Work, episode_count: int) -> WorkListItem:
    return WorkListItem(
        id=work.id,
        title=work.title,
        cover_image_url=r2_service.public_url(work.cover_image, version=work.updated_at),
        status=work.status,
        tags=list(work.tags),
        episode_count=episode_count,
    )


def _to_episode_summary(
    ep: Episode,
    base_price: int,
    work_cover_image: str | None,
    work_updated_at: datetime,
) -> EpisodeSummary:
    if ep.thumbnail is not None:
        thumbnail_url = r2_service.public_url(
            r2_service.episode_thumb_key(ep.work_id, ep.id), version=ep.updated_at
        )
    else:
        # 회차 썸네일 미선택 시 작품 표지로 대체(fallback). 원고 첫 페이지로 대체하면
        # 유료·미공개 페이지가 공개 URL로 새는 경로가 되므로 금지(M2 D2 결정) - 둘 다
        # 없으면 public_url이 None을 반환해 FE가 placeholder로 처리한다.
        thumbnail_url = r2_service.public_url(work_cover_image, version=work_updated_at)
    return EpisodeSummary(
        id=ep.id,
        episode_no=ep.episode_no,
        title=ep.title,
        subtitle=ep.subtitle,
        thumbnail_url=thumbnail_url,
        is_free=ep.is_free,
        is_locked=not ep.is_free,
        is_purchased=False,  # M2는 결제 없음(M3에서 실제 구매 여부로 대체)
        # 실효가 계산은 여기(서버) 한 곳 - episodes.price NULL이면 작품 기준가(models/work.py).
        price=None if ep.is_free else (ep.price if ep.price is not None else base_price),
    )


async def list_public_tags(session: AsyncSession) -> list[PublicTag]:
    """공개 작품에 실제로 달린 태그만 + 공개 작품 수 (#82 - E1 태그 필터의 데이터 소스).

    inner join + public_work_filters()라 미공개·삭제 작품에만 달린 태그는 행 자체가
    안 나온다 - 태그 존재로 미공개 작품의 존재가 새는 경로 차단. Tag 전량 조회 후
    앱단 필터가 아니라 SQL에서 거르는 이유이기도 하다.
    """
    rows = (
        await session.exec(
            # works_tags PK가 (work_id, tag_id)라 태그당 작품 행 중복이 불가능 - count에
            # distinct 불요. group by는 PK(Tag.id)라 Tag 엔티티·name 선택이 유효(PG 함수 종속).
            select(Tag, func.count(Work.id))
            .join(WorkTag, WorkTag.tag_id == Tag.id)
            .join(Work, Work.id == WorkTag.work_id)
            .where(*public_work_filters())
            .group_by(Tag.id)
            .order_by(Tag.name)
        )
    ).all()
    return [PublicTag(id=tag.id, name=tag.name, work_count=count) for tag, count in rows]


async def list_works(
    session: AsyncSession, *, page: int, size: int, tag: str | None
) -> WorkListResponse:
    """공개(is_published) + 미삭제 작품 목록. 최신순, 태그 필터, 페이지네이션."""
    offset, limit = compute_offset(page, size)

    filters = public_work_filters()
    if tag:
        tag_exists = (
            select(WorkTag.work_id)
            .join(Tag, Tag.id == WorkTag.tag_id)
            .where(WorkTag.work_id == Work.id, Tag.name == tag)
            .correlate(Work)
            .exists()
        )
        filters.append(tag_exists)

    total = (await session.exec(select(func.count(Work.id)).where(*filters))).one()

    count_subq = _public_episode_count_subquery()
    rows = (
        await session.exec(
            select(Work, count_subq)
            # Work.episode_count(전체 카운트 column_property)는 여기서 안 쓰는데 defer가
            # 없으면 행마다 상관 서브쿼리가 같이 실려 계산만 하고 버려진다.
            .options(selectinload(Work.tags), defer(Work.episode_count))
            .where(*filters)
            # id tie-breaker: 같은 트랜잭션 일괄 삽입은 created_at(func.now())이 동일해
            # 정렬이 불안정해지고 offset 페이지 경계에서 행이 중복/누락될 수 있다.
            .order_by(Work.created_at.desc(), Work.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [_to_list_item(work, count) for work, count in rows]
    # size는 요청 원값이 아니라 실제 적용된 limit - 클라이언트 페이지 수 계산의 단일 출처.
    return WorkListResponse(items=items, total=total, page=page, size=limit)


async def get_work_detail(work_id: uuid.UUID, session: AsyncSession) -> WorkDetail | None:
    """공개 상세: 작품 자체가 공개+미삭제여야 하고, 회차는 공개분만 노출한다."""
    result = await session.exec(
        select(Work)
        .where(Work.id == work_id, *public_work_filters())
        .options(selectinload(Work.tags), defer(Work.episode_count))
    )
    work = result.first()
    if work is None:
        return None

    episodes = (
        await session.exec(
            select(Episode)
            .where(Episode.work_id == work_id, *public_episode_filters())
            .order_by(Episode.episode_no)
        )
    ).all()

    return WorkDetail(
        id=work.id,
        title=work.title,
        synopsis=work.synopsis,
        cover_image_url=r2_service.public_url(work.cover_image, version=work.updated_at),
        episode_base_price=work.episode_base_price,
        status=work.status,
        tags=list(work.tags),
        episodes=[
            _to_episode_summary(ep, work.episode_base_price, work.cover_image, work.updated_at)
            for ep in episodes
        ],
    )


async def list_public_episodes(
    work_id: uuid.UUID, session: AsyncSession
) -> list[EpisodeSummary] | None:
    """공개 회차 목록 (M2 B1). 작품이 노출 불가면 None(라우터가 404로 매핑).

    get_work_detail을 그대로 재사용한다 - 같은 회차 배열을 두 번 쿼리하면 공개 필터를
    타는 경로가 둘로 갈라지고, 한쪽만 고치는 사고가 난다. 작품 메타(tags·synopsis)를
    같이 읽어 버리는 낭비가 있지만 단일 작품 조회라 무시할 수준이고, 필터 일원화가
    우선이다(B2 우선순위: 안정성 > 성능).
    """
    detail = await get_work_detail(work_id, session)
    return None if detail is None else detail.episodes


async def public_episode_exists(episode_id: uuid.UUID, session: AsyncSession) -> bool:
    """독자에게 노출 가능한 회차인지 확인 (회차 자체 공개 + 소속 작품 public_work_filters()).

    그룹 C1(뷰어 진행도) PUT 저장 게이트. 그룹 B(회차 콘텐츠 API)가 아직 없어 신설했지만
    필터 단일 출처는 그대로 public_work_filters() - B가 나중에 별도 조회 함수를 만들어도
    이 필터는 갈라지지 않는다. Episode.id만 select해 content(JSONB) 로딩을 피한다.
    """
    result = await session.exec(
        select(Episode.id)
        .join(Work, Work.id == Episode.work_id)
        .where(
            Episode.id == episode_id,
            *public_episode_filters(),
            *public_work_filters(),
        )
    )
    return result.first() is not None
