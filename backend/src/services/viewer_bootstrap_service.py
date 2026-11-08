"""중앙 열람 권한을 적용한 최소 뷰어 메타와 공개 이웃 조회."""

import uuid

from sqlalchemy import true, tuple_
from sqlalchemy.orm import aliased
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.work import Episode, Work
from src.schemas.viewer import ViewerBootstrap, ViewerEpisodeLink
from src.services.episode_access_service import (
    EpisodeAccessScope,
    episode_access_columns,
    evaluate_episode_access,
)


async def get_viewer_bootstrap(
    work_id: uuid.UUID,
    public_id: int,
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
) -> ViewerBootstrap | None:
    # 권한 입력·메타·양쪽 이웃을 동일 statement snapshot에서 읽는다. 따로 조회하면
    # 공개 전 비공개 메타를 공개 후 권한으로 허용하거나 재정렬 전후 이웃을 섞을 수 있다.
    def neighbor_query(*, previous: bool):
        neighbor = aliased(Episode)
        position = tuple_(neighbor.sort_order, neighbor.created_at, neighbor.id)
        current = tuple_(Episode.sort_order, Episode.created_at, Episode.id)
        ordering = (neighbor.sort_order, neighbor.created_at, neighbor.id)
        return (
            select(neighbor.public_id, neighbor.title)
            .where(
                neighbor.work_id == Episode.work_id,
                neighbor.is_published.is_(True),
                neighbor.deleted_at.is_(None),
                Work.is_published.is_(True),
                position < current if previous else position > current,
            )
            .order_by(*(column.desc() for column in ordering) if previous else ordering)
            .limit(1)
            .correlate(Episode, Work)
            .lateral()
        )

    previous = neighbor_query(previous=True)
    following = neighbor_query(previous=False)
    row = (
        await session.exec(
            select(
                Work.title.label("work_title"),
                Episode.id,
                Episode.title,
                Episode.subtitle,
                previous.c.public_id.label("previous_public_id"),
                previous.c.title.label("previous_title"),
                following.c.public_id.label("next_public_id"),
                following.c.title.label("next_title"),
                *episode_access_columns(user_id),
            )
            .join(Work, Work.id == Episode.work_id)
            .outerjoin(previous, true())
            .outerjoin(following, true())
            .where(
                Work.id == work_id,
                Episode.public_id == public_id,
                Work.deleted_at.is_(None),
                Episode.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return None
    snapshot = evaluate_episode_access(
        episode_public=row.episode_public,
        work_public=row.work_public,
        content=row.content,
        image_keys=row.image_keys,
        active_purchase_id=row.active_purchase_id,
        viewed_at=row.viewed_at,
    )
    if snapshot.access.scope == EpisodeAccessScope.UNAVAILABLE:
        return None

    previous_episode = (
        ViewerEpisodeLink(public_id=row.previous_public_id, title=row.previous_title)
        if row.previous_public_id is not None
        else None
    )
    next_episode = (
        ViewerEpisodeLink(public_id=row.next_public_id, title=row.next_title)
        if row.next_public_id is not None
        else None
    )

    return ViewerBootstrap(
        work_id=work_id,
        work_title=row.work_title,
        episode_id=row.id,
        public_id=public_id,
        episode_title=row.title,
        episode_subtitle=row.subtitle,
        previous_episode=previous_episode,
        next_episode=next_episode,
    )
