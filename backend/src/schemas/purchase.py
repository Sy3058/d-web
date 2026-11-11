import uuid
from datetime import datetime

from pydantic import BaseModel

from src.models.payment import PurchaseStatus


class PurchaseHistoryItem(BaseModel):
    id: uuid.UUID
    payment_id: str
    item_title: str
    order_name: str
    amount: int
    currency: str
    paid_at: datetime
    status: PurchaseStatus
    first_viewed_at: datetime | None
    refunded_at: datetime | None
    refund_amount: int | None
    receipt_url: str | None
    viewer_path: str | None


class PurchaseHistoryRead(BaseModel):
    items: list[PurchaseHistoryItem]
    total: int
    page: int
    page_size: int = 20
