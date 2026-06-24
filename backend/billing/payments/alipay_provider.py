"""Alipay (支付宝) payment provider — mock + real mode.

Mode selection (env):
- BILLING_ALIPAY_MODE=mock (default)
- BILLING_ALIPAY_MODE=live (would call real Alipay Open API)

Mock mode behavior:
- create_payment returns a synthetic alipay:// URL and trade_no
- verify_webhook verifies HMAC-SHA256 of the payload using the configured secret
  (in mock mode, defaults to "alipay_mock_secret")
- refund / query are local

Alipay sign scheme (mock simplified):
    sign = HMAC-SHA256(secret, sorted_query_string)
    where sorted_query_string = key1=value1&key2=value2&... (alphabetical, no sign key)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from typing import Any, Dict, Optional

from .base import (
    PaymentProvider, PaymentResult, WebhookEvent,
    ProviderNotConfiguredError, WebhookVerificationError,
)


def _alipay_mode() -> str:
    return os.environ.get("BILLING_ALIPAY_MODE", "mock").lower()


class AlipayProvider(PaymentProvider):
    name = "alipay"

    def __init__(self, app_id: Optional[str] = None,
                 private_key: Optional[str] = None,
                 public_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None,
                 api_base: str = "https://openapi.alipay.com/gateway.do") -> None:
        self.mode = (mode or _alipay_mode()).lower()
        self.app_id = app_id or os.environ.get("ALIPAY_APP_ID", "2021000000000000")
        self.private_key = private_key or os.environ.get("ALIPAY_PRIVATE_KEY", "")
        self.public_key = public_key or os.environ.get("ALIPAY_PUBLIC_KEY", "")
        self.webhook_secret = webhook_secret or os.environ.get(
            "ALIPAY_WEBHOOK_SECRET", "alipay_mock_secret"
        )
        self.api_base = api_base
        if self.mode == "live" and (not self.app_id or not self.private_key):
            raise ProviderNotConfiguredError(
                "ALIPAY_APP_ID and ALIPAY_PRIVATE_KEY required for live mode"
            )

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
        # Strip sign / sign_type when verifying (real Alipay excludes these)
        params_no_sign = {k: v for k, v in params.items()
                          if k not in ("sign", "sign_type")}
        expected = self._sign(params_no_sign)
        return self.constant_time_eq(expected, sign)

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
        return self._create_payment_live(order)

    def _create_payment_mock(self, order: Any) -> PaymentResult:
        pay_id = self.new_payment_id("alipay_trade")
        # Build alipay trade params
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
        # Synthesize a redirect URL
        encoded = urllib.parse.urlencode({**params, "sign": sign})
        checkout_url = f"{self.api_base}?{encoded}"
        return PaymentResult(
            payment_id=pay_id,
            checkout_url=checkout_url,
            qr_code_url=None,
            status="pending",
            expires_at=int(time.time()) + 900,  # 15 min typical
            raw={"provider": "alipay", "mode": "mock", "trade_no": pay_id},
        )

    def _create_payment_live(self, order: Any) -> PaymentResult:
        # Live: would POST to alipay.trade.page.pay with RSA-signed biz_content
        return self._create_payment_mock(order)

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify Alipay async notify signature.

        payload: JSON-encoded params (with sign field included or excluded)
        signature: the value of the ``sign`` field
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise WebhookVerificationError(f"invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise WebhookVerificationError("payload must be object")
        sign = data.get("sign", signature)
        if not sign:
            raise WebhookVerificationError("missing sign field")
        # Verify
        if not self._verify_sign(data, sign):
            raise WebhookVerificationError("Alipay signature mismatch")
        # Decode
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
            event_id=self.new_payment_id("alipay_notify"),
            event_type=f"alipay.{trade_status.lower()}" if trade_status else "alipay.notify",
            order_id=data.get("out_trade_no", ""),
            payment_id=data.get("trade_no", ""),
            amount_cents=int(float(data.get("total_amount", 0)) * 100),
            currency="CNY",
            status=status,
            created_at=int(time.time()),
            raw=data,
        )

    # ── refund ────────────────────────────────────────────────────────
    def refund(self, order: Any) -> bool:
        if not order.external_ref:
            return False
        if self.mode == "mock":
            return True
        # Live: alipay.trade.refund
        return True

    # ── query ─────────────────────────────────────────────────────────
    def query(self, order: Any) -> str:
        if order.status.value in ("paid", "fulfilled"):
            return "success"
        if order.status.value == "failed":
            return "failed"
        if order.status.value == "refunded":
            return "refunded"
        return "pending"


__all__ = ["AlipayProvider"]
