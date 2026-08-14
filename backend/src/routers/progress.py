"""뷰어 진행도 라우터 (M2 그룹 C1). 인증 필수 - 로그인 유저만 저장/조회 가능.

PUT은 회차 공개성 검사를 통과해야 저장된다(검사 자체는 progress_service 소관 -
서비스가 도메인 불변식을 소유한다). GET은 공개성을 재검사하지 않고 진행도 행 존재만
본다 - 작품이 일시 비공개로 전환됐다 재공개돼도 기존 진행도가 유지되는 편이 UX상
맞다는 결정(2026-07-20). GET이 노출하는 값은 요청자 본인의 위치 값뿐이라 숨길
대상이 아니다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import get_current_user
from src.lib.db import get_session
from src.models.user import User
from src.models.viewer import ViewerProgress
from src.schemas.viewer import LastReadEpisode, ProgressRead, ProgressUpdate, WorkProgressRead
from src.services import progress_service

router = APIRouter(prefix="/episodes", tags=["progress"])
work_router = APIRouter(prefix="/works", tags=["progress"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

# 두 404를 구분한다 - GET에서 "회차 없음"을 쓰면 회차가 멀쩡히 존재하는데도 없다고
# 알리게 되고, FE가 detail을 그대로 노출하면 틀린 오류 문구가 뜬다.
_EPISODE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="회차를 찾을 수 없습니다"
)
_PROGRESS_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="저장된 진행도가 없습니다",
    headers={"Cache-Control": "no-store"},
)


def _to_read(progress: ViewerProgress) -> ProgressRead:
    return ProgressRead(
        episode_id=progress.episode_id,
        page_no=progress.page_no,
        block_offset_bp=progress.block_offset_bp,
        updated_at=progress.updated_at,
    )


def _no_store(response: Response) -> None:
    """유저별 개인 데이터라 브라우저·중간 캐시에 남기지 않는다."""
    response.headers["Cache-Control"] = "no-store"


@router.put("/{episode_id}/progress", response_model=ProgressRead)
async def update_progress(
    episode_id: uuid.UUID,
    body: ProgressUpdate,
    current_user: CurrentUserDep,
    session: SessionDep,
    response: Response,
) -> ProgressRead:
    progress = await progress_service.upsert_progress(
        current_user.id,
        episode_id,
        body.page_no,
        body.block_offset_bp if "block_offset_bp" in body.model_fields_set else None,
        session,
    )
    if progress is None:
        raise _EPISODE_NOT_FOUND
    _no_store(response)
    return _to_read(progress)


@router.get("/{episode_id}/progress", response_model=ProgressRead)
async def read_progress(
    episode_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    response: Response,
) -> ProgressRead:
    progress = await progress_service.get_progress(current_user.id, episode_id, session)
    if progress is None:
        raise _PROGRESS_NOT_FOUND
    _no_store(response)
    return _to_read(progress)


@work_router.get("/{work_id}/progress", response_model=WorkProgressRead)
async def read_work_progress(
    work_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    response: Response,
) -> WorkProgressRead:
    progress = await progress_service.get_work_progress(current_user.id, work_id, session)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="작품을 찾을 수 없습니다",
            headers={"Cache-Control": "no-store"},
        )
    _no_store(response)
    last_episode = (
        None
        if progress.last_episode is None
        else LastReadEpisode(
            id=progress.last_episode.id,
            public_id=progress.last_episode.public_id,
            title=progress.last_episode.title,
        )
    )
    return WorkProgressRead(
        read_episode_ids=progress.read_episode_ids,
        last_episode=last_episode,
    )
