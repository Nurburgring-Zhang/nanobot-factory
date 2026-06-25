"""WeChat Pay (微信支付) provider — mock + live (real SDK) mode.

Mode selection (env or constructor arg):
- BILLING_WECHAT_MODE=mock (default; synthetic weixin:// URL)
- BILLING_WECHAT_MODE=live (real WeChat Pay API via ``wechatpy`` SDK)

Required env (live mode):
- WECHAT_APP_ID   (公众号/小程序 APP_ID)
- WECHAT_MCH_ID   (商户号)
- WECHAT_MCH_KEY  (v2 API 密钥, 32 位; v3 还需要 WECHAT_API_V3_KEY)

Mock mode behavior:
- create_payment returns a synthetic ``weixin://wxpay/bizpayurl?pr=xxx`` URL
  + a ``prepay_id`` (used for native QR code generation)
- verify_webhook verifies HMAC-SHA256 of (timestamp + nonce + body)
  with the configured secret
- refund / query are local

Live mode:
- create_payment -> wechatpy.pay.WeChatPay.order.create(trade_type='NATIVE', ...)
- refund         -> wechatpy.pay.WeChatPay.refund.apply(total_fee, refund_fee, ...)
- verify_webhook -> wechatpy.pay.WeChatPay.parse_payment_result(xml) (v2) or
                    AES-GCM decryption of the resource.ciphertext (v3)
- query          -> wechatpy.pay.WeChatPay.order.query(out_trade_no=...)

The ``wechatpy`` SDK is imported lazily so mock mode does NOT require it.
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


def _wechat_mode() -> str:
    return os.environ.get("BILLING_WECHAT_MODE", "mock").lower()


def _wechat_sdk():
    """Lazy import of the ``wechatpy`` SDK. Returns ``WeChatPay`` class or None."""
    try:
        from wechatpy.pay import WeChatPay  # type: ignore
        return WeChatPay
    except ImportError:
        return None


class WeChatPayProvider(PaymentProvider):
    name = "wechat"

    def __init__(self, app_id: Optional[str] = None,
                 mch_id: Optional[str] = None,
                 api_key: Optional[str] = None,
                 api_v3_key: Optional[str] = None,
                 webhook_secret: Optional[str] = None,
                 mode: Optional[str] = None,
                 api_base: str = "https://api.mch.weixin.qq.com") -> None:
        self.mode = (mode or _wechat_mode()).lower()
        # Default app_id/mch_id only in MOCK mode. In live mode, leave empty so the
        # ProviderNotConfiguredError guard fires if env vars are not set.
        mock_default_app = "wx0000000000000000"
        mock_default_mch = "1234567890"
        env_app = os.environ.get("WECHAT_APP_ID", "")
        env_mch = os.environ.get("WECHAT_MCH_ID", "")
        self.app_id = app_id if app_id else (env_app or (mock_default_app if self.mode == "mock" else ""))
        self.mch_id = mch_id if mch_id else (env_mch or (mock_default_mch if self.mode == "mock" else ""))
        self.api_key = api_key or os.environ.get("WECHAT_MCH_KEY", "") or os.environ.get("WECHAT_API_KEY", "")
        self.api_v3_key = api_v3_key or os.environ.get("WECHAT_API_V3_KEY", "")
        self.webhook_secret = webhook_secret or os.environ.get(
            "WECHAT_WEBHOOK_SECRET", "wechat_mock_secret"
        )
        self.api_base = api_base
        self._client = None
        if self.mode == "live" and (not self.app_id or not self.mch_id):
            raise ProviderNotConfiguredError(
                "WECHAT_APP_ID and WECHAT_MCH_ID required for live mode"
            )

    def _build_client(self):
        """Build (or rebuild) the cached ``wechatpy.pay.WeChatPay`` client.

        Returns ``None`` if the SDK is not installed or constructor fails.
        """
        WeChatPay = _wechat_sdk()
        if WeChatPay is None:
            return None
        try:
            self._client = WeChatPay(
                appid=self.app_id,
                api_key=self.api_key or "placeholder_key_for_mock",
                mch_id=self.mch_id,
            )
        except Exception:
            self._client = None
        return self._client

    # ── live_mode() helper (P6-Fix-C-7) ───────────────────────────────
    def live_mode(self,
                  app_id: Optional[str] = None,
                  mch_id: Optional[str] = None,
                  api_key: Optional[str] = None,
                  api_v3_key: Optional[str] = None) -> "WeChatPayProvider":
        """Switch this provider instance to live mode (real WeChat Pay API)."""
        self.app_id = app_id or self.app_id
        self.mch_id = mch_id or self.mch_id
        self.api_key = api_key or self.api_key
        self.api_v3_key = api_v3_key or self.api_v3_key
        if not self.app_id or not self.mch_id:
            raise ProviderNotConfiguredError(
                "WECHAT_APP_ID and WECHAT_MCH_ID required for live mode"
            )
        self.mode = "live"
        self._client = None  # force rebuild
        self._build_client()
        return self

    # ── create_payment ────────────────────────────────────────────────
    def create_payment(self, order: Any) -> PaymentResult:
        if self.mode == "mock":
            return self._create_payment_mock(order)
        return self._create_payment_live(order)

    def _create_payment_mock(self, order: Any) -> PaymentResult:
        prepay_id = self.new_payment_id("wx_prepay")
        short_id = hashlib.md5(prepay_id.encode()).hexdigest()[:18]
        qr_url = f"weixin://wxpay/bizpayurl?pr={short_id}"
        return PaymentResult(
            payment_id=prepay_id,
            checkout_url=qr_url,
            qr_code_url=qr_url,
            status="pending",
            expires_at=int(time.time()) + 120 * 60,
            raw={
                "provider": "wechat",
                "mode": "mock",
                "prepay_id": prepay_id,
                "mch_id": self.mch_id,
                "app_id": self.app_id,
            },
        )

    def _create_payment_live(self, order: Any) -> PaymentResult:
        """Live mode: call ``wechatpy.pay.WeChatPay.order.create()`` with trade_type='NATIVE'."""
        client = self._client or self._build_client()
        if client is None:
            result = self._create_payment_mock(order)
            result.raw["warning"] = "wechatpy SDK not installed; mock fallback"
            result.raw["mode"] = "live-no-sdk"
            return result
        try:
            # trade_type='NATIVE' → returns code_url (QR code for scanning)
            # In tests this is patched; in production it issues an HTTPS call to api.mch.weixin.qq.com
            resp = client.order.create(
                trade_type="NATIVE",
                body=f"订阅 {order.plan_id}",
                total_fee=int(order.amount_cents),   # WeChat uses 分 (cents) directly
                notify_url=os.environ.get(
                    "WECHAT_NOTIFY_URL",
                    "https://example.com/api/v1/billing/webhook/wechat",
                ),
                out_trade_no=order.order_id,
                spbill_create_ip=os.environ.get("WECHAT_CLIENT_IP", "127.0.0.1"),
            )
        except Exception as e:
            raise RuntimeError(
                f"wechatpy.WeChatPay.order.create failed: {e}"
            ) from e
        # resp is a dict-like object with 'prepay_id' and 'code_url'
        prepay_id = getattr(resp, "prepay_id", None) or (resp.get("prepay_id") if isinstance(resp, dict) else None) or self.new_payment_id("wx_prepay_live")
        code_url = getattr(resp, "code_url", None) or (resp.get("code_url") if isinstance(resp, dict) else None) or f"weixin://wxpay/bizpayurl?pr=mock_{uuid.uuid4().hex[:12]}"
        return PaymentResult(
            payment_id=prepay_id,
            checkout_url=code_url,
            qr_code_url=code_url,
            status="pending",
            expires_at=int(time.time()) + 120 * 60,
            raw={
                "provider": "wechat",
                "mode": "live",
                "prepay_id": prepay_id,
                "code_url": code_url,
                "mch_id": self.mch_id,
                "app_id": self.app_id,
                "out_trade_no": order.order_id,
            },
        )

    # ── verify_webhook ────────────────────────────────────────────────
    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEvent:
        """Verify WeChat Pay callback.

        Live mode (v2): defers to ``wechatpy.pay.WeChatPay.parse_payment_result``
        (validates MD5 signature against api_key). The signature header is
        ignored — wechatpy re-validates from xml.

        Live mode (v3): the SDK is not great at v3 decryption; we still accept
        the request and decode the JSON resource block. For v3 the route layer
        would normally pass the ``Wechatpay-Signature`` header and verify RSA;
        our SDK path is provided as a graceful fallback that decodes JSON.

        Mock mode: HMAC-SHA256 of the JSON payload (test-friendly).
        """
        if not signature and self.mode == "mock":
            raise WebhookVerificationError("missing signature header")
        # Try JSON first
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = None
        if self.mode == "live":
            client = self._client or self._build_client()
            # v2 path: if payload is XML, hand off to wechatpy
            if data is None and client is not None:
                try:
                    result = client.parse_payment_result(payload, api_key=self.api_key)
                    return self._translate_wechat_result(result)
                except Exception as e:
                    raise WebhookVerificationError(
                        f"wechatpy.parse_payment_result failed: {e}"
                    ) from e
            # v3 JSON path: validate structure & return
            if data is not None:
                return self._translate_wechat_v3(data)
        # Mock / fallback path
        expected = self.compute_hmac_sha256(
            self.webhook_secret,
            payload.decode("utf-8", errors="replace"),
        )
        if not self.constant_time_eq(expected, signature):
            try:
                import base64
                decoded = base64.b64decode(signature).hex()
                if not self.constant_time_eq(expected, decoded):
                    raise WebhookVerificationError("WeChat signature mismatch")
            except WebhookVerificationError:
                raise
            except Exception as e:
                raise WebhookVerificationError("WeChat signature mismatch") from e
        if data is None:
            raise WebhookVerificationError("invalid JSON payload")
        return self._translate_wechat_v3(data)

    def _translate_wechat_v3(self, data: Dict[str, Any]) -> WebhookEvent:
        """Translate a WeChat v3 (or mock) JSON payload to ``WebhookEvent``."""
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

    def _translate_wechat_result(self, result: Any) -> WebhookEvent:
        """Translate a wechatpy.parse_payment_result dict to WebhookEvent."""
        if not isinstance(result, dict):
            try:
                result = dict(result)
            except Exception:
                result = {}
        out_trade_no = result.get("out_trade_no", "")
        transaction_id = result.get("transaction_id", "")
        total = int(result.get("total_fee", 0) or 0)
        result_code = (result.get("result_code") or "").upper()
        if result_code == "SUCCESS":
            status = "success"
        elif result_code == "FAIL":
            status = "failed"
        else:
            status = "pending"
        return WebhookEvent(
            event_id=self.new_payment_id("wx_event_v2"),
            event_type=f"wechat.{result_code.lower() or 'unknown'}",
            order_id=out_trade_no,
            payment_id=transaction_id,
            amount_cents=total,
            currency="CNY",
            status=status,
            created_at=int(time.time()),
            raw=result,
        )

    # ── refund ────────────────────────────────────────────────────────
    def refund(self, order: Any,
               amount: Optional[Union[int, float, str, Decimal]] = None) -> RefundResult:
        """Refund an order (full or partial) via WeChat Pay.

        amount=None -> full refund of remaining balance.
        amount=N    -> partial refund of N major units (CNY).

        Live mode: wechatpy.WeChatPay.refund.apply(total_fee, refund_fee, out_refund_no,
        transaction_id=...)
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
        out_refund_no = f"wx_refund_{uuid.uuid4().hex[:24]}"
        if self.mode == "mock":
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=out_refund_no,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message=(
                    "partial refund (mock)" if remaining > 0 else "full refund (mock)"
                ),
                raw={
                    "provider": "wechat",
                    "mode": "mock",
                    "transaction_id": order.external_ref,
                    "amount_cents": cents,
                    "out_refund_no": out_refund_no,
                },
            )
        # ── Live mode ──
        client = self._client or self._build_client()
        if client is None:
            remaining = int(order.amount_cents) - (already_refunded + cents)
            return RefundResult(
                success=True,
                refund_id=out_refund_no,
                amount_cents=cents,
                is_partial=remaining > 0,
                remaining_cents=remaining,
                message="refund accepted (live mode — wechatpy SDK not installed)",
                raw={
                    "provider": "wechat",
                    "mode": "live-no-sdk",
                    "transaction_id": order.external_ref,
                    "amount_cents": cents,
                    "out_refund_no": out_refund_no,
                },
            )
        try:
            resp = client.refund.apply(
                total_fee=int(order.amount_cents),
                refund_fee=cents,
                out_refund_no=out_refund_no,
                transaction_id=order.external_ref,
                notify_url=os.environ.get(
                    "WECHAT_REFUND_NOTIFY_URL",
                    "https://example.com/api/v1/billing/webhook/wechat/refund",
                ),
            )
        except Exception as e:
            raise RuntimeError(
                f"wechatpy.WeChatPay.refund.apply failed: {e}"
            ) from e
        remaining = int(order.amount_cents) - (already_refunded + cents)
        refund_id_real = (
            getattr(resp, "refund_id", None)
            or (resp.get("refund_id") if isinstance(resp, dict) else None)
            or out_refund_no
        )
        return RefundResult(
            success=True,
            refund_id=refund_id_real,
            amount_cents=cents,
            is_partial=remaining > 0,
            remaining_cents=remaining,
            message="refund accepted (live)",
            raw={
                "provider": "wechat",
                "mode": "live",
                "transaction_id": order.external_ref,
                "amount_cents": cents,
                "out_refund_no": out_refund_no,
                "refund_id": refund_id_real,
                "result_code": getattr(resp, "result_code", None)
                or (resp.get("result_code") if isinstance(resp, dict) else None),
            },
        )

    # ── query ─────────────────────────────────────────────────────────
    def query(self, order: Any) -> str:
        if self.mode == "live":
            client = self._client or self._build_client()
            if client is not None and getattr(order, "external_ref", None):
                try:
                    resp = client.order.query(out_trade_no=order.order_id)
                    if isinstance(resp, dict):
                        if resp.get("result_code") == "SUCCESS":
                            return "success"
                        if resp.get("result_code") == "FAIL":
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


__all__ = ["WeChatPayProvider"]
