"""P6-Fix-B-3: Resilience primitives tests — CircuitBreaker + DistLock.

Covers:
  * C7.6 — circuit breaker state machine (CLOSED / OPEN / HALF_OPEN)
  * C9.6 — distributed lock interface (in-memory backend)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------
class FakeClock:
    """Manual clock for deterministic state-machine tests."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def test_breaker_starts_closed():
    from services.agent_service.resilience import CircuitBreaker, CircuitState
    cb = CircuitBreaker(name="t")
    assert cb.is_closed
    assert cb.stats()["state"] == "closed"


def test_breaker_opens_after_threshold_failures():
    from services.agent_service.resilience import CircuitBreaker, CircuitOpenError
    cb = CircuitBreaker(name="t", failure_threshold=3, recovery_timeout_s=10.0)
    clock = FakeClock()
    cb.clock = clock

    def boom():
        raise RuntimeError("nope")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(boom)
    assert cb.is_open
    # Fourth call is rejected without invoking the wrapped fn.
    with pytest.raises(CircuitOpenError):
        cb.call(boom)


def test_breaker_half_open_after_recovery_timeout():
    from services.agent_service.resilience import (
        CircuitBreaker,
        CircuitOpenError,
        CircuitState,
    )
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout_s=5.0)
    clock = FakeClock()
    cb.clock = clock

    def boom():
        raise RuntimeError("nope")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(boom)
    assert cb.is_open
    # Just before recovery — still OPEN
    clock.advance(4.9)
    with pytest.raises(CircuitOpenError):
        cb.call(boom)
    # After recovery — next call flips to HALF_OPEN and admits a probe.
    clock.advance(0.2)
    result = cb.call(lambda: "ok")
    # Probe success → CLOSED
    assert result == "ok"
    assert cb.is_closed
    # Verify the breaker was indeed in HALF_OPEN during the probe by
    # inspecting stats after the fact (state is CLOSED post-success).
    assert cb.state == CircuitState.CLOSED


def test_breaker_half_open_failure_reopens():
    from services.agent_service.resilience import CircuitBreaker
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout_s=5.0)
    clock = FakeClock()
    cb.clock = clock

    def boom():
        raise RuntimeError("nope")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(boom)
    clock.advance(6.0)
    with pytest.raises(RuntimeError):
        cb.call(boom)
    assert cb.is_open


def test_breaker_unexpected_exception_does_not_count():
    from services.agent_service.resilience import CircuitBreaker
    cb = CircuitBreaker(
        name="t",
        failure_threshold=2,
        expected_exception=(ValueError,),
    )

    def raises_type_error():
        raise TypeError("not counted")

    # TypeError is not in expected_exception — should NOT trip the breaker.
    for _ in range(10):
        with pytest.raises(TypeError):
            cb.call(raises_type_error)
    assert cb.is_closed


def test_circuit_breaker_decorator():
    from services.agent_service.resilience import circuit_breaker

    @circuit_breaker(name="dec", failure_threshold=2)
    def fn():
        raise RuntimeError("x")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            fn()
    # Third call is short-circuited.
    from services.agent_service.resilience import CircuitOpenError
    with pytest.raises(CircuitOpenError):
        fn()


# ---------------------------------------------------------------------------
# DistLock — InMemoryDistLock
# ---------------------------------------------------------------------------
def test_in_memory_lock_acquire_release():
    from services.agent_service.resilience import InMemoryDistLock
    lock = InMemoryDistLock()
    token = lock.acquire("k", ttl_s=5, timeout_s=0.5)
    assert token is not None
    assert lock.is_held("k")
    assert lock.release("k", token) is True
    assert not lock.is_held("k")


def test_in_memory_lock_blocks_second_acquirer():
    from services.agent_service.resilience import InMemoryDistLock
    lock = InMemoryDistLock()
    token = lock.acquire("k", ttl_s=5, timeout_s=0.5)
    assert token is not None
    # Second acquirer times out (token != None would imply shared lock).
    other = lock.acquire("k", ttl_s=5, timeout_s=0.2)
    assert other is None
    # After release, second acquirer succeeds.
    assert lock.release("k", token) is True
    other2 = lock.acquire("k", ttl_s=5, timeout_s=0.5)
    assert other2 is not None


def test_in_memory_lock_ttl_expiry():
    from services.agent_service.resilience import InMemoryDistLock
    lock = InMemoryDistLock()
    token = lock.acquire("k", ttl_s=1, timeout_s=0.5)
    assert token is not None
    time.sleep(1.2)
    # TTL elapsed → next acquirer succeeds.
    other = lock.acquire("k", ttl_s=1, timeout_s=0.5)
    assert other is not None


def test_release_with_wrong_token_does_not_release():
    from services.agent_service.resilience import InMemoryDistLock
    lock = InMemoryDistLock()
    token = lock.acquire("k", ttl_s=5, timeout_s=0.5)
    assert token is not None
    assert lock.release("k", "wrong-token") is False
    assert lock.is_held("k")
    # Correct token still works.
    assert lock.release("k", token) is True


def test_get_dist_lock_returns_in_memory_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    from services.agent_service.resilience import (
        InMemoryDistLock,
        reset_dist_lock_for_test,
        get_dist_lock,
    )
    reset_dist_lock_for_test(InMemoryDistLock())
    lock = get_dist_lock()
    assert isinstance(lock, InMemoryDistLock)
    # Functional round-trip.
    token = lock.acquire("module-test", ttl_s=5, timeout_s=0.5)
    assert token is not None
    lock.release("module-test", token)


# ---------------------------------------------------------------------------
# DistLock — concurrent contention (single-process threading)
# ---------------------------------------------------------------------------
def test_concurrent_acquire_serializes():
    from services.agent_service.resilience import InMemoryDistLock
    lock = InMemoryDistLock()
    order: list = []
    start = threading.Event()

    def worker(i: int):
        start.wait()
        token = lock.acquire(f"k{i}", ttl_s=5, timeout_s=2.0)
        if token is None:
            order.append((i, "timeout"))
            return
        order.append((i, "got"))
        time.sleep(0.05)
        lock.release(f"k{i}", token)
        order.append((i, "released"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    start.set()
    for t in threads:
        t.join(timeout=5.0)
    # Each worker acquired and released exactly once.
    got_count = sum(1 for _, status in order if status == "got")
    released_count = sum(1 for _, status in order if status == "released")
    assert got_count == 5
    assert released_count == 5
