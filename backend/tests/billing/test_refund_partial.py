"""P6-Fix-C-2: Partial refund tests.

Tests cover:
- to_refund_cents() helper validation
- Stripe / Alipay / WeChat refund(amount=...) partial refund
- Cumulative partial refund + remaining balance tracking
- Validation: amount <= 0, amount > remaining, parse error
- OrderService.refund(amount_cents=...) end-to-end
- Routes: POST /api/v1/billing/refund/{id} with amount
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.payments.base import (
    PaymentProvider, PaymentResult, WebhookEvent, RefundResult,
    PaymentStatus, RefundValidationError, to_refund_cents,
)
from billing.payments.stripe_provider import StripeProvider
from billing.payments.alipay_provider import AlipayProvider
from billing.payments.wechat_provider import WeChatPayProvider
from billing.orders import (
    Order, OrderStatus, OrderService, InMemoryOrderStore,
)


# ── helpers ─────────────────────────────────────────────────────────
def _make_order(order_id: str = "ord_refund_001",
                amount_cents: int = 10000,           # $100 / ¥100
                currency: str = "USD",
                payment_method: str = "stripe",
                plan_id: str = "pro",
                refunded_amount_cents: int = 0,
                status: OrderStatus = OrderStatus.FULFILLED,
                external_ref: str = "pi_test_external_xxx") -> Order:
    return Order(
        order_id=order_id, user_id="u_refund_test", plan_id=plan_id,
        amount_cents=amount_cents, currency=currency,
        status=status, payment_method=payment_method,
        created_at="2026-06-25T04:00:00+00:00",
        external_ref=external_ref,
        refunded_amount_cents=refunded_amount_cents,
    )


# ════════════════════════════════════════════════════════════════════
# 1. to_refund_cents() — validation helper
# ════════════════════════════════════════════════════════════════════
class TestToRefundCentsHelper:
    def test_001_amount_none_returns_full_remaining(self):
        """amount=None → full refund = order - already_refunded."""
        assert to_refund_cents(None, 10000, 0) == 10000
        assert to_refund_cents(None, 10000, 3000) == 7000
        assert to_refund_cents(None, 5000, 2500) == 2500

    def test_002_amount_none_raises_when_fully_refunded(self):
        with pytest.raises(RefundValidationError, match="already fully refunded"):
            to_refund_cents(None, 5000, 5000)
        # 0 already refunded but order is 0 → also fully refunded
        with pytest.raises(RefundValidationError, match="already fully refunded"):
            to_refund_cents(None, 0, 0)

    def test_003_amount_decimal_converts_to_cents(self):
        """amount=Decimal('9.99') → 999 cents."""
        assert to_refund_cents(Decimal("9.99"), 10000) == 999
        assert to_refund_cents(Decimal("50.00"), 10000) == 5000

    def test_004_amount_float_converts_to_cents(self):
        assert to_refund_cents(9.99, 10000) == 999
        assert to_refund_cents(50.0, 10000) == 5000

    def test_005_amount_int_treated_as_major_units(self):
        """amount=10 → 1000 cents (not 10 cents)."""
        assert to_refund_cents(10, 10000) == 1000

    def test_006_amount_string_parses_correctly(self):
        assert to_refund_cents("9.99", 10000) == 999
        assert to_refund_cents("  9.99  ", 10000) == 999  # whitespace stripped

    def test_007_amount_zero_or_negative_rejected(self):
        with pytest.raises(RefundValidationError, match="must be > 0"):
            to_refund_cents(0, 10000)
        with pytest.raises(RefundValidationError, match="must be > 0"):
            to_refund_cents(-5, 10000)
        with pytest.raises(RefundValidationError, match="must be > 0"):
            to_refund_cents(Decimal("-1.50"), 10000)

    def test_008_amount_exceeds_remaining_rejected(self):
        """amount > (order - already_refunded) → RefundValidationError."""
        with pytest.raises(RefundValidationError, match="exceeds remaining"):
            to_refund_cents(Decimal("200.00"), 10000)
        with pytest.raises(RefundValidationError, match="exceeds remaining"):
            to_refund_cents(Decimal("80.00"), 10000, already_refunded_cents=3000)

    def test_009_amount_unparseable_rejected(self):
        with pytest.raises(RefundValidationError, match="cannot parse"):
            to_refund_cents("not-a-number", 10000)
        with pytest.raises(RefundValidationError, match="empty"):
            to_refund_cents("   ", 10000)
        with pytest.raises(RefundValidationError, match="unsupported amount type"):
            to_refund_cents(object(), 10000)

    def test_010_amount_too_small_rejected(self):
        """amount < 0.01 (less than 1 cent) → reject."""
        with pytest.raises(RefundValidationError, match="too small"):
            to_refund_cents(Decimal("0.001"), 10000)

    def test_011_amount_at_boundary_succeeds(self):
        """amount == remaining → succeeds (== full remaining refund)."""
        # 9900 cents order, refunding 99.00 (exact)
        assert to_refund_cents(Decimal("99.00"), 9900) == 9900

    def test_012_amount_already_partially_refunded(self):
        """Subsequent partial refunds subtract from already_refunded."""
        # Order 10000, already refunded 3000 → remaining 7000
        assert to_refund_cents(Decimal("50.00"), 10000,
                               already_refunded_cents=3000) == 5000
        # Try to refund 80 (more than remaining 70)
        with pytest.raises(RefundValidationError):
            to_refund_cents(Decimal("80.00"), 10000,
                            already_refunded_cents=3000)


# ════════════════════════════════════════════════════════════════════
# 2. Stripe refund — full & partial
# ════════════════════════════════════════════════════════════════════
class TestStripePartialRefund:
    def test_020_stripe_full_refund_default(self):
        """refund(order) with no amount → full refund."""
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        result = prov.refund(order)
        assert isinstance(result, RefundResult)
        assert result.success is True
        assert result.amount_cents == 10000
        assert result.is_partial is False
        assert result.remaining_cents == 0
        assert result.refund_id.startswith("re_mock_")

    def test_021_stripe_partial_refund(self):
        """refund(order, amount=Decimal('30.00')) → 3000 cents partial."""
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        result = prov.refund(order, amount=Decimal("30.00"))
        assert result.success is True
        assert result.amount_cents == 3000
        assert result.is_partial is True
        assert result.remaining_cents == 7000  # 10000 - 3000
        assert result.message == "partial refund (mock)"
        assert result.refund_id.startswith("re_mock_")
        # raw payload should include payment_intent
        assert result.raw["provider"] == "stripe"
        assert result.raw["mode"] == "mock"
        assert result.raw["payment_intent"] == order.external_ref
        assert result.raw["amount_cents"] == 3000

    def test_022_stripe_partial_refund_with_string_amount(self):
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        result = prov.refund(order, amount="49.99")
        assert result.amount_cents == 4999
        assert result.is_partial is True

    def test_023_stripe_partial_refund_with_int_amount(self):
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        result = prov.refund(order, amount=10)  # 10 yuan/dollar → 1000 cents
        assert result.amount_cents == 1000
        assert result.is_partial is True

    def test_024_stripe_rejects_amount_exceeding_remaining(self):
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        with pytest.raises(RefundValidationError, match="exceeds remaining"):
            prov.refund(order, amount=Decimal("200.00"))

    def test_025_stripe_rejects_negative_amount(self):
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000)
        with pytest.raises(RefundValidationError, match="must be > 0"):
            prov.refund(order, amount=Decimal("-5.00"))

    def test_026_stripe_rejects_no_external_ref(self):
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000, external_ref=None)
        with pytest.raises(RefundValidationError, match="no external_ref"):
            prov.refund(order)

    def test_027_stripe_cumulative_partial_refunds(self):
        """Refund $30, then $40 → 3000 + 4000 = 7000 of 10000 refunded."""
        prov = StripeProvider(mode="mock")
        order = _make_order(amount_cents=10000, refunded_amount_cents=0)
        r1 = prov.refund(order, amount=Decimal("30.00"))
        assert r1.amount_cents == 3000
        assert r1.is_partial is True
        assert r1.remaining_cents == 7000
        # Mutate order to track cumulative refund
        order.refunded_amount_cents += r1.amount_cents
        r2 = prov.refund(order, amount=Decimal("40.00"))
        assert r2.amount_cents == 4000
        assert r2.is_partial is True
        assert r2.remaining_cents == 3000
        # Final refund of remaining $30 → exhausts balance, NOT partial
        order.refunded_amount_cents += r2.amount_cents
        r3 = prov.refund(order, amount=Decimal("30.00"))
        assert r3.amount_cents == 3000
        assert r3.is_partial is False  # == remaining → exhausted
        assert r3.remaining_cents == 0


# ════════════════════════════════════════════════════════════════════
# 3. Alipay refund — full & partial
# ════════════════════════════════════════════════════════════════════
class TestAlipayPartialRefund:
    def test_030_alipay_full_refund_default(self):
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="alipay")
        result = prov.refund(order)
        assert isinstance(result, RefundResult)
        assert result.success is True
        assert result.amount_cents == 10000
        assert result.is_partial is False
        assert result.remaining_cents == 0
        assert result.refund_id.startswith("refund_")

    def test_031_alipay_partial_refund_decimal(self):
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="alipay")
        result = prov.refund(order, amount=Decimal("25.50"))
        assert result.success is True
        assert result.amount_cents == 2550
        assert result.is_partial is True
        # raw should include CNY-formatted refund_amount
        assert result.raw["refund_amount"] == "25.50"
        assert result.raw["trade_no"] == order.external_ref

    def test_032_alipay_partial_refund_float(self):
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="alipay")
        result = prov.refund(order, amount=15.75)
        assert result.amount_cents == 1575
        assert result.is_partial is True

    def test_033_alipay_rejects_amount_exceeding_remaining(self):
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=5000, currency="CNY",
                            payment_method="alipay")
        with pytest.raises(RefundValidationError, match="exceeds remaining"):
            prov.refund(order, amount=Decimal("100.00"))

    def test_034_alipay_rejects_no_external_ref(self):
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=10000, external_ref=None,
                            payment_method="alipay")
        with pytest.raises(RefundValidationError, match="no external_ref"):
            prov.refund(order, amount=Decimal("10.00"))

    def test_035_alipay_partial_then_partial(self):
        """Two partial refunds on alipay order."""
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="alipay",
                            refunded_amount_cents=0)
        r1 = prov.refund(order, amount=Decimal("10.00"))
        assert r1.amount_cents == 1000
        assert r1.is_partial is True
        assert r1.remaining_cents == 9000
        # Track cumulative
        order.refunded_amount_cents += r1.amount_cents
        r2 = prov.refund(order, amount=Decimal("20.00"))
        assert r2.amount_cents == 2000
        assert r2.is_partial is True
        assert r2.remaining_cents == 7000


# ════════════════════════════════════════════════════════════════════
# 4. WeChat refund — full & partial
# ════════════════════════════════════════════════════════════════════
class TestWeChatPartialRefund:
    def test_040_wechat_full_refund_default(self):
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="wechat")
        result = prov.refund(order)
        assert isinstance(result, RefundResult)
        assert result.success is True
        assert result.amount_cents == 10000
        assert result.is_partial is False
        assert result.remaining_cents == 0
        assert result.refund_id.startswith("wx_refund_")

    def test_041_wechat_partial_refund(self):
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="wechat")
        result = prov.refund(order, amount=Decimal("33.33"))
        assert result.success is True
        assert result.amount_cents == 3333
        assert result.is_partial is True
        assert result.raw["provider"] == "wechat"
        assert result.raw["transaction_id"] == order.external_ref

    def test_042_wechat_partial_refund_with_string(self):
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="wechat")
        result = prov.refund(order, amount="100.00")
        assert result.amount_cents == 10000
        assert result.is_partial is False  # == full amount

    def test_043_wechat_rejects_amount_exceeding_remaining(self):
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=5000, currency="CNY",
                            payment_method="wechat")
        with pytest.raises(RefundValidationError, match="exceeds remaining"):
            prov.refund(order, amount=Decimal("100.00"))

    def test_044_wechat_rejects_no_external_ref(self):
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=10000, external_ref=None,
                            payment_method="wechat")
        with pytest.raises(RefundValidationError, match="no external_ref"):
            prov.refund(order, amount=Decimal("10.00"))

    def test_045_wechat_cumulative_partial_then_full(self):
        """Refund 25, then 75 → second refund exhausts remaining, not partial."""
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=10000, currency="CNY",
                            payment_method="wechat")
        r1 = prov.refund(order, amount=Decimal("25.00"))
        assert r1.amount_cents == 2500
        assert r1.is_partial is True
        assert r1.remaining_cents == 7500
        order.refunded_amount_cents = r1.amount_cents
        r2 = prov.refund(order, amount=Decimal("75.00"))
        assert r2.amount_cents == 7500
        # 7500 == remaining (7500), so this exhausts → not partial
        assert r2.is_partial is False
        assert r2.remaining_cents == 0


# ════════════════════════════════════════════════════════════════════
# 5. OrderService.refund() — end-to-end with partial amount_cents
# ════════════════════════════════════════════════════════════════════
class TestOrderServicePartialRefund:
    def test_050_order_service_full_refund(self):
        """No amount_cents → full refund, status → REFUNDED."""
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        refunded = svc.refund(order.order_id, reason="customer_request")
        assert refunded.status == OrderStatus.REFUNDED
        assert refunded.refunded_amount_cents == 10000
        assert refunded.refund_reason == "customer_request"

    def test_051_order_service_partial_refund(self):
        """amount_cents=3000 → order stays FULFILLED, partial tracking set."""
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        refunded = svc.refund(order.order_id, reason="partial1",
                              amount_cents=3000)
        assert refunded.status == OrderStatus.FULFILLED  # not yet full
        assert refunded.refunded_amount_cents == 3000
        # Refund history recorded
        assert len(refunded.metadata["refunds"]) == 1
        assert refunded.metadata["refunds"][0]["amount_cents"] == 3000
        assert refunded.metadata["refunds"][0]["is_partial"] is True

    def test_052_order_service_two_partial_refunds(self):
        """Two partial refunds → cumulative tracking."""
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        r1 = svc.refund(order.order_id, reason="partial1", amount_cents=3000)
        assert r1.status == OrderStatus.FULFILLED
        assert r1.refunded_amount_cents == 3000
        r2 = svc.refund(order.order_id, reason="partial2", amount_cents=4000)
        assert r2.status == OrderStatus.FULFILLED
        assert r2.refunded_amount_cents == 7000
        assert len(r2.metadata["refunds"]) == 2

    def test_053_order_service_partial_then_full(self):
        """Partial refund leaves order in non-terminal state; second full flips to REFUNDED."""
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        r1 = svc.refund(order.order_id, reason="p1", amount_cents=4000)
        assert r1.status == OrderStatus.FULFILLED
        r2 = svc.refund(order.order_id, reason="final", amount_cents=6000)
        assert r2.status == OrderStatus.REFUNDED  # full now
        assert r2.refunded_amount_cents == 10000

    def test_054_order_service_rejects_amount_exceeding_remaining(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        with pytest.raises(ValueError, match="exceeds remaining"):
            svc.refund(order.order_id, reason="too_much", amount_cents=15000)

    def test_055_order_service_rejects_zero_or_negative_amount(self):
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u1", plan_id="pro",
                                 amount_cents=10000, currency="USD")
        svc.mark_paid(order.order_id, external_ref="pi_test_xxx")
        with pytest.raises(ValueError, match="must be > 0"):
            svc.refund(order.order_id, reason="zero", amount_cents=0)
        with pytest.raises(ValueError, match="must be > 0"):
            svc.refund(order.order_id, reason="neg", amount_cents=-100)


# ════════════════════════════════════════════════════════════════════
# 6. End-to-end: provider + OrderService round-trip
# ════════════════════════════════════════════════════════════════════
class TestProviderPlusServiceIntegration:
    def test_060_partial_refund_through_provider_and_service(self):
        """Stripe partial refund → service tracks partial cumulative."""
        prov = StripeProvider(mode="mock")
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u_int", plan_id="pro",
                                 amount_cents=10000, currency="USD",
                                 payment_method="stripe")
        svc.mark_paid(order.order_id, external_ref="pi_test_int_001")
        # Provider-side: partial refund of $30
        order_after_pay = svc.get(order.order_id)
        prov_result = prov.refund(order_after_pay, amount=Decimal("30.00"))
        assert prov_result.success
        assert prov_result.amount_cents == 3000
        assert prov_result.is_partial is True
        assert prov_result.remaining_cents == 7000
        # Service-side: record the partial refund
        svc.refund(order.order_id, reason="customer_30",
                   amount_cents=prov_result.amount_cents)
        order_after = svc.get(order.order_id)
        assert order_after.status == OrderStatus.FULFILLED  # partial, not full
        assert order_after.refunded_amount_cents == 3000
        # Second partial refund of $40 → cumulative 7000
        prov_result2 = prov.refund(order_after, amount=Decimal("40.00"))
        assert prov_result2.amount_cents == 4000
        assert prov_result2.is_partial is True
        assert prov_result2.remaining_cents == 3000
        svc.refund(order.order_id, reason="customer_40",
                   amount_cents=prov_result2.amount_cents)
        order_after2 = svc.get(order.order_id)
        assert order_after2.refunded_amount_cents == 7000
        assert order_after2.status == OrderStatus.FULFILLED
        # Third refund of remaining $30 → exhausts, not partial
        prov_result3 = prov.refund(order_after2, amount=Decimal("30.00"))
        assert prov_result3.amount_cents == 3000
        assert prov_result3.is_partial is False  # == remaining → exhausted
        assert prov_result3.remaining_cents == 0
        svc.refund(order.order_id, reason="final",
                   amount_cents=prov_result3.amount_cents)
        order_final = svc.get(order.order_id)
        assert order_final.status == OrderStatus.REFUNDED
        assert order_final.refunded_amount_cents == 10000


# ════════════════════════════════════════════════════════════════════
# 7. HTTP route — POST /api/v1/billing/refund/{id} with amount
# ════════════════════════════════════════════════════════════════════
class TestRefundRoutePartial:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Reset service state + dedup store for each test (Redis-backed)."""
        from billing.routes import reset_state
        from billing.payments.webhook_dedup import reset_store
        from billing.payments.idempotency import reset_store as reset_idem_store
        reset_state()
        # Reset the Redis-backed dedup/idempotency stores so unique event IDs
        # aren't polluted from previous test runs (24h TTL).
        reset_store()
        reset_idem_store()
        # Build fresh FastAPI app with billing router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from billing.routes import router as billing_router
        self.app = FastAPI()
        self.app.include_router(billing_router)
        self.client = TestClient(self.app)

    def test_070_route_full_refund_no_amount(self):
        """POST /refund/{id} without amount → full refund."""
        client = self.client
        # Create order
        r = client.post("/api/v1/billing/orders", json={
            "user_id": "u_r", "plan_id": "pro", "currency": "USD",
            "period": "monthly", "payment_method": "stripe",
        })
        order_id = r.json()["order_id"]
        client.post(f"/api/v1/billing/payment/{order_id}", json={})
        # Mark paid via webhook
        import hashlib, hmac, json, time
        payload = json.dumps({
            "id": "evt_route_refund", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_route_refund", "client_reference_id": order_id,
                "amount": 9900, "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post("/api/v1/billing/webhook/stripe", content=payload,
                    headers={"stripe-signature": f"t={ts},v1={v1}",
                             "content-type": "application/json"})
        # Refund (no amount)
        r3 = client.post(f"/api/v1/billing/refund/{order_id}",
                         json={"reason": "customer_request"})
        assert r3.status_code == 200, r3.text
        body = r3.json()
        assert body["status"] == "refunded"
        assert body["refunded_amount_cents"] == 9900

    def test_071_route_partial_refund_with_amount(self):
        """POST /refund/{id} with amount=30.00 → partial."""
        client = self.client
        r = client.post("/api/v1/billing/orders", json={
            "user_id": "u_rp", "plan_id": "pro", "currency": "USD",
            "period": "monthly", "payment_method": "stripe",
        })
        order_id = r.json()["order_id"]
        client.post(f"/api/v1/billing/payment/{order_id}", json={})
        import hashlib, hmac, json, time
        payload = json.dumps({
            "id": "evt_partial", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_partial", "client_reference_id": order_id,
                "amount": 9900, "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post("/api/v1/billing/webhook/stripe", content=payload,
                    headers={"stripe-signature": f"t={ts},v1={v1}",
                             "content-type": "application/json"})
        # Partial refund $30
        r3 = client.post(f"/api/v1/billing/refund/{order_id}",
                         json={"reason": "partial30", "amount": "30.00"})
        assert r3.status_code == 200, r3.text
        body = r3.json()
        # Order stays fulfilled (partial, not full)
        assert body["status"] == "fulfilled"
        assert body["refunded_amount_cents"] == 3000

    def test_072_route_partial_refund_rejects_exceeding_remaining(self):
        """POST /refund/{id} with amount > order → 400."""
        client = self.client
        r = client.post("/api/v1/billing/orders", json={
            "user_id": "u_too", "plan_id": "pro", "currency": "USD",
            "period": "monthly", "payment_method": "stripe",
        })
        order_id = r.json()["order_id"]
        client.post(f"/api/v1/billing/payment/{order_id}", json={})
        import hashlib, hmac, json, time
        payload = json.dumps({
            "id": "evt_too", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_too", "client_reference_id": order_id,
                "amount": 9900, "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post("/api/v1/billing/webhook/stripe", content=payload,
                    headers={"stripe-signature": f"t={ts},v1={v1}",
                             "content-type": "application/json"})
        # Try to refund $200 (order is only $99)
        r3 = client.post(f"/api/v1/billing/refund/{order_id}",
                         json={"reason": "too_much", "amount": "200.00"})
        assert r3.status_code == 400
        assert "exceeds remaining" in r3.json()["detail"]

    def test_073_route_partial_then_full_refund(self):
        """Partial refund → full refund exhausts remaining → status=REFUNDED."""
        client = self.client
        r = client.post("/api/v1/billing/orders", json={
            "user_id": "u_two", "plan_id": "pro", "currency": "USD",
            "period": "monthly", "payment_method": "stripe",
        })
        order_id = r.json()["order_id"]
        client.post(f"/api/v1/billing/payment/{order_id}", json={})
        import hashlib, hmac, json, time
        payload = json.dumps({
            "id": "evt_two", "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_two", "client_reference_id": order_id,
                "amount": 9900, "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        v1 = hmac.new(b"whsec_mock_secret",
                      f"{ts}.{payload.decode()}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
        client.post("/api/v1/billing/webhook/stripe", content=payload,
                    headers={"stripe-signature": f"t={ts},v1={v1}",
                             "content-type": "application/json"})
        # First partial $40
        r3 = client.post(f"/api/v1/billing/refund/{order_id}",
                         json={"reason": "p1", "amount": "40.00"})
        assert r3.status_code == 200
        assert r3.json()["status"] == "fulfilled"
        assert r3.json()["refunded_amount_cents"] == 4000
        # Second partial $59 (== remaining) → full, status flips to REFUNDED
        r4 = client.post(f"/api/v1/billing/refund/{order_id}",
                         json={"reason": "p2", "amount": "59.00"})
        assert r4.status_code == 200
        assert r4.json()["status"] == "refunded"
        assert r4.json()["refunded_amount_cents"] == 9900