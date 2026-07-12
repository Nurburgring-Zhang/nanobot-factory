"""P17-A1 webhook config tests.

Coverage:
- 5 supported events
- WebhookConfig validation (url, secret, events)
- InMemoryWebhookStore CRUD
- JsonlWebhookStore CRUD
- WebhookDispatcher.register_webhook + emit_event
- HMAC-SHA256 signature compute / verify
- All 5 events dispatch successfully
- DeliveryResult captures success + signature
- Mock HTTP poster for deterministic testing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing import webhook_config as wh
from billing.webhook_config import (
    WebhookEvent, WebhookConfig, WebhookDispatcher,
    InMemoryWebhookStore, JsonlWebhookStore,
    HTTPPoster, DeliveryResult,
    compute_signature, verify_signature,
    WEBHOOK_EVENTS, SIGNATURE_HEADER, EVENT_HEADER,
    TIMESTAMP_HEADER, DELIVERY_ID_HEADER, NONCE_HEADER,
)


# ── 1. Constants ──────────────────────────────────────────────────────────

class TestConstants:
    def test_001_webhook_events(self):
        assert len(WEBHOOK_EVENTS) == 5
        assert "payment.created" in WEBHOOK_EVENTS
        assert "payment.succeeded" in WEBHOOK_EVENTS
        assert "payment.failed" in WEBHOOK_EVENTS
        assert "refund.created" in WEBHOOK_EVENTS
        assert "refund.succeeded" in WEBHOOK_EVENTS

    def test_002_webhook_event_enum(self):
        assert WebhookEvent.PAYMENT_CREATED.value == "payment.created"
        assert WebhookEvent.PAYMENT_SUCCEEDED.value == "payment.succeeded"
        assert WebhookEvent.PAYMENT_FAILED.value == "payment.failed"
        assert WebhookEvent.REFUND_CREATED.value == "refund.created"
        assert WebhookEvent.REFUND_SUCCEEDED.value == "refund.succeeded"


# ── 2. Signature compute / verify ─────────────────────────────────────────

class TestSignature:
    def test_010_compute_signature_format(self):
        sig = compute_signature("test-secret", b"hello")
        assert sig.startswith("sha256=")
        assert len(sig) == 7 + 64  # sha256= + 64 hex chars

    def test_011_verify_valid_signature(self):
        payload = b'{"event":"payment.succeeded","amount":9900}'
        sig = compute_signature("mysecret", payload)
        assert verify_signature("mysecret", payload, sig) is True

    def test_012_verify_invalid_signature(self):
        payload = b"hello"
        assert verify_signature("mysecret", payload, "sha256=wrong") is False

    def test_013_verify_with_timestamp(self):
        payload = b"hello"
        ts = "1700000000"
        sig = compute_signature("mysecret", payload, ts)
        assert verify_signature("mysecret", payload, sig, ts) is True
        # Different timestamp -> signature mismatch
        assert verify_signature("mysecret", payload, sig, "1700000001") is False

    def test_014_signature_changes_with_payload(self):
        sig1 = compute_signature("secret", b"hello")
        sig2 = compute_signature("secret", b"world")
        assert sig1 != sig2

    def test_015_signature_changes_with_secret(self):
        sig1 = compute_signature("secret1", b"hello")
        sig2 = compute_signature("secret2", b"hello")
        assert sig1 != sig2

    def test_016_verify_rejects_malformed_header(self):
        assert verify_signature("secret", b"x", "invalid") is False
        assert verify_signature("secret", b"x", "") is False
        assert verify_signature("secret", b"x", "md5=abc") is False


# ── 3. WebhookConfig validation ──────────────────────────────────────────

class TestWebhookConfig:
    def test_020_minimal_config(self):
        c = WebhookConfig(
            webhook_id="wh_001",
            url="https://example.com/webhook",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        assert c.webhook_id == "wh_001"
        assert c.enabled is True
        assert c.created_at != ""

    def test_021_subscribes_to(self):
        c = WebhookConfig(
            webhook_id="wh_001",
            url="https://example.com",
            events=["payment.succeeded", "payment.failed"],
            secret="mysecret123",
        )
        assert c.subscribes_to("payment.succeeded") is True
        assert c.subscribes_to("payment.failed") is True
        assert c.subscribes_to("refund.created") is False

    def test_022_disabled_does_not_subscribe(self):
        c = WebhookConfig(
            webhook_id="wh_001",
            url="https://example.com",
            events=["payment.succeeded"],
            secret="mysecret123",
            enabled=False,
        )
        assert c.subscribes_to("payment.succeeded") is False

    def test_030_invalid_url_raises(self):
        with pytest.raises(ValueError):
            WebhookConfig(
                webhook_id="wh_001",
                url="not-a-url",
                events=["payment.succeeded"],
                secret="mysecret123",
            )

    def test_031_short_secret_raises(self):
        with pytest.raises(ValueError):
            WebhookConfig(
                webhook_id="wh_001",
                url="https://example.com",
                events=["payment.succeeded"],
                secret="short",
            )

    def test_032_invalid_event_raises(self):
        with pytest.raises(ValueError):
            WebhookConfig(
                webhook_id="wh_001",
                url="https://example.com",
                events=["bogus.event"],
                secret="mysecret123",
            )


# ── 4. InMemoryWebhookStore ──────────────────────────────────────────────

class TestInMemoryStore:
    def test_040_save_and_get(self):
        s = InMemoryWebhookStore()
        c = WebhookConfig(
            webhook_id="wh_001", url="https://x.com",
            events=["payment.succeeded"], secret="mysecret123",
        )
        s.save(c)
        assert s.get("wh_001") is c

    def test_041_list(self):
        s = InMemoryWebhookStore()
        for i in range(3):
            s.save(WebhookConfig(
                webhook_id=f"wh_{i}", url="https://x.com",
                events=["payment.succeeded"], secret="mysecret123",
            ))
        assert len(s.list()) == 3

    def test_042_delete(self):
        s = InMemoryWebhookStore()
        s.save(WebhookConfig(
            webhook_id="wh_001", url="https://x.com",
            events=["payment.succeeded"], secret="mysecret123",
        ))
        assert s.delete("wh_001") is True
        assert s.get("wh_001") is None
        assert s.delete("nonexistent") is False


# ── 5. JsonlWebhookStore ──────────────────────────────────────────────────

class TestJsonlStore:
    def test_050_persistence(self, tmp_path):
        p = tmp_path / "webhooks.jsonl"
        s1 = JsonlWebhookStore(p)
        s1.save(WebhookConfig(
            webhook_id="wh_001", url="https://x.com",
            events=["payment.succeeded"], secret="mysecret123",
        ))
        # Reload from disk
        s2 = JsonlWebhookStore(p)
        assert s2.get("wh_001") is not None
        assert s2.get("wh_001").url == "https://x.com"

    def test_051_delete_persists(self, tmp_path):
        p = tmp_path / "webhooks.jsonl"
        s1 = JsonlWebhookStore(p)
        s1.save(WebhookConfig(
            webhook_id="wh_001", url="https://x.com",
            events=["payment.succeeded"], secret="mysecret123",
        ))
        s1.delete("wh_001")
        s2 = JsonlWebhookStore(p)
        assert s2.get("wh_001") is None


# ── 6. Dispatcher with mock poster ────────────────────────────────────────

class MockPoster:
    """Records all POST requests, returns configurable status code."""
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.requests: List[Dict] = []

    def post(self, url, data, headers):
        self.requests.append({"url": url, "data": data, "headers": headers})
        return (self.status_code, "OK")


class TestDispatcher:
    def test_060_register_and_list(self):
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=MockPoster())
        wh = d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        assert wh.webhook_id.startswith("wh_")
        assert len(d.list_webhooks()) == 1

    def test_061_unregister(self):
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=MockPoster())
        wh = d.register_webhook(
            url="https://example.com",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        assert d.unregister_webhook(wh.webhook_id) is True
        assert d.unregister_webhook(wh.webhook_id) is False

    def test_062_emit_event_dispatches(self):
        poster = MockPoster(status_code=200)
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        wh_config = d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {
            "order_id": "ord_001", "amount_cents": 9900,
        })
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].status_code == 200
        assert results[0].signature.startswith("sha256=")
        assert len(poster.requests) == 1
        # Verify request headers
        req = poster.requests[0]
        assert req["headers"][EVENT_HEADER] == "payment.succeeded"
        assert req["headers"][SIGNATURE_HEADER].startswith("sha256=")
        assert TIMESTAMP_HEADER in req["headers"]
        assert DELIVERY_ID_HEADER in req["headers"]

    def test_063_unsubscribed_event_skipped(self):
        poster = MockPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("refund.created", {"refund_id": "rf_001"})
        assert len(results) == 0
        assert len(poster.requests) == 0

    def test_064_disabled_webhook_skipped(self):
        poster = MockPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        wh = d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        # Disable
        wh.enabled = False
        d.store.save(wh)
        results = d.emit_event("payment.succeeded", {})
        assert len(results) == 0

    def test_065_http_error_marks_failure(self):
        poster = MockPoster(status_code=500)
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {})
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].status_code == 500

    def test_066_invalid_event_raises(self):
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=MockPoster())
        with pytest.raises(ValueError):
            d.emit_event("bogus.event", {})

    def test_067_multiple_webhooks_same_event(self):
        poster = MockPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        for i in range(3):
            d.register_webhook(
                url=f"https://example.com/wh{i}",
                events=["payment.succeeded"],
                secret=f"secret{i}123",
            )
        results = d.emit_event("payment.succeeded", {"x": 1})
        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(poster.requests) == 3


# ── 7. All 5 events dispatch successfully (spec required) ────────────────

class TestAllFiveEvents:
    """Spec: 5 事件全部 dispatch 成功."""

    def test_070_all_five_events(self):
        poster = MockPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster)
        # One webhook subscribed to all 5 events
        d.register_webhook(
            url="https://example.com/all",
            events=list(WEBHOOK_EVENTS),
            secret="mysecret123",
        )
        payloads = {
            "payment.created":   {"order_id": "ord_001"},
            "payment.succeeded": {"order_id": "ord_001", "amount_cents": 9900},
            "payment.failed":    {"order_id": "ord_001", "error": "card_declined"},
            "refund.created":    {"refund_id": "rf_001", "order_id": "ord_001"},
            "refund.succeeded":  {"refund_id": "rf_001", "amount_cents": 9900},
        }
        all_results: List[DeliveryResult] = []
        for event, payload in payloads.items():
            results = d.emit_event(event, payload)
            assert len(results) == 1, f"{event} did not dispatch"
            all_results.extend(results)
        # Verify all 5 succeeded
        assert len(all_results) == 5
        for r in all_results:
            assert r.success is True
            assert r.status_code == 200
            assert r.signature.startswith("sha256=")
            assert r.event in WEBHOOK_EVENTS
        # Verify 5 HTTP calls were made
        assert len(poster.requests) == 5
        # Each request has correct event header
        for req, event in zip(poster.requests, payloads.keys()):
            assert req["headers"][EVENT_HEADER] == event


# ── 8. Signature verify on received request ───────────────────────────────

class TestSignatureVerifyOnReceive:
    """End-to-end: dispatcher signs, receiver verifies."""

    def test_080_signed_payload_verifies(self):
        poster = MockPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster,
                              allow_http_urls=True)
        wh_config = d.register_webhook(
            url="https://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        d.emit_event("payment.succeeded", {"order_id": "ord_001"})
        # Extract request from poster
        req = poster.requests[0]
        body = req["data"]
        sig_header = req["headers"][SIGNATURE_HEADER]
        ts = req["headers"][TIMESTAMP_HEADER]
        nonce = req["headers"][NONCE_HEADER]
        # P17-D1: signature now includes timestamp + nonce + body
        assert verify_signature(wh_config.secret, body, sig_header, ts, nonce) is True
        # Tampered body fails
        tampered = body + b"x"
        assert verify_signature(wh_config.secret, tampered, sig_header, ts, nonce) is False
        # Wrong secret fails
        assert verify_signature("wrongsecret", body, sig_header, ts, nonce) is False
        # Wrong nonce fails
        assert verify_signature(wh_config.secret, body, sig_header, ts, "wrongnonce") is False


# ── 9. Singleton reset (for tests) ────────────────────────────────────────

class TestSingleton:
    def test_090_reset(self):
        d1 = wh.get_default_dispatcher()
        wh.reset_default_dispatcher()
        d2 = wh.get_default_dispatcher()
        assert d1 is not d2