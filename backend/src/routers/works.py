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
from src.schemas.catalog import WorkDetail, WorkListResponse
from src.services import catalog_service

router = APIRouter(prefix="/works", tags=["works"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="작품을 찾을 수 없습니다")


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
