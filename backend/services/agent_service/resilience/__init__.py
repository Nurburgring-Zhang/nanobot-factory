"""P6-Fix-B-3: Resilience primitives — circuit breaker + distributed lock.

Addresses C7.6 (Circuit breaker) and C9.6 (Distributed lock) FAIL items
from ``reports/p6_3_findings.md``.

Both classes are intentionally framework-agnostic — they take no
FastAPI / Pydantic dependency so they can be unit-tested without
spinning up an app and reused by the executor / scheduler layers.
"""
from __future__ import annotations

from .circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    circuit_breaker,
)
from .dist_lock import (
    DistLock,
    InMemoryDistLock,
    RedisDistLock,
    LockAcquireError,
    LockReleaseError,
    get_dist_lock,
    reset_dist_lock_for_test,
)

__all__ = [
    # circuit breaker
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "circuit_breaker",
    # distributed lock
    "DistLock",
    "InMemoryDistLock",
    "RedisDistLock",
    "LockAcquireError",
    "LockReleaseError",
    "get_dist_lock",
    "reset_dist_lock_for_test",
]\

