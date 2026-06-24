"""PaymentProvider ABC + shared types."""
from __future__ import annotations

import abc
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


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


class PaymentProvider(abc.ABC):
    """Abstract base for payment providers.

    Implementations:
    - create_payment(order) -> PaymentResult
    - verify_webhook(payload_bytes, signature) -> WebhookEvent
    - refund(order) -> bool
    - query(order) -> PaymentStatus
    """
    name: str = "base"

    @abc.abstractmethod
    def create_payment(self, order: Any) -> PaymentResult: ...

    @abc.abstractmethod
    def verify_webhook(self, payload: bytes,
                       signature: str) -> WebhookEvent: ...

    @abc.abstractmethod
    def refund(self, order: Any) -> bool: ...

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
    "PaymentProvider", "PaymentResult", "WebhookEvent", "PaymentStatus",
    "ProviderNotConfiguredError", "WebhookVerificationError",
]
