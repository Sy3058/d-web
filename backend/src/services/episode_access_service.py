"""서버 내부의 회차 열람 범위 판정."""

import uuid
from dataclasses import dataclass
from enum import StrEnum

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


async def resolve_episode_access(
    user_id: uuid.UUID | None,
    episode_id: uuid.UUID,
    session: AsyncSession,
) -> EpisodeAccessResult:
    """최신 DB 컬럼으로 열람 범위를 판정하며 세션을 커밋하지 않는다.

    결과는 조회 시점의 스냅샷이다. 전문 발급 인가의 최종 보장이 아니며,
    발급 경로는 환불 등과 경합하는 최종 인가를 별도로 수행해야 한다.
    """
    purchase_id = (
        select(Purchase.id)
        .join(PaymentOrder, PaymentOrder.id == Purchase.payment_order_id)
        .join(User, User.id == Purchase.user_id)
        .where(
            Purchase.episode_id == Episode.id,
            Purchase.user_id == user_id,
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.environment == settings.payment_environment,
            PaymentOrder.environment == settings.payment_environment,
            PaymentOrder.user_id == Purchase.user_id,
            PaymentOrder.episode_id == Purchase.episode_id,
            User.deleted_at.is_(None),
        )
        .correlate(Episode)
        .scalar_subquery()
    )
    row = (
        await session.exec(
            select(
                Episode.is_published,
                Work.is_published,
                Episode.content,
                Episode.image_keys,
                purchase_id,
            )
            .join(Work, Work.id == Episode.work_id)
            .where(
                Episode.id == episode_id,
                Episode.deleted_at.is_(None),
                Work.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return EpisodeAccessResult(EpisodeAccessScope.UNAVAILABLE)

    episode_public, work_public, content, image_keys, active_purchase_id = row
    fallback = (
        EpisodeAccessScope.PREVIEW
        if episode_public and work_public
        else EpisodeAccessScope.UNAVAILABLE
    )
    if not isinstance(image_keys, list) or any(not isinstance(key, str) for key in image_keys):
        return EpisodeAccessResult(fallback)
    try:
        validate_content(content, set(image_keys))
    except EpisodeValidationError:
        return EpisodeAccessResult(fallback)
    if active_purchase_id is not None:
        return EpisodeAccessResult(EpisodeAccessScope.FULL, active_purchase_id)
    if episode_public and work_public and derive_is_free(content):
        return EpisodeAccessResult(EpisodeAccessScope.FULL)
    return EpisodeAccessResult(fallback)
