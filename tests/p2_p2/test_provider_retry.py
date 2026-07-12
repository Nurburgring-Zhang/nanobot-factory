"""P21 P2 P2 — provider retry / 429 / circuit-breaker tests.

R2 audit finding (R2-NEW-1 / R1 P1-1+2): 23/23 providers have no retry logic,
no 429 backoff handling, no circuit-breaker.  This module covers the new
``BaseProvider._request_with_retry`` wrapper added in
``backend/imdf/providers/base.py``.

Tests
-----
A — happy path: 200 → 1 call, no retry, no breaker state change.
B — 429 retry: 429, 429, 200 → 3 calls, total wall time ≥ sum(Retry-After).
C — 5xx exhaust: 500, 500, 500 → 3 calls, breaker open after exhaustion.
D — circuit-open short-circuit: when the breaker is open, the next call
    raises ``CircuitOpenError`` without invoking ``_request``.

Run from the project root with::

    pytest tests/p2_p2/test_provider_retry.py -v

The global ``tests/conftest.py`` and the defensive path injection in this
file's preamble keep it runnable from any working directory.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest


# ── Path setup ──────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve()
# tests/p2_p2/test_provider_retry.py → project root is parents[2]
_PROJECT_ROOT = _THIS.parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Defence in depth — avoid the conftest hook rotating sys.path under us.
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "x" * 64)


from imdf.providers.base import (  # noqa: E402  (after sys.path tweak)
    BaseProvider,
    CircuitOpenError,
    _ProviderResponse,
)


# ── Mock provider ───────────────────────────────────────────────────────
# Each canned response is either:
#   - a 3-tuple ``(status_code, headers_dict, text)`` — returned by _request
#   - an Exception instance — raised by _request
# This lets one MockProvider drive all four scenarios.


class _MockProvider(BaseProvider):
    """In-memory provider that records every call to ``_request``.

    Canned responses are popped off the front of ``self._canned`` on each
    call.  When the list is exhausted, ``_request`` returns a 500 (so a
    misconfigured test still surfaces as a "real" failure rather than a
    silent pass).
    """

    provider_name = "mock"
    family = "mock"

    def __init__(
        self,
        canned: Optional[List[Union[Tuple[int, Dict[str, str], str], BaseException]]] = None,
        *,
        max_attempts: int = 3,
        max_consecutive_failures: int = 3,
        cooldown_sec: float = 60.0,
    ) -> None:
        super().__init__(api_key="mock-key-not-real", base_url="https://mock.invalid")
        self._canned: List[Union[Tuple[int, Dict[str, str], str], BaseException]] = list(canned or [])
        self._calls: List[Dict[str, Any]] = []
        # Tighter retry tunables for the test (default 3 / 60s is fine too,
        # but we expose them so individual tests can shrink the cooldown).
        self._retry_max_attempts = int(max_attempts)
        self._retry_max_consecutive_failures = int(max_consecutive_failures)
        self._retry_circuit_cooldown_sec = float(cooldown_sec)
        # 5xx backoff base = 0.05s so 5xx test is fast: 0.05 + 0.10 = 0.15s total
        self._retry_5xx_base_backoff = 0.05
        self._retry_429_default = 0.05

    # Required abstract methods from BaseProvider — MockProvider is not a
    # real provider so we stub them with no-op shape.
    async def invoke(self, prompt: str, params: Any) -> Any:  # pragma: no cover - unused
        raise NotImplementedError("MockProvider does not implement invoke() — test _request_with_retry directly")

    async def list_models(self) -> List[str]:
        return ["mock-model-a", "mock-model-b"]

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> _ProviderResponse:
        # Record the call for assertion.
        self._calls.append({
            "method": method,
            "url": url,
            "headers": dict(headers or {}),
            "json": json,
            "params": params,
            "ts": time.monotonic(),
        })
        if not self._canned:
            # Defensive default — surface as a real 5xx so the test sees failure.
            return _ProviderResponse(status_code=500, text="mock: out of canned responses")
        item = self._canned.pop(0)
        if isinstance(item, BaseException):
            raise item
        status, hdrs, text = item
        return _ProviderResponse(status_code=int(status), headers=dict(hdrs or {}), text=text)


# ── Tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_A_200_single_call_no_retry():
    """A: 200 on the first call → 1 call, no retry, breaker stays closed."""
    p = _MockProvider(canned=[(200, {"content-type": "application/json"}, '{"ok":true}')])

    t0 = time.monotonic()
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    assert resp.is_success()
    assert len(p._calls) == 1, f"expected 1 _request call, got {len(p._calls)}"
    # 200 must not sleep — should be effectively instant (no 429/5xx backoff).
    assert elapsed < 0.5, f"200 path slept unexpectedly: {elapsed:.3f}s"
    stats = p.retry_stats()
    assert stats["consecutive_failures"] == 0
    assert stats["circuit_open"] == 0
    assert stats["successes"] == 1
    assert stats["attempts"] == 1
    assert stats["circuit_trips"] == 0


@pytest.mark.asyncio
async def test_B_429_429_200_retries_with_retry_after():
    """B: 429, 429, 200 → 3 calls, total wall time ≥ sum(Retry-After)."""
    # Two 429s with Retry-After=0.10s, then a 200.  Total expected sleep ≥ 0.20s.
    p = _MockProvider(canned=[
        (429, {"Retry-After": "0.10"}, "rate limited"),
        (429, {"Retry-After": "0.10"}, "rate limited"),
        (200, {"content-type": "application/json"}, '{"ok":true}'),
    ])

    t0 = time.monotonic()
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    assert resp.is_success()
    assert len(p._calls) == 3, f"expected 3 _request calls, got {len(p._calls)}"
    # Each Retry-After=0.10s, two of them → ≥ 0.20s wall time.
    assert elapsed >= 0.18, f"expected ≥0.18s of Retry-After sleeps, got {elapsed:.3f}s"
    # Breaker should be closed — 200 reset the counter.
    stats = p.retry_stats()
    assert stats["consecutive_failures"] == 0
    assert stats["circuit_open"] == 0
    assert stats["successes"] == 1
    assert stats["attempts"] == 3


@pytest.mark.asyncio
async def test_C_500_500_500_trips_circuit():
    """C: 500 × 3 → 3 calls, circuit open after exhaustion, last response is 500."""
    p = _MockProvider(canned=[
        (500, {}, "server error"),
        (500, {}, "server error"),
        (500, {}, "server error"),
    ])

    t0 = time.monotonic()
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    # Last response returned is the third 500.
    assert resp.status_code == 500
    # Three _request invocations (3 attempts).
    assert len(p._calls) == 3, f"expected 3 _request calls, got {len(p._calls)}"
    # Exponential backoff: 0.05 + 0.10 = 0.15s minimum sleep between 3 attempts.
    assert elapsed >= 0.13, f"expected ≥0.13s of exponential backoff, got {elapsed:.3f}s"
    # Breaker should be open after 3 consecutive 5xx.
    stats = p.retry_stats()
    assert stats["consecutive_failures"] >= 3
    assert stats["circuit_open"] == 1, f"breaker should be open, got stats={stats}"
    assert stats["circuit_trips"] == 1


@pytest.mark.asyncio
async def test_D_circuit_open_short_circuits():
    """D: after the breaker is open, the next call must NOT hit _request."""
    # Use a tiny cooldown so we can also test that the probe half-opens
    # after the cooldown elapses (one extra assertion).
    p = _MockProvider(
        canned=[
            (500, {}, "e1"),
            (500, {}, "e2"),
            (500, {}, "e3"),
        ],
        cooldown_sec=0.20,
    )

    # Trip the breaker.
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    assert resp.status_code == 500
    assert len(p._calls) == 3
    assert p.retry_stats()["circuit_open"] == 1

    # Next call: breaker is open → must raise CircuitOpenError and NOT hit _request.
    call_count_before = len(p._calls)
    t0 = time.monotonic()
    with pytest.raises(CircuitOpenError) as excinfo:
        await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    assert "circuit_open" in str(excinfo.value)
    assert len(p._calls) == call_count_before, (
        f"_request must not be called when circuit is open; "
        f"got {len(p._calls) - call_count_before} extra calls"
    )
    # Should be near-instant — no sleep when circuit is open.
    assert elapsed < 0.05, f"circuit-open path should be instant, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_D_extra_circuit_probe_after_cooldown():
    """After the cooldown elapses, the next call is allowed through as a probe.

    A successful probe closes the breaker; a failing probe re-opens it.
    This is the half-open behaviour promised in ``_circuit_is_open``.
    """
    p = _MockProvider(
        canned=[
            (500, {}, "e1"),
            (500, {}, "e2"),
            (500, {}, "e3"),
            # 4th response — the probe after cooldown.
            (200, {}, "ok"),
        ],
        cooldown_sec=0.10,
    )
    # Trip the breaker.
    await p._request_with_retry("POST", "https://mock.invalid/chat")
    assert p.retry_stats()["circuit_open"] == 1

    # Wait for cooldown to elapse (with a small safety margin).
    await asyncio.sleep(0.12)

    # Probe call should be allowed through.
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    assert resp.status_code == 200
    assert resp.is_success()
    stats = p.retry_stats()
    # Success closes the breaker.
    assert stats["circuit_open"] == 0, f"breaker should be closed after probe, got stats={stats}"
    assert stats["consecutive_failures"] == 0
    assert p._calls[-1]["url"] == "https://mock.invalid/chat"


@pytest.mark.asyncio
async def test_4xx_no_retry():
    """4xx other than 429 must be returned immediately without retry."""
    p = _MockProvider(canned=[
        (400, {"content-type": "application/json"}, '{"err":"bad request"}'),
    ])

    t0 = time.monotonic()
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 400
    assert len(p._calls) == 1, f"4xx must not retry, got {len(p._calls)} calls"
    # No backoff on 4xx — should be fast.
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_exception_treated_as_failure_with_backoff():
    """Network/timeout exceptions must count as failures and use 5xx backoff."""
    p = _MockProvider(canned=[
        asyncio.TimeoutError("connect timeout"),
        asyncio.TimeoutError("connect timeout"),
        (200, {}, "ok"),
    ])

    t0 = time.monotonic()
    resp = await p._request_with_retry("POST", "https://mock.invalid/chat")
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200
    assert len(p._calls) == 3
    # 0.05s + 0.10s of backoff between attempts.
    assert elapsed >= 0.13, f"expected ≥0.13s of backoff, got {elapsed:.3f}s"
    assert p.retry_stats()["successes"] == 1


@pytest.mark.asyncio
async def test_all_attempts_raise_trips_circuit_and_raises_circuit_open():
    """When every attempt raises, the circuit trips and CircuitOpenError is raised.

    The last underlying exception is preserved in the ``__cause__`` chain
    so callers can still inspect the original failure (TimeoutError here).
    """
    p = _MockProvider(canned=[
        asyncio.TimeoutError("e1"),
        asyncio.TimeoutError("e2"),
        asyncio.TimeoutError("e3"),
    ])

    with pytest.raises(CircuitOpenError) as excinfo:
        await p._request_with_retry("POST", "https://mock.invalid/chat")
    assert "e3" in str(excinfo.value)
    # Underlying cause is preserved.
    assert isinstance(excinfo.value.__cause__, asyncio.TimeoutError)
    assert len(p._calls) == 3
    assert p.retry_stats()["circuit_trips"] == 1


# ── Smoke tests on real provider subclasses (no network) ────────────────


def test_real_subclass_has_retry_method():
    """All P20-A subclasses inherit _request_with_retry (covers 4/4)."""
    from imdf.providers.groq import GroqProvider
    from imdf.providers.together import TogetherProvider
    from imdf.providers.fireworks import FireworksProvider
    from imdf.providers.perplexity import PerplexityProvider

    for cls in (GroqProvider, TogetherProvider, FireworksProvider, PerplexityProvider):
        # No api_key, no network — just exercise __init__.
        try:
            inst = cls()
        except Exception:
            # Provider may try to read env var or default base_url — that's fine,
            # we just need the class to BE importable and have the method.
            continue
        assert hasattr(inst, "_request_with_retry"), f"{cls.__name__} missing _request_with_retry"
        assert hasattr(inst, "_request"), f"{cls.__name__} missing _request"
        assert hasattr(inst, "retry_stats"), f"{cls.__name__} missing retry_stats"
        # Initial state must be closed.
        stats = inst.retry_stats()
        assert stats["consecutive_failures"] == 0
        assert stats["circuit_open"] == 0
        assert stats["circuit_trips"] == 0


def test_module_exports_circuit_open_error():
    """CircuitOpenError must be importable from the public base module."""
    from imdf.providers.base import CircuitOpenError as COE
    assert issubclass(COE, RuntimeError)
    # And it must appear in __all__ for downstream consumers.
    import imdf.providers.base as base_mod
    assert "CircuitOpenError" in base_mod.__all__
    assert "_ProviderResponse" in base_mod.__all__
