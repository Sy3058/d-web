"""커미션 카드·사이트 문구 관리 엔드포인트 (M2 그룹 G). 전 엔드포인트 require_owner.

카드 = 크레페식 홍보 카드(schemas/commission.py). 샘플 이미지 업로드 흐름은
admin_episodes(원고)와 같고 대상 버킷만 다르다(공개 dweb-cover - service가 결정).
신청 폼·접수 관리는 M5 - 이 라우터는 홍보 콘텐츠 편집까지만.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import require_owner
from src.lib.db import get_session
from src.lib.exceptions import (
    CommissionConflictError,
    CommissionValidationError,
    ImageValidationError,
)
from src.lib.uploads import R2_UNAVAILABLE, read_image_upload
from src.models.commission import CommissionItem, SiteText, SiteTextSlotKey
from src.models.user import User
from src.schemas.commission import (
    AdminCommissionItemRead,
    ArtistProfileRead,
    ArtistProfileUpdate,
    CommissionItemCreate,
    CommissionItemReorder,
    CommissionItemUpdate,
    SiteTextRead,
    SiteTextUpdate,
)
from src.services import commission_service
from src.services.commission_service import MAX_SAMPLES_PER_ITEM
from src.services.image_service import convert_to_webp
from src.services.r2_service import R2NotConfiguredError

router = APIRouter(prefix="/admin", tags=["admin-commission"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OwnerDep = Annotated[User, Depends(require_owner)]

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="커미션 카드를 찾을 수 없습니다"
)


async def _item_or_404(item_id: uuid.UUID, session: AsyncSession) -> CommissionItem:
    item = await commission_service.get_item(item_id, session)
    if item is None:
        raise _NOT_FOUND
    return item


@router.get("/commission-items", response_model=list[AdminCommissionItemRead])
async def list_commission_items(owner: OwnerDep, session: SessionDep) -> Sequence[CommissionItem]:
    return await commission_service.list_items(session)


@router.post(
    "/commission-items",
    response_model=AdminCommissionItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_commission_item(
    body: CommissionItemCreate, owner: OwnerDep, session: SessionDep
) -> CommissionItem:
    return await commission_service.create_item(body, session)


@router.put("/commission-items", response_model=list[AdminCommissionItemRead])
async def reorder_commission_items(
    body: CommissionItemReorder, owner: OwnerDep, session: SessionDep
) -> list[CommissionItem]:
    """카드 전량을 원하는 순서로 받아 한 트랜잭션에서 1..N으로 재배정한다."""
    try:
        return list(await commission_service.reorder_items(body.item_ids, session))
    except CommissionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.put("/commission-items/{item_id}", response_model=AdminCommissionItemRead)
async def update_commission_item(
    item_id: uuid.UUID, body: CommissionItemUpdate, owner: OwnerDep, session: SessionDep
) -> CommissionItem:
    item = await _item_or_404(item_id, session)
    try:
        return await commission_service.update_item(item, body, session)
    except CommissionValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/commission-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_commission_item(item_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> None:
    item = await _item_or_404(item_id, session)
    await commission_service.delete_item(item, session)


@router.post("/commission-items/{item_id}/images", response_model=AdminCommissionItemRead)
async def upload_commission_sample(
    item_id: uuid.UUID, image: UploadFile, owner: OwnerDep, session: SessionDep
) -> CommissionItem:
    """샘플 1장 업로드: 변환 → 공개 버킷 → sample_image_keys 끝에 원자 append
    (admin_episodes.upload_episode_image와 같은 구조 - 주석 근거는 그쪽 참조)."""
    item = await _item_or_404(item_id, session)
    # 싼 선검증 - 진짜 상한 보증은 append의 조건부 UPDATE(동시 요청 race 차단).
    if len(item.sample_image_keys) >= MAX_SAMPLES_PER_ITEM:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"카드당 샘플 이미지는 최대 {MAX_SAMPLES_PER_ITEM}장입니다",
        )
    expected_len = len(item.sample_image_keys)
    # 읽기 트랜잭션 종료 - 변환·R2 왕복 동안 커넥션 미점유. rollback으로 item ORM 객체가
    # 만료되므로 이후 속성 접근 금지(필요한 값은 위에서 스냅샷).
    await session.rollback()
    try:
        data = await read_image_upload(image)
        webp = await convert_to_webp(data)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        return await commission_service.append_sample_image(item_id, expected_len, webp, session)
    except CommissionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except R2NotConfiguredError as exc:
        raise R2_UNAVAILABLE from exc


@router.get("/site-texts/{key}", response_model=SiteTextRead)
async def get_site_text(
    key: SiteTextSlotKey, owner: OwnerDep, session: SessionDep
) -> SiteText | SiteTextRead:
    """행 없음 = 404가 아니라 빈 기본값 응답 - 행은 시딩하지 않고 PUT이 upsert하므로
    첫 편집 진입이 여기서 막히면 안 된다(models/commission.py SiteText docstring)."""
    row = await commission_service.get_site_text(key, session)
    if row is None:
        return SiteTextRead(key=key, body="", updated_at=None)
    return row


@router.put("/site-texts/{key}", response_model=SiteTextRead)
async def put_site_text(
    key: SiteTextSlotKey, body: SiteTextUpdate, owner: OwnerDep, session: SessionDep
) -> SiteText:
    return await commission_service.upsert_site_text(key, body.body, session)


@router.get("/artist-profile", response_model=ArtistProfileRead)
async def get_artist_profile(owner: OwnerDep, session: SessionDep) -> ArtistProfileRead:
    return await commission_service.get_artist_profile(session)


@router.put("/artist-profile", response_model=ArtistProfileRead)
async def put_artist_profile(
    body: ArtistProfileUpdate, owner: OwnerDep, session: SessionDep
) -> ArtistProfileRead:
    return await commission_service.upsert_artist_profile(body, session)


@router.post("/artist-profile/image", response_model=ArtistProfileRead)
async def upload_artist_profile_image(
    image: UploadFile, owner: OwnerDep, session: SessionDep
) -> ArtistProfileRead:
    try:
        data = await read_image_upload(image)
        webp = await convert_to_webp(data)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        return await commission_service.upload_artist_profile_image(webp, session)
    except R2NotConfiguredError as exc:
        raise R2_UNAVAILABLE from exc
