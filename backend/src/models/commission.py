"""커미션 카드·사이트 문구 모델 (M2 그룹 G, 2026-07-29 카드 모델 확정).

크레페식 커미션 홍보 카드(제목·가격·기간·샘플 이미지·슬롯 마감)와 작가가 admin에서
편집하는 사이트 문구(랜딩 소개·커미션 유의사항). 본문은 TipTap 문서가 아니라 플레인
텍스트(줄바꿈만) - 구조 표현은 카드 필드가 담당한다(DECISIONS "랜딩 페이지 구성 +
커미션 단계 분리"). 신청 폼·접수 관리는 M5 - 이 모델은 홍보 표시 전용이라 결제·주문과
무관하다(price_text가 자유 문자열인 이유 - "50,000원~"·"오마카세" 표기 허용).

샘플 이미지는 원고(dweb)가 아니라 **공개 버킷(dweb-cover)** 에 올린다 - 커미션 예시는
의도적으로 공개하는 미끼 자산이라 표지·썸네일과 같은 부류다(M2 결정 2). 키는
`commission/{item_id}/{uuid4hex}.webp`(r2_service.commission_sample_key).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlmodel import Field, SQLModel


class CommissionItem(SQLModel, table=True):
    """커미션 카드 1종(예: "두상~전신 일러스트").

    works와 달리 soft delete가 없다 - 참조하는 자식 테이블·독자 URL이 없어 하드
    삭제로 충분하다(M5 신청 폼이 생기면 그쪽 설계에서 재검토). 삭제 시 샘플 이미지는
    커밋 성공 후 공개 버킷에서 정리한다(commission_service - D2 삭제 순서 패턴).
    """

    __tablename__ = "commission_items"
    # UPDATE에도 RETURNING으로 서버 계산 컬럼(onupdate updated_at)을 받는다
    # (models/work.py와 동일 - 만료 컬럼 MissingGreenlet 함정 예방).
    __mapper_args__ = {"eager_defaults": True}

    id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PgUUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
    )
    title: str = Field(sa_column=Column(String(200), nullable=False))
    # 플레인 텍스트(줄바꿈 보존, 마크업 없음) - FE가 텍스트 노드로만 렌더한다.
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # 표시 전용 자유 문자열. 숫자 컬럼이 아닌 이유: 커미션은 사이트 결제 대상이
    # 아니고(M5도 이메일 접수) 범위·협의 표기가 필요하다.
    price_text: str = Field(sa_column=Column(String(100), nullable=False))
    duration_text: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    # 업로드 매니페스트 겸 표시 순서(episodes.image_keys와 달리 배열 순서가 곧 표시
    # 순서다 - 카드에는 별도 콘텐츠 문서가 없어 순서의 진실이 여기뿐이다).
    sample_image_keys: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    # 크레페식 슬롯 상태(열림/마감). 마감이어도 카드는 노출한다(마감 배지 - 수요 표시).
    is_open: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    # 공개 목록 정렬 키(오름차순). 생성 시 서버가 max+1, 재배열은 컬렉션 PUT이 1..N으로 갱신한다.
    sort_order: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class SiteTextKey(StrEnum):
    """사이트 문구 슬롯. VARCHAR(50) 저장 + 앱 enum 검증(네이티브 PG enum 아님 -
    MISTAKES StrEnum 패턴). 슬롯 추가는 멤버만 늘리면 되고 마이그레이션이 없다.
    후보: 약관·개인정보처리방침(M7 법무 문서 - 같은 모양이라 여기로 흡수 가능).
    """

    LANDING_INTRO = "landing_intro"  # 랜딩 히어로 옆 작가 소개
    COMMISSION_NOTES = "commission_notes"  # /commission 하단 유의사항·신청 방법


class SiteText(SQLModel, table=True):
    """작가가 admin에서 편집하는 플레인 텍스트 문구. key = 자연키(SiteTextKey 값).

    행은 시딩하지 않는다 - admin GET이 행 없음을 빈 body로 응답하고 PUT이 upsert한다
    (첫 편집 진입이 404로 막히지 않게 - 계획 v2 시딩 규약).
    """

    __tablename__ = "site_texts"
    __mapper_args__ = {"eager_defaults": True}

    key: str = Field(sa_column=Column(String(50), primary_key=True))
    body: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
