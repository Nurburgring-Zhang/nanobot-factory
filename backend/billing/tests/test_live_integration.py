"""P6-Fix-C-7: Live mode SDK integration tests (Stripe / Alipay / WeChat Pay).

Goal
----
Verify that each of the 3 payment providers can be switched to live mode
and will invoke the real (mocked) SDK call path. Mock mode is preserved
so existing tests don't regress.

Test plan
---------
1. SDK availability — all 3 SDKs are importable from the local venv.
2. Stripe live_mode() fluent API — switches mode and pushes api_key to SDK.
3. Stripe create_payment_live calls stripe.checkout.Session.create.
4. Stripe refund_live calls stripe.Refund.create.
5. Stripe verify_webhook_live defers to stripe.Webhook.construct_event.
6. Alipay live_mode() validates app_id + private_key.
7. Alipay create_payment_live calls AliPay.api_alipay_trade_page_pay.
8. Alipay refund_live calls AliPay.api_alipay_trade_refund.
9. Alipay verify_webhook_live calls AliPay.verify (RSA2 path).
10. Alipay graceful degrade when private key is invalid.
11. WeChat live_mode() validates app_id + mch_id.
12. WeChat create_payment_live calls WeChatPay.order.create.
13. WeChat refund_live calls WeChatPay.refund.apply.
14. WeChat graceful degrade when wechatpy SDK not installed (simulated).
15. .env.example has all the keys for live mode.
16. Mock mode still works for all 3 providers (regression).
17. live_mode() is a no-op idempotent when called twice.
18. Mock mode does NOT import the SDK (cheap path).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.payments.base import (
    PaymentProvider, PaymentResult, WebhookEvent, RefundResult,
    ProviderNotConfiguredError, WebhookVerificationError,
)
from billing.payments.stripe_provider import StripeProvider
from billing.payments.alipay_provider import AlipayProvider
from billing.payments.wechat_provider import WeChatPayProvider
from billing.orders import Order, OrderStatus


# ── helpers ────────────────────────────────────────────────────────────
def _make_order(order_id: str = "ord_live_001",
                amount_cents: int = 9900,
                currency: str = "USD",
                payment_method: str = "stripe",
                plan_id: str = "pro",
                external_ref: str = "pi_seed_xxx") -> Order:
    return Order(
        order_id=order_id, user_id="u_live_test", plan_id=plan_id,
        amount_cents=amount_cents, currency=currency,
        status=OrderStatus.PENDING, payment_method=payment_method,
        created_at="2026-06-25T05:30:00+00:00",
        external_ref=external_ref,
    )


# ── 1. SDK availability ───────────────────────────────────────────────
class TestSDKAvailability:
    def test_001_stripe_sdk_importable(self):
        import stripe  # noqa: F401
        assert stripe.VERSION is not None

    def test_002_alipay_sdk_importable(self):
        from alipay import AliPay  # noqa: F401
        assert AliPay is not None

    def test_003_wechat_sdk_importable(self):
        from wechatpy.pay import WeChatPay  # noqa: F401
        assert WeChatPay is not None

    def test_004_lazy_imports_in_providers(self):
        """The ``_stripe_sdk``/``_alipay_sdk``/``_wechat_sdk`` helpers return the SDK class or None."""
        from billing.payments.stripe_provider import _stripe_sdk
        from billing.payments.alipay_provider import _alipay_sdk
        from billing.payments.wechat_provider import _wechat_sdk
        assert _stripe_sdk() is not None
        assert _alipay_sdk() is not None
        assert _wechat_sdk() is not None


# ── 2-5. Stripe live mode ────────────────────────────────────────────
class TestStripeLiveMode:
    def test_010_constructor_without_key_in_live_raises(self, monkeypatch):
        monkeypatch.setenv("BILLING_STRIPE_MODE", "live")
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(ProviderNotConfiguredError):
            StripeProvider()

    def test_011_constructor_with_env_key_works(self, monkeypatch):
        monkeypatch.setenv("BILLING_STRIPE_MODE", "live")
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_xxx")
        prov = StripeProvider()
        assert prov.mode == "live"
        assert prov.secret_key == "sk_test_xxx"

    def test_012_live_mode_fluent_switch(self):
        """StripeProvider(mode='mock').live_mode(api_key) flips to live."""
        prov = StripeProvider(mode="mock")
        assert prov.mode == "mock"
        prov.live_mode(api_key="sk_test_dummy")
        assert prov.mode == "live"
        assert prov.secret_key == "sk_test_dummy"

    def test_013_live_mode_pushes_api_key_to_sdk(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_pushed")
        import stripe
        assert stripe.api_key == "sk_test_pushed"

    def test_014_live_mode_without_key_raises(self):
        prov = StripeProvider(mode="mock")
        prov.secret_key = ""
        with pytest.raises(ProviderNotConfiguredError):
            prov.live_mode()

    def test_015_create_payment_live_calls_stripe_session(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_session")
        # Stub the SDK call
        fake_session = mock.MagicMock()
        fake_session.id = "cs_test_abc123"
        fake_session.url = "https://checkout.stripe.com/c/pay/cs_test_abc123"
        fake_session.expires_at = int(time.time()) + 3600
        fake_session.payment_status = "unpaid"
        with mock.patch(
            "stripe.checkout.Session.create", return_value=fake_session
        ) as m:
            result = prov.create_payment(_make_order())
        m.assert_called_once()
        kwargs = m.call_args.kwargs
        assert kwargs["mode"] == "payment"
        assert kwargs["client_reference_id"] == "ord_live_001"
        assert result.payment_id == "cs_test_abc123"
        assert result.checkout_url == "https://checkout.stripe.com/c/pay/cs_test_abc123"
        assert result.raw["mode"] == "live"
        assert result.raw["session_id"] == "cs_test_abc123"

    def test_016_create_payment_live_propagates_sdk_error(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_err")
        with mock.patch(
            "stripe.checkout.Session.create",
            side_effect=RuntimeError("stripe api down"),
        ):
            with pytest.raises(RuntimeError, match="stripe.checkout.Session.create"):
                prov.create_payment(_make_order())

    def test_017_refund_live_calls_stripe_refund(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_refund")
        fake_refund = mock.MagicMock()
        fake_refund.id = "re_test_xyz"
        fake_refund.amount = 5000
        fake_refund.status = "succeeded"
        with mock.patch("stripe.Refund.create", return_value=fake_refund) as m:
            r = prov.refund(_make_order(amount_cents=10000, external_ref="pi_real_1"),
                            amount=50.00)
        m.assert_called_once()
        assert m.call_args.kwargs["payment_intent"] == "pi_real_1"
        assert m.call_args.kwargs["amount"] == 5000
        assert r.refund_id == "re_test_xyz"
        assert r.amount_cents == 5000
        assert r.is_partial is True
        assert r.remaining_cents == 5000
        assert r.raw["mode"] == "live"

    def test_018_verify_webhook_live_uses_stripe_construct_event(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_wh")
        # Build a payload that looks like a Stripe event
        evt = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "created": int(time.time()),
            "data": {"object": {
                "id": "cs_test_xyz",
                "client_reference_id": "ord_live_001",
                "amount": 9900,
                "currency": "usd",
            }},
        }
        # Mock the SDK's construct_event to return a dict-like event
        with mock.patch("stripe.Webhook.construct_event", return_value=evt):
            wh = prov.verify_webhook(
                payload=json.dumps(evt).encode(),
                signature="t=1234,v1=deadbeef",
            )
        assert wh.event_id == "evt_test_123"
        assert wh.event_type == "checkout.session.completed"
        assert wh.status == "success"
        assert wh.amount_cents == 9900

    def test_019_verify_webhook_live_bad_sig_raises(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_bad")
        with mock.patch(
            "stripe.Webhook.construct_event",
            side_effect=ValueError("Signature verification failed"),
        ):
            with pytest.raises(WebhookVerificationError):
                prov.verify_webhook(b"{}", signature="bad_sig")


# ── 6-10. Alipay live mode ───────────────────────────────────────────
class TestAlipayLiveMode:
    def test_020_constructor_without_app_id_raises(self, monkeypatch):
        monkeypatch.setenv("BILLING_ALIPAY_MODE", "live")
        monkeypatch.delenv("ALIPAY_APP_ID", raising=False)
        monkeypatch.setenv("ALIPAY_PRIVATE_KEY", "x")
        # Pass app_id="" explicitly to bypass the default fallback
        with pytest.raises(ProviderNotConfiguredError):
            AlipayProvider(app_id="", private_key="x")

    def test_021_constructor_without_private_key_raises(self, monkeypatch):
        monkeypatch.setenv("BILLING_ALIPAY_MODE", "live")
        monkeypatch.setenv("ALIPAY_APP_ID", "2021000000000000")
        monkeypatch.delenv("ALIPAY_PRIVATE_KEY", raising=False)
        with pytest.raises(ProviderNotConfiguredError):
            AlipayProvider(app_id="2021000000000000", private_key="")

    def test_022_live_mode_fluent_switch(self):
        prov = AlipayProvider(mode="mock")
        assert prov.mode == "mock"
        prov.live_mode(app_id="2021xxx", private_key="rsa-dummy", public_key="rsa-dummy")
        assert prov.mode == "live"
        assert prov.app_id == "2021xxx"

    def test_023_live_mode_without_keys_raises(self):
        prov = AlipayProvider(mode="mock")
        prov.app_id = ""
        prov.private_key = ""
        with pytest.raises(ProviderNotConfiguredError):
            prov.live_mode()

    def test_024_create_payment_live_calls_alipay_sdk(self):
        prov = AlipayProvider(mode="mock")
        # Mock the SDK client to a MagicMock so the live path is exercised
        prov._client = mock.MagicMock()
        prov._client.api_alipay_trade_page_pay.return_value = (
            "https://openapi.alipay.com/gateway.do?xxx"
        )
        prov.mode = "live"
        prov.app_id = "2021xxx"
        prov.private_key = "rsa-dummy"
        result = prov.create_payment(_make_order(order_id="ord_alipay_001",
                                                 currency="CNY"))
        prov._client.api_alipay_trade_page_pay.assert_called_once()
        kwargs = prov._client.api_alipay_trade_page_pay.call_args.kwargs
        assert kwargs["out_trade_no"] == "ord_alipay_001"
        assert result.raw.get("mode") == "live"
        assert result.checkout_url

    def test_025_create_payment_live_propagates_sdk_error(self):
        prov = AlipayProvider(mode="mock")
        prov._client = mock.MagicMock()
        prov._client.api_alipay_trade_page_pay.side_effect = RuntimeError(
            "alipay gateway 500"
        )
        prov.mode = "live"
        prov.app_id = "2021xxx"
        prov.private_key = "rsa-dummy"
        with pytest.raises(RuntimeError, match="alipay.api_alipay_trade_page_pay"):
            prov.create_payment(_make_order(currency="CNY"))

    def test_026_refund_live_calls_alipay_sdk(self):
        prov = AlipayProvider(mode="mock")
        prov._client = mock.MagicMock()
        prov._client.api_alipay_trade_refund.return_value = {
            "fund_change": "Y", "trade_no": "2021xxx",
        }
        prov.mode = "live"
        prov.app_id = "2021xxx"
        prov.private_key = "rsa-dummy"
        r = prov.refund(_make_order(amount_cents=10000, currency="CNY",
                                    external_ref="2021seed"),
                        amount=50.00)
        prov._client.api_alipay_trade_refund.assert_called_once()
        kwargs = prov._client.api_alipay_trade_refund.call_args.kwargs
        assert kwargs["trade_no"] == "2021seed"
        assert kwargs["refund_amount"] == "50.00"
        assert r.success
        assert r.amount_cents == 5000
        assert r.is_partial is True
        assert r.remaining_cents == 5000
        assert r.raw["mode"] == "live"

    def test_027_verify_webhook_live_uses_alipay_verify(self):
        prov = AlipayProvider(mode="mock")
        prov._client = mock.MagicMock()
        prov._client.verify.return_value = True
        prov.mode = "live"
        prov.app_id = "2021xxx"
        prov.private_key = "rsa-dummy"
        payload_dict = {
            "notify_id": "alipay_notify_001",
            "trade_status": "TRADE_SUCCESS",
            "out_trade_no": "ord_live_001",
            "trade_no": "2021alipaytrade",
            "total_amount": "99.00",
            "sign": "fake-signature",
        }
        wh = prov.verify_webhook(
            payload=json.dumps(payload_dict).encode(),
            signature="fake-signature",
        )
        prov._client.verify.assert_called_once()
        assert wh.order_id == "ord_live_001"
        assert wh.status == "success"
        assert wh.amount_cents == 9900

    def test_028_verify_webhook_live_bad_sig_raises(self):
        prov = AlipayProvider(mode="mock")
        prov._client = mock.MagicMock()
        prov._client.verify.return_value = False
        prov.mode = "live"
        prov.app_id = "2021xxx"
        prov.private_key = "rsa-dummy"
        payload_dict = {
            "trade_status": "TRADE_SUCCESS",
            "out_trade_no": "ord_x",
            "total_amount": "10.00",
            "sign": "bad-sig",
        }
        with pytest.raises(WebhookVerificationError):
            prov.verify_webhook(
                payload=json.dumps(payload_dict).encode(),
                signature="bad-sig",
            )

    def test_029_alipay_graceful_degrade_with_invalid_key(self):
        """Invalid RSA key should NOT raise at live_mode() — degrade silently."""
        prov = AlipayProvider(mode="mock")
        prov.live_mode(app_id="2021xxx",
                       private_key="not-a-real-rsa-key",
                       public_key="not-a-real-rsa-key")
        # Client should be None (key invalid)
        assert prov._client is None
        assert prov.mode == "live"
        # create_payment should still work (degrade to synthesized live response)
        result = prov.create_payment(_make_order(currency="CNY"))
        assert result.payment_id
        assert result.raw.get("mode") == "live-no-sdk"


# ── 11-14. WeChat live mode ──────────────────────────────────────────
class TestWechatLiveMode:
    def test_030_constructor_without_app_id_raises(self, monkeypatch):
        monkeypatch.setenv("BILLING_WECHAT_MODE", "live")
        monkeypatch.delenv("WECHAT_APP_ID", raising=False)
        monkeypatch.setenv("WECHAT_MCH_ID", "1234")
        # Pass app_id="" explicitly to bypass the default fallback
        with pytest.raises(ProviderNotConfiguredError):
            WeChatPayProvider(app_id="", mch_id="1234")

    def test_031_constructor_without_mch_id_raises(self, monkeypatch):
        monkeypatch.setenv("BILLING_WECHAT_MODE", "live")
        monkeypatch.setenv("WECHAT_APP_ID", "wx_xxx")
        monkeypatch.delenv("WECHAT_MCH_ID", raising=False)
        with pytest.raises(ProviderNotConfiguredError):
            WeChatPayProvider(app_id="wx_xxx", mch_id="")

    def test_032_live_mode_fluent_switch(self):
        prov = WeChatPayProvider(mode="mock")
        assert prov.mode == "mock"
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        assert prov.mode == "live"
        assert prov.app_id == "wx_xxx"
        assert prov.mch_id == "1234567890"

    def test_033_live_mode_without_required_raises(self):
        prov = WeChatPayProvider(mode="mock")
        prov.app_id = ""
        prov.mch_id = ""
        with pytest.raises(ProviderNotConfiguredError):
            prov.live_mode()

    def test_034_create_payment_live_calls_wechatpy(self):
        prov = WeChatPayProvider(mode="mock")
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        # Patch the order.create method on the client
        fake_resp = mock.MagicMock()
        fake_resp.prepay_id = "wx_prepay_abc"
        fake_resp.code_url = "weixin://wxpay/bizpayurl?pr=abc"
        # Use a MagicMock for client and patch the method
        prov._client = mock.MagicMock()
        prov._client.order.create.return_value = fake_resp
        result = prov.create_payment(_make_order(order_id="ord_wx_001",
                                                 currency="CNY"))
        prov._client.order.create.assert_called_once()
        kwargs = prov._client.order.create.call_args.kwargs
        assert kwargs["trade_type"] == "NATIVE"
        assert kwargs["out_trade_no"] == "ord_wx_001"
        assert kwargs["total_fee"] == 9900
        assert result.payment_id == "wx_prepay_abc"
        assert result.checkout_url == "weixin://wxpay/bizpayurl?pr=abc"
        assert result.raw["mode"] == "live"

    def test_035_create_payment_live_propagates_sdk_error(self):
        prov = WeChatPayProvider(mode="mock")
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        prov._client = mock.MagicMock()
        from wechatpy.exceptions import WeChatPayException
        prov._client.order.create.side_effect = WeChatPayException(
            "FAIL", "mch_id格式错误"
        )
        with pytest.raises(RuntimeError, match="wechatpy.WeChatPay.order.create"):
            prov.create_payment(_make_order(currency="CNY"))

    def test_036_refund_live_calls_wechatpy_refund_apply(self):
        prov = WeChatPayProvider(mode="mock")
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        prov._client = mock.MagicMock()
        fake_refund = mock.MagicMock()
        fake_refund.refund_id = "wx_refund_real_001"
        fake_refund.result_code = "SUCCESS"
        prov._client.refund.apply.return_value = fake_refund
        r = prov.refund(_make_order(amount_cents=10000, currency="CNY",
                                    external_ref="wx_tx_seed"),
                        amount=50.00)
        prov._client.refund.apply.assert_called_once()
        kwargs = prov._client.refund.apply.call_args.kwargs
        assert kwargs["total_fee"] == 10000
        assert kwargs["refund_fee"] == 5000
        assert kwargs["transaction_id"] == "wx_tx_seed"
        assert r.refund_id == "wx_refund_real_001"
        assert r.amount_cents == 5000
        assert r.is_partial is True
        assert r.raw["mode"] == "live"

    def test_037_wechat_verify_webhook_live_v3_json(self):
        """WeChat v3 callback comes as JSON; live mode just decodes it."""
        prov = WeChatPayProvider(mode="mock")
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        payload = {
            "id": "wechat_evt_001",
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "out_trade_no": "ord_wx_001",
                "transaction_id": "wx_tx_001",
                "amount": {"total": 9900, "currency": "CNY"},
            },
        }
        wh = prov.verify_webhook(
            payload=json.dumps(payload).encode(),
            signature="ignored-in-live-v3",
        )
        assert wh.order_id == "ord_wx_001"
        assert wh.status == "success"
        assert wh.amount_cents == 9900

    def test_038_wechat_verify_webhook_live_v2_xml(self):
        """WeChat v2 callback comes as XML; live mode defers to wechatpy."""
        prov = WeChatPayProvider(mode="mock")
        prov.live_mode(app_id="wx_xxx", mch_id="1234567890", api_key="x" * 32)
        prov._client = mock.MagicMock()
        prov._client.parse_payment_result.return_value = {
            "out_trade_no": "ord_wx_002",
            "transaction_id": "wx_tx_002",
            "total_fee": "5000",
            "result_code": "SUCCESS",
        }
        # Live v2 path: payload is XML and signature is ignored (validated by SDK)
        # But our implementation also tries JSON parsing first. Use a non-JSON body.
        result = prov.verify_webhook(
            payload=b"<xml><foo>bar</foo></xml>",  # not JSON
            signature="",
        )
        prov._client.parse_payment_result.assert_called_once()
        assert result.order_id == "ord_wx_002"
        assert result.status == "success"

    def test_039_wechat_graceful_degrade_when_sdk_missing(self):
        """If wechatpy is unavailable, live mode degrades to live-no-sdk."""
        prov = WeChatPayProvider(mode="mock")
        prov.mode = "live"
        prov.app_id = "wx_xxx"
        prov.mch_id = "1234567890"
        prov.api_key = "x" * 32
        # Patch the module-level _wechat_sdk to return None (simulate missing)
        with mock.patch(
            "billing.payments.wechat_provider._wechat_sdk", return_value=None
        ):
            prov._client = None
            result = prov.create_payment(_make_order(currency="CNY"))
            assert result.raw.get("mode") == "live-no-sdk"
            # Refund also degrades (still inside the with block)
            r = prov.refund(_make_order(amount_cents=10000, currency="CNY",
                                        external_ref="wx_seed_x"),
                            amount=20.00)
            assert r.success
            assert r.raw.get("mode") == "live-no-sdk"


# ── 15. .env.example completeness ────────────────────────────────────
class TestEnvExampleCompleteness:
    def test_040_env_example_has_all_keys(self):
        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env.example"
        assert env_path.exists(), f".env.example not found at {env_path}"
        content = env_path.read_text(encoding="utf-8")
        required_keys = [
            "BILLING_STRIPE_MODE",
            "BILLING_ALIPAY_MODE",
            "BILLING_WECHAT_MODE",
            "STRIPE_API_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "ALIPAY_APP_ID",
            "ALIPAY_PRIVATE_KEY",
            "ALIPAY_PUBLIC_KEY",
            "WECHAT_APP_ID",
            "WECHAT_MCH_ID",
            "WECHAT_MCH_KEY",
        ]
        for key in required_keys:
            assert key in content, f".env.example missing key: {key}"


# ── 16. Mock mode regression (no SDK calls) ──────────────────────────
class TestMockModeRegression:
    def test_050_stripe_mock_mode_no_sdk_call(self):
        prov = StripeProvider(mode="mock")
        with mock.patch("stripe.checkout.Session.create") as m:
            result = prov.create_payment(_make_order())
        m.assert_not_called()
        assert result.raw["mode"] == "mock"
        assert result.checkout_url.startswith("https://checkout.stripe.com/")

    def test_051_alipay_mock_mode_no_sdk_call(self):
        prov = AlipayProvider(mode="mock")
        with mock.patch("alipay.AliPay.api_alipay_trade_page_pay",
                        create=True) as m:
            result = prov.create_payment(_make_order(currency="CNY"))
        m.assert_not_called()
        assert result.raw["mode"] == "mock"
        assert "openapi.alipay.com" in result.checkout_url

    def test_052_wechat_mock_mode_no_sdk_call(self):
        prov = WeChatPayProvider(mode="mock")
        with mock.patch.object(WeChatPayProvider, "_build_client") as m:
            result = prov.create_payment(_make_order(currency="CNY"))
        m.assert_not_called()
        assert result.raw["mode"] == "mock"
        assert result.checkout_url.startswith("weixin://wxpay/bizpayurl")

    def test_053_stripe_mock_refund_no_sdk_call(self):
        prov = StripeProvider(mode="mock")
        with mock.patch("stripe.Refund.create") as m:
            r = prov.refund(_make_order(external_ref="pi_test_1"), amount=5.00)
        m.assert_not_called()
        assert r.refund_id.startswith("re_mock_")
        assert r.raw["mode"] == "mock"

    def test_054_alipay_mock_refund_no_sdk_call(self):
        prov = AlipayProvider(mode="mock")
        with mock.patch("alipay.AliPay.api_alipay_trade_refund",
                        create=True) as m:
            r = prov.refund(_make_order(currency="CNY", external_ref="ali_seed"),
                            amount=5.00)
        m.assert_not_called()
        assert r.raw["mode"] == "mock"

    def test_055_wechat_mock_refund_no_sdk_call(self):
        prov = WeChatPayProvider(mode="mock")
        with mock.patch.object(WeChatPayProvider, "_build_client") as m:
            r = prov.refund(_make_order(currency="CNY", external_ref="wx_seed"),
                            amount=5.00)
        m.assert_not_called()
        assert r.raw["mode"] == "mock"


# ── 17. live_mode() idempotent / chainable ───────────────────────────
class TestLiveModeIdempotence:
    def test_060_stripe_live_mode_called_twice_no_error(self):
        prov = StripeProvider(mode="mock")
        prov.live_mode(api_key="sk_test_1")
        # Calling again should be idempotent
        prov.live_mode(api_key="sk_test_2")
        assert prov.mode == "live"
        assert prov.secret_key == "sk_test_2"

    def test_061_alipay_live_mode_returns_self(self):
        prov = AlipayProvider(mode="mock")
        result = prov.live_mode(app_id="2021x", private_key="x", public_key="y")
        assert result is prov  # fluent chain returns self

    def test_062_wechat_live_mode_returns_self(self):
        prov = WeChatPayProvider(mode="mock")
        result = prov.live_mode(app_id="wx_x", mch_id="1", api_key="y" * 32)
        assert result is prov


# ── 18. Env var override (BILLING_*_MODE) ────────────────────────────
class TestEnvModeOverride:
    def test_070_stripe_env_mode(self, monkeypatch):
        monkeypatch.setenv("BILLING_STRIPE_MODE", "live")
        monkeypatch.setenv("STRIPE_API_KEY", "sk_env_test")
        prov = StripeProvider()
        assert prov.mode == "live"
        assert prov.secret_key == "sk_env_test"

    def test_071_alipay_env_mode(self, monkeypatch):
        monkeypatch.setenv("BILLING_ALIPAY_MODE", "live")
        monkeypatch.setenv("ALIPAY_APP_ID", "2021env")
        monkeypatch.setenv("ALIPAY_PRIVATE_KEY", "env-rsa")
        prov = AlipayProvider()
        assert prov.mode == "live"
        assert prov.app_id == "2021env"

    def test_072_wechat_env_mode(self, monkeypatch):
        monkeypatch.setenv("BILLING_WECHAT_MODE", "live")
        monkeypatch.setenv("WECHAT_APP_ID", "wx_env")
        monkeypatch.setenv("WECHAT_MCH_ID", "9999")
        prov = WeChatPayProvider()
        assert prov.mode == "live"
        assert prov.mch_id == "9999"

    def test_073_stripe_default_mode_is_mock(self, monkeypatch):
        monkeypatch.delenv("BILLING_STRIPE_MODE", raising=False)
        prov = StripeProvider()
        assert prov.mode == "mock"
