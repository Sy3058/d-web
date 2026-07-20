"""공개 회차 본문 라우터 (M2 그룹 B2). 인증 불요 - 무료 구간은 비로그인 열람이다.

routers/progress.py도 prefix가 /episodes지만 그쪽은 인증 필수라 파일을 나눈다 - 인증
유무가 정반대인 라우트를 한 파일에 섞으면 Depends 누락이 눈에 띄지 않는다.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.db import get_session
from src.schemas.viewer import EpisodeContent
from src.services import episode_read_service

router = APIRouter(prefix="/episodes", tags=["episodes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# 미공개·숨긴 작품의 회차도 403이 아니라 404다. 403은 "있긴 한데 못 준다"는 뜻이라
# 회차 ID를 대입해보는 것만으로 아직 공개하지 않은 회차·숨긴 작품의 존재가 확인된다.
#
# headers로 no-store를 직접 싣는 이유: HTTPException이 발생하면 라우터 함수의 Response
# 객체가 아니라 예외 핸들러가 만든 새 응답이 나가므로, 성공 경로에 붙인 헤더가 404엔
# 적용되지 않는다. 404는 명세상 기본 캐시 가능 상태 코드라(RFC 9111) 명시가 없으면
# heuristic 캐싱 대상이 되고, 예약 공개 전에 열어본 독자가 공개 후에도 캐시된 404를 본다.
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="회차를 찾을 수 없습니다",
    headers={"Cache-Control": "no-store"},
)


@router.get("/{episode_id}/content", response_model=EpisodeContent)
async def get_episode_content(
    episode_id: uuid.UUID, session: SessionDep, response: Response
) -> EpisodeContent:
    """무료 구간 본문(유료 경계 이전)을 presigned URL로 치환해 반환한다."""
    content = await episode_read_service.get_free_content(episode_id, session)
    if content is None:
        raise _NOT_FOUND
    # 본문 image src가 presigned URL이라 중간 캐시·브라우저에 남으면 만료(600초) 전까지
    # 다른 사람이 그 URL로 원고를 받는다. presigned는 어디서도 캐시 금지(DECISIONS).
    response.headers["Cache-Control"] = "no-store"
    return content
