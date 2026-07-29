"""커미션 카드·사이트 문구 서비스 (M2 그룹 G).

카드 CRUD + 샘플 이미지 원자 append + 사이트 문구 upsert. 검증·순서 결정은
episode_service의 확정 패턴을 따른다(조건부 UPDATE append·R2 먼저·삭제는 커밋 후).
다른 점은 버킷 하나 - 샘플은 원고(dweb)가 아니라 **공개 버킷(dweb-cover)** 에 올린다
(커미션 예시는 의도적 공개 자산 - M2 결정 2 부류, models/commission.py docstring).
동시성 정책은 last-write-wins(작가 1인 - 계획 v2 확정). 샘플 append만 조건부 UPDATE로
원자화한다 - 덮어쓰기는 되돌릴 수 있지만 매니페스트 유실 키는 미참조 파일로 남기 때문.
"""

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.exceptions import CommissionConflictError, CommissionValidationError
from src.models.commission import CommissionItem, SiteText, SiteTextKey
from src.schemas.commission import (
    CommissionItemCreate,
    CommissionItemUpdate,
    PublicCommissionItem,
)
from src.services import r2_service

logger = structlog.get_logger(__name__)

# 카드당 샘플 이미지 상한. 회차(50장)와 달리 홍보 카드라 소수면 충분하다 -
# 더 필요하면 카드를 나누는 게 맞다(카드 = 커미션 1종).
MAX_SAMPLES_PER_ITEM = 10

_STALE_ITEM = "커미션 카드가 다른 요청으로 먼저 변경되었습니다 - 새로고침 후 다시 시도하세요"


async def list_items(session: AsyncSession) -> Sequence[CommissionItem]:
    """admin·공개 공용 목록. sort_order 오름차순(동률은 등록순 - 안정 정렬)."""
    result = await session.exec(
        select(CommissionItem).order_by(CommissionItem.sort_order, CommissionItem.created_at)
    )
    return result.all()


async def get_item(item_id: uuid.UUID, session: AsyncSession) -> CommissionItem | None:
    return await session.get(CommissionItem, item_id)


async def create_item(body: CommissionItemCreate, session: AsyncSession) -> CommissionItem:
    item = CommissionItem(**body.model_dump())
    session.add(item)
    await session.commit()
    return item


def _validate_samples(current: list[str], new: list[str]) -> None:
    """재배열 = 기존 키의 **중복 없는 부분집합**(episode_service._validate_reorder와
    같은 규칙 - 순서 자유, 삭제 허용, 주입·복제 금지)."""
    if len(new) != len(set(new)):
        raise CommissionValidationError("sample_image_keys에 중복 키가 있습니다")
    if not set(new) <= set(current):
        raise CommissionValidationError("sample_image_keys에 이 카드의 키가 아닌 값이 있습니다")


async def _cleanup_public_samples(keys: Sequence[str]) -> None:
    """공개 버킷의 샘플 객체 정리(베스트 에포트). DB 커밋 **성공 후**에만 호출할 것.

    한 장 실패가 나머지 정리를 막지 않게 개별 로깅 후 계속한다 - 잔재는 무해한
    미참조 파일(orphan)이고, 실패를 삼키지 않고 로그로 남긴다(관측성 - MISTAKES
    "리뷰 수정의 비용" 항목).
    """
    for key in keys:
        try:
            await r2_service.delete_object(key, bucket=settings.r2_public_bucket)
        except Exception:  # noqa: BLE001 - 정리 실패는 요청 실패가 아니다(커밋 이미 성공)
            # exc_info로 원인까지 남긴다(episode_service:408과 동일) - 키만 남기면
            # "이미 없는 객체(정상)"와 "권한 상실(장애)"이 로그에서 구분 불가.
            logger.warning("commission_sample_cleanup_failed", key=key, exc_info=True)


async def update_item(
    item: CommissionItem, body: CommissionItemUpdate, session: AsyncSession
) -> CommissionItem:
    """부분 수정. sample_image_keys 축소로 빠진 키는 커밋 성공 후 공개 버킷에서 지운다."""
    changes = body.model_dump(exclude_unset=True)
    removed: list[str] = []
    if "sample_image_keys" in changes:
        new_keys: list[str] = changes["sample_image_keys"]
        _validate_samples(item.sample_image_keys, new_keys)
        kept = set(new_keys)
        removed = [key for key in item.sample_image_keys if key not in kept]
    for name, value in changes.items():
        setattr(item, name, value)
    await session.commit()
    await _cleanup_public_samples(removed)
    return item


