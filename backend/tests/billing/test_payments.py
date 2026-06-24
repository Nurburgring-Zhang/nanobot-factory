"""P4-10-W1: Payment providers tests (5+ tests)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.payments.base import (
    PaymentProvider, PaymentResult, WebhookEvent,
    WebhookVerificationError,
)
from billing.payments.stripe_provider import StripeProvider
from billing.payments.alipay_provider import AlipayProvider
from billing.payments.wechat_provider import WeChatPayProvider
from billing.payments.factory import (
    get_provider, get_providers, register_provider, reset_providers,
    register_defaults,
)
from billing.orders import Order, OrderStatus


def _make_order(order_id: str = "ord_test_001",
                amount_cents: int = 9900,
                currency: str = "USD",
                payment_method: str = "stripe",
                plan_id: str = "pro") -> Order:
    return Order(
        order_id=order_id, user_id="u_test", plan_id=plan_id,
        amount_cents=amount_cents, currency=currency,
        status=OrderStatus.PENDING, payment_method=payment_method,
        created_at="2026-06-24T04:00:00+00:00",
    )


class TestStripeProvider:
    def test_001_stripe_create_payment_mock(self):
        """Mock mode returns synthetic Stripe checkout URL."""
        prov = StripeProvider(mode="mock")
        order = _make_order()
        result = prov.create_payment(order)
        assert result.payment_id.startswith("pi_test_")
        assert result.checkout_url.startswith("https://checkout.stripe.com/c/pay/")
        assert result.status == "pending"
        assert result.expires_at > int(time.time())

    def test_002_stripe_webhook_signature_verification(self):
        """Verify webhook signature with HMAC-SHA256(timestamp + body)."""
        prov = StripeProvider(mode="mock",
                              webhook_secret="whsec_test_secret")
        payload_dict = {
            "id": "evt_test_1",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_123",
                "client_reference_id": "ord_test_001",
                "amount": 9900,
                "currency": "usd",
            }},
            "created": int(time.time()),
        }
        payload = json.dumps(payload_dict).encode("utf-8")
        ts = str(int(time.time()))
        signed = f"{ts}.{payload.decode('utf-8')}"
        v1 = hmac.new(
            "whsec_test_secret".encode("utf-8"),
            signed.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        sig = f"t={ts},v1={v1}"
        event = prov.verify_webhook(payload, sig)
        assert event.event_type == "checkout.session.completed"
        assert event.order_id == "ord_test_001"
        assert event.amount_cents == 9900
        assert event.status == "success"

    def test_003_stripe_webhook_bad_signature(self):
        prov = StripeProvider(mode="mock",
                              webhook_secret="whsec_test_secret")
        payload = json.dumps({"id": "evt_bad", "type": "x"}).encode("utf-8")
        with pytest.raises(WebhookVerificationError):
            prov.verify_webhook(payload, "t=1,v1=bogus")


class TestAlipayProvider:
    def test_004_alipay_create_payment_mock(self):
        """Mock mode returns alipay:// trade URL."""
        prov = AlipayProvider(mode="mock")
        order = _make_order(amount_cents=9900, currency="CNY",
                            payment_method="alipay")
        result = prov.create_payment(order)
        assert result.payment_id.startswith("alipay_trade_")
        assert "openapi.alipay.com" in result.checkout_url or "alipay.com" in result.checkout_url
        assert result.status == "pending"

    def test_005_alipay_webhook_signature(self):
        """Alipay uses HMAC-SHA256 over sorted query string."""
        prov = AlipayProvider(mode="mock", webhook_secret="alipay_test_secret")
        params = {
            "out_trade_no": "ord_alipay_001",
            "trade_no": "20260624xxxx",
            "total_amount": "99.00",
            "trade_status": "TRADE_SUCCESS",
        }
        # Compute sign
        sorted_items = sorted(
            f"{k}={v}" for k, v in params.items()
        )
        sign_str = "&".join(sorted_items)
        sign = hmac.new(
            "alipay_test_secret".encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params_with_sign = {**params, "sign": sign}
        payload = json.dumps(params_with_sign).encode("utf-8")
        event = prov.verify_webhook(payload, sign)
        assert event.order_id == "ord_alipay_001"
        assert event.amount_cents == 9900  # 99.00 * 100
        assert event.status == "success"


class TestWeChatProvider:
    def test_006_wechat_create_payment_mock(self):
        """Mock mode returns weixin:// wxpay QR code URL."""
        prov = WeChatPayProvider(mode="mock")
        order = _make_order(amount_cents=9900, currency="CNY",
                            payment_method="wechat")
        result = prov.create_payment(order)
        assert result.payment_id.startswith("wx_prepay_")
        assert result.checkout_url.startswith("weixin://wxpay/bizpayurl")
        assert result.qr_code_url is not None
        assert result.qr_code_url.startswith("weixin://wxpay/bizpayurl")

    def test_007_wechat_webhook_signature(self):
        """WeChat v3 mock: HMAC-SHA256 of raw body."""
        prov = WeChatPayProvider(mode="mock", webhook_secret="wechat_test_secret")
        body = json.dumps({
            "id": "wx_event_001",
            "event_type": "TRANSACTION.SUCCESS",
            "create_time": int(time.time()),
            "resource": {
                "out_trade_no": "ord_wechat_001",
                "transaction_id": "wx_42000xxxx",
                "amount": {"total": 9900, "currency": "CNY"},
            },
        }, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(
            "wechat_test_secret".encode("utf-8"),
            body, hashlib.sha256,
        ).hexdigest()
        event = prov.verify_webhook(body, sig)
        assert event.order_id == "ord_wechat_001"
        assert event.amount_cents == 9900
        assert event.currency == "CNY"
        assert event.status == "success"


class TestProviderFactory:
    def test_008_three_providers_registered_by_default(self):
        reset_providers()
        register_defaults()
        names = {p.name for p in get_providers()}
        assert names == {"stripe", "alipay", "wechat"}

    def test_009_get_provider_raises_for_unknown(self):
        reset_providers()
        register_defaults()
        with pytest.raises(KeyError):
            get_provider("paypal")

    def test_010_register_custom_provider(self):
        reset_providers()
        register_defaults()
        # Register a custom (mock) provider
        class CustomProvider(PaymentProvider):
            name = "custom"
            def create_payment(self, order):  # type: ignore
                return PaymentResult(payment_id="cp_1", checkout_url="x://y", status="pending")
            def verify_webhook(self, payload, signature):
                return WebhookEvent(event_id="e1", event_type="x", order_id="o1",
                                    payment_id="p1", amount_cents=0, currency="USD",
                                    status="success", created_at=0)
            def refund(self, order): return True
            def query(self, order): return "success"
        cp = CustomProvider()
        register_provider(cp)
        assert get_provider("custom") is cp


class TestEndToEndFlow:
    """Full flow: create order → payment → webhook → mark paid."""

    def test_011_stripe_full_flow(self):
        """Mock order → Stripe payment → webhook → mark paid."""
        from billing.orders import OrderService, InMemoryOrderStore
        store = InMemoryOrderStore()
        svc = OrderService(store)
        order = svc.create_order(user_id="u_e2e", plan_id="pro",
                                 amount_cents=9900, currency="USD",
                                 payment_method="stripe")
        # Create payment
        prov = StripeProvider(mode="mock")
        result = prov.create_payment(order)
        assert result.checkout_url.startswith("https://checkout.stripe.com/c/pay/")
        # Build webhook
        payload = json.dumps({
            "id": "evt_e2e",
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": result.payment_id,
                "client_reference_id": order.order_id,
                "amount": order.amount_cents,
                "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")
        ts = str(int(time.time()))
        sig = f"t={ts},v1={hmac.new(b'whsec_mock_secret', f'{ts}.{payload.decode()}'.encode(), hashlib.sha256).hexdigest()}"
        event = prov.verify_webhook(payload, sig)
        # Mark paid
        paid = svc.mark_paid(event.order_id, external_ref=event.payment_id)
        assert paid.status == OrderStatus.FULFILLED
        assert paid.paid_at is not None
        assert paid.external_ref == event.payment_id
