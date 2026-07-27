"""에피소드 관리 엔드포인트 (M1.5 D3, ADM-03). 전 엔드포인트 require_owner.

구조 A(장당 업로드 - 2026-07-10 council 후 확정): POST 메타(JSON, draft 생성)
→ POST images(multipart 단건) 반복 → PUT(JSON, 메타·재배열·썸네일·공개).
단일 multipart 일괄안은 폐기 - PUT의 부분수정 검증(model_fields_set)이 Form
인코딩에서 성립하지 않고, episode_id 확보·메모리 피크·부분 실패가 전부 악화된다.

응답은 AdminEpisodeRead 전용(image_keys 노출 - 독자 라우터 재사용 금지, M2는 별도 DTO).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import require_owner
from src.lib.db import get_session
from src.lib.exceptions import (
    EpisodeConflictError,
    EpisodeValidationError,
    ImageValidationError,
)
from src.lib.uploads import R2_UNAVAILABLE, read_image_upload
from src.models.user import User
from src.models.work import Episode
from src.schemas.work import AdminEpisodeRead, EpisodeCreate, EpisodeImageUrl, EpisodeUpdate
from src.services import episode_service, r2_service, work_service
from src.services.image_service import MAX_IMAGES_PER_EPISODE, convert_to_webp
from src.services.r2_service import R2NotConfiguredError

router = APIRouter(prefix="/admin/works/{work_id}/episodes", tags=["admin-episodes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
OwnerDep = Annotated[User, Depends(require_owner)]

_WORK_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="작품을 찾을 수 없습니다"
)
_EPISODE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="에피소드를 찾을 수 없습니다"
)


async def _work_or_404(work_id: uuid.UUID, session: AsyncSession) -> None:
    if await work_service.get_work(work_id, session, with_tags=False) is None:
        raise _WORK_NOT_FOUND


async def _episode_or_404(
    work_id: uuid.UUID, episode_id: uuid.UUID, session: AsyncSession
) -> Episode:
    # get_episode가 Work join으로 soft-delete까지 거른다(삭제 작품의 에피소드 = 404).
    episode = await episode_service.get_episode(work_id, episode_id, session)
    if episode is None:
        raise _EPISODE_NOT_FOUND
    return episode


@router.post("", response_model=AdminEpisodeRead, status_code=status.HTTP_201_CREATED)
async def create_episode(
    work_id: uuid.UUID, body: EpisodeCreate, owner: OwnerDep, session: SessionDep
) -> Episode:
    """draft 생성(JSON, 이미지 없음). episode_no 중복은 이미지 업로드 전에 즉시 409."""
    await _work_or_404(work_id, session)
    try:
        return await episode_service.create_episode(work_id, body, session)
    except EpisodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{episode_id}/images", response_model=AdminEpisodeRead)
async def upload_episode_image(
    work_id: uuid.UUID,
    episode_id: uuid.UUID,
    image: UploadFile,
    owner: OwnerDep,
    session: SessionDep,
) -> Episode:
    """페이지 1장 업로드: 변환(D2) → R2(D1) → image_keys 끝에 원자 append.

    F3가 페이지 순서대로 반복 호출한다(진행바 = 장 단위). 실패한 장만 재시도하면
    되고, 최종 순서는 PUT 재배열로 조정 가능하다.
    """
    episode = await _episode_or_404(work_id, episode_id, session)
    # 싼 선검증(변환·업로드 비용 절약). 진짜 상한 보증은 append의 조건부 UPDATE가 담당 -
    # 여기서만 걸면 동시 요청 두 개가 49장 상태를 같이 읽고 51장이 되는 race가 남는다.
    if len(episode.image_keys) >= MAX_IMAGES_PER_EPISODE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"회차당 이미지는 최대 {MAX_IMAGES_PER_EPISODE}장입니다",
        )
    expected_len = len(episode.image_keys)
    # 읽기 트랜잭션 종료 - 변환(CPU 수 초)·R2 업로드(재시도 시 분 단위) 동안 DB
    # 커넥션을 잡아두지 않는다(리뷰 ⑨: idle-in-transaction 풀 고갈). rollback으로
    # episode ORM 객체가 만료되므로 이후 속성 접근 금지 - 필요한 값은 위에서 스냅샷.
    await session.rollback()
    try:
        data = await read_image_upload(image)
        webp = await convert_to_webp(data)
    except ImageValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    try:
        return await episode_service.append_image(work_id, episode_id, expected_len, webp, session)
    except EpisodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except R2NotConfiguredError as exc:
        raise R2_UNAVAILABLE from exc


@router.put("/{episode_id}", response_model=AdminEpisodeRead)
async def update_episode(
    work_id: uuid.UUID,
    episode_id: uuid.UUID,
    body: EpisodeUpdate,
    owner: OwnerDep,
    session: SessionDep,
) -> Episode:
    """메타 부분수정(JSON) + 페이지 재배열/삭제 + 썸네일 선택 + 공개(즉시/예약)."""
    episode = await _episode_or_404(work_id, episode_id, session)
    try:
        return await episode_service.update_episode(episode, body, session)
    except EpisodeValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except EpisodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    work_id: uuid.UUID, episode_id: uuid.UUID, owner: OwnerDep, session: SessionDep
) -> None:
    """회차 soft delete (#85). 공개 중인 회차도 지울 수 있고, 삭제와 동시에 공개가 풀린다.

    이미 삭제된 회차는 404다(_episode_or_404가 deleted_at을 본다) - DELETE를 멱등하게
    두지 않은 건 "지웠는데 204가 또 온다"보다 "그 회차는 이미 없다"가 관리자에게
    정확한 정보이기 때문. 되살리는 엔드포인트는 두지 않는다.
    """
    episode = await _episode_or_404(work_id, episode_id, session)
    try:
        await episode_service.soft_delete_episode(episode, session)
    except EpisodeConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("", response_model=list[AdminEpisodeRead])
async def list_episodes(work_id: uuid.UUID, owner: OwnerDep, session: SessionDep) -> list[Episode]:
    """episode_no 순 목록(삭제분 제외). image_keys 포함(F3 재배열 UI 소비)이라 상세 GET은 없다."""
    await _work_or_404(work_id, session)
    return list(await episode_service.list_episodes(work_id, session))


@router.get("/{episode_id}/image-urls", response_model=list[EpisodeImageUrl])
async def get_episode_image_urls(
    work_id: uuid.UUID, episode_id: uuid.UUID, owner: OwnerDep, session: SessionDep
) -> list[EpisodeImageUrl]:
    """업로드된 페이지의 presigned GET URL(image_keys 순서). 관리자 미리보기 전용.

    원래 M3(결제·잠금) 소관이던 GET 발급을 F3 업로드 화면(draft 재진입 미리보기·
    재배열·썸네일 선택)용으로 앞당김(2026-07-15). 매 요청 새로 발급하고 캐시하지
    않는다(backend/CLAUDE.md Signed URL 규칙).
    """
    episode = await _episode_or_404(work_id, episode_id, session)
    keys = list(episode.image_keys)
    try:
        urls = await r2_service.presign_get_urls(keys)
    except R2NotConfiguredError as exc:
        raise R2_UNAVAILABLE from exc
    return [EpisodeImageUrl(key=key, url=url) for key, url in zip(keys, urls, strict=True)]
