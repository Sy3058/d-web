import uuid

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.payment_receipt import safe_receipt_url
from src.models.payment import PaymentOrder, Purchase, PurchaseStatus
from src.models.work import Episode, Work
from src.schemas.purchase import PurchaseHistoryItem, PurchaseHistoryRead
from src.services.episode_access_service import (
    EpisodeAccessScope,
    episode_access_columns,
    evaluate_episode_access,
)

PAGE_SIZE = 20


async def get_purchase_history(
    user_id: uuid.UUID, page: int, session: AsyncSession
) -> PurchaseHistoryRead:
    conditions = (Purchase.user_id == user_id, Purchase.environment == settings.payment_environment)
    total = (await session.exec(select(func.count(Purchase.id)).where(*conditions))).one()
    rows = (
        await session.exec(
            select(
                Purchase.id,
                PaymentOrder.payment_id,
                PaymentOrder.item_title,
                PaymentOrder.order_name,
                Purchase.amount,
                PaymentOrder.currency,
                Purchase.paid_at,
                Purchase.status,
                Purchase.first_viewed_at,
                Purchase.refunded_at,
                Purchase.refund_amount,
                PaymentOrder.receipt_url,
                Episode.id.label("episode_id"),
                Episode.public_id,
                Episode.deleted_at.label("episode_deleted_at"),
                Work.id.label("work_id"),
                Work.deleted_at.label("work_deleted_at"),
                *episode_access_columns(user_id),
            )
            .select_from(Purchase)
            .join(PaymentOrder, PaymentOrder.id == Purchase.payment_order_id)
            .outerjoin(Episode, Episode.id == Purchase.episode_id)
            .outerjoin(Work, Work.id == Episode.work_id)
            .where(*conditions)
            .order_by(Purchase.paid_at.desc(), Purchase.id.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    ).all()
    items = []
    for row in rows:
        viewer_path = None
        if (
            row.status == PurchaseStatus.ACTIVE
            and row.episode_id is not None
            and row.work_id is not None
            and row.episode_deleted_at is None
            and row.work_deleted_at is None
        ):
            access = evaluate_episode_access(
                episode_public=row.episode_public,
                work_public=row.work_public,
                content=row.content,
                image_keys=row.image_keys,
                active_purchase_id=row.active_purchase_id,
                viewed_at=row.viewed_at,
            ).access
            if access.scope == EpisodeAccessScope.FULL and access.purchase_id == row.id:
                viewer_path = f"/works/{row.work_id}/{row.public_id}"
        items.append(
            PurchaseHistoryItem(
                **{
                    key: row._mapping[key]
                    for key in PurchaseHistoryItem.model_fields
                    if key not in {"receipt_url", "viewer_path"}
                },
                receipt_url=safe_receipt_url(row.receipt_url),
                viewer_path=viewer_path,
            )
        )
    return PurchaseHistoryRead(items=items, total=total, page=page)
