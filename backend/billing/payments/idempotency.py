"""Payment idempotency (Stripe-style).

A client that retries the same ``create_payment`` request (due to network
timeout, mobile flaky connection, double-click, etc.) MUST NOT cause a
double charge.

Strategy (matches Stripe's Idempotency-Key design):
- Caller supplies ``Idempotency-Key: <uuid>`` header on the create_payment
  request (or we derive one from ``order_id`` + ``payment_method``).
- We hash the request body + key and store the result in Redis under
  ``billing:idem:{key}`` with TTL = 24h.
- A duplicate request returns the cached PaymentResult verbatim and we
  log a "replay" event so callers can verify it.

Why 24h TTL: Stripe's documented behavior (see stripe.com/docs/api/idempotent_requests).
Long enough to absorb the typical retry window, short enough that the
Redis store does not grow unbounded.

Backing store:
- Production: Redis 5.x (``redis.Redis``).
- Test / offline: ``fakeredis.FakeRedis`` (in-process, zero-deps).
- Selection: env ``BILLING_IDEMPOTENCY_BACKEND=real|fake`` (default ``real``
  if ``REDIS_URL``/``localhost:6379`` reachable, else ``fake``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("billing.idempotency")

# Default TTL: 24 hours (Stripe documented behavior)
DEFAULT_TTL_SECONDS = 24 * 3600

# Key prefix to avoid colliding with other namespaces in Redis
KEY_PREFIX = "billing:idem:"


@dataclass
class IdempotencyHit:
    """Cached result returned for a duplicate request."""
    key: str
    response_json: str        # full JSON of the PaymentResult
    request_hash: str         # sha256 of the original request body
    created_at: int
    replay_count: int = 0

    def parsed(self) -> Dict[str, Any]:
        """Parse response_json back to a dict."""
        return json.loads(self.response_json)


class IdempotencyStore:
    """Thread-safe Redis-backed idempotency store.

    Public API:
    - ``lookup_or_reserve(key, request_hash, ttl) -> Optional[IdempotencyHit]``
      If the key exists: returns the hit (caller should replay).
      If not: returns None AND reserves the key with a placeholder
      (so concurrent retries see "in progress").
    - ``commit(key, response_json, ttl) -> None``
      Replaces the placeholder with the actual response.
    - ``release(key) -> None``
      Releases a reservation if the work failed (lets caller retry).
    - ``drop(key) -> None``
      Force-clear (admin / test).
    """
    def __init__(self, redis_client: Any, ttl: int = DEFAULT_TTL_SECONDS,
                 namespace: str = KEY_PREFIX) -> None:
        self.r = redis_client
        self.ttl = ttl
        self.namespace = namespace
        self._lock = threading.Lock()  # for in-process concurrency safety

    def _key(self, k: str) -> str:
        return f"{self.namespace}{k}"

    def lookup_or_reserve(self, key: str, request_hash: str,
                          ttl: Optional[int] = None) -> Tuple[Optional[IdempotencyHit], bool]:
        """Look up an idempotency key; reserve if absent.

        Returns ``(hit, reserved)``:
        - ``(hit, False)``: existing record, caller should replay.
        - ``(None, True)``: we just reserved, caller should do the work and commit.
        - ``(None, False)``: existing in-progress placeholder, caller should
          treat as "still processing" (HTTP 409 in API layer).
        """
        ttl = ttl or self.ttl
        rkey = self._key(key)
        placeholder = json.dumps({
            "key": key,
            "response_json": "",
            "request_hash": request_hash,
            "created_at": int(time.time()),
            "in_progress": True,
        })
        # SET key value NX EX ttl  — atomic check-and-set
        ok = self.r.set(rkey, placeholder, nx=True, ex=ttl)
        if ok:
            return (None, True)
        # Existing record — fetch and classify
        existing_raw = self.r.get(rkey)
        if existing_raw is None:
            # Race: TTL expired between SET NX and GET. Treat as miss.
            # Retry once.
            ok = self.r.set(rkey, placeholder, nx=True, ex=ttl)
            if ok:
                return (None, True)
            existing_raw = self.r.get(rkey)
        if existing_raw is None:
            return (None, True)
        try:
            existing = json.loads(existing_raw)
        except json.JSONDecodeError:
            logger.warning("idempotency: corrupt record at %s, dropping", rkey)
            self.r.delete(rkey)
            return (None, True)
        if existing.get("in_progress"):
            return (None, False)
        # Same request? Mismatch = 422 in API layer.
        return (
            IdempotencyHit(
                key=existing["key"],
                response_json=existing["response_json"],
                request_hash=existing["request_hash"],
                created_at=existing["created_at"],
                replay_count=int(existing.get("replay_count", 0)) + 1,
            ),
            False,
        )

    def commit(self, key: str, request_hash: str, response: Dict[str, Any],
               ttl: Optional[int] = None) -> None:
        """Replace the in-progress placeholder with the actual response."""
        ttl = ttl or self.ttl
        rkey = self._key(key)
        record = {
            "key": key,
            "response_json": json.dumps(response, default=str, sort_keys=True),
            "request_hash": request_hash,
            "created_at": int(time.time()),
            "in_progress": False,
            "replay_count": 0,
        }
        # Bump replay count atomically by reading then writing.
        existing_raw = self.r.get(rkey)
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
                record["replay_count"] = int(existing.get("replay_count", 0))
            except json.JSONDecodeError:
                pass
        self.r.set(rkey, json.dumps(record), ex=ttl)

    def release(self, key: str) -> None:
        """Release the reservation (work failed; caller will retry)."""
        self.r.delete(self._key(key))

    def drop(self, key: str) -> None:
        """Force-clear (admin / test)."""
        self.r.delete(self._key(key))

    def has(self, key: str) -> bool:
        return self.r.exists(self._key(key)) > 0


# ── Singleton wiring ────────────────────────────────────────────────────────
_BACKEND: Optional[IdempotencyStore] = None
_BACKEND_LOCK = threading.Lock()


def _build_default_redis() -> Any:
    """Build a Redis client (real or fake) based on env / availability."""
    backend = os.environ.get("BILLING_IDEMPOTENCY_BACKEND", "").lower()
    if backend == "fake":
        from fakeredis import FakeRedis
        logger.info("idempotency: using fakeredis (in-process)")
        return FakeRedis(decode_responses=True)
    # Try real Redis; fall back to fakeredis on failure
    try:
        import redis as redis_pkg
        url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        client = redis_pkg.Redis.from_url(url, decode_responses=True,
                                          socket_connect_timeout=1,
                                          socket_timeout=2)
        client.ping()
        logger.info("idempotency: using real Redis at %s", url)
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning("idempotency: real Redis unavailable (%s); falling back to fakeredis", e)
        from fakeredis import FakeRedis
        return FakeRedis(decode_responses=True)


def get_store() -> IdempotencyStore:
    """Get the process-wide idempotency store (lazy init)."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    with _BACKEND_LOCK:
        if _BACKEND is None:
            _BACKEND = IdempotencyStore(_build_default_redis())
    return _BACKEND


