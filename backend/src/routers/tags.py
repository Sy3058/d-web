"""공개 태그 목록 라우터 (#82). 인증 불요 - 독자 사이트 태그 필터의 데이터 소스.

`GET /works?tag=` 필터링 자체는 works 라우터 소관이고, 여기는 "어떤 태그가
있는지"만 알려준다. 응답 구성 규칙(공개 작품에 달린 태그만)은 catalog_service 참조.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import get_session
from src.schemas.catalog import PublicTag
from src.services import catalog_service

router = APIRouter(prefix="/tags", tags=["tags"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[PublicTag])
async def list_tags(session: SessionDep) -> list[PublicTag]:
    return await catalog_service.list_public_tags(session)
