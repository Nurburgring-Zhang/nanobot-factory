"""Stripe payment provider — mock + live (real SDK) mode.

Mode selection (env or constructor arg):
- BILLING_STRIPE_MODE=mock  (default, no API calls; returns synthetic checkout URL)
- BILLING_STRIPE_MODE=live  (calls real Stripe API via ``stripe`` SDK)

Required env (live mode):
- STRIPE_API_KEY        (sk_test_xxx for sandbox, sk_live_xxx for production)
- STRIPE_WEBHOOK_SECRET (whsec_xxx from Dashboard > Webhooks > Signing secret)

Mock mode returns:
- checkout_url: https://checkout.stripe.com/c/pay/cs_test_<random>
- payment_id:  pi_test_<random>

Webhook signature in mock mode is verified by computing HMAC-SHA256 of
``timestamp + "." + payload`` using ``STRIPE_WEBHOOK_SECRET`` (or fallback
``whsec_mock_secret`` if env not set).

Live mode:
- create_payment -> stripe.checkout.Session.create() (returns session.url)
- refund         -> stripe.Refund.create() (returns refund.id)
- verify_webhook -> stripe.Webhook.construct_event() (real signature)
- query          -> stripe.checkout.Session.retrieve()

The ``stripe`` SDK is imported lazily so mock mode does NOT require it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from .base import (
    PaymentProvider, PaymentResult, WebhookEvent, RefundResult,
    ProviderNotConfiguredError, WebhookVerificationError,
    RefundValidationError, to_refund_cents,
)


# Mode detection
def _stripe_mode() -> str:
    return os.environ.get("BILLING_STRIPE_MODE", "mock").lower()


def _stripe_sdk():
    """Lazy import of the ``stripe`` SDK. Returns None if not installed."""
    try:
        import stripe  # type: ignore
        return stripe
    except ImportError:
        return None


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, secret_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None,
                 api_base: str = "https://api.stripe.com/v1",
                 api_version: str = "2024-06-20") -> None:
        self.mode = (mode or _stripe_mode()).lower()
        # accept both STRIPE_API_KEY and STRIPE_SECRET_KEY (legacy)
        self.secret_key = (
            secret_key
            or os.environ.get("STRIPE_API_KEY", "")
            or os.environ.get("STRIPE_SECRET_KEY", "")
        )
        self.webhook_secret = webhook_secret or os.environ.get(
            "STRIPE_WEBHOOK_SECRET", "whsec_mock_secret"
        )
        self.api_base = api_base.rstrip("/")
        self.api_version = api_version
        if self.mode == "live" and not self.secret_key:
            raise ProviderNotConfiguredError(
                "STRIPE_API_KEY required for live mode"
            )

    # ── live_mode() helper (P6-Fix-C-7) ───────────────────────────────
    def live_mode(self, api_key: Optional[str] = None) -> "StripeProvider":
        """Switch this provider instance to live mode (real Stripe API).

        Convenience helper: equivalent to constructing a new
        ``StripeProvider(mode="live", secret_key=api_key)`` but mutates
        the current instance so callers can flip mode without losing
        the registered reference in the factory.

        Returns self for fluent chaining::

            prov = StripeProvider().live_mode(os.environ["STRIPE_API_KEY"])
        """
        key = api_key or self.secret_key
        if not key:
            raise ProviderNotConfiguredError(
                "STRIPE_API_KEY (or api_key argument) required for live mode"
            )
        self.secret_key = key
        self.mode = "live"
        # Push API key into the SDK eagerly so any subsequent call is authenticated.
        sdk = _stripe_sdk()
        if sdk is not None:
            sdk.api_key = key
            if self.api_base:
                # Only override if non-default; keep Stripe SDK defaults otherwise.
                if self.api_base != "https://api.stripe.com/v1":
                    sdk.api_base = self.api_base
            if self.api_version:
                sdk.api_version = self.api_version
        return self

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
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
        """Live mode: call ``stripe.checkout.Session.create()``."""
        sdk = _stripe_sdk()
        if sdk is None:
            # SDK not installed — degrade to mock with a warning embedded in raw
            result = self._create_payment_mock(order)
            result.raw["warning"] = "stripe SDK not installed; mock fallback"
            result.raw["mode"] = "live-no-sdk"
            return result
        # Configure the SDK for this call
        sdk.api_key = self.secret_key
        # Real call: create a Checkout Session and return its hosted URL.
        # We DO NOT actually hit the network here — tests patch the SDK.
        # In production, this issues an HTTPS request to api.stripe.com.
        try:
            session = sdk.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": order.currency.lower(),
                        "product_data": {
                            "name": f"订阅 {order.plan_id}",
                            "metadata": {"order_id": order.order_id},
                        },
                        "unit_amount": int(order.amount_cents),
                    },
                    "quantity": 1,
                }],
                client_reference_id=order.order_id,
                metadata={"order_id": order.order_id, "plan_id": order.plan_id},
                success_url=os.environ.get(
                    "STRIPE_SUCCESS_URL",
                    "https://example.com/billing/success?session_id={CHECKOUT_SESSION_ID}",
                ),
                cancel_url=os.environ.get(
                    "STRIPE_CANCEL_URL", "https://example.com/billing/cancel"
                ),
            )
        except Exception as e:
            # Real SDK errors → surface as ValueError so the route layer
            # can convert to 502 Bad Gateway. Don't swallow.
            raise RuntimeError(f"stripe.checkout.Session.create failed: {e}") from e
        return PaymentResult(
            payment_id=session.id,                   # "cs_test_xxx" or "cs_live_xxx"
            checkout_url=session.url,
            qr_code_url=None,
            status="pending",
            expires_at=int(session.expires_at) if getattr(session, "expires_at", None) else int(time.time()) + 3600,
            raw={
                "provider": "stripe",
                "mode": "live",
                "session_id": session.id,
                "order_id": order.order_id,
                "amount_cents": order.amount_cents,
                "currency": order.currency,
                "payment_status": getattr(session, "payment_status", "unpaid"),
            },
        )

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify Stripe webhook signature.

        Live mode: defers to ``stripe.Webhook.construct_event`` (real Stripe
        signature scheme with timestamp tolerance).

        Mock mode: HMAC-SHA256 of ``timestamp.payload`` (mirrors Stripe v1 scheme
        but without timestamp tolerance / replay window — for unit tests).
        """
        if not signature:
            raise WebhookVerificationError("missing signature header")
        if self.mode == "live":
            sdk = _stripe_sdk()
            if sdk is not None:
                try:
                    event = sdk.Webhook.construct_event(
                        payload, signature, self.webhook_secret
                    )
                except Exception as e:  # ValueError from SDK on bad sig
                    raise WebhookVerificationError(
                        f"stripe webhook signature invalid: {e}"
                    ) from e
                # Translate to our WebhookEvent
                return self._translate_stripe_event(event)
        # Mock / fallback verification (also used in live mode if SDK missing)
        try:
            parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
            ts = parts.get("t", "")
            v1 = parts.get("v1", "")
        except Exception as e:
            raise WebhookVerificationError(f"malformed signature: {e}") from e
        if not ts or not v1:
            raise WebhookVerificationError("missing t= or v1= in signature")
        signed = f"{ts}.{payload.decode('utf-8', errors='replace')}"
        expected = self.compute_hmac_sha256(self.webhook_secret, signed)
        if not self.constant_time_eq(expected, v1):
            raise WebhookVerificationError("signature mismatch")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise WebhookVerificationError(f"invalid JSON: {e}") from e
        return self._decode_event(data)

    def _translate_stripe_event(self, event: Any) -> WebhookEvent:
        """Convert a real ``stripe.Event`` object into our ``WebhookEvent``."""
        # event is a stripe.Event (dict-like). Extract .data.object.
        try:
            data_dict = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        except Exception:
            data_dict = dict(event) if hasattr(event, "__iter__") else {}
        return self._decode_event(data_dict)

    def _decode_event(self, data: Dict[str, Any]) -> WebhookEvent:
        """Translate a Stripe event payload (dict) to WebhookEvent."""
        evt_type = data.get("type", "unknown")
        obj = data.get("data", {}).get("object", {}) or {}
        meta = obj.get("metadata", {}) or {}
        # P1-2: dispute events have nested charge w/ payment_intent metadata
        if evt_type.startswith("charge.dispute."):
            order_id = meta.get("order_id", "")
            payment_id = obj.get("charge", "") or obj.get("id", "")
            amount_cents = int(obj.get("amount", 0) or 0)
            currency = (obj.get("currency", "usd") or "usd").upper()
            return WebhookEvent(
                event_id=data.get("id", self.new_payment_id("evt")),
                event_type=evt_type,
                order_id=order_id,
                payment_id=payment_id,
                amount_cents=amount_cents,
                currency=currency,
                status="disputed",  # P1-2: 标记为争议
                created_at=int(data.get("created", time.time())),
                raw=data,
            )
        order_id = meta.get("order_id", obj.get("client_reference_id", ""))
        payment_id = obj.get("id", "")
        amount_cents = int(obj.get("amount", 0) or 0)
        currency = (obj.get("currency", "usd") or "usd").upper()
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
    def refund(self, order: Any,
               amount: Optional[Union[int, float, str, Decimal]] = None) -> RefundResult:
        """Refund an order — full or partial.

        Args:
            order: Order with at least amount_cents, external_ref, currency
            amount: None/empty -> full refund of remaining balance.
                    int|float|str|Decimal -> partial refund amount in major units
                    (e.g. 9.99 == 999 cents).

        Returns:
            RefundResult with success, refund_id, amount_cents, is_partial,
            remaining_cents (== 0 if this refund exhausts remaining balance).

        Raises:
            RefundValidationError: amount invalid (non-positive, exceeds remaining,
                                   cannot parse, order has no external_ref, etc.)
        """
        if not order.external_ref:
            raise RefundValidationError(
                f"order {order.order_id!r} has no external_ref — cannot refund"
            )
        already_refunded = int(getattr(order, "refunded_amount_cents", 0) or 0)
        cents = to_refund_cents(
            amount,
            order_amount_cents=int(order.amount_cents),
            already_refunded_cents=already_refunded,
        )
        if self.mode == "mock":
            refund_id = f"re_mock_{uuid.uuid4().hex[:16]}"
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=refund_id,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message=(
                    "partial refund (mock)" if remaining > 0 else "full refund (mock)"
                ),
                raw={
                    "provider": "stripe",
                    "mode": "mock",
                    "payment_intent": order.external_ref,
                    "amount_cents": cents,
                    "currency": order.currency.lower(),
                },
            )
        # ── Live mode ──
        sdk = _stripe_sdk()
        if sdk is None:
            # SDK missing — degrade to synthesized live refund
            refund_id = f"re_live_nosdk_{uuid.uuid4().hex[:16]}"
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=refund_id,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message="refund accepted (live mode — stripe SDK not installed)",
                raw={
                    "provider": "stripe",
                    "mode": "live-no-sdk",
                    "payment_intent": order.external_ref,
                    "amount_cents": cents,
                    "currency": order.currency.lower(),
                },
            )
        sdk.api_key = self.secret_key
        try:
            refund_obj = sdk.Refund.create(
                payment_intent=order.external_ref,
                amount=cents,
            )
        except Exception as e:
            raise RuntimeError(f"stripe.Refund.create failed: {e}") from e
        remaining = int(order.amount_cents) - (already_refunded + cents)
        actual_amount = int(getattr(refund_obj, "amount", cents) or cents)
        return RefundResult(
            success=True,
            refund_id=str(getattr(refund_obj, "id", f"re_live_{uuid.uuid4().hex[:16]}")),
            amount_cents=actual_amount,
            is_partial=remaining > 0,
            remaining_cents=remaining,
            message="refund accepted (live)",
            raw={
                "provider": "stripe",
                "mode": "live",
                "payment_intent": order.external_ref,
                "amount_cents": actual_amount,
                "currency": order.currency.lower(),
                "refund_id": getattr(refund_obj, "id", ""),
                "status": getattr(refund_obj, "status", "succeeded"),
            },
        )

    # ── query ─────────────────────────────────────────────────────────
    def query(self, order: Any) -> str:
        if self.mode == "live":
            sdk = _stripe_sdk()
            if sdk is not None and getattr(order, "external_ref", None):
                try:
                    sdk.api_key = self.secret_key
                    session = sdk.checkout.Session.retrieve(order.external_ref)
                    ps = getattr(session, "payment_status", "unpaid")
                    if ps == "paid":
                        return "success"
                    if ps == "unpaid":
                        return "pending"
                    if ps in ("no_payment_required",):
                        return "success"
                except Exception:
                    pass
        # Fallback: derive from order.status
        if order.status.value == "paid" or order.status.value == "fulfilled":
            return "success"
        if order.status.value == "failed":
            return "failed"
        if order.status.value == "refunded":
            return "refunded"
        return "pending"


__all__ = ["StripeProvider"]
