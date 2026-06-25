"""P6-Fix-C-1: Webhook replay protection tests.

Goal: verify that a webhook event delivered twice (with the same event id)
is processed exactly once. The duplicate delivery must:
- return HTTP 200 with ``"duplicate": true``
- NOT re-apply business logic (mark_paid, refund, etc.)

Provider-specific:
- Stripe:  event id = payload["id"] (e.g. ``evt_...``)
- Alipay:  event id = payload["notify_id"] (with hash fallback)
- WeChat:  event id = payload["id"] (e.g. ``evt_...``)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.payments.webhook_dedup import (
    WebhookDedupStore, extract_event_id,
    extract_stripe_event_id, extract_alipay_event_id, extract_wechat_event_id,
    reset_store, DEFAULT_TTL_SECONDS, KEY_PREFIX,
)
from billing.payments.stripe_provider import StripeProvider
from billing.payments.alipay_provider import AlipayProvider
from billing.payments.wechat_provider import WeChatPayProvider


# ── 1. Event-id extraction per provider ───────────────────────────────────
class TestEventIdExtraction:
    def test_001_stripe_event_id(self):
        payload = json.dumps({"id": "evt_abc123", "type": "x"}).encode("utf-8")
        assert extract_stripe_event_id(payload) == "evt_abc123"

    def test_002_stripe_missing_id(self):
        payload = json.dumps({"type": "x"}).encode("utf-8")
        assert extract_stripe_event_id(payload) == ""

    def test_003_stripe_invalid_json(self):
        assert extract_stripe_event_id(b"not json") == ""

    def test_004_alipay_notify_id(self):
        payload = json.dumps({
            "notify_id": "2026062500000001",
            "out_trade_no": "ord_x",
        }).encode("utf-8")
        assert extract_alipay_event_id(payload) == "2026062500000001"

    def test_005_alipay_fallback_hash(self):
        payload = json.dumps({
            "out_trade_no": "ord_x",
            "trade_no": "20260624000001",
            "trade_status": "TRADE_SUCCESS",
        }).encode("utf-8")
        eid = extract_alipay_event_id(payload)
        assert eid.startswith("alipay_")
        assert len(eid) > 10
        # Deterministic — same payload → same id
        eid2 = extract_alipay_event_id(payload)
        assert eid == eid2

    def test_006_wechat_event_id(self):
        payload = json.dumps({
            "id": "evt_wx_001",
            "event_type": "TRANSACTION.SUCCESS",
        }).encode("utf-8")
        assert extract_wechat_event_id(payload) == "evt_wx_001"

    def test_007_wechat_fallback_transaction_id(self):
        payload = json.dumps({
            "resource": {"transaction_id": "4200000123456789"},
        }).encode("utf-8")
        eid = extract_wechat_event_id(payload)
        assert eid == "wx_txn_4200000123456789"

    def test_008_extract_event_id_dispatch(self):
        stripe_payload = json.dumps({"id": "evt_dispatch"}).encode()
        alipay_payload = json.dumps({"notify_id": "n_dispatch"}).encode()
        wechat_payload = json.dumps({"id": "evt_wx_dispatch"}).encode()
        assert extract_event_id("stripe", stripe_payload) == "evt_dispatch"
        assert extract_event_id("alipay", alipay_payload) == "n_dispatch"
        assert extract_event_id("wechat", wechat_payload) == "evt_wx_dispatch"
        assert extract_event_id("unknown", stripe_payload) == ""


# ── 2. Store-level unit tests ──────────────────────────────────────────────
class TestDedupStoreUnit:
    def test_010_register_new_event(self):
        store = reset_store()
        r = store.register("evt_a", "stripe")
        assert r.is_duplicate is False
        assert r.is_new is True

    def test_011_register_duplicate_event(self):
        store = reset_store()
        store.register("evt_b", "stripe")
        r = store.register("evt_b", "stripe")
        assert r.is_duplicate is True
        assert r.is_new is False

    def test_012_different_providers_same_id_dont_collide(self):
        store = reset_store()
        r1 = store.register("evt_c", "stripe")
        r2 = store.register("evt_c", "alipay")
        assert r1.is_new and r2.is_new

    def test_013_seen_check(self):
        store = reset_store()
        assert store.seen("evt_d", "stripe") is False
        store.register("evt_d", "stripe")
        assert store.seen("evt_d", "stripe") is True

    def test_014_release_makes_slot_available(self):
        store = reset_store()
        store.register("evt_e", "stripe")
        store.release("evt_e", "stripe")
        r = store.register("evt_e", "stripe")
        assert r.is_new is True

    def test_015_empty_event_id_always_new(self):
        store = reset_store()
        r1 = store.register("", "stripe")
        r2 = store.register("", "stripe")
        assert r1.is_new and r2.is_new

    def test_016_default_ttl_24h(self):
        assert DEFAULT_TTL_SECONDS == 24 * 3600

    def test_017_short_ttl_expires(self):
        from fakeredis import FakeRedis
        from billing.payments.webhook_dedup import WebhookDedupStore
        r = FakeRedis(decode_responses=True)
        store = WebhookDedupStore(r, ttl=1)
        store.register("evt_short", "stripe")
        time.sleep(1.2)
        result = store.register("evt_short", "stripe")
        assert result.is_new is True  # TTL expired → new registration


# ── 3. End-to-end webhook replay tests (HTTP layer) ───────────────────────
class TestWebhookReplayE2E:
    """Verify duplicate webhook delivery is short-circuited at the route layer."""

    def _build_app(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from billing.routes import build_billing_router, reset_state
        reset_state()
        app = FastAPI()
        app.include_router(build_billing_router())
        return TestClient(app)

    def _create_paid_order(self, c, order_id: str = "ord_wb_replay"):
        body = {
            "user_id": "u_wb",
            "plan_id": "pro",
            "currency": "USD",
            "period": "monthly",
            "payment_method": "stripe",
        }
        r = c.post("/api/v1/billing/orders", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    def _stripe_payload(self, event_id: str = "evt_replay_1",
                        order_id: str = "ord_wb_replay"):
        return json.dumps({
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_xyz",
                "client_reference_id": order_id,
                "amount": 9900,
                "currency": "usd",
            }},
            "created": int(time.time()),
        }).encode("utf-8")

    def _stripe_signature(self, payload: bytes, secret: str = "whsec_mock_secret"):
        ts = str(int(time.time()))
        signed = f"{ts}.{payload.decode('utf-8')}"
        v1 = hmac.new(secret.encode("utf-8"),
                      signed.encode("utf-8"),
                      hashlib.sha256).hexdigest()
        return f"t={ts},v1={v1}"

    def test_020_first_webhook_processes(self):
        c = self._build_app()
        order = self._create_paid_order(c)
        payload = self._stripe_payload(order_id=order["order_id"])
        sig = self._stripe_signature(payload)
        r = c.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": sig, "content-type": "application/json"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["received"] is True
        assert body["duplicate"] is False
        assert body["business_applied"] is True

    def test_021_duplicate_webhook_short_circuits(self):
        c = self._build_app()
        order = self._create_paid_order(c)
        payload = self._stripe_payload(
            event_id="evt_dup_001",
            order_id=order["order_id"],
        )
        sig1 = self._stripe_signature(payload)
        # First delivery
        r1 = c.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": sig1, "content-type": "application/json"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["duplicate"] is False
        # Second delivery (provider retry) — different sig but same payload
        sig2 = self._stripe_signature(payload)
        r2 = c.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": sig2, "content-type": "application/json"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["duplicate"] is True
        assert body["received"] is True
        # Order status was NOT changed again (we can query it)
        order_after = c.get(f"/api/v1/billing/orders/{order['order_id']}").json()
        assert order_after["status"] in ("fulfilled", "paid")

    def test_022_alipay_duplicate_webhook_short_circuits(self):
        c = self._build_app()
        # Order with alipay
        body = {
            "user_id": "u_wb_ali",
            "plan_id": "pro",
            "currency": "CNY",
            "period": "monthly",
            "payment_method": "alipay",
        }
        order = c.post("/api/v1/billing/orders", json=body).json()

        # Build a signed alipay notify
        params = {
            "notify_id": "20260625_n_001",
            "out_trade_no": order["order_id"],
            "trade_no": "20260624000001",
            "total_amount": "99.00",
            "trade_status": "TRADE_SUCCESS",
        }
        sorted_items = sorted(f"{k}={v}" for k, v in params.items())
        sign = hmac.new(
            "alipay_mock_secret".encode("utf-8"),
            "&".join(sorted_items).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["sign"] = sign
        payload = json.dumps(params).encode("utf-8")
        # First delivery
        r1 = c.post(
            "/api/v1/billing/webhook/alipay",
            content=payload,
            headers={"alipay-signature": sign, "content-type": "application/json"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["duplicate"] is False
        # Duplicate delivery (same notify_id, same payload)
        r2 = c.post(
            "/api/v1/billing/webhook/alipay",
            content=payload,
            headers={"alipay-signature": sign, "content-type": "application/json"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["duplicate"] is True

    def test_023_wechat_duplicate_webhook_short_circuits(self):
        c = self._build_app()
        body = {
            "user_id": "u_wb_wx",
            "plan_id": "pro",
            "currency": "CNY",
            "period": "monthly",
            "payment_method": "wechat",
        }
        order = c.post("/api/v1/billing/orders", json=body).json()

        payload = json.dumps({
            "id": "evt_wx_replay_001",
            "event_type": "TRANSACTION.SUCCESS",
            "create_time": int(time.time()),
            "resource": {
                "out_trade_no": order["order_id"],
                "transaction_id": "wx_42000xxxx",
                "amount": {"total": 9900, "currency": "CNY"},
            },
        }, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(
            "wechat_mock_secret".encode("utf-8"),
            payload, hashlib.sha256,
        ).hexdigest()
        # First delivery
        r1 = c.post(
            "/api/v1/billing/webhook/wechat",
            content=payload,
            headers={"wechat-signature": sig, "content-type": "application/json"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["duplicate"] is False
        # Replay
        r2 = c.post(
            "/api/v1/billing/webhook/wechat",
            content=payload,
            headers={"wechat-signature": sig, "content-type": "application/json"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["duplicate"] is True

    def test_024_bad_signature_releases_dedup_slot(self):
        """If signature verify fails, dedup slot is released so legit retry works."""
        c = self._build_app()
        order = self._create_paid_order(c, order_id="ord_wb_badsig")
        payload = self._stripe_payload(
            event_id="evt_badsig_001",
            order_id=order["order_id"],
        )
        # Send with bad signature
        r1 = c.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": "t=1,v1=deadbeef",
                     "content-type": "application/json"},
        )
        assert r1.status_code == 400  # signature failure
        # Retry with correct signature — should process (not 400, not duplicate)
        good_sig = self._stripe_signature(payload)
        r2 = c.post(
            "/api/v1/billing/webhook/stripe",
            content=payload,
            headers={"stripe-signature": good_sig,
                     "content-type": "application/json"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["duplicate"] is False
        assert r2.json()["business_applied"] is True