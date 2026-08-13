"""공개 커미션·사이트 문구 조회 (M2 그룹 G). 인증 불요 - 랜딩·/commission 표시 전용.

admin DTO(AdminCommissionItemRead - sample_image_keys 노출)를 재사용하지 않는다.
공개 버킷 키라 유출 위험은 없지만, "독자 응답에 R2 키 부재"(B2 계약)와 표면을
일치시킨다(routers/works.py가 admin 스키마를 안 쓰는 것과 같은 계열).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import get_session
from src.models.commission import SiteText, SiteTextSlotKey
from src.schemas.commission import ArtistProfileRead, PublicCommissionItem, SiteTextRead
from src.services import commission_service

router = APIRouter(tags=["commission"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# 404 no-store: 작가가 문구를 처음 저장하기 전에 캐시된 404가 저장 후에도 남으면 안 된다
# (routers/works.py _NOT_FOUND와 같은 근거 - 404는 명세상 기본 캐시 가능).
_TEXT_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="문구를 찾을 수 없습니다",
    headers={"Cache-Control": "no-store"},
)


@router.get("/commission-items", response_model=list[PublicCommissionItem])
async def list_commission_items(session: SessionDep) -> list[PublicCommissionItem]:
    """카드 전량(마감 포함 - 마감 배지 표시). 정렬은 sort_order(서비스)."""
    return await commission_service.list_public_items(session)


@router.get("/site-texts/{key}", response_model=SiteTextRead)
async def get_site_text(key: SiteTextSlotKey, session: SessionDep) -> SiteText:
    """무등록 key = 422(문구 슬롯 enum 검증), 미저장 슬롯 = 404(FE 존 접기)."""
    row = await commission_service.get_site_text(key, session)
    if row is None:
        raise _TEXT_NOT_FOUND
    return row


@router.get("/artist-profile", response_model=ArtistProfileRead)
async def get_artist_profile(session: SessionDep) -> ArtistProfileRead:
    return await commission_service.get_artist_profile(session)
