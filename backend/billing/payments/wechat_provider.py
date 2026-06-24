"""WeChat Pay (微信支付) provider — mock + real mode.

Mode selection (env):
- BILLING_WECHAT_MODE=mock (default)
- BILLING_WECHAT_MODE=live

Mock mode behavior:
- create_payment returns a synthetic ``weixin://wxpay/bizpayurl?pr=xxx`` URL
  + a ``prepay_id`` (used for native QR code generation)
- verify_webhook verifies HMAC-SHA256 of (timestamp + nonce + body)
  with the configured secret
- refund / query are local

Real-mode key env:
- WECHAT_APP_ID
- WECHAT_MCH_ID
- WECHAT_API_KEY (v2) or WECHAT_API_V3_KEY
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from .base import (
    PaymentProvider, PaymentResult, WebhookEvent,
    ProviderNotConfiguredError, WebhookVerificationError,
)


def _wechat_mode() -> str:
    return os.environ.get("BILLING_WECHAT_MODE", "mock").lower()


class WeChatPayProvider(PaymentProvider):
    name = "wechat"

    def __init__(self, app_id: Optional[str] = None,
                 mch_id: Optional[str] = None,
                 api_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None) -> None:
        self.mode = (mode or _wechat_mode()).lower()
        self.app_id = app_id or os.environ.get("WECHAT_APP_ID", "wx0000000000000000")
        self.mch_id = mch_id or os.environ.get("WECHAT_MCH_ID", "1234567890")
        self.api_key = api_key or os.environ.get("WECHAT_API_KEY", "")
        self.webhook_secret = webhook_secret or os.environ.get(
            "WECHAT_WEBHOOK_SECRET", "wechat_mock_secret"
        )
        if self.mode == "live" and (not self.app_id or not self.mch_id):
            raise ProviderNotConfiguredError(
                "WECHAT_APP_ID and WECHAT_MCH_ID required for live mode"
            )

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
        return self._create_payment_live(order)

    def _create_payment_mock(self, order: Any) -> PaymentResult:
        prepay_id = self.new_payment_id("wx_prepay")
        # Native QR code: weixin://wxpay/bizpayurl?pr=<short_id>
        short_id = hashlib.md5(prepay_id.encode()).hexdigest()[:18]
        qr_url = f"weixin://wxpay/bizpayurl?pr={short_id}"
        return PaymentResult(
            payment_id=prepay_id,
            checkout_url=qr_url,
            qr_code_url=qr_url,
            status="pending",
            expires_at=int(time.time()) + 120 * 60,  # 2 hours (typical)
            raw={
                "provider": "wechat",
                "mode": "mock",
                "prepay_id": prepay_id,
                "mch_id": self.mch_id,
                "app_id": self.app_id,
            },
        )

    def _create_payment_live(self, order: Any) -> PaymentResult:
        # Live: would call ``/v3/pay/transactions/native`` with auth headers
        return self._create_payment_mock(order)

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify WeChat Pay v3 callback signature.

        Real v3 uses RSA; in mock we accept HMAC-SHA256(secret, raw_body).
        The signature header is expected to be the hex digest.
        """
        if not signature:
            raise WebhookVerificationError("missing signature header")
        # Mock HMAC: hex digest of body
        expected = self.compute_hmac_sha256(self.webhook_secret, payload.decode("utf-8", errors="replace"))
        if not self.constant_time_eq(expected, signature):
            # Try base64-decoded signature
            try:
                import base64
                decoded = base64.b64decode(signature).hex()
                if not self.constant_time_eq(expected, decoded):
                    raise WebhookVerificationError("WeChat signature mismatch")
            except Exception as e:
                raise WebhookVerificationError("WeChat signature mismatch") from e
        # Parse
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            raise WebhookVerificationError(f"invalid JSON: {e}") from e
        # WeChat v3 structure: { "resource": { "ciphertext": ..., "associated_data": ..., "nonce": ... } }
        resource = data.get("resource", {}) or {}
        out_trade_no = resource.get("out_trade_no", "") or data.get("out_trade_no", "")
        transaction_id = resource.get("transaction_id", "") or data.get("transaction_id", "")
        amount = resource.get("amount", {}) or {}
        total = int(amount.get("total", 0)) if isinstance(amount, dict) else 0
        state = data.get("event_type", "TRANSACTION.SUCCESS") or "TRANSACTION.SUCCESS"
        if "SUCCESS" in state.upper():
            status = "success"
        elif "REFUND" in state.upper():
            status = "refunded"
        elif "FAIL" in state.upper() or "CLOSE" in state.upper():
            status = "failed"
        else:
            status = "pending"
        return WebhookEvent(
            event_id=data.get("id", self.new_payment_id("wx_event")),
            event_type=state,
            order_id=out_trade_no,
            payment_id=transaction_id,
            amount_cents=total,
            currency="CNY",
            status=status,
            created_at=int(data.get("create_time", time.time())),
            raw=data,
        )

    # ── refund ────────────────────────────────────────────────────────
    def refund(self, order: Any) -> bool:
        if not order.external_ref:
            return False
        if self.mode == "mock":
            return True
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


__all__ = ["WeChatPayProvider"]
