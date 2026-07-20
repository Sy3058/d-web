"""공개 작품 카탈로그 라우터 (M2 그룹 A). 인증 불요 - 비로그인 유저도 조회 가능.

관리자 CRUD(routers/admin_works.py)와 별개 라우터. 응답은 schemas/catalog.py 전용
DTO만 사용한다(admin 스키마 재사용 금지 - services/catalog_service.py 모듈 docstring 참조).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import get_session
from src.lib.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.schemas.catalog import EpisodeSummary, WorkDetail, WorkListResponse
from src.services import catalog_service

router = APIRouter(prefix="/works", tags=["works"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# 404에 no-store를 싣는 이유: 404는 명세상 기본 캐시 가능 상태 코드라(RFC 9111) 명시가
# 없으면 heuristic 캐싱 대상이 된다. 작가가 작품 공개 토글을 켜기 전에 독자가 열어본
# 404가 캐시되면, 공개한 뒤에도 그 독자는 계속 404를 본다. HTTPException은 라우터
# 함수의 Response가 아니라 예외 핸들러가 만든 응답으로 나가므로 여기서 직접 실어야 한다.
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="작품을 찾을 수 없습니다",
    headers={"Cache-Control": "no-store"},
)


@router.get("", response_model=WorkListResponse)
async def list_works(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    # le= 상한을 계약(OpenAPI)에 노출해 초과 요청을 422로 명시 거부 - 조용한 클램프만
    # 있으면 클라이언트가 요청 size로 페이지 수를 계산하다 어긋난다.
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    tag: str | None = Query(default=None),
) -> WorkListResponse:
    return await catalog_service.list_works(session, page=page, size=size, tag=tag)


@router.get("/{work_id}", response_model=WorkDetail)
async def get_work(work_id: uuid.UUID, session: SessionDep) -> WorkDetail:
    detail = await catalog_service.get_work_detail(work_id, session)
    if detail is None:
        raise _NOT_FOUND
    return detail


@router.get("/{work_id}/episodes", response_model=list[EpisodeSummary])
async def list_work_episodes(work_id: uuid.UUID, session: SessionDep) -> list[EpisodeSummary]:
    """공개 회차 목록 (M2 B1). GET /works/{id}(A2)의 episodes와 같은 배열을, 작품 메타
    없이 필요한 소비자(뷰어 네비 등)를 위해 단독으로 낸다."""
    episodes = await catalog_service.list_public_episodes(work_id, session)
    if episodes is None:
        raise _NOT_FOUND
    return episodes