async def delete_item(item: CommissionItem, session: AsyncSession) -> None:
    """하드 삭제(자식 테이블·독자 URL 없음 - models/commission.py docstring).
    샘플 객체는 커밋 성공 후 정리."""
    keys = list(item.sample_image_keys)
    await session.delete(item)
    await session.commit()
    await _cleanup_public_samples(keys)


async def append_sample_image(
    item_id: uuid.UUID, expected_len: int, webp: bytes, session: AsyncSession
) -> CommissionItem:
    """변환 완료된 WebP 1장을 공개 버킷에 올리고 sample_image_keys 끝에 원자 append.

    호출자(라우터)는 카드 존재 확인 후 읽기 트랜잭션을 닫고(rollback) 변환까지 마친 뒤
    진입한다(admin_episodes 업로드와 같은 근거 - 변환·R2 왕복 동안 커넥션 미점유).
    """
    key = r2_service.commission_sample_key(item_id)
    await r2_service.upload_bytes(key, webp, bucket=settings.r2_public_bucket)

    # episode_service.append_image와 동일: 조건부 UPDATE 하나로 append와 상한을 원자화 -
    # 길이 기대값이 어긋나면 0행 매칭이라 check-then-act race가 없다.
    result = await session.exec(
        update(CommissionItem)
        .where(
            CommissionItem.id == item_id,
            func.jsonb_array_length(CommissionItem.sample_image_keys) == expected_len,
            func.jsonb_array_length(CommissionItem.sample_image_keys) < MAX_SAMPLES_PER_ITEM,
        )
        .values(
            sample_image_keys=CommissionItem.sample_image_keys.op("||")(func.jsonb_build_array(key))
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise CommissionConflictError(_STALE_ITEM)
    await session.commit()

    item = await session.get(CommissionItem, item_id)
    if item is None:
        # UPDATE 성공 직후 소실 = 동시 삭제 계열 - 방어적 충돌 처리(append_image와 동일)
        raise CommissionConflictError(_STALE_ITEM)
    return item


# ── 공개 조회 ─────────────────────────────────────────────────────────────────


def _to_public_item(item: CommissionItem) -> PublicCommissionItem:
    # public_asset_base_url 미설정(dev 초기)이면 public_url이 None - URL 없는 카드로
    # 조용히 접는다(빈 배열). 키 문자열은 내보내지 않는다(schemas/commission.py docstring).
    urls = [
        url
        for url in (r2_service.public_url(key) for key in item.sample_image_keys)
        if url is not None
    ]
    return PublicCommissionItem(
        id=item.id,
        title=item.title,
        description=item.description,
        price_text=item.price_text,
        duration_text=item.duration_text,
        sample_image_urls=urls,
        is_open=item.is_open,
    )


async def list_public_items(session: AsyncSession) -> list[PublicCommissionItem]:
    """독자용 카드 목록. 마감(is_open=false) 카드도 포함한다 - 마감 배지 표시(크레페식)."""
    return [_to_public_item(item) for item in await list_items(session)]


# ── 사이트 문구 ───────────────────────────────────────────────────────────────


async def get_site_text(key: SiteTextKey, session: AsyncSession) -> SiteText | None:
    return await session.get(SiteText, key.value)


async def upsert_site_text(key: SiteTextKey, body: str, session: AsyncSession) -> SiteText:
    """문구 upsert(행 없으면 생성). progress_service와 같은 ON CONFLICT 단일 문장 -
    check-then-insert로 갈라 쓰면 동시 첫 저장 두 건이 PK 충돌 500을 낸다.

    updated_at을 SET절에 명시하는 이유: onupdate=func.now()는 일반 UPDATE에만 발동하고
    ON CONFLICT DO UPDATE에는 적용되지 않는다(study postgres-upsert-onupdate-trap).
    """
    stmt = pg_insert(SiteText).values(key=key.value, body=body)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SiteText.key],
        set_={"body": stmt.excluded.body, "updated_at": func.now()},
    ).returning(SiteText)

    result = await session.exec(stmt)
    row = result.scalars().one()
    await session.commit()
    return row
