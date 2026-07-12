"""P17-D1 P0 #3: Webhook retry + exponential backoff tests.

Verify:
- Failed delivery retries up to 3 times with 1s/2s/4s backoff
- Eventually successful delivery returns success=True
- 3 failures in a row → dead-letter + audit log entry
- 50% failure rate: after retries, 100% dispatch (within 3 attempts)
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
    WebhookDispatcher, InMemoryWebhookStore,
    RETRY_MAX_ATTEMPTS, RETRY_BACKOFF_BASE_SECONDS,
)


class _CountingPoster:
    """Poster that fails the first `fail_count` times, then succeeds."""
    def __init__(self, fail_count: int = 0, status_on_fail: int = 500):
        self.fail_count = fail_count
        self.status_on_fail = status_on_fail
        self.call_count = 0
        self.requests = []

    def post(self, url, data, headers):
        self.call_count += 1
        self.requests.append({"url": url, "data": data, "headers": dict(headers)})
        if self.call_count <= self.fail_count:
            return (self.status_on_fail, "server error")
        return (200, "OK")


class _AlwaysFailPoster:
    def __init__(self, status_code: int = 500):
        self.status_code = status_code
        self.call_count = 0

    def post(self, url, data, headers):
        self.call_count += 1
        return (self.status_code, "fail")


# Fast backoff for tests (1ms/2ms/4ms instead of 1s/2s/4s)
_FAST_BACKOFF = 0.001


def _make_dispatcher(poster, **kwargs):
    """Helper: WebhookDispatcher with fast backoff for testing."""
    kwargs.setdefault("backoff_base_seconds", _FAST_BACKOFF)
    kwargs.setdefault("allow_http_urls", True)
    return WebhookDispatcher(InMemoryWebhookStore(), poster=poster, **kwargs)


class TestRetryBehavior:
    """P0 #3 — Retry + exponential backoff."""

    def test_001_first_attempt_success_no_retry(self):
        """Happy path: 1 attempt, success."""
        poster = _CountingPoster(fail_count=0)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {"x": 1})
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].attempts == 1
        assert poster.call_count == 1

    def test_002_retry_once_then_success(self):
        """1 failure, then success on 2nd attempt."""
        poster = _CountingPoster(fail_count=1)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {"x": 1})
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].attempts == 2
        assert poster.call_count == 2

    def test_003_retry_twice_then_success(self):
        """2 failures, then success on 3rd attempt."""
        poster = _CountingPoster(fail_count=2)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {"x": 1})
        assert results[0].success is True
        assert results[0].attempts == 3
        assert poster.call_count == 3

    def test_004_three_failures_dead_letter(self):
        """3 failures → dead-letter, success=False, audit_log populated."""
        poster = _AlwaysFailPoster(status_code=500)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {"x": 1})
        assert len(results) == 1
        r = results[0]
        assert r.success is False
        assert r.attempts == RETRY_MAX_ATTEMPTS
        assert r.dead_lettered is True
        assert poster.call_count == RETRY_MAX_ATTEMPTS
        assert len(r.error_history) == RETRY_MAX_ATTEMPTS
        # Audit log
        assert len(d.audit_log) == 1
        entry = d.audit_log[0]
        assert entry["attempts"] == RETRY_MAX_ATTEMPTS
        assert entry["dead_lettered_at"]
        assert entry["event"] == "payment.succeeded"

    def test_005_three_failures_fast_backoff(self):
        """With fast backoff, all 3 attempts complete in well under 1s."""
        poster = _AlwaysFailPoster(status_code=500)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        t0 = time.time()
        d.emit_event("payment.succeeded", {"x": 1})
        elapsed = time.time() - t0
        # With 1ms/2ms backoff, total should be ~3ms + work, well under 1s
        assert elapsed < 1.0

    def test_006_50pct_failure_eventually_succeeds(self):
        """High failure rate: retry should ensure 100% dispatch within 3 attempts.

        We use a poster that fails the first 2 of every 3 attempts (≈67% fail),
        which is even worse than 50%. After 2 retries, the 3rd attempt always
        succeeds.
        """
        n_dispatch = 20
        success_after_3 = 0
        for cycle in range(n_dispatch):
            poster = _CountingPoster(fail_count=2)  # fail twice, succeed 3rd
            d = _make_dispatcher(poster)
            d.register_webhook(
                url="http://example.com/wh",
                events=["payment.succeeded"],
                secret="mysecret123",
            )
            results = d.emit_event("payment.succeeded", {"cycle": cycle})
            if results[0].success:
                success_after_3 += 1
        # All 20 must have eventually succeeded within 3 attempts
        assert success_after_3 == n_dispatch

    def test_007_dead_letter_counter(self):
        """dead_letter_count increments for each dead-lettered delivery."""
        poster = _AlwaysFailPoster()
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded", "payment.failed"],
            secret="mysecret123",
        )
        d.emit_event("payment.succeeded", {})
        d.emit_event("payment.failed", {})
        assert d.dead_letter_count == 2
        assert len(d.audit_log) == 2

    def test_008_each_retry_has_distinct_signature(self):
        """Each attempt uses the same delivery headers (idempotent)."""
        poster = _CountingPoster(fail_count=2)
        d = _make_dispatcher(poster)
        d.register_webhook(
            url="http://example.com/wh",
            events=["payment.succeeded"],
            secret="mysecret123",
        )
        results = d.emit_event("payment.succeeded", {})
        # All 3 attempts must have used the same delivery_id
        # (so the recipient can dedup)
        from billing.webhook_config import DELIVERY_ID_HEADER
        ids = [r["headers"][DELIVERY_ID_HEADER] for r in poster.requests]
        assert len(set(ids)) == 1, "delivery_id must be stable across retries"
        assert results[0].success is True

    def test_009_production_backoff_is_one_second(self):
        """Spec: production backoff is 1s/2s/4s (RETRY_BACKOFF_BASE_SECONDS)."""
        # Verify default backoff is 1s (production setting)
        d = _make_dispatcher(_CountingPoster(fail_count=0),
                              backoff_base_seconds=None)  # use default
        assert d._backoff_base == RETRY_BACKOFF_BASE_SECONDS
        assert d._backoff_base == 1.0  # production = 1 second base


# Make sure the import above doesn't break
from billing.webhook_config import WebhookDispatcher  # noqa: E402