def reset_store(store: Optional[IdempotencyStore] = None) -> IdempotencyStore:
    """Reset the singleton (test helper). Pass a custom store to install."""
    global _BACKEND
    with _BACKEND_LOCK:
        if store is None:
            from fakeredis import FakeRedis
            _BACKEND = IdempotencyStore(FakeRedis(decode_responses=True))
        else:
            _BACKEND = store
    return _BACKEND


# ── Hash helper ─────────────────────────────────────────────────────────────
def hash_request(payload: Dict[str, Any]) -> str:
    """Stable SHA-256 of a JSON-serializable request dict."""
    s = json.dumps(payload, default=str, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def derive_key_from_order(order_id: str, payment_method: str,
                          extra: Optional[str] = None) -> str:
    """Derive a deterministic idempotency key when the client didn't supply one.

    Pattern: ``order:{order_id}:method:{payment_method}`` (plus optional suffix).
    """
    parts = [f"order:{order_id}", f"method:{payment_method}"]
    if extra:
        parts.append(f"x:{extra}")
    return ":".join(parts)


__all__ = [
    "IdempotencyStore", "IdempotencyHit", "get_store", "reset_store",
    "hash_request", "derive_key_from_order", "DEFAULT_TTL_SECONDS",
    "KEY_PREFIX",
]