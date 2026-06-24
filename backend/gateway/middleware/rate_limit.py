"""Token-bucket rate limiter (per client IP).

Algorithm
=========
A token bucket has:
  * ``capacity``     — the bucket size (max burst)
  * ``refill_rate``  — tokens added per second
Each request consumes one token; if the bucket is empty, the request is
rejected with HTTP 429.  The bucket refills continuously with time, so
a client that pauses will accumulate tokens up to ``capacity``.

We use ``time.monotonic()`` for refills (immune to wall-clock jumps) and
a single ``asyncio.Lock`` per bucket to keep things hermetic when many
concurrent requests share a key.

This is intentionally a pure-Python implementation — no Redis, no
external service.  The gateway runs in-process; if you scale to many
gateway workers, replace the in-memory dict with Redis ``INCR`` + TTL.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class _Bucket:
    capacity: float
    refill_rate: float            # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    async def take(self, n: float = 1.0) -> bool:
        """Try to take ``n`` tokens.  Returns True if allowed, False if rejected."""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            # Refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


class TokenBucketRateLimiter(BaseHTTPMiddleware):
    """ASGI middleware that throttles per client IP.

    Configure via:
        capacity         — max burst tokens (default 100)
        refill_per_second — steady-state rate (default 50/s)
    """

    def __init__(
        self,
        app,
        *,
        capacity: int = 100,
        refill_per_second: float = 50.0,
        trusted_proxies: int = 0,
    ) -> None:
        super().__init__(app)
        self.capacity = float(capacity)
        self.refill_rate = float(refill_per_second)
        self.trusted_proxies = trusted_proxies
        self._buckets: Dict[str, _Bucket] = {}
        self._buckets_lock = asyncio.Lock()

    async def _get_bucket(self, key: str) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is not None:
            return bucket
        async with self._buckets_lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(capacity=self.capacity, refill_rate=self.refill_rate)
                self._buckets[key] = bucket
            return bucket

    @staticmethod
    def _client_key(request: Request) -> str:
        # Best effort: honour X-Forwarded-For first hop, else client.host
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        # Bypass for health probes and gateway control endpoints
        if request.url.path in (
            "/healthz", "/readyz", "/",
            "/_gw/routes", "/_gw/breakers",
        ):
            return await call_next(request)

        key = self._client_key(request)
        bucket = await self._get_bucket(key)
        allowed = await bucket.take(1.0)
        if not allowed:
            # Expose 429 with helpful headers
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "rate_limited",
                    "limit_per_second": self.refill_rate,
                    "burst": self.capacity,
                    "key": key,
                },
                headers={
                    "Retry-After": "1",
                    "X-RateLimit-Limit": str(int(self.refill_rate)),
                    "X-RateLimit-Burst": str(int(self.capacity)),
                },
            )
        response = await call_next(request)
        # Inform well-behaved clients
        response.headers["X-RateLimit-Burst"] = str(int(self.capacity))
        return response


__all__ = ["TokenBucketRateLimiter", "_Bucket"]
