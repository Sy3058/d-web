"""작품 CRUD 엔드포인트 (M1.5 C1, ADM-02). 전 엔드포인트 require_owner - 비-owner 403.

표지(cover_image)·에피소드 이미지는 R2 키 문자열만 수용한다(실제 업로드·변환은 그룹 D).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import require_owner
from src.lib.db import get_session
from src.lib.exceptions import ImageValidationError
from src.lib.uploads import R2_UNAVAILABLE, read_image_upload
from src.models.user import User
from src.models.work import Work
from src.schemas.work import WorkCreate, WorkRead, WorkUpdate
from src.services import work_service
from src.services.image_service import convert_to_webp
from src.services.r2_service import R2NotConfiguredError

router = APIRouter(prefix="/admin/works", tags=["admin-works"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OwnerDep = Annotated[User, Depends(require_owner)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="작품을 찾을 수 없습니다")


async def _get_or_404(work_id: uuid.UUID, session: AsyncSession, *, with_tags: bool = True) -> Work:
    work = await work_service.get_work(work_id, session, with_tags=with_tags)
    if work is None:
        raise _NOT_FOUND
    return work


@router.post("", response_model=WorkRead, status_code=status.HTTP_201_CREATED)
async def create_work(body: WorkCreate, owner: OwnerDep, session: SessionDep) -> Work:
    return await work_service.create_work(body, owner.id, session)


# _get_or_404·update_work·delete_work 전부 author_id로 필터링하지 않는다 - 어떤 owner든
# 전 작품을 조회·수정·삭제할 수 있다(단일 작가 정체성, owner 계정이 여럿이어도 매출은
# 단수 - DECISIONS "관리자 권한 분리").


@router.get("", response_model=list[WorkRead])
async def list_works(owner: OwnerDep, session: SessionDep) -> list[Work]:
    return list(await work_service.list_works(session))


@router.get("/{work_id}", response_model=WorkRead)
async def get_work(work_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> Work:
    return await _get_or_404(work_id, session)


@router.put("/{work_id}", response_model=WorkRead)
async def update_work(
    work_id: uuid.UUID, body: WorkUpdate, owner: OwnerDep, session: SessionDep
) -> Work:
    work = await _get_or_404(work_id, session)
    return await work_service.update_work(work, body, session)


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(work_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> None:
    # 204 응답은 태그를 읽지 않으므로 with_tags=False로 불필요한 조인 로드를 생략.
    work = await _get_or_404(work_id, session, with_tags=False)
    await work_service.soft_delete_work(work, session)


@router.post("/{work_id}/cover", response_model=WorkRead)
async def upload_cover(
    work_id: uuid.UUID, image: UploadFile, owner: OwnerDep, session: SessionDep
) -> Work:
    """표지 단건 업로드(M1.5 D3, C1 이연분): 변환 → works/{id}/cover.webp 덮어쓰기.

    표지는 에피소드 페이지와 별개 파일이다(회차 썸네일 선택은 에피소드 PUT의
    thumbnail - 그쪽은 업로드된 페이지 중 선택, 여기는 독립 일러스트 업로드).
    """
    work = await _get_or_404(work_id, session)
    try:
        data = await read_image_upload(image)
        webp = await convert_to_webp(data)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        return await work_service.set_cover_image(work, webp, session)
    except R2NotConfiguredError as exc:
        raise R2_UNAVAILABLE from exc
