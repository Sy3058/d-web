"""뷰어 진행도·본문 응답/요청 스키마 (M2 그룹 C1, B2)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    # #76 콘텐츠 모델 전환 이후 "문서 최상위 블록 인덱스"로 재해석된 값.
    # 실제 블록 수 기준 상한은 두지 않는다(content 로딩이 필요해 비용 대비 이득 없음 -
    # 과대값의 피해는 본인 진행도 복원 위치뿐이라 보안 영향 없음).
    # 단 INT4 상한은 필수: 컬럼이 4바이트 Integer라 초과 값은 드라이버(asyncpg)에서
    # DataError로 터져 422가 아니라 500이 된다(리뷰 실측 2026-07-20).
    page_no: int = Field(ge=0, le=2_147_483_647)
    # 최상위 블록 내부의 상대 위치. 기본값은 신규 행의 블록 시작점이다. 기존 클라이언트가
    # 필드를 생략했는지는 model_fields_set으로 구분해 기존 정밀 위치를 덮어쓰지 않는다.
    block_offset_bp: int = Field(default=0, ge=0, le=10_000)


class ProgressRead(BaseModel):
    episode_id: uuid.UUID
    page_no: int
    block_offset_bp: int
    updated_at: datetime


class LastReadEpisode(BaseModel):
    id: uuid.UUID
    public_id: int
    title: str


class WorkProgressRead(BaseModel):
    read_episode_ids: list[uuid.UUID]
    last_episode: LastReadEpisode | None


class EpisodeContent(BaseModel):
    """무료 구간 본문 응답 (M2 B2). 회차 메타·네비는 GET /works/{id}(A2)가 담당한다."""

    episode_id: uuid.UUID
    # ⚠️ 저장 문서의 image 노드는 attrs={"key": R2키}지만 여기서는 attrs={"src": presigned
    # URL}이다. 저장 스키마는 "무엇을 받아들일까"(입력 검증·XSS 방어선, lib/content_doc),
    # 이 응답은 "무엇을 보여줄까"의 계약이라 원래 다르다 - R2 키는 내보낼 수 없고 뷰어는
    # URL 없이 렌더할 수 없다. 노드·마크 화이트리스트는 동일하므로 #76의 "서버·에디터·뷰어
    # 3곳 동일 스키마" 규칙에서 image attrs 하나만 의도적 예외다(뷰어 렌더러는 src 기준).
    content: dict[str, Any]
    # 응답만으로는 "원래 여기서 끝난 회차"와 "유료라 잘린 회차"가 구분되지 않는다. 절단은
    # 서버가 하고 잠금 placeholder를 띄울지는 이 플래그가 알려준다.
    has_paid_part: bool
