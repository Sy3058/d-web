"""뷰어 진행도 응답/요청 스키마 (M2 그룹 C1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    # #76 콘텐츠 모델 전환 이후 "문서 최상위 블록 인덱스"로 재해석된 값.
    # 실제 블록 수 기준 상한은 두지 않는다(content 로딩이 필요해 비용 대비 이득 없음 -
    # 과대값의 피해는 본인 진행도 복원 위치뿐이라 보안 영향 없음).
    # 단 INT4 상한은 필수: 컬럼이 4바이트 Integer라 초과 값은 드라이버(asyncpg)에서
    # DataError로 터져 422가 아니라 500이 된다(리뷰 실측 2026-07-20).
    page_no: int = Field(ge=0, le=2_147_483_647)


class ProgressRead(BaseModel):
    episode_id: uuid.UUID
    page_no: int
    updated_at: datetime
