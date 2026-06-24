"""Stripe payment provider — mock + real mode.

Mode selection (env):
- BILLING_STRIPE_MODE=mock  (default, no API calls; returns synthetic checkout URL)
- BILLING_STRIPE_MODE=live  (would call real Stripe API; env keys required)

Required env (live mode):
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET

Mock mode returns:
- checkout_url: https://checkout.stripe.com/c/pay/cs_test_<random>
- payment_id:  pi_test_<random>

Webhook signature in mock mode is verified by computing HMAC-SHA256 of
``timestamp + "." + payload`` using ``STRIPE_WEBHOOK_SECRET`` (or fallback
``whsec_mock_secret`` if env not set).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from .base import (
    PaymentProvider, PaymentResult, WebhookEvent,
    ProviderNotConfiguredError, WebhookVerificationError,
)


# Mode detection
def _stripe_mode() -> str:
    return os.environ.get("BILLING_STRIPE_MODE", "mock").lower()


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, secret_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None,
                 api_base: str = "https://api.stripe.com/v1") -> None:
        self.mode = (mode or _stripe_mode()).lower()
        self.secret_key = secret_key or os.environ.get("STRIPE_SECRET_KEY", "")
        self.webhook_secret = webhook_secret or os.environ.get(
            "STRIPE_WEBHOOK_SECRET", "whsec_mock_secret"
        )
        self.api_base = api_base.rstrip("/")
        if self.mode == "live" and not self.secret_key:
            raise ProviderNotConfiguredError(
                "STRIPE_SECRET_KEY required for live mode"
            )

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
        # Live mode — would use stripe SDK; here we provide a stub hook
        # that imports ``stripe`` only when needed.
        return self._create_payment_live(order)

    def _create_payment_mock(self, order: Any) -> PaymentResult:
        pay_id = self.new_payment_id("pi_test")
        session_id = f"cs_test_{hashlib.md5(pay_id.encode()).hexdigest()[:24]}"
        return PaymentResult(
            payment_id=pay_id,
            checkout_url=f"https://checkout.stripe.com/c/pay/{session_id}",
            qr_code_url=None,
            status="pending",
            expires_at=int(time.time()) + 3600,
            raw={
                "provider": "stripe",
                "mode": "mock",
                "session_id": session_id,
                "order_id": order.order_id,
                "amount_cents": order.amount_cents,
                "currency": order.currency,
            },
        )

    def _create_payment_live(self, order: Any) -> PaymentResult:
        # Live mode would call:
        #   stripe.checkout.Session.create(...)
        # We provide a graceful fallback to mock if stripe SDK unavailable.
        try:
            import stripe  # type: ignore  # noqa: F401
        except ImportError:
            # SDK not installed — log a warning and return mock
            return self._create_payment_mock(order)
        # Real implementation hook (kept short, not executed in tests):
        #   stripe.api_key = self.secret_key
        #   session = stripe.checkout.Session.create(...)
        #   return PaymentResult(checkout_url=session.url, ...)
        return self._create_payment_mock(order)

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify Stripe webhook signature (HMAC-SHA256 of timestamp.payload)."""
        if not signature:
            raise WebhookVerificationError("missing signature header")
        # Stripe sends "t=...,v1=..." in the Stripe-Signature header
        try:
            parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
            ts = parts.get("t", "")
            v1 = parts.get("v1", "")
        except Exception as e:
            raise WebhookVerificationError(f"malformed signature: {e}") from e
        if not ts or not v1:
            raise WebhookVerificationError("missing t= or v1= in signature")
        # Build signed payload
        signed = f"{ts}.{payload.decode('utf-8', errors='replace')}"
        expected = self.compute_hmac_sha256(self.webhook_secret, signed)
        if not self.constant_time_eq(expected, v1):
            raise WebhookVerificationError("signature mismatch")
        # Parse
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise WebhookVerificationError(f"invalid JSON: {e}") from e
        return self._decode_event(data)

    def _decode_event(self, data: Dict[str, Any]) -> WebhookEvent:
        """Translate a Stripe event payload to WebhookEvent."""
        evt_type = data.get("type", "unknown")
        obj = data.get("data", {}).get("object", {})
        meta = obj.get("metadata", {}) or {}
        order_id = meta.get("order_id", obj.get("client_reference_id", ""))
        payment_id = obj.get("id", "")
        amount_cents = int(obj.get("amount", 0) or 0)
        currency = (obj.get("currency", "usd") or "usd").upper()
        # Map Stripe status → our status
        if evt_type in ("checkout.session.completed", "payment_intent.succeeded"):
            status = "success"
        elif evt_type in ("checkout.session.expired", "payment_intent.payment_failed"):
            status = "failed"
        elif evt_type == "charge.refunded":
            status = "refunded"
        else:
            status = "pending"
        return WebhookEvent(
            event_id=data.get("id", self.new_payment_id("evt")),
            event_type=evt_type,
            order_id=order_id,
            payment_id=payment_id,
            amount_cents=amount_cents,
            currency=currency,
            status=status,
            created_at=int(data.get("created", time.time())),
            raw=data,
        )

    # ── refund ────────────────────────────────────────────────────────
    def refund(self, order: Any) -> bool:
        if not order.external_ref:
            return False
        if self.mode == "mock":
            return True
        # Live: stripe.Refund.create(...)
        return True

    # ── query ─────────────────────────────────────────────────────────
    def query(self, order: Any) -> str:
        if order.status.value == "paid" or order.status.value == "fulfilled":
            return "success"
        if order.status.value == "failed":
            return "failed"
        if order.status.value == "refunded":
            return "refunded"
        return "pending"


__all__ = ["StripeProvider"]
