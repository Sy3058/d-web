"""뷰어 진행도 저장/조회 서비스 (M2 그룹 C1, E4)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.viewer import ViewerProgress
from src.models.work import Episode, Work
from src.services import catalog_service


@dataclass(frozen=True)
class LastReadEpisodeSnapshot:
    id: uuid.UUID
    public_id: int
    title: str


@dataclass(frozen=True)
class WorkProgressSnapshot:
    read_episode_ids: list[uuid.UUID]
    last_episode: LastReadEpisodeSnapshot | None


async def upsert_progress(
    user_id: uuid.UUID,
    episode_id: uuid.UUID,
    page_no: int,
    block_offset_bp: int | None,
    session: AsyncSession,
) -> ViewerProgress | None:
    """진행도 upsert. 없으면 insert, 있으면 블록·내부 위치·updated_at 갱신.

    회차가 독자에게 노출 가능한 상태가 아니면 저장하지 않고 None을 반환한다(라우터가
    404로 매핑 - catalog_service.get_work_detail과 같은 패턴). 이 검사를 호출자(라우터)에
    두지 않는 이유: 저장 가능 여부는 HTTP 포장이 아니라 도메인 불변식이라 트랜잭션 경계를
    소유한 서비스가 지켜야 한다(backend/CLAUDE.md 레이어 규칙). 라우터에만 두면 두 번째
    호출부가 생길 때 조용히 우회된다 - public_work_filters() docstring이 경고하는 것과
    같은 계열의 사고.

    onupdate=func.now()(models/viewer.py)는 일반 UPDATE 문에서만 발동하고 ON CONFLICT
    DO UPDATE의 SET절에는 적용되지 않아 updated_at을 여기서 명시한다(study
    postgres-upsert-onupdate-trap).
    """
    if not await catalog_service.public_episode_exists(episode_id, session):
        return None

    insert_offset = 0 if block_offset_bp is None else block_offset_bp
    stmt = pg_insert(ViewerProgress).values(
        user_id=user_id,
        episode_id=episode_id,
        page_no=page_no,
        block_offset_bp=insert_offset,
    )
    # 구버전 클라이언트는 offset 필드를 보내지 않는다. 같은 블록을 저장하는 동안에는 새
    # 클라이언트가 기록한 정밀 위치를 보존하고, 블록이 바뀌면 새 블록 시작점으로 초기화한다.
    offset_update = (
        stmt.excluded.block_offset_bp
        if block_offset_bp is not None
        else case(
            (stmt.excluded.page_no != ViewerProgress.page_no, 0),
            else_=ViewerProgress.block_offset_bp,
        )
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_viewer_progress_user_episode",
        set_={
            "page_no": stmt.excluded.page_no,
            "block_offset_bp": offset_update,
            "updated_at": func.now(),
        },
    ).returning(ViewerProgress)

    result = await session.exec(stmt)
    row = result.scalars().one()
    await session.commit()
    return row


async def get_progress(
    user_id: uuid.UUID, episode_id: uuid.UUID, session: AsyncSession
) -> ViewerProgress | None:
    """저장된 진행도 조회. 없으면 None(라우터가 404로 매핑)."""
    result = await session.exec(
        select(ViewerProgress).where(
            ViewerProgress.user_id == user_id,
            ViewerProgress.episode_id == episode_id,
        )
    )
    return result.first()


async def get_work_progress(
    user_id: uuid.UUID, work_id: uuid.UUID, session: AsyncSession
) -> WorkProgressSnapshot | None:
    """공개 작품의 사용자별 읽은 회차와 마지막 읽은 회차를 조회한다.

    먼저 PK로 공개 작품 존재를 확인하고, 진행도는 ViewerProgress에서 시작해 실제로 읽은
    행만 가져온다. Work에서 공개 Episode 전체를 LEFT JOIN하면 진행도 0건인 사용자도 작품의
    모든 회차를 DB에서 앱으로 전송하게 되므로 피한다. 두 번째 쿼리에도 작품 공개 필터를
    반복해 두 SELECT 사이에 비공개 전환이 일어나도 개인 진행도를 fail-closed로 숨긴다.
    """
    work_exists = await session.exec(
        select(Work.id).where(Work.id == work_id, *catalog_service.public_work_filters())
    )
    if work_exists.first() is None:
        return None

    rows = (
        await session.exec(
            select(
                ViewerProgress.episode_id,
                Episode.public_id,
                Episode.title,
                ViewerProgress.updated_at,
                ViewerProgress.id,
            )
            .select_from(ViewerProgress)
            .join(Episode, Episode.id == ViewerProgress.episode_id)
            .join(Work, Work.id == Episode.work_id)
            .where(
                ViewerProgress.user_id == user_id,
                Episode.work_id == work_id,
                *catalog_service.public_episode_filters(),
                *catalog_service.public_work_filters(),
            )
            .order_by(
                ViewerProgress.updated_at.desc(),
                ViewerProgress.id.desc(),
            )
        )
    ).all()
    if not rows:
        return WorkProgressSnapshot(read_episode_ids=[], last_episode=None)

    latest_episode_id, latest_public_id, latest_title, _, _ = rows[0]
    return WorkProgressSnapshot(
        read_episode_ids=[episode_id for episode_id, _, _, _, _ in rows],
        last_episode=LastReadEpisodeSnapshot(
            id=latest_episode_id,
            public_id=latest_public_id,
            title=latest_title,
        ),
    )
