import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EpisodePaymentMethod(StrEnum):
    CARD = "card"
    KAKAOPAY = "kakaopay"
    TOSSPAY = "tosspay"


class EpisodePaymentIntentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: uuid.UUID
    expected_amount: int = Field(strict=True, gt=0, le=2_147_483_647)
    payment_method: EpisodePaymentMethod
    checkout_notice_version: str = Field(min_length=1, max_length=32)
    immediate_supply_consented: bool = Field(strict=True)


class EpisodePaymentIntentRead(BaseModel):
    payment_id: str
    store_id: str
    channel_key: str
    order_name: str
    total_amount: int
    currency: str
    pay_method: str
    notice_version: str
    expires_at: datetime
    reused: bool


class CheckoutChangedDetail(BaseModel):
    code: str = "checkout_changed"
    episode_id: uuid.UUID
    item_title: str
    total_amount: int
    currency: str = "KRW"
    notice_version: str
