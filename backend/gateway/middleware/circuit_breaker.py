"""Per-service circuit breaker.

States
======
  CLOSED     — normal; requests pass through
  OPEN       — failing; requests are rejected immediately (fail fast)
  HALF_OPEN  — letting one trial request through to test recovery

Transitions
===========
  CLOSED → OPEN        after N consecutive failures
  OPEN   → HALF_OPEN   after ``reset_timeout`` seconds
  HALF_OPEN → CLOSED   on trial success
  HALF_OPEN → OPEN     on trial failure

This module exposes both:
  * ``CircuitBreaker``        — standalone object you can use directly
  * ``CircuitBreakerRegistry`` — keyed by service name, used by the gateway
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Dict, Optional


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a request is rejected because the breaker is OPEN."""


class CircuitBreaker:
    """Thread-safe (asyncio) circuit breaker for a single dependency."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name
        self._state: BreakerState = BreakerState.CLOSED
        self._failures: int = 0
        self._opened_at: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BreakerState:
        return self._state

    async def _maybe_half_open(self) -> None:
        """If we are OPEN and the reset window has elapsed, move to HALF_OPEN."""
        if self._state == BreakerState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = BreakerState.HALF_OPEN

    async def allow(self) -> bool:
        """Return True if a call may proceed, False if it should be rejected."""
        async with self._lock:
            await self._maybe_half_open()
            if self._state == BreakerState.OPEN:
                return False
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = BreakerState.CLOSED
            self._opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if (
                self._state == BreakerState.HALF_OPEN
                or self._failures >= self.failure_threshold
            ):
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()


class CircuitBreakerRegistry:
    """A registry keyed by service name.  Cheap to instantiate."""

    def __init__(self, *, failure_threshold: int = 5, reset_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> CircuitBreaker:
        b = self._breakers.get(name)
        if b is not None:
            return b
        async with self._lock:
            b = self._breakers.get(name)
            if b is None:
                b = CircuitBreaker(
                    failure_threshold=self.failure_threshold,
                    reset_timeout=self.reset_timeout,
                    name=name,
                )
                self._breakers[name] = b
            return b

    def snapshot(self) -> Dict[str, str]:
        """Read-only state map for /healthz."""
        return {name: b.state.value for name, b in self._breakers.items()}


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "BreakerState",
    "CircuitOpenError",
]
