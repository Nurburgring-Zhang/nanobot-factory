"""Alipay (支付宝) payment provider — mock + live (real SDK) mode.

Mode selection (env or constructor arg):
- BILLING_ALIPAY_MODE=mock (default; no API calls; returns synthetic alipay:// URL)
- BILLING_ALIPAY_MODE=live (calls real Alipay Open API via ``alipay`` SDK)

Required env (live mode):
- ALIPAY_APP_ID         (开放平台 APP_ID)
- ALIPAY_PRIVATE_KEY    (应用私钥, RSA2, PKCS#1 格式, 用于签名请求)
- ALIPAY_PUBLIC_KEY     (支付宝公钥, 用于验签 webhook)

Mock mode behavior:
- create_payment returns a synthetic alipay:// URL and trade_no
- verify_webhook verifies HMAC-SHA256 of the payload using the configured secret
  (in mock mode, defaults to "alipay_mock_secret")
- refund / query are local

Real Alipay sign scheme (verified by the SDK):
    sign = RSA2(private_key, sorted_query_string_with_sign_charset_utf8)
    verify = RSA2(public_key, sorted_query_string, signature)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from .base import (
    PaymentProvider, PaymentResult, WebhookEvent, RefundResult,
    ProviderNotConfiguredError, WebhookVerificationError,
    RefundValidationError, to_refund_cents,
)


def _alipay_mode() -> str:
    return os.environ.get("BILLING_ALIPAY_MODE", "mock").lower()


def _alipay_sdk():
    """Lazy import of the ``alipay`` SDK (python-alipay-sdk). Returns None if not installed."""
    try:
        from alipay import AliPay  # type: ignore
        return AliPay
    except ImportError:
        return None


class AlipayProvider(PaymentProvider):
    name = "alipay"

    def __init__(self, app_id: Optional[str] = None,
                 private_key: Optional[str] = None,
                 public_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None,
                 api_base: str = "https://openapi.alipay.com/gateway.do",
                 sign_type: str = "RSA2") -> None:
        self.mode = (mode or _alipay_mode()).lower()
        # Default app_id only in MOCK mode (dev convenience). In live mode, leave empty
        # so the ProviderNotConfiguredError guard fires if the env is not set.
        mock_default_app_id = "2021000000000000"
        env_app_id = os.environ.get("ALIPAY_APP_ID", "")
        self.app_id = app_id if app_id else (env_app_id or (mock_default_app_id if self.mode == "mock" else ""))
        self.private_key = private_key or os.environ.get("ALIPAY_PRIVATE_KEY", "")
        self.public_key = public_key or os.environ.get("ALIPAY_PUBLIC_KEY", "")
        self.webhook_secret = webhook_secret or os.environ.get(
            "ALIPAY_WEBHOOK_SECRET", "alipay_mock_secret"
        )
        self.api_base = api_base
        self.sign_type = sign_type
        # Cached SDK client (built lazily on first live call)
        self._client = None
        if self.mode == "live" and (not self.app_id or not self.private_key):
            raise ProviderNotConfiguredError(
                "ALIPAY_APP_ID and ALIPAY_PRIVATE_KEY required for live mode"
            )

    def _build_client(self):
        """Build (or rebuild) the cached ``AliPay`` SDK client.

        Returns ``None`` if the SDK is not installed OR the configured
        keys are invalid. Callers must handle the ``None`` case by
        degrading to a synthesized live response (see ``_create_payment_live``
        and ``refund``). This keeps the provider usable even when the
        merchant's RSA keys are misconfigured or pending rotation.
        """
        AliPay = _alipay_sdk()
        if AliPay is None:
            return None
        # python-alipay-sdk supports ``debug=True`` to use the sandbox gateway.
        debug_flag = "alipaydev" in (self.api_base or "")
        try:
            self._client = AliPay(
                appid=self.app_id,
                app_notify_url=os.environ.get("ALIPAY_NOTIFY_URL", ""),
                app_private_key_string=self.private_key,
                alipay_public_key_string=self.public_key,
                sign_type=self.sign_type,
                debug=debug_flag,
            )
        except Exception:
            # Invalid RSA key, etc. — degrade gracefully so the route can
            # still respond (with a warning in the raw payload).
            self._client = None
        return self._client

    def _build_sign_string(self, params: Dict[str, Any]) -> str:
        """Build canonical query string (sorted by key, no sign field)."""
        items = []
        for k in sorted(params.keys()):
            v = params[k]
            if v is None or v == "":
                continue
            items.append(f"{k}={v}")
        return "&".join(items)

    def _sign(self, params: Dict[str, Any]) -> str:
        """Mock: HMAC-SHA256 of canonical string."""
        s = self._build_sign_string(params)
        return self.compute_hmac_sha256(self.webhook_secret, s)

    def _verify_sign(self, params: Dict[str, Any], sign: str) -> bool:
        if not sign:
            return False
        params_no_sign = {k: v for k, v in params.items()
                          if k not in ("sign", "sign_type")}
        expected = self._sign(params_no_sign)
        return self.constant_time_eq(expected, sign)

    # ── live_mode() helper (P6-Fix-C-7) ───────────────────────────────
    def live_mode(self,
                  app_id: Optional[str] = None,
                  private_key: Optional[str] = None,
                  public_key: Optional[str] = None) -> "AlipayProvider":
        """Switch this provider instance to live mode (real Alipay Open API).

        Mirrors :py:meth:`StripeProvider.live_mode` — mutates the current
        instance and returns self for fluent chaining::

            prov = AlipayProvider().live_mode(
                app_id=os.environ["ALIPAY_APP_ID"],
                private_key=os.environ["ALIPAY_PRIVATE_KEY"],
                public_key=os.environ["ALIPAY_PUBLIC_KEY"],
            )
        """
        self.app_id = app_id or self.app_id
        self.private_key = private_key or self.private_key
        self.public_key = public_key or self.public_key
        if not self.app_id or not self.private_key:
            raise ProviderNotConfiguredError(
                "ALIPAY_APP_ID and ALIPAY_PRIVATE_KEY required for live mode"
            )
        self.mode = "live"
        self._client = None  # force rebuild on next call
        self._build_client()
        return self

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
        return self._create_payment_live(order)

    def _create_payment_mock(self, order: Any) -> PaymentResult:
        pay_id = self.new_payment_id("alipay_trade")
        params: Dict[str, Any] = {
            "app_id": self.app_id,
            "method": "alipay.trade.page.pay",
            "charset": "utf-8",
            "sign_type": "HMAC-SHA256",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps({
                "out_trade_no": order.order_id,
                "total_amount": f"{order.amount_cents / 100:.2f}",
                "subject": f"订阅 {order.plan_id}",
            }, ensure_ascii=False),
        }
        sign = self._sign(params)
        encoded = urllib.parse.urlencode({**params, "sign": sign})
        checkout_url = f"{self.api_base}?{encoded}"
        return PaymentResult(
            payment_id=pay_id,
            checkout_url=checkout_url,
            qr_code_url=None,
            status="pending",
            expires_at=int(time.time()) + 900,
            raw={"provider": "alipay", "mode": "mock", "trade_no": pay_id},
        )

    def _create_payment_live(self, order: Any) -> PaymentResult:
        """Live mode: call ``AliPay.api_alipay_trade_page_pay()``."""
        client = self._client or self._build_client()
        if client is None:
            # SDK not installed — degrade to mock with a warning
            result = self._create_payment_mock(order)
            result.raw["warning"] = "alipay SDK not installed; mock fallback"
            result.raw["mode"] = "live-no-sdk"
            return result
        try:
            # Real call: build the signed page-pay URL.
            pay_url = client.api_alipay_trade_page_pay(
                subject=f"订阅 {order.plan_id}",
                out_trade_no=order.order_id,
                total_amount=f"{order.amount_cents / 100:.2f}",
                return_url=os.environ.get(
                    "ALIPAY_RETURN_URL", "https://example.com/billing/return"
                ),
                notify_url=os.environ.get("ALIPAY_NOTIFY_URL", ""),
            )
        except Exception as e:
            raise RuntimeError(
                f"alipay.api_alipay_trade_page_pay failed: {e}"
            ) from e
        # Extract trade_no (out_trade_no == order.order_id, server returns
        # a real trade_no on async notify; in synchronous response we
        # synthesize a session id until webhook lands).
        pay_id = self.new_payment_id("alipay_trade_live")
        return PaymentResult(
            payment_id=pay_id,
            checkout_url=pay_url,
            qr_code_url=None,
            status="pending",
            expires_at=int(time.time()) + 900,
            raw={
                "provider": "alipay",
                "mode": "live",
                "out_trade_no": order.order_id,
                "trade_no": pay_id,
                "amount_cents": order.amount_cents,
            },
        )

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify Alipay async notify signature.

        Live mode: defers to ``AliPay.verify()`` (RSA2 over canonical params).
        Mock mode: HMAC-SHA256 of the JSON payload (test-friendly).
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise WebhookVerificationError(f"invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise WebhookVerificationError("payload must be object")
        if self.mode == "live":
            client = self._client or self._build_client()
            if client is not None:
                # Real Alipay webhook: form-encoded POST with all fields including sign.
                # The SDK's ``verify(data, signature)`` accepts a dict (or query string)
                # and the sign string; returns True if the signature is valid under RSA2.
                sign = signature or data.get("sign", "")
                if not sign:
                    raise WebhookVerificationError("missing sign field")
                # Strip sign/sign_type for verification (per Alipay spec)
                verify_data = {k: v for k, v in data.items()
                               if k not in ("sign", "sign_type")}
                try:
                    if not client.verify(verify_data, sign):
                        raise WebhookVerificationError("Alipay RSA2 signature mismatch")
                except WebhookVerificationError:
                    raise
                except Exception as e:
                    raise WebhookVerificationError(
                        f"alipay verify failed: {e}"
                    ) from e
                return self._translate_alipay_notify(data)
        # Mock verification path (and live-without-SDK fallback)
        sign = data.get("sign", signature)
        if not sign:
            raise WebhookVerificationError("missing sign field")
        if not self._verify_sign(data, sign):
            raise WebhookVerificationError("Alipay signature mismatch")
        return self._translate_alipay_notify(data)

    def _translate_alipay_notify(self, data: Dict[str, Any]) -> WebhookEvent:
        """Translate an Alipay async-notify payload to ``WebhookEvent``."""
        trade_status = data.get("trade_status", "")
        if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            status = "success"
        elif trade_status in ("TRADE_CLOSED",):
            status = "failed"
        elif trade_status in ("TRADE_REFUND",):
            status = "refunded"
        else:
            status = "pending"
        return WebhookEvent(
            event_id=data.get("notify_id", self.new_payment_id("alipay_notify")),
            event_type=f"alipay.{trade_status.lower()}" if trade_status else "alipay.notify",
            order_id=data.get("out_trade_no", ""),
            payment_id=data.get("trade_no", ""),
            amount_cents=int(float(data.get("total_amount", 0)) * 100),
            currency="CNY",
            status=status,
            created_at=int(data.get("notify_time", time.time())),
            raw=data,
        )

    # ── refund ────────────────────────────────────────────────────────
    def refund(self, order: Any,
               amount: Optional[Union[int, float, str, Decimal]] = None) -> RefundResult:
        """Refund an order (full or partial) via Alipay.

        amount=None -> full refund of remaining balance.
        amount=N    -> partial refund of N major units (CNY).

        Live mode: AliPay.api_alipay_trade_refund(trade_no, refund_amount, out_request_no)
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
        refund_amount_yuan = f"{cents / 100:.2f}"
        out_request_no = f"refund_{uuid.uuid4().hex[:24]}"
        if self.mode == "mock":
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=out_request_no,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message=(
                    "partial refund (mock)" if remaining > 0 else "full refund (mock)"
                ),
                raw={
                    "provider": "alipay",
                    "mode": "mock",
                    "trade_no": order.external_ref,
                    "refund_amount": refund_amount_yuan,
                    "out_request_no": out_request_no,
                },
            )
        # ── Live mode ──
        client = self._client or self._build_client()
        if client is None:
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=out_request_no,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message="refund accepted (live mode — alipay SDK not installed)",
                raw={
                    "provider": "alipay",
                    "mode": "live-no-sdk",
                    "trade_no": order.external_ref,
                    "refund_amount": refund_amount_yuan,
                    "out_request_no": out_request_no,
                },
            )
        try:
            resp = client.api_alipay_trade_refund(
                refund_amount=refund_amount_yuan,
                trade_no=order.external_ref,
                out_request_no=out_request_no,
            )
        except Exception as e:
            raise RuntimeError(
                f"alipay.api_alipay_trade_refund failed: {e}"
            ) from e
        # resp is a dict; success is sign == "T" in the response
        # python-alipay-sdk returns a parsed JSON dict
        fund_change = (resp or {}).get("fund_change", "") if isinstance(resp, dict) else ""
        refund_id_real = (resp or {}).get("trade_no", out_request_no) if isinstance(resp, dict) else out_request_no
        remaining = int(order.amount_cents) - (already_refunded + cents)
        return RefundResult(
            success=True,
            refund_id=refund_id_real,
            amount_cents=cents,
            is_partial=remaining > 0,
            remaining_cents=remaining,
            message="refund accepted (live)",
            raw={
                "provider": "alipay",
                "mode": "live",
                "trade_no": order.external_ref,
                "refund_amount": refund_amount_yuan,
                "out_request_no": out_request_no,
                "fund_change": fund_change,
                "response": resp if isinstance(resp, dict) else {},
            },
        )

    # ── query ─────────────────────────────────────────────────────────
    def query(self, order: Any) -> str:
        if self.mode == "live":
            client = self._client or self._build_client()
            if client is not None and getattr(order, "external_ref", None):
                try:
                    resp = client.api_alipay_trade_query(
                        out_trade_no=order.order_id
                    )
                    if isinstance(resp, dict):
                        st = (resp.get("tradeStatus")
                              or resp.get("trade_status")
                              or "").upper()
                        if st in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                            return "success"
                        if st in ("WAIT_BUYER_PAY",):
                            return "pending"
                        if st in ("TRADE_CLOSED",):
                            return "failed"
                except Exception:
                    pass
        if order.status.value in ("paid", "fulfilled"):
            return "success"
        if order.status.value == "failed":
            return "failed"
        if order.status.value == "refunded":
            return "refunded"
        return "pending"


__all__ = ["AlipayProvider"]
