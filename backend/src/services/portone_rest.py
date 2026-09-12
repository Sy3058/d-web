"""PortOne V2 비동기 REST adapter.

네트워크 I/O는 httpx.AsyncClient만 사용한다. GET 결제 조회만 제한적으로 한 번
재시도하고 pre-register와 cancel 같은 write는 호출자 동의 없이 재시도하지 않는다.
반환값은 동기화에 필요한 allowlist 필드만 가지며 원시 응답과 고객 정보는 보존하지 않는다.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from src.models.payment import PaymentCancelReason

PORTONE_V2_BASE_URL = "https://api.portone.io"
PORTONE_TIMEOUT = httpx.Timeout(connect=5.0, read=65.0, write=10.0, pool=5.0)
_GET_RETRYABLE_STATUS = {429}
_PAYMENT_NOT_FOUND_ERROR_TYPE = "PAYMENT_NOT_FOUND"
_IDEMPOTENCY_OUTSTANDING_ERROR_TYPE = "IDEMPOTENCY_OUTSTANDING_REQUEST"


class PortOneMoneyState(StrEnum):
    READY = "READY"
    PENDING = "PENDING"
    VIRTUAL_ACCOUNT_ISSUED = "VIRTUAL_ACCOUNT_ISSUED"
    PAY_PENDING = "PAY_PENDING"
    FAILED = "FAILED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    PARTIAL_CANCELLED = "PARTIAL_CANCELLED"
    UNKNOWN = "UNKNOWN"


class PortOneCancellationState(StrEnum):
    REQUESTED = "REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PortOneAdapterError(RuntimeError):
    """Secret, 원시 body와 개인정보를 포함하지 않는 adapter 오류."""


class PortOneNotConfiguredError(PortOneAdapterError):
    pass


class PortOneTransportError(PortOneAdapterError):
    pass


class PortOneProtocolError(PortOneAdapterError):
    pass


class PortOneApiError(PortOneAdapterError):
    def __init__(self, status_code: int, error_type: str, *, retryable: bool) -> None:
        self.status_code = status_code
        self.error_type = error_type
        self.retryable = retryable
        super().__init__(f"PortOne API request failed: {status_code} {error_type}")


def _string(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    return value


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _money_state(provider_status: str | None) -> PortOneMoneyState:
    try:
        return PortOneMoneyState(provider_status)
    except (TypeError, ValueError):
        return PortOneMoneyState.UNKNOWN


def _cancellation_state(provider_status: str | None) -> PortOneCancellationState:
    try:
        return PortOneCancellationState(provider_status)
    except (TypeError, ValueError):
        return PortOneCancellationState.UNKNOWN


@dataclass(frozen=True, slots=True)
class PortOnePaymentSnapshot:
    money_state: PortOneMoneyState
    provider_status: str | None
    payment_id: str | None
    transaction_id: str | None
    store_id: str | None
    channel_type: str | None
    channel_key: str | None
    pg_provider: str | None
    total_amount: int | None
    currency: str | None
    order_name: str | None
    payment_method: str | None
    easy_pay_provider: str | None
    receipt_url: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None

    @classmethod
    def from_payload(cls, payload: Any) -> "PortOnePaymentSnapshot":
        data = _mapping(payload)
        channel = _mapping(data.get("channel"))
        amount = _mapping(data.get("amount"))
        method = _mapping(data.get("method"))
        provider_status = _string(data.get("status"), limit=40)
        return cls(
            money_state=_money_state(provider_status),
            provider_status=provider_status,
            payment_id=_string(data.get("id"), limit=64),
            transaction_id=_string(data.get("transactionId"), limit=255),
            store_id=_string(data.get("storeId"), limit=255),
            channel_type=_string(channel.get("type"), limit=8),
            channel_key=_string(channel.get("key"), limit=255),
            pg_provider=_string(channel.get("pgProvider"), limit=40),
            total_amount=_integer(amount.get("total")),
            currency=_string(data.get("currency"), limit=3),
            order_name=_string(data.get("orderName"), limit=255),
            payment_method=_string(method.get("type"), limit=40),
            easy_pay_provider=_string(method.get("provider"), limit=40),
            receipt_url=_string(data.get("receiptUrl"), limit=2048),
            paid_at=_datetime(data.get("paidAt")),
            cancelled_at=_datetime(data.get("cancelledAt")),
        )


@dataclass(frozen=True, slots=True)
class PortOneCancelRequest:
    """DB에 exact JSON snapshot으로 저장할 개인정보 없는 전액 취소 요청."""

    store_id: str
    reason: PaymentCancelReason
    amount: int
    current_cancellable_amount: int
    requester: str = "ADMIN"

    def __post_init__(self) -> None:
        if not self.store_id:
            raise ValueError("store_id is required")
        try:
            reason = PaymentCancelReason(self.reason)
        except (TypeError, ValueError):
            raise ValueError("reason must be an allowed payment cancel reason") from None
        object.__setattr__(self, "reason", reason)
        if self.amount <= 0:
            raise ValueError("amount must be positive")
        if self.current_cancellable_amount <= 0:
            raise ValueError("current_cancellable_amount must be positive")
        if self.amount != self.current_cancellable_amount:
            raise ValueError("full cancellation amounts must match")
        if self.requester not in {"CUSTOMER", "ADMIN"}:
            raise ValueError("requester must be CUSTOMER or ADMIN")
        expected_requester = (
            "CUSTOMER" if reason is PaymentCancelReason.CUSTOMER_REFUND else "ADMIN"
        )
        if self.requester != expected_requester:
            raise ValueError("requester does not match payment cancel reason")

    def snapshot(self) -> dict[str, str | int]:
        return {
            "storeId": self.store_id,
            "reason": self.reason,
            "amount": self.amount,
            "currentCancellableAmount": self.current_cancellable_amount,
            "requester": self.requester,
        }


@dataclass(frozen=True, slots=True)
class PortOneCancellationSnapshot:
    state: PortOneCancellationState
    provider_status: str | None
    cancellation_id: str | None
    total_amount: int | None
    cancelled_at: datetime | None
    receipt_url: str | None

    @classmethod
    def from_payload(cls, payload: Any) -> "PortOneCancellationSnapshot":
        data = _mapping(payload)
        provider_status = _string(data.get("status"), limit=40)
        return cls(
            state=_cancellation_state(provider_status),
            provider_status=provider_status,
            cancellation_id=_string(data.get("id"), limit=255),
            total_amount=_integer(data.get("totalAmount")),
            cancelled_at=_datetime(data.get("cancelledAt")),
            receipt_url=_string(data.get("receiptUrl"), limit=2048),
        )


def quote_idempotency_key(value: str) -> str:
    """PortOne의 16~256 ASCII 계약을 검증하고 RFC 8941 문자열로 인코딩한다."""
    if not 16 <= len(value) <= 256:
        raise ValueError("idempotency key must be between 16 and 256 characters")
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise ValueError("idempotency key must contain printable ASCII only")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class PortOneRestAdapter:
    def __init__(
        self,
        api_secret: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        secret = api_secret.get_secret_value()
        if not secret:
            raise PortOneNotConfiguredError("PortOne V2 API secret is not configured")
        self._sleep = sleep
        self._jitter = jitter
        self._client = httpx.AsyncClient(
            base_url=PORTONE_V2_BASE_URL,
            headers={"Authorization": f"PortOne {secret}"},
            timeout=PORTONE_TIMEOUT,
            transport=transport,
        )

    async def __aenter__(self) -> "PortOneRestAdapter":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def pre_register_payment(
        self,
        *,
        payment_id: str,
        store_id: str,
        total_amount: int,
        currency: str = "KRW",
    ) -> None:
        await self._request(
            "POST",
            f"/payments/{quote(payment_id, safe='')}/pre-register",
            json={
                "storeId": store_id,
                "totalAmount": total_amount,
                "currency": currency,
            },
        )

    async def get_payment(self, payment_id: str) -> PortOnePaymentSnapshot | None:
        response = await self._request(
            "GET",
            f"/payments/{quote(payment_id, safe='')}",
            not_found_is_none=True,
        )
        if response is None:
            return None
        return PortOnePaymentSnapshot.from_payload(self._json(response))

    async def cancel_payment(
        self,
        *,
        payment_id: str,
        idempotency_key: str,
        request: PortOneCancelRequest,
    ) -> PortOneCancellationSnapshot:
        response = await self._request(
            "POST",
            f"/payments/{quote(payment_id, safe='')}/cancel",
            headers={"Idempotency-Key": quote_idempotency_key(idempotency_key)},
            json=request.snapshot(),
        )
        assert response is not None
        body = _mapping(self._json(response))
        return PortOneCancellationSnapshot.from_payload(body.get("cancellation"))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        not_found_is_none: bool = False,
        **kwargs: Any,
    ) -> httpx.Response | None:
        is_retryable_get = method == "GET"
        for attempt in range(2):
            try:
                response = await self._client.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                if is_retryable_get and attempt == 0:
                    await self._retry_delay()
                    continue
                raise PortOneTransportError("PortOne connection failed") from None
            except httpx.TimeoutException:
                raise PortOneTransportError("PortOne request timed out") from None
            except httpx.HTTPError:
                raise PortOneTransportError("PortOne request failed") from None

            if not_found_is_none and response.status_code == 404:
                error = self._api_error(response)
                if error.error_type == _PAYMENT_NOT_FOUND_ERROR_TYPE:
                    return None
                raise error
            if (
                is_retryable_get
                and attempt == 0
                and (
                    response.status_code in _GET_RETRYABLE_STATUS
                    or 500 <= response.status_code <= 599
                )
            ):
                await self._retry_delay()
                continue
            if not response.is_success:
                raise self._api_error(response)
            return response
        raise AssertionError("unreachable")

    async def _retry_delay(self) -> None:
        await self._sleep(self._jitter(0.05, 0.15))

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise PortOneProtocolError("PortOne returned invalid JSON") from None

    @staticmethod
    def _api_error(response: httpx.Response) -> PortOneApiError:
        error_type = "UNKNOWN_ERROR"
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, Mapping):
            candidate = body.get("type")
            if (
                isinstance(candidate, str)
                and 1 <= len(candidate) <= 80
                and all(
                    character.isascii() and (character.isalnum() or character == "_")
                    for character in candidate
                )
            ):
                error_type = candidate
        return PortOneApiError(
            response.status_code,
            error_type,
            retryable=(
                response.status_code == 429
                or 500 <= response.status_code <= 599
                or (
                    response.status_code == 409
                    and error_type == _IDEMPOTENCY_OUTSTANDING_ERROR_TYPE
                )
            ),
        )
