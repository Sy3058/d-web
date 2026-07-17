"""공개 카탈로그 조회 서비스 (M2 그룹 A).

router는 HTTP 매핑만, 여기서 필터·집계·DTO 조립까지 담당한다. admin work_service와
조회 조건(공개+미삭제만)·응답 DTO가 다르므로 별도 모듈로 둔다(재사용 아님 - 독자 노출
경로는 필드 하나까지 의도적으로 갈라야 한다).
"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.pagination import compute_offset
from src.models.work import Episode, Tag, Work, WorkTag
from src.schemas.catalog import EpisodeSummary, WorkDetail, WorkListItem, WorkListResponse


def _public_url(key: str | None) -> str | None:
    """R2 키를 공개 버킷 URL로 조립. 키가 없으면 None(표지 미등록)."""
    if not key:
        return None
    return f"{settings.public_asset_base_url}/{key}"


def _public_episode_count_subquery():
    """작품별 공개(is_published) 회차 수. models.work.Work.episode_count(전체 카운트,
    column_property)와는 다른 값이라 재사용하지 않고 여기서 별도 계산한다."""
    return (
        select(func.count(Episode.id))
        .where(Episode.work_id == Work.id, Episode.is_published.is_(True))
        .correlate(Work)
        .scalar_subquery()
    )


def _to_list_item(work: Work, episode_count: int) -> WorkListItem:
    return WorkListItem(
        id=work.id,
        title=work.title,
        cover_image_url=_public_url(work.cover_image),
        status=work.status,
        tags=list(work.tags),
        episode_count=episode_count,
    )


def _to_episode_summary(ep: Episode) -> EpisodeSummary:
    return EpisodeSummary(
        id=ep.id,
        episode_no=ep.episode_no,
        title=ep.title,
        subtitle=ep.subtitle,
        thumbnail_url=None,  # D2(공개 축소본) 이전 - schemas/catalog.py 모듈 docstring 참조
        is_free=ep.is_free,
        is_locked=not ep.is_free,
        is_purchased=False,  # M2는 결제 없음(M3에서 실제 구매 여부로 대체)
    )


async def list_works(
    session: AsyncSession, *, page: int, size: int, tag: str | None
) -> WorkListResponse:
    """공개(is_published) + 미삭제 작품 목록. 최신순, 태그 필터, 페이지네이션."""
    offset, limit = compute_offset(page, size)

    filters = [Work.is_published.is_(True), Work.deleted_at.is_(None)]
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
            .where(*filters)
            .options(selectinload(Work.tags))
            .order_by(Work.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [_to_list_item(work, count) for work, count in rows]
    return WorkListResponse(items=items, total=total, page=page, size=size)


async def get_work_detail(work_id: uuid.UUID, session: AsyncSession) -> WorkDetail | None:
    """공개 상세: 작품 자체가 공개+미삭제여야 하고, 회차는 공개분만 노출한다."""
    result = await session.exec(
        select(Work)
        .where(
            Work.id == work_id,
            Work.is_published.is_(True),
            Work.deleted_at.is_(None),
        )
        .options(selectinload(Work.tags))
    )
    work = result.first()
    if work is None:
        return None

    episodes = (
        await session.exec(
            select(Episode)
            .where(Episode.work_id == work_id, Episode.is_published.is_(True))
            .order_by(Episode.episode_no)
        )
    ).all()

    return WorkDetail(
        id=work.id,
        title=work.title,
        synopsis=work.synopsis,
        cover_image_url=_public_url(work.cover_image),
        episode_base_price=work.episode_base_price,
        status=work.status,
        tags=list(work.tags),
        episodes=[_to_episode_summary(ep) for ep in episodes],
    )
