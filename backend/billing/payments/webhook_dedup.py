"""Webhook replay protection (event-id dedup).

Payment providers (Stripe, Alipay, WeChat) will retry webhook delivery
if our endpoint returns non-2xx, or even on flaky networks. A duplicate
event MUST NOT be applied twice — otherwise we'd:
- charge the order twice,
- issue a refund on a non-existent second charge,
- corrupt the order status state machine.

Strategy (matches Stripe's ``Stripe-Event-Id`` dedup pattern):
- Each provider gives us an event id:
    - Stripe:  payload.id  (``evt_...``)
    - Alipay:  notify_id (delivered in payload or via header; we fallback to a hash)
    - WeChat:  payload.id  (``evt_...``)
- We register the event id in Redis using ``SET key value NX EX 86400``
  (24h TTL — covers all documented retry windows for these 3 providers).
- If SET NX returns 0 (key existed), the event is a duplicate and the
  webhook handler short-circuits with HTTP 200 + ``"duplicate": true``
  (so the provider stops retrying but we don't re-apply business logic).

Storage:
- Production: Redis 5.x.
- Test: ``fakeredis.FakeRedis``.
- Same backend selection as idempotency.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("billing.webhook_dedup")

# Default TTL: 24 hours
DEFAULT_TTL_SECONDS = 24 * 3600

# Key prefix
KEY_PREFIX = "billing:webhook_evt:"


@dataclass
class DedupResult:
    """Result of a dedup check."""
    event_id: str
    is_duplicate: bool        # True if the event was already processed
    is_new: bool              # True if this is the first time we see the event
    reserved_at: Optional[int] = None


class WebhookDedupStore:
    """Redis-backed event-id dedup.

    Public API:
    - ``register(event_id, provider, ttl) -> DedupResult``
      Marks the event id as seen. If already seen, returns ``is_duplicate=True``.
    - ``release(event_id, provider) -> None``
      Releases the reservation (handler should call this if it crashed
      mid-processing so the provider's retry succeeds next time).
    - ``seen(event_id, provider) -> bool``
      Non-mutating check.
    """
    def __init__(self, redis_client: Any, ttl: int = DEFAULT_TTL_SECONDS,
                 namespace: str = KEY_PREFIX) -> None:
        self.r = redis_client
        self.ttl = ttl
        self.namespace = namespace
        self._lock = threading.Lock()

    def _key(self, event_id: str, provider: str) -> str:
        # Provider-scoped so the same event id across providers doesn't collide.
        # (Not a real concern today but defensive.)
        return f"{self.namespace}{provider}:{event_id}"

    def register(self, event_id: str, provider: str,
                 ttl: Optional[int] = None) -> DedupResult:
        """Atomic SET NX — returns ``DedupResult(is_duplicate=...)``."""
        if not event_id:
            # Empty event id = not dedupable. Always allow.
            return DedupResult(event_id="", is_duplicate=False, is_new=True)
        ttl = ttl or self.ttl
        rkey = self._key(event_id, provider)
        record = json.dumps({
            "event_id": event_id,
            "provider": provider,
            "seen_at": int(time.time()),
        })
        ok = self.r.set(rkey, record, nx=True, ex=ttl)
        if ok:
            return DedupResult(
                event_id=event_id, is_duplicate=False, is_new=True,
                reserved_at=int(time.time()),
            )
        return DedupResult(event_id=event_id, is_duplicate=True, is_new=False)

    def release(self, event_id: str, provider: str) -> None:
        """Release the reservation (handler crashed; let provider retry)."""
        if not event_id:
            return
        self.r.delete(self._key(event_id, provider))

    def seen(self, event_id: str, provider: str) -> bool:
        """Non-mutating check."""
        if not event_id:
            return False
        return self.r.exists(self._key(event_id, provider)) > 0

    def count(self, provider: Optional[str] = None) -> int:
        """Diagnostic: how many event ids we have cached."""
        pattern = f"{self.namespace}{provider}:*" if provider else f"{self.namespace}*"
        # Use SCAN, not KEYS, to avoid blocking Redis
        n = 0
        for _ in self.r.scan_iter(match=pattern, count=100):
            n += 1
        return n


# ── Singleton wiring ────────────────────────────────────────────────────────
_BACKEND: Optional[WebhookDedupStore] = None
_BACKEND_LOCK = threading.Lock()


def _build_default_redis() -> Any:
    backend = os.environ.get("BILLING_DEDUP_BACKEND", "").lower()
    if backend == "fake":
        from fakeredis import FakeRedis
        logger.info("webhook_dedup: using fakeredis (in-process)")
        return FakeRedis(decode_responses=True)
    try:
        import redis as redis_pkg
        url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        client = redis_pkg.Redis.from_url(url, decode_responses=True,
                                          socket_connect_timeout=1,
                                          socket_timeout=2)
        client.ping()
        logger.info("webhook_dedup: using real Redis at %s", url)
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning("webhook_dedup: real Redis unavailable (%s); falling back to fakeredis", e)
        from fakeredis import FakeRedis
        return FakeRedis(decode_responses=True)


def get_store() -> WebhookDedupStore:
    """Get the process-wide webhook dedup store (lazy init)."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    with _BACKEND_LOCK:
        if _BACKEND is None:
            _BACKEND = WebhookDedupStore(_build_default_redis())
    return _BACKEND


def reset_store(store: Optional[WebhookDedupStore] = None) -> WebhookDedupStore:
    """Reset the singleton (test helper)."""
    global _BACKEND
    with _BACKEND_LOCK:
        if store is None:
            from fakeredis import FakeRedis
            _BACKEND = WebhookDedupStore(FakeRedis(decode_responses=True))
        else:
            _BACKEND = store
    return _BACKEND


# ── Event-id extraction helpers (per-provider) ─────────────────────────────
def extract_stripe_event_id(payload: bytes) -> str:
    """Extract ``evt_...`` from a Stripe webhook payload."""
    try:
        data = json.loads(payload)
        eid = data.get("id", "")
        if isinstance(eid, str) and eid:
            return eid
    except json.JSONDecodeError:
        pass
    return ""


def extract_alipay_event_id(payload: bytes) -> str:
    """Extract event id from Alipay async notify.

    Alipay's documented field is ``notify_id`` (returned on the same
    notify call). It's the most stable dedup key — using the
    ``out_trade_no + trade_no + trade_status`` tuple as a fallback.
    """
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return ""
        nid = data.get("notify_id")
        if isinstance(nid, str) and nid:
            return nid
        # Fallback: deterministic hash of the meaningful fields
        out_trade = data.get("out_trade_no", "")
        trade_no = data.get("trade_no", "")
        status = data.get("trade_status", "")
        if out_trade and trade_no:
            raw = f"{out_trade}|{trade_no}|{status}"
            return "alipay_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    except json.JSONDecodeError:
        pass
    return ""


def extract_wechat_event_id(payload: bytes) -> str:
    """Extract event id from WeChat Pay v3 payload.

    WeChat v3 includes ``id`` (event id) and ``resource.transaction_id``.
    Prefer ``id`` (one event = one delivery).
    """
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return ""
        eid = data.get("id")
        if isinstance(eid, str) and eid:
            return eid
        # Fallback: transaction_id (one per payment, but a single
        # transaction can have multiple events; deduping by transaction_id
        # would over-block — so we only use it when id is missing)
        tid = data.get("resource", {}).get("transaction_id")
        if isinstance(tid, str) and tid:
            return "wx_txn_" + tid
    except json.JSONDecodeError:
        pass
    return ""


def extract_event_id(provider: str, payload: bytes) -> str:
    """Dispatch to the right extractor based on provider name."""
    if provider == "stripe":
        return extract_stripe_event_id(payload)
    if provider == "alipay":
        return extract_alipay_event_id(payload)
    if provider == "wechat":
        return extract_wechat_event_id(payload)
    # Unknown — caller decides whether to dedup
    return ""


__all__ = [
    "WebhookDedupStore", "DedupResult", "get_store", "reset_store",
    "extract_event_id",
    "extract_stripe_event_id", "extract_alipay_event_id", "extract_wechat_event_id",
    "DEFAULT_TTL_SECONDS", "KEY_PREFIX",
]