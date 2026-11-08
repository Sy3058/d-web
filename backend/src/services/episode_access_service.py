"""서버 내부의 회차 열람 범위 판정."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.content_doc import derive_is_free, validate_content
from src.lib.exceptions import EpisodeValidationError
from src.models.payment import PaymentOrder, Purchase, PurchaseStatus
from src.models.user import User
from src.models.work import Episode, Work


class EpisodeAccessScope(StrEnum):
    UNAVAILABLE = "unavailable"
    PREVIEW = "preview"
    FULL = "full"


@dataclass(frozen=True)
class EpisodeAccessResult:
    scope: EpisodeAccessScope
    purchase_id: uuid.UUID | None = None


@dataclass(frozen=True)
class EpisodeAccessSnapshot:
    """인가와 본문 투영이 공유하는 서버 내부 스냅샷. API 응답에 사용하지 않는다."""

    access: EpisodeAccessResult
    content: Any = None
    first_viewed_at: datetime | None = None


def active_purchase_query(user_id: uuid.UUID | None):
    """환경·주문 출처·활성 사용자 조건을 최종 발급 검사에서도 공유한다."""
    return (
        select(Purchase.id)
        .join(PaymentOrder, PaymentOrder.id == Purchase.payment_order_id)
        .join(User, User.id == Purchase.user_id)
        .where(
            Purchase.user_id == user_id,
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.environment == settings.payment_environment,
            PaymentOrder.environment == settings.payment_environment,
            PaymentOrder.user_id == Purchase.user_id,
            PaymentOrder.episode_id == Purchase.episode_id,
            User.deleted_at.is_(None),
        )
    )


def episode_access_columns(user_id: uuid.UUID | None):
    """메타·본문 조회가 같은 statement에서 읽을 중앙 권한 입력 컬럼."""
    purchase_id = (
        active_purchase_query(user_id)
        .where(Purchase.episode_id == Episode.id)
        .correlate(Episode)
        .scalar_subquery()
    )
    first_viewed_at = (
        active_purchase_query(user_id)
        .with_only_columns(Purchase.first_viewed_at)
        .where(Purchase.episode_id == Episode.id)
        .correlate(Episode)
        .scalar_subquery()
    )
    return (
        Episode.is_published.label("episode_public"),
        Work.is_published.label("work_public"),
        Episode.content.label("content"),
        Episode.image_keys.label("image_keys"),
        purchase_id.label("active_purchase_id"),
        first_viewed_at.label("viewed_at"),
    )


def evaluate_episode_access(
    *,
    episode_public: bool,
    work_public: bool,
    content: Any,
    image_keys: Any,
    active_purchase_id: uuid.UUID | None,
    viewed_at: datetime | None,
) -> EpisodeAccessSnapshot:
    """조회된 한 스냅샷만 평가한다. DB 조회나 발급 부작용은 없다."""
    fallback = (
        EpisodeAccessScope.PREVIEW
        if episode_public and work_public
        else EpisodeAccessScope.UNAVAILABLE
    )
    if not isinstance(image_keys, list) or any(not isinstance(key, str) for key in image_keys):
        return EpisodeAccessSnapshot(EpisodeAccessResult(fallback), content)
    try:
        validate_content(content, set(image_keys))
    except EpisodeValidationError:
        return EpisodeAccessSnapshot(EpisodeAccessResult(fallback), content)
    if active_purchase_id is not None:
        return EpisodeAccessSnapshot(
            EpisodeAccessResult(EpisodeAccessScope.FULL, active_purchase_id), content, viewed_at
        )
    if episode_public and work_public and derive_is_free(content):
        return EpisodeAccessSnapshot(EpisodeAccessResult(EpisodeAccessScope.FULL), content)
    return EpisodeAccessSnapshot(EpisodeAccessResult(fallback), content)


async def load_episode_access(
    user_id: uuid.UUID | None,
    episode_id: uuid.UUID,
    session: AsyncSession,
) -> EpisodeAccessSnapshot:
    """최신 컬럼을 한 SELECT로 읽고 그 문서에 대한 열람 범위를 판정한다."""
    row = (
        await session.exec(
            select(*episode_access_columns(user_id))
            .join(Work, Work.id == Episode.work_id)
            .where(
                Episode.id == episode_id,
                Episode.deleted_at.is_(None),
                Work.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return EpisodeAccessSnapshot(EpisodeAccessResult(EpisodeAccessScope.UNAVAILABLE))
    return evaluate_episode_access(**row._mapping)


async def resolve_episode_access(
    user_id: uuid.UUID | None,
    episode_id: uuid.UUID,
    session: AsyncSession,
) -> EpisodeAccessResult:
    """커밋 없이 판정 스냅샷을 반환한다. 전문 발급은 최종 인가가 별도로 필요하다."""
    return (await load_episode_access(user_id, episode_id, session)).access
