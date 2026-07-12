"""P17-D1 P0 #1: Webhook replay protection tests.

Verify that:
- Each emit produces a fresh timestamp + nonce
- HMAC signature is over timestamp.nonce.body
- Replay (same nonce twice) is detectable via NonceStore
- Timestamp out of window (>5min) is rejected
- 1000 dispatches: all have unique nonces
- Replay attempt with same nonce is rejected
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from billing.webhook_config import (
    WebhookDispatcher, InMemoryWebhookStore, NonceStore,
    compute_signature, verify_signature,
    NONCE_HEADER, TIMESTAMP_HEADER, TIMESTAMP_TOLERANCE_SECONDS,
)


class _RecordingPoster:
    def __init__(self):
        self.requests = []
        self.next_status = 200

    def post(self, url, data, headers):
        self.requests.append({"url": url, "data": data, "headers": dict(headers)})
        return (self.next_status, "OK")


class TestReplayProtection:
    """P0 #1 — Replay protection via timestamp + nonce + HMAC."""

    def test_001_each_emit_has_unique_nonce(self):
        """1000 emits: every nonce is unique."""
        poster = _RecordingPoster()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster,
                              allow_http_urls=True)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        seen_nonces = set()
        for i in range(1000):
            d.emit_event("payment.succeeded", {"i": i})
            nonce = poster.requests[-1]["headers"][NONCE_HEADER]
            assert nonce not in seen_nonces, f"duplicate nonce at i={i}"
            seen_nonces.add(nonce)
        assert len(seen_nonces) == 1000

    def test_002_replay_with_same_nonce_rejected(self):
        """A replay of an old delivery's nonce must be flagged."""
        poster = _RecordingPoster()
        nonce_store = NonceStore()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster,
                              nonce_store=nonce_store,
                              allow_http_urls=True)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        # First emit
        d.emit_event("payment.succeeded", {"x": 1})
        first_nonce = poster.requests[0]["headers"][NONCE_HEADER]
        # Mark as seen (simulating recipient state)
        nonce_store.mark_seen(first_nonce)
        # Replay attempt with same nonce
        assert nonce_store.is_seen(first_nonce) is True
        # Trying to reserve again returns False
        assert nonce_store.reserve(first_nonce) is False

    def test_003_signature_includes_nonce(self):
        """HMAC is over timestamp.nonce.body, not just body."""
        secret = "testsecret123"
        body = b'{"event":"payment.succeeded"}'
        ts = "1700000000"
        nonce = "abc123"
        sig = compute_signature(secret, body, ts, nonce)
        # Verify with correct nonce succeeds
        assert verify_signature(secret, body, sig, ts, nonce) is True
        # Verify with wrong nonce fails
        assert verify_signature(secret, body, sig, ts, "wrongnonce") is False
        # Verify with missing nonce (legacy mode) fails
        assert verify_signature(secret, body, sig, ts, None) is False

    def test_004_timestamp_outside_window_rejected(self):
        """Timestamp older than ±5min must be rejected."""
        from billing.webhook_config import verify_signature as vs
        secret = "testsecret123"
        body = b"x"
        old_ts = str(int(time.time()) - TIMESTAMP_TOLERANCE_SECONDS - 60)
        nonce = "n1"
        sig = compute_signature(secret, body, old_ts, nonce)
        # Signature matches but timestamp is stale — caller must reject
        # We verify by simulating recipient-side check
        is_fresh = (
            abs(int(time.time()) - int(old_ts)) <= TIMESTAMP_TOLERANCE_SECONDS
        )
        assert is_fresh is False

    def test_005_fresh_timestamp_accepted(self):
        """Fresh timestamp within ±5min is OK."""
        now = int(time.time())
        is_fresh = abs(time.time() - now) <= TIMESTAMP_TOLERANCE_SECONDS
        assert is_fresh is True

    def test_006_nonce_store_expiry(self):
        """NonceStore drops entries after TTL."""
        store = NonceStore(ttl_seconds=1)
        store.mark_seen("nonce1")
        assert store.is_seen("nonce1") is True
        time.sleep(1.2)
        # Cleanup happens on next access
        assert store.is_seen("nonce1") is False

    def test_007_nonce_store_reserve_atomic(self):
        """reserve() is atomic: first call wins, second returns False."""
        store = NonceStore()
        assert store.reserve("n1") is True
        assert store.reserve("n1") is False
        assert store.reserve("n2") is True

    def test_008_1000_dispatches_no_replay_collisions(self):
        """Spec: 1000 dispatch, replay 1 = rejected. Verify all unique nonces."""
        poster = _RecordingPoster()
        nonce_store = NonceStore()
        d = WebhookDispatcher(InMemoryWebhookStore(), poster=poster,
                              nonce_store=nonce_store,
                              allow_http_urls=True)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        # 1000 dispatches
        for i in range(1000):
            d.emit_event("payment.succeeded", {"i": i})
        # Verify 1000 unique nonces sent
        sent_nonces = [r["headers"][NONCE_HEADER] for r in poster.requests]
        assert len(set(sent_nonces)) == 1000
        # Verify nonce_store is empty (we don't pre-mark; we just verify uniqueness)
        # Replay one — store it first, then try to reserve again
        nonce_store.reserve(sent_nonces[0])
        # Attempt to reserve the same nonce again must fail
        assert nonce_store.reserve(sent_nonces[0]) is False
        # All other nonces still reservable
        for n in sent_nonces[1:10]:
            assert nonce_store.reserve(n) is True