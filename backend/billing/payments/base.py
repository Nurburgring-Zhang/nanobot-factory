"""PaymentProvider ABC + shared types."""
from __future__ import annotations

import abc
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Union


class PaymentStatus(str):
    """Payment status enum-as-string (compatible with Pydantic)."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class ProviderNotConfiguredError(RuntimeError):
    """Raised when provider is not configured (missing API keys)."""


class WebhookVerificationError(ValueError):
    """Raised when webhook signature verification fails."""


class RefundValidationError(ValueError):
    """Raised when refund amount is invalid (non-positive, exceeds remaining, etc.)."""


@dataclass
class PaymentResult:
    """Result of create_payment() — provider returns redirect URL or QR."""
    payment_id: str             # provider-side ID (e.g. Stripe session id, alipay trade_no)
    checkout_url: str           # URL to redirect user to (Stripe Checkout / 支付宝收银台 / 微信二维码 URL)
    qr_code_url: Optional[str]  # for WeChat: 微信返回的 prepay_id 嵌入到二维码 URL
    status: str = "pending"     # PaymentStatus value
    expires_at: Optional[int] = None   # unix ts
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WebhookEvent:
    """Decoded webhook event."""
    event_id: str
    event_type: str             # "payment.success" / "payment.failed" / "refund.completed"
    order_id: str               # the internal order_id
    payment_id: str             # provider payment id
    amount_cents: int
    currency: str
    status: str
    created_at: int             # unix ts
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RefundResult:
    """Result of refund() — provider returns success status and refunded amount.

    Fields:
    - success:        True if refund was initiated successfully at provider side
    - refund_id:      provider-side refund ID (e.g. Stripe re_xxx, alipay refund_no)
    - amount_cents:   actual amount refunded in cents (== full order amount for full refund,
                      or == requested amount for partial refund)
    - is_partial:     True if this single refund operation did NOT consume the entire
                      remaining balance (i.e. order is left with positive remaining).
                      False if this refund exhausts remaining (== full).
    - remaining_cents: order.amount_cents - order.refunded_amount_cents AFTER this
                      refund completes (== 0 if this was a full refund).
    - message:        optional human-readable status
    - raw:            provider-specific raw response
    """
    success: bool
    refund_id: str
    amount_cents: int
    is_partial: bool
    remaining_cents: int = 0
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def to_refund_cents(amount: Optional[Union[int, float, str, Decimal]],
                    order_amount_cents: int,
                    already_refunded_cents: int = 0) -> int:
    """Normalize refund ``amount`` argument into integer cents.

    Rules:
    - amount is None or empty -> full refund = order_amount_cents - already_refunded_cents
    - amount is numeric       -> converted to cents; if amount < 1 cent, raises
    - amount may be a Decimal, int, float (interpreted as yuan/dollar, NOT cents),
      or string with optional currency suffix
    - already_refunded_cents is excluded from the refundable remaining.

    Raises RefundValidationError on:
    - amount <= 0
    - amount > remaining (order_amount_cents - already_refunded_cents)
    - amount cannot be parsed
    """
    if amount is None:
        remaining = order_amount_cents - already_refunded_cents
        if remaining <= 0:
            raise RefundValidationError(
                f"order already fully refunded (already_refunded={already_refunded_cents})"
            )
        return remaining
    # Parse amount -> Decimal (interpret as yuan/dollar, convert to cents)
    try:
        if isinstance(amount, Decimal):
            d = amount
        elif isinstance(amount, (int, float)):
            d = Decimal(str(amount))
        elif isinstance(amount, str):
            s = amount.strip()
            if not s:
                raise RefundValidationError("amount string is empty")
            d = Decimal(s)
        else:
            raise RefundValidationError(
                f"unsupported amount type: {type(amount).__name__}"
            )
    except (InvalidOperation, ValueError) as e:
        raise RefundValidationError(f"cannot parse amount {amount!r}: {e}") from e
    if d <= 0:
        raise RefundValidationError(f"refund amount must be > 0, got {d}")
    # Convert major units (yuan/dollar) -> cents. Use ROUND_HALF_UP to mirror payment logic.
    cents = int((d * Decimal(100)).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
    if cents <= 0:
        raise RefundValidationError(f"refund amount too small: {d} (< 0.01)")
    remaining = order_amount_cents - already_refunded_cents
    if cents > remaining:
        raise RefundValidationError(
            f"refund amount {cents} cents exceeds remaining {remaining} cents "
            f"(order={order_amount_cents}, already_refunded={already_refunded_cents})"
        )
    return cents


class PaymentProvider(abc.ABC):
    """Abstract base for payment providers.

    Implementations:
    - create_payment(order) -> PaymentResult
    - verify_webhook(payload_bytes, signature) -> WebhookEvent
    - refund(order, amount=None) -> RefundResult
        - amount=None  -> full refund (entire remaining amount)
        - amount=int|float|Decimal|str (major units, e.g. 9.99) -> partial refund
    - query(order) -> PaymentStatus

    Concrete implementations must validate ``amount`` via
    :func:`to_refund_cents` to ensure the requested amount does not
    exceed the order's remaining refundable balance.
    """
    name: str = "base"

    @abc.abstractmethod
    def create_payment(self, order: Any) -> PaymentResult: ...

    @abc.abstractmethod
    def verify_webhook(self, payload: bytes,
                       signature: str) -> WebhookEvent: ...

    @abc.abstractmethod
    def refund(self, order: Any,
               amount: Optional[Union[int, float, str, Decimal]] = None) -> RefundResult: ...

    @abc.abstractmethod
    def query(self, order: Any) -> str: ...

    # ── Shared helpers (concrete) ──────────────────────────────────────
    @staticmethod
    def compute_hmac_sha256(secret: str, message: str) -> str:
        """Standard HMAC-SHA256 hex digest."""
        return hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def constant_time_eq(a: str, b: str) -> bool:
        return hmac.compare_digest(a, b)

    @staticmethod
    def new_payment_id(prefix: str = "pay") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"


__all__ = [
    "PaymentProvider", "PaymentResult", "WebhookEvent", "RefundResult",
    "PaymentStatus",
    "ProviderNotConfiguredError", "WebhookVerificationError",
    "RefundValidationError",
    "to_refund_cents",
]
